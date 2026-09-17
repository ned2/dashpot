from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .sessions.hook_publish import publish_hook_event

# A failed publish is reported but never blocks the session: Claude Code reads
# exit code 2 as "deny this action and feed stderr back to the model", which
# would let a full disk or an unwritable state directory erase a prompt or
# refuse a Stop. Observation must never get in the session's way.
NON_BLOCKING_FAILURE_EXIT_CODE = 1


def publish_from_stream(stream: TextIO, harness: str = "codex") -> None:
    event: Any = json.load(stream)
    if not isinstance(event, dict):
        raise RuntimeError("hook input must be a JSON object")
    publish_hook_event(event, harness=harness)


def _run(harness: str, label: str) -> int:
    # ``ValueError`` is the store's refusal of an occupied destination and
    # the base of a record's Pydantic validation failure; both are reported
    # like every other failed publish rather than shown as a traceback.
    try:
        publish_from_stream(sys.stdin, harness)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"dashpot {label} hook: {exc}", file=sys.stderr)
        return NON_BLOCKING_FAILURE_EXIT_CODE
    return 0


def main() -> int:
    return _run("codex", "Codex")


def claude_code_main() -> int:
    return _run("claude-code", "Claude Code")


if __name__ == "__main__":
    raise SystemExit(main())
