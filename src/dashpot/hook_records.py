"""Store hook Agent Session records."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field

from .core.git import Git, GitError
from .core.json_records import optional_string, require_string
from .core.pydantic import (
    NonEmptyString,
    PersistedRecord,
)
from .core.record_store import LockedRecordStore
from .harnesses import (
    HARNESS_DISPLAY,
    SESSION_ID,
    HookSessionIdentity,
)
from .processes import (
    ProcessIdentity,
    SessionProcessRecord,
)
from .session_matching import SessionEvidence
from .timestamps import observed_instant, utc_now

EVENT_STATES: dict[str, str] = {
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
    # ``turnStartedAt`` and ``liveSubagents`` are the store's to derive
    # against the previous record.
    return record.model_dump(
        by_alias=True, exclude={"turn_started_at", "live_subagents"}
    )


def turn_started_at(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str | None:
    """When the running turn began: carried while running, cleared once not.

    A turn's age and a session's idle time are different questions, so the
    record keeps the turn's start rather than overloading its last activity.
    """
    if current.get("event") in SUBAGENT_EVENTS:
        # A sub-agent's boundary is not the main turn's: its clock carries.
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
        """Publish one native identity without overwriting another harness."""
        session_id = require_string(record.get("sessionId"), "sessionId")
        harness = require_string(record.get("harness"), "harness")
        identity = SessionEvidence(harness, session_id)
        scoped_key = identity.storage_key()
        with ExitStack() as stack:
            for key in sorted((session_id, scoped_key)):
                stack.enter_context(self.locked(key))
            scoped = self._read(self.record_path(scoped_key))
            legacy = self._read(self.record_path(session_id))
            if scoped is not None:
                key, previous = scoped_key, scoped
            elif (
                legacy is None
                or (legacy.get("harness"), legacy.get("sessionId"))
                == identity.native_key
            ):
                key, previous = session_id, legacy
            else:
                key, previous = scoped_key, None
            if (
                previous is not None
                and (previous.get("harness"), previous.get("sessionId"))
                != identity.native_key
            ):
                raise ValueError(
                    "hook destination is occupied by another Agent Session Identity"
                )
            destination = self.record_path(key)
            if record.get("state") == "ended":
                if previous is not None and (
                    previous.get("sessionProcess") != record.get("sessionProcess")
                    or observed_instant(previous.get("lastActivityAt"))
                    > observed_instant(record.get("lastActivityAt"))
                ):
                    return destination
                destination.unlink(missing_ok=True)
                return destination
            current = dict(record)
            current["liveSubagents"] = live_subagents(current, previous)
            current["turnStartedAt"] = turn_started_at(current, previous)
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
            except (RuntimeError, ValueError):
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
            raise RuntimeError(f"hook record is not an object: {path}")
        return raw


def session_directory(worktree: Path) -> Path:
    """The Project-local session record store beneath one Worktree."""
    return worktree / ".dashpot" / "state" / "sessions"
