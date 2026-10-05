"""Live Relocation, child scope and a shared Host Process through the hook seam (ADR 0067)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest

from dashpot.core.git import GitError
from dashpot.core.model import Harness
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions import hook_records, work_reconciliation
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecord,
    HookRecordStore,
    HookRecordWrite,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import (
    locate_agent_session,
    reachable_hook_stores,
    sessions_at_worktree,
    sessions_with_live_subagents,
)
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.session_identity import IssueWorkError
from dashpot.sessions.work import (
    relocate_issue_work,
    show_issue_work,
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
        store: HookRecordStore, record: HookRecord, **options: Any
    ) -> HookRecordWrite:
        written = write(store, record, **options)
        written.path.unlink()
        return written

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

    # The parent's record keeps the state its own turn left (#489).
    assert (publication.state, publication.work) == ("waiting", "unchanged")
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


# --- Accepting the Live Relocation route (#278) ------------------------------

# Hook stamps either side of a carry, for evidence that arrives out of order.
BEFORE_THE_MOVE = LATER
AT_THE_MOVE = "2026-08-30T03:45:00.000000Z"
NO_WORK_HERE = ["no active Issue work at this worktree"]


@dataclass(frozen=True, slots=True)
class Mover:
    """One harness's session and the designated events that move it live."""

    harness: Harness
    session: str
    process: ProcessIdentity
    environ: dict[str, str]
    # The designated event's name, its fields for a move onward to another
    # Worktree, and its fields for a return to the Worktree the session left.
    event: str
    onward_fields: dict[str, Any]
    return_fields: dict[str, Any]

    @property
    def lookup(self) -> ProcessLookup:
        """A lookup that finds the session's Host Process at every PID."""
        return present(self.process)

    def publish(self, at: Path, event: str, **fields: Any) -> HookPublication:
        """Publish ``event`` of the session from its Host Process at ``at``."""
        return publish(
            at,
            event,
            session=self.session,
            harness=self.harness,
            process=self.process,
            lookup=self.lookup,
            **fields,
        )

    def bind(self, at: Path) -> None:
        """Start Issue work for the session at ``at``, as ``work start`` does."""
        hook_record(at, self.session, self.harness, self.process)
        start_issue_work(at, "build-observer", lookup=self.lookup, environ=self.environ)

    def place(self, at: Path) -> None:
        """Place the session at ``at`` with no Issue work."""
        hook_record(at, self.session, self.harness, self.process)

    def move(self, at: Path) -> HookPublication:
        """Publish the designated event of a move onward to ``at``."""
        return self.publish(at, self.event, **self.onward_fields)

    def move_back(self, at: Path) -> HookPublication:
        """Publish the designated event of a return to ``at``."""
        return self.publish(at, self.event, **self.return_fields)


MOVERS = [
    # A controller's ``turn/start`` with a ``cwd`` override: the next turn's
    # UserPromptSubmit is the first hook at the new Worktree.
    Mover(
        "codex",
        CODEX_SESSION,
        CODEX,
        CODEX_ENVIRON,
        "UserPromptSubmit",
        onward_fields={},
        return_fields={},
    ),
    # The worktree tools' PostToolUse arrives at the Worktree they moved to.
    Mover(
        "claude-code",
        CLAUDE_SESSION,
        CLAUDE,
        CLAUDE_ENVIRON,
        "PostToolUse",
        onward_fields={"tool_name": "EnterWorktree"},
        return_fields={"tool_name": "ExitWorktree", "tool_input": {"action": "keep"}},
    ),
]
movers = pytest.mark.parametrize(
    "mover", MOVERS, ids=[mover.harness for mover in MOVERS]
)


# Both Host Processes, each found only at its own PID, for a Worktree that a
# Codex thread shares with the session that moves.
BOTH_HOSTS = table_lookup({CODEX.pid: CODEX, CLAUDE.pid: CLAUDE})


def bystander_at(at: Path) -> list[Any]:
    """Bind another Codex thread at ``at``, and return the Work Store's runs there.

    Its run gives the Repository a Work Store outside the moving session's
    Worktree, so a carry looks for that session's run rather than stopping
    at an empty Repository.
    """
    codex_run(at, session=SECOND_THREAD, issue="fix-crash")
    return WorkStore(at).active()[0]


