"""Runtime Events are closed models: written strictly, read tolerantly, holding no free text."""

from __future__ import annotations

import json
import typing
from collections.abc import Iterable

import pytest
from pydantic import BaseModel, ValidationError

from dashpot.core import runtime_events
from dashpot.core.pydantic import validate_rfc3339_timestamp
from dashpot.core.runtime_events import (
    SCHEMA_VERSION,
    AgentSessionChanged,
    CommandAttributes,
    CommandOutcome,
    DiagnosticChanged,
    EventLogWriteFailed,
    EventModel,
    HookOutcome,
    LevelChanged,
    ProcessEnd,
    ProcessIdentity,
    ProcessStart,
    RuntimeEvent,
    SpanAttributes,
    SpanEnded,
    fitting,
    is_recorded,
    read_runtime_event,
)

RUN = "0123456789abcdef0123456789abcdef"
SPAN = "0123456789abcdef"
NOW = "2026-09-27T12:00:00.000000Z"


def identity(**changes: object) -> ProcessIdentity:
    return ProcessIdentity.model_validate(
        {"run_id": RUN, "kind": "hook:claude-code:SessionStart", **changes}
    )


def start_facts(**changes: object) -> ProcessStart:
    return ProcessStart.model_validate(
        {
            "version": "0.1.0",
            "install_kind": "editable",
            "revision": "0" * 40,
            "pid": 42,
            "python_version": "3.14.0",
            "working_directory": "/home/someone/project with space",
            "subcommand": "work start",
            **changes,
        }
    )


def event(body: runtime_events.EventBody, **changes: object) -> RuntimeEvent:
    return RuntimeEvent.model_validate(
        {
            "time": NOW,
            "dashpot.level": "standard",
            "process": identity(),
            "body": body,
            **changes,
        }
    )


def test_an_event_is_one_flat_line_named_by_otel_conventions() -> None:
    line = event(start_facts(), process=identity(session_id="abc-123")).line()

    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert json.loads(line) == {
        "schema": SCHEMA_VERSION,
        "time": NOW,
        "dashpot.level": "standard",
        "service.instance.id": RUN,
        "dashpot.process.kind": "hook:claude-code:SessionStart",
        "dashpot.agent_session.id": "abc-123",
        "event.name": "process.start",
        "service.version": "0.1.0",
        "dashpot.install.kind": "editable",
        "vcs.ref.head.revision": "0" * 40,
        "process.pid": 42,
        "process.runtime.version": "3.14.0",
        "process.working_directory": "/home/someone/project with space",
        "dashpot.subcommand": "work start",
    }


@pytest.mark.parametrize(
    "body",
    [
        start_facts(),
        ProcessEnd(exit_code=2, duration_seconds=0.5),
        LevelChanged(previous="standard", current="full"),
        EventLogWriteFailed(error_type="ENOSPC"),
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            parent_span_id="f" * 16,
            duration_seconds=0.25,
            status="OK",
            attributes=CommandAttributes(
                program="git", subcommand="rev-parse", exit_code=128
            ),
        ),
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            duration_seconds=0,
            status="ERROR",
            error_type="CommandError",
        ),
        HookOutcome(
            hook_event="SessionEnd",
            result="succeeded",
            record_state="ended",
            work="ended",
        ),
        CommandOutcome(
            command="worktree create",
            result="refused",
            refusal_count=2,
            dry_run=True,
            duration_seconds=0.125,
            target_path="/work/dashpot.worktrees/314-x",
            target_branch="314-x",
        ),
        AgentSessionChanged(
            change="relocated", previous_worktree="/work/dashpot with space"
        ),
        DiagnosticChanged(
            change="cleared",
            source="settings:/home/someone/.config/dashpot/config.toml",
            code="refresh-failed",
            severity="error",
        ),
    ],
    ids=lambda body: body.name,
)
def test_every_event_reads_back_as_written(body: runtime_events.EventBody) -> None:
    written = event(body)

    assert read_runtime_event(written.line()) == written


def test_reading_ignores_fields_a_newer_dashpot_added() -> None:
    written = event(
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            duration_seconds=1,
            status="OK",
            attributes=CommandAttributes(program="gh", subcommand="api graphql"),
        )
    )
    raw = json.loads(written.line())
    raw["dashpot.something.new"] = [1, 2]
    raw["attributes"]["process.something.new"] = "x"

    assert read_runtime_event(json.dumps(raw)) == written


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[1, 2]",
        json.dumps({"schema": SCHEMA_VERSION + 1, "event.name": "process.end"}),
        json.dumps({"schema": SCHEMA_VERSION, "event.name": "something.else"}),
        json.dumps({"schema": SCHEMA_VERSION, "event.name": "process.end"}),
        json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "event.name": "span",
                "dashpot.span.name": "unknown",
                "attributes": {},
            }
        ),
    ],
    ids=[
        "malformed",
        "not-an-object",
        "later-schema",
        "unknown-event",
        "invalid",
        "unknown-span",
    ],
)
def test_a_line_this_dashpot_cannot_read_reads_as_nothing(line: str) -> None:
    assert read_runtime_event(line) is None


