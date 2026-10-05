"""Assess what obstructs removing a Worktree or deleting its Branch."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...core.git import Git, GitError
from ...core.model import HARNESS_DISPLAY
from ...core.worktree_paths import is_within, worktree_paths, worktree_root
from ...sessions.hook_scan import (
    HookRecordClassification,
    reachable_hook_stores,
    sessions_at_worktree,
    sessions_with_live_subagents,
    stored_session_records,
)
from ...sessions.liveness import session_liveness
from ...sessions.opencode_publishers import NO_LIVE_INSTANCE
from ...sessions.processes import ProcessLookup, host_process_lookup
from ...sessions.session_exits import (
    ended_session_subagent_stop,
    forget_subagents_command,
    listed_subagents,
    named_subagents,
    session_exit,
    unreported_subagent_stop,
)
from ...sessions.work_store import ActiveWork, WorkStore
from ...sessions.working_directories import ProcessScan, ScanGap, processes_inside
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


def session_blocker(record: HookRecordClassification) -> CleanupBlocker:
    """The ``agent-session`` blocker of a live or unknown session placed here.

    It names the session, says whether it is live here or of unknown
    liveness, and how to free the Worktree from it. Only verifying an
    unknown session's Host Process is a command a person runs.
    """
    session = f"{HARNESS_DISPLAY[record.harness]} session {record.session_id}"
    way = session_exit(record.harness)
    move = way.move.replace("{session_id}", record.session_id)
    end = way.end.replace("{session_id}", record.session_id)
    steps = f"{move}, or {end}"
    activity = f"last activity {record.last_activity_at}"
    if record.outcome == "live":
        return CleanupBlocker(
            kind="agent-session",
            detail=f"{session} is live here ({activity}). "
            f"To free this Worktree, {steps}.",
        )
    if record.process is None:
        return CleanupBlocker(
            kind="agent-session",
            detail=f"{session} may be live here: its liveness is unknown, as "
            f"its hook record names no Host Process ({activity}). If that "
            f"session is still open, free this Worktree: {steps}. If it has "
            f"ended, resume it and end it again so that it publishes its end.",
        )
    process = record.process
    if record.reason == NO_LIVE_INSTANCE:
        # The server is observed and runs; what is missing is a plugin
        # instance observing the session in it (ADR 0080, ADR 0090).
        return CleanupBlocker(
            kind="agent-session",
            detail=f"{session} may be live here: its liveness is unknown "
            f"({activity}). Its OpenCode server, pid {process.pid}, still "
            f"runs, but no Dashpot plugin instance has run in it since the "
            f"session was last published. To free this Worktree, {steps}.",
        )
    if record.reason == "isolated-namespace":
        verify = (
            f"Dashpot cannot see its Host Process, pid {process.pid}, from "
            f"inside this sandbox: check again from a shell outside it."
        )
    else:
        verify = (
            f"Dashpot could not observe its Host Process ({record.reason}): "
            f"check whether pid {process.pid}, started {process.started_at} "
            f"UTC, still runs."
        )
    return CleanupBlocker(
        kind="agent-session",
        detail=f"{session} may be live here: its liveness is unknown "
        f"({activity}). {verify} If it is live, free this Worktree: {steps}.",
        # The start time is recorded as ps renders it in the C locale and UTC.
        command=f"env LC_ALL=C TZ=UTC ps -p {process.pid} -o lstart=,args=",
    )


def assess_worktree_occupancy(
    path: Path,
    worktrees: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[CleanupBlocker]:
    """The Agent Sessions, sub-agents, and Agent Runs that may occupy a Worktree.

    An unreadable Work Store record obstructs too, as a possible Agent Run.
    A live sub-agent obstructs every Worktree of the Repository: its hooks
    carry its session's location, never its own, so Dashpot cannot prove it
    is not working here (ADR 0066).
    """
    obstacles: list[CleanupBlocker] = []
    stores = reachable_hook_stores(worktrees)
    occupants: set[tuple[str, str]] = set()
    for location in sessions_at_worktree(path, stores, lookup):
        record = location.record
        occupants.add((record.harness, record.session_id))
        obstacles.append(session_blocker(record))
    for location in sessions_with_live_subagents(worktrees, stores, lookup):
        record = location.record
        # A session here already blocks removal, its sub-agents with it.
        if (record.harness, record.session_id) in occupants:
            continue
        harness = HARNESS_DISPLAY[record.harness]
        agents = ", ".join(record.live_subagents)
        unplaced = (
            "Dashpot cannot tell which Worktree a sub-agent works in, so one "
            "may be working here: wait for it to finish."
        )
        if record.outcome == "ended":
            # The session ended and left these working: no client of it is
            # left to end, so the way out forgets them (ADR 0095).
            obstacles.append(
                CleanupBlocker(
                    kind="sub-agent",
                    detail=f"{harness} session {record.session_id} at "
                    f"{record.worktree} ended with "
                    f"{named_subagents(record.live_subagents)}. {unplaced} "
                    f"{ended_session_subagent_stop(record.harness, record.session_id)}.",
                    command=f"cd {path} && "
                    f"{forget_subagents_command(record.harness, record.session_id)}",
                    session_id=record.session_id,
                    harness=record.harness,
                    agents=record.live_subagents,
                )
            )
            continue
        obstacles.append(
            CleanupBlocker(
                kind="sub-agent",
                detail=f"{harness} session {record.session_id} at "
                f"{record.worktree} has "
                f"{listed_subagents(len(record.live_subagents))} "
                f"({agents}; session {record.outcome}). {unplaced} "
                f"{unreported_subagent_stop(record.harness)}.",
                session_id=record.session_id,
                harness=record.harness,
                agents=record.live_subagents,
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
            session_liveness(
                work.session_process.key,
                lookup,
                namespace=work.session_process.pid_namespace,
            ).liveness
            if work.session_process is not None
            else "unknown"
        )
        if liveness == "gone":
            detail = (
                f"Orphaned Agent Run on {work.issue_reference} for {work.session_label}"
            )
            command = f"cd {path} && dashpot work stop --session {work.session_key}"
        elif liveness == "live" and _unrecorded_opencode_session(work, stores):
            # A session's record is gone while its run stays only when its end
            # was not reconciled with it, and no command runs inside a session
            # that has none, so the run is ended from outside (ADR 0090).
            detail = (
                f"{work.session_label} is working on {work.issue_reference}, "
                "but no hook record of that session is left while the OpenCode "
                "server that served it still runs: end the run"
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


# How many processes a ``process`` blocker names before it counts the rest.
NAMED_PROCESSES = 5

# Why a scan of process working directories could not cover every process,
# in the words a person reads beneath a removable Worktree.
UNCHECKED_PROCESSES: Mapping[ScanGap, str] = {
    "isolated-namespace": "Dashpot runs inside a sandbox's process namespace "
    "and cannot see the processes outside it; check again from a shell "
    "outside the sandbox",
    "proc-unreadable": "/proc could not be read",
    "lsof-unavailable": "this host has no /proc, and lsof could not be run",
    "lsof-timeout": "lsof did not answer in time",
    "lsof-failed": "lsof failed",
}


def unchecked_processes(gap: ScanGap) -> str:
    """Say which processes the occupancy check could not read, and why."""
    return (
        "Processes running inside this Worktree were not all checked: "
        f"{UNCHECKED_PROCESSES[gap]}."
    )


def assess_processes_inside(
    located: LocatedWorktree, scan: ProcessScan | None = None
) -> tuple[list[CleanupBlocker], str | None]:
    """The ``process`` blocker of a Worktree some process runs inside, and any gap.

    One blocker names every process whose working directory is inside the
    Worktree, so its count changing never changes the preview's blockers.
    The evidence is positive only: finding none clears no other blocker,
    and a scan that could not read every process says so in the returned
    sentence instead of a blocker (ADR 0104). The main Worktree is never
    removable, and its tree may hold linked Worktrees whose occupants are
    not its own, so it is not scanned.
    """
    if located.role == "main":
        return [], None
    found = processes_inside(located.path, scan)
    unchecked = (
        unchecked_processes(found.incomplete) if found.incomplete is not None else None
    )
    if not found.processes:
        return [], unchecked
    named = [
        f"pid {process.pid} ({process.command}) at {process.cwd}"
        for process in found.processes[:NAMED_PROCESSES]
    ]
    rest = len(found.processes) - len(named)
    if rest:
        named.append(f"and {rest} more")
    if len(found.processes) == 1:
        opening = "A process is running inside this Worktree"
        pronoun = "it"
    else:
        opening = f"{len(found.processes)} processes are running inside this Worktree"
        pronoun = "them"
    pids = ",".join(str(process.pid) for process in found.processes)
    blocker = CleanupBlocker(
        kind="process",
        detail=f"{opening}: {'; '.join(named)}. Removing the Worktree would "
        f"delete the directory it works in: end {pronoun} or move {pronoun} "
        f"out of the Worktree.",
        command=f"ps -ww -o pid=,args= -p {pids}",
    )
    return [blocker], unchecked


def _unrecorded_opencode_session(work: ActiveWork, stores: Sequence[Path]) -> bool:
    """Whether an OpenCode run's session has no hook record left in any store."""
    if work.harness != "opencode" or work.session_id is None:
        return False
    records, unreadable = stored_session_records(stores, "opencode", work.session_id)
    return not records and not unreadable


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
    work is where it was meant to land ([ADR 0017](../../../../docs/adr/0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)).
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