def stamp_hooks_at(monkeypatch: pytest.MonkeyPatch, at: str) -> None:
    """Stamp every hook record published from now on at ``at``.

    The publisher takes no clock, so this stands in for one: it orders two
    events' stamps apart from the order they are published in.
    """
    monkeypatch.setattr(hook_records, "utc_now", lambda: at)


@movers
def test_work_show_and_observation_report_the_carried_run_unchanged(
    tmp_path: Path, mover: Mover
) -> None:
    a, b = two_worktrees(tmp_path)
    mover.bind(a)
    (before,) = WorkStore(a).active()[0]
    shown_before = show_issue_work(a)

    assert mover.move(b).work == "relocated"

    # ``dashpot work show`` names the same run, Issue and ``startedAt`` at B.
    assert show_issue_work(b) == shown_before
    assert show_issue_work(a) == NO_WORK_HERE
    runs, diagnostics = observe(a, b, lookup=mover.lookup)
    assert [
        (run.id, run.observation_target, run.issue_id, run.started_at) for run in runs
    ] == [(before.run_id, str(b), before.issue_id, before.started_at)]
    assert diagnostics == []


@movers
def test_an_unbound_session_is_reported_unbound_at_its_new_worktree(
    tmp_path: Path, mover: Mover
) -> None:
    a, b = two_worktrees(tmp_path)
    others = bystander_at(a)
    mover.place(a)

    assert mover.move(b).work == "unchanged"

    assert WorkStore(a).active()[0] == others
    assert show_issue_work(b) == NO_WORK_HERE
    runs, diagnostics = observe(a, b, lookup=BOTH_HOSTS)
    assert sorted(
        (run.session_id, run.observation_target, run.issue_id) for run in runs
    ) == sorted([(mover.session, str(b), None), (SECOND_THREAD, str(a), "I_crash")])
    assert diagnostics == []


def return_after_a_sub_agent_stops(mover: Mover, at: Path) -> HookPublication:
    """Publish a Sub-agent's stop at ``at``, then the designated return there.

    The stop reaches the parent's record at B; were it to make that record
    as old as itself, the return stamped alongside it would read as fresh as
    B and carry the run back (#355).
    """
    mover.publish(at, "SubagentStop", agent_id="child-thread")
    return mover.move_back(at)


# Late evidence at the origin: the designated event of a return there, the
# end of a turn there, and that return after a Sub-agent's stop there. The
# stop names no Sub-agent the session lists, so it holds only that it never
# makes B's record older; a Sub-agent live during a move is ADR 0102's, below.
LATE_AT_ORIGIN: list[Callable[[Mover, Path], HookPublication]] = [
    Mover.move_back,
    lambda mover, at: mover.publish(at, "Stop"),
    return_after_a_sub_agent_stops,
]


@movers
@pytest.mark.parametrize(
    "late", LATE_AT_ORIGIN, ids=["designated", "Stop", "SubagentStop"]
)
def test_late_evidence_from_the_origin_never_moves_the_run_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mover: Mover,
    late: Callable[[Mover, Path], HookPublication],
) -> None:
    a, b = two_worktrees(tmp_path)
    mover.bind(a)
    (before,) = WorkStore(a).active()[0]
    stamp_hooks_at(monkeypatch, AT_THE_MOVE)
    assert mover.move(b).work == "relocated"

    # The event was stamped at A before the carry and published after it.
    stamp_hooks_at(monkeypatch, BEFORE_THE_MOVE)
    publication = late(mover, a)

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == []
    (carried,) = WorkStore(b).active()[0]
    assert (carried.run_id, carried.started_at) == (before.run_id, before.started_at)
    # It is not fresher than the session's record at B, so B still
    # places the session and nothing reports it elsewhere.
    runs, diagnostics = observe(a, b, lookup=mover.lookup)
    assert [run.observation_target for run in runs] == [str(b)]
    assert diagnostics == []


