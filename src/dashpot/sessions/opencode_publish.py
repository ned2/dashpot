"""Translate an OpenCode plugin publication into the shared hook record rules.

Dashpot's OpenCode plugin reports OpenCode v2's own session events, each
with its durable sequence, and its own registration and last cleanup; this
module decides what they mean (ADR 0090):

- a root session's creation or fork starts its record, an execution's start
  is a running turn and its end, however it ended, a waiting one; a move is
  its designated location evidence, and its deletion its end;
- a child session, one with a native parent, is a Sub-agent of its root:
  only its executions and its deletion change the root's live Sub-agents,
  and it is never an Agent Session of its own (ADR 0016, ADR 0067);
- a root's publication begins an incarnation, writing ``SessionStart`` first,
  where its hook store holds no record of the session or one that names
  another Host Process; a move does only in the store of another Project it
  takes the session to, which takes over the session's Sub-agents from the
  store it left (ADR 0109).

A publication is written to the hook store of the Worktree holding its root
session's OpenCode location, under that store's Publisher Record lock, so
the sequence check, the hook record writes and the record's update are one
ordered step. A location outside every Project is not published. The hook
record and Work Store are reached through ``publish_hook_event``, which owns
their rules, save for the marker a Host Process's last cleanup leaves on its
running sessions and the Sub-agents a later publication forgets with it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, ValidationError, model_validator

from ..core.git import Git, GitError
from ..core.pydantic import NonEmptyString, PublishedModel
from ..core.state_paths import ensure_state_directory, is_configured_checkout
from ..core.worktree_paths import repository_worktrees, same_path
from .harnesses import HookSessionIdentity
from .hook_publish import HookPublication, publish_hook_event
from .hook_records import HookRecord, HookRecordStore, session_directory
from .hook_scan import stored_session_records
from .opencode_publishers import (
    NO_LIVE_INSTANCE,
    PUBLISHER_KEY,
    PublisherGeneration,
    PublisherStore,
    SessionEntry,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .session_matching import session_storage_key

PLUGIN_PROTOCOL = 2
RequestKind = Literal["register", "event", "gone", "unobserved"]
EventType = Literal[
    "session.created",
    "session.forked",
    "session.execution.started",
    "session.execution.succeeded",
    "session.execution.failed",
    "session.execution.interrupted",
    "session.moved",
    "session.deleted",
]
AcknowledgmentResult = Literal["accepted", "stale", "refused", "rejected"]
# OpenCode's own reason words, such as an interruption's ``inactivity``.
NativeReason = str
# What each OpenCode event is written as on a root session, and on the root
# of a child session; ``None`` writes nothing.
TRANSLATION: dict[EventType, tuple[str | None, str | None]] = {
    "session.created": ("SessionStart", None),
    "session.forked": ("SessionStart", None),
    "session.execution.started": ("UserPromptSubmit", "SubagentStart"),
    "session.execution.succeeded": ("Stop", "SubagentStop"),
    "session.execution.failed": ("Stop", "SubagentStop"),
    "session.execution.interrupted": ("Stop", "SubagentStop"),
    "session.moved": ("SessionMoved", None),
    "session.deleted": ("SessionEnd", "SubagentStop"),
}
# The Host Processes' registrations recover at most this many sessions.
RECOVERY_LIMIT = 64


class PluginSession(PublishedModel):
    """One OpenCode session a publication is about, as the plugin placed it.

    ``location`` is the OpenCode location of its root session, which routes
    the publication; a move's is the location it left.
    """

    model_config = ConfigDict(extra="forbid")

    id: HookSessionIdentity
    root: HookSessionIdentity
    location: NonEmptyString


class PluginEvent(PublishedModel):
    """One OpenCode session event: its id, type and the session's durable sequence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: EventType
    sequence: int = Field(ge=0)
    reason: NativeReason | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$"
    )
    # Where a move took its session.
    to: NonEmptyString | None = None


