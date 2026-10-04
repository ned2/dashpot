"""An OpenCode root moved to another Project takes its working Sub-agents along (#459).

#448 measured it at OpenCode 2.0.22 (its ``move-other-project`` order,
``docs/spikes/measurements/issue-448-opencode-trace.jsonl`` receipts 863 to
1021): the shared service moved a root to another Project while the root's
child held a command. Dashpot wrote the move in the first Project's store,
naming where the session went, and the root's next publication began its
incarnation in the other Project's store with no Sub-agents (#951). The
record left behind kept the child listed and ``running`` (#1020), the new
record never listed it, and the child's stop there removed nothing. Each
test replays such an order through the publisher and reads it through the
hook records and ``assess_worktree_occupancy`` (ADR 0109).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dashpot.sessions.hook_scan import (
    reachable_hook_stores,
    sessions_with_live_subagents,
)
from test_opencode import CHILD, ROOT, SHELL_PID, Server
from test_second_host_process_subagents import (
    CLIENT,
    SERVICE,
    alive,
    record,
    resumed_by_a_standalone_client,
    running,
    sub_agent_blockers,
)
from test_work import linked_worktree, repository


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def project_at(root: Path, linked: Path) -> list[Path]:
    """A Project's main checkout and a linked Worktree Cleanup is asked about."""
    main = repository(root).resolve()
    return [main, linked_worktree(main, linked, linked.name).resolve()]


@pytest.fixture
def first(tmp_path: Path) -> list[Path]:
    """The Project the root starts in, the trace's ``repository``."""
    return project_at(tmp_path / "repository", tmp_path / "repository-a")


@pytest.fixture
def second(tmp_path: Path) -> list[Path]:
    """The Project the root is moved to, the trace's ``other``."""
    return project_at(tmp_path / "other", tmp_path / "other-a")


@pytest.fixture
def shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every publisher run below the shell ``SHELL_PID``."""
    monkeypatch.setattr("dashpot.sessions.processes.os.getppid", lambda: SHELL_PID)


@pytest.fixture
def server(shell: None) -> Server:
    """The shared service, whose helper runs below it."""
    return Server(running(SERVICE), host=SERVICE)


def launched(server: Server, at: Path) -> None:
    """#448's order up to the move: the root's child works on after its turn."""
    # Receipts 875-921: the root is created, and a warm-up turn runs.
    assert server.event("created", at).written == ("SessionStart",)
    server.turn(at)
    server.finish(at)
    # Receipts 922-925: the root's turn creates its child and starts its
    # execution, and the root's execution ends while the child works.
    server.turn(at)
    assert server.event("created", at, CHILD, root=ROOT).written == ()
    assert server.turn(at, CHILD, root=ROOT) == "accepted"
    server.finish(at)
    assert record(at, ROOT)["liveSubagents"] == [CHILD]


