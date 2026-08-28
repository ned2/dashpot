from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .agents import publish_hook_event


def publish_from_stream(stream: TextIO, harness: str = "codex") -> None:
    event: Any = json.load(stream)
    if not isinstance(event, dict):
        raise RuntimeError("hook input must be a JSON object")
    publish_hook_event(event, harness=harness)


def _run(harness: str, label: str) -> int:
    try:
        publish_from_stream(sys.stdin, harness)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"dashpot {label} hook: {exc}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    return _run("codex", "Codex")


def claude_code_main() -> int:
    return _run("claude-code", "Claude Code")


if __name__ == "__main__":
    raise SystemExit(main())
