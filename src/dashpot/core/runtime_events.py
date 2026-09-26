"""Model the Runtime Events a Dashpot process records in its Event Log.

Every event is a closed model, so the content policy of ADR 0059 is kept by
which fields exist: no field holds a message, command output or other free
text, and every string field is constrained to the identifier it names. An
error is recorded by its code or class. Field names on disk follow
OpenTelemetry semantic conventions where one exists and are ``dashpot.*``
otherwise, so the models set their aliases explicitly rather than taking
``DashpotModel``'s camelCase ones.

Writing is strict; :func:`read_runtime_event` is tolerant of fields a newer
Dashpot added, and a change it could not read bumps :data:`SCHEMA_VERSION`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    SerializationInfo,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    StringConstraints,
    ValidationError,
    model_serializer,
    model_validator,
)

from .model import Harness
from .pydantic import PublishedModel, Rfc3339Timestamp

SCHEMA_VERSION = 1
# The largest line an event may take, newline included; a longer one is
# dropped rather than split, so every line a reader sees is whole.
MAX_EVENT_BYTES = 8192

# How much a process records: its level in force.
EventLevel = Literal["off", "standard", "full"]
# The level one event belongs to; ``off`` is never an event's own.
RecordedLevel = Literal["standard", "full"]
EVENT_LEVELS: tuple[EventLevel, ...] = ("off", "standard", "full")


def is_recorded(level: RecordedLevel, in_force: EventLevel) -> bool:
    """Whether an event of ``level`` is written while ``in_force`` is the level."""
    return in_force == "full" or (in_force == "standard" and level == "standard")


def _identifier(pattern: str, max_length: int) -> object:
    return StringConstraints(pattern=pattern, max_length=max_length)


# Every string a Runtime Event holds is one of these. None admits a line
# break, and only a path admits a space.
RunId = Annotated[str, _identifier(r"^[0-9a-f]{32}$", 32)]
SpanId = Annotated[str, _identifier(r"^[0-9a-f]{16}$", 16)]
# A Diagnostic code, a ``DashpotError`` subclass, an errno name: never a message.
ErrorType = Annotated[str, _identifier(r"^[A-Za-z][A-Za-z0-9_.:-]*$", 128)]
# ``dashboard``, ``command:work-start``, ``hook:claude-code:SessionStart``.
ProcessKind = Annotated[
    str,
    _identifier(
        r"^(dashboard|command:[a-z]+(-[a-z]+)*|hook:[a-z]+(-[a-z]+)*(:[A-Za-z]+)?)$",
        128,
    ),
]
# An opaque identity: an Agent Session's native ID, a Project or Issue Identity.
OpaqueIdentity = Annotated[str, _identifier(r"^[A-Za-z0-9][A-Za-z0-9_.:/#@+=-]*$", 512)]
AbsolutePath = Annotated[str, _identifier(r"^/[^\x00-\x1f\x7f]*$", 4096)]
VersionText = Annotated[str, _identifier(r"^[0-9A-Za-z][0-9A-Za-z.+!_-]*$", 64)]
Revision = Annotated[str, _identifier(r"^([0-9a-f]{40}|[0-9a-f]{64}|unknown)$", 64)]
# A subcommand without its arguments: ``work start``, ``issue list``.
Subcommand = Annotated[
    str, _identifier(r"^[a-z]+(-[a-z]+)*( [a-z]+(-[a-z]+)*){0,2}$", 64)
]
ProgramName = Annotated[str, _identifier(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", 64)]
# A command's subcommand words, never its arguments: ``rev-parse``,
# ``api graphql DashpotQueryPage``.
CommandWords = Annotated[
    str,
    _identifier(
        r"^[A-Za-z0-9][A-Za-z0-9_.:-]*( [A-Za-z0-9][A-Za-z0-9_.:-]*){0,2}$", 128
    ),
]

InstallKind = Literal["wheel", "editable", "directory", "archive", "vcs", "unknown"]
EventName = Literal[
    "process.start",
    "process.continued",
    "process.end",
    "level.changed",
    "event_log.write_failed",
    "span",
    "hook.outcome",
    "command.outcome",
    "agent_session.changed",
    "diagnostic.changed",
]
SpanName = Literal["command"]
SpanStatus = Literal["OK", "ERROR"]


class EventModel(PublishedModel):
    """A closed part of a Runtime Event, with explicit on-disk field names."""

    model_config = ConfigDict(extra="forbid", alias_generator=None)


class ProcessIdentity(EventModel):
    """Which process recorded an event, and what it worked for when known.

    Work is followed across processes by these shared identifiers, never by
    propagating trace IDs between them.
    """

    run_id: RunId = Field(alias="service.instance.id")
    kind: ProcessKind = Field(alias="dashpot.process.kind")
    harness: Harness | None = Field(default=None, alias="dashpot.agent_session.harness")
    session_id: OpaqueIdentity | None = Field(
        default=None, alias="dashpot.agent_session.id"
    )
    project_id: OpaqueIdentity | None = Field(default=None, alias="dashpot.project.id")
    worktree: AbsolutePath | None = Field(default=None, alias="dashpot.worktree.path")
    issue_id: OpaqueIdentity | None = Field(default=None, alias="dashpot.issue.id")


class EventBody(EventModel):
    """What one Runtime Event says, beside the envelope every event shares."""

    # The level a standalone event belongs to; a span chooses its own.
    LEVEL: ClassVar[RecordedLevel] = "standard"

    name: EventName = Field(alias="event.name")


class ProcessFacts(EventBody):
    """What a process is: its Dashpot, its interpreter, and where it runs.

    ``revision`` is the commit of Dashpot's own source, not of any observed
    Repository; ``source_dirty`` is recorded by a dashboard only.
    """

    version: VersionText = Field(alias="service.version")
    install_kind: InstallKind = Field(alias="dashpot.install.kind")
    revision: Revision = Field(alias="vcs.ref.head.revision")
    source_dirty: bool | None = Field(default=None, alias="dashpot.source.dirty")
    pid: int = Field(alias="process.pid")
    python_version: VersionText = Field(alias="process.runtime.version")
    working_directory: AbsolutePath | None = Field(
        default=None, alias="process.working_directory"
    )
    subcommand: Subcommand | None = Field(default=None, alias="dashpot.subcommand")


class ProcessStart(ProcessFacts):
    """A process's first event."""

    name: Literal["process.start"] = Field(default="process.start", alias="event.name")


