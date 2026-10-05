"""Assign a Lead's working Sub-agents, as Workers, to Issues, and end those assignments.

A Worker Assignment belongs to the Lead's own active Agent Run and ends with
it (ADR 0096), so ``work assign`` and ``work unassign`` find that run the way
every ``work`` command does and change only its Workers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from ..core.command_outcomes import OutcomeNote
from ..core.timestamps import utc_now
from ..core.worktree_paths import repository_worktrees, same_path, worktree_root
from ..issues.issue_resolution import resolve_issue
from .agent_runs import WorkerEvidence
from .harnesses import SESSION_ID, adapter
from .processes import ProcessLookup, host_process_lookup
from .session_identity import AgentSessionIdentity, IssueWorkError, enclosing_session
from .work import refuse_other_host_process, session_runs
from .work_store import ActiveWork, WorkerAssignment, WorkStore


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
    session, stores = enclosing_session(
        root, worktrees, command="assign", lookup=lookup, environ=environ, note=note
    )
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
    session, _stores = enclosing_session(
        root, worktrees, command="unassign", lookup=lookup, environ=environ, note=note
    )
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
    found, diagnostics = session_runs(session, worktrees)
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
    _worktree, store, work = found[0]
    refuse_other_host_process(session, work, lookup)
    return store, work


def _replace_assigning_run(
    store: WorkStore, expected: ActiveWork, replacement: ActiveWork
) -> None:
    """Replace the run's assignments unless something changed the run first."""
    if not store.replace_current(expected, replacement):
        raise IssueWorkError(
            "this Agent Run changed while its Workers were being assigned; "
            "nothing was overwritten, so inspect it with 'dashpot work show'"
        )
