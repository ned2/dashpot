"""Observe Agent Runs and Agent Sessions across Work Stores and hook stores."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.model import AgentRun, Diagnostic, Harness, ObservationTarget, RunState
from ..core.timestamps import observed_instant
from ..core.worktree_paths import is_within, same_path
from .hook_records import HookRecordStore
from .hook_scan import (
    HookRecordClassification,
    reachable_hook_stores,
    scan_hook_stores,
    session_record_named,
)
from .liveness import LivenessObservation, LivenessProbe
from .processes import (
    ProcessKey,
    ProcessLookup,
    host_boot_time,
    host_process_lookup,
    process_started_at,
)
from .session_matching import SessionEvidence
from .work_store import ActiveWork, SessionProcess, WorkStore

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
BootTime = Callable[[], datetime | None]


@dataclass(frozen=True, slots=True)
class GoneHookRecord:
    """A gone session's hook record, kept while an Orphaned Agent Run needs it."""

    store: HookRecordStore
    name: str
    raw: Mapping[str, Any]
    record: HookRecordClassification


@dataclass(slots=True)
class LastSeenIndex:
    """When each gone session was last seen, for its Orphaned Agent Run.

    A gone session's hook record is the only evidence of when it was last
    active, so observation keeps it while an Orphaned Agent Run of the same
    Agent Session Identity and process claims it, and prunes the rest.
    """

    records: Sequence[GoneHookRecord]
    _claimed: set[int] = field(default_factory=set)

    def claim(self, work: ActiveWork) -> str | None:
        """The last activity of the gone session that recorded this run."""
        evidence = work.evidence
        seen: str | None = None
        for index, gone in enumerate(self.records):
            if (
                evidence.native_key is None
                or gone.record.evidence.native_key != evidence.native_key
                or gone.record.process_key != evidence.process_key
            ):
                continue
            self._claimed.add(index)
            activity = gone.record.last_activity_at
            if observed_instant(activity) >= observed_instant(seen):
                seen = activity
        return seen

    def prune_unclaimed(self, observed: frozenset[Path]) -> None:
        """Remove every gone record no Orphaned Agent Run still needs.

        A record at a Worktree this pass did not observe is kept only while
        that Worktree's Work Store holds an active run of the same session,
        which an observation of it would claim; the records of unconfigured
        checkouts and removed Worktrees have no such run and are pruned.
        """
        pruned: dict[Path, HookRecordStore] = {}
        for index, gone in enumerate(self.records):
            if index in self._claimed:
                continue
            root = gone.raw.get("repositoryRoot")
            if (
                isinstance(root, str)
                and Path(root) not in observed
                and holds_run_of(Path(root), gone.record)
            ):
                continue
            # Cleanup failures are not observations.
            with contextlib.suppress(OSError):
                gone.store.prune(gone.name, gone.raw)
            pruned[gone.store.directory] = gone.store
        # Pruning leaves each record's lock file behind; reclaim those now
        # rather than on the next pass.
        for store in pruned.values():
            store.sweep()


def holds_run_of(root: Path, record: HookRecordClassification) -> bool:
    """Whether the Work Store at ``root`` holds an active run of this session."""
    native_key = record.evidence.native_key
    store = WorkStore(root)
    try:
        if not store.directory.is_dir():
            return False
        active, _diagnostics = store.active()
    except OSError:
        # An unreadable Work Store may still hold the run; keep its evidence.
        return True
    return native_key is not None and any(
        work.evidence.native_key == native_key for work in active
    )