class PluginRequest(PublishedModel):
    """One request from Dashpot's OpenCode plugin to its helper."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal[2]
    kind: RequestKind
    generation: PublisherGeneration
    pid: int = Field(gt=0)
    deadline_ms: int = Field(gt=0)
    location: NonEmptyString | None = None
    locations: list[NonEmptyString] = Field(default_factory=list, max_length=256)
    session: PluginSession | None = None
    event: PluginEvent | None = None

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if self.kind == "register" and self.location is None:
            raise ValueError("a registration names its instance's location")
        if self.kind in {"event", "gone"} and self.session is None:
            raise ValueError(f"a {self.kind} publication names its session")
        if (self.kind == "event") != (self.event is not None):
            raise ValueError("only an event publication carries an event")
        if self.event is not None and (self.event.type == "session.moved") != (
            self.event.to is not None
        ):
            raise ValueError("only a move names where it took its session")
        return self


def parse_request(raw: str) -> PluginRequest:
    """Validate one plugin request, raising ``ValueError`` with its wire path."""
    try:
        return PluginRequest.model_validate_json(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"])
        raise ValueError(f"OpenCode plugin request: {where}: {error['msg']}") from exc


class RecoveredSession(PublishedModel):
    """A root session recorded on the registering Host Process, with its Sub-agents."""

    id: HookSessionIdentity
    subagents: list[HookSessionIdentity] = Field(default_factory=list)


class PluginAcknowledgment(PublishedModel):
    """The helper's answer to one plugin request: the line it prints on stdout."""

    result: AcknowledgmentResult
    reason: str | None = None
    sessions: list[RecoveredSession] | None = None

    def wire(self) -> str:
        """The acknowledgment as the plugin reads it: only the fields it was given."""
        return self.model_dump_json(by_alias=True, exclude_unset=True)


@dataclass(frozen=True, slots=True)
class OpenCodeOutcome:
    """What one plugin request did: its acknowledgment and hook publications.

    ``written`` names the shared hook events in the order they were written.
    """

    acknowledgment: PluginAcknowledgment
    publications: tuple[HookPublication, ...] = ()
    written: tuple[str, ...] = ()

    @property
    def result(self) -> AcknowledgmentResult:
        return self.acknowledgment.result


def _acknowledge(
    result: AcknowledgmentResult,
    reason: str | None = None,
    publications: tuple[HookPublication, ...] = (),
    written: tuple[str, ...] = (),
    **fields: object,
) -> OpenCodeOutcome:
    if reason is not None:
        fields["reason"] = reason
    acknowledgment = PluginAcknowledgment.model_validate({"result": result, **fields})
    return OpenCodeOutcome(acknowledgment, publications, written)


def corroborate_host_process(
    request: PluginRequest, lookup: ProcessLookup
) -> ProcessIdentity | str:
    """The Host Process the helper runs under, or why it is not the one the plugin named.

    The plugin starts the helper itself, so the nearest OpenCode process in
    the helper's ancestry is the server it runs in, and its pid must be the
    one the plugin reported; the process's start time then names the Host
    Process in every record, which a reused pid cannot imitate.
    """
    ancestry = observe_agent_ancestry(lookup, harness="opencode")
    if ancestry.located is None:
        return ancestry.unobservable_reason or "host-process-not-found"
    _harness, host = ancestry.located
    if host.pid != request.pid:
        return "host-process-not-corroborated"
    return host


def publish_opencode(
    request: PluginRequest, lookup: ProcessLookup = host_process_lookup
) -> OpenCodeOutcome:
    """Apply one plugin request from the Host Process that ran its helper."""
    host = corroborate_host_process(request, lookup)
    if not isinstance(host, ProcessIdentity):
        return _acknowledge("rejected", host)
    if request.kind == "register":
        return _register(request, host)
    if request.kind == "unobserved":
        return _unobserved(request, host)
    return _publish(request, host, lookup)


@dataclass(frozen=True, slots=True)
class Place:
    """The Worktree of a configured Project holding an OpenCode location."""

    worktree: Path

    @property
    def store(self) -> Path:
        return session_directory(self.worktree)

    def holds_repository_of(self, other: Place) -> bool:
        """Whether ``other`` is a Worktree of this one's Git Repository."""
        try:
            worktrees = repository_worktrees(self.worktree, timeout=2)
        except (GitError, OSError):
            return False
        return any(same_path(worktree, other.worktree) for worktree in worktrees)


def place_of(location: Path) -> Place | None:
    """The configured Project Worktree holding ``location``; ``None`` outside every Project."""
    try:
        root = Git(location, timeout=2).maybe("rev-parse", "--show-toplevel")
    except GitError:
        return None
    if not root or not is_configured_checkout(Path(root)):
        return None
    return Place(Path(root))