def test_a_codex_move_during_a_turn_carries_the_run_at_the_next_turn(
    tmp_path: Path,
) -> None:
    # A ``turn/start`` override sent while a turn runs joins that turn, which
    # keeps executing at A although ``thread/read`` already reports B. The
    # joined input publishes its own UserPromptSubmit under the running turn,
    # at A, and the next turn's is the first at B (measured at 0.159.3).
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    (before,) = WorkStore(a).active()[0]
    publish(a, "UserPromptSubmit", turn_id="turn-1")

    assert publish(a, "UserPromptSubmit", turn_id="turn-1").work == "unchanged"
    assert publish(a, "Stop", turn_id="turn-1").work == "unchanged"

    # Observation follows execution: the run is still at A, and never early at B.
    assert WorkStore(a).active()[0] == [before]
    assert observe(a, b)[1] == []
    assert publish(b, "UserPromptSubmit", turn_id="turn-2").work == "relocated"
    (carried,) = WorkStore(b).active()[0]
    assert (carried.run_id, carried.started_at) == (before.run_id, before.started_at)
    assert observe(a, b)[1] == []


def test_a_declared_relocation_of_a_daemon_hosted_thread_is_unchanged(
    tmp_path: Path,
) -> None:
    # The managed daemon hosts the thread before and after ``codex resume -C``,
    # so both sides share one Host Process. Whether the thread was still
    # loaded or already unloaded at the resume, the daemon publishes the
    # origin's SessionEnd and then the target's SessionStart (#272).
    a, b = two_worktrees(tmp_path)
    codex_run(a)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]

    assert publish(a, "SessionEnd", reason="other").work == "unchanged"
    assert WorkStore(a).active()[0] == [before]
    resumed = publish(b, "SessionStart", source="resume")

    assert (resumed.work, resumed.issue_id) == ("relocated", before.issue_id)
    assert WorkStore(a).active()[0] == []
    (moved,) = WorkStore(b).active()[0]
    assert moved == replace(
        before, working_directory=str(b), branch="linked", relocation=None
    )
    # The resumed turn finds the run already there; nothing else moves it.
    assert publish(b, "UserPromptSubmit").work == "unchanged"
    assert WorkStore(b).active()[0] == [moved]
    assert observe(a, b)[1] == []
    assert publish(b, "SessionEnd", reason="other").work == "ended"
    assert observe(a, b) == ([], [])


@movers
@pytest.mark.parametrize("bound", [True, False], ids=["bound", "unbound"])
def test_a_handoff_is_verified_from_the_seam_alone(
    tmp_path: Path, mover: Mover, bound: bool
) -> None:
    # What #148 reads after a controller move, with no harness-specific
    # location logic: the session's freshest record, each Worktree's
    # occupants, and each Worktree's Work Store.
    a, b = two_worktrees(tmp_path)
    others = bystander_at(a)
    if bound:
        mover.bind(a)
    else:
        mover.place(a)
    own = [work for work in WorkStore(a).active()[0] if work not in others]

    publication = mover.move(b)

    stores = reachable_hook_stores([a, b])
    location = locate_agent_session(
        stores, mover.lookup, session_id=mover.session, harness=mover.harness
    )
    assert location is not None
    assert location.worktree == b
    assert location.record.process_key == mover.process.key
    assert mover.session not in {
        item.record.session_id for item in sessions_at_worktree(a, stores, BOTH_HOSTS)
    }
    assert [
        item.record.session_id for item in sessions_at_worktree(b, stores, BOTH_HOSTS)
    ] == [mover.session]
    assert WorkStore(a).active() == (others, [])
    carried = WorkStore(b).active()[0]
    assert [(work.run_id, work.started_at, work.issue_id) for work in carried] == [
        (work.run_id, work.started_at, work.issue_id) for work in own
    ]
    assert publication.work == ("relocated" if bound else "unchanged")
    assert len(own) == (1 if bound else 0)


# --- A Sub-agent across a move (ADR 0102) -------------------------------------


def listed_at(at: Path, mover: Mover) -> list[str]:
    """The Sub-agents the session's record at ``at`` lists as working."""
    return cast(
        "list[str]", recorded(session_directory(at), mover.session)["liveSubagents"]
    )


def delegating(a: Path, b: Path, mover: Mover) -> list[tuple[Path, tuple[str, ...]]]:
    """Each session the scan finds delegating in the Repository: where, and to whom."""
    return [
        (location.worktree, location.record.live_subagents)
        for location in sessions_with_live_subagents(
            [a, b], reachable_hook_stores([a, b]), mover.lookup
        )
    ]


