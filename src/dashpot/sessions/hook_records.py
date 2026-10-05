"""Store hook Agent Session records."""

from __future__ import annotations

import json
import os
from collections.abc import Collection, Iterable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

from pydantic import AfterValidator, BeforeValidator, Field, ValidationError

from ..core.git import Git, GitError
from ..core.json_records import HookRecordError, require_string
from ..core.model import Harness
from ..core.pydantic import NonEmptyString, PersistedRecord, validate_degrading
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


def _path_text(value: str | None) -> str | None:
    # No operating system path holds a NUL, and resolving one raises.
    if value is not None and "\0" in value:
        raise ValueError("must be a path without a NUL character")
    return value


def _readable_hosts(value: object) -> object:
    # Each sub-agent's Host Process is read alone: one named unreadably is
    # unknown (None), and never makes its siblings' the record's own.
    if not isinstance(value, dict):
        return value
    return {agent: _session_process(host) for agent, host in value.items()}


# The validator ahead of the union keeps the record's refusal naming the state.
ActiveStateName = Annotated[ActiveState, BeforeValidator(_active_state)]
OptionalText = Annotated[str | None, AfterValidator(_blank_to_none)]
PathText = Annotated[NonEmptyString, AfterValidator(_path_text)]
OptionalPathText = Annotated[OptionalText, AfterValidator(_path_text)]


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
    cwd: PathText
    repository_root: OptionalPathText = None
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
    # One whose entry is malformed maps to None: its Host Process is unknown.
    subagent_processes: Annotated[
        dict[str, SessionProcessRecord | None], BeforeValidator(_readable_hosts)
    ] = Field(default_factory=dict)
    # When this store last saw the session begin an incarnation (its latest
    # ``SessionStart``), so a live move can be told from a restart (ADR
    # 0067); absent on a record written before it was kept, or by a store
    # that has seen none.
    last_session_start_at: OptionalText = None

    @property
    def unreadable_subagent_hosts(self) -> list[str]:
        """The sub-agents whose recorded Host Process is malformed, so unknown."""
        return sorted(
            agent for agent, host in self.subagent_processes.items() if host is None
        )

    @property
    def has_global_binding(self) -> bool:
        # Retired records bound an Issue in the hook record itself; the Work
        # Store is the sole authority now, so the fields are only detected.
        extra = self.model_extra or {}
        return (
            extra.get("issueId") is not None
            or extra.get("issueReferenceHint") is not None
        )

    @property
    def delegate(self) -> str | None:
        """The Sub-agent whose event this record was published for, if any."""
        return delegate_id(self.agent_id)

    @property
    def worktree(self) -> Path:
        """The Worktree the record places its session at: its root, else its cwd."""
        return Path(self.repository_root or self.cwd)

    @property
    def process_key(self) -> ProcessKey | None:
        """The key of the Host Process the record names, if it names one."""
        process = self.session_process
        return None if process is None else process.identity.key

    @property
    def ended(self) -> bool:
        """Whether the record says its session ended, kept or about to be written."""
        return self.state == "ended"


# A harness that is present but unsupported is fatal too: defaulting it to
# codex would report another harness's session as a Codex one.
HOOK_RECORD_FATAL = frozenset({"version", "sessionId", "harness", "state", "cwd"})


def read_stored_record(raw: Mapping[str, Any]) -> HookRecord:
    """A stored hook record as a ``HookRecord``, read as a scan reads it.

    A malformed non-fatal field falls back to its default; a malformed fatal
    one raises ``ValueError`` (a ``ValidationError``).
    """
    record, _degraded = validate_degrading(HookRecord, raw, fatal=HOOK_RECORD_FATAL)
    return record


