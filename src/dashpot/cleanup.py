"""Preview the Cleanup of a Branch or a Worktree without mutating anything.

A Cleanup ([ADR 0019](../../docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md))
begins with a read-only preview: every concrete target a person could select
— the local Branch, the Branch at each remote, the Worktree — with its own
integration fact, blockers, consequences, and the value confirmation must
find unchanged. Integration is the gate that makes a Branch target eligible;
the selection is the authority. Nothing here runs a Git command that writes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import computed_field

from .git import Git, GitError
from .models import LaxSequence, PublishedModel
from .processes import ProcessLookup, host_process_lookup
from .repository import (
    LOCAL_REF_PREFIX,
    ORIGIN_HEAD_REF,
    REMOTE_REF_PREFIX,
    LockHolderProbe,
    assess_content_integration,
    choose_integration_ref,
    last_fetched_at,
    worktree_root,
)
from .worktrees import (
    LocatedWorktree,
    RemovalObstacle,
    assess_detached_head_preservation,
    assess_worktree_occupancy,
    assess_worktree_safety,
    ignored_content,
    locate_worktree,
)

TargetKind = Literal["local-branch", "remote-branch", "worktree"]
BlockerKind = Literal[
    "integration-branch",
    "checked-out",
    "unintegrated",
    "unknown-integration",
    "remote-mapping",
    "push-url",
    "main-worktree",
    "protected",
    "unavailable",
    "dirty",
    "locked",
    "agent-session",
    "agent-run",
    "work-store",
    "detached",
]
IntegrationState = Literal[
    "integrated", "content-integrated", "unintegrated", "unknown"
]
# The Worktree obstacles that block removing the Worktree itself; the Branch
# ones (unpushed, unmerged) belong to the Branch target's own gate.
_WORKTREE_BLOCKERS: Mapping[str, BlockerKind] = {
    "main-worktree": "main-worktree",
    "dirty": "dirty",
    "locked": "locked",
    "agent-session": "agent-session",
    "agent-run": "agent-run",
    "work-store": "work-store",
    "detached": "detached",
}
CANONICAL_FETCH_REFSPEC = "+refs/heads/*:refs/remotes/{remote}/*"


class CleanupBlocker(PublishedModel):
    """One reason a target is unavailable, with the command a person could run."""

    kind: BlockerKind
    detail: str
    command: str | None = None


class IntegrationFact(PublishedModel):
    """How one concrete ref stands against the Integration Branch."""

    integration_ref: str | None
    unintegrated_commits: int | None
    content_integrated: bool | None

    @computed_field
    @property
    def state(self) -> IntegrationState:
        if self.unintegrated_commits is None:
            return "unknown"
        if self.unintegrated_commits == 0:
            return "integrated"
        if self.content_integrated:
            return "content-integrated"
        return "unintegrated"


class CleanupTarget(PublishedModel):
    """One concrete thing a Cleanup could remove, starting unselected.

    ``expected`` is the value confirmation must observe again — a ref's
    commit, or a Worktree's HEAD — before anything is performed. A target
    with ``requires`` can only be selected together with that other target:
    the attached Branch of a Worktree is deletable once the Worktree is gone.
    """

    identity: str
    kind: TargetKind
    label: str
    expected: str
    ref: str | None = None
    remote: str | None = None
    path: str | None = None
    integration: IntegrationFact | None = None
    # When the facts about a remote were last fetched; a Remote Branch is only
    # ever known through its Remote-Tracking Branch.
    observed_at: str | None = None
    requires: str | None = None
    blockers: LaxSequence[CleanupBlocker] = ()
    consequences: LaxSequence[str] = ()

    @computed_field
    @property
    def available(self) -> bool:
        return not self.blockers


class CleanupPreview(PublishedModel):
    """What a Cleanup of one Branch or Worktree could remove, and why not.

    ``fingerprint`` summarises every observed fact the targets rest on;
    confirmation compares it with a fresh preview's and performs nothing when
    they differ. ``ignored`` lists the ignored paths a Worktree removal would
    delete, which a person acknowledges separately.
    """

    kind: Literal["branch", "worktree"]
    subject: str
    anchor: str
    targets: LaxSequence[CleanupTarget] = ()
    ignored: LaxSequence[str] = ()
    refusals: LaxSequence[str] = ()
    fingerprint: str = ""

    @property
    def selectable(self) -> tuple[CleanupTarget, ...]:
        return tuple(target for target in self.targets if target.available)

    def target(self, identity: str) -> CleanupTarget | None:
        for target in self.targets:
            if target.identity == identity:
                return target
        return None


@dataclass(frozen=True, slots=True)
class BranchCleanupRequest:
    """Preview deleting the Branch ``name`` at the Repository of ``anchor``."""

    anchor: Path
    name: str


@dataclass(frozen=True, slots=True)
class WorktreeCleanupRequest:
    """Preview removing the Worktree at ``path`` of the Repository ``current`` is in."""

    current: Path
    path: Path


CleanupRequest = BranchCleanupRequest | WorktreeCleanupRequest


def inspect_cleanup(
    request: CleanupRequest,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    protected: Sequence[Path] = (),
    timeout: float = 10,
    git: Git | None = None,
) -> CleanupPreview:
    """Preview a Cleanup: every concrete target, its gate, and what would follow.

    ``protected`` names Worktrees that are never removable — the checkout
    Dashpot runs from and the configured Repository Anchors — since removing
    one takes the observer's own ground away.
    """
    adapter = git if git is not None else Git(Path.cwd(), timeout)
    if isinstance(request, BranchCleanupRequest):
        return _inspect_branch(request, adapter)
    return _inspect_worktree(request, adapter, lookup, lock_probe, protected, timeout)


# --- Branch ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RefIndex:
    """Every Branch ref of a Repository: commit, commit time, and origin/HEAD."""

    commits: Mapping[str, str]
    committed_at: Mapping[str, str]
    origin_head: str | None

    @classmethod
    def read(cls, git: Git) -> _RefIndex:
        records = git.records(
            "refs/heads",
            "refs/remotes",
            fields=(
                "%(refname)",
                "%(objectname)",
                "%(committerdate:iso-strict)",
                "%(symref)",
            ),
        )
        commits: dict[str, str] = {}
        committed_at: dict[str, str] = {}
        origin_head: str | None = None
        for refname, commit, committed, symref in records:
            if refname == ORIGIN_HEAD_REF:
                origin_head = symref or None
                continue
            if symref:
                continue
            commits[refname] = commit
            committed_at[refname] = committed
        return cls(commits, committed_at, origin_head)

    def integration_ref(self) -> str | None:
        return choose_integration_ref(self.origin_head, self.commits)


def _inspect_branch(request: BranchCleanupRequest, git: Git) -> CleanupPreview:
    anchor = worktree_root(request.anchor, git)
    scoped = git.at(anchor)
    name = request.name
    refs = _RefIndex.read(scoped)
    integration_ref = refs.integration_ref()
    targets: list[CleanupTarget] = []
    local_ref = f"{LOCAL_REF_PREFIX}{name}"
    if local_ref in refs.commits:
        targets.append(
            _local_branch_target(
                scoped,
                name,
                refs,
                integration_ref,
                checked_out_at=_checked_out_at(scoped, local_ref),
            )
        )
    fetched = last_fetched_at(anchor, scoped)
    for remote in _remotes(scoped):
        tracking = f"{REMOTE_REF_PREFIX}{remote}/{name}"
        if tracking in refs.commits:
            targets.append(
                _remote_branch_target(
                    scoped, name, remote, refs, integration_ref, fetched
                )
            )
    refusals = () if targets else (f"no Branch named {name} at {anchor}",)
    return _preview("branch", name, anchor, targets, (), refusals)


def _local_branch_target(
    git: Git,
    name: str,
    refs: _RefIndex,
    integration_ref: str | None,
    *,
    checked_out_at: Path | None,
    requires: str | None = None,
) -> CleanupTarget:
    refname = f"{LOCAL_REF_PREFIX}{name}"
    commit = refs.commits[refname]
    fact = _integration_fact(
        git, integration_ref, refname, refs.committed_at.get(refname)
    )
    blockers = _integration_branch_blockers(refname, name, integration_ref, None)
    if checked_out_at is not None:
        blockers.append(
            CleanupBlocker(
                kind="checked-out",
                detail=f"checked out at {checked_out_at}; remove that Worktree first",
            )
        )
    blockers.extend(_integration_blockers(fact, refname))
    consequences = [
        f"deletes {refname} at {commit[:7]}; recreate with: git branch {name} {commit}"
    ]
    if requires is not None:
        consequences[0] = "after the Worktree is removed, " + consequences[0]
    consequences.extend(_content_consequence(fact))
    return CleanupTarget(
        identity=f"local:{refname}",
        kind="local-branch",
        label="Local Branch",
        expected=commit,
        ref=refname,
        integration=fact,
        requires=requires,
        blockers=tuple(blockers),
        consequences=tuple(consequences),
    )


def _remote_branch_target(
    git: Git,
    name: str,
    remote: str,
    refs: _RefIndex,
    integration_ref: str | None,
    fetched: str | None,
) -> CleanupTarget:
    tracking = f"{REMOTE_REF_PREFIX}{remote}/{name}"
    commit = refs.commits[tracking]
    fact = _integration_fact(
        git, integration_ref, tracking, refs.committed_at.get(tracking)
    )
    blockers = _integration_branch_blockers(
        tracking, name, integration_ref, refs.origin_head
    )
    blockers.extend(_remote_blockers(git, remote))
    blockers.extend(_integration_blockers(fact, tracking))
    observed = f" as of the last fetch at {fetched}" if fetched else ""
    consequences = [
        f"deletes {name} at {remote}, leased on {tracking} at {commit[:7]}"
        f"{observed}; recreate with: git push {remote} {commit}:refs/heads/{name}",
        f"Git drops {tracking} itself once the deletion is accepted",
    ]
    consequences.extend(_content_consequence(fact))
    return CleanupTarget(
        identity=f"remote:{remote}:{LOCAL_REF_PREFIX}{name}",
        kind="remote-branch",
        label=f"Branch at {remote}",
        expected=commit,
        ref=tracking,
        remote=remote,
        integration=fact,
        observed_at=fetched,
        blockers=tuple(blockers),
        consequences=tuple(consequences),
    )


def _remote_blockers(git: Git, remote: str) -> list[CleanupBlocker]:
    """The remote's configuration must map the Branch the canonical way."""
    blockers: list[CleanupBlocker] = []
    canonical = CANONICAL_FETCH_REFSPEC.format(remote=remote)
    listed = git.maybe("config", "--get-all", f"remote.{remote}.fetch")
    refspecs = [line.strip() for line in (listed or "").splitlines() if line.strip()]
    if refspecs != [canonical]:
        blockers.append(
            CleanupBlocker(
                kind="remote-mapping",
                detail=f"remote {remote} fetches "
                f"{', '.join(refspecs) if refspecs else 'nothing'} rather than the "
                f"canonical {canonical}, so its Remote-Tracking Branch does not "
                f"stand for the Branch at the remote",
            )
        )
    listed = git.maybe("remote", "get-url", "--push", "--all", remote)
    urls = [line.strip() for line in (listed or "").splitlines() if line.strip()]
    if len(urls) != 1:
        blockers.append(
            CleanupBlocker(
                kind="push-url",
                detail=f"remote {remote} has "
                f"{'no push URL' if not urls else f'{len(urls)} push URLs'}; "
                f"exactly one is needed to delete at one destination",
            )
        )
    return blockers


