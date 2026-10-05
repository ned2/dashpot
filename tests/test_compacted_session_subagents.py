"""A session's own ``SessionStart`` keeps its working Sub-agents listed (#448).

Claude Code publishes ``SessionStart`` with ``source: compact`` when it
compacts a session's context, with no ``SessionEnd`` first, while the
background Sub-agents the session delegated to keep working. Each test
publishes that order for a Lead bound to an Arc Issue and reads the result
through the hook record, observation, Cleanup and ``work assign`` seams
(ADR 0097).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import factories
from dashpot.core.model import AgentRun
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import session_directory, state_directory
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.work import start_issue_work
from dashpot.sessions.worker_assignments import assign_worker
from helpers import present, table_lookup
from test_work import CLAUDE_ENVIRON, CLAUDE_SESSION, target
from test_worker_assignments import activity, arc, states

LEAD = factories.CLAUDE
# The process a `claude --resume` of the Lead's session runs in.
RESUMED = ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026")
WORKER = "a1b2c3d4e5f607182"
SECOND_WORKER = "a1b2c3d4e5f607183"
# Every compaction reports its summarizer stopping, with no SubagentStart.
SUMMARIZER = "ad12c3d4e5f607184"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(
    at: Path,
    event: str,
    agent: str | None = None,
    *,
    host: ProcessIdentity = LEAD,
    **fields: str,
) -> HookPublication:
    """Publish one hook event of the Lead from ``host``, its worker's when ``agent`` is given."""
    payload: dict[str, Any] = {
        "session_id": CLAUDE_SESSION,
        "cwd": str(at),
        "hook_event_name": event,
        **fields,
    }
    if agent is not None:
        payload["agent_id"] = agent
    return publish_hook_event(
        payload, process=host, harness="claude-code", lookup=present(host)
    )


def compact(at: Path, *, host: ProcessIdentity = LEAD) -> HookPublication:
    """Publish the ``SessionStart`` Claude Code publishes when it compacts the Lead."""
    return publish(at, "SessionStart", host=host, source="compact")


def recorded(at: Path) -> dict[str, Any]:
    """The Lead's hook record in ``at``'s store."""
    path = session_directory(at) / f"{CLAUDE_SESSION}.json"
    return json.loads(path.read_text())


def lead_run(lookup: ProcessLookup, *worktrees: Path) -> AgentRun:
    """The Lead's one observed Agent Run."""
    runs, diagnostics = observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup,
    )
    assert diagnostics == []
    (run,) = runs
    return run


def blockers(path: Path, lookup: ProcessLookup, *worktrees: Path) -> list[Any]:
    """The Cleanup blockers that occupy ``path``."""
    return assess_worktree_occupancy(path, list(worktrees), lookup)


def leading(main: Path, *workers: str) -> None:
    """Bind the Lead to the Arc at ``main``, start each worker, and end its turn."""
    publish(main, "SessionStart", source="startup")
    publish(main, "UserPromptSubmit")
    start_issue_work(main, "arc", lookup=present(LEAD), environ=CLAUDE_ENVIRON)
    for worker in workers:
        publish(main, "SubagentStart", worker)
    publish(main, "Stop")


def test_a_compacted_lead_keeps_its_working_worker_until_it_stops(
    tmp_path: Path,
) -> None:
    # The measured order of a manual `/compact` (scenario `compact`): the
    # summarizer's stop, never started, then the compaction's SessionStart.
    main, first, second = arc(tmp_path)
    live = present(LEAD)
    leading(main, WORKER)
    publish(main, "SubagentStop", SUMMARIZER)

    compact(main)

    record = recorded(main)
    assert (record["state"], record["liveSubagents"]) == ("running", [WORKER])
    assert lead_run(live, main, first, second).state == "running"
    (blocker,) = [
        one for one in blockers(first, live, main, first) if one.kind == "sub-agent"
    ]
    assert f"({WORKER}; session live)" in blocker.detail

    # The worker stops, and its notification is the Lead's next turn.
    publish(main, "SubagentStop", WORKER)
    assert recorded(main)["liveSubagents"] == []
    assert blockers(first, live, main, first) == []
    publish(main, "UserPromptSubmit")
    publish(main, "Stop")

    assert recorded(main)["state"] == "waiting"