def test_a_root_moved_to_another_project_takes_its_working_child_there(
    first: list[Path], second: list[Path], server: Server
) -> None:
    main, linked = first
    there, there_linked = second
    launched(server, main)

    # Receipts 948-950: the move runs as an execution of the root; an
    # instance registers at the new location; the move is published from
    # where the session was.
    server.turn(main)
    assert server.register(there) == {"result": "accepted", "sessions": []}
    moved = server.event("moved", main, to=there)

    assert moved.written == ("SessionMoved", "SessionStart")
    left, arrived = record(main, ROOT), record(there, ROOT)
    # The record left names where the session went and lists the child no
    # more; the record it arrived at lists it, from the same Host Process.
    assert (left["cwd"], left["event"], left["liveSubagents"]) == (
        str(there),
        "SessionMoved",
        [],
    )
    assert (arrived["cwd"], arrived["state"], arrived["liveSubagents"]) == (
        str(there),
        "running",
        [CHILD],
    )
    assert arrived["sessionProcess"]["pid"] == SERVICE.pid
    assert "subagentProcesses" not in arrived

    # Receipt 951: the move's execution ends at the new location. Its
    # incarnation there has begun, so only the turn's end is written.
    assert server.event("execution.succeeded", there).written == ("Stop",)
    # Receipts 963-979: a turn of the root there.
    server.turn(there)
    server.finish(there)
    stopped = record(there, ROOT)
    assert (stopped["event"], stopped["state"], stopped["liveSubagents"]) == (
        "Stop",
        "running",
        [CHILD],
    )

    # The child blocks the Project the root is in now, and not the one it left.
    (blocker,) = sub_agent_blockers(there_linked, second, server.lookup)
    assert f"at {there} has 1 sub-agent listed as working ({CHILD};" in blocker
    assert sub_agent_blockers(linked, first, server.lookup) == []
    assert (
        sessions_with_live_subagents(first, reachable_hook_stores(first), server.lookup)
        == []
    )

    # Receipt 1017: the child's execution ends, published at its root's new
    # location, and its stop clears it there.
    assert server.finish(there, CHILD, root=ROOT) == "accepted"
    # Receipts 1018-1019: the root's next turn, woken by the child's notice.
    server.turn(there)
    server.finish(there)
    settled, left = record(there, ROOT), record(main, ROOT)
    assert (settled["state"], settled["liveSubagents"]) == ("waiting", [])
    assert left["liveSubagents"] == []
    assert sub_agent_blockers(there_linked, second, server.lookup) == []
    assert sub_agent_blockers(linked, first, server.lookup) == []


def test_a_root_moved_back_takes_its_child_from_the_project_it_left(
    first: list[Path], second: list[Path], server: Server
) -> None:
    main, linked = first
    there, there_linked = second
    # The root begins in the second Project, moves to the first and starts
    # its child there, then moves back while the child works.
    server.turn(there)
    server.finish(there)
    assert server.event("moved", there, to=main).written == (
        "SessionMoved",
        "SessionStart",
    )
    server.turn(main)
    server.turn(main, CHILD, root=ROOT)
    server.finish(main)

    assert server.event("moved", main, to=there).written == (
        "SessionMoved",
        "SessionStart",
    )

    # The record the root left in the second Project the first time is
    # older than the one it moved back from, which seeds its return.
    assert record(there, ROOT)["liveSubagents"] == [CHILD]
    assert record(main, ROOT)["liveSubagents"] == []
    assert sub_agent_blockers(linked, first, server.lookup) == []
    (blocker,) = sub_agent_blockers(there_linked, second, server.lookup)
    assert f"({CHILD}; session live)" in blocker


def test_a_project_that_saw_a_later_event_takes_nothing_from_the_move(
    first: list[Path], second: list[Path], server: Server
) -> None:
    main, _linked = first
    there, _there_linked = second
    launched(server, main)
    # A later event of the root already reached the second Project.
    server.turn(there, sequence=100)
    before = record(there, ROOT)

    moved = server.event("moved", main, to=there, sequence=50)

    assert moved.written == ("SessionMoved",)
    assert record(there, ROOT) == before


@pytest.mark.usefixtures("shell")
def test_a_sub_agent_another_host_process_runs_is_listed_where_it_was_too(
    first: list[Path], second: list[Path]
) -> None:
    main, linked = first
    there, there_linked = second
    # #448's standalone order: a client's server resumed the root, whose
    # child the shared service runs, and the client then moves the root.
    _service, client = resumed_by_a_standalone_client(main)

    assert client.event("moved", main, to=there).written == (
        "SessionMoved",
        "SessionStart",
    )

    # The move's Host Process takes along the sub-agent of a process still
    # running, tagged with it; only its own leave the record left behind.
    arrived, left = record(there, ROOT), record(main, ROOT)
    for kept in (arrived, left):
        assert kept["liveSubagents"] == [CHILD]
        assert kept["subagentProcesses"][CHILD]["pid"] == SERVICE.pid
    both = alive(SERVICE, CLIENT)
    (blocker,) = sub_agent_blockers(there_linked, second, both)
    assert f"({CHILD}; session live)" in blocker
    # The record left names where the session went, so it blocks nothing.
    assert sub_agent_blockers(linked, first, both) == []
    # Once the service is gone, neither lists its child.
    assert sub_agent_blockers(there_linked, second, alive(CLIENT)) == []
