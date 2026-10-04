"""Declare, relocate, end, and show Issue work for the enclosing Agent Session.

A Lead's ``work assign`` and ``work unassign`` live here too, since a Worker
Assignment belongs to the Lead's Agent Run (ADR 0096), as does ``work
forget-subagents``: it forgets the sub-agents an ended Agent Session still
lists, which hold Worktree Cleanup as its Issue work did.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
    harness_alternatives,
)
from ..core.timestamps import utc_now
from ..core.worktree_paths import repository_worktrees, same_path, worktree_root
from ..issues.issue_resolution import resolve_issue
from .agents import (
    NO_WORKER_EVIDENCE,
    WorkerEvidence,
    assigned_workers,
)
from .harnesses import (
    SESSION_ID,
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    adapter,
    native_claims,
    opencode_shell_refusal,
    override_claim,
)
from .hook_claims import (
    SessionClaimError,
    ValidatedSessionIdentity,
    validate_session_claim,
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
from .processes import (
    AgentAncestry,
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .session_exits import (
    ended_session_subagent_stop,
    named_subagents,
    unreported_subagent_stop,
)
from .session_labels import work_session_label
from .session_matching import SessionEvidence
from .work_store import (
    SESSION_KEY,
    ActiveWork,
    RelocationIntent,
    SessionProcess,
    WorkerAssignment,
    WorkStore,
)


class IssueWorkError(DashpotError):
    """A refusal of a work management command, for the enclosing or a named Agent Session."""


@dataclass(frozen=True, slots=True)
class AgentSessionIdentity:
    """Represent a confirmed Agent Session and its corroborating process evidence.

    ``delegate`` names the Sub-agent the command runs in, when its harness
    tells a Sub-agent's shell apart from its session's own: the identity is
    still the session's, so reading resolves to it, but every command that
    changes the session's Issue work refuses (ADR 0067). Only Codex sets it:
    an OpenCode child session's claim is refused at validation instead
    (ADR 0090), and a Claude Code Sub-agent's shell carries its session's
    own identity.
    """

    harness: Harness
    session_key: str
    session_label: str
    process: ProcessIdentity | None
    session_id: str | None = None
    delegate: str | None = None

    @property
    def session_process(self) -> SessionProcess | None:
        if self.process is None:
            return None
        return SessionProcess(pid=self.process.pid, started_at=self.process.started_at)

    @property
    def process_key(self) -> ProcessKey | None:
        if self.process is None:
            return None
        return self.process.pid, self.process.started_at


def identify_agent_session(
    lookup: ProcessLookup = host_process_lookup,
    *,
    environ: Mapping[str, str] | None = None,
    worktree: Path | None = None,
    stores: Sequence[Path] | None = None,
) -> AgentSessionIdentity:
    """Identify the enclosing session by a hook-confirmed native identity.

    A Sub-agent's command identifies its session, with ``delegate`` set, so
    a caller that changes Issue work refuses it with ``_refuse_delegate``.
    """
    environment = environ if environ is not None else os.environ
    ancestry = observe_agent_ancestry(lookup)
    claims = _session_claims(environment)
    if not claims:
        raise IssueWorkError(_no_session_message(ancestry, environment))
    if worktree is None:
        raise IssueWorkError(
            "an Agent Session Identity claimed by the environment can only be "
            "validated at a Worktree with a Project-local hook record store"
        )
    validated: list[ValidatedSessionIdentity] = []
    failures: list[str] = []
    for claim in claims:
        try:
            validated.append(
                validate_session_claim(claim, worktree, lookup, stores=stores)
            )
        except SessionClaimError as exc:
            failures.append(str(exc))
    if len(validated) == 1:
        confirmed = validated[0]
        if ancestry.located is not None:
            harness, process = ancestry.located
            if harness != confirmed.harness or (
                confirmed.process is not None and confirmed.process.key != process.key
            ):
                raise IssueWorkError(
                    "the claimed Agent Session Identity does not corroborate the "
                    "enclosing harness process; nothing was written"
                )
            return _process_identity(
                harness, process, confirmed.session_id, confirmed.delegate
            )
        return _session_identity(confirmed)
    if validated:
        names = " and ".join(
            f"{HARNESS_DISPLAY[item.harness]} session {item.session_id}"
            for item in validated
        )
        raise IssueWorkError(
            f"the environment claims more than one live Agent Session ({names}); "
            f"set {SESSION_OVERRIDE_VARIABLE}=<harness>:<session id> to say which "
            f"session this command belongs to"
        )
    raise IssueWorkError(
        _no_session_message(ancestry, environment) + "; " + "; ".join(failures)
    )


def _session_claims(environment: Mapping[str, str]) -> list[SessionIdentityClaim]:
    """The identities to validate: an explicit override alone, else every native claim."""
    explicit = override_claim(environment)
    if explicit is not None:
        return [explicit]
    return native_claims(environment)


def _no_session_message(ancestry: AgentAncestry, environment: Mapping[str, str]) -> str:
    unobservable_reason = ancestry.unobservable_reason
    message = (
        "no supported agent session encloses this command; Issue work opt-in "
        f"must run from inside a running {harness_alternatives()} session"
    )
    in_opencode = ancestry.located is not None and ancestry.located[0] == "opencode"
    refusal = opencode_shell_refusal(environment, in_opencode)
    if refusal is not None:
        message += f" ({refusal})"
    if unobservable_reason == "isolated-namespace":
        message += (
            " (this command runs in a sandbox's isolated process namespace, so "
            "the harness must be identified by the Agent Session Identity its "
            "lifecycle hooks publish; check 'dashpot integrate <harness> --status')"
        )
    elif unobservable_reason is not None:
        message += (
            f" (the enclosing process could not be observed: {unobservable_reason})"
        )
    return message


def _process_identity(
    harness: Harness,
    process: ProcessIdentity,
    session_id: str,
    delegate: str | None,
) -> AgentSessionIdentity:
    return AgentSessionIdentity(
        harness=harness,
        session_key=SessionEvidence(harness, session_id).storage_key(),
        session_label=work_session_label(harness, session_id, pid=process.pid),
        process=process,
        session_id=session_id,
        delegate=delegate,
    )


def _session_identity(confirmed: ValidatedSessionIdentity) -> AgentSessionIdentity:
    """Identify a session by its confirmed native identity on either route."""
    return AgentSessionIdentity(
        harness=confirmed.harness,
        session_key=SessionEvidence(
            confirmed.harness, confirmed.session_id
        ).storage_key(),
        session_label=work_session_label(
            confirmed.harness,
            confirmed.session_id,
            pid=confirmed.process.pid if confirmed.process is not None else None,
        ),
        process=confirmed.process,
        session_id=confirmed.session_id,
        delegate=confirmed.delegate,
    )


def _refuse_delegate(session: AgentSessionIdentity, command: str) -> None:
    """Refuse a command that changes Issue work when a Sub-agent runs it.

    A Sub-agent's work belongs to its session's Agent Run, so only the
    session itself starts, moves, ends or assigns that run (ADR 0067), as an
    OpenCode child session is refused (ADR 0090).
    """
    if session.delegate is None:
        return
    raise IssueWorkError(
        f"{HARNESS_DISPLAY[session.harness]} sub-agent {session.delegate} is "
        f"refused (delegated-session): it is a sub-agent of session "
        f"{session.session_id}, whose Agent Run its work belongs to; run "
        f"'dashpot work {command}' from session {session.session_id}, so "
        f"nothing was written"
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
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    note.identify(harness=session.harness, session_id=session.session_id)
    _refuse_delegate(session, "start")
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
    unreadable_elsewhere: list[Diagnostic] = []
    selected_elsewhere: list[tuple[Path, ActiveWork]] = []
    for candidate in worktrees:
        if same_path(candidate, root):
            continue
        pending, candidate_diagnostics = _session_work(WorkStore(candidate), session)
        unreadable_elsewhere.extend(candidate_diagnostics)
        if pending is None:
            continue
        _check_runtime(session, pending, lookup)
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
    if session.session_id is not None and unreadable_elsewhere:
        raise IssueWorkError(
            "; ".join(item.message for item in unreadable_elsewhere)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    store = WorkStore(root)
    previous, store_diagnostics = _session_work(store, session)
    if previous is not None:
        _check_runtime(session, previous, lookup)
    if session.session_id is not None and store_diagnostics:
        raise IssueWorkError(
            "; ".join(item.message for item in store_diagnostics)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    unreadable = _own_record_diagnostic(store, session.session_key, store_diagnostics)
    if unreadable is not None:
        # Writing beside an unreadable record for this session's own key would
        # leave two records for one session, so this is a refusal instead.
        raise IssueWorkError(
            f"{unreadable.message}; fix or remove the record before declaring "
            f"Issue work, so this session keeps one record"
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
    # Other sessions' unreadable records do not block this start, but they
    # are surfaced rather than dropped, as `work show` already surfaces them.
    messages.extend(diagnostic.message for diagnostic in store_diagnostics)
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
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    note.identify(harness=session.harness, session_id=session.session_id)
    _refuse_delegate(session, "relocate")
    if session.harness != "codex":
        raise IssueWorkError(
            "work relocate is for a sequential Codex resume; Claude Code moves "
            "its live session with EnterWorktree"
        )
    if session.session_id is None:
        raise IssueWorkError(
            "the Codex Agent Session Identity is not confirmed by its lifecycle "
            "hook record; run 'dashpot integrate codex --status'"
        )
    location = _session_location(session, stores, lookup)
    if location is None or not same_path(location.worktree, root):
        observed = "nowhere" if location is None else str(location.worktree)
        raise IssueWorkError(
            f"{session.session_label} is at {observed} according to its freshest "
            f"Codex hook record, not at {root}; nothing was written"
        )
    matches: list[tuple[Path, WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        work, found_diagnostics = _session_work(store, session)
        diagnostics.extend(found_diagnostics)
        if work is not None:
            matches.append((worktree, store, work))
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
    _check_runtime(session, work, lookup)
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
        session = identify_agent_session(
            lookup,
            environ=environ,
            worktree=root,
            stores=reachable_hook_stores(worktrees),
        )
        note.identify(harness=session.harness, session_id=session.session_id)
        _refuse_delegate(session, "stop")
        stopped, diagnostics = _stop_elsewhere(session, worktrees, None, lookup)
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
    if work.session_process is not None:
        return session_liveness(work.session_process.key, lookup).liveness != "gone"
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


def assign_worker(
    current: Path,
    reference: str,
    worker_id: str,
    worktree: Path,
    *,
    timeout: float = 10,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """Assign one of this Lead's working Sub-agents, as a Worker, to an Issue.

    The assignment joins the session's own active Agent Run, unchanged in
    its Issue Binding, identity and location, and ends with it (ADR 0096).
    The Worker must be a Sub-agent this session's hooks list as working, so
    a mistyped or foreign identity is refused rather than recorded.
    ``worktree`` is where the Lead intends the Worker's commands to run: it
    must be a Worktree of this Repository, and is never taken as evidence
    that the Worker is there. ``outcome`` hears the session, the Issue and
    the Worktree once each is confirmed, and what the command did.
    """
    note = outcome if outcome is not None else OutcomeNote()
    if not SESSION_ID.fullmatch(worker_id):
        raise IssueWorkError(
            f"{worker_id!r} is not a Sub-agent identity a harness publishes; "
            "nothing was written"
        )
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    intended = next(
        (
            candidate
            for candidate in worktrees
            if same_path(candidate, worktree.expanduser().resolve())
        ),
        None,
    )
    if intended is None:
        raise IssueWorkError(
            f"{worktree} is not a Worktree of the current Git Repository; "
            "nothing was written"
        )
    note.target_path = intended
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    note.identify(harness=session.harness, session_id=session.session_id)
    _refuse_delegate(session, "assign")
    store, work = _assigning_run(session, worktrees, lookup)
    if work.evidence.process_key not in (None, session.process_key):
        # The run is orphaned under a Host Process that is gone (the runtime
        # check refused a live one), and observation reports none of an
        # Orphaned Agent Run's Workers until this session continues it.
        # Only a harness whose session owns its Host Process, or a declared
        # relocation, has a hook event take the run over; any other run is
        # recovered with ``work start``, which ends its assignments.
        recovery = (
            "assign once this session's next hook event has continued the run"
            if work.relocation is not None
            or adapter(work.harness).exclusive_session_process
            else f"recover it with 'dashpot work start {work.issue_reference}' "
            "from this session, which ends its Worker Assignments, then assign "
            "each Worker again"
        )
        raise IssueWorkError(
            "this session's Agent Run is still recorded under its earlier Host "
            f"Process, which is gone; {recovery}, so nothing was written"
        )
    issue = resolve_issue(root, reference, timeout)
    note.identify(issue_id=issue.id)
    if (
        WorkerEvidence.recorded(stores, lookup).state(
            work.harness, work.session_id, work.evidence.process_key, worker_id
        )
        is None
    ):
        raise IssueWorkError(
            f"{session.session_label} lists no Sub-agent {worker_id} as working; "
            "assign a Worker once its harness has reported it started, by the "
            "identity its launch returned, so nothing was written"
        )
    assigned = WorkerAssignment(
        worker_id=worker_id,
        issue_id=issue.id,
        issue_reference=issue.reference,
        worktree=str(intended),
        assigned_at=utc_now(),
    )
    previous = next(
        (item for item in work.workers if item.worker_id == worker_id), None
    )
    if previous is not None and (previous.issue_id, previous.worktree) == (
        assigned.issue_id,
        assigned.worktree,
    ):
        return [
            f"Worker {worker_id} is already assigned to {issue.reference} "
            f"({issue.id}) at {intended}"
        ]
    workers = (
        *(item for item in work.workers if item.worker_id != worker_id),
        assigned,
    )
    _replace_assigning_run(store, work, replace(work, workers=workers))
    if previous is None:
        note.action = "assigned"
        return [
            f"assigned Worker {worker_id} to {issue.reference} ({issue.id}) at {intended}"
        ]
    note.action = "reassigned"
    return [
        f"reassigned Worker {worker_id} from {previous.issue_reference} at "
        f"{previous.worktree} to {issue.reference} ({issue.id}) at {intended}"
    ]


def unassign_worker(
    current: Path,
    worker_id: str,
    *,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """End one Worker Assignment of this session's active Agent Run.

    Nothing about the Worker is checked: one that finished, failed or was
    stopped is unassigned the same way, and the run is otherwise unchanged.
    """
    note = outcome if outcome is not None else OutcomeNote()
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    session = identify_agent_session(
        lookup,
        environ=environ,
        worktree=root,
        stores=reachable_hook_stores(worktrees),
    )
    note.identify(harness=session.harness, session_id=session.session_id)
    _refuse_delegate(session, "unassign")
    store, work = _assigning_run(session, worktrees, lookup)
    previous = next(
        (item for item in work.workers if item.worker_id == worker_id), None
    )
    if previous is None:
        note.action = "no-assignment"
        return [f"this session's Agent Run assigns no Worker {worker_id}"]
    note.identify(issue_id=previous.issue_id)
    _replace_assigning_run(
        store,
        work,
        replace(
            work,
            workers=tuple(item for item in work.workers if item.worker_id != worker_id),
        ),
    )
    note.action = "unassigned"
    return [f"unassigned Worker {worker_id} from {previous.issue_reference}"]


def _assigning_run(
    session: AgentSessionIdentity, worktrees: Sequence[Path], lookup: ProcessLookup
) -> tuple[WorkStore, ActiveWork]:
    """The session's one active Agent Run, wherever in the Repository it is."""
    found: list[tuple[WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        work, store_diagnostics = _session_work(store, session)
        diagnostics.extend(store_diagnostics)
        if work is not None:
            found.append((store, work))
    if diagnostics:
        raise IssueWorkError(
            "; ".join(item.message for item in diagnostics)
            + "; repair the Work Store before assigning Workers"
        )
    if not found:
        raise IssueWorkError(
            "this Agent Session has no active Issue work to assign Workers "
            "under; a Lead binds its Arc with 'dashpot work start' first"
        )
    if len(found) > 1:
        raise IssueWorkError(
            "this Agent Session has Issue work recorded at more than one "
            "Worktree; resolve the work-session-conflict before assigning Workers"
        )
    store, work = found[0]
    _check_runtime(session, work, lookup)
    return store, work


def _orphaned(work: ActiveWork, lookup: ProcessLookup) -> bool:
    """Whether observation reports the run as an Orphaned Agent Run."""
    return (
        work.relocation is None
        and work.session_process is not None
        and session_liveness(work.session_process.key, lookup).liveness == "gone"
    )


def _replace_assigning_run(
    store: WorkStore, expected: ActiveWork, replacement: ActiveWork
) -> None:
    """Replace the run's assignments unless something changed the run first."""
    if not store.replace_current(expected, replacement):
        raise IssueWorkError(
            "this Agent Run changed while its Workers were being assigned; "
            "nothing was overwritten, so inspect it with 'dashpot work show'"
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
        session = identify_agent_session(
            lookup,
            environ=environ,
            worktree=root,
            stores=reachable_hook_stores(worktrees),
        )
    except DashpotError:
        # Whatever keeps the session from being identified, the Issue work
        # ``work show`` lists stands on its own.
        return []
    if session.session_id is None:
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
    if session.session_id is None and session.process_key is None:
        return None
    try:
        location = locate_agent_session(
            stores,
            lookup,
            harness=session.harness,
            session_id=session.session_id,
            process_key=session.process_key,
        )
    except ValueError as exc:
        raise IssueWorkError(
            f"the lifecycle hook record for {session.session_label} cannot be "
            f"read: {exc}; run 'dashpot integrate {session.harness} --status'"
        ) from exc
    if location is None or location.record.outcome in {"ended", "gone"}:
        return None
    return location


def _stop_elsewhere(
    session: AgentSessionIdentity,
    worktrees: Sequence[Path],
    here: Path | None,
    lookup: ProcessLookup,
) -> tuple[list[tuple[Path, ActiveWork]], list[Diagnostic]]:
    """End the session's active runs at every Worktree other than ``here``.

    Each Worktree's unreadable Work Store records come back beside the runs:
    a corrupt record could hide the very run this session is looking for.
    """
    selected: list[tuple[Path, WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        if here is not None and same_path(worktree, here):
            continue
        store = WorkStore(worktree)
        work, store_diagnostics = _session_work(store, session)
        diagnostics.extend(store_diagnostics)
        if work is not None:
            _check_runtime(session, work, lookup)
            selected.append((worktree, store, work))
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


def _check_runtime(
    session: AgentSessionIdentity, work: ActiveWork, lookup: ProcessLookup
) -> None:
    """Refuse reassignment while another runtime may still own the run."""
    recorded = work.session_process.key if work.session_process else None
    if recorded != session.process_key and (
        recorded is None or session_liveness(recorded, lookup).liveness != "gone"
    ):
        raise IssueWorkError(
            "this Agent Session has an Agent Run owned by another live or "
            "unobservable runtime; nothing was changed"
        )


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