def observe_agent_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
    boot_time: BootTime = host_boot_time,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Observe Work Store Agent Runs and unmatched hook Agent Sessions.

    This is the only place Session Liveness becomes an outcome. A gone
    session with an Issue Binding is an Orphaned Agent Run and stays listed,
    marked orphaned, until its session continues it or a person ends it; a
    gone unbound session is stale observation state and is dropped silently.
    """
    probe = LivenessProbe(lookup)
    sessions, gone, diagnostics = observe_hook_sessions(
        targets_by_project, directory, probe
    )
    activity = ObservedActivityIndex(sessions)
    last_seen = LastSeenIndex(gone)
    work_runs, work_diagnostics = observe_work_runs(
        targets_by_project,
        probe,
        activity,
        directory,
        last_seen=last_seen,
        boot_time=boot_time,
    )
    last_seen.prune_unclaimed(
        frozenset(
            Path(target.path)
            for targets in targets_by_project.values()
            for target in targets
            if target.availability == "available"
        )
    )
    diagnostics.extend(work_diagnostics)
    diagnostics.extend(activity.diagnostics)
    runs = list(work_runs)
    runs.extend(session.run for session in sessions if not activity.consumed(session))
    return runs, diagnostics


class ObservedActivityIndex:
    """Join Agent Runs to their own native identity's hook activity."""

    def __init__(self, sessions: Sequence[HookSessionObservation]) -> None:
        self._by_session: dict[SessionIdentityKey, HookSessionObservation] = {}
        for session in sessions:
            self._by_session[session.run.harness, session.session_id] = session
        self._consumed: set[SessionIdentityKey] = set()
        self.diagnostics: list[Diagnostic] = []

    def adopt(
        self,
        harness: Harness,
        session_id: str | None,
        process_key: ProcessKey | None,
    ) -> ObservedActivity | None:
        session = None
        identity = SessionEvidence(harness, session_id, process_key)
        if identity.native_key is not None:
            session = self._by_session.get(identity.native_key)
        if (
            session is not None
            and process_key is not None
            and (session.process_key is not None and session.process_key != process_key)
        ):
            return None
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
    directory: Path | None,
    *,
    last_seen: LastSeenIndex | None = None,
    boot_time: BootTime = host_boot_time,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Turn each Worktree's active Work Store records into bound Agent Runs."""
    seen = last_seen if last_seen is not None else LastSeenIndex(())
    runs: list[AgentRun] = []
    diagnostics: list[Diagnostic] = []
    sessions_seen: set[tuple[str, ...]] = set()
    for project_id, target in available_targets(targets_by_project):
        store = WorkStore(Path(target.path))
        active, store_diagnostics = store.active()
        diagnostics.extend(store_diagnostics)
        store.sweep()
        for work in active:
            process_key = work.evidence.process_key
            if work.session_id is None:
                diagnostics.append(
                    Diagnostic(
                        source=work.run_id,
                        severity="warning",
                        code="work-session-unresolved",
                        message=f"Agent Run {work.session_key} has no confirmed Agent Session "
                        "Identity; process evidence cannot establish ownership. After its "
                        "recorded process is proved gone, run "
                        f"'dashpot work stop --session {work.session_key}' at {target.path}",
                    )
                )
            # The gone process, when this run is an Orphaned Agent Run.
            gone = (
                work.session_process
                if work.relocation is None
                and work.session_process is not None
                and probe.observe(work.session_process.key).liveness == "gone"
                else None
            )
            identities = run_identities(work)
            if identities & sessions_seen:
                diagnostics.append(conflicting_run_diagnostic(work))
            sessions_seen |= identities
            if gone is not None:
                # Nothing is running this session, so no live hook activity
                # is its; the gone record says when it was last seen.
                observed = ObservedActivity("unknown", seen.claim(work), None)
            else:
                observed = activity.adopt(work.harness, work.session_id, process_key)
            if observed is None:
                # No hook has ever reported this run; the Work Store knows
                # when the work began and nothing about what it has done.
                observed = ObservedActivity("unknown", None, None)
            run = work_to_run(work, target, project_id, observed)
            if gone is not None:
                run = run.model_copy(
                    update={
                        "orphaned": True,
                        "host_restarted": host_restarted_since(gone, boot_time),
                    }
                )
            runs.append(run)
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


