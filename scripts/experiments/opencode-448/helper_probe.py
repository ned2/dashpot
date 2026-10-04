"""Run Dashpot's OpenCode helper, recording what each plugin request wrote.

The fixture's Dashpot plugin is bound to this wrapper instead of the
installed ``dashpot-opencode-hook``; the runner writes it into the fixture
environment with that environment's Python as its interpreter. It runs the
installed helper's own entry point in the same process, so the Host Process
ancestry the helper corroborates is unchanged, and records, as one JSON line
in the file ``SPIKE_PUBLICATIONS`` names:

- the request: its kind, Publisher Generation, session, root and OpenCode
  event type, sequence and reason;
- every shared hook event it wrote, in order, each with the record's state,
  last event, live Sub-agents and Host Process pid read straight after that
  write;
- every in-place record rewrite (the unobserved marker, forgotten
  Sub-agents), with the record read after it;
- the acknowledgment.

The line is written after the helper's own work and acknowledgment, so a
slow write never changes what the helper did.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dashpot.hook as hook
import dashpot.sessions.opencode_publish as opencode_publish
from dashpot.sessions.hook_publish import HookPublication
from dashpot.sessions.opencode_publish import OpenCodeOutcome, PluginRequest

probe: dict[str, Any] = {"writes": [], "rewrites": []}


def snapshot(path: Path) -> dict[str, Any] | None:
    """The fields of one hook record this experiment reads, or ``None``."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    process = raw.get("sessionProcess") or {}
    return {
        "state": raw.get("state"),
        "event": raw.get("event"),
        "liveSubagents": raw.get("liveSubagents"),
        "hostPid": process.get("pid"),
        "unobservable": raw.get("sessionProcessUnobservable"),
    }


def record_publication[**P](
    original: Callable[P, HookPublication],
) -> Callable[P, HookPublication]:
    """Wrap ``publish_hook_event`` to read the record after each write."""

    def wrapped(*args: P.args, **kwargs: P.kwargs) -> HookPublication:
        publication = original(*args, **kwargs)
        event = args[0] if args else kwargs.get("event")
        named = event if isinstance(event, dict) else {}
        probe["writes"].append(
            {
                "name": named.get("hook_event_name"),
                "agentId": named.get("agent_id"),
                "path": str(publication.path),
                "record": snapshot(publication.path),
                "at": time.time() * 1000,
            }
        )
        return publication

    return wrapped


def record_rewrite[**P](original: Callable[P, None]) -> Callable[P, None]:
    """Wrap ``_rewrite_record`` to read the record after each rewrite."""

    def wrapped(*args: P.args, **kwargs: P.kwargs) -> None:
        store, session_id, _host, change = args[:4]
        path = (
            store / f"{session_id}.json"
            if isinstance(store, Path) and isinstance(session_id, str)
            else None
        )
        before = None if path is None else snapshot(path)
        original(*args, **kwargs)
        if path is None:
            return
        after = snapshot(path)
        probe["rewrites"].append(
            {
                "change": getattr(change, "__name__", None),
                "onlyMarked": kwargs.get("only_marked", False),
                "path": str(path),
                "changed": before != after,
                "record": after,
            }
        )

    return wrapped


def record_request[**P](
    original: Callable[P, OpenCodeOutcome],
) -> Callable[P, OpenCodeOutcome]:
    """Wrap ``publish_opencode`` to keep its request and acknowledgment."""

    def wrapped(*args: P.args, **kwargs: P.kwargs) -> OpenCodeOutcome:
        request = args[0] if args else kwargs.get("request")
        if isinstance(request, PluginRequest):
            probe["request"] = {
                "kind": request.kind,
                "generation": request.generation,
                "pid": request.pid,
                "location": request.location,
                "locations": request.locations,
                "session": None
                if request.session is None
                else request.session.model_dump(mode="json"),
                "event": None
                if request.event is None
                else request.event.model_dump(mode="json", exclude_none=True),
            }
        outcome = original(*args, **kwargs)
        acknowledgment = outcome.acknowledgment
        probe["acknowledgment"] = {
            "result": acknowledgment.result,
            "reason": acknowledgment.reason,
            "sessions": None
            if acknowledgment.sessions is None
            else [item.model_dump(mode="json") for item in acknowledgment.sessions],
        }
        probe["written"] = list(outcome.written)
        return outcome

    return wrapped


def main() -> int:
    """Run the installed helper once and append what it did."""
    started = time.time() * 1000
    vars(opencode_publish)["publish_hook_event"] = record_publication(
        opencode_publish.publish_hook_event
    )
    vars(opencode_publish)["_rewrite_record"] = record_rewrite(
        vars(opencode_publish)["_rewrite_record"]
    )
    vars(hook)["publish_opencode"] = record_request(hook.publish_opencode)
    code = hook.opencode_main()
    probe.update(code=code, startedAt=started, endedAt=time.time() * 1000)
    try:
        with open(os.environ["SPIKE_PUBLICATIONS"], "a") as output:
            output.write(json.dumps(probe) + "\n")
    except (KeyError, OSError):
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
