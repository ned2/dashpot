"""Classify and scan hook Agent Session records."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from ..core.model import HARNESS_DISPLAY, Harness
from ..core.pydantic import describe_validation_error, validate_degrading
from ..core.timestamps import observed_instant
from ..core.worktree_paths import same_path
from .hook_records import (
    HOOK_RECORD_FATAL,
    HOOK_RECORD_VERSION,
    ActiveState,
    HookRecord,
    session_directory,
    state_directory,
)
from .liveness import (
    LivenessObservation,
    LivenessProbe,
    SessionLiveness,
)
from .processes import (
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
)
from .session_matching import SessionEvidence

# A hook record's outcome is its Session Liveness, plus the one fact liveness
# cannot express: a graceful SessionEnd, which is a record state, not a probe.
HookRecordOutcome = SessionLiveness | Literal["ended"]


@dataclass(frozen=True, slots=True)
class HookRecordClassification:
    """One validated hook Agent Session record and its reconciled outcome."""

    session_id: str
    harness: Harness
    state: ActiveState
    cwd: str
    repository_root: str | None
    branch: str | None
    event: str | None
    last_activity_at: str | None
    turn_started_at: str | None
    process: ProcessIdentity | None
    outcome: HookRecordOutcome
    reason: str | None = None
    # Malformed non-fatal fields the record was read without, by wire path.
    degraded: tuple[str, ...] = ()
    has_global_binding: bool = False
    # The ``agent_id`` of each sub-agent the store holds started and not yet
    # stopped (ADR 0016), from Claude Code or Codex (ADR 0067).
    live_subagents: tuple[str, ...] = ()
    # Whether an ended record still holds sub-agents its session left
    # working: it lists some and its Host Process is not proved gone (ADR
    # 0095). The session is over; those sub-agents may not be.
    retains_subagents: bool = False

    @property
    def process_key(self) -> ProcessKey | None:
        return self.process.key if self.process else None

    @property
    def evidence(self) -> SessionEvidence:
        """The session facts this record was published under, for matching."""
        return SessionEvidence(self.harness, self.session_id, self.process_key)

    @property
    def worktree(self) -> Path:
        """The Worktree the harness last published from: its root, else its cwd."""
        return Path(self.repository_root or self.cwd)

    @property
    def display(self) -> str:
        return HARNESS_DISPLAY[self.harness]

    @property
    def run_id(self) -> str:
        return f"{self.harness}-session:{self.session_id}"


@dataclass(frozen=True, slots=True)
class StaleSessionRecord:
    """A hook record whose Agent Session is over: gone, or ended gracefully."""

    session_id: str
    harness: Harness
    event: str | None
    last_activity_at: str | None
    pid: int | None
    outcome: Literal["gone", "ended"]
    # The sub-agents an ended record still holds, which keep it (ADR 0095).
    retained_subagents: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionRecordSummary:
    """Point-in-time classification of every hook record in one store."""

    directory: Path
    live: int
    unknown: int
    unknown_reasons: tuple[tuple[str, int], ...]
    stale: tuple[StaleSessionRecord, ...]
    unreadable: int

    @property
    def total(self) -> int:
        return self.live + self.unknown + len(self.stale) + self.unreadable


@dataclass(frozen=True, slots=True)
class SessionLocation:
    """Where an Agent Session's freshest hook record places it.

    The record's ``repositoryRoot`` (else its ``cwd``) is the Worktree the
    harness itself last published from, which is the session's current
    location whatever directory a command inside it runs in.
    """

    record: HookRecordClassification
    store: Path

    @property
    def worktree(self) -> Path:
        return self.record.worktree

    @property
    def process(self) -> ProcessIdentity | None:
        return self.record.process


def reachable_hook_stores(
    worktrees: Sequence[Path], directory: Path | None = None
) -> list[Path]:
    """The hook stores a Repository's sessions publish to, plus the global one.

    A session at a Worktree whose checkout predates ``.dashpot/config.json``
    publishes to the global store, so that store is always reachable too.
    """
    stores: list[Path] = []
    seen: set[Path] = set()
    candidates = [session_directory(worktree) for worktree in worktrees]
    candidates.append(directory or state_directory())
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        stores.append(candidate)
    return stores


def read_hook_record(path: Path) -> dict[str, Any]:
    """Load one version-2 hook record, raising ``ValueError`` otherwise."""
    raw: Any = json.loads(path.read_text())
    if not isinstance(raw, dict) or raw.get("version") != HOOK_RECORD_VERSION:
        raise ValueError("unsupported record shape or version")
    return raw


def classify_hook_record(
    raw: Mapping[str, Any],
    probe: LivenessProbe,
    expected_session_id: str | None = None,
) -> HookRecordClassification:
    """Validate one hook record and derive its lifecycle outcome.

    Independent of Observation Targets, so integration status can classify a
    store's records without an observation scope. Raises ``ValueError`` for
    records Dashpot cannot interpret: a fatal field is malformed, or the
    record is not the session its filename names.
    """
    record, degraded = _validated_hook_record(raw, expected_session_id)
    return _classify_validated_record(record, degraded, probe)


def _validated_hook_record(
    raw: Mapping[str, Any], expected_session_id: str | None
) -> tuple[HookRecord, tuple[str, ...]]:
    """Validate the record and its filename before any process is probed."""
    try:
        record, degraded = validate_degrading(HookRecord, raw, fatal=HOOK_RECORD_FATAL)
    except ValidationError as exc:
        raise ValueError(describe_validation_error(exc)) from exc
    if expected_session_id is not None and expected_session_id not in {
        record.session_id,
        SessionEvidence(record.harness, record.session_id).storage_key(),
    }:
        raise ValueError("record sessionId does not match its filename")
    return record, degraded


def _classify_validated_record(
    record: HookRecord, degraded: tuple[str, ...], probe: LivenessProbe
) -> HookRecordClassification:
    """Derive one validated record's outcome from the pass's process evidence."""
    process = record.session_process.identity if record.session_process else None
    retains_subagents = False
    if record.state == "ended":
        liveness = LivenessObservation("unknown")
        outcome: HookRecordOutcome = "ended"
        retains_subagents = (
            bool(record.live_subagents)
            and process is not None
            and probe.observe(process.key).liveness != "gone"
        )
    else:
        liveness = probe.observe(process.key if process else None)
        if (
            liveness.liveness == "live"
            and record.session_process_unobservable is not None
        ):
            # The record names its Host Process yet says nothing observes the
            # session there (an OpenCode server with no live plugin instance,
            # ADR 0090): a live process vouches for nothing, while a gone one
            # still ends it.
            liveness = LivenessObservation(
                "unknown", record.session_process_unobservable
            )
        outcome = liveness.liveness
    return HookRecordClassification(
        session_id=record.session_id,
        harness=record.harness,
        state=record.state,
        cwd=record.cwd,
        repository_root=record.repository_root,
        branch=record.branch,
        event=record.event,
        last_activity_at=record.last_activity_at,
        turn_started_at=record.turn_started_at,
        process=process,
        outcome=outcome,
        reason=liveness.reason,
        degraded=degraded,
        has_global_binding=record.has_global_binding,
        live_subagents=tuple(record.live_subagents),
        retains_subagents=retains_subagents,
    )


@dataclass(frozen=True, slots=True)
class ScannedRecord:
    """One readable hook record a store scan classified, with where it lives."""

    store: Path
    path: Path
    raw: dict[str, Any]
    record: HookRecordClassification


@dataclass(frozen=True, slots=True)
class _PendingRecord:
    """One validated record awaiting the scan's batched liveness evidence."""

    store: Path
    path: Path
    raw: dict[str, Any]
    record: HookRecord
    degraded: tuple[str, ...]