def subagent_lines(at: Path, mover: Mover) -> list[str]:
    """What ``dashpot work show`` at ``at`` says of the run's Sub-agents."""
    return [
        line
        for line in show_issue_work(at, lookup=mover.lookup)
        if "listed as working" in line
    ]


@movers
def test_a_sub_agent_dispatched_before_a_move_blocks_until_its_stop_clears_both_records(
    tmp_path: Path, mover: Mover
) -> None:
    # #421's order: the lead dispatches a background worker, its turn ends,
    # it moves while the worker runs, and the worker's end wakes it at B.
    a, b = two_worktrees(tmp_path)
    mover.bind(a)
    mover.publish(a, "SubagentStart", agent_id="worker-1")
    mover.publish(a, "Stop")
    assert mover.move(b).work == "relocated"
    left = recorded(session_directory(a), mover.session)

    # Still working: both records list it, and the session reported at B
    # holds it for every Worktree of the Repository.
    assert listed_at(a, mover) == listed_at(b, mover) == ["worker-1"]
    assert delegating(a, b, mover) == [(b, ("worker-1",))]
    (working,) = subagent_lines(b, mover)
    assert "has 1 sub-agent listed as working (worker-1)" in working

    mover.publish(b, "SubagentStop", agent_id="worker-1")
    mover.publish(b, "UserPromptSubmit")
    mover.publish(b, "Stop")

    assert listed_at(a, mover) == listed_at(b, mover) == []
    assert delegating(a, b, mover) == []
    assert subagent_lines(b, mover) == []
    # Only the list left the record at A: it keeps its stamp and state, so
    # it never reads as fresher than B, which still places the session.
    assert recorded(session_directory(a), mover.session) == {
        **left,
        "liveSubagents": [],
    }
    stores = reachable_hook_stores([a, b])
    location = locate_agent_session(
        stores, mover.lookup, session_id=mover.session, harness=mover.harness
    )
    assert location is not None
    assert location.worktree == b
    # Its `running` stays unread: the freshest record alone gives the
    # session's state and location, so the dashboard reads it waiting at B
    # and Cleanup finds nothing of it at A.
    assert left["state"] == "running"
    runs, diagnostics = observe(a, b, lookup=mover.lookup)
    assert [(run.observation_target, run.state) for run in runs] == [
        (str(b), "waiting")
    ]
    assert diagnostics == []
    assert sessions_at_worktree(a, stores, mover.lookup) == []
    assert assess_worktree_occupancy(a, [a, b], mover.lookup) == []


def test_the_running_record_a_claude_code_move_leaves_behind_places_nothing(
    tmp_path: Path,
) -> None:
    # #519: #466's measured `mv` order (Claude Code 2.1.289, one Host
    # Process). The turn that enters B began at A, so A's store keeps its
    # `UserPromptSubmit` running; the session's `SessionEnd` carries A's cwd.
    a, b = two_worktrees(tmp_path)
    mover = MOVERS[1]
    stores = reachable_hook_stores([a, b])
    mover.publish(a, "SessionStart", source="startup")
    mover.publish(a, "UserPromptSubmit")
    mover.publish(a, "Stop")
    mover.publish(a, "UserPromptSubmit")
    mover.move(b)
    mover.publish(b, "Stop")

    def placed_at_b_alone() -> None:
        # A's record is current but never the freshest current one, so
        # nothing places the session by it or reads its state: the
        # dashboard, Cleanup and placement see the session waiting at B.
        runs, diagnostics = observe(a, b, lookup=mover.lookup)
        assert [(run.observation_target, run.state) for run in runs] == [
            (str(b), "waiting")
        ]
        assert diagnostics == []
        assert sessions_at_worktree(a, stores, mover.lookup) == []
        assert assess_worktree_occupancy(a, [a, b], mover.lookup) == []
        location = locate_agent_session(
            stores, mover.lookup, session_id=mover.session, harness=mover.harness
        )
        assert location is not None
        assert (location.worktree, location.record.state) == (b, "waiting")

    left = recorded(session_directory(a), mover.session)
    assert (left["event"], left["state"]) == ("UserPromptSubmit", "running")
    placed_at_b_alone()

    mover.publish(b, "UserPromptSubmit")
    mover.publish(b, "Stop")
    assert recorded(session_directory(a), mover.session) == left
    placed_at_b_alone()

    mover.publish(a, "SessionEnd", reason="prompt_input_exit")

    # The end at A removes the record there and the session's record at B.
    assert stored(session_directory(a), mover.session) is None
    assert stored(session_directory(b), mover.session) is None
    assert observe(a, b, lookup=mover.lookup) == ([], [])
    assert assess_worktree_occupancy(b, [a, b], mover.lookup) == []


