"""Live Relocation, child scope and a shared Host Process through the hook seam (ADR 0067)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn

import pytest

from dashpot.core.git import GitError
from dashpot.core.model import Harness
from dashpot.sessions import work_reconciliation
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecordStore,
    session_directory,
    state_directory,
)
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.work import (
    IssueWorkError,
    relocate_issue_work,
    start_issue_work,
    stop_issue_work,
)
from dashpot.sessions.work_store import WorkStore
from factories import CLAUDE, CODEX, EARLIER, LATER, hook_record
from helpers import absent, present, table_lookup, unobservable
from test_work import (
    CLAUDE_ENVIRON,
    CLAUDE_SESSION,
    CODEX_ENVIRON,
    CODEX_SESSION,
    codex_lookup,
    target,
    two_worktrees,
)

# A second root thread served by the same Codex Host Process.
SECOND_THREAD = "01a05099-1563-79a3-8504-e30d50949cb7"
SECOND_ENVIRON = {"CODEX_THREAD_ID": SECOND_THREAD}
OTHER_CODEX = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
FUTURE = "2099-01-01T00:00:00.000000Z"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(
    at: Path,
    event: str,
    *,
    session: str = CODEX_SESSION,
    harness: Harness = "codex",
    process: ProcessIdentity | None = CODEX,
    lookup: ProcessLookup = codex_lookup,
    **fields: Any,
) -> HookPublication:
    """Publish one hook event of ``session`` from the Host Process ``process`` at ``at``."""
    return publish_hook_event(
        {"session_id": session, "cwd": str(at), "hook_event_name": event, **fields},
        process=process,
        harness=harness,
        lookup=lookup,
    )


def codex_run(
    at: Path, *, session: str = CODEX_SESSION, issue: str = "build-observer"
) -> None:
    hook_record(at, session, "codex", CODEX)
    start_issue_work(
        at, issue, lookup=codex_lookup, environ={"CODEX_THREAD_ID": session}
    )


def stored(store: Path, session: str = CODEX_SESSION) -> dict[str, Any] | None:
    path = store / f"{session}.json"
    return json.loads(path.read_text()) if path.exists() else None


def recorded(store: Path, session: str = CODEX_SESSION) -> dict[str, Any]:
    record = stored(store, session)
    assert record is not None, f"no record of {session} in {store}"
    return record


def third_worktree(a: Path, tmp_path: Path) -> Path:
    c = (tmp_path / "repo-third").resolve()
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "third", str(c)], cwd=a, check=True
    )
    return c


def observe(*worktrees: Path, lookup: ProcessLookup = codex_lookup) -> tuple[Any, Any]:
    return observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup,
    )


# --- The carry ---------------------------------------------------------------


def test_a_turn_at_another_worktree_carries_the_run_there(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]

    publication = publish(b, "UserPromptSubmit")

    assert (publication.work, publication.issue_id) == ("relocated", before.issue_id)
    assert WorkStore(a).active()[0] == []
    (carried,) = WorkStore(b).active()[0]
    assert (carried.session_key, carried.run_id, carried.started_at) == (
        before.session_key,
        before.run_id,
        before.started_at,
    )
    assert (carried.issue_id, carried.binding_provenance) == (
        before.issue_id,
        before.binding_provenance,
    )
    assert (carried.working_directory, carried.branch) == (str(b), "linked")
    assert carried.session_process == before.session_process
    runs, diagnostics = observe(a, b)
    assert [(run.observation_target, run.issue_id) for run in runs] == [
        (str(b), "I_observer")
    ]
    assert diagnostics == []


def test_an_unbound_session_stays_unbound_when_it_moves(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    stop_issue_work(a, lookup=codex_lookup, environ=CODEX_ENVIRON)

    publication = publish(b, "UserPromptSubmit")

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == []


def test_evidence_that_is_not_designated_leaves_the_run_and_says_so(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]

    # A Stop at B is where the turn ended, not where the harness placed it.
    assert publish(b, "Stop").work == "unchanged"

    assert WorkStore(a).active()[0] == [before]
    _runs, diagnostics = observe(a, b)
    assert [item.code for item in diagnostics] == ["work-session-elsewhere"]
    assert str(b) in diagnostics[0].message
    assert str(a) in diagnostics[0].message
    assert "dashpot work start" in diagnostics[0].message
    # The next turn there is designated, and carries it.
    assert publish(b, "UserPromptSubmit").work == "relocated"
    assert observe(a, b)[1] == []


def test_a_late_stop_from_the_origin_does_not_move_the_run_back(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    publish(b, "UserPromptSubmit")

    assert publish(a, "Stop").work == "unchanged"

    assert WorkStore(a).active()[0] == []
    assert len(WorkStore(b).active()[0]) == 1


def test_another_host_process_cannot_carry_the_run(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]

    publication = publish(
        b,
        "UserPromptSubmit",
        process=OTHER_CODEX,
        lookup=table_lookup({CODEX.pid: CODEX, OTHER_CODEX.pid: OTHER_CODEX}),
    )

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == [before]
    assert WorkStore(b).active()[0] == []


def test_an_unobserved_host_process_cannot_carry_the_run(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)

    publication = publish(
        b, "UserPromptSubmit", process=None, lookup=unobservable("isolated-namespace")
    )

    assert publication.work == "unchanged"
    assert len(WorkStore(a).active()[0]) == 1


def test_a_new_incarnation_at_the_target_is_a_restart_not_a_move(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]

    publish(b, "SessionStart")
    publication = publish(b, "UserPromptSubmit")

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == [before]
    assert recorded(session_directory(b))["lastSessionStartAt"] is not None


def test_a_newer_record_elsewhere_refuses_the_carry(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    # Evidence from A arrived after this event was stamped: it is stale.
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=FUTURE)

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    assert len(WorkStore(a).active()[0]) == 1


def test_an_unreadable_record_of_the_session_refuses_the_carry(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    unreadable = state_directory() / f"{CODEX_SESSION}.json"
    unreadable.parent.mkdir(parents=True, exist_ok=True)
    unreadable.write_text("not json")

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    assert len(WorkStore(a).active()[0]) == 1


def test_a_competing_run_at_the_target_refuses_the_carry(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]
    competing = replace(before, session_key="codex-competing")
    WorkStore(b).start(competing)

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    assert WorkStore(a).active()[0] == [before]
    assert WorkStore(b).active()[0] == [competing]


def test_an_unreadable_or_unresolved_record_at_the_target_refuses_the_carry(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]
    unreadable = WorkStore(b).record_path("codex-unreadable")
    unreadable.parent.mkdir(parents=True)
    unreadable.write_text("not json")

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    unreadable.unlink()
    # A legacy record naming no session may be this session's.
    WorkStore(b).start(
        replace(before, session_key="codex-4242-legacy", session_id=None)
    )
    assert publish(b, "UserPromptSubmit").work == "unchanged"
    assert WorkStore(a).active()[0] == [before]


def test_a_run_recorded_by_another_host_process_is_not_carried(
    tmp_path: Path,
) -> None:
    # The session resumed at A in a new Codex process, which never continues
    # a Codex run (ADR 0053); a move by that process cannot carry it either.
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]
    hook_record(a, CODEX_SESSION, "codex", OTHER_CODEX, at=LATER)
    lookup = table_lookup({OTHER_CODEX.pid: OTHER_CODEX})

    publication = publish(b, "UserPromptSubmit", process=OTHER_CODEX, lookup=lookup)

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == [before]


def test_a_run_at_a_worktree_the_session_did_not_leave_is_not_carried(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    c = third_worktree(a, tmp_path)
    codex_run(c)
    (before,) = WorkStore(c).active()[0]
    # The session's record at A is fresher than C's: it came to B from A.
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=LATER)

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    assert WorkStore(c).active()[0] == [before]


@pytest.mark.parametrize("method", ["active", "complete_relocation"])
def test_an_unusable_work_store_never_breaks_the_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    before = WorkStore(a).active()

    def refuse(*_args: object) -> NoReturn:
        raise OSError("read-only file system")

    with monkeypatch.context() as patched:
        patched.setattr(WorkStore, method, refuse)
        publication = publish(b, "UserPromptSubmit")

    assert publication.work == "unchanged"
    assert WorkStore(a).active() == before


def test_a_record_replaced_before_the_carry_locks_decides_for_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Between H's write and the carry's locks, a concurrent SessionEnd at B
    # removed H: the carry sees H is no longer the session's and moves nothing.
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    write = HookRecordStore.write

    def write_then_lose(
        store: HookRecordStore, record: dict[str, Any], **options: Any
    ) -> Path:
        destination = write(store, record, **options)
        destination.unlink()
        return destination

    with monkeypatch.context() as patched:
        patched.setattr(HookRecordStore, "write", write_then_lose)
        publication = publish(b, "UserPromptSubmit")

    assert publication.work == "unchanged"
    assert len(WorkStore(a).active()[0]) == 1


def test_evidence_outside_any_repository_carries_nothing(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    codex_run(a)
    outside = tmp_path / "outside"
    outside.mkdir()

    assert publish(outside, "UserPromptSubmit").work == "unchanged"

    assert len(WorkStore(a).active()[0]) == 1


def test_a_repository_git_cannot_list_reconciles_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)

    def unlistable(*_args: object, **_options: object) -> NoReturn:
        raise GitError(["git", "worktree", "list"], b, returncode=128)

    with monkeypatch.context() as patched:
        patched.setattr(work_reconciliation, "repository_worktrees", unlistable)
        publication = publish(b, "SessionEnd")

    assert publication.work == "unchanged"
    assert len(WorkStore(a).active()[0]) == 1


def test_a_carry_finishes_the_crash_pair_it_left(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]
    copy = replace(before, working_directory=str(b), branch="linked", relocation=None)
    WorkStore(b).start(copy)

    assert publish(b, "UserPromptSubmit").work == "relocated"

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == [copy]


def test_a_carry_completes_a_relocation_intent_naming_its_target(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)

    assert publish(b, "UserPromptSubmit").work == "relocated"

    (carried,) = WorkStore(b).active()[0]
    assert carried.relocation is None
    assert observe(a, b)[1] == []


def test_a_relocation_intent_naming_another_worktree_blocks_the_carry(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    c = third_worktree(a, tmp_path)
    codex_run(a)
    relocate_issue_work(a, c, lookup=codex_lookup, environ=CODEX_ENVIRON)

    assert publish(b, "UserPromptSubmit").work == "unchanged"

    assert len(WorkStore(a).active()[0]) == 1
    _runs, diagnostics = observe(a, b, c)
    # The freshest record says where the session went, though A's is live.
    assert [item.code for item in diagnostics] == ["work-relocation-mismatched"]
    assert str(b) in diagnostics[0].message
    assert str(c) in diagnostics[0].message


def test_a_declared_cold_resume_still_completes_its_relocation(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]
    publish(a, "SessionEnd")

    publication = publish(
        b,
        "SessionStart",
        process=OTHER_CODEX,
        lookup=table_lookup({OTHER_CODEX.pid: OTHER_CODEX}),
    )

    assert publication.work == "relocated"
    (moved,) = WorkStore(b).active()[0]
    assert (moved.run_id, moved.started_at) == (before.run_id, before.started_at)


# --- Two root threads on one Host Process ------------------------------------


@pytest.mark.parametrize("apart", [False, True], ids=["same-worktree", "two-worktrees"])
def test_one_threads_session_end_leaves_the_other_thread_alone(
    tmp_path: Path, apart: bool
) -> None:
    a, b = two_worktrees(tmp_path)
    second_at = b if apart else a
    codex_run(a)
    codex_run(second_at, session=SECOND_THREAD, issue="fix-crash")

    publication = publish(a, "SessionEnd")

    assert publication.work == "ended"
    remaining = [item for root in {a, b} for item in WorkStore(root).active()[0]]
    assert [(item.session_id, item.issue_id) for item in remaining] == [
        (SECOND_THREAD, "I_crash")
    ]
    assert Path(remaining[0].working_directory) == second_at
    runs, diagnostics = observe(a, b)
    assert [(run.session_id, run.state) for run in runs] == [(SECOND_THREAD, "running")]
    assert diagnostics == []


def test_one_thread_moving_carries_only_its_own_run(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    codex_run(b, session=SECOND_THREAD, issue="fix-crash")

    assert publish(b, "UserPromptSubmit").work == "relocated"

    assert sorted(item.issue_id for item in WorkStore(b).active()[0]) == [
        "I_crash",
        "I_observer",
    ]
    runs, diagnostics = observe(a, b)
    assert {run.observation_target for run in runs} == {str(b)}
    assert diagnostics == []


def test_a_shared_host_process_never_continues_a_run(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]

    publication = publish(
        a,
        "SessionStart",
        process=OTHER_CODEX,
        lookup=table_lookup({OTHER_CODEX.pid: OTHER_CODEX}),
    )

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == [before]


# --- SessionEnd removes the session's older records --------------------------


def test_session_end_removes_the_record_a_move_left_behind(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    publish(b, "UserPromptSubmit")
    assert stored(session_directory(a)) is not None

    publish(b, "SessionEnd")

    # The daemon outlives the thread; nothing it left may read live at A.
    assert stored(session_directory(a)) is None
    assert stored(session_directory(b)) is None
    assert observe(a, b) == ([], [])


def test_session_end_keeps_another_processs_record(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", OTHER_CODEX)
    publish(b, "UserPromptSubmit")

    publish(b, "SessionEnd")

    assert stored(session_directory(a)) is not None


def test_session_end_keeps_a_record_written_after_it(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    publish(b, "UserPromptSubmit")
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=FUTURE)

    publish(b, "SessionEnd")

    assert stored(session_directory(a)) is not None


def test_an_unobserved_session_end_removes_nothing_elsewhere(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)

    publish(b, "SessionEnd", process=None, lookup=unobservable("isolated-namespace"))

    assert stored(session_directory(a)) is not None
    # Unknown is never gone: the record reads unknown, not ended.
    runs, _diagnostics = observe(a, b, lookup=unobservable("isolated-namespace"))
    assert [(run.session_id, run.state) for run in runs] == [(CODEX_SESSION, "unknown")]


# --- Delegated threads are child-scoped --------------------------------------


def test_a_sub_agent_turn_never_places_or_carries_its_parent(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    publish(a, "Stop")
    (before,) = WorkStore(a).active()[0]

    publication = publish(b, "UserPromptSubmit", agent_id="child-thread")

    assert (publication.state, publication.work) == ("running", "unchanged")
    assert WorkStore(a).active()[0] == [before]
    assert stored(session_directory(b)) is None
    parent = recorded(session_directory(a))
    assert (parent["cwd"], parent["repositoryRoot"], parent["state"]) == (
        str(a),
        str(a),
        "waiting",
    )
    assert parent["turnStartedAt"] is None


def test_a_codex_sub_agent_holds_its_parent_running(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    codex_run(a)
    publish(a, "UserPromptSubmit")
    publish(a, "SubagentStart", agent_id="child-thread")
    publish(a, "Stop")

    parent = recorded(session_directory(a))
    assert (parent["state"], parent["liveSubagents"]) == ("running", ["child-thread"])
    publish(a, "SubagentStop", agent_id="child-thread")
    assert recorded(session_directory(a))["state"] == "waiting"


def test_a_sub_agents_end_never_ends_its_parent(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    codex_run(a)

    publication = publish(a, "SessionEnd", agent_id="child-thread")

    assert publication.work == "unchanged"
    assert len(WorkStore(a).active()[0]) == 1
    assert stored(session_directory(a)) is not None


def test_a_delegated_thread_does_not_inherit_its_parents_binding(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    codex_run(a)
    publish(a, "UserPromptSubmit", agent_id="child-thread")

    # The child's shell claims its own thread id, which no hook confirms.
    with pytest.raises(IssueWorkError):
        start_issue_work(
            a,
            "fix-crash",
            lookup=codex_lookup,
            environ={"CODEX_THREAD_ID": "child-thread"},
        )

    assert [item.issue_id for item in WorkStore(a).active()[0]] == ["I_observer"]
    assert stored(session_directory(a), "child-thread") is None


def test_a_sub_agent_with_no_reachable_parent_is_routed_by_its_own_cwd(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)

    publish(a, "SubagentStart", agent_id="child-thread")

    assert recorded(session_directory(a))["liveSubagents"] == ["child-thread"]


@pytest.mark.parametrize("event", ["SessionEnd", "UserPromptSubmit", "Stop"])
def test_a_sub_agent_event_with_no_parent_record_invents_no_parent(
    tmp_path: Path, event: str
) -> None:
    a, _b = two_worktrees(tmp_path)

    publication = publish(a, event, agent_id="child-thread")

    assert publication.work == "unchanged"
    assert stored(session_directory(a)) is None
    assert observe(a) == ([], [])


def test_an_isolated_claude_sub_agent_never_places_its_parent(tmp_path: Path) -> None:
    # A Claude sub-agent run with ``isolation: "worktree"`` reports its own
    # Worktree as its hook cwd (#358); it must not place its parent there.
    a, b = two_worktrees(tmp_path)
    hook_record(a, CLAUDE_SESSION, "claude-code", CLAUDE)
    start_issue_work(
        a, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )

    for event, fields in (
        ("SubagentStart", {}),
        ("PostToolUse", {"tool_name": "Bash"}),
    ):
        publish(
            b,
            event,
            session=CLAUDE_SESSION,
            harness="claude-code",
            process=CLAUDE,
            lookup=present(CLAUDE),
            agent_id="isolated",
            **fields,
        )

    assert stored(session_directory(b), CLAUDE_SESSION) is None
    parent = recorded(session_directory(a), CLAUDE_SESSION)
    assert (parent["cwd"], parent["liveSubagents"]) == (str(a), ["isolated"])
    runs, diagnostics = observe(a, b, lookup=present(CLAUDE))
    assert [run.observation_target for run in runs] == [str(a)]
    assert diagnostics == []


# --- Seeding a move ----------------------------------------------------------


def test_a_move_carries_the_live_sub_agents_and_turn_clock(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    publish(b, "Stop")
    publish(a, "UserPromptSubmit")
    publish(a, "SubagentStart", agent_id="child-thread")
    turn = recorded(session_directory(a))["turnStartedAt"]

    publish(b, "UserPromptSubmit")

    # B's own older record knew nothing of the turn or the sub-agent; A's
    # seeded both.
    moved = recorded(session_directory(b))
    assert (moved["state"], moved["liveSubagents"]) == ("running", ["child-thread"])
    assert moved["turnStartedAt"] == turn
    publish(b, "Stop")
    assert recorded(session_directory(b))["state"] == "running"


def test_a_reparented_host_still_seeds_the_move(tmp_path: Path) -> None:
    # The daemon a terminal autostarted outlives it under a new parent; the
    # Host Process is its pid and start time, not its parent or arguments.
    a, b = two_worktrees(tmp_path)
    launched = replace(CODEX, parent_pid=4100, arguments="app-server --listen")
    reparented = replace(CODEX, parent_pid=1, arguments="app-server --managed-daemon")
    publish(b, "Stop", process=launched, lookup=present(launched))
    publish(a, "UserPromptSubmit", process=launched, lookup=present(launched))
    publish(
        a,
        "SubagentStart",
        agent_id="child-thread",
        process=launched,
        lookup=present(launched),
    )
    turn = recorded(session_directory(a))["turnStartedAt"]

    publish(b, "UserPromptSubmit", process=reparented, lookup=present(reparented))

    moved = recorded(session_directory(b))
    assert (moved["state"], moved["liveSubagents"]) == ("running", ["child-thread"])
    assert moved["turnStartedAt"] == turn


def test_a_reused_pid_seeds_nothing(tmp_path: Path) -> None:
    # The same pid with another start time is another Host Process.
    a, b = two_worktrees(tmp_path)
    reused = replace(CODEX, started_at="Sun Sep 06 05:20:00 2026")
    publish(b, "Stop")
    publish(a, "UserPromptSubmit")
    publish(a, "SubagentStart", agent_id="child-thread")
    turn = recorded(session_directory(a))["turnStartedAt"]

    publish(b, "UserPromptSubmit", process=reused, lookup=present(reused))

    moved = recorded(session_directory(b))
    assert moved["liveSubagents"] == []
    assert moved["turnStartedAt"] != turn


def test_another_processs_record_seeds_nothing(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", OTHER_CODEX)
    publish(
        a,
        "SubagentStart",
        agent_id="child-thread",
        process=OTHER_CODEX,
        lookup=present(OTHER_CODEX),
    )

    publish(b, "Stop")

    moved = recorded(session_directory(b))
    assert (moved["state"], moved["liveSubagents"]) == ("waiting", [])


# --- A gone session ---------------------------------------------------------


def test_a_gone_session_left_elsewhere_is_orphaned_not_elsewhere(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    hook_record(b, CODEX_SESSION, "codex", CODEX, at=EARLIER)

    runs, diagnostics = observe(a, b, lookup=absent())

    assert [run.orphaned for run in runs] == [True]
    assert "work-session-elsewhere" not in {item.code for item in diagnostics}
