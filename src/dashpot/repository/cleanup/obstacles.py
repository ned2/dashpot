"""Assess what obstructs removing a Worktree or deleting its Branch."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...core.git import Git, GitError
from ...core.model import HARNESS_DISPLAY
from ...core.worktree_paths import worktree_paths, worktree_root
from ...sessions.hook_scan import reachable_hook_stores, sessions_at_worktree
from ...sessions.liveness import session_liveness
from ...sessions.processes import ProcessLookup, host_process_lookup
from ...sessions.work_store import WorkStore
from ..repository import (
    LockHolderProbe,
    RefIndex,
    assess_content_integration,
    lock_holder,
    short_ref,
)
from ..worktrees.records import INITIALIZING_LOCK, registered_at, short_branch
from .targets import CleanupBlocker, CleanupError, IntegrationFact


def counted(count: int, noun: str) -> str:
    """``1 commit`` or ``3 commits``: a count with its noun agreeing."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@dataclass(frozen=True, slots=True)
class LocatedWorktree:
    """One registered Worktree, as Git lists it, with the adapter at its anchor."""

    git: Git
    anchor: Path
    path: Path
    record: Mapping[str, str]
    role: Literal["main", "linked"]
    # Every Worktree of the Repository, resolved; bare entries are not Worktrees.
    worktrees: tuple[Path, ...]

    @property
    def branch(self) -> str | None:
        return short_branch(self.record)

    @property
    def head(self) -> str:
        return self.record.get("HEAD", "")

    @property
    def detached(self) -> bool:
        return "detached" in self.record


def locate_worktree(
    current: Path, target: Path, *, timeout: float = 10, git: Git | None = None
) -> LocatedWorktree:
    """Find ``target`` among the Worktrees of the Repository ``current`` is in.

    A path Git does not list is a ``CleanupError``: every assessment is about
    a registered Worktree, never about a directory that merely looks like one.
    """
    path = target.expanduser().resolve()
    try:
        anchor = worktree_root(current, git)
    except GitError:
        anchor = worktree_root(path, git)
    scoped = (git if git is not None else Git(anchor, timeout)).at(anchor)
    records = scoped.worktree_records()
    registered = registered_at(records, path)
    if registered is None:
        raise CleanupError(f"{path} is not a Worktree of the Repository at {anchor}")
    role: Literal["main", "linked"] = (
        "main" if records and records[0] is registered else "linked"
    )
    return LocatedWorktree(
        scoped, anchor, path, registered, role, tuple(worktree_paths(records))
    )


def assess_worktree_safety(
    located: LocatedWorktree, lock_probe: LockHolderProbe | None = None
) -> list[CleanupBlocker]:
    """The obstacles Git itself raises: the main Worktree, a lock, a dirty tree."""
    path, registered = located.path, located.record
    obstacles: list[CleanupBlocker] = []
    if located.role == "main":
        obstacles.append(
            CleanupBlocker(
                kind="main-worktree",
                detail="the main Worktree cannot be removed with git worktree remove",
            )
        )
    lock = registered.get("locked")
    if lock is not None:
        reason = lock or "no reason reported"
        holder = lock_holder(reason, lock_probe)
        if INITIALIZING_LOCK in reason:
            command = f"git worktree remove -f -f {path}"
        else:
            command = f"git worktree unlock {path}"
        obstacles.append(
            CleanupBlocker(
                kind="locked",
                detail=f"locked: {reason} (holding process {holder})",
                command=command,
            )
        )
    if path.is_dir():
        status = located.git.at(path).run(
            "status", "--porcelain=v1", "--untracked-files=normal"
        )
        if status.returncode != 0:
            obstacles.append(
                CleanupBlocker(
                    kind="dirty",
                    detail=f"cannot inspect: "
                    f"{status.stderr.strip() or 'git status failed'}",
                    command=f"git -C {path} status",
                )
            )
        elif status.stdout:
            count = len(status.stdout.splitlines())
            obstacles.append(
                CleanupBlocker(
                    kind="dirty",
                    detail=counted(count, "changed or untracked path"),
                    command=f"git -C {path} status",
                )
            )
    return obstacles


