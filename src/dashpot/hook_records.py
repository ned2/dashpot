"""Author, store, route, classify, and scan hook Agent Session records."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, ValidationError

from .git import Git, GitError
from .harnesses import HARNESS_DISPLAY, SESSION_ID, SessionIdentityClaim
from .json_records import optional_string, require_string
from .liveness import LivenessObservation, LivenessProbe, SessionLiveness
from .models import (
    NonEmptyString,
    PersistedRecord,
    describe_validation_error,
    validate_degrading,
)
from .processes import (
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    SessionProcessRecord,
    host_process_lookup,
    observe_agent_ancestry,
)
from .record_store import LockedRecordStore
from .repository import repository_worktrees

EVENT_STATES: dict[str, str] = {
    "SessionStart": "running",
    "UserPromptSubmit": "running",
    "PreToolUse": "running",
    "PostToolUse": "running",
    "Stop": "waiting",
    "Interrupt": "waiting",
    "SessionEnd": "ended",
}


def now_iso() -> str:
    """Stamp an observation, at a fixed width so records order by text too."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def observed_instant(value: str | None) -> datetime:
    """Order observations by instant; a record may be older than the format.

    Unstamped and unparsable records sort before every stamped one rather
    than claiming a time Dashpot never observed.
    """
    if value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def state_directory() -> Path:
    override = os.environ.get("DASHPOT_STATE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "dashpot" / "runs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dashpot" / "runs"
    return Path.home() / ".local" / "state" / "dashpot" / "runs"


HOOK_RECORD_VERSION = 2


def _session_identity(value: str) -> str:
    if not SESSION_ID.fullmatch(value):
        raise ValueError("contains unsupported characters")
    return value


def _supported_harness(value: str) -> str:
    if value not in HARNESS_DISPLAY:
        raise ValueError(f"unsupported harness: {value!r}")
    return value


def _active_state(value: str) -> str:
    if value not in {"running", "waiting", "ended"}:
        raise ValueError(f"unsupported active state: {value!r}")
    return value


def _blank_to_none(value: str | None) -> str | None:
    # The hand reader these fields replace read "" as absent; keep that.
    return value or None


HookSessionIdentity = Annotated[str, AfterValidator(_session_identity)]
Harness = Annotated[str, AfterValidator(_supported_harness)]
ActiveState = Annotated[str, AfterValidator(_active_state)]
OptionalText = Annotated[str | None, AfterValidator(_blank_to_none)]


class HookRecord(PersistedRecord):
    """One version-2 hook Agent Session record, as its harness's hook published it.

    Only the fields in ``HOOK_RECORD_FATAL`` fail the record; every other
    field degrades to its default with a message, so a session whose record
    is partly malformed stays visible-but-degraded rather than lost.
    ``source``, ``turnId``, and ``model`` are harness payload copied through
    unvalidated: a surprising payload must never make the hook itself fail.
    """

    version: Literal[2]
    session_id: HookSessionIdentity
    harness: Harness = "codex"
    state: ActiveState
    cwd: NonEmptyString
    repository_root: OptionalText = None
    branch: OptionalText = None
    event: OptionalText = None
    source: Any = None
    turn_id: Any = None
    model: Any = None
    last_activity_at: OptionalText = None
    session_process: SessionProcessRecord | None = None
    # Why the host process is unknown, when it is: distinguishes a hook that
    # ran where the harness is unobservable from one with no harness.
    session_process_unobservable: OptionalText = None
    turn_started_at: OptionalText = None

    @property
    def has_global_binding(self) -> bool:
        # Retired records bound an Issue in the hook record itself; the Work
        # Store is the sole authority now, so the fields are only detected.
        extra = self.model_extra or {}
        return (
            extra.get("issueId") is not None
            or extra.get("issueReferenceHint") is not None
        )


# A harness that is present but unsupported is fatal too: defaulting it to
# codex would report another harness's session as a Codex one.
HOOK_RECORD_FATAL = frozenset({"version", "sessionId", "harness", "state", "cwd"})


def build_hook_record(
    event: dict[str, Any],
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
    harness: str = "codex",
    process_unobservable: str | None = None,
) -> dict[str, Any]:
    session_id = require_string(event.get("session_id"), "session_id")
    if not SESSION_ID.fullmatch(session_id):
        raise RuntimeError("hook session_id contains unsupported characters")
    event_name = require_string(event.get("hook_event_name"), "hook_event_name")
    state = EVENT_STATES.get(event_name)
    if state is None:
        raise RuntimeError(f"unsupported hook event: {event_name}")
    cwd = Path(require_string(event.get("cwd"), "cwd")).expanduser().resolve()
    # ``environ`` stays in the signature for its callers even though records
    # no longer read anything from the environment: the retired
    # DASHPOT_ISSUE_ID/DASHPOT_ISSUE_REF global-binding convention was the
    # last such read, and the Work Store is the sole binding authority now.
    # Each answer stands alone: a detached HEAD has no symbolic ref but is
    # still inside a Worktree whose root routes the record. A hook must never
    # break its harness, so a Git that cannot answer at all — a vanished cwd,
    # no git binary — is recorded as unobserved rather than raised.
    git = Git(cwd, timeout=2)
    try:
        observed_target = git.maybe("rev-parse", "--show-toplevel")
    except GitError:
        observed_target = None
    try:
        branch = git.maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    except GitError:
        branch = None
    record = HookRecord(
        version=HOOK_RECORD_VERSION,
        session_id=session_id,
        harness=harness,
        state=state,
        cwd=str(cwd),
        repository_root=observed_target,
        branch=branch,
        event=event_name,
        source=event.get("source"),
        turn_id=event.get("turn_id"),
        model=event.get("model"),
        last_activity_at=now_iso(),
        session_process=SessionProcessRecord.of(process) if process else None,
        session_process_unobservable=None if process else process_unobservable,
    )
    # ``turnStartedAt`` is the store's to derive against the previous record.
    return record.model_dump(by_alias=True, exclude={"turn_started_at"})


def turn_started_at(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str | None:
    """When the running turn began: carried while running, cleared once not.

    A turn's age and a session's idle time are different questions, so the
    record keeps the turn's start rather than overloading its last activity.
    """
    if current.get("state") != "running":
        return None
    if previous is not None and previous.get("state") == "running":
        carried = optional_string(previous.get("turnStartedAt"))
        if carried is not None:
            return carried
    return optional_string(current.get("lastActivityAt"))


def write_hook_record(record: dict[str, Any], directory: Path) -> Path:
    return HookRecordStore(directory).write(record)


class HookRecordStore(LockedRecordStore):
    """Own the lifecycle of hook Agent Session records in one directory.

    Events are published atomically, a graceful ``SessionEnd`` removes the
    session's record, and confirmed stale records can be pruned without
    racing a concurrent hook write.
    """

    def __init__(self, directory: Path) -> None:
        super().__init__(
            directory, SESSION_ID, "hook sessionId contains unsupported characters"
        )

    def write(self, record: dict[str, Any]) -> Path:
        session_id = require_string(record.get("sessionId"), "sessionId")
        destination = self.record_path(session_id)
        if record.get("state") == "ended":
            # A graceful SessionEnd ends the Agent Session; a tombstone would
            # only be an active-looking record that observers have to skip.
            with self.locked(session_id):
                destination.unlink(missing_ok=True)
            return destination
        current = dict(record)
        with self.locked(session_id):
            previous = self._read(destination)
            current["turnStartedAt"] = turn_started_at(current, previous)
            self.replace(session_id, current)
        return destination

    def prune(self, session_id: str, observed: Mapping[str, Any]) -> bool:
        """Delete a stale record only if it still equals ``observed``.

        The conditional re-read under the session's lock means a record that a
        hook updated between observation and cleanup is kept. The lock file
        is left for ``prune_lock`` to reclaim on a later pass. Returns whether
        the record was removed.
        """
        destination = self.record_path(session_id)
        with self.locked(session_id):
            try:
                current = self._read(destination)
            except (RuntimeError, ValueError):
                return False
            if current is None or current != dict(observed):
                return False
            destination.unlink(missing_ok=True)
            return True

    def read(self, session_id: str) -> dict[str, Any] | None:
        """Read one session's current record, or ``None`` when it has none.

        Raises ``ValueError`` when the record exists but cannot be interpreted.
        """
        try:
            return read_hook_record(self.record_path(session_id))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(str(exc)) from exc

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            raw: Any = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            raise RuntimeError(f"hook record is not an object: {path}")
        return raw


def session_directory(worktree: Path) -> Path:
    """The Project-local session record store beneath one Worktree."""
    return worktree / ".dashpot" / "state" / "sessions"


def route_record_directory(record: Mapping[str, Any]) -> Path:
    """Choose the Project-local store for a configured checkout, else global."""
    root = optional_string(record.get("repositoryRoot"))
    if root and (Path(root) / ".dashpot" / "config.json").is_file():
        return session_directory(Path(root))
    return state_directory()


def publish_hook_event(
    event: dict[str, Any],
    directory: Path | None = None,
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
    harness: str = "codex",
) -> Path:
    identity = process
    process_unobservable: str | None = None
    if identity is None:
        ancestry = observe_agent_ancestry(harness=harness)
        identity = None if ancestry.located is None else ancestry.located[1]
        process_unobservable = ancestry.unobservable_reason
    record = build_hook_record(
        event,
        environ=environ,
        process=identity,
        harness=harness,
        process_unobservable=process_unobservable,
    )
    return write_hook_record(record, directory or route_record_directory(record))


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
        return Path(self.record.repository_root or self.record.cwd)

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
    if expected_session_id is not None and record.session_id != expected_session_id:
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


def locate_agent_session(
    stores: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
    *,
    session_id: str | None = None,
    process_key: ProcessKey | None = None,
) -> SessionLocation | None:
    """Place an Agent Session by its freshest hook record across ``stores``.

    A record is the session's when it carries its Agent Session Identity or
    was published for its host process; the freshest by ``lastActivityAt``
    wins, so a record left behind at a Worktree the session moved away from
    never places it. A record named by ``session_id`` that cannot be read
    raises ``ValueError``; other unreadable records are not evidence and are
    skipped.
    """
    if session_id is None and process_key is None:
        raise ValueError("a session is located by its identity or its process")

    def named(path: Path) -> bool:
        return session_id is not None and path.stem == session_id

    def worth_reading(path: Path) -> bool:
        return named(path) or process_key is not None

    def refuse_named(path: Path, exc: Exception) -> None:
        if named(path):
            raise ValueError(str(exc)) from exc

    probe = LivenessProbe(lookup)
    freshest: SessionLocation | None = None
    for scanned in scan_hook_stores(
        stores, probe, select=worth_reading, on_unreadable=refuse_named
    ):
        if not named(scanned.path) and scanned.record.process_key != process_key:
            continue
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
    freshest: dict[str, SessionLocation] = {}
    for scanned in scan_hook_stores(stores, probe):
        previous = freshest.get(scanned.record.session_id)
        if previous is None or observed_instant(
            scanned.record.last_activity_at
        ) > observed_instant(previous.record.last_activity_at):
            freshest[scanned.record.session_id] = SessionLocation(
                scanned.record, scanned.store
            )
    return [
        location
        for _session_id, location in sorted(freshest.items())
        if location.record.outcome not in {"ended", "gone"}
        and location.worktree.resolve() == target
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


@dataclass(frozen=True, slots=True)
class ValidatedSessionIdentity:
    """A claimed Agent Session Identity its harness's hook record confirmed."""

    claim: SessionIdentityClaim
    record: HookRecordClassification
    process: ProcessIdentity | None
    location: SessionLocation | None = None

    @property
    def harness(self) -> str:
        return self.claim.harness

    @property
    def session_id(self) -> str:
        return self.claim.session_id


def validate_session_claim(
    claim: SessionIdentityClaim,
    worktree: Path,
    lookup: ProcessLookup = host_process_lookup,
    *,
    stores: Sequence[Path] | None = None,
) -> ValidatedSessionIdentity:
    """Confirm a claimed identity against its harness's freshest hook record.

    The record is the session's freshest across every hook store reachable
    from ``worktree`` — those of the Repository's Worktrees and the global
    store — and must still describe a session that is live or unknown; a
    missing, unreadable, ended, gone, cross-harness, or process-mismatched
    record raises an actionable ``RuntimeError`` so that no Issue Binding is
    created from the claim. Where that record places the session is
    returned with it; whether that is ``worktree`` is the caller's question.
    """
    display = HARNESS_DISPLAY[claim.harness]
    name = f"{display} session {claim.session_id} (from {claim.source})"
    if stores is None:
        stores = reachable_hook_stores(repository_worktrees(worktree))
    try:
        location = locate_agent_session(stores, lookup, session_id=claim.session_id)
    except ValueError as exc:
        raise RuntimeError(
            f"the lifecycle hook record for {name} cannot be read: {exc}; "
            f"run 'dashpot integrate {claim.harness} --status'"
        ) from exc
    if location is None:
        raise RuntimeError(
            f"no lifecycle hook record for {name} at {worktree} or any other "
            f"Worktree of its Repository; the {display} hooks must be installed "
            f"and have published this session (check 'dashpot integrate "
            f"{claim.harness} --status')"
        )
    record = location.record
    if record.harness != claim.harness:
        raise RuntimeError(
            f"{name} names a hook record published by {record.display}; the "
            f"identities of two harnesses cannot be combined"
        )
    if record.outcome in {"ended", "gone"}:
        how = "ended" if record.outcome == "ended" else "whose process is gone"
        raise RuntimeError(
            f"the lifecycle hook record for {name} at {location.worktree} is "
            f"stale ({how}); it identifies no running session"
        )
    process = location.process
    if claim.pid is not None and process is not None and process.pid != claim.pid:
        raise RuntimeError(
            f"{name} attributes the harness to pid {claim.pid}, but its hook "
            f"record was published for pid {process.pid}; the identities do "
            f"not describe one session"
        )
    return ValidatedSessionIdentity(claim, record, process, location)