def build_hook_record(
    event: dict[str, Any],
    process: ProcessIdentity | None = None,
    harness: Harness = "codex",
    process_unobservable: str | None = None,
) -> HookRecord:
    """The hook record one harness event publishes, before the store derives its rest.

    ``turnStartedAt``, ``liveSubagents``, ``subagentProcesses`` and
    ``lastSessionStartAt`` are the store's to derive against the previous
    record, so they are left at their defaults here.
    """
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
    return HookRecord(
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


def stored_document(record: HookRecord) -> dict[str, Any]:
    """The JSON object a store writes for ``record``, fields a newer Dashpot wrote included.

    ``subagentProcesses`` is left out while no listed sub-agent runs in
    another process, so a record of one Host Process keeps the shape it had
    before ADR 0107, and ``lastSessionStartAt`` while the store has seen no
    ``SessionStart``.
    """
    omitted: set[str] = set()
    if not record.subagent_processes:
        omitted.add("subagent_processes")
    if record.last_session_start_at is None:
        omitted.add("last_session_start_at")
    return record.model_dump(mode="json", by_alias=True, exclude=omitted)


def is_child_record(record: HookRecord) -> bool:
    """Whether a hook record was published for a Sub-agent's event, not its session's."""
    return record.delegate is not None


# Each listed sub-agent with the Host Process recorded as running it. None is
# a process no record names, or names unreadably: the publisher takes that
# sub-agent to be its session's own, as far as anything can tell, so it is
# written untagged and goes with the session's own process. That differs on
# purpose from a scan, which reads an unreadable tag as a process not proved
# gone (ADR 0107): the store writes no tag it cannot read back (ADR 0134).
SubagentHosts = dict[str, SessionProcessRecord | None]


def turn_started_at(current: HookRecord, previous: HookRecord | None) -> str | None:
    """When the running turn began: carried while running, cleared once not.

    A turn's age and a session's idle time are different questions, so the
    record keeps the turn's start rather than overloading its last activity.
    """
    if current.event in SUBAGENT_EVENTS or is_child_record(current):
        # A sub-agent's event is not the main turn's: its clock carries.
        return None if previous is None else previous.turn_started_at
    if current.state != "running":
        return None
    if (
        previous is not None
        and previous.state == "running"
        and previous.turn_started_at is not None
    ):
        return previous.turn_started_at
    return current.last_activity_at


def _carried_subagents(
    current: HookRecord,
    previous: HookRecord | None,
    gone_hosts: Collection[ProcessKey],
) -> SubagentHosts:
    """Each sub-agent of the session alive after this event, with its Host Process.

    A sub-agent belongs to the Host Process that runs it, which a session's
    resumption in another process does not end (ADR 0107). One the event's
    own process runs carries as the record's own; one another named process
    runs carries, tagged with that process, unless the publisher found that
    process among ``gone_hosts``. One whose process no record names carries
    unless the event is a ``SessionStart``: a session whose process cannot be
    named might have restarted unseen (ADR 0097). A starting sub-agent's
    process is the event's.
    """
    hosts = (
        {}
        if previous is None
        else _carried_by_host(current, subagent_hosts(previous), gone_hosts)
    )
    return _crossing_boundary(current, hosts)


def _crossing_boundary(current: HookRecord, hosts: SubagentHosts) -> SubagentHosts:
    """``hosts`` after ``current``'s sub-agent boundary, if it is one.

    ``SubagentStart`` adds the agent, run by the event's Host Process, and
    ``SubagentStop`` removes it; an event that names no agent changes
    nothing rather than guessing.
    """
    agent = current.delegate
    if agent is None:
        return hosts
    if current.event == "SubagentStart":
        hosts[agent] = current.session_process
    elif current.event == "SubagentStop":
        hosts.pop(agent, None)
    return hosts


def subagent_hosts(record: HookRecord) -> SubagentHosts:
    """Each sub-agent a stored record lists, with the Host Process recorded as running it.

    That is the agent's own entry in ``subagentProcesses``, else the
    record's ``sessionProcess`` (ADR 0107).
    """
    own = record.session_process
    return {
        agent: record.subagent_processes.get(agent, own)
        for agent in record.live_subagents
    }


def hosts_subagent(
    record: HookRecord, agent: str, process: SessionProcessRecord | None
) -> bool:
    """Whether ``record`` lists ``agent`` as run by the Host Process ``process``."""
    return agent in subagents_hosted_by(record, process)


def subagents_hosted_by(
    record: HookRecord, process: SessionProcessRecord | None
) -> list[str]:
    """The sub-agents ``record`` lists as run by the Host Process ``process``."""
    if process is None:
        return []
    return sorted(
        agent
        for agent, host in subagent_hosts(record).items()
        if _same_process(host, process)
    )


def subagent_host_processes(
    record: HookRecord,
) -> dict[ProcessKey, SessionProcessRecord]:
    """The Host Processes ``record`` names for its listed sub-agents, by key.

    One named unreadably, such as by a PID no process can have, is left out.
    """
    return {
        host.identity.key: host
        for host in subagent_hosts(record).values()
        if host is not None
    }


def _carried_by_host(
    current: HookRecord,
    hosts: SubagentHosts,
    gone_hosts: Collection[ProcessKey],
) -> SubagentHosts:
    """The sub-agents of ``hosts`` that ``current``'s event carries, by their Host Process.

    A tagged process the publisher did not probe, because a record named it
    only after the publisher read them, carries: that errs toward blocking
    Cleanup, and a scan stops listing it once the process is gone.
    """
    own = current.session_process
    starting = current.event == "SessionStart"
    carried: SubagentHosts = {}
    for agent, host in hosts.items():
        if own is not None and host is not None and _same_process(host, own):
            carried[agent] = own
        elif host is not None:
            if host.identity.key not in gone_hosts:
                carried[agent] = host
        elif not starting:
            # A process no record names, or names unreadably, is the
            # session's own as far as anything can tell.
            carried[agent] = None
    return carried


def _with_listing(record: HookRecord, hosts: SubagentHosts) -> HookRecord:
    """``record`` listing the sub-agents of ``hosts``, each tagged with a process not its own.

    The tags are omitted where every listed sub-agent is the record's own,
    so a record of one Host Process keeps the shape it had before ADR 0107.
    """
    own = record.session_process
    tags = {
        agent: host
        for agent, host in sorted(hosts.items())
        if host is not None and not _same_process(host, own)
    }
    return record.model_copy(
        update={"live_subagents": sorted(hosts), "subagent_processes": tags}
    )


def _retained_subagents(
    ending: HookRecord,
    previous: HookRecord | None,
    seed: HookRecord | None,
    gone_hosts: Collection[ProcessKey],
) -> SubagentHosts:
    """The sub-agents a ``SessionEnd`` keeps listed in its ended record (ADR 0095).

    A session's end does not end the sub-agents it delegated to: a Codex
    thread the daemon unloads leaves its worker running. They stay listed
    until their ``SubagentStop``, or until the Host Process running them is
    gone, so only an end that names one keeps any: nothing else could ever
    clear them. They are those the session's records of that process list,
    with the process each runs in (ADR 0107). The previous record that the
    end was accepted beside is the ending process's even when it names no
    Host Process, since nothing says another runs the session (ADR 0132).
    """
    if ending.session_process is None:
        return {}
    kept: SubagentHosts = {}
    if previous is not None and not names_another_process(previous, ending):
        kept.update(_carried_by_host(ending, subagent_hosts(previous), gone_hosts))
    if seed is not None and _same_host_process(seed, ending):
        kept.update(_carried_by_host(ending, subagent_hosts(seed), gone_hosts))
    return kept


def last_session_start_at(
    current: HookRecord, previous: HookRecord | None
) -> str | None:
    """When this store last saw the session begin an incarnation.

    Set by the session's own ``SessionStart`` and carried, like the turn
    clock, from the same store's previous record of the identity.
    """
    if current.event == "SessionStart" and not is_child_record(current):
        return current.last_activity_at
    return None if previous is None else previous.last_session_start_at


def session_start_kind(current: HookRecord) -> SessionStartKind | None:
    """What a session's ``SessionStart`` says its Host Process did, by its ``source``.

    The one place a ``SessionStart``'s ``source`` is read: a compaction goes
    on with the session it names (ADR 0100), and a Conversation Switch moves
    its Host Process on from another session (ADR 0101). Any other source,
    no source, and a Sub-agent's event say neither.
    """
    if current.event != "SessionStart" or is_child_record(current):
        return None
    source: object = current.source
    if source == COMPACTION_SOURCE:
        return "compaction"
    if isinstance(source, str) and source in CONVERSATION_SWITCH_SOURCES:
        return "switch"
    return None


def continues_turn(current: HookRecord, previous: HookRecord) -> bool:
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
        and previous.state in LIVE_STATES
        and _same_named_process(current, previous)
    )


