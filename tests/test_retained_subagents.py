"""A session that ends while its sub-agents work keeps them blocking Cleanup (#431).

Measured on Codex 0.160.0 (#420, scenario ``lead-unload``): the managed
daemon unloads an idle lead about 60 s after its last client leaves, while a
worker it spawned keeps working, and the worker's ``SubagentStop`` arrives
well after the settler of ADR 0086 has ended the lead's run. Each test
replays that order, or a variation of it, through the hook publisher, the
settler and the Cleanup and observation seams (ADR 0095).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dashpot.core.command_outcomes import OutcomeNote
from dashpot.core.model import AgentRun
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecordStore,
    build_hook_record,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import summarize_session_records
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.session_matching import session_storage_key
from dashpot.sessions.work import (
    IssueWorkError,
    forget_session_subagents,
    show_issue_work,
)
from dashpot.sessions.work_store import WorkStore
from helpers import absent, present, unobservable
from test_deferred_session_end import (
    DAEMON,
    REPLACEMENT,
    Settlers,
    bind,
    session_end,
    settle,
)
from test_work import CODEX_SESSION, target, two_worktrees

# The lead's worker thread, and a second one.
WORKER = "01a1055e-b174-72d2-af3e-1f0adc120810"
SECOND_WORKER = "01a1055e-b174-72d2-af3e-1f0adc120811"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(
    at: Path,
    event: str,
    agent: str | None = None,
    *,
    host: ProcessIdentity = DAEMON,
) -> HookPublication:
    """Publish one hook event of the lead from ``host``, the worker's when ``agent`` is given."""
    payload: dict[str, Any] = {
        "session_id": CODEX_SESSION,
        "cwd": str(at),
        "hook_event_name": event,
    }
    if agent is not None:
        payload["agent_id"] = agent
    return publish_hook_event(
        payload, process=host, harness="codex", lookup=present(host)
    )


def stored(at: Path) -> dict[str, Any] | None:
    """The lead's hook record in ``at``'s store, if there is one."""
    path = session_directory(at) / f"{CODEX_SESSION}.json"
    return json.loads(path.read_text()) if path.exists() else None


def sessions(lookup: ProcessLookup, *worktrees: Path) -> list[AgentRun]:
    """Every Agent Run observation shows at ``worktrees``."""
    observed, diagnostics = observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup,
    )
    assert diagnostics == []
    return observed


def blockers(path: Path, lookup: ProcessLookup, *worktrees: Path) -> list[Any]:
    """The Cleanup blockers that occupy ``path``."""
    return assess_worktree_occupancy(path, list(worktrees), lookup)


def delegated_and_ended(a: Path, settlers: Settlers) -> None:
    """Bind the lead at ``a``, start its worker, then end the lead as an unload does."""
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    publish(a, "SubagentStart", WORKER)
    publish(a, "Stop")
    assert session_end(a, CODEX_SESSION, DAEMON, settlers).work == "deferred"


def forget_command(at: Path) -> str:
    """The command the ended lead's `sub-agent` blocker names at ``at``."""
    return f"cd {at} && dashpot work forget-subagents {CODEX_SESSION} --harness codex"


def ended_blocker_detail(a: Path, agents: str, count: str) -> str:
    """The `sub-agent` blocker's detail for the lead that ended at ``a``."""
    return (
        f"Codex session {CODEX_SESSION} at {a} ended with {count} listed as "
        f"working ({agents}). Dashpot cannot tell which Worktree a sub-agent "
        f"works in, so one may be working here: wait for it to finish. Dashpot "
        f"lists a sub-agent of an ended session until Codex reports that it "
        f"stopped or the session's process exits, which one that was stopped, "
        f"was interrupted or ended with its session may never do, so if none "
        f"is still working, run dashpot work forget-subagents {CODEX_SESSION} "
        f"--harness codex."
    )


# --- The measured order ---------------------------------------------------------