def _location(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _register(request: PluginRequest, host: ProcessIdentity) -> OpenCodeOutcome:
    """Accept a registration, returning the root sessions to recover there.

    They are the roots its location's store records on this Host Process,
    with their recorded Sub-agents, which the plugin reads back from
    OpenCode to repair a deletion no live instance received.
    """
    place = None if request.location is None else place_of(_location(request.location))
    if place is None:
        return _acknowledge("accepted", sessions=[])
    sessions = [
        RecoveredSession(id=record.session_id, subagents=list(record.live_subagents))
        for _key, record in _host_roots(place.store, host)
    ]
    return _acknowledge("accepted", sessions=sessions[:RECOVERY_LIMIT])


def _host_roots(store: Path, host: ProcessIdentity) -> Iterator[tuple[str, HookRecord]]:
    """Every root OpenCode record in ``store`` naming ``host``, by its record key."""
    if not store.is_dir():
        return
    for path in sorted(store.glob("*.json")):
        try:
            record = HookRecord.model_validate(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
        process = record.session_process
        # A Sub-agent's events are written on its root's record, so every
        # OpenCode record is a root's.
        if (
            record.harness == "opencode"
            and process is not None
            and process.identity.key == host.key
        ):
            yield path.stem, record


def _unobserved(request: PluginRequest, host: ProcessIdentity) -> OpenCodeOutcome:
    """Mark the running roots of a Host Process whose last live instance went.

    Nothing observes them any more, and the end of their execution may have
    reached no instance, so while the Host Process lives they read unknown
    rather than as last published (ADR 0080, ADR 0090). A root holding
    Sub-agents is marked too, since their ends may be lost as well. The
    record keeps naming its Host Process, whose exit still reads gone.
    """
    stores: list[Path] = []
    for raw in request.locations:
        place = place_of(_location(raw))
        if place is not None and not any(same_path(place.store, s) for s in stores):
            stores.append(place.store)
    for store in stores:
        for _key, record in _host_roots(store, host):
            _rewrite_record(store, record.session_id, host, _mark_unobserved_record)
    return _acknowledge("accepted")


def _mark_unobserved_record(raw: dict[str, Any]) -> bool:
    # Decided under the record's lock, so a publication that ended the
    # execution since the scan leaves nothing to mark.
    if raw.get("state") != "running" and not raw.get("liveSubagents"):
        return False
    raw["sessionProcessUnobservable"] = NO_LIVE_INSTANCE
    return True


def _forget_subagents(raw: dict[str, Any]) -> bool:
    raw["liveSubagents"] = []
    return True


def _rewrite_record(
    store: Path,
    session_id: str,
    host: ProcessIdentity,
    change: Callable[[dict[str, Any]], bool],
    *,
    only_marked: bool = False,
) -> None:
    """Change one OpenCode record of ``host`` in place, under its record locks.

    This is the one hook record write that does not pass through
    ``publish_hook_event``: the marker is no hook event of the session's,
    and must change only who observes it. The record is found under either
    name the store may have given it, and every other field is kept;
    ``change`` answers whether there is anything to write.
    """
    records = HookRecordStore(store)
    scoped = session_storage_key("opencode", session_id)
    with ExitStack() as stack:
        for key in sorted((session_id, scoped)):
            stack.enter_context(records.locked(key))
        # The store's own order: the scoped name, once another harness's
        # record took the plain one, else the plain name.
        for key in (scoped, session_id):
            try:
                raw: Any = json.loads(records.record_path(key).read_text())
                record = HookRecord.model_validate(raw)
            except (OSError, ValueError):
                continue
            if (record.harness, record.session_id) == ("opencode", session_id):
                break
        else:
            return
        process = record.session_process
        if process is None or process.identity.key != host.key:
            return
        if only_marked and record.session_process_unobservable != NO_LIVE_INSTANCE:
            return
        if change(raw):
            records.replace(key, raw)


@dataclass(frozen=True, slots=True)
class Route:
    """Where one publication is written: its hook store, and the location it names."""

    place: Place
    cwd: Path
    # The one store every record is written to, for a move written where the
    # session was; otherwise ``publish_hook_event`` routes by ``cwd``.
    directory: Path | None = None
    # The other Project a move took the session to, whose store begins its
    # incarnation there with the Sub-agents it had (ADR 0109).
    arrival: Place | None = None


def _route(session: PluginSession, event: PluginEvent | None) -> Route | None:
    """Route a publication to the store of its root's location, or ``None``.

    A move within one Git Repository is written at the new location's store,
    where a bound run follows it (ADR 0067). Any other move is written where
    the session was, naming where it went, so it no longer reads as there;
    one to another Project then arrives there too (ADR 0109).
    """
    origin = _location(session.location)
    here = place_of(origin)
    if event is None or event.to is None:
        return None if here is None else Route(here, origin)
    destination = _location(event.to)
    there = place_of(destination)
    if here is not None and there is not None and here.holds_repository_of(there):
        return Route(there, destination)
    if here is None:
        return None
    return Route(here, destination, directory=here.store, arrival=there)


def _publish(
    request: PluginRequest, host: ProcessIdentity, lookup: ProcessLookup
) -> OpenCodeOutcome:
    """Write one session's event, or its recovered deletion, under its store's lock."""
    session, event = request.session, request.event
    if session is None:
        # Unreachable past validation, which requires it here.
        return _acknowledge("rejected", "incomplete-publication")
    child = session.id != session.root
    if event is None:
        # A recovered deletion: OpenCode answered that it has no such session.
        name = "SubagentStop" if child else "SessionEnd"
    else:
        name = TRANSLATION[event.type][1 if child else 0]
    route = _route(session, event)
    if route is None:
        return _acknowledge("refused", "outside-project")
    ensure_state_directory(route.place.worktree)
    publishers = PublisherStore(route.place.store, checkout=route.place.worktree)
    with publishers.locked(PUBLISHER_KEY):
        record = publishers.read()
        if record.refuses(session.id, session.root):
            return _acknowledge("refused", "session-deleted")
        entry = record.sessions.get(session.id)
        if event is not None and entry is not None and event.sequence <= entry.sequence:
            return _acknowledge("stale")
        names: list[str] = []
        if name is not None:
            if _begins_incarnation(route.place.store, session.root, host, name):
                names.append("SessionStart")
            if name != "SessionStart" or not names:
                names.append(name)
        # A marked root's recorded Sub-agents may have ended unseen; a live
        # one's next event adds it again (ADR 0090).
        if names and names[0] != "SessionStart":
            _rewrite_record(
                route.place.store,
                session.root,
                host,
                _forget_subagents,
                only_marked=True,
            )
        publications = tuple(
            publish_hook_event(
                _hook_event(written, session, route.cwd),
                directory=route.directory,
                process=host,
                harness="opencode",
                lookup=lookup,
            )
            for written in names
        )
        sessions = dict(record.sessions)
        deleted = list(record.deleted)
        sessions.pop(session.id, None)
        if event is None or event.type == "session.deleted":
            deleted.append(session.id)
        else:
            sessions[session.id] = SessionEntry(
                sequence=event.sequence, root=session.root if child else None
            )
        publishers.write(
            record.model_copy(update={"sessions": sessions, "deleted": deleted})
        )
    if route.arrival is not None and event is not None and names:
        arrived = _arrive(route.arrival, route, session, event, host, lookup)
        if arrived is not None:
            publications = (*publications, arrived)
            names.append("SessionStart")
    reason = None if event is None else event.reason
    return _acknowledge("accepted", reason, publications, tuple(names))


def _arrive(
    arrival: Place,
    move: Route,
    session: PluginSession,
    event: PluginEvent,
    host: ProcessIdentity,
    lookup: ProcessLookup,
) -> HookPublication | None:
    """Begin a root's incarnation in the other Project ``move`` took it to.

    Written once the move is written where the session was, under the new
    store's own Publisher Record lock, never both at once. The
    ``SessionStart`` seeds from the record the move left, as ADR 0097 has a
    ``SessionStart`` of the same Host Process do, so the new record lists
    the Sub-agents still working, and the record left behind then stops
    listing them: their later events reach only the new Project's stores
    (ADR 0109). The plugin publishes a root's events and its children's in
    order, so none of them is written there before the move. A store that
    refuses the session, or has seen a later event of it, takes nothing.
    """
    ensure_state_directory(arrival.worktree)
    publishers = PublisherStore(arrival.store, checkout=arrival.worktree)
    with publishers.locked(PUBLISHER_KEY):
        record = publishers.read()
        entry = record.sessions.get(session.id)
        if record.refuses(session.id, session.root) or (
            entry is not None and event.sequence <= entry.sequence
        ):
            return None
        publication = publish_hook_event(
            _hook_event("SessionStart", session, move.cwd),
            process=host,
            harness="opencode",
            lookup=lookup,
            moved_from=move.place.store,
        )
        sessions = dict(record.sessions)
        sessions[session.id] = SessionEntry(sequence=event.sequence, root=None)
        publishers.write(record.model_copy(update={"sessions": sessions}))
    return publication


def _begins_incarnation(
    store: Path, root: str, host: ProcessIdentity, name: str
) -> bool:
    """Whether a publication on ``root`` begins an incarnation in ``store``.

    It does where the store holds no record of the root, or one naming
    another Host Process: the session began there, or resumed in a new
    server. A move never begins one where it is written, nor does an end,
    nor a Sub-agent's stop where there is no record to stop it on; a move to
    another Project begins one in that Project's store (``_arrive``).
    """
    if name in {"SessionMoved", "SessionEnd"}:
        return False
    records, unreadable = stored_session_records([store], "opencode", root)
    if not records:
        # A record that cannot be read is no evidence that the session began
        # here; its next readable publication decides.
        return not unreadable and name != "SubagentStop"
    process = records[0].record.session_process
    return process is None or process.identity.key != host.key


def _hook_event(name: str, session: PluginSession, cwd: Path) -> dict[str, Any]:
    event: dict[str, Any] = {
        "session_id": session.root,
        "hook_event_name": name,
        "cwd": str(cwd),
        "source": "opencode-plugin",
    }
    if session.id != session.root and name in {"SubagentStart", "SubagentStop"}:
        event["agent_id"] = session.id
    return event
