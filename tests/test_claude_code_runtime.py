"""Claude Code clients and supervised workers through the shared runtime model (ADR 0067).

Each scenario follows what the #162 acceptance run measured at Claude Code
2.1.286 (``docs/spikes/measurements/issue-162-claude-trace.jsonl``), driven through
the hook publisher with a fake process lookup.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dashpot import hook
from dashpot.core.event_log import EventLogDestination
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import session_directory, state_directory
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.work import start_issue_work
from dashpot.sessions.work_store import RelocationIntent, SessionProcess, WorkStore
from factories import CLAUDE, CODEX, EARLIER, hook_record
from helpers import present, table_lookup, unobservable
from test_event_logs import written
from test_live_relocation import recorded, stored
from test_work import (
    CLAUDE_ENVIRON,
    CLAUDE_SESSION,
    CODEX_ENVIRON,
    CODEX_SESSION,
    DIRECT_WORKER,
    EXECUTABLE,
    RESUMED_WORKER,
    SHELL_PID,
    SPARE_WORKER,
    SUPERVISOR,
    WORKER_ENVIRON,
    codex_lookup,
    linked_worktree,
    repository,
    target,
    two_worktrees,
)

# A second worker under the same supervisor, hosting a session of its own.
OTHER_SESSION = "5d527e10-0bc9-4798-a873-7034b8710a6e"
OTHER_WORKER = ProcessIdentity(
    5500,
    5490,
    "2.1.285",
    "Thu Oct 01 09:01:00 2026",
    f"{EXECUTABLE} --session-id {OTHER_SESSION} add the export --name other",
)
OTHER_ENVIRON = {
    "CLAUDE_CODE_SESSION_ID": OTHER_SESSION,
    "CLAUDE_PID": str(OTHER_WORKER.pid),
}


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


@pytest.fixture
def shell_below(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ProcessLookup]:
    """Build a lookup whose ancestry walk meets ``host`` just above a shell.

    ``running`` are the other processes still alive; every other PID is gone.
    """
    monkeypatch.setattr("dashpot.sessions.processes.os.getppid", lambda: SHELL_PID)

    def lookup(host: ProcessIdentity, *running: ProcessIdentity) -> ProcessLookup:
        shell = ProcessIdentity(SHELL_PID, host.pid, "bash", host.started_at)
        return table_lookup(
            {process.pid: process for process in (shell, host, *running)}
        )

    return lookup


def claude(
    at: Path,
    event: str,
    *,
    process: ProcessIdentity | None = CLAUDE,
    lookup: ProcessLookup | None = None,
    session: str = CLAUDE_SESSION,
    **fields: Any,
) -> HookPublication:
    """Publish one Claude Code hook event of ``session`` at ``at``.

    With no ``process`` the publisher locates the Host Process itself, as it
    does below a supervised worker.
    """
    return publish_hook_event(
        {"session_id": session, "cwd": str(at), "hook_event_name": event, **fields},
        process=process,
        harness="claude-code",
        lookup=lookup if lookup is not None else present(CLAUDE),
    )


def enter(at: Path, **options: Any) -> HookPublication:
    """Publish ``EnterWorktree``'s ``PostToolUse`` arriving at ``at``."""
    return claude(at, "PostToolUse", tool_name="EnterWorktree", **options)


def leave(at: Path, action: str = "keep", **options: Any) -> HookPublication:
    """Publish ``ExitWorktree``'s ``PostToolUse`` arriving back at ``at``."""
    return claude(
        at,
        "PostToolUse",
        tool_name="ExitWorktree",
        tool_input={"action": action},
        **options,
    )


def client_run(at: Path) -> None:
    """Bind a headless client's session at ``at``, as ``work start`` does."""
    hook_record(at, CLAUDE_SESSION, "claude-code", CLAUDE)
    start_issue_work(
        at, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )


def observe(*worktrees: Path, lookup: ProcessLookup | None = None) -> tuple[Any, Any]:
    return observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup if lookup is not None else present(CLAUDE),
    )


def placed(*worktrees: Path, lookup: ProcessLookup | None = None) -> list[Any]:
    """Each observed run as (Worktree, Issue, orphaned)."""
    runs, _diagnostics = observe(*worktrees, lookup=lookup)
    return sorted(
        (run.observation_target, run.issue_id, run.orphaned)
        for run in runs
        if run.issue_id
    )


def codes(*worktrees: Path, lookup: ProcessLookup | None = None) -> list[str]:
    return [item.code for item in observe(*worktrees, lookup=lookup)[1]]