def test_an_unloaded_lead_keeps_its_working_worker_blocking_until_it_stops(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    publish(a, "SubagentStart", WORKER)
    publish(a, "Stop")
    # lead-unload-bound-fourth: while the lead is loaded, its worker blocks.
    (bound,) = blockers(b, live, a, b)
    assert (bound.kind, bound.command) == ("sub-agent", None)
    assert f"has 1 sub-agent listed as working ({WORKER}; session live)" in bound.detail

    # The daemon unloads the lead, and the settler finds the daemon live.
    settlers = Settlers()
    assert session_end(a, CODEX_SESSION, DAEMON, settlers).work == "deferred"
    (deferred,) = settlers.started
    assert len(settle(deferred, live)) == 1
    assert WorkStore(a).active() == ([], [])

    # lead-unload-settled-fourth: no run, but the worker still blocks.
    (kept,) = blockers(b, live, a, b)
    assert kept.kind == "sub-agent"
    assert kept.detail == ended_blocker_detail(a, WORKER, "1 sub-agent")
    assert kept.command == forget_command(b)
    # The ended session is not observed, and observation keeps its record.
    assert sessions(live, a, b) == []
    assert stored(a) is not None

    # The worker's later commands neither revive nor move the ended lead.
    assert publish(b, "PreToolUse", WORKER).state == "running"
    assert publish(b, "UserPromptSubmit", WORKER).state == "running"
    assert stored(b) is None
    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("ended", [WORKER])
    assert sessions(live, a, b) == []

    # Its SubagentStop, which #420 saw recorded as changing nothing, now
    # ends the listing, and never lists the ended lead as waiting.
    publish(a, "SubagentStop", WORKER)
    assert stored(a) is None
    assert blockers(b, live, a, b) == []
    assert sessions(live, a, b) == []


def test_each_worker_stops_on_its_own(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    publish(a, "SubagentStart", WORKER)
    publish(a, "SubagentStart", SECOND_WORKER)
    publish(a, "Stop")
    session_end(a, CODEX_SESSION, DAEMON, Settlers())

    (kept,) = blockers(b, live, a, b)
    assert kept.detail == ended_blocker_detail(
        a, f"{WORKER}, {SECOND_WORKER}", "2 sub-agents"
    )

    publish(a, "SubagentStop", SECOND_WORKER)
    (kept,) = blockers(b, live, a, b)
    assert kept.detail == ended_blocker_detail(a, WORKER, "1 sub-agent")
    # A repeated stop changes nothing.
    publish(a, "SubagentStop", SECOND_WORKER)
    assert stored(a) is not None

    publish(a, "SubagentStop", WORKER)
    assert blockers(b, live, a, b) == []


def test_a_worker_the_ended_lead_never_listed_is_added_by_its_start(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())

    publish(a, "SubagentStart", SECOND_WORKER)

    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == (
        "ended",
        [WORKER, SECOND_WORKER],
    )


def test_an_end_with_no_live_worker_still_removes_its_record(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    publish(a, "SubagentStart", WORKER)
    publish(a, "SubagentStop", WORKER)

    session_end(a, CODEX_SESSION, DAEMON, Settlers())

    assert stored(a) is None
    assert blockers(b, present(DAEMON), a, b) == []


def test_work_show_names_the_ended_sessions_workers_before_the_settler_decides(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())

    shown = show_issue_work(a, lookup=present(DAEMON))

    assert shown[1:] == [
        f"  codex pid 4242 ended with 1 sub-agent listed as working ({WORKER}). "
        f"Dashpot lists a sub-agent of an ended session until Codex reports that "
        f"it stopped or the session's process exits, which one that was "
        f"stopped, was interrupted or ended with its session may never do, so "
        f"if none is still working, run dashpot work forget-subagents "
        f"{CODEX_SESSION} --harness codex"
    ]


# --- The Host Process bounds the listing ------------------------------------------


def test_a_gone_host_takes_the_listing_with_it(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())

    assert blockers(b, absent(), a, b) == []
    # Observation prunes the record once its process is gone.
    sessions(absent(), a, b)
    assert stored(a) is None


def test_an_unobservable_host_keeps_the_listing(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())
    unknown = unobservable("isolated-namespace")

    (kept,) = blockers(b, unknown, a, b)

    assert kept.kind == "sub-agent"
    sessions(unknown, a, b)
    assert stored(a) is not None


def test_an_end_naming_no_host_keeps_nothing(tmp_path: Path) -> None:
    # Nothing but a SubagentStop could ever clear a listing with no process.
    a, _b = two_worktrees(tmp_path)
    store = HookRecordStore(session_directory(a))
    event = {"session_id": CODEX_SESSION, "cwd": str(a)}
    store.write(build_hook_record({**event, "hook_event_name": "SessionStart"}))
    store.write(
        build_hook_record(
            {**event, "hook_event_name": "SubagentStart", "agent_id": WORKER}
        )
    )
    assert stored(a) is not None

    store.write(build_hook_record({**event, "hook_event_name": "SessionEnd"}))

    assert stored(a) is None


def test_integration_status_names_what_keeps_an_ended_record(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())

    summary = summarize_session_records(session_directory(a), present(DAEMON))

    (kept,) = summary.stale
    assert (kept.outcome, kept.retained_subagents) == ("ended", (WORKER,))
    (gone,) = summarize_session_records(session_directory(a), absent()).stale
    assert gone.retained_subagents == ()


# --- The session starting again ---------------------------------------------------


def test_a_lead_resumed_on_the_same_daemon_carries_its_workers(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    delegated_and_ended(a, Settlers())

    publish(a, "SessionStart")

    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("running", [WORKER])
    publish(a, "Stop")
    (run,) = sessions(live, a, b)
    assert run.state == "running"

    publish(a, "SubagentStop", WORKER)
    (run,) = sessions(live, a, b)
    assert run.state == "waiting"
    assert blockers(b, live, a, b) == []


def test_another_host_neither_carries_nor_stops_the_listing(tmp_path: Path) -> None:
    # A restart's replacement daemon reloads the lead; the old daemon's
    # workers are not its own.
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())

    publish(a, "SubagentStop", WORKER, host=REPLACEMENT)
    record = stored(a)
    assert record is not None
    assert record["liveSubagents"] == [WORKER]

    publish(a, "UserPromptSubmit", host=REPLACEMENT)

    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("running", [])


# --- Forgetting a listing no SubagentStop will clear ---------------------------


def test_forget_removes_a_listing_no_stop_will_clear(tmp_path: Path) -> None:
    # Measured on 0.160.0: deleting a lead ends its worker too, and no
    # SubagentStop follows.
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    delegated_and_ended(a, Settlers())
    note = OutcomeNote()

    messages = forget_session_subagents(b, CODEX_SESSION, outcome=note)

    assert messages == [
        f"forgot 1 sub-agent listed as working ({WORKER}) of ended session "
        f"{CODEX_SESSION} at {a}"
    ]
    assert (note.action, note.harness, note.session_id) == (
        "forgotten",
        "codex",
        CODEX_SESSION,
    )
    assert blockers(b, live, a, b) == []
    assert forget_session_subagents(b, CODEX_SESSION, harness="codex") == [
        f"no ended session {CODEX_SESSION} lists sub-agents in this Repository"
    ]


def test_forget_leaves_a_live_sessions_workers_listed(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    publish(a, "SubagentStart", WORKER)
    note = OutcomeNote()

    messages = forget_session_subagents(a, CODEX_SESSION, outcome=note)

    assert messages == [
        f"no ended session {CODEX_SESSION} lists sub-agents in this Repository"
    ]
    assert note.action is None
    record = stored(a)
    assert record is not None
    assert record["liveSubagents"] == [WORKER]


def test_forget_keeps_a_record_a_hook_changed_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())
    monkeypatch.setattr(HookRecordStore, "prune", lambda *_args: False)
    note = OutcomeNote()

    messages = forget_session_subagents(a, CODEX_SESSION, outcome=note)

    assert messages == [
        f"the record of session {CODEX_SESSION} at {a} changed while it was "
        f"read; nothing of it was forgotten: run the command again"
    ]
    assert (note.action, note.result()) == (None, "failed")


def test_forget_reports_records_it_cannot_read(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())
    session_directory(a).joinpath(f"{CODEX_SESSION}.json").write_text("{")

    messages = forget_session_subagents(a, CODEX_SESSION, harness="codex")

    assert messages == [
        f"no ended session {CODEX_SESSION} lists sub-agents in this Repository",
        f"1 hook record(s) named {CODEX_SESSION} cannot be read and were left "
        f"as they are",
    ]


def test_forget_refuses_an_id_two_harnesses_ended_with(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    session_directory(a).mkdir(parents=True)
    for harness in ("codex", "claude-code"):
        store = HookRecordStore(session_directory(a))
        record = build_hook_record(
            {
                "session_id": CODEX_SESSION,
                "cwd": str(a),
                "hook_event_name": "SessionEnd",
            },
            process=DAEMON,
            harness=harness,
        )
        store.replace(
            session_storage_key(harness, CODEX_SESSION),
            {**record, "liveSubagents": [WORKER]},
        )

    with pytest.raises(IssueWorkError, match="choose one with --harness"):
        forget_session_subagents(a, CODEX_SESSION)


def test_a_later_end_elsewhere_leaves_the_kept_record_in_place(
    tmp_path: Path,
) -> None:
    # The lead resumes on the same daemon in another Worktree and ends there;
    # removing its older records never removes the one kept for its worker.
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    delegated_and_ended(a, Settlers())
    publish(b, "SessionStart")
    publish(b, "Stop")

    session_end(b, CODEX_SESSION, DAEMON, Settlers())

    assert stored(b) is None
    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("ended", [WORKER])
    (kept,) = blockers(b, live, a, b)
    assert kept.detail == ended_blocker_detail(a, WORKER, "1 sub-agent")


def test_a_stop_reaches_the_kept_record_after_the_lead_resumed_elsewhere(
    tmp_path: Path,
) -> None:
    # The lead resumes on the same daemon in another Worktree, whose live
    # record routes the worker's stop; the record its end kept still clears.
    a, b = two_worktrees(tmp_path)
    live = present(DAEMON)
    delegated_and_ended(a, Settlers())
    publish(b, "SessionStart")
    publish(b, "Stop")

    publish(b, "SubagentStop", WORKER)

    assert stored(a) is None
    record = stored(b)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("waiting", [])
    assert [one.kind for one in blockers(a, live, a, b)] == ["agent-run"]


def test_a_stop_from_another_host_leaves_the_kept_record_elsewhere(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    delegated_and_ended(a, Settlers())
    publish(b, "SessionStart", host=REPLACEMENT)

    publish(b, "SubagentStop", WORKER, host=REPLACEMENT)

    record = stored(a)
    assert record is not None
    assert (record["state"], record["liveSubagents"]) == ("ended", [WORKER])
