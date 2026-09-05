"""Observe Agent Runs and Agent Sessions across Work Stores and hook stores."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .hook_records import (
    HookRecordClassification,
    HookRecordStore,
    observed_instant,
    scan_hook_stores,
    session_directory,
    state_directory,
)
from .liveness import LivenessObservation, LivenessProbe
from .model import AgentRun, Diagnostic, ObservationTarget, RunState
from .processes import ProcessKey, ProcessLookup, host_process_lookup
from .repository import is_within
from .work_store import ActiveWork, WorkStore

# Diagnostics about hook Agent Session records are harness-neutral.
SESSION_DIAGNOSTIC_SOURCE = "agent-sessions"


@dataclass(frozen=True, slots=True)
class HookSessionObservation:
    run: AgentRun
    process_key: ProcessKey | None
    liveness: LivenessObservation
    session_id: str


@dataclass(frozen=True, slots=True)
class ObservedActivity:
    """What the hooks have seen a run doing, for a Work Store run to adopt."""

    state: RunState
    last_activity_at: str | None
    turn_started_at: str | None


SessionIdentityKey = tuple[str, str]


def observe_agent_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Observe Work Store Agent Runs and unmatched hook Agent Sessions.

    This is the only place Session Liveness becomes an outcome. Callers
    receive active runs plus actionable diagnostics: a gone session with an
    Issue Binding is an Orphaned Agent Run and is reported once; a gone
    unbound session is stale observation state and is dropped silently.
    """
    probe = LivenessProbe(lookup)
    sessions, diagnostics = observe_hook_sessions(targets_by_project, directory, probe)
    activity = ObservedActivityIndex(sessions)
    work_runs, work_diagnostics = observe_work_runs(
        targets_by_project, probe, activity, directory
    )
    diagnostics.extend(work_diagnostics)
    diagnostics.extend(activity.diagnostics)
    runs = list(work_runs)
    runs.extend(session.run for session in sessions if not activity.consumed(session))
    return runs, diagnostics


class ObservedActivityIndex:
    """Join Work Store runs to hook Agent Sessions by either identity.

    A run correlates by the harness's Agent Session Identity when the record
    carries one, else by host process identity; a hook session joined to a
    run is consumed so the pane lists the session once.
    """

    def __init__(self, sessions: Sequence[HookSessionObservation]) -> None:
        self._by_session: dict[SessionIdentityKey, HookSessionObservation] = {}
        self._by_process: dict[ProcessKey, list[HookSessionObservation]] = {}
        for session in sessions:
            self._by_session[session.run.harness, session.session_id] = session
            if session.process_key is not None:
                self._by_process.setdefault(session.process_key, []).append(session)
        self._consumed: set[SessionIdentityKey] = set()
        self._reported: set[ProcessKey] = set()
        self.diagnostics: list[Diagnostic] = []

    def adopt(
        self,
        harness: str,
        session_id: str | None,
        process_key: ProcessKey | None,
    ) -> ObservedActivity | None:
        session = None
        if session_id is not None:
            session = self._by_session.get((harness, session_id))
        if session is None and process_key is not None:
            session = self._freshest_by_process(process_key)
        if session is None:
            return None
        self._consumed.add((session.run.harness, session.session_id))
        return ObservedActivity(
            session.run.state,
            session.run.last_activity_at,
            session.run.turn_started_at,
        )

    def _freshest_by_process(
        self, process_key: ProcessKey
    ) -> HookSessionObservation | None:
        """Resolve a process key to one session, reporting any ambiguity.

        A resumed session reuses its host process, so two hook records can
        share one key; the freshest is adopted and the tie is reported rather
        than silently resolved. A Work Store record that carries an Agent
        Session Identity never reaches this route.
        """
        candidates = self._by_process.get(process_key)
        if not candidates:
            return None
        # ``max`` keeps the first-scanned candidate on an equal instant, which
        # is deterministic because stores and records are scanned in sorted
        # order; the per-session fold prefers the last-scanned instead.
        freshest = max(
            candidates,
            key=lambda candidate: observed_instant(candidate.run.last_activity_at),
        )
        if len(candidates) > 1 and process_key not in self._reported:
            self._reported.add(process_key)
            self.diagnostics.append(
                Diagnostic(
                    source=SESSION_DIAGNOSTIC_SOURCE,
                    severity="warning",
                    message=f"{len(candidates)} Agent Sessions share host process "
                    f"{process_key[0]}; adopting the freshest "
                    f"({freshest.session_id}). A resumed session keeps its host "
                    f"process; run 'dashpot work start' from the session to "
                    f"record its Agent Session Identity",
                    code="agent-session-process-ambiguous",
                )
            )
        return freshest

    def consumed(self, session: HookSessionObservation) -> bool:
        return (session.run.harness, session.session_id) in self._consumed


