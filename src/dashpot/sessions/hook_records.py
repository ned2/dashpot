"""Store hook Agent Session records."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

from pydantic import AfterValidator, BeforeValidator, Field, ValidationError

from ..core.git import Git, GitError
from ..core.json_records import HookRecordError, optional_string, require_string
from ..core.model import Harness
from ..core.project_state import project_state_directory
from ..core.pydantic import NonEmptyString, PersistedRecord
from ..core.record_store import LockedRecordStore
from ..core.state_paths import machine_state_directory
from ..core.timestamps import observed_instant, utc_now
from .harnesses import SESSION_ID, HarnessName, HookSessionIdentity, delegate_id
from .processes import ProcessIdentity, ProcessKey, SessionProcessRecord
from .session_matching import session_storage_key

# What a hook record says its session is doing; ``ended`` is the state a
# graceful SessionEnd leaves, which the published ``RunState`` never shows.
ActiveState = Literal["running", "waiting", "ended"]
EVENT_STATES: dict[str, ActiveState] = {
    "SessionStart": "running",
    "UserPromptSubmit": "running",
    "PreToolUse": "running",
    "PostToolUse": "running",
    "Stop": "waiting",
    "Interrupt": "waiting",
    "SessionEnd": "ended",
    # A sub-agent's boundaries are the session's too: the store reconciles
    # these base states against the sub-agents it knows to be alive.
    "SubagentStart": "running",
    "SubagentStop": "waiting",
}
SUBAGENT_EVENTS = frozenset({"SubagentStart", "SubagentStop"})
# Where a record places its session; a Sub-agent's event keeps its parent's.
LOCATION_FIELDS = ("cwd", "repositoryRoot", "branch")


def state_directory() -> Path:
    override = os.environ.get("DASHPOT_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return machine_state_directory() / "runs"


HOOK_RECORD_VERSION = 2


def _active_state(value: object) -> object:
    if value not in get_args(ActiveState):
        raise ValueError(f"unsupported active state: {value!r}")
    return value


def _blank_to_none(value: str | None) -> str | None:
    # The hand reader these fields replace read "" as absent; keep that.
    return value or None


# The validator ahead of the union keeps the record's refusal naming the state.
ActiveStateName = Annotated[ActiveState, BeforeValidator(_active_state)]
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
    harness: HarnessName = "codex"
    state: ActiveStateName
    cwd: NonEmptyString
    repository_root: OptionalText = None
    branch: OptionalText = None
    event: OptionalText = None
    source: Any = None
    turn_id: Any = None
    model: Any = None
    agent_id: Any = None
    last_activity_at: OptionalText = None
    session_process: SessionProcessRecord | None = None
    # Why the host process is unknown, when it is: distinguishes a hook that
    # ran where the harness is unobservable from one with no harness.
    session_process_unobservable: OptionalText = None
    turn_started_at: OptionalText = None
    # The session's sub-agents observed started and not yet stopped; a
    # session whose main turn has ended is still running while any is alive.
    live_subagents: list[str] = Field(default_factory=list)
    # When this store last saw the session begin an incarnation (its latest
    # ``SessionStart``), so a live move can be told from a restart (ADR
    # 0067); absent on a record written before it was kept, or by a store
    # that has seen none.
    last_session_start_at: OptionalText = None

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
    process: ProcessIdentity | None = None,
    harness: Harness = "codex",
    process_unobservable: str | None = None,
) -> dict[str, Any]:
    session_id = require_string(event.get("session_id"), "session_id")
    if not SESSION_ID.fullmatch(session_id):
        raise HookRecordError("hook session_id contains unsupported characters")
    event_name = require_string(event.get("hook_event_name"), "hook_event_name")
    state = EVENT_STATES.get(event_name)
    if state is None:
        raise HookRecordError(f"unsupported hook event: {event_name}")
    cwd = Path(require_string(event.get("cwd"), "cwd")).expanduser().resolve()
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
        agent_id=event.get("agent_id"),
        last_activity_at=utc_now(),
        session_process=SessionProcessRecord.of(process) if process else None,
        session_process_unobservable=None if process else process_unobservable,
    )
    # ``turnStartedAt``, ``liveSubagents`` and ``lastSessionStartAt`` are the
    # store's to derive against the previous record.
    return record.model_dump(
        by_alias=True,
        exclude={"turn_started_at", "live_subagents", "last_session_start_at"},
    )


def is_child_record(record: Mapping[str, Any]) -> bool:
    """Whether a hook record was published for a Sub-agent's event, not its session's."""
    return delegate_id(record.get("agentId")) is not None


def turn_started_at(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str | None:
    """When the running turn began: carried while running, cleared once not.

    A turn's age and a session's idle time are different questions, so the
    record keeps the turn's start rather than overloading its last activity.
    """
    if current.get("event") in SUBAGENT_EVENTS or is_child_record(current):
        # A sub-agent's event is not the main turn's: its clock carries.
        if previous is None:
            return None
        return optional_string(previous.get("turnStartedAt"))
    if current.get("state") != "running":
        return None
    if previous is not None and previous.get("state") == "running":
        carried = optional_string(previous.get("turnStartedAt"))
        if carried is not None:
            return carried
    return optional_string(current.get("lastActivityAt"))


def live_subagents(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> list[str]:
    """Which sub-agents of the session are alive after this event.

    ``SubagentStart`` adds the agent, ``SubagentStop`` removes it, a new
    session starts with none, and every other event carries the set. An
    event that names no agent changes nothing rather than guessing.
    """
    event = current.get("event")
    if event == "SessionStart" or previous is None:
        alive: list[str] = []
    else:
        recorded: Any = previous.get("liveSubagents")
        alive = (
            [str(item) for item in recorded if isinstance(item, str)]
            if isinstance(recorded, list)
            else []
        )
    agent = current.get("agentId")
    if not isinstance(agent, str) or not agent:
        return alive
    if event == "SubagentStart":
        return sorted({*alive, agent})
    if event == "SubagentStop":
        return [item for item in alive if item != agent]
    return alive


def last_session_start_at(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str | None:
    """When this store last saw the session begin an incarnation.

    Set by the session's own ``SessionStart`` and carried, like the turn
    clock, from the same store's previous record of the identity.
    """
    if current.get("event") == "SessionStart" and not is_child_record(current):
        return optional_string(current.get("lastActivityAt"))
    if previous is None:
        return None
    return optional_string(previous.get("lastSessionStartAt"))


def carried_state(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str:
    """The base state a record starts from before its sub-agents are reconciled.

    A Sub-agent's own events (its prompt, tool calls, or an end of its own)
    say nothing about its parent's turn, so the parent keeps the state its
    previous record held; only the sub-agent boundaries change it (ADR 0016).
    A child-scoped event never ends its parent.
    """
    if not is_child_record(current) or current.get("event") in SUBAGENT_EVENTS:
        return str(current.get("state"))
    # A parent record whose state cannot be read is taken as busy: its
    # Sub-agent is evidently at work.
    recorded = None if previous is None else previous.get("state")
    return str(recorded) if recorded in {"running", "waiting"} else "running"


def observed_state(current: Mapping[str, Any]) -> str:
    """The session's state once its live sub-agents are accounted for.

    A main turn that stops while a sub-agent it delegated to is still working
    leaves the session running; a sub-agent stopping while the main turn is
    still in flight leaves it running too.
    """
    state = str(current.get("state"))
    if state == "waiting" and current.get("liveSubagents"):
        return "running"
    if current.get("event") == "SubagentStop" and current.get("turnStartedAt"):
        return "running"
    return state


def _same_host_process(one: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    """Whether two hook records name the same Host Process: its pid and start time.

    The parent and the argument vector are what a process was observed with,
    not its identity (ADR 0067): a Codex daemon that a terminal autostarted
    is reparented when that terminal exits and still serves the same
    sessions. Two records without a process match, as do two whose process
    cannot be read but is recorded identically; a process on one side only
    never matches.
    """
    first, second = one.get("sessionProcess"), other.get("sessionProcess")
    if first is None or second is None:
        return first is None and second is None
    first_key, second_key = _process_key(first), _process_key(second)
    if first_key is None or second_key is None:
        return first == second
    return first_key == second_key


def _process_key(raw: object) -> ProcessKey | None:
    try:
        return SessionProcessRecord.model_validate(raw).identity.key
    except ValidationError:
        return None


def write_hook_record(record: dict[str, Any], directory: Path) -> Path:
    return HookRecordStore(directory).write(record)


class HookRecordStore(LockedRecordStore):
    """Own the lifecycle of hook Agent Session records in one directory.

    Events are published atomically, a graceful ``SessionEnd`` removes the
    session's record, and confirmed stale records can be pruned without
    racing a concurrent hook write. A Project-local store names its
    ``checkout`` (see ``project_session_store``).
    """

    def __init__(self, directory: Path, *, checkout: Path | None = None) -> None:
        super().__init__(
            directory,
            SESSION_ID,
            "hook sessionId contains unsupported characters",
            checkout=checkout,
        )

    def write(
        self, record: dict[str, Any], *, seed: Mapping[str, Any] | None = None
    ) -> Path:
        """Publish one native identity without overwriting another harness.

        ``seed`` is the session's freshest record in another store, when the
        publisher found one: a session-scoped event of the same Host Process
        that moves the session's freshest record here derives its live
        sub-agents and turn clock from it rather than from an older record of
        this store, so a move never forgets a live Sub-agent (ADR 0067). A
        child-scoped event instead keeps this store's previous record's
        location, never ends it, and writes nothing but a sub-agent boundary
        where there is no record.
        """
        session_id = require_string(record.get("sessionId"), "sessionId")
        harness = require_string(record.get("harness"), "harness")
        # The store keeps what a harness published; a record naming an
        # unsupported harness is refused by the read model, as a diagnostic.
        native_key = (harness, session_id)
        scoped_key = session_storage_key(harness, session_id)
        with ExitStack() as stack:
            for key in sorted((session_id, scoped_key)):
                stack.enter_context(self.locked(key))
            scoped = self._read(self.record_path(scoped_key))
            legacy = self._read(self.record_path(session_id))
            if scoped is not None:
                key, previous = scoped_key, scoped
            elif (
                legacy is None
                or (legacy.get("harness"), legacy.get("sessionId")) == native_key
            ):
                key, previous = session_id, legacy
            else:
                key, previous = scoped_key, None
            if (
                previous is not None
                and (previous.get("harness"), previous.get("sessionId")) != native_key
            ):
                raise ValueError(
                    "hook destination is occupied by another Agent Session Identity"
                )
            destination = self.record_path(key)
            child = is_child_record(record)
            if record.get("state") == "ended" and not child:
                if previous is not None and (
                    not _same_host_process(previous, record)
                    or observed_instant(previous.get("lastActivityAt"))
                    > observed_instant(record.get("lastActivityAt"))
                ):
                    return destination
                destination.unlink(missing_ok=True)
                return destination
            if (
                child
                and previous is None
                and record.get("event") not in SUBAGENT_EVENTS
            ):
                # With no parent record here, only a boundary has anything to
                # say: the live set. Any other Sub-agent event would invent a
                # parent at the Sub-agent's location (ADR 0067).
                return destination
            current = dict(record)
            origin = previous
            if child and previous is not None:
                # A Sub-agent's event never places or routes its parent.
                for field in LOCATION_FIELDS:
                    current[field] = previous.get(field)
            elif (
                seed is not None
                and current.get("event") != "SessionStart"
                # Another process's sub-agents and turn are not this one's.
                and current.get("sessionProcess") is not None
                and _same_host_process(seed, current)
                and observed_instant(optional_string(seed.get("lastActivityAt")))
                > observed_instant(
                    None
                    if previous is None
                    else optional_string(previous.get("lastActivityAt"))
                )
            ):
                origin = seed
            current["state"] = carried_state(current, previous)
            current["liveSubagents"] = live_subagents(current, origin)
            current["turnStartedAt"] = turn_started_at(current, origin)
            started = last_session_start_at(current, previous)
            if started is not None:
                current["lastSessionStartAt"] = started
            current["state"] = observed_state(current)
            self.replace(key, current)
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
            except (HookRecordError, ValueError):
                return False
            if current is None or current != dict(observed):
                return False
            destination.unlink(missing_ok=True)
            return True

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            raw: Any = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            raise HookRecordError(f"hook record is not an object: {path}")
        return raw


def session_directory(worktree: Path) -> Path:
    """The Project-local session record store beneath one Worktree."""
    return project_state_directory(worktree) / "sessions"


def project_session_store(worktree: Path) -> HookRecordStore:
    """The Project-local hook store of one Worktree, whose writes keep it out of Git."""
    return HookRecordStore(session_directory(worktree), checkout=worktree)