def host_restarted_since(process: SessionProcess, boot_time: BootTime) -> bool | None:
    """Whether the host booted after a run's recorded process started.

    A restart since the process started is compatible with the process having
    exited earlier for another reason, so this dates the boot, not the cause.
    """
    started = process_started_at(process.started_at)
    booted = boot_time()
    if started is None or booted is None:
        return None
    return booted > started


def relocation_diagnostic(
    work: ActiveWork,
    target: ObservationTarget,
    project_targets: Sequence[ObservationTarget],
    directory: Path | None,
    probe: LivenessProbe,
) -> Diagnostic:
    """Report why a declared relocation has not completed yet."""
    assert work.relocation is not None
    stores = reachable_hook_stores(
        [Path(item.path) for item in project_targets], directory
    )
    locations: set[Path] = set()
    if work.session_id is not None:
        for scanned in scan_hook_stores(
            stores,
            probe,
            select=lambda path: session_record_named(
                path, work.session_id or "", work.harness
            ),
        ):
            if (
                scanned.record.harness == work.harness
                and scanned.record.outcome not in {"ended", "gone"}
            ):
                try:
                    locations.add(scanned.record.worktree.resolve())
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


def run_identities(work: ActiveWork) -> set[tuple[str, ...]]:
    """Identify a named run for harness-scoped conflict detection."""
    identity = work.evidence
    if identity.native_key is None:
        return set()
    return {("session", *identity.native_key)}


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
        session_id=work.session_id,
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
) -> tuple[list[HookSessionObservation], list[GoneHookRecord], list[Diagnostic]]:
    """Read every visible hook store into live and unknown Agent Sessions.

    Ended records are stale observation state and are pruned here. Gone
    records are never reported as sessions either, but are returned for the
    Work Store pass, which keeps those an Orphaned Agent Run still needs and
    prunes the rest. Pruning is the only write observation performs, and it
    is conditional so a concurrently updated record survives.
    """
    stores = reachable_hook_stores(
        [
            Path(target.path)
            for _project_id, target in available_targets(targets_by_project)
        ],
        directory,
    )
    # A session's record may exist both globally and Project-locally around
    # an integration upgrade; the freshest observation per session wins.
    latest: dict[str, HookSessionObservation] = {}
    gone: list[GoneHookRecord] = []
    diagnostics: list[Diagnostic] = []

    def report_unreadable(path: Path, exc: Exception) -> None:
        diagnostics.append(
            Diagnostic(
                source=SESSION_DIAGNOSTIC_SOURCE,
                severity="warning",
                message=f"Cannot read {path}: {exc}",
            )
        )

    for candidate in stores:
        root = candidate.resolve()
        if not root.exists():
            continue
        store = HookRecordStore(root)
        for scanned in scan_hook_stores([root], probe, on_unreadable=report_unreadable):
            record = scanned.record
            if record.outcome == "gone":
                gone.append(
                    GoneHookRecord(store, scanned.path.stem, scanned.raw, record)
                )
                continue
            if record.outcome == "ended":
                # Cleanup failures are not observations.
                with contextlib.suppress(OSError):
                    store.prune(scanned.path.stem, scanned.raw)
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
        # behind; reclaim those, and a crashed writer's temporaries.
        store.sweep()
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
    return list(latest.values()), gone, diagnostics


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
    # A live record's state is running or waiting; ``ended`` is what a graceful
    # SessionEnd leaves and is only ever seen with the ``ended`` outcome.
    recorded = record.state
    state: RunState = (
        recorded if record.outcome == "live" and recorded != "ended" else "unknown"
    )
    return (
        HookSessionObservation(
            AgentRun(
                id=record.run_id,
                harness=record.harness,
                process_or_session=f"{record.session_id} hook",
                session_id=record.session_id,
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
            if same_path(Path(target.path), root_path)
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