def _integration_branch_blockers(
    refname: str, name: str, integration_ref: str | None, origin_head: str | None
) -> list[CleanupBlocker]:
    """The Integration Branch, and every ref carrying its name, is never a target.

    ``origin/main`` may be the Integration Branch while ``refs/heads/main``
    and ``upstream/main`` are other refs of the same line of development;
    deleting any of them is not cleanup, whatever it is compared against.
    """
    if integration_ref is None:
        return []
    if refname in {integration_ref, origin_head}:
        return [
            CleanupBlocker(
                kind="integration-branch",
                detail=f"{refname} is the Integration Branch",
            )
        ]
    if name == _branch_name(integration_ref):
        return [
            CleanupBlocker(
                kind="integration-branch",
                detail=f"{refname} carries the Integration Branch's name "
                f"({integration_ref})",
            )
        ]
    return []


def _branch_name(refname: str) -> str:
    """The Branch name of a local or Remote-Tracking ref."""
    if refname.startswith(LOCAL_REF_PREFIX):
        return refname.removeprefix(LOCAL_REF_PREFIX)
    if refname.startswith(REMOTE_REF_PREFIX):
        _remote, _slash, name = refname.removeprefix(REMOTE_REF_PREFIX).partition("/")
        return name
    return refname


def _integration_fact(
    git: Git, integration_ref: str | None, refname: str, committed_at: str | None
) -> IntegrationFact:
    if integration_ref is None:
        return IntegrationFact(
            integration_ref=None, unintegrated_commits=None, content_integrated=None
        )
    count = git.count("rev-list", "--count", f"{integration_ref}..{refname}")
    content: bool | None = None
    if count:
        try:
            content = assess_content_integration(
                git, integration_ref, refname, committed_at
            )
        except GitError:
            content = None
    return IntegrationFact(
        integration_ref=integration_ref,
        unintegrated_commits=count,
        content_integrated=content,
    )


