"""Publish one harness lifecycle hook event from standard input."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

from .core.errors import DashpotError
from .core.event_log import EventLog, EventLogDestination, error_type, working_directory
from .core.json_records import HookRecordError
from .core.model import Harness
from .core.runtime_events import HookOutcome, OutcomeResult, fitting
from .event_logs import open_event_log
from .sessions.hook_publish import HookPublication, publish_hook_event
from .sessions.work_store import ActiveWork

# A failed publish is reported but never blocks the session: Claude Code reads
# exit code 2 as "deny this action and feed stderr back to the model", which
# would let a full disk or an unwritable state directory erase a prompt or
# refuse a Stop. Observation must never get in the session's way.
NON_BLOCKING_FAILURE_EXIT_CODE = 1
# The Claude Code events whose hook output can add context for the model. Only
# a Claude Code run is ever continued (ADR 0053), so no other harness reaches
# this output.
CONTEXT_EVENTS = frozenset({"SessionStart", "UserPromptSubmit", "PostToolUse"})
# A hook event name as a process kind may carry it; anything else is left out.
HOOK_EVENT_NAME = re.compile(r"[A-Za-z]{1,64}")


def publish_from_stream(stream: TextIO, harness: Harness = "codex") -> str | None:
    """Publish one hook event; return the hook output the harness should read."""
    return publish_event(json.load(stream), harness)


def publish_event(event: object, harness: Harness = "codex") -> str | None:
    """Publish one parsed hook event; return the hook output the harness should read."""
    return _publish(event, harness)[1]


def _publish(event: object, harness: Harness) -> tuple[HookPublication, str | None]:
    if not isinstance(event, dict):
        raise HookRecordError("hook input must be a JSON object")
    publication = publish_hook_event(event, harness=harness)
    name = event.get("hook_event_name")
    if publication.continued is None or name not in CONTEXT_EVENTS:
        return publication, None
    return publication, json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": name,
                "additionalContext": continued_work_context(publication.continued),
            }
        }
    )


def continued_work_context(work: ActiveWork) -> str:
    """Tell a resumed session that its Issue work was carried over to it."""
    return (
        f"Dashpot: this Agent Session still holds Issue work on "
        f"{work.issue_reference}, started {work.started_at} at "
        f"{work.working_directory}; its Agent Run continued from the session's "
        f"previous process. Run 'dashpot work show' to confirm it. If this "
        f"conversation is no longer working on that Issue, run 'dashpot work stop'."
    )


def hook_event_log(
    harness: Harness,
    event: object,
    *,
    destination: EventLogDestination | None = None,
) -> EventLog:
    """Open the Event Log of one hook process, named for its harness and event.

    It is routed from the session's working directory, as its hook record
    is, and names the session when the payload does; a payload that says
    neither leaves the process's own working directory and no session.
    """
    payload: dict[str, Any] = event if isinstance(event, dict) else {}
    name = payload.get("hook_event_name")
    kind = f"hook:{harness}"
    if isinstance(name, str) and HOOK_EVENT_NAME.fullmatch(name):
        kind = f"{kind}:{name}"
    cwd = payload.get("cwd")
    directory = Path(cwd) if isinstance(cwd, str) and cwd else working_directory()
    session = payload.get("session_id")
    return open_event_log(
        kind,
        working_directory=directory,
        destination=destination,
        harness=harness,
        session_id=session if isinstance(session, str) else None,
    )


def _run(
    harness: Harness, label: str, *, event_log: EventLogDestination | None = None
) -> int:
    # ``ValueError`` is the store's refusal of an occupied destination and
    # the base of a record's Pydantic validation failure; both are reported
    # like every other failed publish rather than shown as a traceback.
    # ``RuntimeError`` stays for Python's own runtime faults, such as a
    # symlink loop under ``Path.resolve``: a hook must never break its harness.
    try:
        event: object = json.load(sys.stdin)
    except (OSError, ValueError, RuntimeError) as exc:
        event = None
        failure: Exception | None = exc
    else:
        failure = None
    log = hook_event_log(harness, event, destination=event_log)
    log.start()
    code = 0
    publication: HookPublication | None = None
    error: Exception | None = None
    try:
        if failure is not None:
            raise failure
        publication, output = _publish(event, harness)
        if output is not None:
            print(output)
    except (OSError, ValueError, RuntimeError, DashpotError) as exc:
        print(f"dashpot {label} hook: {exc}", file=sys.stderr)
        code = NON_BLOCKING_FAILURE_EXIT_CODE
        error = exc
    record_hook_outcome(log, event, publication, error)
    log.end(code)
    log.close()
    return code


def record_hook_outcome(
    log: EventLog,
    event: object,
    publication: HookPublication | None,
    error: Exception | None,
) -> None:
    """Record what one hook run did to its record and the Work Store, or its error class.

    The Issue of an Agent Run it changed names the process from here on.
    """
    payload: dict[str, Any] = event if isinstance(event, dict) else {}
    # A hook asks for nothing a person could be refused: any error failed it.
    result: OutcomeResult = "succeeded" if error is None else "failed"
    if publication is not None:
        log.identify(issue_id=publication.issue_id)
    log.record(
        fitting(
            HookOutcome,
            {"result": result},
            {
                "hook_event": payload.get("hook_event_name"),
                "record_state": None if publication is None else publication.state,
                "work": None if publication is None else publication.work,
                "error_type": None if error is None else error_type(error),
            },
        )
    )


def main(*, event_log: EventLogDestination | None = None) -> int:
    """Publish one Codex hook event from standard input."""
    return _run("codex", "Codex", event_log=event_log)


def claude_code_main(*, event_log: EventLogDestination | None = None) -> int:
    """Publish one Claude Code hook event from standard input."""
    return _run("claude-code", "Claude Code", event_log=event_log)


if __name__ == "__main__":
    raise SystemExit(main())
