"""A hook's ``hook.outcome`` reports the state its record was stored with (#489).

The store can store a state other than the one the hook event maps to: a
manual ``/compact`` of a waiting session keeps it waiting (ADR 0100), and a
turn's ``Stop`` leaves a session running while a sub-agent works (ADR 0016).
Each test runs the Claude Code hook over a measured order and reads the
outcome from the Event Log and the stored state through the hook-record
store.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import factories
from dashpot import hook
from dashpot.core.event_log import EventLogDestination
from dashpot.core.model import Harness
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import session_directory
from dashpot.sessions.hook_scan import stored_session_records
from dashpot.sessions.processes import ProcessIdentity
from helpers import present

SESSION = "01c7192b-2990-4f83-ad33-290ac22eb4d1"
HOST = factories.CLAUDE
# The process a `claude --resume` of the session runs in.
RESUMED = ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026")
WORKER = "a1b2c3d4e5f607182"
# Every compaction reports its summarizer stopping, with no SubagentStart.
SUMMARIZER = "ad12c3d4e5f607184"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store here, record outcomes, and pin the Host Process."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    def pinned(event: dict[str, Any], harness: Harness) -> HookPublication:
        return publish_hook_event(
            event, process=HOST, harness=harness, lookup=present(HOST)
        )

    monkeypatch.setattr(hook, "publish_hook_event", pinned)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A configured checkout, whose own store holds the session's record."""
    root = factories.init_repository(tmp_path / "checkout")
    factories.write_project_config(root)
    return root


class Hooks:
    """Run the Claude Code hook, one process per event, each with its own Event Log."""

    def __init__(
        self, checkout: Path, events: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.checkout = checkout
        self.events = events
        self.monkeypatch = monkeypatch
        self.runs = 0

    def run(self, name: str, agent: str | None = None, **fields: str) -> dict[str, Any]:
        """Run one hook event and return its ``hook.outcome`` Runtime Event."""
        payload: dict[str, Any] = {
            "session_id": SESSION,
            "cwd": str(self.checkout),
            "hook_event_name": name,
            **fields,
        }
        if agent is not None:
            payload["agent_id"] = agent
        self.runs += 1
        log = self.events / str(self.runs)
        self.monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.claude_code_main(event_log=EventLogDestination(log)) == 0
        (outcome,) = [
            event
            for path in sorted(log.glob("*.jsonl"))
            for line in path.read_bytes().splitlines()
            if (event := json.loads(line))["event.name"] == "hook.outcome"
        ]
        assert outcome["dashpot.outcome.result"] == "succeeded"
        return outcome

    def stored(self) -> str | None:
        """The state the session's record is stored with, or None without one."""
        records, unreadable = stored_session_records(
            [session_directory(self.checkout)], "claude-code", SESSION
        )
        assert unreadable == 0
        if not records:
            return None
        (item,) = records
        return item.record.state


@pytest.fixture
def hooks(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Hooks:
    """The Claude Code hook of one session at ``checkout``."""
    return Hooks(checkout, tmp_path / "events", monkeypatch)


def reported(outcome: dict[str, Any]) -> str | None:
    """The session state one ``hook.outcome`` reports, None when it reports none."""
    state = outcome.get("dashpot.agent_session.state")
    assert state is None or isinstance(state, str)
    return state


def test_a_manual_compact_of_a_waiting_session_reports_it_waiting(
    hooks: Hooks,
) -> None:
    # The measured order of a manual `/compact` (ADR 0100, scenario
    # `compact`): the turn ends, the summarizer stops, never started, and the
    # compaction's SessionStart follows on the same session and Host Process.
    for name, agent, fields in [
        ("SessionStart", None, {"source": "startup"}),
        ("UserPromptSubmit", None, {}),
        ("Stop", None, {}),
        ("SubagentStop", SUMMARIZER, {}),
    ]:
        outcome = hooks.run(name, agent, **fields)
        assert reported(outcome) == hooks.stored()

    compacted = hooks.run("SessionStart", source="compact")

    # A SessionStart maps to `running`; the store kept the session waiting.
    assert hooks.stored() == "waiting"
    assert reported(compacted) == "waiting"


def test_a_stop_while_a_worker_works_reports_the_session_running(
    hooks: Hooks,
) -> None:
    hooks.run("SessionStart", source="startup")
    hooks.run("UserPromptSubmit")
    hooks.run("SubagentStart", WORKER)

    stopped = hooks.run("Stop")

    # A Stop maps to `waiting`; the working sub-agent holds the session running.
    assert hooks.stored() == "running"
    assert reported(stopped) == "running"

    released = hooks.run("SubagentStop", WORKER)

    assert hooks.stored() == "waiting"
    assert reported(released) == "waiting"


def test_a_sub_agent_event_with_no_record_to_join_reports_no_state(
    hooks: Hooks,
) -> None:
    # Only a starting sub-agent has anything to say without its parent's
    # record, so the store keeps nothing of this event.
    outcome = hooks.run("PreToolUse", WORKER)

    assert hooks.stored() is None
    assert reported(outcome) is None


def test_an_end_from_another_host_process_reports_no_state(
    checkout: Path, hooks: Hooks
) -> None:
    # The session was resumed in another process, so the end of the process
    # it left says nothing about the record the resumed one keeps.
    publish_hook_event(
        {
            "session_id": SESSION,
            "cwd": str(checkout),
            "hook_event_name": "UserPromptSubmit",
        },
        process=RESUMED,
        harness="claude-code",
        lookup=present(RESUMED),
    )

    outcome = hooks.run("SessionEnd", reason="other")

    assert hooks.stored() == "running"
    assert reported(outcome) is None


def test_an_end_reports_its_session_ended(hooks: Hooks) -> None:
    hooks.run("SessionStart", source="startup")

    outcome = hooks.run("SessionEnd", reason="other")

    assert hooks.stored() is None
    assert reported(outcome) == "ended"


def test_an_end_that_keeps_a_working_sub_agent_reports_the_session_ended(
    hooks: Hooks,
) -> None:
    # The ended record is kept for the sub-agent its session left working
    # (ADR 0095); only the sub-agent's boundaries change it from then on.
    hooks.run("SessionStart", source="startup")
    hooks.run("UserPromptSubmit")
    hooks.run("SubagentStart", WORKER)
    hooks.run("Stop")

    ended = hooks.run("SessionEnd", reason="other")

    assert hooks.stored() == "ended"
    assert reported(ended) == "ended"

    working = hooks.run("PreToolUse", WORKER)

    # The ended record is unchanged, so the store kept nothing of the event.
    assert hooks.stored() == "ended"
    assert reported(working) is None

    stopped = hooks.run("SubagentStop", WORKER)

    assert hooks.stored() is None
    assert reported(stopped) == "ended"