def _integration_blockers(fact: IntegrationFact, refname: str) -> list[CleanupBlocker]:
    state = fact.state
    if state == "unknown":
        if fact.integration_ref is None:
            detail = (
                "no Integration Branch could be chosen: origin/HEAD is not set and "
                "there is no unique local main or master Branch"
            )
        else:
            detail = (
                f"commits of {refname} not reachable from {fact.integration_ref} "
                f"could not be counted"
            )
        return [
            CleanupBlocker(
                kind="unknown-integration",
                detail=detail,
                command=f"git log --oneline {refname}",
            )
        ]
    if state == "unintegrated":
        return [
            CleanupBlocker(
                kind="unintegrated",
                detail=f"{fact.unintegrated_commits} commit(s) not reachable from "
                f"{fact.integration_ref}",
                command=f"git log --oneline {fact.integration_ref}..{refname}",
            )
        ]
    return []


def _content_consequence(fact: IntegrationFact) -> list[str]:
    if fact.state != "content-integrated":
        return []
    return [
        f"content is integrated, but {fact.unintegrated_commits} original commit(s) "
        f"are not reachable from {fact.integration_ref} and lose their last named ref"
    ]


def _checked_out_at(git: Git, refname: str) -> Path | None:
    for record in git.worktree_records():
        if record.get("branch") == refname and record.get("worktree"):
            return Path(record["worktree"]).resolve()
    return None