def switched_from(current: HookRecord, ended: HookRecord) -> bool:
    """Whether a ``SessionStart`` switched its Host Process here from ``ended``'s session.

    Claude Code's ``/clear``, ``/resume`` and ``/branch`` end the session
    with a switch ``reason``, then start another session id in the same Host
    Process, and the sub-agents the first session left working go on under
    the second (ADR 0101). Both sides must say so: a Codex daemon's
    ``SessionStart`` ``clear`` follows no end, while a thread it unloads,
    whose worker stays its own, ends with ``reason`` ``other``. A process
    neither record names, another harness, or the same session is no switch.
    """
    reason: object = ended.reason
    return (
        session_start_kind(current) == "switch"
        and ended.ended
        and isinstance(reason, str)
        and reason in CONVERSATION_SWITCH_REASONS
        and ended.harness == current.harness
        and ended.session_id != current.session_id
        and _same_named_process(current, ended)
    )


def carried_state(current: HookRecord, previous: HookRecord | None) -> ActiveState:
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
        return "running" if previous.turn_started_at is not None else "waiting"
    if session_start_kind(current) == "compaction":
        return "running"
    if not is_child_record(current) or current.event in SUBAGENT_EVENTS:
        return current.state
    # A parent record whose state cannot be read is taken as busy: its
    # Sub-agent is evidently at work.
    recorded = None if previous is None else previous.state
    return recorded if recorded is not None and recorded in LIVE_STATES else "running"


