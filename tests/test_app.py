from __future__ import annotations

import asyncio
from collections.abc import Callable
from threading import Event, Lock

import pytest
from textual.widgets import DataTable, Label, Static

from dashpot.app import (
    COLUMN_KEYS,
    DashpotApp,
    build_rows,
    project_label,
    selection_detail_text,
)
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ProjectObservation,
    ProjectSnapshot,
    Repository,
    SourceStatus,
    WorkItem,
    WorkspaceSnapshot,
    Worktree,
)


NOW = "2026-08-25T01:00:00Z"


def work_item(key: str, title: str, priority: str = "P1") -> WorkItem:
    return WorkItem(
        key=key,
        source="github-issues",
        title=title,
        priority=priority,
        tags=["tasks.md"],
        declared_claimant=None,
        declared_blocked="unknown",
        location=None,
    )


def workspace_snapshot(
    *items: WorkItem,
    runs: list[AgentRun] | None = None,
    status: SourceStatus = "fresh",
    diagnostics: list[Diagnostic] | None = None,
    elapsed_ms: int = 12,
) -> WorkspaceSnapshot:
    repository = Repository(
        root="/repo",
        name="repo",
        branch="main",
        head="abcdef123456",
        dirty=False,
        worktrees=[Worktree("/repo", "abcdef123456", "main")],
    )
    project_snapshot = ProjectSnapshot(
        collected_at=NOW,
        task_source_status=status,
        task_source_attempted_at=NOW,
        task_source_last_good_at=NOW if status != "unavailable" else None,
        repository=repository,
        work_items=list(items),
        agent_runs=runs or [],
        diagnostics=diagnostics or [],
    )
    project = ProjectObservation(
        workspace="test",
        repository="repo",
        root="/repo",
        status=status,
        elapsed_ms=elapsed_ms,
        snapshot=project_snapshot,
        diagnostics=[],
    )
    return WorkspaceSnapshot(NOW, elapsed_ms, [project])


class SequenceCollector:
    def __init__(self, *results: WorkspaceSnapshot | Exception) -> None:
        self.results = list(results)
        self.lock = Lock()

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