def _remotes(git: Git) -> list[str]:
    listed = git.maybe("remote")
    return [name.strip() for name in (listed or "").splitlines() if name.strip()]


# --- Worktree -------------------------------------------------------------


def _inspect_worktree(
    request: WorktreeCleanupRequest,
    git: Git,
    lookup: ProcessLookup,
    lock_probe: LockHolderProbe | None,
    protected: Sequence[Path],
    timeout: float,
) -> CleanupPreview:
    located = locate_worktree(request.current, request.path, timeout=timeout, git=git)
    path = located.path
    blockers = _worktree_blockers(located, lookup, lock_probe, protected)
    ignored = tuple(ignored_content(located.git, path))
    identity = f"worktree:{path}"
    branch = located.branch
    consequences = [f"removes {path} with git worktree remove"]
    if ignored:
        consequences.append(
            f"{len(ignored)} ignored path(s) inside it are deleted too, including "
            f"any Dashpot state, hook records, and Work Store there"
        )
    if branch is not None:
        consequences.append(
            f"the local Branch {branch} is retained unless selected as well"
        )
    targets = [
        CleanupTarget(
            identity=identity,
            kind="worktree",
            label="Worktree",
            expected=located.head,
            ref=f"{LOCAL_REF_PREFIX}{branch}" if branch is not None else None,
            path=str(path),
            blockers=tuple(blockers),
            consequences=tuple(consequences),
        )
    ]
    if branch is not None:
        refs = _RefIndex.read(located.git)
        if f"{LOCAL_REF_PREFIX}{branch}" in refs.commits:
            targets.append(
                _local_branch_target(
                    located.git,
                    branch,
                    refs,
                    refs.integration_ref(),
                    checked_out_at=None,
                    requires=identity,
                )
            )
    return _preview("worktree", str(path), located.anchor, targets, ignored, ())