def scan_hook_stores(
    stores: Iterable[Path],
    probe: LivenessProbe,
    *,
    select: Callable[[Path], bool] | None = None,
    on_unreadable: Callable[[Path, Exception], None] | None = None,
) -> Iterator[ScannedRecord]:
    """Classify every selected hook record, store by store, records in path order.

    The one scan every observer shares: what varies per caller is which paths
    are worth reading (``select``), what an unreadable record means to it
    (``on_unreadable``, which may raise to abort the scan; the default treats
    the record as no evidence and skips it), and how the yielded records fold.
    The hook publisher, which must not probe processes while it holds the
    session's locks, reads one identity's records with
    ``stored_session_records`` instead.
    """
    readable: list[_PendingRecord] = []
    keys: list[ProcessKey] = []
    for store in stores:
        if not store.is_dir():
            continue
        for path in sorted(store.glob("*.json")):
            if select is not None and not select(path):
                continue
            try:
                raw = read_hook_record(path)
                validated, degraded = _validated_hook_record(raw, path.stem)
            except (OSError, ValueError) as exc:
                if on_unreadable is not None:
                    on_unreadable(path, exc)
                continue
            readable.append(_PendingRecord(store, path, raw, validated, degraded))
            if validated.session_process is not None and (
                validated.state != "ended" or validated.live_subagents
            ):
                keys.append(validated.session_process.identity.key)
    probe.prepare(keys)
    for pending in readable:
        record = _classify_validated_record(pending.record, pending.degraded, probe)
        yield ScannedRecord(pending.store, pending.path, pending.raw, record)