async def wait_until(
    predicate: Callable[[], bool], timeout: float = 1.5
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not met before timeout")
        await asyncio.sleep(0.01)


def assert_context_above_full_width_queue(app: DashpotApp) -> None:
    body = app.query_one("#body")
    detail_row = app.query_one("#detail-row")
    project_pane = app.query_one("#project-pane")
    selection_pane = app.query_one("#selection-pane")
    queue_pane = app.query_one("#queue-pane")

    assert project_pane.region.y == selection_pane.region.y == detail_row.region.y
    assert project_pane.region.x < selection_pane.region.x
    assert project_pane.region.bottom <= queue_pane.region.y
    assert selection_pane.region.bottom <= queue_pane.region.y
    assert queue_pane.region.x == body.region.x
    assert queue_pane.region.width == body.region.width
    assert project_pane.region.height >= 4
    assert selection_pane.region.height >= 4
    assert queue_pane.region.height >= 6
    assert abs(detail_row.region.height - queue_pane.region.height) <= 2


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        work_item("github:test/repo#1", "First"),
        work_item("github:test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.snapshot is snapshot)
        table = app.query_one("#queue", DataTable)
        project_detail = str(app.query_one("#project-detail", Static).render())
        selection_detail = str(app.query_one("#selection-detail", Static).render())

        assert table.row_count == 2
        assert COLUMN_KEYS == (
            "status",
            "project",
            "priority",
            "assignee",
            "sessions",
            "title",
        )
        assert [str(column.label) for column in table.columns.values()] == [
            "S",
            "PROJECT",
            "PRI",
            "ASSIGNEE",
            "SESSIONS",
            "TITLE",
        ]
        assert app.selected_row_key == "github:test/repo#1"
        assert "Status: fresh" in project_detail
        assert "Root: /repo" in project_detail
        assert "test/repo" not in project_detail
        assert "Refresh:" not in project_detail
        assert "First" in selection_detail
        assert "Status:" not in selection_detail
        assert "Assignee: unassigned" in selection_detail
        assert "Agent sessions:" in selection_detail
        assert "Declared" not in selection_detail
        assert "blocked" not in selection_detail.lower()
        assert str(app.query_one("#selection-title", Static).render()) == "WORK ITEM"
        diagnostics = app.query_one("#diagnostics", Static)
        assert_context_above_full_width_queue(app)
        assert app.query_one("#queue-pane").region.bottom <= diagnostics.region.y
        assert "1 project  1 fresh" in str(
            app.query_one("#source-status", Label).render()
        )
        assert not app.query_one("#diagnostics", Static).has_class("-has-messages")


@pytest.mark.asyncio
async def test_refresh_preserves_selection_by_stable_row_key() -> None:
    first = workspace_snapshot(
        work_item("github:test/repo#1", "First"),
        work_item("github:test/repo#2", "Second", "P2"),
    )
    second = workspace_snapshot(
        work_item("github:test/repo#0", "Inserted", "P0"),
        work_item("github:test/repo#1", "First renamed"),
        work_item("github:test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(SequenceCollector(second), refresh_seconds=0, initial_snapshot=first)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        table.move_cursor(row=table.get_row_index("github:test/repo#2"), animate=False)
        await wait_until(lambda: app.selected_row_key == "github:test/repo#2")

        await app.run_action("refresh")
        await wait_until(lambda: app.snapshot is second)

        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == "github:test/repo#2"
        assert app.selected_row_key == "github:test/repo#2"
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_rows_and_shows_diagnostic() -> None:
    snapshot = workspace_snapshot(work_item("github:test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(RuntimeError("GitHub is unavailable")),
        refresh_seconds=0,
        initial_snapshot=snapshot,
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.ui_error is not None)

        assert app.snapshot is snapshot
        assert app.query_one("#queue", DataTable).row_count == 1
        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.query_one("#diagnostics", Static).has_class("-has-messages")


@pytest.mark.asyncio
async def test_unmatched_agent_is_visible_as_its_own_row() -> None:
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        repository_root="/repo",
        worktree="/repo",
        branch="main",
        declared_work_key=None,
    )
    snapshot = workspace_snapshot(runs=[run])
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.snapshot is snapshot)

        assert app.selected_row_key == "run:codex-session:42"
        assert "Unmatched codex run" in str(
            app.query_one("#selection-detail", Static).render()
        )
        assert str(app.query_one("#selection-title", Static).render()) == "AGENT RUN"


@pytest.mark.asyncio
async def test_layout_switches_at_horizontal_breakpoint() -> None:
    snapshot = workspace_snapshot(work_item("github:test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(60, 20)) as pilot:
        await wait_until(lambda: app.snapshot is snapshot)
        assert app.screen.has_class("-compact")

        await pilot.resize_terminal(120, 32)
        await pilot.pause()
        assert app.screen.has_class("-wide")
        assert_context_above_full_width_queue(app)


def test_workspace_root_uses_workspace_name_without_dot_suffix() -> None:
    project = workspace_snapshot().projects[0]
    project.workspace = "portable"
    project.repository = "."

    assert project_label(project) == "portable"


def test_correlated_run_state_is_visible_in_queue_and_detail() -> None:
    item = work_item("github:test/repo#1", "First")
    item.declared_claimant = "ned2"
    item.observed_runs = ["codex-session:42"]
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        repository_root="/repo",
        worktree="/repo",
        branch="issue/1",
        declared_work_key=item.key,
    )
    snapshot = workspace_snapshot(item, runs=[run])

    contexts, cells = build_rows(snapshot)

    assert len(cells[item.key]) == len(COLUMN_KEYS) == 6
    assert cells[item.key][3] == "ned2"
    assert cells[item.key][4] == "Ⅱ1"
    detail = selection_detail_text(contexts[item.key])
    assert "Assignee: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


class RacingCollector:
    def __init__(self, old: WorkspaceSnapshot, new: WorkspaceSnapshot) -> None:
        self.old = old
        self.new = new
        self.started = Event()
        self.release = Event()
        self.calls = 0
        self.lock = Lock()

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.started.set()
            self.release.wait(timeout=2)
            return self.old
        return self.new


@pytest.mark.asyncio
async def test_superseded_refresh_cannot_overwrite_newer_result() -> None:
    initial = workspace_snapshot(work_item("github:test/repo#1", "Initial"))
    old = workspace_snapshot(work_item("github:test/repo#1", "Old result"))
    new = workspace_snapshot(work_item("github:test/repo#1", "New result"))
    collector = RacingCollector(old, new)
    app = DashpotApp(collector, refresh_seconds=0, initial_snapshot=initial)

    try:
        async with app.run_test(size=(80, 24)):
            app.request_refresh("manual")
            assert await asyncio.to_thread(collector.started.wait, 1)
            app.request_refresh("manual")
            await wait_until(lambda: app.snapshot is new)

            collector.release.set()
            await asyncio.sleep(0.1)
            assert app.snapshot is new
            assert "New result" in str(
                app.query_one("#selection-detail", Static).render()
            )
    finally:
        collector.release.set()
