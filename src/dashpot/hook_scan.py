"""Classify and scan hook Agent Session records."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from .core.pydantic import (
    describe_validation_error,
    validate_degrading,
)
from .harnesses import (
    HARNESS_DISPLAY,
)
from .hook_records import (
    HOOK_RECORD_FATAL,
    HOOK_RECORD_VERSION,
    HookRecord,
    session_directory,
    state_directory,
)
from .liveness import LivenessObservation, LivenessProbe, SessionLiveness
from .processes import (
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
)
from .repository import same_path
from .session_matching import SessionEvidence
from .timestamps import observed_instant

# A hook record's outcome is its Session Liveness, plus the one fact liveness
# cannot express: a graceful SessionEnd, which is a record state, not a probe.
HookRecordOutcome = SessionLiveness | Literal["ended"]


@dataclass(frozen=True, slots=True)
class HookRecordClassification:
    """One validated hook Agent Session record and its reconciled outcome."""

    session_id: str
    harness: str
    state: str
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
    harness: str
    event: str | None
    last_activity_at: str | None
    pid: int | None
    outcome: Literal["gone", "ended"]


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
    try:
        record, degraded = validate_degrading(HookRecord, raw, fatal=HOOK_RECORD_FATAL)
    except ValidationError as exc:
        raise ValueError(describe_validation_error(exc)) from exc
    if expected_session_id is not None and expected_session_id not in {
        record.session_id,
        SessionEvidence(record.harness, record.session_id).storage_key(),
    }:
        raise ValueError("record sessionId does not match its filename")
    process = record.session_process.identity if record.session_process else None
    if record.state == "ended":
        liveness = LivenessObservation("unknown")
        outcome: HookRecordOutcome = "ended"
    else:
        liveness = probe.observe(process.key if process else None)
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
    )


@dataclass(frozen=True, slots=True)
class ScannedRecord:
    """One readable hook record a store scan classified, with where it lives."""

    store: Path
    path: Path
    raw: dict[str, Any]
    record: HookRecordClassification


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
    """
    for store in stores:
        if not store.is_dir():
            continue
        for path in sorted(store.glob("*.json")):
            if select is not None and not select(path):
                continue
            try:
                raw = read_hook_record(path)
                record = classify_hook_record(raw, probe, expected_session_id=path.stem)
            except (OSError, ValueError) as exc:
                if on_unreadable is not None:
                    on_unreadable(path, exc)
                continue
            yield ScannedRecord(store, path, raw, record)


def session_record_named(
    path: Path, session_id: str, harness: str | None = None
) -> bool:
    """Select legacy and harness-scoped filenames for full record validation."""
    if path.stem == session_id:
        return True
    harnesses = (harness,) if harness is not None else tuple(HARNESS_DISPLAY)
    return any(
        path.stem == SessionEvidence(candidate, session_id).storage_key()
        for candidate in harnesses
    )


def locate_agent_session(
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
    *,
    session_id: str | None = None,
    harness: str | None = None,
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


def sessions_at_worktree(
    worktree: Path,
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[SessionLocation]:
    """Every live or unknown Agent Session whose hooks last placed it at ``worktree``.

    Ended and gone records describe sessions that are over and are not
    reported; a record that cannot be read is not evidence and is skipped.
    """
    probe = LivenessProbe(lookup)
    target = worktree.resolve()
    freshest: dict[tuple[str, str], SessionLocation] = {}
    for scanned in scan_hook_stores(stores, probe):
        identity = (scanned.record.harness, scanned.record.session_id)
        previous = freshest.get(identity)
        if previous is None or observed_instant(
            scanned.record.last_activity_at
        ) > observed_instant(previous.record.last_activity_at):
            freshest[identity] = SessionLocation(scanned.record, scanned.store)
    return [
        location
        for _session_id, location in sorted(freshest.items())
        if location.record.outcome not in {"ended", "gone"}
        and same_path(location.worktree, target)
    ]


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
