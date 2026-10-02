"""Translate an OpenCode plugin publication into the shared hook record rules.

Dashpot's OpenCode plugin reports native metadata only — a session's status,
its deletion, its parent, the plugin instance's own registration and
retirement — and this module decides what it means (ADR 0077):

- a root session's ``busy`` or ``retry`` is a running turn and ``idle`` a
  waiting one; its deletion is the session's end, and its first publication
  by a generation starts the session's record afresh;
- a child session, one with a native ``parentID``, is a Sub-agent of its root
  session: its activity changes only the root's live sub-agents, and it is
  never an Agent Session of its own (ADR 0016, ADR 0067);
- a shell command's bootstrap is activity of its session, and a root
  session's accepted bootstrap is acknowledged with the claim the plugin
  gives that command alone.

Every publication runs under its backend directory's publisher record lock,
so registration, retirement, the per-session sequence, and the hook record
write are one ordered step; the hook record and Work Store are reached
through ``publish_hook_event``, which owns their rules, save for the mark a
retirement leaves on its sessions' records.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, ValidationError, model_validator

from ..core.git import Git, GitError
from ..core.pydantic import NonEmptyString, PublishedModel
from ..core.state_paths import is_configured_checkout
from ..core.worktree_paths import same_path
from .harnesses import HookSessionIdentity
from .hook_publish import HookPublication, publish_hook_event
from .hook_records import (
    HookRecord,
    HookRecordStore,
    session_directory,
    state_directory,
)
from .opencode_publishers import (
    RETIRED_PUBLISHER,
    NativeStatus,
    PublisherGeneration,
    PublisherRecord,
    PublisherStore,
    SessionWatermark,
    new_publisher_record,
    publisher_key,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    ProcessPresent,
    ProcessUnobservable,
    host_process_lookup,
    observe_agent_ancestry,
)
from .session_matching import session_storage_key

PLUGIN_PROTOCOL = 1
PublicationKind = Literal["register", "retire", "status", "deleted", "bootstrap"]
AcknowledgmentResult = Literal[
    "accepted", "duplicate", "stale", "conflict", "retired", "rejected"
]


class PluginSession(PublishedModel):
    """The native metadata of one OpenCode session, as the plugin read it."""

    model_config = ConfigDict(extra="forbid")

    id: HookSessionIdentity
    directory: NonEmptyString
    parent_id: HookSessionIdentity | None = Field(default=None, alias="parentID")


class PluginPublication(PublishedModel):
    """One request from Dashpot's OpenCode plugin to its helper."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal[1]
    kind: PublicationKind
    generation: PublisherGeneration
    directory: NonEmptyString
    pid: int = Field(gt=0)
    deadline_ms: int = Field(gt=0)
    sequence: int | None = Field(default=None, gt=0)
    session: PluginSession | None = None
    root: HookSessionIdentity | None = None
    status: NativeStatus | None = None
    command: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if self.kind in {"register", "retire"}:
            return self
        if self.session is None or self.root is None or self.sequence is None:
            raise ValueError(f"a {self.kind} publication names its session and root")
        if (self.session.parent_id is None) != (self.root == self.session.id):
            raise ValueError("a root session is its own root, and a child is not")
        if (self.kind == "status") != (self.status is not None):
            raise ValueError("only a status publication carries a status")
        return self


def parse_publication(raw: str) -> PluginPublication:
    """Validate one plugin request, raising ``ValueError`` with its wire path."""
    try:
        return PluginPublication.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError(f"OpenCode plugin request: {exc.errors()[0]['msg']}") from exc


class PluginClaim(PublishedModel):
    """The Agent Session Identity claim the plugin gives one shell command."""

    session_id: HookSessionIdentity = Field(alias="sessionID")
    generation: PublisherGeneration
    pid: int


class PluginAcknowledgment(PublishedModel):
    """The helper's answer to one plugin request: the line it prints on stdout.

    A bootstrap's acknowledgment echoes its ``command``, absent or not, so
    the plugin can tell its own answer from another command's.
    """

    result: AcknowledgmentResult
    reason: str | None = None
    command: str | None = None
    claim: PluginClaim | None = None

    def wire(self) -> str:
        """The acknowledgment as the plugin reads it: only the fields it was given."""
        return self.model_dump_json(by_alias=True, exclude_unset=True)


@dataclass(frozen=True, slots=True)
class OpenCodeOutcome:
    """What one plugin publication did: its acknowledgment and hook publications."""

    acknowledgment: PluginAcknowledgment
    publications: tuple[HookPublication, ...] = ()

    @property
    def result(self) -> AcknowledgmentResult:
        return self.acknowledgment.result


def _acknowledge(
    result: AcknowledgmentResult,
    reason: str | None = None,
    publications: tuple[HookPublication, ...] = (),
    **fields: object,
) -> OpenCodeOutcome:
    if reason is not None:
        fields["reason"] = reason
    acknowledgment = PluginAcknowledgment.model_validate({"result": result, **fields})
    return OpenCodeOutcome(acknowledgment, publications)


