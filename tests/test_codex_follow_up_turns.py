"""A Codex Sub-agent's follow-up turn is observed from the call that starts it (#674).

Codex 0.166.0 publishes no ``SubagentStart`` for a turn a ``followup_task``
or ``send_input`` call gives an existing Sub-agent, only that turn's
``SubagentStop``; the calling thread's ``PostToolUse`` for an accepted call
comes first and names the Sub-agent (docs/spikes/codex-followup-tool-hooks-spike.md).
Each test replays such an order through the publisher and reads it through
the hook record and observation (ADR 0161).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dashpot.sessions.harnesses import followed_up_subagent
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import state_directory
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from factories import CODEX
from helpers import present, table_lookup
from test_codex_delegated_work import (
    CHILD,
    SECOND_CHILD,
    bound_session,
    recorded,
    run_of,
    stored,
)
from test_work import CODEX_SESSION, two_worktrees

FOLLOW_UP = "collaborationfollowup_task"
SEND_INPUT = "multi_agent_v1send_input"
# The process a ``codex resume`` of the session runs in, beside the first.
RESUMED = ProcessIdentity(4243, 1, "codex", "Tue Aug 25 04:00:00 2026")


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(
    at: Path,
    event: str,
    child: str | None = None,
    *,
    host: ProcessIdentity = CODEX,
    lookup: ProcessLookup | None = None,
    **fields: Any,
) -> HookPublication:
    """Publish one Codex hook event of the session, child-scoped when ``child`` is given."""
    payload: dict[str, Any] = {
        "session_id": CODEX_SESSION,
        "cwd": str(at),
        "hook_event_name": event,
        **fields,
    }
    if child is not None:
        payload["agent_id"] = child
    return publish_hook_event(
        payload,
        process=host,
        harness="codex",
        lookup=lookup if lookup is not None else present(host),
    )


def follow_up(
    at: Path,
    target: str,
    caller: str | None = None,
    *,
    tool: str = FOLLOW_UP,
    event: str = "PostToolUse",
    **fields: Any,
) -> HookPublication:
    """Publish ``caller``'s follow-up call to ``target``; the root thread's when ``caller`` is None."""
    return publish(
        at,
        event,
        caller,
        tool_name=tool,
        tool_input={"target": target, "message": "Continue with the review."},
        tool_response={"submission_id": "0198"},
        **fields,
    )


def finished_sub_agent(at: Path) -> None:
    """Bind the session and run one Sub-agent's first turn to its end, then the root's."""
    bound_session(at)
    for event in ("SubagentStart", "UserPromptSubmit", "SubagentStop"):
        publish(at, event, CHILD)
    publish(at, "Stop")
    assert (run_of(at).state, recorded(at)["liveSubagents"]) == ("waiting", [])


def test_a_follow_up_holds_the_session_until_the_sub_agents_turn_stops(
    tmp_path: Path,
) -> None:
    # The measured order: the root thread's PostToolUse, its Stop while the
    # Sub-agent works, then the Sub-agent's SubagentStop alone.
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)
    publish(a, "UserPromptSubmit")

    follow_up(a, CHILD)

    assert recorded(a)["liveSubagents"] == [CHILD]
    publish(a, "Stop")
    held = run_of(a)
    assert (held.state, held.turn_started_at) == ("running", None)

    publish(a, "SubagentStop", CHILD)

    assert run_of(a).state == "waiting"
    assert recorded(a)["liveSubagents"] == []


def test_the_follow_up_is_never_stored(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, CHILD)

    record = recorded(a)
    assert "followUp" not in record
    assert "Continue with the review." not in str(record)
    assert "submission_id" not in str(record)


@pytest.mark.parametrize(
    "spelling",
    [
        CHILD.upper(),
        CHILD.replace("-", ""),
        f"{{{CHILD}}}",
        f"urn:uuid:{CHILD}",
    ],
    ids=["uppercase", "simple", "braced", "urn"],
)
def test_every_spelling_codex_parses_names_one_sub_agent(
    tmp_path: Path, spelling: str
) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, spelling)
    assert recorded(a)["liveSubagents"] == [CHILD]

    # The stop names the thread as Codex prints it, and ends the listing.
    publish(a, "SubagentStop", CHILD)
    assert recorded(a)["liveSubagents"] == []


@pytest.mark.parametrize(
    "target",
    ["/root/reviewer", "reviewer", f"uuid:{CHILD}", CHILD[:-1], f"{CHILD} "],
    ids=["path", "relative-path", "bad-prefix", "short", "padded"],
)
def test_a_target_that_is_no_thread_id_changes_nothing(
    tmp_path: Path, target: str
) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, target)
    publish(a, "Stop")

    assert (run_of(a).state, recorded(a)["liveSubagents"]) == ("waiting", [])


def test_a_follow_up_naming_the_sessions_own_thread_changes_nothing(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, CODEX_SESSION)
    publish(a, "Stop")

    assert (run_of(a).state, recorded(a)["liveSubagents"]) == ("waiting", [])


@pytest.mark.parametrize(
    ("event", "tool"),
    [
        # A call Codex refused publishes its PreToolUse alone.
        ("PreToolUse", FOLLOW_UP),
        ("PostToolUse", "collaborationspawn_agent"),
        ("PostToolUse", "exec_command"),
    ],
    ids=["pre-tool-use", "spawn", "other-tool"],
)
def test_only_an_accepted_follow_up_call_lists_its_target(
    tmp_path: Path, event: str, tool: str
) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, CHILD, tool=tool, event=event)

    assert recorded(a)["liveSubagents"] == []


def test_a_v1_send_input_lists_its_target_too(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    finished_sub_agent(a)

    follow_up(a, CHILD, tool=SEND_INPUT)
    publish(a, "Stop")
    # A v1 Sub-agent's follow-up turn publishes its own prompt.
    publish(a, "UserPromptSubmit", CHILD)

    assert run_of(a).state == "running"
    publish(a, "SubagentStop", CHILD)
    assert run_of(a).state == "waiting"


def test_a_follow_up_to_a_working_sub_agent_keeps_its_listing(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)

    follow_up(a, CHILD)
    publish(a, "Stop")
    assert recorded(a)["liveSubagents"] == [CHILD]

    # One stop ends the one listing, however many calls named it.
    publish(a, "SubagentStop", CHILD)
    assert run_of(a).state == "waiting"


def test_a_follow_up_from_another_host_process_keeps_the_sub_agents_own(
    tmp_path: Path,
) -> None:
    # The resumed process's call must not claim a Sub-agent the first process
    # still runs, which would tie its listing to the wrong process (ADR 0107).
    a, _b = two_worktrees(tmp_path)
    both = table_lookup({CODEX.pid: CODEX, RESUMED.pid: RESUMED})
    bound_session(a)
    publish(a, "SubagentStart", CHILD, lookup=both)
    publish(a, "Stop", lookup=both)
    publish(a, "SessionStart", host=RESUMED, lookup=both, source="resume")
    publish(a, "UserPromptSubmit", host=RESUMED, lookup=both)

    publish(
        a,
        "PostToolUse",
        host=RESUMED,
        lookup=both,
        tool_name=FOLLOW_UP,
        tool_input={"target": CHILD, "message": "More."},
    )

    record = recorded(a)
    assert record["liveSubagents"] == [CHILD]
    assert record["subagentProcesses"][CHILD]["pid"] == CODEX.pid


def test_a_sub_agents_follow_up_lists_its_target_in_the_sessions_record(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    for child in (CHILD, SECOND_CHILD):
        for event in ("SubagentStart", "UserPromptSubmit", "SubagentStop"):
            publish(a, event, child)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    follow_up(a, SECOND_CHILD, caller=CHILD)
    publish(a, "SubagentStop", CHILD)

    assert recorded(a)["liveSubagents"] == [SECOND_CHILD]
    assert run_of(a).state == "running"
    assert stored(a, CHILD) is None
    publish(a, "SubagentStop", SECOND_CHILD)
    assert run_of(a).state == "waiting"


def test_a_sub_agents_follow_up_without_its_sessions_record_writes_nothing(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)

    follow_up(a, SECOND_CHILD, caller=CHILD)

    assert stored(a) is None
    assert stored(a, CHILD) is None
    assert list(state_directory().rglob("*.json")) == []


def test_a_sub_agents_follow_up_after_the_session_ended_is_listed(
    tmp_path: Path,
) -> None:
    # An ended record keeps the Sub-agents its session left working (ADR
    # 0095), and one of them may still give another a turn.
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")
    assert publish(a, "SessionEnd").work == "ended"

    follow_up(a, SECOND_CHILD, caller=CHILD)

    ended = recorded(a)
    assert (ended["state"], ended["liveSubagents"]) == ("ended", [CHILD, SECOND_CHILD])


def test_only_codex_reads_a_follow_up() -> None:
    event = {
        "session_id": CODEX_SESSION,
        "hook_event_name": "PostToolUse",
        "tool_name": FOLLOW_UP,
        "tool_input": {"target": CHILD},
    }

    assert followed_up_subagent("codex", event) == CHILD
    assert followed_up_subagent("claude-code", event) is None
    assert followed_up_subagent("opencode", event) is None
    for malformed in (None, "target", {"target": 7}, {}):
        assert followed_up_subagent("codex", {**event, "tool_input": malformed}) is None
