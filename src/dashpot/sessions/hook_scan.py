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
    names_another_process,
    session_directory,
    state_directory,
    subagent_hosts,
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
# The outcomes of a record whose session is over where it places it.
SESSION_OVER: frozenset[HookRecordOutcome] = frozenset({"ended", "gone"})


@dataclass(frozen=True, slots=True)
class HookRecordClassification:
    """One validated hook Agent Session record and its reconciled outcome.

    ``published`` is the record as its harness's hook published it; the
    rest is what this pass's process evidence makes of it.
    """

    published: HookRecord
    outcome: HookRecordOutcome
    # The record's state once its sub-agents' Host Processes are accounted
    # for: running only while a main turn or a living sub-agent holds it.
    state: ActiveState
    reason: str | None = None
    # Malformed non-fatal fields the record was read without, by wire path.
    degraded: tuple[str, ...] = ()
    # The ``agent_id`` of each sub-agent the store holds started and not yet
    # stopped (ADR 0016), from Claude Code or Codex (ADR 0067), save one
    # whose Host Process is proved gone (ADR 0107).
    live_subagents: tuple[str, ...] = ()

    @property
    def session_id(self) -> str:
        return self.published.session_id

    @property
    def harness(self) -> Harness:
        return self.published.harness

    @property
    def cwd(self) -> str:
        return self.published.cwd

    @property
    def repository_root(self) -> str | None:
        return self.published.repository_root

    @property
    def branch(self) -> str | None:
        return self.published.branch

    @property
    def event(self) -> str | None:
        return self.published.event

    @property
    def last_activity_at(self) -> str | None:
        return self.published.last_activity_at

    @property
    def turn_started_at(self) -> str | None:
        return self.published.turn_started_at

    @property
    def has_global_binding(self) -> bool:
        return self.published.has_global_binding

    @property
    def process(self) -> ProcessIdentity | None:
        process = self.published.session_process
        return None if process is None else process.identity

    @property
    def process_key(self) -> ProcessKey | None:
        return self.published.process_key

    @property
    def over(self) -> bool:
        """Whether the record says its session is over here: ended, or gone."""
        return self.outcome in SESSION_OVER

    @property
    def retains_subagents(self) -> bool:
        """Whether an ended record still holds sub-agents its session left working.

        It lists some whose Host Process is not proved gone (ADR 0095). The
        session is over; those sub-agents may not be.
        """
        return self.outcome == "ended" and bool(self.live_subagents)

    @property
    def retains_other_host_subagents(self) -> bool:
        """Whether a gone record still lists sub-agents another Host Process runs.

        That process is not proved gone: a second process that resumed the
        session exited while the first one's sub-agent works on (ADR 0107).
        """
        return self.outcome == "gone" and bool(self.live_subagents)

    @property
    def evidence(self) -> SessionEvidence:
        """The session facts this record was published under, for matching."""
        return SessionEvidence(self.harness, self.session_id, self.process_key)

    @property
    def worktree(self) -> Path:
        """The Worktree the harness last published from: its root, else its cwd."""
        return self.published.worktree

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
    # Each Sub-agent keeping an ended or gone record, with the Host Process
    # that runs it; None means its process is unreadable (ADR 0107).
    retained_subagents: tuple[tuple[str, ProcessKey | None], ...] = ()


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
    """Where one hook record places its Agent Session.

    ``SessionHistory`` decides which record places a session. The record's
    ``repositoryRoot`` (else its ``cwd``) is the Worktree the harness itself
    published it from, which is where it places the session whatever
    directory a command inside it runs in.
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
    degraded = (
        *degraded,
        *(
            f"subagentProcesses.{agent} names no readable Host Process"
            for agent in record.unreadable_subagent_hosts
        ),
    )
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
    namespace = record.session_process.pid_namespace if record.session_process else None
    if record.state == "ended":
        liveness = LivenessObservation("unknown")
        outcome: HookRecordOutcome = "ended"
        own_living = (
            process is not None
            and probe.observe(process.key, namespace=namespace).liveness != "gone"
        )
    else:
        liveness = probe.observe(process.key if process else None, namespace=namespace)
        if process is None and record.session_process_unobservable is not None:
            # The hook said why it could name no Host Process, such as an
            # isolated namespace; that is the reason its liveness is unknown.
            liveness = LivenessObservation(
                "unknown", record.session_process_unobservable
            )
        elif (
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
        own_living = outcome != "gone"
    living = tuple(
        agent
        for agent in record.live_subagents
        if _subagent_living(record, agent, probe, own_living=own_living)
    )
    state = record.state
    if (
        state == "running"
        and own_living
        and record.turn_started_at is None
        and record.live_subagents
        and not living
    ):
        # No main turn runs, and every sub-agent that held the session
        # running ran in a Host Process since gone (ADR 0107).
        state = "waiting"
    return HookRecordClassification(
        published=record,
        outcome=outcome,
        state=state,
        reason=liveness.reason,
        degraded=degraded,
        live_subagents=living,
    )


def _subagent_living(
    record: HookRecord, agent: str, probe: LivenessProbe, *, own_living: bool
) -> bool:
    """Whether the Host Process running ``record``'s ``agent`` is not gone (ADR 0107).

    That is the record's own process unless the agent is tagged with another.
    One tagged with a malformed process is not known to be gone, so it stays.
    """
    if agent not in record.subagent_processes:
        return own_living
    host = record.subagent_processes[agent]
    if host is None:
        return True
    return (
        probe.observe(host.identity.key, namespace=host.pid_namespace).liveness
        != "gone"
    )


@dataclass(frozen=True, slots=True)
class ScannedRecord:
    """One readable hook record a store scan classified, with where it lives."""

    store: Path
    path: Path
    raw: dict[str, Any]
    record: HookRecordClassification

    @property
    def location(self) -> SessionLocation:
        """Where this record places its session, and the store holding it."""
        return SessionLocation(self.record, self.store)


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
            keys.extend(
                host.identity.key
                for host in validated.subagent_processes.values()
                if host is not None
            )
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
        return self.record.worktree

    @property
    def process_key(self) -> ProcessKey | None:
        return self.record.process_key

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
    (ADR 0101) and every live record its session left behind (ADR 0102).
    Like ``stored_session_records`` it probes no process. A record that
    cannot be read or validated is no evidence and is skipped: a caller
    changes a record only through its store, which re-reads it under its own
    lock.
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


def freshest_first[T](
    records: Iterable[T], stamp: Callable[[T], str | None]
) -> list[T]:
    """``records`` by their ``lastActivityAt`` ``stamp``, freshest first: the one tie-break.

    Of two stamped alike, the first read leads, since the sort is stable.
    A caller reads stores in the order ``reachable_hook_stores`` gives them,
    each Worktree's own store before the global one, and a store's records
    in path order. The scan's ``SessionHistory`` and the publisher's
    unprobed reads order a session's records this one way.
    """
    return sorted(
        records, key=lambda record: observed_instant(stamp(record)), reverse=True
    )


def freshest_stored_record(
    records: Iterable[StoredSessionRecord],
) -> StoredSessionRecord | None:
    """The record stamped latest; of two stamped alike, the first read."""
    ordered = freshest_first(records, lambda item: item.record.last_activity_at)
    return ordered[0] if ordered else None


@dataclass(frozen=True, slots=True)
class SessionHistory:
    """One Agent Session Identity's readable hook records across stores, freshest first.

    Each checkout keeps its own store, so a session that moved between
    Worktrees has a record in each. This is the one place that decides which
    record places the session, and every reader of placement asks it:
    observation, Cleanup occupancy, ``work start``/``show``/``assign``,
    claim validation and a pending relocation's diagnosis.

    The rule: records are ordered by ``lastActivityAt`` with one tie-break
    (``freshest_first``). A live or unknown record is *current*, saying the
    session may run where it places it, unless a fresher record that is
    over (ended, or gone) ends it. An over record speaks for its own Host
    Process only, so it ends an older record of that process, or of none
    named, which is no evidence of another (ADR 0132), and never an older
    record another named process still holds: a Codex client whose resumed
    successor exited, or a Host Process still running after another one's
    ``SessionEnd`` (ADR 0107). The session is placed by its freshest current
    record, and is over when it has none.
    """

    records: tuple[ScannedRecord, ...]

    @classmethod
    def of(cls, records: Iterable[ScannedRecord]) -> SessionHistory:
        """The history of one identity's scanned records, in the order they were read."""
        return cls(
            tuple(freshest_first(records, lambda item: item.record.last_activity_at))
        )

    @property
    def identity(self) -> tuple[Harness, str]:
        """The harness and native session id every record here shares."""
        record = self.records[0].record
        return record.harness, record.session_id

    @property
    def freshest(self) -> ScannedRecord:
        """The record stamped latest, whatever its outcome."""
        return self.records[0]

    @property
    def current(self) -> tuple[ScannedRecord, ...]:
        """Every record that says the session may run where it places it, freshest first.

        More than one is current when the session's records at several
        Worktrees are live or unknown: a move leaves the record it left
        behind (ADR 0102), and two clients may hold one Codex session.
        """
        over: list[HookRecordClassification] = []
        found: list[ScannedRecord] = []
        for scanned in self.records:
            record = scanned.record
            if record.over:
                over.append(record)
            elif all(
                names_another_process(ended.published, record.published)
                for ended in over
            ):
                found.append(scanned)
        return tuple(found)

    @property
    def superseded(self) -> tuple[ScannedRecord, ...]:
        """The live or unknown records a fresher ended or gone record superseded, freshest first.

        None of them places the session or lists its sub-agents any more.
        """
        current = {scanned.path for scanned in self.current}
        return tuple(
            scanned
            for scanned in self.records
            if not scanned.record.over and scanned.path not in current
        )

    @property
    def freshest_current(self) -> ScannedRecord | None:
        """The record that places the session while it runs; None once it is over."""
        current = self.current
        return current[0] if current else None

    @property
    def placing(self) -> ScannedRecord:
        """The record that says where the session is, or why it is over.

        That is its freshest current record, else its freshest record, whose
        outcome says how the session ended.
        """
        current = self.freshest_current
        return self.freshest if current is None else current

    @property
    def retained_subagents(self) -> frozenset[str]:
        """The sub-agents the session's ended records keep listed (ADR 0095).

        An ended record keeps those its session left working while their
        Host Process is not proved gone. This assumes, as ADR 0066 does, that
        no hook places a sub-agent itself: which of the session's records
        lists it, not where it works, is what is known (#474 re-measures it).
        """
        return frozenset(
            agent
            for scanned in self.records
            if scanned.record.retains_subagents
            for agent in scanned.record.live_subagents
        )

    @property
    def subagent_listings(self) -> tuple[ScannedRecord, ...]:
        """The records whose listed sub-agents may still be working, freshest first.

        Those are the current records, each ended record that keeps the
        sub-agents its session left working (ADR 0095), and each gone record
        that lists a sub-agent another Host Process runs (ADR 0107). A
        current record its session moved on from counts: a sub-agent's hooks
        carry its session's location, never its own, and the record left
        behind may be the only one to list it (ADR 0102).
        """
        current = {scanned.path for scanned in self.current}
        return tuple(
            scanned
            for scanned in self.records
            if scanned.path in current
            or scanned.record.retains_subagents
            or scanned.record.retains_other_host_subagents
        )


