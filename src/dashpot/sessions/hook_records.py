"""Store hook Agent Session records."""

from __future__ import annotations

import json
import os
from collections.abc import Collection, Iterable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, cast, get_args

from pydantic import AfterValidator, BeforeValidator, Field, ValidationError

from ..core.git import Git, GitError
from ..core.json_records import HookRecordError, optional_string, require_string
from ..core.model import Harness
from ..core.pydantic import NonEmptyString, PersistedRecord
from ..core.record_store import LockedRecordStore
from ..core.state_paths import machine_state_directory, project_state_directory
from ..core.timestamps import observed_instant, utc_now
from .harnesses import SESSION_ID, HarnessName, HookSessionIdentity, delegate_id
from .processes import ProcessIdentity, ProcessKey, SessionProcessRecord
from .session_matching import session_storage_key

# What a hook record says its session is doing; ``ended`` is the state a
# graceful SessionEnd leaves, which the published ``RunState`` never shows.
ActiveState = Literal["running", "waiting", "ended"]
EVENT_STATES: dict[str, ActiveState] = {
    # A session's start begins no turn: its harness publishes the prompt
    # that does, and a compaction keeps the turn it falls in (ADR 0106).
    "SessionStart": "waiting",
    "UserPromptSubmit": "running",
    "PreToolUse": "running",
    "PostToolUse": "running",
    # OpenCode's move of a session, which the OpenCode helper writes from
    # ``session.moved``; a move always falls inside an execution (ADR 0090).
    "SessionMoved": "running",
    "Stop": "waiting",
    "Interrupt": "waiting",
    "SessionEnd": "ended",
    # A sub-agent's boundaries are the session's too: the store reconciles
    # these base states against the sub-agents it knows to be alive.
    "SubagentStart": "running",
    "SubagentStop": "waiting",
}
SUBAGENT_EVENTS = frozenset({"SubagentStart", "SubagentStop"})
# The ``source`` Claude Code and Codex give the ``SessionStart`` they publish
# when they compact a live session, which goes on in the same turn, or goes on
# waiting (ADR 0100).
COMPACTION_SOURCE = "compact"
# The ``source`` Claude Code 2.1.289 gives the ``SessionStart`` of the
# conversation its Host Process switches to with ``/clear``, ``/resume`` or
# ``/branch``, and the ``reason`` of the ``SessionEnd`` it publishes first for
# the conversation it leaves; its sub-agents follow the switch (ADR 0101).
CONVERSATION_SWITCH_SOURCES = frozenset({"clear", "resume", "fork"})
CONVERSATION_SWITCH_REASONS = frozenset({"clear", "resume"})
# What a session's own ``SessionStart`` says its Host Process did, when its
# ``source`` says anything Dashpot acts on.
SessionStartKind = Literal["compaction", "switch"]
# Which records a stopped sub-agent is released from: an ended record of any
# session of its Host Process (ADR 0101), or a live record its own session
# left behind at another Worktree (ADR 0102).
ReleasedRecord = Literal["ended", "left-behind"]
# The states a live record holds; an ended record holds ``ended``.
LIVE_STATES = frozenset({"running", "waiting"})
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
    ``source``, ``reason``, ``turnId``, and ``model`` are harness payload
    copied through unvalidated: a surprising payload must never make the hook
    itself fail.
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
    reason: Any = None
    turn_id: Any = None
    model: Any = None
    agent_id: Any = None
    last_activity_at: OptionalText = None
    session_process: SessionProcessRecord | None = None
    # Why the host process is unknown, when it is: distinguishes a hook that
    # ran where the harness is unobservable from one with no harness. Beside a
    # named process, it says nothing observes the session in that process (an
    # OpenCode Host Process with no live plugin instance, ADR 0080), which
    # reads unknown while it lives.
    session_process_unobservable: OptionalText = None
    turn_started_at: OptionalText = None
    # The session's sub-agents observed started and not yet stopped; a
    # session whose main turn has ended is still running while any is alive,
    # and an ended record lists those its session left working (ADR 0095).
    live_subagents: list[str] = Field(default_factory=list)
    # The Host Process of each listed sub-agent that another process runs
    # than the one ``sessionProcess`` names, as a second Host Process's
    # events leave it; an agent absent here is the record's own (ADR 0107).
    subagent_processes: dict[str, SessionProcessRecord] = Field(default_factory=dict)
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
        reason=event.get("reason"),
        turn_id=event.get("turn_id"),
        model=event.get("model"),
        agent_id=event.get("agent_id"),
        last_activity_at=utc_now(),
        session_process=SessionProcessRecord.of(process) if process else None,
        session_process_unobservable=None if process else process_unobservable,
    )
    # ``turnStartedAt``, ``liveSubagents``, ``subagentProcesses`` and
    # ``lastSessionStartAt`` are the store's to derive against the previous
    # record.
    return record.model_dump(
        by_alias=True,
        exclude={
            "turn_started_at",
            "live_subagents",
            "subagent_processes",
            "last_session_start_at",
        },
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


def _carried_subagents(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    gone_hosts: Collection[ProcessKey],
) -> dict[str, Any]:
    """Each sub-agent of the session alive after this event, with its Host Process.

    A sub-agent belongs to the Host Process that runs it, which a session's
    resumption in another process does not end (ADR 0107). One the event's
    own process runs carries as the record's own; one another named process
    runs carries, tagged with that process, unless the publisher found that
    process among ``gone_hosts``. One whose process no record names carries
    unless the event is a ``SessionStart``: a session whose process cannot be
    named might have restarted unseen (ADR 0097). A starting sub-agent's
    process is the event's. The value is the raw ``sessionProcess`` of the
    sub-agent's Host Process, None where none is named.
    """
    hosts = (
        {}
        if previous is None
        else _carried_by_host(current, subagent_hosts(previous), gone_hosts)
    )
    return _crossing_boundary(current, hosts)


def _crossing_boundary(
    current: Mapping[str, Any], hosts: dict[str, Any]
) -> dict[str, Any]:
    """``hosts`` after ``current``'s sub-agent boundary, if it is one.

    ``SubagentStart`` adds the agent, run by the event's Host Process, and
    ``SubagentStop`` removes it; an event that names no agent changes
    nothing rather than guessing.
    """
    agent = current.get("agentId")
    if not isinstance(agent, str) or not agent:
        return hosts
    event = current.get("event")
    if event == "SubagentStart":
        hosts[agent] = current.get("sessionProcess")
    elif event == "SubagentStop":
        hosts.pop(agent, None)
    return hosts


def subagent_hosts(record: Mapping[str, Any]) -> dict[str, Any]:
    """Each sub-agent a stored record lists, with the Host Process recorded as running it.

    That is the agent's own entry in ``subagentProcesses``, else the
    record's ``sessionProcess`` (ADR 0107).
    """
    tags: Any = record.get("subagentProcesses")
    tagged: Mapping[str, Any] = tags if isinstance(tags, dict) else {}
    own = record.get("sessionProcess")
    return {agent: tagged.get(agent, own) for agent in _recorded_subagents(record)}


def hosts_subagent(record: Mapping[str, Any], agent: str, process: object) -> bool:
    """Whether ``record`` lists ``agent`` as run by the Host Process ``process`` names."""
    return agent in subagents_hosted_by(record, process)


def subagents_hosted_by(record: Mapping[str, Any], process: object) -> list[str]:
    """The sub-agents ``record`` lists as run by the Host Process ``process`` names."""
    if process is None:
        return []
    return sorted(
        agent
        for agent, host in subagent_hosts(record).items()
        if _same_process(host, process)
    )


def subagent_host_keys(record: Mapping[str, Any]) -> set[ProcessKey]:
    """The Host Processes ``record`` names for its listed sub-agents, by key."""
    keys = {_process_key(host) for host in subagent_hosts(record).values()}
    return {key for key in keys if key is not None}


def _carried_by_host(
    current: Mapping[str, Any],
    hosts: Mapping[str, Any],
    gone_hosts: Collection[ProcessKey],
) -> dict[str, Any]:
    """The sub-agents of ``hosts`` that ``current``'s event carries, by their Host Process.

    A tagged process the publisher did not probe, because a record named it
    only after the publisher read them, carries: that errs toward blocking
    Cleanup, and a scan stops listing it once the process is gone.
    """
    own = current.get("sessionProcess")
    starting = current.get("event") == "SessionStart"
    carried: dict[str, Any] = {}
    for agent, host in hosts.items():
        key = None if host is None else _process_key(host)
        if own is not None and host is not None and _same_process(host, own):
            carried[agent] = own
        elif key is not None:
            if key not in gone_hosts:
                carried[agent] = host
        elif not starting:
            # A process no record names, or names unreadably, is the
            # session's own as far as anything can tell.
            carried[agent] = None
    return carried


def _with_listing(
    record: Mapping[str, Any], hosts: Mapping[str, Any]
) -> dict[str, Any]:
    """``record`` listing the sub-agents of ``hosts``, each tagged with a process not its own.

    The tags are omitted where every listed sub-agent is the record's own,
    so a record of one Host Process keeps the shape it had before ADR 0107.
    """
    own = record.get("sessionProcess")
    tags = {
        agent: host
        for agent, host in sorted(hosts.items())
        if host is not None and not _same_process(host, own)
    }
    listed = {**record, "liveSubagents": sorted(hosts)}
    listed.pop("subagentProcesses", None)
    if tags:
        listed["subagentProcesses"] = tags
    return listed


def _is_ended(record: Mapping[str, Any]) -> bool:
    """Whether a record says its session ended, kept or about to be written."""
    state: Any = record.get("state")
    return isinstance(state, str) and state == "ended"


def _recorded_subagents(record: Mapping[str, Any]) -> list[str]:
    """The sub-agents a stored record lists as live; a malformed list lists none."""
    recorded: Any = record.get("liveSubagents")
    if not isinstance(recorded, list):
        return []
    return [str(item) for item in recorded if isinstance(item, str)]


def _retained_subagents(
    ending: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    seed: Mapping[str, Any] | None,
    gone_hosts: Collection[ProcessKey],
) -> dict[str, Any]:
    """The sub-agents a ``SessionEnd`` keeps listed in its ended record (ADR 0095).

    A session's end does not end the sub-agents it delegated to: a Codex
    thread the daemon unloads leaves its worker running. They stay listed
    until their ``SubagentStop``, or until the Host Process running them is
    gone, so only an end that names one keeps any: nothing else could ever
    clear them. They are those the session's records of that process list,
    with the process each runs in (ADR 0107). A record that names no Host
    Process is no evidence of another, so its sub-agents are the ending
    process's as far as anything can tell (ADR 0132).
    """
    if ending.get("sessionProcess") is None:
        return {}
    kept: dict[str, Any] = {}
    for record in (previous, seed):
        if record is not None and not _names_another_process(record, ending):
            kept.update(_carried_by_host(ending, subagent_hosts(record), gone_hosts))
    return kept


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


def session_start_kind(current: Mapping[str, Any]) -> SessionStartKind | None:
    """What a session's ``SessionStart`` says its Host Process did, by its ``source``.

    The one place a ``SessionStart``'s ``source`` is read: a compaction goes
    on with the session it names (ADR 0100), and a Conversation Switch moves
    its Host Process on from another session (ADR 0101). Any other source,
    no source, and a Sub-agent's event say neither.
    """
    if current.get("event") != "SessionStart" or is_child_record(current):
        return None
    source: Any = current.get("source")
    if source == COMPACTION_SOURCE:
        return "compaction"
    if isinstance(source, str) and source in CONVERSATION_SWITCH_SOURCES:
        return "switch"
    return None


def continues_turn(current: Mapping[str, Any], previous: Mapping[str, Any]) -> bool:
    """Whether a ``SessionStart`` goes on with the turn of the record it follows.

    A compaction's ``SessionStart`` names the live session and the Host
    Process its record names, and begins no turn: an automatic one runs
    inside a turn whose ``Stop`` follows, and a manual Claude Code
    ``/compact`` publishes neither a prompt nor a ``Stop``. No other
    ``SessionStart`` continues the turn: not a Sub-agent's, nor one that
    follows an ended record or a record of another or unnamed Host Process
    (ADR 0100).
    """
    return (
        session_start_kind(current) == "compaction"
        and previous.get("state") in LIVE_STATES
        and _same_named_process(current, previous)
    )


def switched_from(current: Mapping[str, Any], ended: Mapping[str, Any]) -> bool:
    """Whether a ``SessionStart`` switched its Host Process here from ``ended``'s session.

    Claude Code's ``/clear``, ``/resume`` and ``/branch`` end the session
    with a switch ``reason``, then start another session id in the same Host
    Process, and the sub-agents the first session left working go on under
    the second (ADR 0101). Both sides must say so: a Codex daemon's
    ``SessionStart`` ``clear`` follows no end, while a thread it unloads,
    whose worker stays its own, ends with ``reason`` ``other``. A process
    neither record names, another harness, or the same session is no switch.
    """
    reason: Any = ended.get("reason")
    # Typed as objects so the comparisons answer a bool, not Any.
    harness: object = current.get("harness")
    left_harness: object = ended.get("harness")
    session: object = current.get("sessionId")
    left_session: object = ended.get("sessionId")
    return (
        session_start_kind(current) == "switch"
        and _is_ended(ended)
        and isinstance(reason, str)
        and reason in CONVERSATION_SWITCH_REASONS
        and left_harness == harness
        and left_session != session
        and _same_named_process(current, ended)
    )


def carried_state(
    current: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> str:
    """The base state a record starts from before its sub-agents are reconciled.

    A Sub-agent's own events (its prompt, tool calls, or an end of its own)
    say nothing about its parent's turn, so the parent keeps the state its
    previous record held; only the sub-agent boundaries change it (ADR 0016).
    A child-scoped event never ends its parent. A session's own
    ``SessionStart`` begins no turn, so it waits (ADR 0106), save a
    compaction's. That keeps the main turn's state: running while the
    previous record's turn clock runs, and waiting otherwise. A compaction
    with no live record of its Host Process to follow reads running, as an
    automatic one inside a turn would (ADR 0100).
    """
    if previous is not None and continues_turn(current, previous):
        # The recorded state counts the sub-agents too; only the turn clock
        # says whether the main turn itself was in flight.
        in_turn = optional_string(previous.get("turnStartedAt")) is not None
        return "running" if in_turn else "waiting"
    if session_start_kind(current) == "compaction":
        return "running"
    if not is_child_record(current) or current.get("event") in SUBAGENT_EVENTS:
        return str(current.get("state"))
    # A parent record whose state cannot be read is taken as busy: its
    # Sub-agent is evidently at work.
    recorded = None if previous is None else previous.get("state")
    return str(recorded) if recorded in LIVE_STATES else "running"


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
    return _same_process(one.get("sessionProcess"), other.get("sessionProcess"))


def _same_process(first: object, second: object) -> bool:
    """Whether two raw ``sessionProcess`` values name the same Host Process."""
    if first is None or second is None:
        return first is None and second is None
    first_key, second_key = _process_key(first), _process_key(second)
    if first_key is None or second_key is None:
        return first == second
    return first_key == second_key


def _names_another_process(one: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    """Whether two hook records each name a Host Process, and not the same one.

    A record that names none, as a hook whose ancestry probe failed leaves,
    is no evidence of another process (ADR 0132).
    """
    return (
        one.get("sessionProcess") is not None
        and other.get("sessionProcess") is not None
        and not _same_host_process(one, other)
    )


def _ending_process(
    ending: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> dict[str, Any]:
    """``ending`` naming the Host Process ``previous`` names, when it names none itself.

    An end accepted beside a named process is that process's end, so an
    ended record it keeps for its sub-agents waits on that process rather
    than on one nothing can observe (ADR 0132).
    """
    if (
        previous is None
        or ending.get("sessionProcess") is not None
        or previous.get("sessionProcess") is None
    ):
        return dict(ending)
    named = dict(ending)
    for field in ("sessionProcess", "sessionProcessUnobservable"):
        named.pop(field, None)
        if field in previous:
            named[field] = previous[field]
    return named


def _same_named_process(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> bool:
    """Whether an event names a Host Process, and the one ``previous`` names.

    A session whose process cannot be named might have restarted unseen, so
    its sub-agents are never taken to have survived its ``SessionStart``.
    """
    return current.get("sessionProcess") is not None and _same_host_process(
        current, previous
    )


def _process_key(raw: object) -> ProcessKey | None:
    try:
        return SessionProcessRecord.model_validate(raw).identity.key
    except ValidationError:
        return None


@dataclass(frozen=True, slots=True)
class HookRecordWrite:
    """Where the store published one hook event, and the state it stored.

    ``state`` is the state the session's record was stored with, which may
    differ from the one the event maps to. It is ``ended`` when the event
    ended the session, whether its record was removed or kept for its
    sub-agents, and when a sub-agent's boundary changed or removed such a
    kept record (ADR 0095); None when the store kept nothing of the event.
    """

    path: Path
    state: ActiveState | None


def _stored_state(record: Mapping[str, Any]) -> ActiveState:
    """The state ``record`` names, refused unless a hook record may hold it."""
    return cast("ActiveState", _active_state(record.get("state")))


class HookRecordStore(LockedRecordStore):
    """Own the lifecycle of hook Agent Session records in one directory.

    Events are published atomically, a graceful ``SessionEnd`` removes the
    session's record, or keeps it ended for the sub-agents it still lists
    (ADR 0095), and confirmed stale records can be pruned without racing a
    concurrent hook write. A Project-local store names its
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
        self,
        record: dict[str, Any],
        *,
        seed: Mapping[str, Any] | None = None,
        adopted: Iterable[str] = (),
        gone_hosts: Collection[ProcessKey] = (),
    ) -> HookRecordWrite:
        """Publish one native identity without overwriting another harness.

        ``seed`` is the session's freshest record in another store, when the
        publisher found one: a session-scoped event of the same Host Process
        that moves the session's freshest record here derives its live
        sub-agents and turn clock from it rather than from an older record of
        this store, so a move never forgets a live Sub-agent (ADR 0067). A
        child-scoped event instead keeps this store's previous record's
        location, never ends it, and writes nothing but a sub-agent's start
        where there is no record. A ``SessionEnd`` older than the previous
        record, or naming another Host Process than it, keeps nothing; where
        only one of the two names a process, the end is that process's
        (ADR 0132). A ``SessionEnd`` whose session still lists
        live sub-agents keeps them in an ended record of its Host Process,
        which only their boundaries change and which a ``SessionStart`` of
        that process carries on (ADR 0095), as it carries a live record's
        (ADR 0097). ``adopted`` names the sub-agents a Conversation Switch's
        ``SessionStart`` takes over from the session its Host Process switched
        from (ADR 0101); the record lists them beside its own.
        ``gone_hosts`` are the Host Processes, other than the event's, that
        the publisher found gone among those running the sub-agents the
        session's records list: a sub-agent of one of them goes, and one of
        any other process stays listed, tagged with its process (ADR 0107). The
        result names the state the record was stored with, which a caller
        reports rather than the state the event maps to.
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
            if _is_ended(record) and not child:
                # Only another named Host Process, or a newer record, refuses
                # an end: a side that names none is no evidence (ADR 0132).
                if previous is not None and (
                    _names_another_process(previous, record)
                    or observed_instant(previous.get("lastActivityAt"))
                    > observed_instant(record.get("lastActivityAt"))
                ):
                    return HookRecordWrite(destination, None)
                ending = _ending_process(record, previous)
                retained = _retained_subagents(ending, previous, seed, gone_hosts)
                if retained:
                    self.replace(key, _with_listing(ending, retained))
                else:
                    destination.unlink(missing_ok=True)
                return HookRecordWrite(destination, "ended")
            ended_elsewhere: Mapping[str, Any] | None = None
            if (
                previous is not None
                and _is_ended(previous)
                and not _same_host_process(previous, record)
                and not (
                    child
                    and hosts_subagent(
                        previous,
                        str(record.get("agentId")),
                        record.get("sessionProcess"),
                    )
                )
            ):
                # An ended record another Host Process kept for its sub-agents
                # says nothing about this one's session (ADR 0095), save the
                # sub-agents it lists by the process each runs in: a child's
                # event of one this process runs is that agent's (ADR 0107).
                ended_elsewhere, previous = previous, None
            if child and previous is not None and _is_ended(previous):
                # Only the sub-agent boundaries change a retained record: none
                # of its sub-agents' events revives the ended session.
                hosts = _crossing_boundary(record, subagent_hosts(previous))
                remaining = _with_listing(previous, hosts)
                if not hosts:
                    destination.unlink(missing_ok=True)
                elif remaining != previous:
                    self.replace(key, remaining)
                else:
                    # The record is as it was: the store kept nothing.
                    return HookRecordWrite(destination, None)
                return HookRecordWrite(destination, "ended")
            if child and previous is None and record.get("event") != "SubagentStart":
                # With no parent record here, only a starting Sub-agent has
                # anything to say: it is live. Any other Sub-agent event would
                # invent a parent at the Sub-agent's location (ADR 0067), and
                # a stop has no live set to leave: one arriving after its
                # parent's SessionEnd would list the ended session as waiting
                # for as long as a shared Host Process lives.
                return HookRecordWrite(destination, None)
            current = dict(record)
            origin = previous
            if child and previous is not None:
                # A Sub-agent's event never places or routes its parent, nor
                # makes its record older: one stamped before its parent moved
                # here but written after would let the record left behind
                # read as the freshest again.
                for field in LOCATION_FIELDS:
                    current[field] = previous.get(field)
                recorded_at = optional_string(previous.get("lastActivityAt"))
                if observed_instant(recorded_at) > observed_instant(
                    optional_string(current.get("lastActivityAt"))
                ):
                    current["lastActivityAt"] = recorded_at
            elif (
                seed is not None
                # Another process's sub-agents and turn are not this one's. A
                # SessionStart seeds too, so a session that came back here
                # without a hook carries what it lists now (ADR 0097).
                and _same_named_process(current, seed)
                and observed_instant(optional_string(seed.get("lastActivityAt")))
                > observed_instant(
                    None
                    if previous is None
                    else optional_string(previous.get("lastActivityAt"))
                )
            ):
                origin = seed
            # A child-scoped event's origin is this store's previous record;
            # a compaction's state follows the record it carries from.
            current["state"] = carried_state(current, origin)
            hosts = _carried_subagents(current, origin, gone_hosts)
            ended = (
                previous
                if previous is not None and _is_ended(previous)
                else ended_elsewhere
            )
            if ended is not None:
                # The session goes on in the Host Process that kept its ended
                # record's sub-agents, which may still be working, even where
                # a fresher record elsewhere seeded this one; an ended record
                # of another process keeps those of a process still running
                # (ADR 0107).
                hosts = {
                    **_carried_by_host(current, subagent_hosts(ended), gone_hosts),
                    **hosts,
                }
            if not child:
                own = current.get("sessionProcess")
                hosts.update(dict.fromkeys(adopted, own))
            elif (
                previous is not None
                and previous.get("sessionProcess") is not None
                and not _same_host_process(previous, current)
            ):
                # A sub-agent another Host Process runs speaks for itself,
                # not for its session's process: the record keeps naming the
                # process its session's own events named (ADR 0107).
                for field in ("sessionProcess", "sessionProcessUnobservable"):
                    current.pop(field, None)
                    if field in previous:
                        current[field] = previous[field]
            current = _with_listing(current, hosts)
            current["turnStartedAt"] = turn_started_at(current, origin)
            started = last_session_start_at(current, previous)
            if started is not None:
                current["lastSessionStartAt"] = started
            current["state"] = observed_state(current)
            # Narrowed before the write, so a state no record may hold is
            # refused rather than stored.
            stored = _stored_state(current)
            self.replace(key, current)
            return HookRecordWrite(destination, stored)

    def release_subagents(
        self, key: str, agents: Iterable[str], by: Mapping[str, Any]
    ) -> bool:
        """Stop listing ``agents`` in the ended record ``key``, if ``by``'s Host Process kept it.

        A sub-agent an ended record keeps (ADR 0095) leaves it once it stops,
        whichever of its Host Process's sessions reports the stop, or once a
        Conversation Switch has listed it on the session that now runs it
        (ADR 0101). The record is re-read under its lock: a live record, one
        of another harness or Host Process, or one already rid of them, is
        left as it is, and an ended record left listing none goes. Returns
        whether the record changed.
        """
        return self._release(key, agents, by, "ended")

    def release_left_behind(
        self, key: str, agents: Iterable[str], by: Mapping[str, Any]
    ) -> bool:
        """Stop listing ``agents`` in the live record ``key`` ``by``'s session left.

        A session that moves to another Worktree carries its sub-agents to
        the record it moves to, and the record it left keeps listing them;
        once a sub-agent stops, that record lets it go too (ADR 0102). The
        record is re-read under its lock, and only one of ``by``'s own
        session, harness and Host Process that is not ended changes. Only its
        list changes: its state, turn clock and stamp stay, so it never reads
        as fresher than the record the session moved to, and it stays when
        it lists none. Returns whether the record changed.
        """
        return self._release(key, agents, by, "left-behind")

    def _release(
        self,
        key: str,
        agents: Iterable[str],
        by: Mapping[str, Any],
        kind: ReleasedRecord,
    ) -> bool:
        """Remove ``agents`` from record ``key`` under its lock, if it is ``kind``.

        An ``ended`` record may be any session's, and goes once it lists
        none; a ``left-behind`` record is a live one of ``by``'s own session,
        and stays. Either names ``by``'s harness, and only the agents it
        lists as run by ``by``'s Host Process leave it: those of a record
        naming that process, and those tagged with it (ADR 0107).
        """
        released = set(agents)
        destination = self.record_path(key)
        with self.locked(key):
            try:
                previous = self._read(destination)
            except (HookRecordError, ValueError):
                return False
            if previous is None:
                return False
            if kind == "ended":
                eligible = _is_ended(previous)
            else:
                same_session = previous.get("sessionId") == by.get("sessionId")
                eligible = not _is_ended(previous) and same_session
            if not eligible or previous.get("harness") != by.get("harness"):
                return False
            hosts = subagent_hosts(previous)
            leaving = set(subagents_hosted_by(previous, by.get("sessionProcess")))
            remaining = {
                agent: host
                for agent, host in hosts.items()
                if agent not in released or agent not in leaving
            }
            if remaining.keys() == hosts.keys():
                return False
            if not remaining and kind == "ended":
                destination.unlink(missing_ok=True)
            elif "subagentProcesses" in previous:
                self.replace(key, _with_listing(previous, remaining))
            else:
                # A record of one Host Process changes only its list.
                listed = _recorded_subagents(previous)
                self.replace(
                    key,
                    {
                        **previous,
                        "liveSubagents": [
                            agent for agent in listed if agent in remaining
                        ],
                    },
                )
            return True

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