def session_record_stems(
    session_id: str, harness: Harness | None = None
) -> tuple[str, ...]:
    """The legacy and harness-scoped filename stems a session's hook record may have."""
    harnesses = (harness,) if harness is not None else tuple(HARNESS_DISPLAY)
    return (
        session_id,
        *(
            SessionEvidence(candidate, session_id).storage_key()
            for candidate in harnesses
        ),
    )


def session_record_named(
    path: Path, session_id: str, harness: Harness | None = None
) -> bool:
    """Select legacy and harness-scoped filenames for full record validation."""
    return path.stem in session_record_stems(session_id, harness)


@dataclass(frozen=True, slots=True)
class StoredSessionRecord:
    """One hook record of a named Agent Session, read without probing its process.

    The hook publisher reads these under its own locks to route and reconcile
    one event, where a process probe per record would cost the harness time
    and add nothing the event's own process does not already say.
    """

    store: Path
    path: Path
    raw: dict[str, Any]
    record: HookRecord

    @property
    def worktree(self) -> Path:
        """The Worktree the record places its session at: its root, else its cwd."""
        return Path(self.record.repository_root or self.record.cwd)

    @property
    def process_key(self) -> ProcessKey | None:
        process = self.record.session_process
        return None if process is None else (process.pid, process.started_at)

    @property
    def last_activity(self) -> datetime:
        return observed_instant(self.record.last_activity_at)


def stored_session_records(
    stores: Iterable[Path], harness: Harness, session_id: str
) -> tuple[list[StoredSessionRecord], int]:
    """Every readable record of one native identity across ``stores``, and how many were not.

    Only the identity's own filenames are read. A record that cannot be read
    or validated, or that names another identity, is counted rather than
    returned, so a caller that must not act on missing evidence can refuse.
    """
    found: list[StoredSessionRecord] = []
    unreadable = 0
    expected = (harness, session_id)
    for store in stores:
        for name in session_record_stems(session_id, harness):
            path = store / f"{name}.json"
            try:
                raw = read_hook_record(path)
                record, _degraded = validate_degrading(
                    HookRecord, raw, fatal=HOOK_RECORD_FATAL
                )
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                unreadable += 1
                continue
            # A legacy filename may hold another harness's session.
            if (record.harness, record.session_id) != expected:
                continue
            found.append(StoredSessionRecord(store, path, raw, record))
    return found, unreadable


