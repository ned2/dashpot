"""Preview and perform the Cleanup of a Branch or a Worktree.

A Cleanup ([ADR 0019](../../docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md))
begins with a read-only preview: every concrete target a person could select
— the local Branch, the Branch at each remote, the Worktree — with its own
integration fact, blockers, consequences, and the value confirmation must
find unchanged. Integration is the gate that makes a Branch target eligible;
the selection is the authority.

Performing a Cleanup re-inspects first and performs nothing when the preview
changed. A local Branch is deleted with the atomic ``update-ref -d`` old-value
check; a Worktree with an unforced ``git worktree remove``; the targets run in
the order remote, Worktree, local Branch, and after a refused or unknown
outcome nothing further is attempted. Every target reports its own outcome and
a deleted one names the command that recreates it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import computed_field

from .commands import non_interactive_runner
from .errors import DashpotError
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
    lines = [f"{verb:<16}{preview.subject}", f"{'Repository':<16}{preview.anchor}"]
    for refusal in preview.refusals:
        lines.append(f"{'Refused':<16}{refusal}")
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


# --- Performing -----------------------------------------------------------


Outcome = Literal["deleted", "already-absent", "refused", "unknown"]
CLEANUP_ENVIRONMENT: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
# Remote first, so a lease refusal can still revise the preview; the Worktree
# before the Branch it has checked out.
_ORDER: Mapping[TargetKind, int] = {
    "remote-branch": 0,
    "worktree": 1,
    "local-branch": 2,
}
CHANGED_SINCE_PREVIEW = (
    "the observed state changed since the preview; confirm again against the "
    "revised preview"
)


class CleanupError(DashpotError, RuntimeError):
    """A Cleanup command refused before previewing: a usage-shaped mistake."""


@dataclass(frozen=True, slots=True)
class CleanupConfirmation:
    """What a person confirmed: the previewed facts and the targets selected.

    ``fingerprint`` is the preview's, ``selected`` names targets by identity,
    and ``delete_ignored`` acknowledges that a Worktree's ignored content goes
    with it.
    """

    request: CleanupRequest
    fingerprint: str
    selected: tuple[str, ...]
    delete_ignored: bool = False


class TargetResult(PublishedModel):
    """What one selected target came to."""

    identity: str
    kind: TargetKind
    label: str
    expected: str
    outcome: Outcome
    detail: str
    # The command that recreates a deleted target while Git still has the commit.
    recovery: str | None = None


class CleanupReport(PublishedModel):
    """What one confirmed Cleanup did, or why it did nothing.

    ``performed`` is false when the observed state changed since the preview
    (``changed``, with the fresh ``preview`` to confirm again), when the
    selection was refused (``refusals``), or on a dry run, which lists the
    targets it would have attempted, in order, as ``planned``.
    """

    kind: Literal["branch", "worktree"]
    subject: str
    anchor: str
    dry_run: bool
    performed: bool
    preview: CleanupPreview
    changed: bool = False
    refusals: LaxSequence[str] = ()
    planned: LaxSequence[str] = ()
    results: LaxSequence[TargetResult] = ()

    @computed_field
    @property
    def succeeded(self) -> bool:
        """Every selected target was deleted or was already absent."""
        return self.performed and all(
            result.outcome in {"deleted", "already-absent"} for result in self.results
        )


def cleanup_git(timeout: float) -> Git:
    """The production adapter for a Cleanup: non-interactive, with Dashpot's timeout."""
    return Git(Path.cwd(), timeout, non_interactive_runner(CLEANUP_ENVIRONMENT))


