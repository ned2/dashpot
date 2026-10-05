"""A Sub-agent stays listed while the Host Process that runs it lives (#460).

A second Host Process can take a session on while the first one's
Sub-agent works. #448 measured it at OpenCode 2.0.22 (its ``standalone``
order, ``docs/spikes/measurements/issue-448-opencode-trace.jsonl``
receipts 1083 to 1168): a ``--standalone`` client resumed a root whose
child the shared service ran, published its ``SessionStart``, and exited
while the child worked on. Each test replays such an order through the
publishers and reads it through the hook record, observation, ``work
show`` and ``assess_worktree_occupancy`` (ADR 0107).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import factories
from dashpot.core.model import AgentRun
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions import hook_publish
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecordStore,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import classify_hook_record
from dashpot.sessions.liveness import LivenessProbe
from dashpot.sessions.processes import ProcessIdentity, ProcessKey, ProcessLookup
from dashpot.sessions.work import show_issue_work, start_issue_work
from helpers import table_lookup
from test_opencode import CHILD, ROOT, SERVER, SHELL_PID, STANDALONE, Server
from test_work import CLAUDE_ENVIRON, CLAUDE_SESSION, linked_worktree, repository
from test_work import target as observation_target

# The processes as the shell's ancestry walk reads them: the shell is a
# direct child of the server, which is the walk's last harness process.
SERVICE = ProcessIdentity(
    SERVER.pid, 1, SERVER.command, SERVER.started_at, SERVER.arguments
)
CLIENT = ProcessIdentity(
    STANDALONE.pid, 1, STANDALONE.command, STANDALONE.started_at, STANDALONE.arguments
)
LEAD = factories.CLAUDE
# The process a `claude --resume` of the Lead's session runs in, beside the
# Lead's own, which still runs the Lead's background worker.
RESUMED = ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026")
WORKER = "a1b2c3d4e5f607182"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


@pytest.fixture
def shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every publisher run below the shell ``SHELL_PID``."""
    monkeypatch.setattr("dashpot.sessions.processes.os.getppid", lambda: SHELL_PID)


def running(host: ProcessIdentity, *beside: ProcessIdentity) -> ProcessLookup:
    """A process table whose shell is ``host``'s child, with ``beside`` running too."""
    shell = ProcessIdentity(SHELL_PID, host.pid, "bash", host.started_at)
    return table_lookup({one.pid: one for one in (shell, host, *beside)})


def alive(*processes: ProcessIdentity) -> ProcessLookup:
    """A process table of only ``processes``; every other PID is gone."""
    return table_lookup({one.pid: one for one in processes})


def record(at: Path, session: str) -> dict[str, Any]:
    """The session's hook record in ``at``'s store."""
    return stored_in(session_directory(at), session)


def stored_in(directory: Path, session: str = CLAUDE_SESSION) -> dict[str, Any]:
    """The session's hook record in the store ``directory``."""
    return json.loads((directory / f"{session}.json").read_text())


def sub_agent_blockers(
    path: Path, worktrees: list[Path], lookup: ProcessLookup
) -> list[str]:
    """The details of the ``sub-agent`` Cleanup blockers on ``path``."""
    return [
        blocker.detail
        for blocker in assess_worktree_occupancy(path, worktrees, lookup)
        if blocker.kind == "sub-agent"
    ]


def observed(lookup: ProcessLookup, *worktrees: Path) -> list[AgentRun]:
    """The Agent Runs one observation pass reports, which prunes as it goes."""
    runs, _diagnostics = observe_agent_runs(
        {"project:test": [observation_target(one) for one in worktrees]},
        state_directory(),
        lookup=lookup,
    )
    return runs


@pytest.fixture
def worktrees(tmp_path: Path) -> list[Path]:
    """A Project's main checkout and the linked Worktree Cleanup is asked about."""
    main = repository(tmp_path / "repo").resolve()
    linked = linked_worktree(main, tmp_path / "linked", "linked").resolve()
    return [main, linked]


def resumed_by_a_standalone_client(main: Path) -> tuple[Server, Server]:
    """#448's order up to the client's turn: the service's child works on."""
    service = Server(running(SERVICE, CLIENT), host=SERVICE)
    # Receipts 1083-1084: the root's turn starts its child, and the root's
    # execution ends while the child holds a command.
    service.turn(main)
    service.turn(main, CHILD, root=ROOT)
    service.finish(main)
    # Receipt 1108: the client resumes the root, beginning an incarnation in
    # its own server, and its execution starts.
    client = Server(running(CLIENT, SERVICE), host=CLIENT)
    client.sequences = dict(service.sequences)
    assert client.turn(main) == "accepted"
    return service, client