def stored_process_records(
    stores: Iterable[Path], harness: Harness, process: ProcessKey
) -> list[StoredSessionRecord]:
    """Every readable record of ``harness`` that names the Host Process ``process``.

    The hook publisher reads these to move a Sub-agent listing between the
    sessions one Host Process holds, whose records share no filename: a
    Conversation Switch's new session takes over the sub-agents of the one
    it left, and a sub-agent's stop leaves every ended record of its process
    (ADR 0101) and every live record its session left behind (ADR 0102). Like ``stored_session_records`` it probes no process. A
    record that cannot be read or validated is no evidence and is skipped:
    a caller changes a record only through its store, which re-reads it under
    its own lock.
    """
    found: list[StoredSessionRecord] = []
    for store in stores:
        if not store.is_dir():
            continue
        for path in sorted(store.glob("*.json")):
            try:
                raw = read_hook_record(path)
                record, _degraded = _validated_hook_record(raw, path.stem)
            except (OSError, ValueError):
                continue
            stored = StoredSessionRecord(store, path, raw, record)
            if record.harness == harness and stored.process_key == process:
                found.append(stored)
    return found


def freshest_stored_record(
    records: Iterable[StoredSessionRecord],
) -> StoredSessionRecord | None:
    """The record stamped latest; of two stamped alike, the first read."""
    freshest: StoredSessionRecord | None = None
    for candidate in records:
        if freshest is None or candidate.last_activity > freshest.last_activity:
            freshest = candidate
    return freshest


def locate_agent_session(
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
    *,
    session_id: str | None = None,
    harness: Harness | None = None,
    process_key: ProcessKey | None = None,
) -> SessionLocation | None:
    """Place a scoped native identity by its freshest validated hook record."""
    if session_id is None and process_key is None:
        raise ValueError("a session is located by its identity or its process")

    def named(path: Path) -> bool:
        return session_id is not None and session_record_named(
            path, session_id, harness
        )

    def worth_reading(path: Path) -> bool:
        return named(path) if session_id is not None else process_key is not None

    def refuse_named(path: Path, exc: Exception) -> None:
        if named(path):
            raise ValueError(str(exc)) from exc

    probe = LivenessProbe(lookup)
    freshest: SessionLocation | None = None
    for scanned in scan_hook_stores(
        stores, probe, select=worth_reading, on_unreadable=refuse_named
    ):
        record = scanned.record
        if harness is not None and record.harness != harness:
            continue
        if session_id is not None:
            if (
                SessionEvidence(harness or record.harness, session_id).match(
                    record.evidence
                )
                != "same"
            ):
                continue
        elif record.process_key != process_key:
            continue
        if freshest is not None and (
            freshest.record.harness,
            freshest.record.session_id,
        ) != (record.harness, record.session_id):
            raise ValueError(
                "a process or unscoped identity names multiple Agent Sessions"
            )
        if freshest is None or observed_instant(
            scanned.record.last_activity_at
        ) > observed_instant(freshest.record.last_activity_at):
            freshest = SessionLocation(scanned.record, scanned.store)
    return freshest


SESSION_OVER: frozenset[HookRecordOutcome] = frozenset({"ended", "gone"})


def session_histories(
    stores: Sequence[Path], lookup: ProcessLookup
) -> list[list[SessionLocation]]:
    """Each Agent Session's readable records across ``stores``, freshest first.

    Each checkout keeps its own store, so a session that moved between
    Worktrees has a record in each; a record that cannot be read is not
    evidence and is skipped.
    """
    probe = LivenessProbe(lookup)
    grouped: dict[tuple[str, str], list[SessionLocation]] = {}
    for scanned in scan_hook_stores(stores, probe):
        identity = (scanned.record.harness, scanned.record.session_id)
        grouped.setdefault(identity, []).append(
            SessionLocation(scanned.record, scanned.store)
        )
    # The sort is stable: of two records stamped alike, the first read leads.
    return [
        sorted(
            history,
            key=lambda location: observed_instant(location.record.last_activity_at),
            reverse=True,
        )
        for _identity, history in sorted(grouped.items())
    ]