def assess_worktree_occupancy(
    path: Path,
    worktrees: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[CleanupBlocker]:
    """The Agent Sessions, Agent Runs, and unreadable Work Store records at a Worktree."""
    obstacles: list[CleanupBlocker] = []
    stores = reachable_hook_stores(worktrees)
    for location in sessions_at_worktree(path, stores, lookup):
        record = location.record
        obstacles.append(
            CleanupBlocker(
                kind="agent-session",
                detail=f"{HARNESS_DISPLAY[record.harness]} session "
                f"{record.session_id} is {record.outcome} here "
                f"(last activity {record.last_activity_at})",
            )
        )
    active, work_diagnostics = WorkStore(path).active()
    # A record that cannot be read may still be a live Agent Run; removable
    # is never claimed on evidence that could not be examined.
    obstacles.extend(
        CleanupBlocker(kind="work-store", detail=diagnostic.message)
        for diagnostic in work_diagnostics
    )
    for work in active:
        liveness = (
            session_liveness(work.session_process.key, lookup).liveness
            if work.session_process is not None
            else "unknown"
        )
        if liveness == "gone":
            detail = (
                f"Orphaned Agent Run on {work.issue_reference} for {work.session_label}"
            )
            command = f"cd {path} && dashpot work stop --session {work.session_key}"
        else:
            detail = (
                f"{work.session_label} is working on {work.issue_reference} "
                f"(session {liveness})"
            )
            command = "dashpot work stop (inside that session)"
        obstacles.append(
            CleanupBlocker(kind="agent-run", detail=detail, command=command)
        )
    return obstacles


NO_INTEGRATION_BRANCH = (
    "no Integration Branch could be chosen: origin/HEAD is not set and there is "
    "no unique local main or master Branch"
)


def integration_fact(
    git: Git, integration_ref: str | None, refname: str, committed_at: str | None
) -> IntegrationFact:
    """How ``refname`` stands against the Integration Branch, by reachability then content."""
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


def assess_branch_preservation(
    git: Git, path: Path, branch: str
) -> tuple[list[CleanupBlocker], bool]:
    """The Branch's obstacles, and whether its content is already integrated.

    Retained commits whose content the Integration Branch already holds — a
    squash merge — obstruct nothing: neither unmerged nor unpushed, since the
    work is where it was meant to land ([ADR 0017](../../docs/adr/0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)).
    """
    obstacles: list[CleanupBlocker] = []
    refname = f"refs/heads/{branch}"
    upstream = git.maybe(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"
    )
    # The Integration Branch is chosen by the one rule the Cleanup preview of
    # this Worktree applies; when none can be, integration is unknown rather
    # than complete.
    refs = RefIndex.read(git)
    integration_ref = refs.integration_ref()
    fact = integration_fact(
        git, integration_ref, refname, refs.committed_at.get(refname)
    )
    unmerged = fact.unintegrated_commits
    content_integrated = fact.content_integrated is True
    if content_integrated:
        unmerged = 0
    if unmerged is None:
        reason = (
            NO_INTEGRATION_BRANCH
            if integration_ref is None
            else f"commits not reachable from {short_ref(integration_ref)} "
            f"could not be counted"
        )
        obstacles.append(
            CleanupBlocker(
                kind="unmerged",
                detail=f"cannot tell whether Branch {branch} is integrated: {reason}",
                command=f"git log --oneline {branch}",
            )
        )
    if upstream:
        ahead = git.count("rev-list", "--count", f"{upstream}..{refname}")
        if ahead:
            obstacles.append(
                CleanupBlocker(
                    kind="unpushed",
                    detail=f"{counted(ahead, 'commit')} not on {upstream}",
                    command=f"git -C {path} push",
                )
            )
    elif unmerged:
        obstacles.append(
            CleanupBlocker(
                kind="unpushed",
                detail=f"Branch {branch} has no upstream and "
                f"{counted(unmerged, 'commit')} of its own",
                command=f"git -C {path} push -u origin {branch}",
            )
        )
    if unmerged:
        obstacles.append(
            CleanupBlocker(
                kind="unmerged",
                detail=f"{counted(unmerged, 'commit')} not reachable from "
                f"{short_ref(integration_ref or '')}",
                command=f"git log --oneline {integration_ref}..{branch}",
            )
        )
    return obstacles, content_integrated


def durable_refs_containing(git: Git, commit: str) -> list[str]:
    """Local, Remote-Tracking, and tag refs from which ``commit`` is reachable."""
    records = git.records(
        "--contains",
        commit,
        "refs/heads",
        "refs/remotes",
        "refs/tags",
        fields=("%(refname)",),
    )
    return [record[0] for record in records if record[0]]


def assess_detached_head_preservation(git: Git, head: str) -> list[CleanupBlocker]:
    """A detached HEAD no durable ref reaches is lost with the Worktree."""
    if not head:
        return []
    try:
        if durable_refs_containing(git, head):
            return []
    except GitError as exc:
        detail = f"cannot tell whether commit {head[:7]} is reachable: {exc.detail}"
    else:
        detail = (
            f"detached at {head[:7]}, which no local Branch, Remote-Tracking "
            f"Branch, or tag reaches"
        )
    return [
        CleanupBlocker(
            kind="detached",
            detail=detail,
            command=f"git branch rescue/{head[:7]} {head}",
        )
    ]


def ignored_content(git: Git, path: Path) -> list[str]:
    """The ignored paths in a Worktree, which unforced removal deletes too.

    Directories whose every entry is ignored are reported as one path with a
    trailing slash, as ``git status --ignored`` collapses them.
    """
    if not path.is_dir():
        return []
    listing = git.at(path).maybe(
        "status", "--porcelain=v1", "--ignored=traditional", "-z"
    )
    if listing is None:
        return []
    ignored: list[str] = []
    skip = False
    for entry in listing.split("\0"):
        if skip:
            # A rename or copy entry is followed by its source path as a
            # field of its own.
            skip = False
            continue
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in "RC":
            skip = True
        if code == "!!":
            ignored.append(name)
    return ignored