def observed_state(current: HookRecord) -> ActiveState:
    """The session's state once its live sub-agents are accounted for.

    A main turn that stops while a sub-agent it delegated to is still working
    leaves the session running; a sub-agent stopping while the main turn is
    still in flight leaves it running too.
    """
    if current.state == "waiting" and current.live_subagents:
        return "running"
    if current.event == "SubagentStop" and current.turn_started_at:
        return "running"
    return current.state


def _same_host_process(one: HookRecord, other: HookRecord) -> bool:
    """Whether two hook records name the same Host Process: its pid and start time.

    The parent and the argument vector are what a process was observed with,
    not its identity (ADR 0067): a Codex daemon that a terminal autostarted
    is reparented when that terminal exits and still serves the same
    sessions. Two records without a process match, as do two whose process
    cannot be read; a process on one side only never matches.
    """
    return _same_process(one.session_process, other.session_process)


def _same_process(
    first: SessionProcessRecord | None, second: SessionProcessRecord | None
) -> bool:
    """Whether two recorded Host Processes are the same one, or both unnamed."""
    if first is None or second is None:
        return first is None and second is None
    return first.identity.key == second.identity.key


def names_another_process(one: HookRecord, other: HookRecord) -> bool:
    """Whether two hook records each name a Host Process, and not the same one.

    A record that names none, as a hook whose ancestry probe failed leaves,
    is no evidence of another process (ADR 0132).
    """
    return (
        one.session_process is not None
        and other.session_process is not None
        and not _same_host_process(one, other)
    )


def _speaking_for(record: HookRecord, previous: HookRecord) -> HookRecord:
    """``record`` naming the Host Process ``previous`` names, and its observability."""
    return record.model_copy(
        update={
            "session_process": previous.session_process,
            "session_process_unobservable": previous.session_process_unobservable,
        }
    )


def _ending_record(ending: HookRecord, previous: HookRecord | None) -> HookRecord:
    """``ending`` naming the Host Process ``previous`` names, when it names none itself.

    An end accepted beside a named process is that process's end, so an
    ended record it keeps for its sub-agents waits on that process rather
    than on one nothing can observe (ADR 0132).
    """
    if (
        previous is None
        or ending.session_process is not None
        or previous.session_process is None
    ):
        return ending
    return _speaking_for(ending, previous)