def observe_work_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    probe: LivenessProbe,
    activity: ObservedActivityIndex,
    directory: Path | None,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Turn each Worktree's active Work Store records into bound Agent Runs."""
    runs: list[AgentRun] = []
    diagnostics: list[Diagnostic] = []
    sessions_seen: set[tuple[str, ...]] = set()
    for project_id, target in available_targets(targets_by_project):
        store = WorkStore(Path(target.path))
        active, store_diagnostics = store.active()
        diagnostics.extend(store_diagnostics)
        sweep_work_store(store)
        for work in active:
            process_key = work_process_key(work)
            if work.relocation is None and work.session_process is not None:
                liveness = probe.observe(work.session_process.key)
                if liveness.liveness == "gone":
                    diagnostics.append(orphaned_run_diagnostic(work, target))
                    continue
            identities = run_identities(work, process_key)
            if identities & sessions_seen:
                diagnostics.append(conflicting_run_diagnostic(work))
            sessions_seen |= identities
            observed = activity.adopt(work.harness, work.session_id, process_key)
            if observed is None:
                # No hook has ever reported this run; the Work Store knows
                # when the work began and nothing about what it has done.
                observed = ObservedActivity("unknown", None, None)
            runs.append(work_to_run(work, target, project_id, observed))
            if work.relocation is not None:
                diagnostics.append(
                    relocation_diagnostic(
                        work,
                        target,
                        targets_by_project[project_id],
                        directory,
                        probe,
                    )
                )
    return runs, diagnostics