def assess_nested_worktrees(located: LocatedWorktree) -> list[CleanupBlocker]:
    """The ``nested-worktree`` blocker of each Worktree registered inside this one.

    An unforced ``git worktree remove`` checks only this Worktree's own
    status, where a Worktree inside it shows at most as an untracked or
    ignored directory, and then deletes the directory recursively: the
    Worktree inside goes too, its uncommitted work included, without any of
    its own checks running (ADR 0125). A record whose directory is gone
    loses nothing with this one, but removal does not decide that for the
    person: it blocks until ``git worktree prune`` clears it. The main
    Worktree is never removable, and its tree may hold linked Worktrees by
    design, so it is not assessed.
    """
    if located.role == "main":
        return []
    blockers: list[CleanupBlocker] = []
    for nested in sorted(located.worktrees):
        if nested == located.path or not is_within(nested, located.path):
            continue
        if nested.is_dir():
            blockers.append(
                CleanupBlocker(
                    kind="nested-worktree",
                    detail=f"the Worktree {nested} is inside this one, and "
                    f"removing this Worktree would delete it without checking "
                    f"it: remove it first, or move it out with git worktree move",
                    command=f"dashpot worktree remove {nested}",
                )
            )
        else:
            blockers.append(
                CleanupBlocker(
                    kind="nested-worktree",
                    detail=f"a stale record of the Worktree {nested}, whose "
                    f"directory is gone, is inside this one: prune it first",
                    command="git worktree prune",
                )
            )
    return blockers


def ignored_content(git: Git, path: Path) -> tuple[list[str], list[CleanupBlocker]]:
    """The ignored paths in a Worktree, which unforced removal deletes too, or why not.

    Directories whose every entry is ignored are reported as one path with a
    trailing slash, as ``git status --ignored`` collapses them. Git lists
    ignored paths only while it collects untracked ones, so the collection is
    set explicitly rather than taken from ``status.showUntrackedFiles``:
    ``no`` would list nothing, and ``all`` every file inside an ignored
    directory. An inventory Git refuses is an ``ignored-content`` blocker,
    never an empty list (ADR 0125).
    """
    if not path.is_dir():
        return [], []
    listing = git.at(path).run(
        "status",
        "--porcelain=v1",
        "--ignored=traditional",
        "--untracked-files=normal",
        "-z",
    )
    if listing.returncode != 0:
        return [], [
            CleanupBlocker(
                kind="ignored-content",
                detail=f"cannot list the ignored content removing this Worktree "
                f"would delete: {listing.stderr.strip() or 'git status failed'}",
                command=f"git -C {path} status --ignored --untracked-files=normal",
            )
        ]
    ignored: list[str] = []
    skip = False
    for entry in listing.stdout.split("\0"):
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
    return ignored, []