def perform_cleanup(
    confirmation: CleanupConfirmation,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    protected: Sequence[Path] = (),
    timeout: float = 10,
    git: Git | None = None,
    dry_run: bool = False,
) -> CleanupReport:
    """Perform a confirmed Cleanup after re-inspecting it, or say why not.

    The preview is taken again and compared by fingerprint: anything observed
    differently since the person confirmed means nothing is performed and the
    revised preview is returned for another confirmation. A dry run stops
    after validating the selection. Targets run in order — remote, Worktree,
    local Branch — and after a refused or unknown outcome the rest are
    reported as not attempted rather than tried on changed ground.
    """
    adapter = git if git is not None else cleanup_git(timeout)
    preview = inspect_cleanup(
        confirmation.request,
        lookup=lookup,
        lock_probe=lock_probe,
        protected=protected,
        timeout=timeout,
        git=adapter,
    )
    if preview.fingerprint != confirmation.fingerprint:
        return _report(
            preview, dry_run, changed=True, refusals=(CHANGED_SINCE_PREVIEW,)
        )
    refusals, ordered = _select(preview, confirmation)
    if refusals:
        return _report(preview, dry_run, refusals=tuple(refusals))
    if dry_run:
        return _report(
            preview, dry_run, planned=tuple(target.identity for target in ordered)
        )
    scoped = adapter.at(Path(preview.anchor))
    results: list[TargetResult] = []
    halted: TargetResult | None = None
    for target in ordered:
        if halted is not None:
            results.append(
                _result(
                    target,
                    "refused",
                    f"not attempted: {halted.label} was {halted.outcome}",
                )
            )
            continue
        result = _perform(scoped, target)
        results.append(result)
        if result.outcome in {"refused", "unknown"}:
            halted = result
    return _report(preview, dry_run, performed=True, results=tuple(results))


def _report(
    preview: CleanupPreview,
    dry_run: bool,
    *,
    performed: bool = False,
    changed: bool = False,
    refusals: Sequence[str] = (),
    planned: Sequence[str] = (),
    results: Sequence[TargetResult] = (),
) -> CleanupReport:
    return CleanupReport(
        kind=preview.kind,
        subject=preview.subject,
        anchor=preview.anchor,
        dry_run=dry_run,
        performed=performed,
        preview=preview,
        changed=changed,
        refusals=tuple(refusals),
        planned=tuple(planned),
        results=tuple(results),
    )


def _select(
    preview: CleanupPreview, confirmation: CleanupConfirmation
) -> tuple[list[str], list[CleanupTarget]]:
    """The selected targets in performing order, or every reason to refuse them."""
    refusals = list(preview.refusals)
    if not confirmation.selected:
        refusals.append("no target is selected")
    chosen: list[CleanupTarget] = []
    for identity in confirmation.selected:
        target = preview.target(identity)
        if target is None:
            refusals.append(f"{identity} is not a target of this preview")
            continue
        if not target.available:
            reasons = "; ".join(blocker.detail for blocker in target.blockers)
            refusals.append(f"{target.label} is unavailable: {reasons}")
            continue
        if target.requires is not None and target.requires not in confirmation.selected:
            refusals.append(
                f"{target.label} can only be deleted together with {target.requires}"
            )
            continue
        chosen.append(target)
    if (
        preview.ignored
        and any(target.kind == "worktree" for target in chosen)
        and not confirmation.delete_ignored
    ):
        refusals.append(
            f"removing the Worktree deletes {len(preview.ignored)} ignored path(s) "
            f"inside it, which must be acknowledged"
        )
    chosen.sort(key=lambda target: _ORDER[target.kind])
    return refusals, chosen


def _perform(git: Git, target: CleanupTarget) -> TargetResult:
    if target.kind == "local-branch":
        return _delete_local_branch(git, target)
    if target.kind == "worktree":
        return _remove_worktree(git, target)
    return _result(
        target, "refused", "deleting a Branch at a remote is not available yet"
    )