class ProcessContinued(ProcessFacts):
    """The first event of a file a process opened after its first, repeating its start."""

    name: Literal["process.continued"] = Field(
        default="process.continued", alias="event.name"
    )


class ProcessEnd(EventBody):
    """A process's last event; a crash or kill leaves none."""

    name: Literal["process.end"] = Field(default="process.end", alias="event.name")
    exit_code: int = Field(alias="process.exit.code")
    duration_seconds: float = Field(ge=0, alias="dashpot.duration_seconds")


class LevelChanged(EventBody):
    """Where the level in force changed, so a reader knows what it may count."""

    name: Literal["level.changed"] = Field(default="level.changed", alias="event.name")
    previous: EventLevel = Field(alias="dashpot.event_level.previous")
    current: EventLevel = Field(alias="dashpot.event_level.current")


class EventLogWriteFailed(EventBody):
    """A write to the Event Log that failed and was dropped.

    Kept only in a dashboard's in-memory buffer: the Event Log it would be
    written to is the thing that failed.
    """

    name: Literal["event_log.write_failed"] = Field(
        default="event_log.write_failed", alias="event.name"
    )
    error_type: ErrorType = Field(alias="error.type")


# --- Standalone events recorded at Dashpot's seams (#314) --------------------
#
# Each says what a hook, a management command or the dashboard observed, by
# identifiers and closed vocabularies only. The subject of an event — the
# Agent Session, Issue, Project or Worktree it is about — travels in the
# envelope's identity fields, so a reader filters every kind of event by the
# same names.

