"""Inspect Cleanup targets without mutating their Repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from ...core.git import Git
from ...core.model import IntegrationState
from ...core.shell import shell_command
from ...core.worktree_paths import worktree_root
from ...sessions.processes import ProcessLookup, host_process_lookup
from ...sessions.working_directories import ProcessScan
from ..repository import (
    LOCAL_REF_PREFIX,
    REMOTE_REF_PREFIX,
    RefIndex,
    branch_name,
    last_fetched_at,
    short_ref,
)
from ..worktrees.records import BranchInUse, branch_in_use
from .obstacles import (
    NO_INTEGRATION_BRANCH,
    LocatedWorktree,
    assess_worktree,
    counted,
    integration_fact,
    locate_worktree,
)
from .override import DESPITE_SUBAGENTS_FLAG, override_offer, worktree_target
from .targets import (
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupPreview,
    CleanupRequest,
    CleanupTarget,
    IntegrationFact,
    WorktreeCleanupRequest,
    fingerprint,
)

CANONICAL_FETCH_REFSPEC = "+refs/heads/*:refs/remotes/{remote}/*"

SUB_AGENT_SCOPE = (
    "Sub-agents of Agent Sessions outside this Repository are not checked."
)


def inspect_cleanup(
    request: CleanupRequest,
    *,
    lookup: ProcessLookup = host_process_lookup,
    protected: Sequence[Path] = (),
    timeout: float = 10,
    git: Git | None = None,
    scan: ProcessScan | None = None,
) -> CleanupPreview:
    """Preview a Cleanup: every concrete target, its gate, and what would follow.

    ``protected`` names Worktrees that are never removable — the checkout
    Dashpot runs from and the configured Repository Anchors — since removing
    one takes the observer's own ground away. ``scan`` reads the host's
    process working directories, the host itself when omitted. ``lookup``
    observes the processes that Agent Sessions and Worktree locks record.
    """
    adapter = git if git is not None else Git(Path.cwd(), timeout)
    if isinstance(request, BranchCleanupRequest):
        return _inspect_branch(request, adapter)
    return _inspect_worktree(request, adapter, lookup, protected, timeout, scan)


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
                in_use=branch_in_use(scoped, scoped.worktree_records(), local_ref),
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
    in_use: BranchInUse | None,
    blocked_worktree: Path | None = None,
    requires: str | None = None,
) -> CleanupTarget:
    refname = f"{LOCAL_REF_PREFIX}{name}"
    commit = refs.commits[refname]
    fact = integration_fact(
        git, integration_ref, refname, refs.committed_at.get(refname)
    )
    blockers = _integration_branch_blockers(refname, name, integration_ref, None)
    if in_use is not None:
        # ``update-ref -d`` deletes a Branch in use, so the refusal Git's own
        # ``branch -d`` makes is Dashpot's to make (ADR 0019).
        blockers.append(_in_use_blocker(in_use))
    if blocked_worktree is not None:
        # From the Worktrees pane the Branch is a target only because the
        # Worktree goes first; a Worktree that cannot go keeps it checked out.
        blockers.append(
            CleanupBlocker(
                kind="checked-out",
                detail=f"checked out at {blocked_worktree}, whose removal is blocked",
            )
        )
    blockers.extend(_integration_blockers(fact, refname))
    recreate = shell_command("git", "branch", name, commit)
    consequences = [f"deletes {refname} at {commit[:7]}; recreate with: {recreate}"]
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


def _in_use_blocker(in_use: BranchInUse) -> CleanupBlocker:
    """The ``checked-out`` blocker of a Branch a Worktree uses, and how to free it."""
    worktree = in_use.worktree
    if in_use.use == "being rebased":
        return CleanupBlocker(
            kind="checked-out",
            detail=f"being rebased at {worktree}; finish or abort that rebase first",
            command=shell_command("git", "-C", worktree, "status"),
        )
    if in_use.use == "being bisected":
        return CleanupBlocker(
            kind="checked-out",
            detail=f"being bisected at {worktree}; end that bisect first",
            command=shell_command("git", "-C", worktree, "bisect", "reset"),
        )
    return CleanupBlocker(
        kind="checked-out",
        detail=f"checked out at {worktree}; remove that Worktree first",
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
    blocked_worktree: Path | None = None,
) -> CleanupTarget:
    tracking = f"{REMOTE_REF_PREFIX}{remote}/{name}"
    commit = refs.commits[tracking]
    fact = integration_fact(
        git, integration_ref, tracking, refs.committed_at.get(tracking)
    )
    blockers = _integration_branch_blockers(
        tracking, name, integration_ref, refs.origin_head
    )
    if blocked_worktree is not None:
        # Offered from the Worktrees pane only as part of finishing the
        # Worktree, so it goes no further than a Worktree that cannot go.
        blockers.append(
            CleanupBlocker(
                kind="checked-out",
                detail=(
                    f"its local Branch is checked out at {blocked_worktree}, "
                    f"whose removal is blocked"
                ),
            )
        )
    blockers.extend(_remote_blockers(git, remote))
    blockers.extend(_integration_blockers(fact, tracking))
    recreate = shell_command(
        "git", "push", remote, f"{commit}:{LOCAL_REF_PREFIX}{name}"
    )
    consequences = [
        f"deletes {name} at {remote}, leased on {tracking} at {commit[:7]}"
        f"; recreate with: {recreate}",
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
                detail=f"{short_ref(refname)} is the Integration Branch",
            )
        ]
    if name == branch_name(integration_ref):
        return [
            CleanupBlocker(
                kind="integration-branch",
                detail=f"{short_ref(refname)} carries the Integration Branch's "
                f"name ({short_ref(integration_ref)})",
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
                f"commits of {short_ref(refname)} not reachable from "
                f"{short_ref(fact.integration_ref)} could not be counted"
            )
        return [
            CleanupBlocker(
                kind="unknown-integration",
                detail=detail,
                command=shell_command("git", "log", "--oneline", refname),
            )
        ]
    if state == "unintegrated":
        return [
            CleanupBlocker(
                kind="unintegrated",
                detail=f"{counted(fact.unintegrated_commits or 0, 'commit')} not "
                f"reachable from {short_ref(fact.integration_ref or '')}",
                command=shell_command(
                    "git", "log", "--oneline", f"{fact.integration_ref}..{refname}"
                ),
            )
        ]
    return []


def _content_consequence(fact: IntegrationFact) -> list[str]:
    if fact.state != "content-integrated":
        return []
    return [
        f"content is integrated, but deleting it drops the last named ref to "
        f"{counted(fact.unintegrated_commits or 0, 'original commit')} not "
        f"reachable from {short_ref(fact.integration_ref or '')}"
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
    protected: Sequence[Path],
    timeout: float,
    scan: ProcessScan | None,
) -> CleanupPreview:
    located = locate_worktree(request.current, request.path, timeout=timeout, git=git)
    path = located.path
    assessment = assess_worktree(located, lookup=lookup, protected=protected, scan=scan)
    ignored = assessment.ignored
    identity = f"worktree:{path}"
    branch = located.branch
    consequences = [f"removes {path} with git worktree remove"]
    if ignored:
        consequences.append(ignored_consequence(len(ignored)))
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
            blockers=assessment.blockers,
            consequences=tuple(consequences),
        )
    ]
    if branch is not None:
        targets.extend(
            _attached_branch_targets(
                located, branch, identity, blocked=bool(assessment.blockers)
            )
        )
    return _preview(
        "worktree",
        str(path),
        located.anchor,
        targets,
        ignored,
        (),
        unchecked_processes=assessment.unchecked_processes,
    )


def ignored_consequence(count: int) -> str:
    """What removing a Worktree does to the ignored paths inside it."""
    return (
        f"also deletes {counted(count, 'ignored path')} inside it, "
        f"including any Dashpot state, hook records, and Work Store there"
    )


def _attached_branch_targets(
    located: LocatedWorktree, branch: str, worktree: str, *, blocked: bool
) -> list[CleanupTarget]:
    """The Worktree's Branch, locally and at its push remote, each after the Worktree.

    Only the Branch of the same name at the remote a plain ``git push``
    reaches is offered: finishing a piece of work removes what was pushed
    for it, while a Branch at any other remote — or an upstream of another
    name, which may be shared — stays the Branches pane's to delete. The
    local Branch is checked against every other Worktree too, as Git's
    ``branch -d`` would be.
    """
    git = located.git
    refs = RefIndex.read(git)
    integration_ref = refs.integration_ref()
    targets: list[CleanupTarget] = []
    local_ref = f"{LOCAL_REF_PREFIX}{branch}"
    if local_ref in refs.commits:
        targets.append(
            _local_branch_target(
                git,
                branch,
                refs,
                integration_ref,
                in_use=branch_in_use(
                    git, located.records, local_ref, besides=located.path
                ),
                blocked_worktree=located.path if blocked else None,
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
                blocked_worktree=located.path if blocked else None,
            )
        )
    return targets


def _preview(
    kind: Literal["branch", "worktree"],
    subject: str,
    anchor: Path,
    targets: Sequence[CleanupTarget],
    ignored: Sequence[str],
    refusals: Sequence[str],
    *,
    unchecked_processes: str | None = None,
) -> CleanupPreview:
    preview = CleanupPreview(
        kind=kind,
        subject=subject,
        anchor=str(anchor),
        targets=tuple(targets),
        ignored=tuple(ignored),
        refusals=tuple(refusals),
        unchecked_processes=unchecked_processes,
    )
    return preview.model_copy(update={"fingerprint": fingerprint(preview)})


INTEGRATION_WORDS: Mapping[IntegrationState, str] = {
    "integrated": "⊆ every commit is reachable from the Integration Branch",
    "content-integrated": "≡ the Integration Branch holds the content; "
    "the commits are not reachable",
    "unintegrated": "↑ commits are not reachable from the Integration Branch",
    "unknown": "⊘ no Integration Branch comparison is available",
}


def sub_agent_scope(preview: CleanupPreview) -> str | None:
    """The occupancy gap a preview that would remove a Worktree states, or None.

    The ``sub-agent`` blocker counts only Agent Sessions a hook record places
    at a Worktree of the target's Repository, and no hook says where a
    sub-agent works, so a sub-agent of a session elsewhere can be working in
    a Worktree the preview offers for removal. #357 accepted that gap rather
    than block Cleanup across a Project or the machine (ADR 0066). A blocked
    Worktree claims no absence of occupants, so it is said only of one the
    preview would remove, a person's acknowledgement of its listed
    sub-agents included (ADR 0112).
    """
    if preview.kind != "worktree" or preview.refusals:
        return None
    worktree = worktree_target(preview)
    removable = worktree is not None and (
        worktree.available or bool(override_offer(preview))
    )
    return SUB_AGENT_SCOPE if removable else None


def override_lines(preview: CleanupPreview, indent: str) -> list[str]:
    """How a person may remove the Worktree despite its listed sub-agents, if they may.

    The exact flag value is given, so a person acknowledges the set the
    preview names rather than one typed from memory (ADR 0112).
    """
    offer = override_offer(preview)
    if not offer:
        return []
    if not all(listed.spelled for listed in offer):
        return [
            f"{indent}only a person who has checked that none of these sub-agents "
            "works in this Worktree may remove it despite them, from the "
            f"dashboard's Cleanup dialog: {DESPITE_SUBAGENTS_FLAG} spells only "
            "IDs that are identifiers without :"
        ]
    arguments = " ".join(
        f"{DESPITE_SUBAGENTS_FLAG} {listed.argument}"
        for listed in sorted(offer, key=lambda one: one.session_id)
    )
    return [
        f"{indent}only a person who has checked that none of these sub-agents "
        "works in this Worktree may remove it despite them, with:",
        f"{indent}    {arguments}",
    ]


def unchecked_processes_note(preview: CleanupPreview) -> str | None:
    """The process check's gap a preview that would remove a Worktree states, or None.

    Like the sub-agent scope, it is said only of a Worktree the preview
    would remove: a blocked one claims no absence of occupants (ADR 0104).
    """
    if sub_agent_scope(preview) is None:
        return None
    return preview.unchecked_processes


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
        if target.kind == "worktree":
            lines.extend(override_lines(preview, "      "))
        lines.extend(f"      → {consequence}" for consequence in target.consequences)
        if target.kind == "worktree" and (scope := sub_agent_scope(preview)):
            lines.append(f"      {scope}")
            if unchecked := unchecked_processes_note(preview):
                lines.append(f"      {unchecked}")
    if preview.ignored:
        lines.append(
            "Ignored content (deleted with the Worktree, acknowledge to proceed)"
        )
        lines.extend(f"  {path}" for path in preview.ignored)
    return lines