def available_targets(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> Iterator[tuple[str, ObservationTarget]]:
    """Iterate the available Observation Targets in stable Project order."""
    for project_id, targets in sorted(targets_by_project.items()):
        for target in targets:
            if target.availability == "available":
                yield project_id, target


def sweep_work_store(store: WorkStore) -> None:
    """Reclaim a Work Store's leftovers without letting cleanup fail a scan.

    Runs stopped before their lock files were reclaimed leave orphaned locks
    behind; sweep those that guard nothing, and the temporary files a crashed
    writer never renamed into place.
    """
    for session_key in store.orphaned_locks():
        with contextlib.suppress(OSError):
            store.prune_lock(session_key)
    with contextlib.suppress(OSError):
        store.sweep_temporaries()


def work_process_key(work: ActiveWork) -> ProcessKey | None:
    """Key a Work Store run by its recorded host process identity, if any."""
    if work.session_process is None:
        return None
    return (work.session_process.pid, work.session_process.started_at)


def orphaned_run_diagnostic(work: ActiveWork, target: ObservationTarget) -> Diagnostic:
    """Report a gone session that still records Issue work at one Worktree."""
    return Diagnostic(
        source=work.run_id,
        severity="warning",
        message=f"{work.session_label} is gone but still "
        f"records Issue work on "
        f"{work.issue_reference} ({work.issue_id}) at "
        f"{target.path}; run 'dashpot work stop "
        f"--session {work.session_key}' at that "
        f"Worktree to end the orphaned Agent Run",
        code="work-session-orphaned",
    )


def relocation_diagnostic(
    work: ActiveWork,
    target: ObservationTarget,
    project_targets: Sequence[ObservationTarget],
    directory: Path | None,
    probe: LivenessProbe,
) -> Diagnostic:
    """Report why a declared relocation has not completed yet."""
    assert work.relocation is not None
    stores: list[Path] = [directory or state_directory()]
    stores.extend(session_directory(Path(item.path)) for item in project_targets)
    unique_stores = list(dict.fromkeys(path.resolve() for path in stores))
    locations: set[Path] = set()
    if work.session_id is not None:
        for scanned in scan_hook_stores(
            unique_stores,
            probe,
            select=lambda path: path.stem == work.session_id,
        ):
            if (
                scanned.record.harness == work.harness
                and scanned.record.outcome not in {"ended", "gone"}
            ):
                try:
                    locations.add(
                        Path(
                            scanned.record.repository_root or scanned.record.cwd
                        ).resolve()
                    )
                except (OSError, RuntimeError, ValueError):
                    continue
    if len(locations) > 1:
        places = ", ".join(str(path) for path in sorted(locations, key=str))
        return Diagnostic(
            source=work.run_id,
            severity="warning",
            message=(
                f"{work.session_label} cannot complete its relocation while "
                "the same Agent Session Identity is live or unobservable at "
                f"multiple Worktrees: {places}; exit the old Codex client and "
                "begin another turn at the intended target"
            ),
            code="work-relocation-concurrent",
        )
    if len(locations) == 1:
        observed_location = next(iter(locations))
        try:
            intended = Path(work.relocation.target_worktree).resolve()
            source = Path(target.path).resolve()
        except (OSError, RuntimeError, ValueError):
            intended = source = observed_location
        if observed_location not in {source, intended}:
            return Diagnostic(
                source=work.run_id,
                severity="warning",
                message=(
                    f"{work.session_label} resumed at {observed_location}, not its "
                    f"intended relocation target {intended}; the Issue work on "
                    f"{work.issue_reference} ({work.issue_id}) remains at "
                    f"{target.path} and cannot be reassigned there. Resume the "
                    "same Agent Session at the intended Worktree"
                ),
                code="work-relocation-mismatched",
            )
    return Diagnostic(
        source=work.run_id,
        severity="warning",
        message=(
            f"{work.session_label} has a pending relocation of Issue work on "
            f"{work.issue_reference} ({work.issue_id}) from {target.path} to "
            f"{work.relocation.target_worktree}; resume that Agent Session at "
            "the intended Worktree, or if the relocation was abandoned run "
            f"'dashpot work stop --session {work.session_key}' at {target.path}"
        ),
        code="work-relocation-pending",
    )


def run_identities(
    work: ActiveWork, process_key: ProcessKey | None
) -> set[tuple[str, ...]]:
    """Every identity one Work Store run is known by across its routes.

    One session may be recorded by its process at one Worktree and by its
    Agent Session Identity at another (the sandboxed route), so a run is
    known by every identity it carries.
    """
    identities: set[tuple[str, ...]] = set()
    if process_key is not None:
        identities.add(("process", str(process_key[0]), process_key[1]))
    if work.session_id is not None:
        identities.add(("session", work.harness, work.session_id))
    return identities


def conflicting_run_diagnostic(work: ActiveWork) -> Diagnostic:
    """Report one session's Issue work recorded at more than one Worktree."""
    return Diagnostic(
        source=work.run_id,
        severity="warning",
        message=f"{work.session_label} has Issue work recorded "
        f"at more than one Worktree; each recorded run "
        f"is listed",
        code="work-session-conflict",
    )


def work_to_run(
    work: ActiveWork,
    target: ObservationTarget,
    project_id: str,
    observed: ObservedActivity,
) -> AgentRun:
    """Bind one active Work Store record to what the hooks saw it doing."""
    return AgentRun(
        id=work.run_id,
        harness=work.harness,
        process_or_session=work.session_label,
        state=observed.state,
        observation_target=target.path,
        observation_project_id=project_id,
        branch=work.branch or target.branch,
        issue_id=work.issue_id,
        issue_reference_hint=work.issue_reference,
        working_directory=work.working_directory,
        last_activity_at=observed.last_activity_at,
        turn_started_at=observed.turn_started_at,
        started_at=work.started_at,
    )


def observe_hook_sessions(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None,
    probe: LivenessProbe,
) -> tuple[list[HookSessionObservation], list[Diagnostic]]:
    """Read every visible hook store into live and unknown Agent Sessions.

    Ended and gone records are stale observation state: they are pruned and
    never reported here. Pruning is the only write observation performs, and
    it is conditional so a concurrently updated record survives.
    """
    directories: list[Path] = [directory or state_directory()]
    for _project_id, target in available_targets(targets_by_project):
        directories.append(session_directory(Path(target.path)))
    # A session's record may exist both globally and Project-locally around
    # an integration upgrade; the freshest observation per session wins.
    latest: dict[str, HookSessionObservation] = {}
    diagnostics: list[Diagnostic] = []

    def report_unreadable(path: Path, exc: Exception) -> None:
        diagnostics.append(
            Diagnostic(
                source=SESSION_DIAGNOSTIC_SOURCE,
                severity="warning",
                message=f"Cannot read {path}: {exc}",
            )
        )

    seen_directories: set[Path] = set()
    for candidate in directories:
        root = candidate.resolve()
        if root in seen_directories or not root.exists():
            continue
        seen_directories.add(root)
        store = HookRecordStore(root)
        for scanned in scan_hook_stores([root], probe, on_unreadable=report_unreadable):
            record = scanned.record
            if record.outcome in {"ended", "gone"}:
                # A gone session's Issue work, if any, is reported by the
                # Work Store pass; cleanup failures are not observations.
                with contextlib.suppress(OSError):
                    store.prune(record.session_id, scanned.raw)
                continue
            diagnostics.extend(
                Diagnostic(
                    source=SESSION_DIAGNOSTIC_SOURCE,
                    severity="warning",
                    message=f"Reading the hook record for {record.display} session "
                    f"{record.session_id} without its malformed field: {detail}",
                    code="agent-session-record-degraded",
                )
                for detail in record.degraded
            )
            session, record_diagnostics = record_to_session(record, targets_by_project)
            diagnostics.extend(record_diagnostics)
            if session is None:
                continue
            previous = latest.get(session.run.id)
            if previous is None or observed_instant(
                session.run.last_activity_at
            ) >= observed_instant(previous.run.last_activity_at):
                latest[session.run.id] = session
        # Records pruned above, or ended gracefully, leave their lock files
        # behind; reclaim those that guard nothing, and the temporary files a
        # crashed writer never renamed into place.
        for session_id in store.orphaned_locks():
            with contextlib.suppress(OSError):
                store.prune_lock(session_id)
        with contextlib.suppress(OSError):
            store.sweep_temporaries()
    unknown_by_reason: dict[str, int] = {}
    for session in latest.values():
        if session.liveness.liveness == "unknown":
            reason = session.liveness.reason or "host process identity is unavailable"
            unknown_by_reason[reason] = unknown_by_reason.get(reason, 0) + 1
    diagnostics.extend(
        Diagnostic(
            source=SESSION_DIAGNOSTIC_SOURCE,
            severity="info",
            message=f"Liveness of {count} Agent Session(s) is unknown: {reason}",
            code="agent-session-liveness-unknown",
        )
        for reason, count in sorted(unknown_by_reason.items())
    )
    return list(latest.values()), diagnostics


def record_to_session(
    record: HookRecordClassification,
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[HookSessionObservation | None, list[Diagnostic]]:
    """Place a live or unknown Agent Session at its Observation Target."""
    diagnostics: list[Diagnostic] = []
    # The Work Store is the sole Issue-association authority; a global hook
    # record carrying a binding is rejected rather than silently combined.
    if record.has_global_binding:
        diagnostics.append(
            Diagnostic(
                source=record.run_id,
                severity="warning",
                message=f"Rejecting the global Issue binding recorded for "
                f"{record.display} session {record.session_id}: bindings are "
                f"Project-local now; run 'dashpot work start' from the "
                f"session instead",
                code="agent-global-binding-rejected",
            )
        )
    located, target_diagnostic = locate_observation_target(record, targets_by_project)
    if target_diagnostic:
        diagnostics.append(target_diagnostic)
        return None, diagnostics
    if located is None:
        return None, diagnostics
    observation_project_id, target = located
    state: RunState = (
        cast(RunState, record.state) if record.outcome == "live" else "unknown"
    )
    return (
        HookSessionObservation(
            AgentRun(
                id=record.run_id,
                harness=record.harness,
                process_or_session=f"{record.session_id} hook",
                state=state,
                observation_target=target.path,
                observation_project_id=observation_project_id,
                branch=record.branch or target.branch,
                issue_id=None,
                issue_reference_hint=None,
                working_directory=record.cwd,
                last_activity_at=record.last_activity_at,
                turn_started_at=record.turn_started_at,
            ),
            record.process_key,
            LivenessObservation(
                "live" if record.outcome == "live" else "unknown", record.reason
            ),
            record.session_id,
        ),
        diagnostics,
    )


def locate_observation_target(
    record: HookRecordClassification,
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[tuple[str, ObservationTarget] | None, Diagnostic | None]:
    """Match a classified hook record to one available Observation Target."""
    available = [
        (project_id, target)
        for project_id, targets in targets_by_project.items()
        for target in targets
        if target.availability == "available"
    ]
    cwd_path = Path(record.cwd).resolve()
    cwd_matches = [
        (project_id, target)
        for project_id, target in available
        if is_within(cwd_path, Path(target.path).resolve())
    ]
    cwd_target = max(cwd_matches, key=lambda item: len(item[1].path), default=None)
    if not record.repository_root:
        return cwd_target, None
    root_path = Path(record.repository_root).resolve()
    root_target = next(
        (
            (project_id, target)
            for project_id, target in available
            if Path(target.path).resolve() == root_path
        ),
        None,
    )
    if root_target is None:
        return None, None
    if cwd_target is None or cwd_target[1].path != root_target[1].path:
        return None, Diagnostic(
            source=SESSION_DIAGNOSTIC_SOURCE,
            severity="warning",
            message=f"Ignoring {record.display} session {record.session_id}: "
            "recorded Repository root "
            "and working directory resolve to different Observation Targets",
            code="agent-target-mismatch",
        )
    return root_target, None