# A lifecycle hook event's name, as its harness sends it: ``SessionStart``.
HookEventName = Annotated[str, _identifier(r"^[A-Za-z]{1,64}$", 64)]
# A Branch name as Git allows it: no space, control or ref-syntax character.
BranchName = Annotated[str, _identifier(r"^[^\s~^:?*\[\\\x00-\x1f\x7f]+$", 255)]
# A Diagnostic's source: its family or an Agent Run's opaque ID, then the
# identifier (no space) or absolute path it names (``project:<id>``,
# ``settings:<path>``, ``github``).
DiagnosticSource = Annotated[
    str,
    _identifier(
        r"^[A-Za-z0-9][A-Za-z0-9._-]*"
        r"(:(/[^\x00-\x1f\x7f]*|[^\s/\x00-\x1f\x7f][^\s\x00-\x1f\x7f]*))?$",
        4200,
    ),
]
# A Diagnostic's stable code: ``github-rate-limit-low``.
DiagnosticCode = Annotated[str, _identifier(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", 128)]

# How a hook or management command came out. ``refused`` is a refusal
# Dashpot stated to a person (a ``DashpotError``, or a plan's refusals);
# ``failed`` is anything else that stopped the work.
OutcomeResult = Literal["succeeded", "refused", "failed"]
# What a hook did to its session's Agent Run in the Work Store.
WorkStoreChange = Literal["unchanged", "ended", "continued", "relocated"]
# The state a hook wrote to its session's hook record.
HookRecordState = Literal["running", "waiting", "ended"]
# The commands that mutate on explicit invocation (ADR 0008), whose outcome
# each run records.
ManagementCommand = Literal[
    "init",
    "integrate",
    "work start",
    "work relocate",
    "work stop",
    "worktree create",
    "worktree remove",
    "branch delete",
    "events remove",
]
# What a management command did, when it did something.
CommandAction = Literal[
    "initialized",
    "installed",
    "reported",
    "started",
    "switched",
    "restarted",
    "relocation-prepared",
    "relocation-cancelled",
    "stopped",
    "no-work",
    "planned",
    "created",
    "previewed",
    "removed",
    "deleted",
]
AgentSessionChange = Literal[
    "appeared", "bound", "switched", "unbound", "relocated", "ended"
]
DiagnosticChange = Literal["appeared", "cleared"]
DiagnosticSeverity = Literal["info", "warning", "error"]


class HookOutcome(EventBody):
    """What one lifecycle hook run did: the record it wrote and the Work Store change.

    The harness and Agent Session Identity are the hook process's own, in
    the envelope; a failure is its error class, never the line the hook
    printed to its harness.
    """

    name: Literal["hook.outcome"] = Field(default="hook.outcome", alias="event.name")
    hook_event: HookEventName | None = Field(default=None, alias="dashpot.hook.event")
    result: OutcomeResult = Field(alias="dashpot.outcome.result")
    record_state: HookRecordState | None = Field(
        default=None, alias="dashpot.agent_session.state"
    )
    # Absent when the hook failed before it could say.
    work: WorkStoreChange | None = Field(
        default=None, alias="dashpot.work_store.change"
    )
    error_type: ErrorType | None = Field(default=None, alias="error.type")


class CommandOutcome(EventBody):
    """What one management command did to its target, or why it did nothing.

    A refusal is its ``DashpotError`` class, or the count of a plan's
    refusals, never their text.
    """

    name: Literal["command.outcome"] = Field(
        default="command.outcome", alias="event.name"
    )
    command: ManagementCommand = Field(alias="dashpot.subcommand")
    result: OutcomeResult = Field(alias="dashpot.outcome.result")
    action: CommandAction | None = Field(default=None, alias="dashpot.outcome.action")
    error_type: ErrorType | None = Field(default=None, alias="error.type")
    refusal_count: int | None = Field(
        default=None, ge=0, alias="dashpot.outcome.refusal_count"
    )
    dry_run: bool | None = Field(default=None, alias="dashpot.outcome.dry_run")
    duration_seconds: float = Field(ge=0, alias="dashpot.duration_seconds")
    target_path: AbsolutePath | None = Field(default=None, alias="dashpot.target.path")
    target_branch: BranchName | None = Field(
        default=None, alias="dashpot.target.branch"
    )
    target_harness: Harness | None = Field(default=None, alias="dashpot.target.harness")


class AgentSessionChanged(EventBody):
    """An Agent Session a dashboard observed appearing, changing or ending.

    The envelope names the session, its Project, Worktree and Issue as now
    observed; the previous Issue or Worktree is kept beside a change of it.
    """

    name: Literal["agent_session.changed"] = Field(
        default="agent_session.changed", alias="event.name"
    )
    change: AgentSessionChange = Field(alias="dashpot.agent_session.change")
    previous_issue_id: OpaqueIdentity | None = Field(
        default=None, alias="dashpot.issue.previous_id"
    )
    previous_worktree: AbsolutePath | None = Field(
        default=None, alias="dashpot.worktree.previous_path"
    )


class DiagnosticChanged(EventBody):
    """A Diagnostic a dashboard shows appearing or clearing, by its source and code."""

    name: Literal["diagnostic.changed"] = Field(
        default="diagnostic.changed", alias="event.name"
    )
    change: DiagnosticChange = Field(alias="dashpot.diagnostic.change")
    source: DiagnosticSource | None = Field(
        default=None, alias="dashpot.diagnostic.source"
    )
    code: DiagnosticCode = Field(alias="dashpot.diagnostic.code")
    severity: DiagnosticSeverity = Field(alias="dashpot.diagnostic.severity")


def fitting[M: EventModel](
    model: type[M], required: Mapping[str, object], optional: Mapping[str, object]
) -> M:
    """Build ``model``, leaving out each optional value that does not fit its field.

    A value observed at run time — a path, a Branch name, a Diagnostic's
    source — is recorded only when it is the identifier its field names; an
    unfit one is dropped rather than failing the work that recorded it.
    """
    fields = dict(required)
    for field, value in optional.items():
        if value is None:
            continue
        try:
            model.model_validate({**fields, field: value})
        except ValidationError:
            continue
        fields[field] = value
    return model.model_validate(fields)


class SpanAttributes(EventModel):
    """The closed attributes of one kind of span."""


class CommandAttributes(SpanAttributes):
    """One external command: its program and subcommand, and how it exited.

    A non-zero exit is an answer the caller reads, recorded here, never a
    failure of the span.
    """

    program: ProgramName = Field(alias="process.executable.name")
    subcommand: CommandWords | None = Field(
        default=None, alias="dashpot.command.subcommand"
    )
    exit_code: int | None = Field(default=None, alias="process.exit.code")


# Keyed by name as written, so a reader can look up a name it read.
SPAN_ATTRIBUTES: Mapping[str, type[SpanAttributes]] = {
    "command": CommandAttributes,
}


class SpanEnded(EventBody):
    """A timed unit of work, recorded once when it ends.

    It failed (``ERROR``) only when its work could not be done, and then
    names the error's code or class.
    """

    name: Literal["span"] = Field(default="span", alias="event.name")
    span_name: SpanName = Field(alias="dashpot.span.name")
    span_id: SpanId = Field(alias="span_id")
    parent_span_id: SpanId | None = Field(default=None, alias="parent_span_id")
    duration_seconds: float = Field(ge=0, alias="dashpot.duration_seconds")
    status: SpanStatus = Field(alias="otel.status_code")
    error_type: ErrorType | None = Field(default=None, alias="error.type")
    attributes: SerializeAsAny[SpanAttributes] | None = None

    @model_validator(mode="after")
    def check_outcome(self) -> Self:
        """Name an error exactly when the span failed, with its kind's attributes."""
        if (self.status == "ERROR") != (self.error_type is not None):
            raise ValueError("a failed span names its error type, and only it")
        expected = SPAN_ATTRIBUTES[self.span_name]
        if self.attributes is not None and type(self.attributes) is not expected:
            raise ValueError(f"a {self.span_name} span takes {expected.__name__}")
        return self


EVENT_BODIES: Mapping[str, type[EventBody]] = {
    "process.start": ProcessStart,
    "process.continued": ProcessContinued,
    "process.end": ProcessEnd,
    "level.changed": LevelChanged,
    "event_log.write_failed": EventLogWriteFailed,
    "span": SpanEnded,
    "hook.outcome": HookOutcome,
    "command.outcome": CommandOutcome,
    "agent_session.changed": AgentSessionChanged,
    "diagnostic.changed": DiagnosticChanged,
}


class RuntimeEvent(EventModel):
    """One line of an Event Log: the envelope, the process, and what happened.

    The process identity and the body are flattened into the one object on
    disk, as a wide event's attributes are.
    """

    schema_version: Literal[1] = Field(default=SCHEMA_VERSION, alias="schema")
    time: Rfc3339Timestamp
    level: RecordedLevel = Field(alias="dashpot.level")
    process: ProcessIdentity
    body: SerializeAsAny[EventBody]

    @model_serializer(mode="wrap")
    def flatten(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        """Write the process identity and the body beside the envelope's fields."""
        data: dict[str, Any] = handler(self)
        process = data.pop("process")
        body = data.pop("body")
        return {**data, **process, **body}

    def line(self) -> bytes:
        """This event as one JSON line, as the Event Log stores it."""
        return self.model_dump_json(by_alias=True, exclude_none=True).encode() + b"\n"


def _known(model: type[EventModel], raw: Mapping[str, object]) -> dict[str, object]:
    aliases = {field.alias or name for name, field in model.model_fields.items()}
    return {key: value for key, value in raw.items() if key in aliases}


def read_runtime_event(line: str | bytes) -> RuntimeEvent | None:
    """Read one Event Log line, or nothing when it cannot be read.

    Fields a newer Dashpot added are ignored rather than refused. A line that
    is not an event this Dashpot knows — malformed, of a later schema, or
    naming an event it has no model for — reads as nothing.
    """
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_VERSION:
        return None
    name = raw.get("event.name")
    body_model = EVENT_BODIES.get(name) if isinstance(name, str) else None
    if body_model is None:
        return None
    body = _known(body_model, raw)
    try:
        if body_model is SpanEnded and isinstance(raw.get("attributes"), dict):
            span_name = raw.get("dashpot.span.name")
            attributes_model = (
                SPAN_ATTRIBUTES.get(span_name) if isinstance(span_name, str) else None
            )
            if attributes_model is None:
                return None
            body["attributes"] = attributes_model.model_validate(
                _known(attributes_model, raw["attributes"])
            )
        return RuntimeEvent.model_validate(
            {
                "schema": SCHEMA_VERSION,
                "time": raw.get("time"),
                "dashpot.level": raw.get("dashpot.level"),
                "process": ProcessIdentity.model_validate(_known(ProcessIdentity, raw)),
                "body": body_model.model_validate(body),
            }
        )
    except ValidationError:
        return None
