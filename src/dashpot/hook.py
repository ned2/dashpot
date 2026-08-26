from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .agents import publish_hook_event


def publish_from_stream(stream: TextIO) -> None:
    event: Any = json.load(stream)
    if not isinstance(event, dict):
        raise RuntimeError("hook input must be a JSON object")
    publish_hook_event(event)


def main() -> int:
    try:
        publish_from_stream(sys.stdin)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"dashpot Codex hook: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
