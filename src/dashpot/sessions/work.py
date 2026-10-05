"""Declare, relocate, end, and show Issue work for the enclosing Agent Session.

``work forget-subagents`` lives here too: it forgets the sub-agents an ended
Agent Session still lists, which hold Worktree Cleanup as its Issue work did.
Every command that acts for the enclosing session finds it with
:func:`~dashpot.sessions.session_identity.enclosing_session`, and one that
changes its runs across the Repository finds them with :func:`session_runs`,
then applies its own policy to what they find. A Lead's ``work assign`` and ``work unassign`` are in
:mod:`dashpot.sessions.worker_assignments`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..core.command_outcomes import OutcomeNote
from ..core.errors import DashpotError
from ..core.event_log_files import (
    EventSelection,
    describe_runtime_event,
    event_log_directories,
    recent_events,
)
from ..core.git import Git
from ..core.model import (
    HARNESS_DISPLAY,
    Diagnostic,
    Harness,
    WorkerState,
)
from ..core.timestamps import utc_now
from ..core.worktree_paths import repository_worktrees, same_path, worktree_root
from ..issues.issue_resolution import resolve_issue
from .agents import (
    NO_WORKER_EVIDENCE,
    WorkerEvidence,
    assigned_workers,
)
from .hook_records import HookRecordStore
from .hook_scan import (
    SessionLocation,
    StoredSessionRecord,
    locate_agent_session,
    reachable_hook_stores,
    sessions_with_live_subagents,
    stored_session_records,
)
from .liveness import session_liveness
from .orphaned_runs import orphaned_process
from .processes import ProcessLookup, host_process_lookup
from .session_exits import (
    ended_session_subagent_stop,
    named_subagents,
    unreported_subagent_stop,
)
from .session_identity import AgentSessionIdentity, IssueWorkError, enclosing_session
from .session_matching import SessionEvidence
from .work_store import (
    SESSION_KEY,
    ActiveWork,
    RelocationIntent,
    WorkStore,
)


def start_issue_work(
    current: Path,
    reference: str,
    *,
    timeout: float = 10,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """Start or switch confirmed Issue work at the session's observed Worktree.

    ``outcome`` hears which session and Issue the command works for as soon
    as each is confirmed, and what it did.
    """
    note = outcome if outcome is not None else OutcomeNote()
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    session, stores = enclosing_session(
        root, worktrees, command="start", lookup=lookup, environ=environ, note=note
    )
    issue = resolve_issue(root, reference, timeout)
    note.identify(issue_id=issue.id)
    location = _session_location(session, stores, lookup)
    if location is None:
        raise IssueWorkError(
            "this Agent Session has no current hook location; nothing was written"
        )
    if not same_path(location.worktree, root):
        raise IssueWorkError(
            f"{session.session_label} is at {location.worktree} according to "
            f"its freshest {HARNESS_DISPLAY[session.harness]} hook record, not "
            f"at {root}; Issue work is declared where the session itself runs "
            f"(a tool call that changes directory, or a sub-agent, does not "
            f"move the session), so nothing was written"
        )
    found_elsewhere, unreadable_elsewhere = session_runs(
        session,
        [candidate for candidate in worktrees if not same_path(candidate, root)],
    )
    selected_elsewhere: list[tuple[Path, ActiveWork]] = []
    for candidate, _store, pending in found_elsewhere:
        refuse_other_host_process(session, pending, lookup)
        selected_elsewhere.append((candidate, pending))
        if pending.relocation is None:
            continue
        intended = Path(pending.relocation.target_worktree)
        if not same_path(intended, root):
            raise IssueWorkError(
                f"this Agent Run was prepared to resume at {intended}, not {root}; "
                "the pending run was left unchanged"
            )
        raise IssueWorkError(
            f"this Agent Run is still pending relocation from {candidate} to "
            f"{root}; its target hook has not completed the move, so nothing "
            "was written"
        )
    if unreadable_elsewhere:
        raise IssueWorkError(
            "; ".join(item.message for item in unreadable_elsewhere)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    store = WorkStore(root)
    previous, store_diagnostics = _session_work(store, session)
    if previous is not None:
        refuse_other_host_process(session, previous, lookup)
    if store_diagnostics:
        raise IssueWorkError(
            "; ".join(item.message for item in store_diagnostics)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    replacement = ActiveWork(
        session_key=previous.session_key if previous else session.session_key,
        harness=session.harness,
        session_label=session.session_label,
        session_process=session.session_process,
        issue_id=issue.id,
        issue_reference=issue.reference,
        binding_provenance="explicit-reference",
        started_at=utc_now(),
        working_directory=str(current),
        branch=branch,
        session_id=session.session_id,
    )
    if previous is None:
        store.start(replacement)
    elif not store.replace_current(previous, replacement):
        raise IssueWorkError(
            "this Agent Run changed before replacement; nothing was overwritten"
        )
    # The hooks place the session here, so a run recorded at another Worktree
    # of the Repository is where it used to be, and nobody is left behind
    # there.
    elsewhere: list[tuple[Path, ActiveWork]] = []
    for candidate, expected in selected_elsewhere:
        if not WorkStore(candidate).stop_current(expected):
            raise IssueWorkError(
                f"this session's earlier Agent Run at {candidate} changed; "
                "it was not removed. Inspect 'dashpot work show' at both Worktrees"
            )
        elsewhere.append((candidate, expected))
    if previous is None and elsewhere:
        (former_worktree, former), *rest = elsewhere
        messages = [
            f"switched from {former.issue_reference} at {former_worktree} to "
            f"{issue.reference} at {root} ({issue.id})"
        ]
        note.action = "switched"
        elsewhere = rest
    elif previous is None:
        messages = [f"started work on {issue.reference} ({issue.id})"]
        note.action = "started"
    elif previous.issue_id == issue.id:
        messages = [f"already working on {issue.reference}; run restarted"]
        note.action = "restarted"
    else:
        messages = [
            f"switched from {previous.issue_reference} to {issue.reference} "
            f"({issue.id})"
        ]
        note.action = "switched"
    messages.extend(
        f"ended this session's earlier run on {work.issue_reference} at {worktree}"
        for worktree, work in elsewhere
    )
    # A run's Worker Assignments end with it (ADR 0096): say so, since the
    # Workers themselves may still be working.
    messages.extend(
        ended_assignments(work)
        for work in (
            *(() if previous is None else (previous,)),
            *(work for _worktree, work in selected_elsewhere),
        )
        if work.workers
    )
    return messages


def relocate_issue_work(
    current: Path,
    target: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """Prepare this Codex session's active Agent Run for a verified resume.

    ``outcome`` hears the session, the Agent Run's Issue and the target
    Worktree once each is known, and what the command did.
    """
    note = outcome if outcome is not None else OutcomeNote()
    root = worktree_root(current)
    target_root = worktree_root(target)
    note.target_path = target_root
    worktrees = repository_worktrees(root)
    if not any(same_path(target_root, worktree) for worktree in worktrees):
        raise IssueWorkError(
            f"{target_root} is not a linked Worktree of the current Git Repository"
        )
    session, stores = enclosing_session(
        root, worktrees, command="relocate", lookup=lookup, environ=environ, note=note
    )
    if session.harness != "codex":
        raise IssueWorkError(
            "work relocate is for a sequential Codex resume; Claude Code moves "
            "its live session with EnterWorktree"
        )
    location = _session_location(session, stores, lookup)
    if location is None or not same_path(location.worktree, root):
        observed = "nowhere" if location is None else str(location.worktree)
        raise IssueWorkError(
            f"{session.session_label} is at {observed} according to its freshest "
            f"Codex hook record, not at {root}; nothing was written"
        )
    matches, diagnostics = session_runs(session, worktrees)
    if diagnostics:
        raise IssueWorkError(
            "; ".join(item.message for item in diagnostics)
            + "; repair the Work Store before preparing relocation"
        )
    if not matches:
        raise IssueWorkError(
            "this Agent Session has no active Issue work to preserve; resume at "
            "the target and run 'dashpot work start' there"
        )
    if len(matches) != 1:
        raise IssueWorkError(
            "this Agent Session has Issue work recorded at more than one Worktree; "
            "resolve the work-session-conflict before preparing relocation"
        )
    worktree, store, work = matches[0]
    note.identify(issue_id=work.issue_id)
    refuse_other_host_process(session, work, lookup)
    if not same_path(worktree, root):
        raise IssueWorkError(
            f"this Agent Session's active Agent Run is at {worktree}, not {root}; "
            "nothing was written"
        )
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    if same_path(root, target_root):
        if work.relocation is None:
            raise IssueWorkError(
                "the relocation target is this session's current Worktree"
            )
        _replace_current_run(
            store,
            work,
            replace(
                work,
                session_label=session.session_label,
                session_process=session.session_process,
                working_directory=str(current),
                branch=branch,
                session_id=session.session_id,
                relocation=None,
            ),
        )
        note.action = "relocation-cancelled"
        return ["cancelled the pending relocation; this Agent Run remains here"]
    _replace_current_run(
        store,
        work,
        replace(
            work,
            session_label=session.session_label,
            session_process=session.session_process,
            working_directory=str(current),
            branch=branch,
            session_id=session.session_id,
            relocation=RelocationIntent(
                target_worktree=str(target_root), requested_at=utc_now()
            ),
        ),
    )
    note.action = "relocation-prepared"
    return [
        f"prepared this Agent Run to resume at {target_root}; exit this Codex "
        f"client before resuming session {session.session_id} there"
    ]


def _replace_current_run(
    store: WorkStore, expected: ActiveWork, replacement: ActiveWork
) -> None:
    """Replace a run unless another management command changed it first."""
    try:
        replaced = store.replace_current(expected, replacement)
    except (OSError, ValueError) as exc:
        raise IssueWorkError(
            f"cannot safely update this Agent Run for relocation: {exc}"
        ) from exc
    if not replaced:
        raise IssueWorkError(
            "this Agent Run changed while relocation was being prepared; "
            "nothing was overwritten, so inspect it with 'dashpot work show'"
        )


def stop_issue_work(
    current: Path,
    *,
    session_key: str | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """End an active Agent Run of this session, or an orphaned one here.

    Without ``session_key`` the run belongs to the Agent Session enclosing this
    command, which stays alive; it is ended wherever among the Repository's
    Worktrees it is recorded, so a session that moved and simply stops does
    not leave its old Worktree live. With ``session_key`` the run is an
    Orphaned Agent Run left at this Worktree by a session that is no longer
    running, so no enclosing session is required; a session observed to be
    live is refused so its own run cannot be ended from outside. The Work
    Store's authority is unchanged either way. ``outcome`` hears which
    session's run, on which Issue, the command ended.
    """
    note = outcome if outcome is not None else OutcomeNote()
    root = worktree_root(current)
    store = WorkStore(root)
    if session_key is None:
        worktrees = repository_worktrees(root)
        session, _stores = enclosing_session(
            root, worktrees, command="stop", lookup=lookup, environ=environ, note=note
        )
        stopped, diagnostics = _stop_session_runs(session, worktrees, lookup)
        # Unreadable records are surfaced beside the outcome: this session's
        # run may be among the records that could not be read.
        warnings = [diagnostic.message for diagnostic in diagnostics]
        if not stopped:
            note.action = "no-work"
            return ["no active Issue work for this session", *warnings]
        note.identify(issue_id=stopped[0][1].issue_id)
        note.action = "stopped"
        return [
            f"stopped work on {work.issue_reference}"
            + ("" if same_path(worktree, root) else f" at {worktree}")
            + (f"; {ended_assignments(work)}" if work.workers else "")
            for worktree, work in stopped
        ] + warnings
    previous, diagnostics = _session_work_by_key(store, session_key)
    if previous is None:
        unreadable = _own_record_diagnostic(store, session_key, diagnostics)
        if unreadable is not None:
            # An unreadable record cannot answer whether its session is live,
            # so ending it from outside is refused rather than guessed at.
            raise IssueWorkError(
                f"{unreadable.message}; remove the record by hand once the "
                f"session is confirmed over"
            )
        note.action = "no-work"
        return [f"no active Issue work recorded for session {session_key}"]
    note.identify(
        harness=previous.harness,
        session_id=previous.session_id,
        issue_id=previous.issue_id,
    )
    if _recorded_session_is_live(previous, root, lookup):
        raise IssueWorkError(
            f"session {session_key} is still running; run 'dashpot work stop' inside it"
        )
    if not store.stop_current(previous):
        note.action = "no-work"
        return [f"no active Issue work recorded for session {session_key}"]
    note.action = "stopped"
    return [
        f"stopped orphaned work on {previous.issue_reference} for "
        f"{previous.session_label}"
        + (f"; {ended_assignments(previous)}" if previous.workers else "")
    ]


def ended_assignments(work: ActiveWork) -> str:
    """Name the Worker Assignments that ended with a run (ADR 0096)."""
    count = len(work.workers)
    workers = ", ".join(
        f"{worker.worker_id} on {worker.issue_reference}" for worker in work.workers
    )
    return (
        f"ended {count} Worker Assignment{'' if count == 1 else 's'} of the run "
        f"on {work.issue_reference} ({workers})"
    )


def _recorded_session_is_live(
    work: ActiveWork, root: Path, lookup: ProcessLookup
) -> bool:
    """Whether the session that recorded a run is still observed live.

    A run recorded with its host process is probed directly. One recorded by
    Agent Session Identity alone - the sandboxed route - has only its hook
    records to answer from: the freshest that is neither ended nor gone
    places a session that may still be running, and an unreadable record is
    not evidence that it is over.
    """
    if (recorded := work.session_process) is not None:
        return (
            session_liveness(
                recorded.key, lookup, namespace=recorded.pid_namespace
            ).liveness
            != "gone"
        )
    if work.session_id is None:
        return False
    try:
        location = locate_agent_session(
            reachable_hook_stores(repository_worktrees(root)),
            lookup,
            harness=work.harness,
            session_id=work.session_id,
        )
    except ValueError as exc:
        raise IssueWorkError(
            f"the lifecycle hook record for {work.session_label} cannot be "
            f"read: {exc}; run 'dashpot integrate {work.harness} --status'"
        ) from exc
    return location is not None and location.record.outcome not in {"ended", "gone"}


def forget_session_subagents(
    current: Path,
    session_id: str,
    *,
    harness: Harness | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """Forget the sub-agents an ended Agent Session still lists in this Repository.

    A ``SessionEnd`` keeps the sub-agents its session left working in an
    ended record until each ``SubagentStop`` or until its Host Process is
    gone (ADR 0095). One that was stopped, was interrupted or ended with its
    session may report nothing, so a person who has checked that none still
    works removes those records here. Only ended records are touched: a live
    session's sub-agents stay listed until it ends. Each removal is a
    compare-and-delete, so a record a hook changed since it was read is kept.
    """
    note = outcome if outcome is not None else OutcomeNote()
    root = worktree_root(current)
    stores = reachable_hook_stores(repository_worktrees(root))
    found: dict[Harness, list[StoredSessionRecord]] = {}
    unreadable = 0
    for candidate in (harness,) if harness is not None else tuple(HARNESS_DISPLAY):
        records, count = stored_session_records(stores, candidate, session_id)
        unreadable += count
        ended = [
            item
            for item in records
            if item.record.state == "ended" and item.record.live_subagents
        ]
        if ended:
            found[candidate] = ended
    if len(found) > 1:
        raise IssueWorkError(
            f"ended sessions of {' and '.join(HARNESS_DISPLAY[one] for one in found)} "
            f"are named {session_id}; choose one with --harness"
        )
    retained = [item for items in found.values() for item in items]
    warnings: list[str] = []
    if unreadable:
        warnings.append(
            f"{unreadable} hook record(s) named {session_id} cannot be read and "
            f"were left as they are"
        )
    if not retained:
        return [
            f"no ended session {session_id} lists sub-agents in this Repository",
            *warnings,
        ]
    note.identify(harness=next(iter(found)), session_id=session_id)
    messages: list[str] = []
    for item in retained:
        agents = item.record.live_subagents
        if HookRecordStore(item.store).prune(item.path.stem, item.raw):
            messages.append(
                f"forgot {named_subagents(agents)} of ended session {session_id} at {item.worktree}"
            )
        else:
            note.incomplete = True
            messages.append(
                f"the record of session {session_id} at {item.worktree} "
                f"changed while it was read; nothing of it was forgotten: "
                f"run the command again"
            )
    if not note.incomplete:
        note.action = "forgotten"
    return messages + warnings


def _orphaned(work: ActiveWork, lookup: ProcessLookup) -> bool:
    """Whether observation reports the run as an Orphaned Agent Run."""
    return (
        orphaned_process(
            work,
            lambda process: session_liveness(
                process.key, lookup, namespace=process.pid_namespace
            ),
        )
        is not None
    )


# What ``work show`` says of an assigned Worker, by what the dashboard would
# report of it (ADR 0096).
WORKER_STATE_DESCRIPTION: Mapping[WorkerState | None, str] = {
    "running": "listed as working",
    "unknown": "listed as working, but its session's liveness is unknown",
    None: "not listed as working",
}


def show_issue_work(
    current: Path, *, lookup: ProcessLookup = host_process_lookup
) -> list[str]:
    """Read the active Agent Runs recorded at the current Worktree.

    A run whose session has sub-agents listed as working is followed by
    them: they hold the run running, and one that was stopped or interrupted
    may never be reported stopped, so the line names the harness's way out
    (#374, #419).
    Then come the Workers the run assigned (ADR 0096), each saying whether
    its session lists it as working.
    """
    root = worktree_root(current)
    active, diagnostics = WorkStore(root).active()
    delegating: list[SessionLocation] = []
    workers = NO_WORKER_EVIDENCE
    if active:
        worktrees = repository_worktrees(root)
        stores = reachable_hook_stores(worktrees)
        delegating = sessions_with_live_subagents(worktrees, stores, lookup)
        workers = WorkerEvidence.recorded(stores, lookup)
    messages: list[str] = []
    for work in active:
        messages.append(
            f"{work.session_label}: {work.issue_reference} ({work.issue_id}) "
            f"since {work.started_at}"
            + (
                f"; relocation pending to {work.relocation.target_worktree}"
                if work.relocation is not None
                else ""
            )
        )
        for location in delegating:
            if location.record.evidence.match(work.evidence) != "same":
                continue
            record = location.record
            agents = record.live_subagents
            if record.outcome == "ended":
                messages.append(
                    f"  {work.session_label} ended with "
                    f"{named_subagents(agents)}. "
                    f"{ended_session_subagent_stop(work.harness, record.session_id)}"
                )
                continue
            messages.append(
                f"  {work.session_label} has {named_subagents(agents)}. "
                f"{unreported_subagent_stop(work.harness)}"
            )
        messages.extend(
            f"  assigned Worker {worker.worker_id} to {worker.issue_reference_hint} "
            f"({worker.issue_id}) at {worker.worktree}; "
            + WORKER_STATE_DESCRIPTION[worker.state]
            for worker in assigned_workers(
                # Observation reports nothing of an Orphaned Agent Run's Workers.
                work,
                NO_WORKER_EVIDENCE if _orphaned(work, lookup) else workers,
            )
        )
    messages.extend(diagnostic.message for diagnostic in diagnostics)
    if not messages:
        messages = ["no active Issue work at this worktree"]
    return messages


# How many of a session's recent events ``work show`` lists, from how far back.
RECENT_SESSION_EVENTS = 20
RECENT_SESSION_DAYS = 7


def show_session_events(
    current: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """List the enclosing Agent Session's recent outcomes from the Event Log.

    Its hook and command outcomes, Agent Session and Agent Run changes and
    failures, at most :data:`RECENT_SESSION_EVENTS` of them from the last
    :data:`RECENT_SESSION_DAYS` days, read from every Worktree of the
    Repository and the machine-local fallback. A command a Sub-agent runs
    lists its session's. A command no supported session encloses lists
    nothing, as does a session with no such events.
    """
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    try:
        session, _stores = enclosing_session(
            root, worktrees, command=None, lookup=lookup, environ=environ
        )
    except DashpotError:
        # Whatever keeps the session from being identified, the Issue work
        # ``work show`` lists stands on its own.
        return []
    moment = now if now is not None else datetime.now(UTC)
    selection = EventSelection(
        session=session.session_id,
        harness=session.harness,
        since=moment - timedelta(days=RECENT_SESSION_DAYS),
        outcomes_only=True,
    )
    events = recent_events(
        event_log_directories(worktrees), selection, limit=RECENT_SESSION_EVENTS
    )
    if not events:
        return []
    return [
        f"recent events of {session.session_label}:",
        *(f"  {describe_runtime_event(event)}" for event in events),
    ]


def _session_location(
    session: AgentSessionIdentity, stores: Sequence[Path], lookup: ProcessLookup
) -> SessionLocation | None:
    """Where the session's hooks last placed it, if they have placed it at all.

    A record that is ended or whose process is gone describes a session that
    is over, never where this live one is.
    """
    try:
        location = locate_agent_session(
            stores,
            lookup,
            harness=session.harness,
            session_id=session.session_id,
        )
    except ValueError as exc:
        raise IssueWorkError(
            f"the lifecycle hook record for {session.session_label} cannot be "
            f"read: {exc}; run 'dashpot integrate {session.harness} --status'"
        ) from exc
    if location is None or location.record.outcome in {"ended", "gone"}:
        return None
    return location


def _stop_session_runs(
    session: AgentSessionIdentity,
    worktrees: Sequence[Path],
    lookup: ProcessLookup,
) -> tuple[list[tuple[Path, ActiveWork]], list[Diagnostic]]:
    """End the session's active runs at every Worktree of the Repository.

    Each Worktree's unreadable Work Store records come back beside the runs:
    a corrupt record could hide the very run this session is looking for.
    """
    selected, diagnostics = session_runs(session, worktrees)
    for _worktree, _store, work in selected:
        refuse_other_host_process(session, work, lookup)
    if selected and diagnostics:
        raise IssueWorkError(
            "unreadable Work Store records prevent safe ownership selection; nothing was removed"
        )
    stopped: list[tuple[Path, ActiveWork]] = []
    for worktree, store, work in selected:
        if not store.stop_current(work):
            raise IssueWorkError(
                "this Agent Run changed before stopping; the changed run was not removed"
            )
        stopped.append((worktree, work))
    return stopped, diagnostics


def refuse_other_host_process(
    session: AgentSessionIdentity, work: ActiveWork, lookup: ProcessLookup
) -> None:
    """Refuse to change a run that another live or unobservable Host Process may own."""
    recorded = work.session_process
    if (recorded.key if recorded else None) != session.process_key and (
        recorded is None
        or session_liveness(
            recorded.key, lookup, namespace=recorded.pid_namespace
        ).liveness
        != "gone"
    ):
        raise IssueWorkError(
            "this Agent Session has an Agent Run owned by another live or "
            "unobservable runtime; nothing was changed"
        )


def session_runs(
    session: AgentSessionIdentity, worktrees: Sequence[Path]
) -> tuple[list[tuple[Path, WorkStore, ActiveWork]], list[Diagnostic]]:
    """The session's Agent Run at each of ``worktrees``, with unreadable records' Diagnostics.

    More than one run means the session's runs conflict. An unreadable Work
    Store record could be one of the session's runs, so each caller decides
    what its Diagnostic means for its command.
    """
    found: list[tuple[Path, WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        work, store_diagnostics = _session_work(store, session)
        diagnostics.extend(store_diagnostics)
        if work is not None:
            found.append((worktree, store, work))
    return found, diagnostics


def _session_work_by_key(
    store: WorkStore, session_key: str
) -> tuple[ActiveWork | None, list[Diagnostic]]:
    """One session's recorded run by key, with the store's diagnostics."""
    active, diagnostics = store.active()
    found = next((work for work in active if work.session_key == session_key), None)
    return found, diagnostics


def _own_record_diagnostic(
    store: WorkStore, session_key: str, diagnostics: Sequence[Diagnostic]
) -> Diagnostic | None:
    """The diagnostic for exactly this session key's record, if it has one."""
    if not SESSION_KEY.fullmatch(session_key):
        return None
    source = f"work:{store.record_path(session_key)}"
    return next(
        (diagnostic for diagnostic in diagnostics if diagnostic.source == source),
        None,
    )


def _session_work(
    store: WorkStore, session: AgentSessionIdentity
) -> tuple[ActiveWork | None, list[Diagnostic]]:
    """Select one named run while refusing unresolved legacy ownership."""
    active, diagnostics = store.active()
    identity = SessionEvidence(session.harness, session.session_id, session.process_key)
    matches: list[ActiveWork] = []
    for work in active:
        relation = identity.match(work.evidence)
        if relation == "unresolved":
            raise IssueWorkError(
                f"ownership of legacy Agent Run {work.session_key} at {store.directory} "
                "is unresolved; nothing was changed. After its recorded process is "
                f"proved gone, run 'dashpot work stop --session {work.session_key}' "
                "at that Worktree, then declare Issue work again"
            )
        if relation == "same":
            matches.append(work)
        elif work.session_key == session.session_key:
            raise IssueWorkError(
                "the destination is occupied by a conflicting identity"
            )
    if len(matches) > 1:
        raise IssueWorkError(
            "conflicting Agent Runs for this Agent Session; inspect 'dashpot work show' "
            "and end the exact obsolete run with 'dashpot work stop --session'"
        )
    return next(iter(matches), None), diagnostics