# --- A client moved by its worktree tools (ADR 0074) ------------------------


def test_enter_worktree_carries_a_bound_sessions_run(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    client_run(a)
    (before,) = WorkStore(a).active()[0]

    publication = enter(b)

    assert (publication.work, publication.issue_id) == ("relocated", "I_observer")
    assert WorkStore(a).active()[0] == []
    (carried,) = WorkStore(b).active()[0]
    assert (carried.run_id, carried.started_at, carried.session_process) == (
        before.run_id,
        before.started_at,
        before.session_process,
    )
    assert placed(a, b) == [(str(b), "I_observer", False)]
    assert codes(a, b) == []


def test_exit_worktree_keep_carries_the_run_back(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    client_run(a)
    enter(b)

    publication = leave(a)

    assert (publication.work, publication.issue_id) == ("relocated", "I_observer")
    assert placed(a, b) == [(str(a), "I_observer", False)]
    assert codes(a, b) == []


def test_exit_worktree_remove_carries_nothing(tmp_path: Path) -> None:
    # Measured, ``remove`` deletes the Worktree it leaves, and the run with
    # its Work Store; where the Worktree survives, the run stays put.
    a, b = two_worktrees(tmp_path)
    client_run(a)
    enter(b)

    assert leave(a, "remove").work == "unchanged"

    assert placed(a, b) == [(str(b), "I_observer", False)]
    assert codes(a, b) == ["work-session-elsewhere"]


def test_an_unbound_session_moved_by_its_worktree_tools_stays_unbound(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CLAUDE_SESSION, "claude-code", CLAUDE)

    assert enter(b).work == "unchanged"
    assert leave(a).work == "unchanged"

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == []


def test_a_persistent_shell_cd_places_the_session_but_never_carries_its_run(
    tmp_path: Path,
) -> None:
    a = repository(tmp_path / "repo").resolve()
    nested = linked_worktree(a, a / "nested", "nested")
    client_run(a)

    # After ``cd nested`` in the session's shell, its hooks report the nested
    # Worktree; none of them is designated location evidence.
    claude(a, "UserPromptSubmit")
    assert claude(nested, "Stop").work == "unchanged"
    assert claude(nested, "UserPromptSubmit").work == "unchanged"

    assert recorded(session_directory(nested), CLAUDE_SESSION)["cwd"] == str(nested)
    assert placed(a, nested) == [(str(a), "I_observer", False)]
    _runs, diagnostics = observe(a, nested)
    assert [item.code for item in diagnostics] == ["work-session-elsewhere"]
    assert str(nested) in diagnostics[0].message
    # ``work start`` where the session now is takes the run there.
    start_issue_work(
        nested, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )
    assert placed(a, nested) == [(str(nested), "I_observer", False)]
    assert codes(a, nested) == []


def test_a_sub_agents_worktree_tool_never_carries_its_parent(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    client_run(a)

    assert enter(b, agent_id="isolated").work == "unchanged"

    assert placed(a, b) == [(str(a), "I_observer", False)]
    assert stored(session_directory(b), CLAUDE_SESSION) is None


def test_session_end_after_a_carry_ends_the_run_and_removes_the_origin_record(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    client_run(a)
    claude(a, "Stop")
    enter(b)
    assert stored(session_directory(a), CLAUDE_SESSION) is not None

    publication = claude(b, "SessionEnd", reason="other")

    assert (publication.work, publication.issue_id) == ("ended", "I_observer")
    assert WorkStore(a).active() == ([], [])
    assert WorkStore(b).active() == ([], [])
    assert stored(session_directory(a), CLAUDE_SESSION) is None
    assert observe(a, b) == ([], [])


def test_an_unobserved_host_process_carries_nothing(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    client_run(a)

    publication = enter(
        b, process=None, lookup=unobservable("ps is not permitted here")
    )

    assert publication.work == "unchanged"
    assert placed(a, b) == [(str(a), "I_observer", False)]


# --- Supervised workers (ADR 0067) ------------------------------------------


def worker(
    at: Path, lookup: ProcessLookup, event: str, **fields: Any
) -> HookPublication:
    """Publish ``event`` from a hook command below a supervised worker."""
    return claude(at, event, process=None, lookup=lookup, **fields)


def worker_run(at: Path, lookup: ProcessLookup) -> None:
    worker(at, lookup, "SessionStart", source="startup")
    start_issue_work(at, "build-observer", lookup=lookup, environ=WORKER_ENVIRON)


def test_a_supervised_worker_carries_its_run_into_a_worktree(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a, b = two_worktrees(tmp_path)
    alive = shell_below(DIRECT_WORKER, SUPERVISOR)
    worker_run(a, alive)

    publication = worker(b, alive, "PostToolUse", tool_name="EnterWorktree")

    assert (publication.work, publication.issue_id) == ("relocated", "I_observer")
    assert placed(a, b, lookup=alive) == [(str(b), "I_observer", False)]


def replaced_before_its_turn(
    tmp_path: Path,
    shell_below: Callable[..., ProcessLookup],
    replacement: ProcessIdentity = RESUMED_WORKER,
) -> tuple[Path, Path, ProcessLookup]:
    """A worker carried to B, killed, and replaced, with no turn since.

    Measured at 2.1.286: the replacement runs in the Worktree its predecessor
    entered, but its ``SessionStart`` reports the launch directory, so it
    continues nothing.
    """
    a, b = two_worktrees(tmp_path)
    worker_run(a, shell_below(DIRECT_WORKER, SUPERVISOR))
    worker(b, shell_below(DIRECT_WORKER), "PostToolUse", tool_name="EnterWorktree")
    worker(b, shell_below(DIRECT_WORKER), "Stop")
    replaced = shell_below(replacement, SUPERVISOR)
    assert worker(a, replaced, "SessionStart", source="resume").work == "unchanged"
    return a, b, replaced


@pytest.mark.parametrize(
    "replacement",
    [
        pytest.param(RESUMED_WORKER, id="resumed-from-its-transcript"),
        pytest.param(SPARE_WORKER, id="replaced-in-a-spare"),
    ],
)
def test_a_replaced_worker_continues_its_run_at_its_next_turn(
    tmp_path: Path,
    shell_below: Callable[..., ProcessLookup],
    replacement: ProcessIdentity,
) -> None:
    a, b, replaced = replaced_before_its_turn(tmp_path, shell_below, replacement)
    (before,) = WorkStore(b).active()[0]
    assert placed(a, b, lookup=replaced) == [(str(b), "I_observer", True)]

    publication = worker(b, replaced, "UserPromptSubmit")

    assert (publication.work, publication.issue_id) == ("continued", "I_observer")
    (after,) = WorkStore(b).active()[0]
    assert (after.run_id, after.session_process) == (
        before.run_id,
        SessionProcess(pid=replacement.pid, started_at=replacement.started_at),
    )
    assert placed(a, b, lookup=replaced) == [(str(b), "I_observer", False)]


# --- A replacement's end ends its orphaned run (ADR 0075) -------------------


def test_a_replacements_session_end_ends_the_orphaned_run_it_holds(
    tmp_path: Path,
    shell_below: Callable[..., ProcessLookup],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    a, b, replaced = replaced_before_its_turn(tmp_path, shell_below)
    event = {
        "session_id": CLAUDE_SESSION,
        "cwd": str(b),
        "hook_event_name": "SessionEnd",
        "reason": "other",
    }

    publication = publish_hook_event(event, harness="claude-code", lookup=replaced)

    assert (publication.work, publication.issue_id) == ("ended", "I_observer")
    assert publication.continued is None
    assert WorkStore(b).active() == ([], [])
    assert placed(a, b, lookup=replaced) == []
    # The hook logs one outcome: the end, not a continuation followed by one.
    log = hook.hook_event_log(
        "claude-code", event, destination=EventLogDestination(tmp_path / "events")
    )
    log.start()
    hook.record_hook_outcome(log, event, publication, None)
    log.close()
    outcomes = [
        line
        for line in written(tmp_path / "events")
        if line["event.name"] == "hook.outcome"
    ]
    assert [
        (line["dashpot.work_store.change"], line["dashpot.issue.id"])
        for line in outcomes
    ] == [("ended", "I_observer")]


def test_a_replacements_session_end_elsewhere_leaves_the_orphaned_run(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a, b, replaced = replaced_before_its_turn(tmp_path, shell_below)

    publication = worker(a, replaced, "SessionEnd", reason="other")

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert placed(a, b, lookup=replaced) == [(str(b), "I_observer", True)]


@pytest.mark.parametrize(
    "predecessor",
    [
        pytest.param(lambda: present(DIRECT_WORKER), id="still-alive"),
        pytest.param(lambda: unobservable("ps is not permitted"), id="unobservable"),
    ],
)
def test_a_session_end_never_ends_a_run_whose_process_is_not_proved_gone(
    tmp_path: Path,
    shell_below: Callable[..., ProcessLookup],
    predecessor: Callable[[], ProcessLookup],
) -> None:
    a = repository(tmp_path / "repo").resolve()
    worker_run(a, shell_below(DIRECT_WORKER, SUPERVISOR))
    (before,) = WorkStore(a).active()[0]
    probe = predecessor()

    def lookup(pid: int) -> Any:
        # The ending process is located; the run's recorded one is not proved gone.
        if pid == DIRECT_WORKER.pid:
            return probe(pid)
        return shell_below(RESUMED_WORKER, SUPERVISOR)(pid)

    publication = worker(a, lookup, "SessionEnd", reason="other")

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert WorkStore(a).active()[0] == [before]


def test_a_session_end_leaves_a_run_with_a_pending_relocation(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a, b, replaced = replaced_before_its_turn(tmp_path, shell_below)
    store = WorkStore(b)
    (orphaned,) = store.active()[0]
    pending = replace(orphaned, relocation=RelocationIntent(str(a), EARLIER))
    assert store.replace_current(orphaned, pending)

    publication = worker(b, replaced, "SessionEnd", reason="other")

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert store.active()[0] == [pending]


def test_a_codex_session_end_continues_nothing(tmp_path: Path) -> None:
    # Codex threads share their app-server, so a new Host Process's end is
    # never taken for the run's own (ADR 0053).
    a = repository(tmp_path / "repo").resolve()
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]
    other = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")

    publication = publish_hook_event(
        {"session_id": CODEX_SESSION, "cwd": str(a), "hook_event_name": "SessionEnd"},
        process=other,
        harness="codex",
        lookup=table_lookup({other.pid: other}),
    )

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert WorkStore(a).active()[0] == [before]


def test_a_late_event_of_the_killed_worker_never_moves_or_ends_the_continued_run(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a, b = two_worktrees(tmp_path)
    worker_run(a, shell_below(DIRECT_WORKER, SUPERVISOR))
    replaced = shell_below(RESUMED_WORKER, SUPERVISOR)
    worker(a, replaced, "UserPromptSubmit")
    (continued,) = WorkStore(a).active()[0]
    assert continued.session_process == SessionProcess(
        pid=RESUMED_WORKER.pid, started_at=RESUMED_WORKER.started_at
    )

    # Events still in flight from the killed worker arrive afterwards.
    for event, fields in (
        ("PostToolUse", {"tool_name": "EnterWorktree"}),
        ("Stop", {}),
        ("SessionEnd", {"reason": "other"}),
    ):
        publication = claude(b, event, process=DIRECT_WORKER, lookup=replaced, **fields)
        assert publication.work == "unchanged", event

    assert WorkStore(a).active()[0] == [continued]
    assert placed(a, b, lookup=replaced) == [(str(a), "I_observer", False)]


def test_two_workers_under_one_supervisor_hold_their_runs_independently(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a, b = two_worktrees(tmp_path)
    first = shell_below(DIRECT_WORKER, OTHER_WORKER, SUPERVISOR)
    second = shell_below(OTHER_WORKER, DIRECT_WORKER, SUPERVISOR)
    worker_run(a, first)
    worker(a, second, "SessionStart", session=OTHER_SESSION, source="startup")
    start_issue_work(a, "fix-crash", lookup=second, environ=OTHER_ENVIRON)
    both = [(str(a), "I_crash", False), (str(a), "I_observer", False)]
    assert placed(a, b, lookup=first) == both
    # Replacing the supervisor publishes nothing and leaves each worker's
    # process, so with the old supervisor gone neither run changes.
    assert placed(a, b, lookup=shell_below(DIRECT_WORKER, OTHER_WORKER)) == both

    worker(b, first, "PostToolUse", tool_name="EnterWorktree")
    assert placed(a, b, lookup=first) == [
        (str(a), "I_crash", False),
        (str(b), "I_observer", False),
    ]
    worker(b, first, "SessionEnd", reason="other")

    assert placed(a, b, lookup=second) == [(str(a), "I_crash", False)]


def test_a_stopped_workers_respawn_finds_no_run(
    tmp_path: Path, shell_below: Callable[..., ProcessLookup]
) -> None:
    a = repository(tmp_path / "repo").resolve()
    worker_run(a, shell_below(DIRECT_WORKER, SUPERVISOR))
    # ``claude stop`` publishes SessionEnd ``other`` from the worker itself.
    assert worker(a, shell_below(DIRECT_WORKER), "SessionEnd", reason="other").work == (
        "ended"
    )

    respawned = shell_below(SPARE_WORKER, SUPERVISOR)
    publication = worker(a, respawned, "SessionStart", source="resume")

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert placed(a, lookup=respawned) == []