def test_a_compaction_mid_turn_keeps_the_turn_and_its_workers(
    tmp_path: Path,
) -> None:
    # Auto-compaction runs inside a turn, whose Stop follows it with no new
    # prompt (scenario `auto-compact`); the workers hold the Lead running.
    main, _first, _second = arc(tmp_path)
    leading(main)
    publish(main, "UserPromptSubmit")
    publish(main, "SubagentStart", WORKER)
    publish(main, "SubagentStart", SECOND_WORKER)
    publish(main, "SubagentStop", SUMMARIZER)

    compact(main)
    publish(main, "Stop")

    record = recorded(main)
    assert (record["state"], record["liveSubagents"]) == (
        "running",
        [WORKER, SECOND_WORKER],
    )
    publish(main, "SubagentStop", WORKER)
    publish(main, "SubagentStop", SECOND_WORKER)
    assert recorded(main)["state"] == "waiting"


def test_a_compaction_before_the_turn_ends_carries_its_clock(
    tmp_path: Path,
) -> None:
    main, _first, _second = arc(tmp_path)
    leading(main)
    publish(main, "UserPromptSubmit")
    publish(main, "SubagentStart", WORKER)
    turn = recorded(main)["turnStartedAt"]

    compact(main)

    record = recorded(main)
    assert (record["turnStartedAt"], record["liveSubagents"]) == (turn, [WORKER])


def test_a_worker_assigned_before_a_compaction_still_runs_on_its_issue(
    tmp_path: Path,
) -> None:
    main, first, second = arc(tmp_path)
    live = present(LEAD)
    leading(main, WORKER, SECOND_WORKER)
    assign_worker(main, "first", WORKER, first, lookup=live, environ=CLAUDE_ENVIRON)

    compact(main)
    # A worker assigned after the compaction is still listed, so it is accepted.
    assign_worker(
        main, "second", SECOND_WORKER, second, lookup=live, environ=CLAUDE_ENVIRON
    )

    run = lead_run(live, main, first, second)
    assert states(run) == {WORKER: "running", SECOND_WORKER: "running"}
    assert activity(run)["I_first"] == ("running",)
    assert activity(run)["I_second"] == ("running",)


def test_a_compaction_where_the_lead_came_back_lists_only_its_live_workers(
    tmp_path: Path,
) -> None:
    # A shell `cd` moves a Claude Code session's hooks without a hook of its
    # own, so the record at `main` is stale when the Lead compacts back there.
    main, first, _second = arc(tmp_path)
    live = present(LEAD)
    leading(main, WORKER)
    publish(first, "UserPromptSubmit")
    publish(first, "SubagentStart", SECOND_WORKER)
    publish(first, "SubagentStop", WORKER)

    compact(main)

    assert recorded(main)["liveSubagents"] == [SECOND_WORKER]
    (blocker,) = [
        one for one in blockers(first, live, main, first) if one.kind == "sub-agent"
    ]
    assert f"({SECOND_WORKER}; session live)" in blocker.detail


def test_a_start_in_another_process_lists_none_of_the_old_ones_workers(
    tmp_path: Path,
) -> None:
    # A `claude --resume` runs the session in a new process; the old one's
    # workers ended with it, and the new incarnation starts with none.
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)

    publish(main, "SessionStart", host=RESUMED, source="resume")

    assert recorded(main)["liveSubagents"] == []
    resumed = table_lookup({RESUMED.pid: RESUMED})
    assert "sub-agent" not in [
        one.kind for one in blockers(first, resumed, main, first)
    ]