def group_histories(scanned: Iterable[ScannedRecord]) -> list[SessionHistory]:
    """Each Agent Session Identity's ``SessionHistory``, in the order first read."""
    grouped: dict[tuple[Harness, str], list[ScannedRecord]] = {}
    for item in scanned:
        identity = (item.record.harness, item.record.session_id)
        grouped.setdefault(identity, []).append(item)
    return [SessionHistory.of(records) for records in grouped.values()]


def session_histories(
    stores: Sequence[Path], lookup: ProcessLookup
) -> list[SessionHistory]:
    """Each Agent Session's ``SessionHistory`` across ``stores``, by identity.

    A record that cannot be read is not evidence and is skipped.
    """
    histories = group_histories(scan_hook_stores(stores, LivenessProbe(lookup)))
    return sorted(histories, key=lambda history: history.identity)


def locate_agent_session(
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
    *,
    session_id: str,
    harness: Harness,
) -> SessionLocation | None:
    """Place a scoped native identity by its ``SessionHistory``.

    The location is the session's freshest current record, else, once the
    session is over, its freshest record, whose outcome says why: a caller
    refuses a session that is over. An unreadable record of the identity
    raises ``ValueError``.
    """

    def named(path: Path) -> bool:
        return session_record_named(path, session_id, harness)

    def refuse_named(path: Path, exc: Exception) -> None:
        if named(path):
            raise ValueError(str(exc)) from exc

    identity = SessionEvidence(harness, session_id)
    # Every record the identity matches is of that one harness and session.
    histories = group_histories(
        scanned
        for scanned in scan_hook_stores(
            stores, LivenessProbe(lookup), select=named, on_unreadable=refuse_named
        )
        if identity.match(scanned.record.evidence) == "same"
    )
    return histories[0].placing.location if histories else None