def corroborate_backend(
    publication: PluginPublication, lookup: ProcessLookup
) -> ProcessIdentity | str:
    """The backend the helper runs under, or why it is not the one the plugin named.

    The plugin starts the helper itself, so the nearest OpenCode process in
    the helper's ancestry is the backend, and its PID must be the one the
    plugin reported; the process's start time then names the backend in every
    record, which a reused PID cannot imitate.
    """
    ancestry = observe_agent_ancestry(lookup, harness="opencode")
    if ancestry.located is None:
        return ancestry.unobservable_reason or "backend-not-found"
    _harness, backend = ancestry.located
    if backend.pid != publication.pid:
        return "backend-not-corroborated"
    return backend


def publish_opencode(
    publication: PluginPublication, lookup: ProcessLookup = host_process_lookup
) -> OpenCodeOutcome:
    """Apply one plugin publication under its publisher record's lock."""
    backend = corroborate_backend(publication, lookup)
    if not isinstance(backend, ProcessIdentity):
        return _acknowledge("rejected", backend)
    instance = Path(publication.directory).expanduser().resolve()
    hook_store, checkout = _hook_store(instance)
    store = PublisherStore(hook_store, checkout=checkout)
    key = publisher_key(backend.key, instance)
    with store.locked(key):
        record = store.read(key)
        if record is None or record.backend_key != backend.key:
            record = new_publisher_record(backend, instance)
        if publication.kind == "register":
            outcome, record = _register(record, publication)
        elif publication.kind == "retire":
            outcome, record = _retire(record, publication, hook_store, backend)
        else:
            outcome, record = _publish(record, publication, instance, backend, lookup)
        store.write(key, record)
    if publication.kind == "register" and outcome.result == "accepted":
        # Outside this record's lock: each record is locked alone, so two
        # registrations reclaiming at once never wait on each other.
        _reclaim_gone_backends(store, key, lookup)
    return outcome


def _hook_store(instance: Path) -> tuple[Path, Path | None]:
    """The hook store an instance directory's root sessions publish to, and its checkout.

    It is the one ``publish_hook_event`` routes a record at that directory
    to: the Project-local store of a configured checkout, else the global one.
    """
    try:
        root = Git(instance, timeout=2).maybe("rev-parse", "--show-toplevel")
    except GitError:
        root = None
    if root and is_configured_checkout(Path(root)):
        return session_directory(Path(root)), Path(root)
    return state_directory(), None


def _register(
    record: PublisherRecord, publication: PluginPublication
) -> tuple[OpenCodeOutcome, PublisherRecord]:
    generation = publication.generation
    if generation in record.retired:
        return _acknowledge("retired"), record
    if record.active == generation:
        return _acknowledge("duplicate"), record
    if record.active is not None:
        # The predecessor has not retired: OpenCode starts the replacement
        # first, and the plugin retries. One that never retires leaves the
        # directory unobserved until its backend restarts (ADR 0077).
        return _acknowledge("conflict", "another-generation-active"), record
    return _acknowledge("accepted"), record.model_copy(update={"active": generation})


def _reclaim_gone_backends(
    store: PublisherStore, current_key: str, lookup: ProcessLookup
) -> None:
    """Remove the records of backends whose Host Process is proven gone.

    A process that cannot be observed is kept: unknown is never gone.
    """
    for key in store.record_keys():
        if key == current_key:
            continue
        with store.locked(key):
            record = store.read(key)
            if record is None:
                continue
            pid, started_at = record.backend_key
            observed = lookup(pid)
            if isinstance(observed, ProcessUnobservable):
                continue
            if (
                isinstance(observed, ProcessPresent)
                and observed.identity.started_at == started_at
            ):
                continue
            store.record_path(key).unlink(missing_ok=True)
        store.prune_lock(key)


def _retire(
    record: PublisherRecord,
    publication: PluginPublication,
    hook_store: Path,
    backend: ProcessIdentity,
) -> tuple[OpenCodeOutcome, PublisherRecord]:
    generation = publication.generation
    retired = [*(item for item in record.retired if item != generation), generation]
    sessions = dict(record.sessions)
    for session_id, watermark in record.sessions.items():
        if watermark.generation != generation:
            continue
        del sessions[session_id]
        if watermark.root:
            _mark_unobserved(hook_store, session_id, backend)
    active = None if record.active == generation else record.active
    return _acknowledge("accepted"), record.model_copy(
        update={"retired": retired, "sessions": sessions, "active": active}
    )