def _freshest_sessions(
    stores: Sequence[Path], lookup: ProcessLookup
) -> list[SessionLocation]:
    """Each live or unknown Agent Session placed by its freshest readable record.

    Ended and gone records describe sessions that are over and are not
    reported.
    """
    return [
        history[0]
        for history in session_histories(stores, lookup)
        if history[0].record.outcome not in SESSION_OVER
    ]


def sessions_at_worktree(
    worktree: Path,
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[SessionLocation]:
    """Every live or unknown Agent Session whose hooks last placed it at ``worktree``."""
    target = worktree.resolve()
    return [
        location
        for location in _freshest_sessions(stores, lookup)
        if same_path(location.worktree, target)
    ]


def sessions_with_live_subagents(
    worktrees: Sequence[Path],
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[SessionLocation]:
    """Every Agent Session in ``worktrees`` with a sub-agent listed as working.

    A sub-agent's hooks carry its session's location, never its own, so where
    it works is unknown: it may be in any Worktree of the Repository. A
    session that moved on from the Worktree it dispatched them from may
    list them only in the record it left there, as when its move named no
    Host Process to carry them by: every record of the session counts, and
    the location reported is the freshest one's. A sub-agent's stop clears
    it from each of those records (ADR 0102). A session is counted while it is
    live or unknown, and once it has ended while an ended record still holds
    the sub-agents it left working (ADR 0095); that record is the one
    reported when it is the freshest.
    """
    found: list[SessionLocation] = []
    for history in session_histories(stores, lookup):
        running = history[0].record.outcome not in SESSION_OVER
        current = [
            location
            for location in history
            if location.record.retains_subagents
            or (running and location.record.outcome not in SESSION_OVER)
        ]
        if not current:
            continue
        freshest = current[0]
        working = sorted(
            {agent for location in current for agent in location.record.live_subagents}
        )
        placed = any(
            same_path(location.worktree, one)
            for location in current
            for one in worktrees
        )
        if working and placed:
            found.append(
                SessionLocation(
                    replace(freshest.record, live_subagents=tuple(working)),
                    freshest.store,
                )
            )
    return found


def summarize_session_records(
    directory: Path, lookup: ProcessLookup = host_process_lookup
) -> SessionRecordSummary:
    """Classify one hook store's records for troubleshooting, without pruning."""
    probe = LivenessProbe(lookup)
    live = unknown = unreadable = 0
    unknown_by_reason: dict[str, int] = {}
    stale: list[StaleSessionRecord] = []

    def count_unreadable(_path: Path, _exc: Exception) -> None:
        nonlocal unreadable
        unreadable += 1

    for scanned in scan_hook_stores([directory], probe, on_unreadable=count_unreadable):
        record = scanned.record
        if record.outcome == "live":
            live += 1
        elif record.outcome == "unknown":
            unknown += 1
            reason = record.reason or "host process identity is unavailable"
            unknown_by_reason[reason] = unknown_by_reason.get(reason, 0) + 1
        else:
            stale.append(
                StaleSessionRecord(
                    session_id=record.session_id,
                    harness=record.harness,
                    event=record.event,
                    last_activity_at=record.last_activity_at,
                    pid=record.process_key[0] if record.process_key else None,
                    outcome="gone" if record.outcome == "gone" else "ended",
                    retained_subagents=(
                        record.live_subagents if record.retains_subagents else ()
                    ),
                )
            )
    return SessionRecordSummary(
        directory=directory,
        live=live,
        unknown=unknown,
        unknown_reasons=tuple(sorted(unknown_by_reason.items())),
        stale=tuple(stale),
        unreadable=unreadable,
    )