def test_the_level_in_force_records_its_own_and_less() -> None:
    assert [
        is_recorded("standard", level) for level in ("off", "standard", "full")
    ] == [
        False,
        True,
        True,
    ]
    assert [is_recorded("full", level) for level in ("off", "standard", "full")] == [
        False,
        False,
        True,
    ]


# --- Content policy --------------------------------------------------------

GIT_ERROR = "git rev-parse --verify main failed: fatal: Needed a single revision"


def test_an_error_is_recorded_by_its_code_never_its_message() -> None:
    with pytest.raises(ValidationError):
        EventLogWriteFailed(error_type=GIT_ERROR)
    with pytest.raises(ValidationError):
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            duration_seconds=0,
            status="ERROR",
            error_type=GIT_ERROR,
        )


@pytest.mark.parametrize("field", ["message", "error_message", "stderr", "output"])
def test_an_event_cannot_carry_a_message_or_command_output(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProcessEnd.model_validate(
            {"exit_code": 1, "duration_seconds": 0, field: GIT_ERROR}
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CommandAttributes.model_validate({"program": "git", field: GIT_ERROR})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_branch", "not a branch"),
        ("target_path", "relative/path"),
        ("target_harness", "some-other-agent"),
        ("error_type", "cannot write: disk full"),
    ],
)
def test_an_observed_value_that_is_no_identifier_is_left_out(
    field: str, value: str
) -> None:
    outcome = fitting(
        CommandOutcome,
        {"command": "worktree create", "result": "succeeded", "duration_seconds": 0},
        {field: value, "action": "created"},
    )

    assert getattr(outcome, field) is None
    assert outcome.action == "created"


def test_a_command_is_recorded_by_program_and_subcommand_never_its_arguments() -> None:
    with pytest.raises(ValidationError):
        CommandAttributes(program="git", subcommand="log --format=%s -1 main")
    with pytest.raises(ValidationError):
        CommandAttributes(program="/usr/bin/git")


def test_a_span_names_an_error_exactly_when_it_failed() -> None:
    with pytest.raises(ValidationError, match="names its error type"):
        SpanEnded(span_name="command", span_id=SPAN, duration_seconds=0, status="ERROR")
    with pytest.raises(ValidationError, match="names its error type"):
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            duration_seconds=0,
            status="OK",
            error_type="CommandError",
        )


def test_a_span_takes_only_its_own_kinds_attributes() -> None:
    with pytest.raises(ValidationError, match="a command span takes CommandAttributes"):
        SpanEnded(
            span_name="command",
            span_id=SPAN,
            duration_seconds=0,
            status="OK",
            attributes=SpanAttributes(),
        )


def event_models() -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    pending: list[type[BaseModel]] = [EventModel]
    while pending:
        model = pending.pop()
        found.append(model)
        pending.extend(model.__subclasses__())
    return found


def bounded(metadata: Iterable[object]) -> bool:
    """Whether a pattern, or the RFC 3339 validator, bounds a string."""
    return any(
        getattr(item, "pattern", None)
        or getattr(item, "func", None) is validate_rfc3339_timestamp
        for item in metadata
    )


def holds_free_string(annotation: object) -> bool:
    """Whether a type admits a string no pattern bounds."""
    if annotation is str:
        return True
    if typing.get_origin(annotation) is typing.Annotated:
        inner, *metadata = typing.get_args(annotation)
        return (inner is str and not bounded(metadata)) or (
            inner is not str and holds_free_string(inner)
        )
    return any(holds_free_string(arg) for arg in typing.get_args(annotation))


def unbounded_strings(model: type[BaseModel]) -> list[str]:
    """Fields of ``model`` that could hold free text."""
    return [
        name
        for name, field in model.model_fields.items()
        if (field.annotation is str and not bounded(field.metadata))
        or (field.annotation is not str and holds_free_string(field.annotation))
    ]


@pytest.mark.parametrize("model", event_models(), ids=lambda model: model.__name__)
def test_every_string_an_event_holds_is_a_bounded_identifier(
    model: type[BaseModel],
) -> None:
    assert model.model_config.get("extra") == "forbid"
    assert unbounded_strings(model) == []
    assert not {
        "message",
        "detail",
        "output",
        "stdout",
        "stderr",
        "text",
        "title",
        "body_text",
        "reason",
    } & set(model.model_fields)