def _same_named_process(current: HookRecord, previous: HookRecord) -> bool:
    """Whether an event names a Host Process, and the one ``previous`` names.

    A session whose process cannot be named might have restarted unseen, so
    its sub-agents are never taken to have survived its ``SessionStart``.
    """
    return current.session_process is not None and _same_host_process(current, previous)


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


class HookRecordStore(LockedRecordStore):
    """Own the lifecycle of hook Agent Session records in one directory.

    Events are published atomically, a graceful ``SessionEnd`` removes the
    session's record, or keeps it ended for the sub-agents it still lists
    (ADR 0095), and confirmed stale records can be pruned without racing a
    concurrent hook write. A Project-local store names its
    ``checkout`` (see ``project_session_store``). Every record is derived as
    a ``HookRecord`` and becomes its stored JSON object only when written.
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
        record: HookRecord,
        *,
        seed: HookRecord | None = None,
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
        where there is no record. A ``SessionEnd`` keeps nothing when the
        previous record is newer, or names a different Host Process from the
        one the end names. Where only one of the two names a process, as when
        a hook's ancestry probe failed, the end is accepted as that process's
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
        reports rather than the state the event maps to. A previous record
        whose identity this store cannot read is no evidence, and the event
        replaces it.
        """
        session_id, harness = record.session_id, record.harness
        # The store keeps what a harness published; a record naming an
        # unsupported harness is refused by the read model, as a diagnostic.
        native_key = (harness, session_id)
        scoped_key = session_storage_key(harness, session_id)
        with self.locked_identity(session_id, harness):
            scoped = self._read(self.record_path(scoped_key))
            legacy = self._read(self.record_path(session_id))
            if scoped is not None:
                key, stored = scoped_key, scoped
            elif (
                legacy is None
                or (legacy.get("harness"), legacy.get("sessionId")) == native_key
            ):
                key, stored = session_id, legacy
            else:
                key, stored = scoped_key, None
            if (
                stored is not None
                and (stored.get("harness"), stored.get("sessionId")) != native_key
            ):
                raise ValueError(
                    "hook destination is occupied by another Agent Session Identity"
                )
            previous = _readable(stored)
            destination = self.record_path(key)
            child = is_child_record(record)
            if record.ended and not child:
                # Only another named Host Process, or a newer record, refuses
                # an end: a side that names none is no evidence (ADR 0132).
                if previous is not None and (
                    names_another_process(previous, record)
                    or observed_instant(previous.last_activity_at)
                    > observed_instant(record.last_activity_at)
                ):
                    return HookRecordWrite(destination, None)
                ending = _ending_record(record, previous)
                retained = _retained_subagents(ending, previous, seed, gone_hosts)
                if retained:
                    self._replace(key, _with_listing(ending, retained))
                else:
                    destination.unlink(missing_ok=True)
                return HookRecordWrite(destination, "ended")
            ended_elsewhere: HookRecord | None = None
            if (
                previous is not None
                and previous.ended
                and not _same_host_process(previous, record)
                and not (
                    record.delegate is not None
                    and hosts_subagent(
                        previous, record.delegate, record.session_process
                    )
                )
            ):
                # An ended record another Host Process kept for its sub-agents
                # says nothing about this one's session (ADR 0095), save the
                # sub-agents it lists by the process each runs in: a child's
                # event of one this process runs is that agent's (ADR 0107).
                ended_elsewhere, previous = previous, None
            if child and previous is not None and previous.ended:
                # Only the sub-agent boundaries change a retained record: none
                # of its sub-agents' events revives the ended session.
                hosts = _crossing_boundary(record, subagent_hosts(previous))
                remaining = _with_listing(previous, hosts)
                if not hosts:
                    destination.unlink(missing_ok=True)
                elif remaining != previous:
                    self._replace(key, remaining)
                else:
                    # The record is as it was: the store kept nothing.
                    return HookRecordWrite(destination, None)
                return HookRecordWrite(destination, "ended")
            if child and previous is None and record.event != "SubagentStart":
                # With no parent record here, only a starting Sub-agent has
                # anything to say: it is live. Any other Sub-agent event would
                # invent a parent at the Sub-agent's location (ADR 0067), and
                # a stop has no live set to leave: one arriving after its
                # parent's SessionEnd would list the ended session as waiting
                # for as long as a shared Host Process lives.
                return HookRecordWrite(destination, None)
            current = record
            origin = previous
            if child and previous is not None:
                # A Sub-agent's event never places or routes its parent, nor
                # makes its record older: one stamped before its parent moved
                # here but written after would let the record left behind
                # read as the freshest again.
                current = current.model_copy(
                    update={
                        "cwd": previous.cwd,
                        "repository_root": previous.repository_root,
                        "branch": previous.branch,
                        "last_activity_at": max(
                            current.last_activity_at,
                            previous.last_activity_at,
                            key=observed_instant,
                        ),
                    }
                )
            elif (
                seed is not None
                # Another process's sub-agents and turn are not this one's. A
                # SessionStart seeds too, so a session that came back here
                # without a hook carries what it lists now (ADR 0097).
                and _same_named_process(current, seed)
                and observed_instant(seed.last_activity_at)
                > observed_instant(
                    None if previous is None else previous.last_activity_at
                )
            ):
                origin = seed
            # A child-scoped event's origin is this store's previous record;
            # a compaction's state follows the record it carries from.
            current = current.model_copy(
                update={"state": carried_state(current, origin)}
            )
            hosts = _carried_subagents(current, origin, gone_hosts)
            ended = (
                previous if previous is not None and previous.ended else ended_elsewhere
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
                hosts.update(dict.fromkeys(adopted, current.session_process))
            elif (
                previous is not None
                and previous.session_process is not None
                and not _same_host_process(previous, current)
            ):
                # A sub-agent another Host Process runs speaks for itself,
                # not for its session's process: the record keeps naming the
                # process its session's own events named (ADR 0107).
                current = _speaking_for(current, previous)
            current = _with_listing(current, hosts)
            current = current.model_copy(
                update={
                    "turn_started_at": turn_started_at(current, origin),
                    "last_session_start_at": last_session_start_at(current, previous),
                }
            )
            current = current.model_copy(update={"state": observed_state(current)})
            self._replace(key, current)
            return HookRecordWrite(destination, current.state)

    @contextmanager
    def locked_identity(
        self, session_id: str, harness: str, *, create: bool = True
    ) -> Iterator[bool]:
        """Hold both record locks of one Agent Session Identity, in sorted key order.

        A record of the identity is named by its plain session id or by its
        harness-scoped key, and a writer may move it from one to the other,
        so every path that reads a record of the identity, decides, and
        writes or removes it takes both locks, and none can act on a record
        another has just changed. Yields whether the locks are held: a
        conditional change (``create`` false) never creates the store's
        directory, and finds nothing to change where it is gone.
        """
        keys = sorted(set(_identity_keys(session_id, harness)))
        with ExitStack() as stack:
            for key in keys:
                if not stack.enter_context(self.locked(key, create=create)):
                    yield False
                    return
            yield True

    def release_subagents(
        self,
        key: str,
        agents: Iterable[str],
        by: HookRecord,
        *,
        session_id: str,
    ) -> bool:
        """Stop listing ``agents`` in the ended record ``key``, if ``by``'s Host Process kept it.

        A sub-agent an ended record keeps (ADR 0095) leaves it once it stops,
        whichever of its Host Process's sessions reports the stop, or once a
        Conversation Switch has listed it on the session that now runs it
        (ADR 0101). The record is re-read under its lock: a live record, one
        of another harness or Host Process, or one already rid of them, is
        left as it is, and an ended record left listing none goes. Returns
        whether the record changed. ``session_id`` is the session whose
        record ``key`` names, which may be another session of ``by``'s Host
        Process.
        """
        return self._release(key, agents, by, "ended", session_id)

    def release_left_behind(
        self, key: str, agents: Iterable[str], by: HookRecord
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
        return self._release(key, agents, by, "left-behind", by.session_id)

    def _release(
        self,
        key: str,
        agents: Iterable[str],
        by: HookRecord,
        kind: ReleasedRecord,
        session_id: str,
    ) -> bool:
        """Remove ``agents`` from record ``key`` under its identity's locks, if it is ``kind``.

        An ``ended`` record may be any session's, and goes once it lists
        none; a ``left-behind`` record is a live one of ``by``'s own session,
        and stays. Either names ``by``'s harness, and only the agents it
        lists as run by ``by``'s Host Process leave it: those of a record
        naming that process, and those tagged with it (ADR 0107). ``key``
        must be one of the names of ``session_id``'s record of that harness,
        so the locks taken are those every other writer of it takes. A
        record this store cannot read is left as it is.
        """
        released = set(agents)
        destination = self.record_path(key)
        if key not in _identity_keys(session_id, by.harness):
            return False
        with self.locked_identity(session_id, by.harness, create=False) as held:
            if not held:
                return False
            try:
                previous = _readable(self._read(destination))
            except (HookRecordError, ValueError):
                return False
            if previous is None:
                return False
            if kind == "ended":
                eligible = previous.ended
            else:
                eligible = not previous.ended and previous.session_id == by.session_id
            if not eligible or previous.harness != by.harness:
                return False
            hosts = subagent_hosts(previous)
            leaving = set(subagents_hosted_by(previous, by.session_process))
            remaining = {
                agent: host
                for agent, host in hosts.items()
                if agent not in released or agent not in leaving
            }
            if remaining.keys() == hosts.keys():
                return False
            if not remaining and kind == "ended":
                destination.unlink(missing_ok=True)
            elif previous.subagent_processes:
                self._replace(key, _with_listing(previous, remaining))
            else:
                # A record of one Host Process changes only its list.
                self._replace(
                    key,
                    previous.model_copy(
                        update={
                            "live_subagents": [
                                agent
                                for agent in previous.live_subagents
                                if agent in remaining
                            ]
                        }
                    ),
                )
            return True

    def prune(self, key: str, observed: Mapping[str, Any]) -> bool:
        """Delete the stale record ``key`` only if it still equals ``observed``.

        The conditional re-read under the identity's locks means a record that
        a hook updated between observation and cleanup is kept, and a prune
        never creates the store's directory: a store a Cleanup removed has
        nothing to prune. The comparison is of the stored JSON objects, not
        of their models, which cannot tell an absent field from a null one
        (ADR 0013). The lock files are left for ``prune_lock`` to reclaim on
        a later pass. Returns whether the record was removed.
        """
        destination = self.record_path(key)
        # A record without a harness is a Codex one, as ``HookRecord`` reads it.
        session_id = observed.get("sessionId")
        harness = observed.get("harness", "codex")
        if (
            not isinstance(session_id, str)
            or not isinstance(harness, str)
            or key not in _identity_keys(session_id, harness)
        ):
            return False
        with self.locked_identity(session_id, harness, create=False) as held:
            if not held:
                return False
            try:
                current = self._read(destination)
            except (HookRecordError, ValueError):
                return False
            if current is None or current != dict(observed):
                return False
            destination.unlink(missing_ok=True)
            return True

    def _replace(self, key: str, record: HookRecord) -> None:
        """Write ``record`` as the key's stored JSON object."""
        self.replace(key, stored_document(record))

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            raw: Any = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            raise HookRecordError(f"hook record is not an object: {path}")
        return raw


def _session_process(raw: object) -> SessionProcessRecord | None:
    """A raw ``sessionProcess`` value as a record, or ``None`` if malformed."""
    try:
        return SessionProcessRecord.model_validate(raw)
    except ValidationError:
        return None


def _readable(stored: Mapping[str, Any] | None) -> HookRecord | None:
    """A stored record as a ``HookRecord``, or None where there is none it can read."""
    if stored is None:
        return None
    try:
        return read_stored_record(stored)
    except ValueError:
        return None


def _identity_keys(session_id: str, harness: str) -> tuple[str, str]:
    """The two keys a record of one Agent Session Identity may be stored under."""
    return session_id, session_storage_key(harness, session_id)


def session_directory(worktree: Path) -> Path:
    """The Project-local session record store beneath one Worktree."""
    return project_state_directory(worktree) / "sessions"


def project_session_store(worktree: Path) -> HookRecordStore:
    """The Project-local hook store of one Worktree, whose writes keep it out of Git."""
    return HookRecordStore(session_directory(worktree), checkout=worktree)
