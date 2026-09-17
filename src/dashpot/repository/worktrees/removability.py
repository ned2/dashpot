"""Assess whether a registered Worktree can be removed safely."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...core.git import Git, GitError
from ...core.pydantic import LaxSequence, PublishedModel
from ...sessions.harnesses import HARNESS_DISPLAY
from ...sessions.hook_scan import reachable_hook_stores, sessions_at_worktree
from ...sessions.liveness import session_liveness
from ...sessions.processes import ProcessLookup, host_process_lookup
from ...sessions.work_store import WorkStore
from ..repository import (
    LockHolderProbe,
    assess_content_integration,
    lock_holder,
    worktree_paths,
    worktree_root,
)
from .base import resolve_base
from .records import INITIALIZING_LOCK, registered_at, short_branch

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
    "unpushed",
    "unmerged",
    "detached",
]


class CleanupBlocker(PublishedModel):
    """One reason a Cleanup target is unavailable, with the command that acts on it."""

    kind: BlockerKind
    detail: str
    command: str | None = None


class WorktreeRemovability(PublishedModel):
    """A read-only report of whether a Worktree can be removed, and why not."""

    path: str
    branch: str | None
    head: str
    role: Literal["main", "linked"]
    removable: bool
    obstacles: LaxSequence[CleanupBlocker] = ()
    remove_commands: LaxSequence[str] = ()


def linked_worktrees(current: Path, *, timeout: float = 10) -> list[Path]:
    """List the linked Worktrees of the Repository ``current`` belongs to.

    The main Worktree is never removable, so a check of every Worktree is a
    check of the linked ones; a bare entry is not a Worktree.
    """
    anchor = worktree_root(current)
    records = Git(anchor, timeout).worktree_records()
    return sorted(worktree_paths(records[1:]))


def check_worktree(
    current: Path,
    target: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    timeout: float = 10,
) -> WorktreeRemovability:
    """Report whether a Worktree could be removed, and each reason it cannot.

    Everything here is observed: Git's dirty state and locks, the Agent
    Sessions whose hooks place them at the Worktree, the Agent Runs recorded
    there, and commits its Branch has that no upstream or base Branch has.
    Dashpot removes nothing; each obstacle names the command that acts on it.
    """
    located = locate_worktree(current, target, timeout=timeout)
    git, path = located.git, located.path
    branch = located.branch
    obstacles = assess_worktree_safety(located, lock_probe)
    obstacles.extend(assess_worktree_occupancy(path, located.worktrees, lookup))
    content_integrated = False
    if branch is not None:
        branch_obstacles, content_integrated = assess_branch_preservation(
            git, path, branch
        )
        obstacles.extend(branch_obstacles)
    elif located.detached:
        obstacles.extend(assess_detached_head_preservation(git, located.head))
    remove_commands: tuple[str, ...] = ()
    if located.role == "linked":
        # ``branch -d`` refuses a squash-merged Branch, whose commits are not
        # reachable; the forced form is the command that acts on it.
        delete = "-D" if content_integrated else "-d"
        remove_commands = (f"git worktree remove {path}",) + (
            (f"git branch {delete} {branch}",) if branch else ()
        )
    return WorktreeRemovability(
        path=str(path),
        branch=branch,
        head=located.head,
        role=located.role,
        removable=not obstacles,
        obstacles=tuple(obstacles),
        remove_commands=remove_commands,
    )


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

    A path Git does not list is a ``RuntimeError``: every assessment is about
    a registered Worktree, never about a directory that merely looks like one.
    """
    path = target.expanduser().resolve()
    try:
        anchor = worktree_root(current, git)
    except RuntimeError:
        anchor = worktree_root(path, git)
    scoped = (git if git is not None else Git(anchor, timeout)).at(anchor)
    records = scoped.worktree_records()
    registered = registered_at(records, path)
    if registered is None:
        raise RuntimeError(f"{path} is not a Worktree of the Repository at {anchor}")
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
                    detail=f"{count} changed or untracked path(s); inspect with "
                    f"'git -C {path} status'",
                    command=f"git worktree remove --force {path}",
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


def assess_branch_preservation(
    git: Git, path: Path, branch: str
) -> tuple[list[CleanupBlocker], bool]:
    """The Branch's obstacles, and whether its content is already integrated.

    Retained commits whose content the Integration Branch already holds — a
    squash merge — obstruct nothing: neither unmerged nor unpushed, since the
    work is where it was meant to land ([ADR 0017](../../docs/adr/0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)).
    """
    obstacles: list[CleanupBlocker] = []
    upstream = git.maybe(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"
    )
    # The Integration Branch is chosen by the same rule as a new Worktree's
    # base; when none can be, integration is unknown rather than complete.
    resolution = resolve_base(git, None)
    base_ref, base_commit = resolution.ref, resolution.commit
    unmerged = (
        _count(git, f"{base_commit}..refs/heads/{branch}") if base_commit else None
    )
    content_integrated = False
    if unmerged and base_ref is not None:
        try:
            content_integrated = bool(
                assess_content_integration(
                    git,
                    base_ref,
                    f"refs/heads/{branch}",
                    git.maybe("log", "-1", "--format=%cI", f"refs/heads/{branch}"),
                )
            )
        except GitError:
            content_integrated = False
        if content_integrated:
            unmerged = 0
    if unmerged is None:
        reason = (
            "; ".join(resolution.refusals)
            if resolution.refusals
            else f"commits not reachable from {base_ref} could not be counted"
        )
        obstacles.append(
            CleanupBlocker(
                kind="unmerged",
                detail=f"cannot tell whether Branch {branch} is integrated: {reason}",
                command=f"git log --oneline {branch}",
            )
        )
    if upstream:
        ahead = _count(git, f"{upstream}..refs/heads/{branch}")
        if ahead:
            obstacles.append(
                CleanupBlocker(
                    kind="unpushed",
                    detail=f"{ahead} commit(s) not on {upstream}",
                    command=f"git -C {path} push",
                )
            )
    elif unmerged:
        obstacles.append(
            CleanupBlocker(
                kind="unpushed",
                detail=f"Branch {branch} has no upstream and {unmerged} commit(s) "
                f"of its own",
                command=f"git -C {path} push -u origin {branch}",
            )
        )
    if unmerged:
        obstacles.append(
            CleanupBlocker(
                kind="unmerged",
                detail=f"{unmerged} commit(s) not reachable from {base_ref}",
                command=f"git log --oneline {base_ref}..{branch}",
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


def _count(git: Git, revision_range: str) -> int | None:
    return git.count("rev-list", "--count", revision_range)


def describe_removability(report: WorktreeRemovability) -> list[str]:
    """Render a removability report as lines for a person.

    Field/value lines name the Worktree, its Branch, and the verdict; the
    obstacles and the commands to run are indented beneath them so a block
    scans as one Worktree and the commands stand apart from the facts.
    """
    lines = [
        f"Worktree   {report.path}",
        f"Branch     {report.branch or '(detached)'}",
        f"Removable  {'yes' if report.removable else 'no'}",
    ]
    if report.obstacles:
        lines.append("Obstacles")
        for obstacle in report.obstacles:
            lines.append(f"  - {obstacle.kind}: {obstacle.detail}")
            if obstacle.command:
                lines.append(f"      run: {obstacle.command}")
    if report.removable and report.remove_commands:
        lines.append("Remove with")
        lines.extend(f"  $ {command}" for command in report.remove_commands)
    return lines
