"""Inspect Cleanup targets without mutating their Repository."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from ...core.git import Git
from ...core.model import IntegrationState
from ...core.worktree_paths import same_path, worktree_root
from ...sessions.processes import ProcessLookup, host_process_lookup
from ..repository import (
    LOCAL_REF_PREFIX,
    REMOTE_REF_PREFIX,
    LockHolderProbe,
    RefIndex,
    branch_name,
    last_fetched_at,
)
from ..worktrees.records import checked_out_at
from .obstacles import (
    NO_INTEGRATION_BRANCH,
    LocatedWorktree,
    assess_detached_head_preservation,
    assess_worktree_occupancy,
    assess_worktree_safety,
    ignored_content,
    integration_fact,
    locate_worktree,
)
from .targets import (
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupPreview,
    CleanupRequest,
    CleanupTarget,
    IntegrationFact,
    WorktreeCleanupRequest,
)

CANONICAL_FETCH_REFSPEC = "+refs/heads/*:refs/remotes/{remote}/*"


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


def _inspect_branch(request: BranchCleanupRequest, git: Git) -> CleanupPreview:
    anchor = worktree_root(request.anchor, git)
    scoped = git.at(anchor)
    name = request.name
    refs = RefIndex.read(scoped)
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
                checked_out_at=checked_out_at(scoped.worktree_records(), local_ref),
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
    refs: RefIndex,
    integration_ref: str | None,
    *,
    checked_out_at: Path | None,
    requires: str | None = None,
) -> CleanupTarget:
    refname = f"{LOCAL_REF_PREFIX}{name}"
    commit = refs.commits[refname]
    fact = integration_fact(
        git, integration_ref, refname, refs.committed_at.get(refname)
    )
    blockers = _integration_branch_blockers(refname, name, integration_ref, None)
    if checked_out_at is not None:
        # From the Worktrees pane the Branch is a target only because the
        # Worktree goes first; a Worktree that cannot go keeps it checked out.
        detail = (
            f"checked out at {checked_out_at}, whose removal is blocked"
            if requires is not None
            else f"checked out at {checked_out_at}; remove that Worktree first"
        )
        blockers.append(CleanupBlocker(kind="checked-out", detail=detail))
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
    refs: RefIndex,
    integration_ref: str | None,
    fetched: str | None,
    *,
    requires: str | None = None,
    checked_out_at: Path | None = None,
) -> CleanupTarget:
    tracking = f"{REMOTE_REF_PREFIX}{remote}/{name}"
    commit = refs.commits[tracking]
    fact = integration_fact(
        git, integration_ref, tracking, refs.committed_at.get(tracking)
    )
    blockers = _integration_branch_blockers(
        tracking, name, integration_ref, refs.origin_head
    )
    if checked_out_at is not None:
        # Offered from the Worktrees pane only as part of finishing the
        # Worktree, so it goes no further than a Worktree that cannot go.
        blockers.append(
            CleanupBlocker(
                kind="checked-out",
                detail=f"checked out at {checked_out_at}, whose removal is blocked",
            )
        )
    blockers.extend(_remote_blockers(git, remote))
    blockers.extend(_integration_blockers(fact, tracking))
    consequences = [
        f"deletes {name} at {remote}, leased on {tracking} at {commit[:7]}"
        f"; recreate with: git push {remote} {commit}:refs/heads/{name}",
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
        requires=requires,
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
    if name == branch_name(integration_ref):
        return [
            CleanupBlocker(
                kind="integration-branch",
                detail=f"{refname} carries the Integration Branch's name "
                f"({integration_ref})",
            )
        ]
    return []


def _integration_blockers(fact: IntegrationFact, refname: str) -> list[CleanupBlocker]:
    state = fact.state
    if state == "unknown":
        if fact.integration_ref is None:
            detail = NO_INTEGRATION_BRANCH
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


def _remotes(git: Git) -> list[str]:
    listed = git.maybe("remote")
    return [name.strip() for name in (listed or "").splitlines() if name.strip()]


def _push_remote(git: Git, name: str) -> str | None:
    """The configured remote a plain ``git push`` of the Branch ``name`` reaches.

    Git's own order: the Branch's ``pushRemote``, the Repository's
    ``pushDefault``, the Branch's upstream remote, then ``origin``. A name
    that is not a configured remote — ``.`` for a local upstream — is none.
    """
    for key in (
        f"branch.{name}.pushRemote",
        "remote.pushDefault",
        f"branch.{name}.remote",
    ):
        configured = (git.maybe("config", "--get", key) or "").strip()
        if configured:
            break
    else:
        configured = "origin"
    return configured if configured in _remotes(git) else None


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
        targets.extend(
            _attached_branch_targets(located, branch, identity, blocked=bool(blockers))
        )
    return _preview("worktree", str(path), located.anchor, targets, ignored, ())


def _attached_branch_targets(
    located: LocatedWorktree, branch: str, worktree: str, *, blocked: bool
) -> list[CleanupTarget]:
    """The Worktree's Branch, locally and at its push remote, each after the Worktree.

    Only the Branch of the same name at the remote a plain ``git push``
    reaches is offered: finishing a piece of work removes what was pushed
    for it, while a Branch at any other remote — or an upstream of another
    name, which may be shared — stays the Branches pane's to delete.
    """
    git = located.git
    refs = RefIndex.read(git)
    integration_ref = refs.integration_ref()
    targets: list[CleanupTarget] = []
    if f"{LOCAL_REF_PREFIX}{branch}" in refs.commits:
        targets.append(
            _local_branch_target(
                git,
                branch,
                refs,
                integration_ref,
                checked_out_at=located.path if blocked else None,
                requires=worktree,
            )
        )
    remote = _push_remote(git, branch)
    if remote is not None and f"{REMOTE_REF_PREFIX}{remote}/{branch}" in refs.commits:
        targets.append(
            _remote_branch_target(
                git,
                branch,
                remote,
                refs,
                integration_ref,
                last_fetched_at(located.anchor, git),
                requires=worktree,
                checked_out_at=located.path if blocked else None,
            )
        )
    return targets


def _worktree_blockers(
    located: LocatedWorktree,
    lookup: ProcessLookup,
    lock_probe: LockHolderProbe | None,
    protected: Sequence[Path],
) -> list[CleanupBlocker]:
    path = located.path
    blockers: list[CleanupBlocker] = assess_worktree_safety(located, lock_probe)
    blockers.extend(assess_worktree_occupancy(path, located.worktrees, lookup))
    if located.detached:
        blockers.extend(assess_detached_head_preservation(located.git, located.head))
    if any(same_path(path, candidate.expanduser()) for candidate in protected):
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
    lines = [f"{verb:<16}{preview.subject}", f"{'Anchor':<16}{preview.anchor}"]
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
        if target.observed_at:
            lines.append(
                f"      repository fetch timestamp: {target.observed_at} (not per-remote verification)"
            )
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