def sessions_at_worktree(
    worktree: Path,
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[SessionLocation]:
    """Every Agent Session whose freshest current record places it at ``worktree``."""
    target = worktree.resolve()
    return [
        current.location
        for history in session_histories(stores, lookup)
        if (current := history.freshest_current) is not None
        and same_path(current.record.worktree, target)
    ]


def sessions_with_live_subagents(
    worktrees: Sequence[Path],
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[SessionLocation]:
    """Every Agent Session in ``worktrees`` with a sub-agent listed as working.

    A sub-agent's hooks carry its session's location, never its own, so where
    it works is unknown: it may be in any Worktree of the Repository. Every
    record of ``SessionHistory.subagent_listings`` counts, and the location
    reported is the freshest one's: an ended record is the one reported when
    it is the freshest (ADR 0095). A sub-agent's stop clears it from each of
    those records (ADR 0102).
    """
    found: list[SessionLocation] = []
    for history in session_histories(stores, lookup):
        listings = history.subagent_listings
        if not listings:
            continue
        freshest = listings[0]
        working = sorted(
            {agent for scanned in listings for agent in scanned.record.live_subagents}
        )
        placed = any(
            same_path(scanned.record.worktree, one)
            for scanned in listings
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
            hosts = subagent_hosts(record.published)
            stale.append(
                StaleSessionRecord(
                    session_id=record.session_id,
                    harness=record.harness,
                    event=record.event,
                    last_activity_at=record.last_activity_at,
                    pid=record.process_key[0] if record.process_key else None,
                    outcome="gone" if record.outcome == "gone" else "ended",
                    retained_subagents=tuple(
                        (
                            agent,
                            None
                            if (host := hosts[agent]) is None
                            else host.identity.key,
                        )
                        for agent in record.live_subagents
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