@movers
def test_a_stop_clears_only_its_own_sub_agent_from_the_record_left_behind(
    tmp_path: Path, mover: Mover
) -> None:
    a, b = two_worktrees(tmp_path)
    mover.bind(a)
    mover.publish(a, "SubagentStart", agent_id="worker-1")
    mover.publish(a, "SubagentStart", agent_id="worker-2")
    mover.move(b)

    mover.publish(b, "SubagentStop", agent_id="worker-1")

    # The worker still running keeps every Worktree blocked.
    assert listed_at(a, mover) == listed_at(b, mover) == ["worker-2"]
    assert delegating(a, b, mover) == [(b, ("worker-2",))]
    (working,) = subagent_lines(b, mover)
    assert "has 1 sub-agent listed as working (worker-2)" in working


@movers
def test_a_stop_still_clears_a_record_the_session_left_two_moves_back(
    tmp_path: Path, mover: Mover
) -> None:
    a, b = two_worktrees(tmp_path)
    c = third_worktree(a, tmp_path)
    mover.bind(a)
    mover.publish(a, "SubagentStart", agent_id="worker-1")
    mover.move(b)
    mover.move(c)
    assert [listed_at(at, mover) for at in (a, b, c)] == [["worker-1"]] * 3

    mover.publish(c, "SubagentStop", agent_id="worker-1")

    assert [listed_at(at, mover) for at in (a, b, c)] == [[], [], []]
    assert (
        sessions_with_live_subagents(
            [a, b, c], reachable_hook_stores([a, b, c]), mover.lookup
        )
        == []
    )


@movers
def test_a_stop_leaves_another_live_sessions_record_alone(
    tmp_path: Path, mover: Mover
) -> None:
    # Only the stopping session's own live records let the agent go; another
    # session of the same harness and Host Process keeps its own listing.
    a, b = two_worktrees(tmp_path)
    mover.place(a)
    mover.publish(a, "SubagentStart", agent_id="worker-1")
    mover.move(b)
    other = {
        "session": SECOND_THREAD,
        "harness": mover.harness,
        "process": mover.process,
        "lookup": mover.lookup,
    }
    publish(a, "UserPromptSubmit", **other)
    publish(a, "SubagentStart", agent_id="worker-1", **other)

    mover.publish(b, "SubagentStop", agent_id="worker-1")
    other = recorded(session_directory(a), SECOND_THREAD)

    assert other["liveSubagents"] == ["worker-1"]
    assert listed_at(a, mover) == listed_at(b, mover) == []


@movers
def test_a_start_listed_again_after_a_stop_stays_where_the_stop_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mover: Mover
) -> None:
    # A worker that waits on its own background work stops, and starts again
    # when that work ends. Here its start lands between the stop's write and
    # the stop's release of the record left behind: the stop lets the record
    # left behind go, but never the start that listed the worker again.
    a, b = two_worktrees(tmp_path)
    mover.bind(a)
    mover.publish(a, "SubagentStart", agent_id="worker-1")
    mover.move(b)
    write = HookRecordStore.write

    def restarted(
        store: HookRecordStore, record: HookRecord, **options: Any
    ) -> HookRecordWrite:
        written = write(store, record, **options)
        if record.event == "SubagentStop":
            write(
                store,
                record.model_copy(
                    update={"event": "SubagentStart", "state": "running"}
                ),
            )
        return written

    monkeypatch.setattr(HookRecordStore, "write", restarted)
    mover.publish(b, "SubagentStop", agent_id="worker-1")

    assert listed_at(a, mover) == []
    assert listed_at(b, mover) == ["worker-1"]
    assert delegating(a, b, mover) == [(b, ("worker-1",))]