def _mark_unobserved(
    hook_store: Path, session_id: str, backend: ProcessIdentity
) -> None:
    """Mark a retired generation's session record as observed by no plugin instance.

    Nothing observes the session any more, so while its backend lives on its
    activity reads unknown rather than the last status the generation saw.
    The record keeps naming the backend: OpenCode retires a generation when
    its TUI quits too, and the backend's exit must still read as gone
    (ADR 0080). This is the one hook record write that does not pass through
    ``publish_hook_event``: retirement is no hook event of the session's, and
    must change only who observes it. The record is found under either name
    the store may have given it, and every other field is kept as written.
    """
    store = HookRecordStore(hook_store)
    scoped = session_storage_key("opencode", session_id)
    with ExitStack() as stack:
        for key in sorted((session_id, scoped)):
            stack.enter_context(store.locked(key))
        # The store's own order: the scoped name, once another harness's
        # record took the plain one, else the plain name.
        for key in (scoped, session_id):
            try:
                raw: Any = json.loads(store.record_path(key).read_text())
                record = HookRecord.model_validate(raw)
            except (OSError, ValueError):
                continue
            if (record.harness, record.session_id) == ("opencode", session_id):
                break
        else:
            return
        process = record.session_process
        if process is not None and process.identity.key == backend.key:
            raw["sessionProcessUnobservable"] = RETIRED_PUBLISHER
            store.replace(key, raw)


def _publish(
    record: PublisherRecord,
    publication: PluginPublication,
    instance: Path,
    backend: ProcessIdentity,
    lookup: ProcessLookup,
) -> tuple[OpenCodeOutcome, PublisherRecord]:
    generation = publication.generation
    session, root, sequence = (
        publication.session,
        publication.root,
        publication.sequence,
    )
    if session is None or root is None or sequence is None:
        # Unreachable past validation, which requires all three here.
        return _acknowledge("rejected", "incomplete-publication"), record
    if generation in record.retired:
        return _acknowledge("retired"), record
    if record.active != generation:
        return _acknowledge("rejected", "publisher-not-active"), record
    if not same_path(Path(session.directory), instance):
        return _acknowledge("rejected", "session-outside-instance"), record
    if session.id in record.deleted or root in record.deleted:
        return _acknowledge("rejected", "session-deleted"), record
    previous = record.sessions.get(session.id)
    if previous is not None and previous.generation == generation:
        if sequence <= previous.sequence:
            return _acknowledge("stale"), record
        if publication.kind == "status" and previous.status == publication.status:
            sessions = _watermarked(record, session.id, previous, sequence)
            return _acknowledge("duplicate"), record.model_copy(
                update={"sessions": sessions}
            )
    started = record.sessions.get(root)
    events: list[dict[str, Any]] = []
    if started is None or started.generation != generation:
        # A generation's first word on a session starts its record afresh:
        # the record now names this generation's Host Process, and forgets
        # the Sub-agents a retired generation last saw.
        events.append(_hook_event("SessionStart", root, instance))
    child = session.id if session.id != root else None
    events.append(_hook_event(_event_name(publication, child), root, instance, child))
    publications = tuple(
        publish_hook_event(
            event,
            process=backend,
            harness="opencode",
            lookup=lookup,
        )
        for event in events
    )
    sessions = dict(record.sessions)
    if started is None or started.generation != generation:
        sessions[root] = SessionWatermark(generation=generation, sequence=0, root=True)
    watermark = SessionWatermark(
        generation=generation,
        sequence=sequence,
        status=publication.status,
        root=child is None,
    )
    sessions.pop(session.id, None)
    sessions[session.id] = watermark
    deleted = list(record.deleted)
    if publication.kind == "deleted":
        deleted.append(session.id)
        sessions.pop(session.id, None)
    updated = record.model_copy(update={"sessions": sessions, "deleted": deleted})
    if publication.kind == "bootstrap" and child is None:
        outcome = _acknowledge(
            "accepted",
            None,
            publications,
            command=publication.command,
            claim=PluginClaim(
                session_id=session.id, generation=generation, pid=backend.pid
            ),
        )
    elif publication.kind == "bootstrap":
        outcome = _acknowledge(
            "accepted", "delegated-session", publications, command=publication.command
        )
    else:
        outcome = _acknowledge("accepted", None, publications)
    return outcome, updated


def _watermarked(
    record: PublisherRecord, session_id: str, previous: SessionWatermark, sequence: int
) -> dict[str, SessionWatermark]:
    sessions = dict(record.sessions)
    sessions.pop(session_id, None)
    sessions[session_id] = previous.model_copy(update={"sequence": sequence})
    return sessions


def _event_name(publication: PluginPublication, child: str | None) -> str:
    """The shared hook event a publication is, for its root or for a Sub-agent."""
    if publication.kind == "deleted":
        return "SessionEnd" if child is None else "SubagentStop"
    working = publication.kind == "bootstrap" or publication.status != "idle"
    if child is not None:
        return "SubagentStart" if working else "SubagentStop"
    if publication.kind == "bootstrap":
        return "PreToolUse"
    return "UserPromptSubmit" if working else "Stop"


def _hook_event(
    name: str, root: str, instance: Path, child: str | None = None
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "session_id": root,
        "hook_event_name": name,
        "cwd": str(instance),
        "source": "opencode-plugin",
    }
    if child is not None:
        event["agent_id"] = child
    return event