def _delete_local_branch(git: Git, target: CleanupTarget) -> TargetResult:
    """Delete the ref only if it is still at the previewed commit."""
    refname = target.ref or ""
    name = refname.removeprefix(LOCAL_REF_PREFIX)
    recovery = f"git branch {name} {target.expected}"
    try:
        result = git.run("update-ref", "-d", refname, target.expected)
    except GitError as exc:
        return _result(
            target,
            "unknown",
            f"git update-ref did not complete: {exc.detail}; check with: "
            f"git rev-parse --verify {refname}",
            recovery,
        )
    if result.returncode != 0:
        if not _ref_exists(git, refname):
            return _result(target, "already-absent", f"{refname} was already gone")
        return _result(
            target, "refused", _last_line(result.stderr) or "git update-ref refused"
        )
    # The Branch's configuration goes with its ref; ``update-ref`` leaves it,
    # and a Branch that had none makes the removal a no-op.
    with contextlib.suppress(GitError):
        git.run("config", "--remove-section", f"branch.{name}")
    return _result(
        target, "deleted", f"deleted {refname} at {target.expected[:7]}", recovery
    )


def _remove_worktree(git: Git, target: CleanupTarget) -> TargetResult:
    """Remove the Worktree without force, so Git refuses what changed underneath."""
    path = target.path or ""
    recovery = (
        f"git worktree add {path} {target.ref.removeprefix(LOCAL_REF_PREFIX)}"
        if target.ref
        else f"git worktree add --detach {path} {target.expected}"
    )
    try:
        result = git.run("worktree", "remove", "--", path)
    except GitError as exc:
        return _result(
            target,
            "unknown",
            f"git worktree remove did not complete: {exc.detail}; check with: "
            f"git worktree list",
            recovery,
        )
    if result.returncode != 0:
        if not Path(path).exists() and not _registered(git, path):
            return _result(target, "already-absent", f"{path} was already gone")
        return _result(
            target,
            "refused",
            _last_line(result.stderr) or "git worktree remove refused",
        )
    return _result(target, "deleted", f"removed {path}", recovery)


def _ref_exists(git: Git, refname: str) -> bool:
    try:
        return git.maybe("rev-parse", "--verify", "--quiet", refname) is not None
    except GitError:
        # Not knowing is not absence: the target is reported refused, not gone.
        return True


def _registered(git: Git, path: str) -> bool:
    try:
        records = git.worktree_records()
    except GitError:
        return True
    return any(
        record.get("worktree") and Path(record["worktree"]).resolve() == Path(path)
        for record in records
    )


def _result(
    target: CleanupTarget, outcome: Outcome, detail: str, recovery: str | None = None
) -> TargetResult:
    return TargetResult(
        identity=target.identity,
        kind=target.kind,
        label=target.label,
        expected=target.expected,
        outcome=outcome,
        detail=detail,
        recovery=recovery,
    )


def _last_line(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def describe_cleanup_report(report: CleanupReport) -> list[str]:
    """Render a report as lines for a person: what happened to each target."""
    verb = "Delete Branch" if report.kind == "branch" else "Remove Worktree"
    lines = [f"{verb:<16}{report.subject}", f"{'Repository':<16}{report.anchor}"]
    if report.changed:
        lines.append(f"{'Changed':<16}{CHANGED_SINCE_PREVIEW}")
        lines.extend(describe_cleanup_preview(report.preview)[2:])
        return lines
    lines.extend(f"{'Refused':<16}{refusal}" for refusal in report.refusals)
    if report.refusals:
        return lines
    if report.dry_run:
        lines.append(f"{'Dry run':<16}would attempt, in order")
        for index, identity in enumerate(report.planned, 1):
            target = report.preview.target(identity)
            label = target.label if target is not None else identity
            lines.append(f"  {index}. {label} {_where(target)}".rstrip())
        return lines
    lines.append("Results")
    for result in report.results:
        target = report.preview.target(result.identity)
        lines.append(
            f"  {result.outcome:<15}{result.label} {_where(target)} "
            f"@ {result.expected[:7]}"
        )
        lines.append(f"      {result.detail}")
        if result.recovery and result.outcome == "deleted":
            lines.append(f"      recover: {result.recovery}")
    return lines


def _where(target: CleanupTarget | None) -> str:
    if target is None:
        return ""
    if target.kind == "worktree":
        return target.path or ""
    return target.ref or ""
