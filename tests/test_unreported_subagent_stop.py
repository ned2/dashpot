"""A Claude Code sub-agent stopped with no ``SubagentStop`` stays listed (#429).

Measured on Claude Code 2.1.287 (#419,
``docs/spikes/measurements/issue-419-claude-trace.jsonl``): the lead's own
``TaskStop`` on a running worker (scenario ``headless-taskstop``) and a
headless SDK interrupt (scenario ``headless-interrupt``) each end the worker
without a ``SubagentStop``. Each test replays one order through the hook
publisher, then reads what ``dashpot work show`` and the ``sub-agent``
Cleanup blocker say of the worker, and what the session's end clears.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.work import show_issue_work, start_issue_work
from dashpot.sessions.work_store import WorkStore
from factories import CLAUDE
from helpers import absent, present
from test_work import CLAUDE_ENVIRON, CLAUDE_SESSION, two_worktrees

WORKER = "a014e2c4c1bea3efe"

# What each surface says after the sub-agent's count and identity.
WAY_OUT = (
    "Dashpot lists a sub-agent until Claude Code reports that it stopped, "
    "which one that was stopped or interrupted may never do, so if none is "
    "still working, end that session"
)

# The lead's hook events after its worker's ``SubagentStart``, as #419
# recorded them: no ``SubagentStop`` follows in either order.
STRANDING_ORDERS = {
    # The dispatching turn ends, and the lead's next turn calls ``TaskStop``:
    # the task-notification it gets says ``stopped``. Two more turns follow.
    "taskstop": ["Stop", *["UserPromptSubmit", "Stop"] * 3],
    # The SDK host interrupts the dispatching turn, which publishes no
    # ``Stop``; the host's next prompt starts a turn that ends normally.
    "headless-interrupt": ["UserPromptSubmit", "Stop"],
}


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(at: Path, event: str, agent: str | None = None) -> None:
    """Publish one hook event of the lead, the worker's when ``agent`` is given."""
    payload = {"session_id": CLAUDE_SESSION, "cwd": str(at), "hook_event_name": event}
    if agent is not None:
        payload["agent_id"] = agent
    publish_hook_event(
        payload, process=CLAUDE, harness="claude-code", lookup=present(CLAUDE)
    )


@pytest.mark.parametrize("order", STRANDING_ORDERS.values(), ids=STRANDING_ORDERS)
def test_a_stopped_worker_is_named_as_one_that_may_never_report(
    tmp_path: Path, order: list[str]
) -> None:
    a, b = two_worktrees(tmp_path)
    publish(a, "SessionStart")
    publish(a, "UserPromptSubmit")
    start_issue_work(
        a, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )
    publish(a, "SubagentStart", WORKER)
    for event in order:
        publish(a, event)

    shown = show_issue_work(a, lookup=present(CLAUDE))
    assert shown[0].startswith("claude-code pid 7777: build-observer (I_observer) ")
    assert shown[1:] == [
        f"  claude-code pid 7777 has 1 sub-agent listed as working ({WORKER}). "
        f"{WAY_OUT}"
    ]
    (blocker,) = assess_worktree_occupancy(b, [a, b], present(CLAUDE))
    assert blocker.kind == "sub-agent"
    assert blocker.detail == (
        f"Claude Code session {CLAUDE_SESSION} at {a} has 1 sub-agent listed as "
        f"working ({WORKER}; session live). Dashpot cannot tell which Worktree "
        f"a sub-agent works in, so one may be working here: wait for it to "
        f"finish. {WAY_OUT}."
    )

    # The way out the sentence names: the session's end, after which its
    # process exits, clears both the run and the blocker.
    publish(a, "SessionEnd")
    assert WorkStore(a).active() == ([], [])
    assert show_issue_work(a, lookup=absent()) == [
        "no active Issue work at this worktree"
    ]
    assert assess_worktree_occupancy(b, [a, b], absent()) == []