@pytest.mark.usefixtures("shell")
def test_a_standalone_resume_keeps_the_services_child_until_it_stops(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    service, client = resumed_by_a_standalone_client(main)

    resumed = record(main, ROOT)
    assert resumed["sessionProcess"]["pid"] == CLIENT.pid
    assert resumed["liveSubagents"] == [CHILD]
    assert {
        agent: host["pid"] for agent, host in resumed["subagentProcesses"].items()
    } == {CHILD: SERVICE.pid}
    both = alive(SERVICE, CLIENT)
    (blocker,) = sub_agent_blockers(linked, worktrees, both)
    assert f"({CHILD}; session live)" in blocker

    # Receipts 1124-1128: the client's last instance goes, it marks the root,
    # and it exits while the child still works.
    assert client.unobserved(main) == "accepted"
    exited = alive(SERVICE)
    (blocker,) = sub_agent_blockers(linked, worktrees, exited)
    assert f"({CHILD}; session gone)" in blocker
    # The gone record gets no run, and observation keeps it for the child.
    assert observed(exited, *worktrees) == []
    assert record(main, ROOT)["liveSubagents"] == [CHILD]

    # Receipt 1164: the child's end reaches the service, which begins the
    # root's incarnation there, then stops the child.
    assert service.finish(main, CHILD, root=ROOT) == "accepted"
    settled = record(main, ROOT)
    assert (settled["sessionProcess"]["pid"], settled["liveSubagents"]) == (
        SERVICE.pid,
        [],
    )
    assert "subagentProcesses" not in settled
    assert sub_agent_blockers(linked, worktrees, exited) == []


@pytest.mark.usefixtures("shell")
def test_the_gone_record_goes_once_the_service_exits_too(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    _service, client = resumed_by_a_standalone_client(main)
    client.unobserved(main)

    # The service exits too, its child with it, and no stop is reported.
    nothing = alive()
    assert sub_agent_blockers(linked, worktrees, nothing) == []
    assert observed(nothing, *worktrees) == []
    assert not (session_directory(main) / f"{ROOT}.json").exists()


def publish(
    at: Path,
    event: str,
    agent: str | None = None,
    *,
    host: ProcessIdentity = LEAD,
    lookup: ProcessLookup,
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
        payload, process=host, harness="claude-code", lookup=lookup
    )


def resumed_elsewhere(main: Path) -> ProcessLookup:
    """The Lead's worker works on in its process while ``RESUMED`` takes the session."""
    both = alive(LEAD, RESUMED)
    publish(main, "SessionStart", lookup=both, source="startup")
    publish(main, "UserPromptSubmit", lookup=both)
    start_issue_work(main, "build-observer", lookup=both, environ=CLAUDE_ENVIRON)
    publish(main, "SubagentStart", WORKER, lookup=both)
    publish(main, "Stop", lookup=both)
    publish(main, "SessionStart", host=RESUMED, lookup=both, source="resume")
    publish(main, "UserPromptSubmit", host=RESUMED, lookup=both)
    publish(main, "Stop", host=RESUMED, lookup=both)
    return both


def session_state(lookup: ProcessLookup, *worktrees: Path) -> str:
    """The state the Sessions pane shows for the Lead's session.

    That is its hook-observed run, or the Issue work run that claims the
    session's hook record when its Work Store run names the record's process.
    """
    runs = observed(lookup, *worktrees)
    hooked = [run for run in runs if run.id == f"claude-code-session:{CLAUDE_SESSION}"]
    (run,) = hooked or runs
    return run.state


def show_lines(main: Path, lookup: ProcessLookup) -> list[str]:
    """The ``work show`` lines that name a working sub-agent."""
    return [
        line
        for line in show_issue_work(main, lookup=lookup)
        if "listed as working" in line
    ]


def test_a_resumed_session_lists_the_old_processs_worker_as_before(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)

    resumed = record(main, CLAUDE_SESSION)
    assert (resumed["state"], resumed["liveSubagents"]) == ("running", [WORKER])
    assert resumed["subagentProcesses"][WORKER]["pid"] == LEAD.pid
    assert session_state(both, *worktrees) == "running"
    (shown,) = show_lines(main, both)
    assert f"({WORKER})" in shown
    (blocker,) = sub_agent_blockers(linked, worktrees, both)
    assert f"({WORKER}; session live)" in blocker

    # The worker's stop comes from the Lead's first process.
    publish(main, "SubagentStop", WORKER, lookup=both)

    stopped = record(main, CLAUDE_SESSION)
    assert (stopped["state"], stopped["liveSubagents"]) == ("waiting", [])
    # The record still names the process the session's own events named.
    assert stopped["sessionProcess"]["pid"] == RESUMED.pid
    assert "subagentProcesses" not in stopped
    assert session_state(both, *worktrees) == "waiting"
    assert show_lines(main, both) == []
    assert sub_agent_blockers(linked, worktrees, both) == []


def test_a_worker_whose_process_exits_unreported_stops_holding_the_session(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    resumed_elsewhere(main)

    # The Lead's first process exits, its worker with it, and no stop comes.
    left = alive(RESUMED)

    assert session_state(left, *worktrees) == "waiting"
    assert show_lines(main, left) == []
    assert sub_agent_blockers(linked, worktrees, left) == []
    # The next event of the session probes its process and drops it from
    # the record, whose stored state no longer counts it.
    publish(main, "Stop", host=RESUMED, lookup=left)
    stored = record(main, CLAUDE_SESSION)
    assert (stored["state"], stored["liveSubagents"]) == ("waiting", [])
    assert "subagentProcesses" not in stored


def test_the_workers_stop_clears_the_record_its_session_left_behind(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)
    # The resumed session's hooks move to the linked Worktree (ADR 0067).
    publish(linked, "UserPromptSubmit", host=RESUMED, lookup=both)
    assert record(linked, CLAUDE_SESSION)["liveSubagents"] == [WORKER]

    publish(main, "SubagentStop", WORKER, lookup=both)

    assert record(linked, CLAUDE_SESSION)["liveSubagents"] == []
    left = record(main, CLAUDE_SESSION)
    assert left["liveSubagents"] == []
    assert left["sessionProcess"]["pid"] == RESUMED.pid
    assert sub_agent_blockers(linked, worktrees, both) == []


SECOND = "a1b2c3d4e5f607183"


def raced_by_a_start(
    main: Path, monkeypatch: pytest.MonkeyPatch, lookup: ProcessLookup
) -> None:
    """``RESUMED``'s next turn, with the Lead's ``SECOND`` worker starting mid-write.

    The worker's ``SubagentStart`` lands after ``RESUMED``'s publisher read
    the session's records and probed their Host Processes, but before its
    write: the Lead's process is named nowhere it read, so it goes unprobed.
    """
    probe = hook_publish._gone_hosts
    raced: list[bool] = []

    def probed_then_raced(*args: Any) -> frozenset[ProcessKey]:
        gone = probe(*args)
        if not raced:
            raced.append(True)
            publish(main, "SubagentStart", SECOND, lookup=lookup)
        return gone

    monkeypatch.setattr(hook_publish, "_gone_hosts", probed_then_raced)
    publish(main, "UserPromptSubmit", host=RESUMED, lookup=lookup)
    monkeypatch.setattr(hook_publish, "_gone_hosts", probe)
    assert raced


def test_a_worker_tagged_after_the_probe_stays_listed(
    worktrees: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)
    publish(main, "SubagentStop", WORKER, lookup=both)
    assert record(main, CLAUDE_SESSION)["liveSubagents"] == []

    raced_by_a_start(main, monkeypatch, both)

    # The write did not probe the Lead's process, and carried its worker.
    raced = record(main, CLAUDE_SESSION)
    assert raced["liveSubagents"] == [SECOND]
    assert raced["subagentProcesses"][SECOND]["pid"] == LEAD.pid
    (blocker,) = sub_agent_blockers(linked, worktrees, both)
    assert f"({SECOND}; session live)" in blocker
    publish(main, "Stop", host=RESUMED, lookup=both)
    assert record(main, CLAUDE_SESSION)["state"] == "running"
    assert session_state(both, *worktrees) == "running"
    (shown,) = show_lines(main, both)
    assert f"({SECOND})" in shown


@pytest.mark.parametrize("stop_reported", [True, False])
def test_a_raced_worker_goes_once_its_process_exits(
    worktrees: list[Path], monkeypatch: pytest.MonkeyPatch, stop_reported: bool
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)
    publish(main, "SubagentStop", WORKER, lookup=both)
    raced_by_a_start(main, monkeypatch, both)
    if stop_reported:
        publish(main, "SubagentStop", SECOND, lookup=both)

    # The Lead's process exits; the next write probes it, as the records
    # now name it, and finds it gone.
    left = alive(RESUMED)
    publish(main, "Stop", host=RESUMED, lookup=left)

    settled = record(main, CLAUDE_SESSION)
    assert (settled["state"], settled["liveSubagents"]) == ("waiting", [])
    assert "subagentProcesses" not in settled
    assert session_state(left, *worktrees) == "waiting"
    assert show_lines(main, left) == []
    assert sub_agent_blockers(linked, worktrees, left) == []


def test_an_end_keeps_the_other_processs_worker_until_its_stop(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)

    publish(main, "SessionEnd", host=RESUMED, lookup=both, reason="exit")

    ended = record(main, CLAUDE_SESSION)
    assert (ended["state"], ended["liveSubagents"]) == ("ended", [WORKER])
    assert ended["subagentProcesses"][WORKER]["pid"] == LEAD.pid
    gone = alive(LEAD)
    (blocker,) = sub_agent_blockers(linked, worktrees, gone)
    assert f"ended with 1 sub-agent listed as working ({WORKER})" in blocker

    publish(main, "SubagentStop", WORKER, lookup=gone)

    assert not (session_directory(main) / f"{CLAUDE_SESSION}.json").exists()
    assert sub_agent_blockers(linked, worktrees, gone) == []


def test_the_first_process_takes_its_worker_back_on_its_own_start(
    worktrees: list[Path],
) -> None:
    main, linked = worktrees
    both = resumed_elsewhere(main)
    publish(main, "SessionEnd", host=RESUMED, lookup=both, reason="exit")
    gone = alive(LEAD)

    publish(main, "SessionStart", lookup=gone, source="resume")

    back = record(main, CLAUDE_SESSION)
    assert (back["sessionProcess"]["pid"], back["liveSubagents"]) == (
        LEAD.pid,
        [WORKER],
    )
    assert "subagentProcesses" not in back
    (blocker,) = sub_agent_blockers(linked, worktrees, gone)
    assert f"({WORKER}; session live)" in blocker


def test_a_start_where_the_old_process_is_gone_lists_none_of_its_workers(
    worktrees: list[Path],
) -> None:
    main, _linked = worktrees
    both = alive(LEAD, RESUMED)
    publish(main, "UserPromptSubmit", lookup=both)
    publish(main, "SubagentStart", WORKER, lookup=both)

    publish(main, "SessionStart", host=RESUMED, lookup=alive(RESUMED), source="resume")

    resumed = record(main, CLAUDE_SESSION)
    assert resumed["liveSubagents"] == []
    assert "subagentProcesses" not in resumed


def test_a_tagged_worker_of_a_gone_process_is_not_listed(tmp_path: Path) -> None:
    # The record's own process runs no turn; only the worker another process
    # runs held it running.
    raw = factories.hook_record_document(
        tmp_path, CLAUDE_SESSION, "claude-code", RESUMED, event="Stop"
    ) | {"liveSubagents": [WORKER], "subagentProcesses": {WORKER: LEAD.as_record()}}

    def classified(lookup: ProcessLookup) -> tuple[str, tuple[str, ...]]:
        found = classify_hook_record(raw, LivenessProbe(lookup))
        return found.state, found.live_subagents

    assert classified(alive(LEAD, RESUMED)) == ("running", (WORKER,))
    assert classified(alive(RESUMED)) == ("waiting", ())


def test_releasing_an_untagged_record_changes_only_its_list(tmp_path: Path) -> None:
    # A record of one Host Process, as every record before ADR 0107 was.
    second = SECOND
    store = HookRecordStore(tmp_path)
    before = factories.hook_record_document(
        tmp_path, CLAUDE_SESSION, "claude-code", LEAD, event="Stop"
    ) | {"liveSubagents": [WORKER, second], "turnStartedAt": None}
    store.replace(CLAUDE_SESSION, before)
    stop = {**before, "event": "SubagentStop", "agentId": WORKER}

    assert store.release_left_behind(CLAUDE_SESSION, [WORKER], stop) is True
    assert stored_in(tmp_path) == {**before, "liveSubagents": [second]}

    ended = {**before, "state": "ended", "event": "SessionEnd"}
    store.replace(CLAUDE_SESSION, ended)
    assert (
        store.release_subagents(
            CLAUDE_SESSION, [WORKER], stop, session_id=CLAUDE_SESSION
        )
        is True
    )
    assert stored_in(tmp_path) == {**ended, "liveSubagents": [second]}
    # Another process's stop changes nothing.
    other = {**stop, "sessionProcess": RESUMED.as_record()}
    assert (
        store.release_subagents(
            CLAUDE_SESSION, [second], other, session_id=CLAUDE_SESSION
        )
        is False
    )
    assert (
        store.release_subagents(
            CLAUDE_SESSION, [second], stop, session_id=CLAUDE_SESSION
        )
        is True
    )
    assert list(tmp_path.glob("*.json")) == []
