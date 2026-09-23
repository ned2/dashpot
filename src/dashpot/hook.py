"""Publish one harness lifecycle hook event from standard input."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .core.errors import DashpotError
from .core.json_records import HookRecordError
from .core.model import Harness
from .sessions.hook_publish import publish_hook_event
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


def publish_from_stream(stream: TextIO, harness: Harness = "codex") -> str | None:
    """Publish one hook event; return the hook output the harness should read."""
    event: Any = json.load(stream)
    if not isinstance(event, dict):
        raise HookRecordError("hook input must be a JSON object")
    publication = publish_hook_event(event, harness=harness)
    name = event.get("hook_event_name")
    if publication.continued is None or name not in CONTEXT_EVENTS:
        return None
    return json.dumps(
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


def _run(harness: Harness, label: str) -> int:
    # ``ValueError`` is the store's refusal of an occupied destination and
    # the base of a record's Pydantic validation failure; both are reported
    # like every other failed publish rather than shown as a traceback.
    # ``RuntimeError`` stays for Python's own runtime faults, such as a
    # symlink loop under ``Path.resolve``: a hook must never break its harness.
    try:
        output = publish_from_stream(sys.stdin, harness)
        if output is not None:
            print(output)
    except (OSError, ValueError, RuntimeError, DashpotError) as exc:
        print(f"dashpot {label} hook: {exc}", file=sys.stderr)
        return NON_BLOCKING_FAILURE_EXIT_CODE
    return 0


def main() -> int:
    return _run("codex", "Codex")


def claude_code_main() -> int:
    return _run("claude-code", "Claude Code")


if __name__ == "__main__":
    raise SystemExit(main())