def _worktree_blockers(
    located: LocatedWorktree,
    lookup: ProcessLookup,
    lock_probe: LockHolderProbe | None,
    protected: Sequence[Path],
) -> list[CleanupBlocker]:
    path = located.path
    obstacles: list[RemovalObstacle] = assess_worktree_safety(located, lock_probe)
    obstacles.extend(assess_worktree_occupancy(path, located.worktrees, lookup))
    if located.detached:
        obstacles.extend(assess_detached_head_preservation(located.git, located.head))
    blockers = [
        CleanupBlocker(kind=kind, detail=obstacle.detail, command=obstacle.command)
        for obstacle in obstacles
        if (kind := _WORKTREE_BLOCKERS.get(obstacle.kind)) is not None
    ]
    if any(path == candidate.expanduser().resolve() for candidate in protected):
        blockers.append(
            CleanupBlocker(
                kind="protected",
                detail="is the checkout Dashpot runs from or a configured "
                "Repository Anchor, which observation cannot lose",
            )
        )
    prunable = located.record.get("prunable")
    if prunable is not None:
        blockers.append(
            CleanupBlocker(
                kind="unavailable",
                detail=f"prunable: {prunable or 'no reason reported'}",
                command="git worktree prune",
            )
        )
    elif not path.is_dir():
        blockers.append(
            CleanupBlocker(
                kind="unavailable",
                detail=f"{path} does not exist",
                command="git worktree prune",
            )
        )
    return blockers


# --- Preview --------------------------------------------------------------


def _preview(
    kind: Literal["branch", "worktree"],
    subject: str,
    anchor: Path,
    targets: Sequence[CleanupTarget],
    ignored: Sequence[str],
    refusals: Sequence[str],
) -> CleanupPreview:
    facts = [
        [
            target.identity,
            target.expected,
            target.requires,
            [blocker.kind for blocker in target.blockers],
        ]
        for target in targets
    ]
    digest = hashlib.sha256(
        json.dumps([kind, subject, str(anchor), facts, list(ignored)]).encode()
    ).hexdigest()
    return CleanupPreview(
        kind=kind,
        subject=subject,
        anchor=str(anchor),
        targets=tuple(targets),
        ignored=tuple(ignored),
        refusals=tuple(refusals),
        fingerprint=digest[:16],
    )


INTEGRATION_WORDS: Mapping[IntegrationState, str] = {
    "integrated": "⊆ every commit is reachable from the Integration Branch",
    "content-integrated": "≡ the Integration Branch holds the content; "
    "the commits are not reachable",
    "unintegrated": "↑ commits are not reachable from the Integration Branch",
    "unknown": "⊘ no Integration Branch comparison is available",
}


def describe_cleanup_preview(preview: CleanupPreview) -> list[str]:
    """Render a preview as lines for a person: each target, its gate, and what follows."""
    verb = "Delete Branch" if preview.kind == "branch" else "Remove Worktree"
    lines = [f"{verb:<15}{preview.subject}", f"{'Repository':<15}{preview.anchor}"]
    for refusal in preview.refusals:
        lines.append(f"{'Refused':<15}{refusal}")
    if preview.targets:
        lines.append("Targets")
    for target in preview.targets:
        where = f" {target.ref}" if target.ref and target.kind != "worktree" else ""
        state = "available" if target.available else "unavailable"
        lines.append(f"  [ ] {target.label}{where} @ {target.expected[:7]} — {state}")
        if target.integration is not None:
            lines.append(f"      {INTEGRATION_WORDS[target.integration.state]}")
        if target.requires is not None:
            lines.append(f"      only together with {target.requires}")
        for blocker in target.blockers:
            lines.append(f"      blocked: {blocker.kind}: {blocker.detail}")
            if blocker.command:
                lines.append(f"          run: {blocker.command}")
        lines.extend(f"      → {consequence}" for consequence in target.consequences)
    if preview.ignored:
        lines.append(
            "Ignored content (deleted with the Worktree, acknowledge to proceed)"
        )
        lines.extend(f"  {path}" for path in preview.ignored)
    return lines
