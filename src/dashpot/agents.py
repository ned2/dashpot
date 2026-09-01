"""Observe Agent Runs and Agent Sessions across Work Stores and hook stores."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .harnesses import HARNESS_DISPLAY as HARNESS_DISPLAY
from .hook_records import EVENT_STATES as EVENT_STATES
from .hook_records import HookRecordClassification as HookRecordClassification
from .hook_records import HookRecordOutcome as HookRecordOutcome
from .hook_records import HookRecordStore as HookRecordStore
from .hook_records import ScannedRecord as ScannedRecord
from .hook_records import SessionLocation as SessionLocation
from .hook_records import SessionRecordSummary as SessionRecordSummary
from .hook_records import StaleSessionRecord as StaleSessionRecord
from .hook_records import ValidatedSessionIdentity as ValidatedSessionIdentity
from .hook_records import build_hook_record as build_hook_record
from .hook_records import classify_hook_record as classify_hook_record
from .hook_records import locate_agent_session as locate_agent_session
from .hook_records import now_iso as now_iso
from .hook_records import observed_instant as observed_instant
from .hook_records import publish_hook_event as publish_hook_event
from .hook_records import reachable_hook_stores as reachable_hook_stores
from .hook_records import read_hook_record as read_hook_record
from .hook_records import route_record_directory as route_record_directory
from .hook_records import scan_hook_stores as scan_hook_stores
from .hook_records import session_directory as session_directory
from .hook_records import sessions_at_worktree as sessions_at_worktree
from .hook_records import state_directory as state_directory
from .hook_records import summarize_session_records as summarize_session_records
from .hook_records import turn_started_at as turn_started_at
from .hook_records import validate_session_claim as validate_session_claim
from .hook_records import write_hook_record as write_hook_record
from .json_records import optional_string
from .liveness import LivenessObservation as LivenessObservation
from .liveness import LivenessProbe as LivenessProbe
from .liveness import SessionLiveness as SessionLiveness
from .liveness import session_liveness as session_liveness
from .model import AgentRun, Diagnostic, ObservationTarget, RunState
from .processes import CONTAINER_CGROUP_TOKENS as CONTAINER_CGROUP_TOKENS
from .processes import CONTAINER_MARKERS as CONTAINER_MARKERS
from .processes import HARNESS_HOSTS as HARNESS_HOSTS
from .processes import ISOLATING_INITS as ISOLATING_INITS
from .processes import AgentAncestry as AgentAncestry
from .processes import ProcessAbsent as ProcessAbsent
from .processes import ProcessIdentity as ProcessIdentity
from .processes import ProcessKey as ProcessKey
from .processes import ProcessLookup as ProcessLookup
from .processes import ProcessObservation as ProcessObservation
from .processes import ProcessPresent as ProcessPresent
from .processes import ProcessUnobservable as ProcessUnobservable
from .processes import host_process_lookup as host_process_lookup
from .processes import lock_holder_probe as lock_holder_probe
from .processes import namespace_is_isolated as namespace_is_isolated
from .processes import nearest_agent_process as nearest_agent_process
from .processes import nearest_codex_process as nearest_codex_process
from .processes import nearest_harness_process as nearest_harness_process
from .processes import observe_agent_ancestry as observe_agent_ancestry
from .processes import process_identity_of as process_identity_of
from .processes import process_key_of as process_key_of
from .processes import process_namespace_is_isolated as process_namespace_is_isolated
from .repository import is_within
from .work_store import WorkStore

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
    work_runs, work_diagnostics = observe_work_runs(targets_by_project, probe, activity)
    diagnostics.extend(work_diagnostics)
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
        self._by_process: dict[ProcessKey, HookSessionObservation] = {}
        for session in sessions:
            self._by_session[session.run.harness, session.session_id] = session
            if session.process_key is not None:
                self._by_process[session.process_key] = session
        self._consumed: set[SessionIdentityKey] = set()

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
            session = self._by_process.get(process_key)
        if session is None:
            return None
        self._consumed.add((session.run.harness, session.session_id))
        return ObservedActivity(
            session.run.state,
            session.run.last_activity_at,
            session.run.turn_started_at,
        )

    def consumed(self, session: HookSessionObservation) -> bool:
        return (session.run.harness, session.session_id) in self._consumed


def observe_work_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    probe: LivenessProbe,
    activity: ObservedActivityIndex,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Turn each Worktree's active Work Store records into bound Agent Runs."""
    runs: list[AgentRun] = []
    diagnostics: list[Diagnostic] = []
    sessions_seen: set[tuple[str, ...]] = set()
    for project_id, targets in sorted(targets_by_project.items()):
        for target in targets:
            if target.availability != "available":
                continue
            store = WorkStore(Path(target.path))
            active, store_diagnostics = store.active()
            diagnostics.extend(store_diagnostics)
            # Runs stopped before their lock files were reclaimed leave
            # orphaned locks behind; sweep those that guard nothing, and the
            # temporary files a crashed writer never renamed into place.
            for session_key in store.orphaned_locks():
                with contextlib.suppress(OSError):
                    store.prune_lock(session_key)
            with contextlib.suppress(OSError):
                store.sweep_temporaries()
            for work in active:
                process_key: ProcessKey | None = None
                if work.session_process is not None:
                    process_key = (
                        work.session_process.pid,
                        work.session_process.started_at,
                    )
                    liveness = probe.observe(work.session_process.as_record())
                    if liveness.liveness == "gone":
                        diagnostics.append(
                            Diagnostic(
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
                        )
                        continue
                # One session may be recorded by its process at one Worktree
                # and by its Agent Session Identity at another (the sandboxed
                # route), so a run is known by every identity it carries.
                identities: set[tuple[str, ...]] = set()
                if process_key is not None:
                    identities.add(("process", str(process_key[0]), process_key[1]))
                if work.session_id is not None:
                    identities.add(("session", work.harness, work.session_id))
                if identities & sessions_seen:
                    diagnostics.append(
                        Diagnostic(
                            source=work.run_id,
                            severity="warning",
                            message=f"{work.session_label} has Issue work recorded "
                            f"at more than one Worktree; each recorded run "
                            f"is listed",
                            code="work-session-conflict",
                        )
                    )
                sessions_seen |= identities
                observed = activity.adopt(work.harness, work.session_id, process_key)
                if observed is None:
                    # No hook has ever reported this run; the Work Store knows
                    # when the work began and nothing about what it has done.
                    observed = ObservedActivity("unknown", None, None)
                runs.append(
                    AgentRun(
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
                )
    return runs, diagnostics


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
    for _project_id, targets in sorted(targets_by_project.items()):
        for target in targets:
            if target.availability == "available":
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
            session, record_diagnostics = record_to_session(
                record, scanned.raw, targets_by_project
            )
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
    raw: Mapping[str, Any],
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[HookSessionObservation | None, list[Diagnostic]]:
    """Place a live or unknown Agent Session at its Observation Target."""
    diagnostics: list[Diagnostic] = []
    # The Work Store is the sole Issue-association authority; a global hook
    # record carrying a binding is rejected rather than silently combined.
    if raw.get("issueId") is not None or raw.get("issueReferenceHint") is not None:
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
    located, target_diagnostic = locate_observation_target(
        raw, record.cwd, targets_by_project
    )
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
    raw: Mapping[str, Any],
    cwd: str,
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[tuple[str, ObservationTarget] | None, Diagnostic | None]:
    available = [
        (project_id, target)
        for project_id, targets in targets_by_project.items()
        for target in targets
        if target.availability == "available"
    ]
    cwd_path = Path(cwd).resolve()
    cwd_matches = [
        (project_id, target)
        for project_id, target in available
        if is_within(cwd_path, Path(target.path).resolve())
    ]
    cwd_target = max(cwd_matches, key=lambda item: len(item[1].path), default=None)
    repository_root = optional_string(raw.get("repositoryRoot"))
    if not repository_root:
        return cwd_target, None
    root_path = Path(repository_root).resolve()
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
        session_id = optional_string(raw.get("sessionId")) or "unknown"
        display = HARNESS_DISPLAY.get(
            optional_string(raw.get("harness")) or "codex", "agent"
        )
        return None, Diagnostic(
            source=SESSION_DIAGNOSTIC_SOURCE,
            severity="warning",
            message=f"Ignoring {display} session {session_id}: recorded Repository root "
            "and working directory resolve to different Observation Targets",
            code="agent-target-mismatch",
        )
    return root_target, None
