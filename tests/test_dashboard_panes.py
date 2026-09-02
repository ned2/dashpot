"""The dashboard's list panes: sessions, worktrees, and their selections."""

from __future__ import annotations

from typing import cast

import pytest
from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable

import factories
from app_harness import (
    SequenceCollector,
    issue,
    list_rows,
    pane_title,
    prepare_pane,
    selected_title,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot import session_list
from dashpot.app import DashpotApp
from dashpot.issue_list import row_key
from dashpot.issue_profile import IssueProfile
from dashpot.issue_view import IssueScreen
from dashpot.list_pane import ListRow
from dashpot.model import (
    AgentRun,
    ObservationTarget,
    RunState,
    WorkspaceSnapshot,
)
from helpers import snapshot_of, wait_until


@pytest.mark.asyncio
async def test_pane_cursor_leaves_the_issue_selection_alone_and_enter_finds_it() -> (
    None
):
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second")
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert selected_title(app) == "#1: First"
        pane = prepare_pane(app, "sessions-pane")
        pane.show_rows(
            (
                ListRow("bound", ("bound", "-"), issue_id="I_test/repo#2"),
                ListRow("unbound", ("unbound", "-")),
            )
        )
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == ("unbound", 1)
        assert selected_title(app) == "#1: First"

        await pilot.press("enter")
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")
        assert not isinstance(app.screen, IssueScreen)

        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#2")
        assert selected_title(app) == "#2: Second"
        assert app.query_one("#queue", DataTable).cursor_row == 1
        assert not isinstance(app.screen, IssueScreen)
        assert pane.table.has_focus


@pytest.mark.asyncio
async def test_pane_selection_survives_refresh_by_identity_or_moves_to_a_neighbour() -> (
    None
):
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = prepare_pane(app, "worktrees-pane")
        rows = list_rows(4)
        pane.show_rows(rows)
        pane.table.move_cursor(row=2)
        await pilot.pause()
        assert pane.highlighted() == ("row-2", 2)

        pane.show_rows((rows[2], rows[0], rows[3]))
        await pilot.pause()
        assert pane.highlighted() == ("row-2", 0)

        pane.table.move_cursor(row=2)
        pane.show_rows((rows[2], rows[0]))
        await pilot.pause()
        assert pane.highlighted() == ("row-0", 1)

        pane.show_rows(())
        await pilot.pause()
        assert pane.highlighted() == (None, 0)
        assert pane.highlighted_row() is None


def session_run(
    run_id: str,
    *,
    state: str = "waiting",
    issue_id: str | None = None,
    harness: str = "codex",
    last_activity_at: str | None = "2026-08-25T00:59:00Z",
    target: str = "/repo",
) -> AgentRun:
    return factories.agent_run(
        run_id,
        "project:test-repo",
        harness=harness,
        state=cast("RunState", state),
        issue_id=issue_id,
        target_path=target,
        working_directory="/repo/src",
        last_activity_at=last_activity_at,
    )


def sessions_snapshot(
    *runs: AgentRun, issues: tuple[IssueProfile, ...]
) -> WorkspaceSnapshot:
    snapshot = workspace_snapshot(*issues, runs=list(runs))
    issue_runs = {key: list(value) for key, value in snapshot.issue_runs.items()}
    for run in runs:
        if run.issue_id is not None:
            issue_runs.setdefault(run.issue_id, []).append(run.id)
    return snapshot.model_copy(update={"issue_runs": issue_runs})


def session_pane_keys(app: DashpotApp) -> list[str]:
    table = app.dashboard.sessions_pane().table
    return [
        str(table.coordinate_to_cell_key(Coordinate(index, 0)).row_key.value)
        for index in range(table.row_count)
    ]


@pytest.mark.asyncio
async def test_sessions_pane_lists_every_active_session_from_observations() -> None:
    issues = (issue("test/repo#1", "First"), issue("test/repo#2", "Second"))
    snapshot = sessions_snapshot(
        session_run("work:codex:bound", state="waiting", issue_id="I_test/repo#2"),
        session_run("claude-code-session:free", state="running", harness="claude-code"),
        session_run("codex-session:lost", state="unknown", last_activity_at=None),
        issues=issues,
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        assert pane_title(app, "#sessions-pane") == "SESSIONS · 3"
        assert session_pane_keys(app) == [
            row_key("session", "claude-code-session:free"),
            row_key("session", "work:codex:bound"),
            row_key("session", "codex-session:lost"),
        ]
        table = app.dashboard.sessions_pane().table
        labels = [str(column.label) for column in table.columns.values()]
        # Every session is in the one Worktree, so TARGET says nothing.
        assert labels == [
            "STATE",
            "HARNESS",
            "BRANCH",
            "ISSUE",
            "DIRECTORY",
            "ACTIVITY",
        ]
        first = [str(cell) for cell in table.get_row_at(0)]
        assert first[:2] == ["● running", "Claude Code"]
        assert first[3] == "no active Issue work"
        # With TARGET dropped, DIRECTORY locates itself in full.
        assert first[4] == "/repo/src"
        second = [str(cell) for cell in table.get_row_at(1)]
        assert second[0] == "◐ waiting"
        assert second[3] == "#2 Second"
        assert str(table.get_row_at(2)[0]) == "○ unknown"
        assert str(table.get_row_at(2)[5]) == "-"
        assert not app.query_one("#sessions-pane .list-pane-empty").display


@pytest.mark.asyncio
async def test_sessions_target_column_follows_the_worktrees_in_view() -> None:
    issues = (issue("test/repo#1", "First"),)
    spread = sessions_snapshot(
        session_run("codex-session:main"),
        session_run("codex-session:linked", target="/repo/wt/issue-42"),
        issues=issues,
    )
    together = sessions_snapshot(session_run("codex-session:main"), issues=issues)
    app = DashpotApp(SequenceCollector(spread, together), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        table = app.dashboard.sessions_pane().table
        assert "TARGET" in [str(column.label) for column in table.columns.values()]
        assert {
            str(table.get_row_at(index)[2]) for index in range(table.row_count)
        } == {"/repo", "/repo/wt/issue-42"}

        # The linked Worktree's session ends, and the column stops earning
        # its width without waiting for a restart.
        await pilot.press("r")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()

        table = app.dashboard.sessions_pane().table
        assert "TARGET" not in [str(column.label) for column in table.columns.values()]
        assert table.row_count == 1
        assert [str(cell) for cell in table.get_row_at(0)][2] == "main"
        assert [str(cell) for cell in table.get_row_at(0)][4] == "/repo/src"


@pytest.mark.asyncio
async def test_a_theme_change_repaints_the_list_panes() -> None:
    issues = (issue("test/repo#1", "First"),)
    snapshot = sessions_snapshot(
        session_run("codex-session:busy", state="running"), issues=issues
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)
    running = session_list.STATE_GLYPHS["running"]

    def state_color() -> str:
        cell = app.dashboard.sessions_pane().table.get_row_at(0)[0]
        assert isinstance(cell, Text)
        return str(cell.style).casefold()

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert state_color() == running.style(dark=True)

        app.theme = "textual-light"
        # Without a new observation, only the theme handler can repaint.
        await wait_until(lambda: state_color() == running.style(dark=False))


@pytest.mark.asyncio
async def test_enter_on_a_bound_session_highlights_its_issue_and_unbound_is_safe() -> (
    None
):
    issues = (issue("test/repo#1", "First"), issue("test/repo#2", "Second"))
    snapshot = sessions_snapshot(
        session_run("work:codex:bound", state="running", issue_id="I_test/repo#2"),
        session_run("codex-session:free", state="waiting"),
        issues=issues,
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert selected_title(app) == "#1: First"

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")
        assert selected_title(app) == "#1: First"

        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#2")
        assert selected_title(app) == "#2: Second"
        assert not isinstance(app.screen, IssueScreen)
        assert app.dashboard.sessions_pane().table.has_focus


@pytest.mark.asyncio
async def test_session_selection_survives_refresh_by_identity_or_moves_on() -> None:
    issues = (issue("test/repo#1", "First"),)
    first = sessions_snapshot(
        session_run("a", state="running", last_activity_at="2026-08-25T00:50:00Z"),
        session_run("b", state="running", last_activity_at="2026-08-25T00:40:00Z"),
        session_run("c", state="waiting"),
        issues=issues,
    )
    # ``b`` becomes the most recent so the rows reorder; ``c`` stays put.
    reordered = sessions_snapshot(
        session_run("a", state="running", last_activity_at="2026-08-25T00:50:00Z"),
        session_run("b", state="running", last_activity_at="2026-08-25T00:55:00Z"),
        session_run("c", state="waiting"),
        issues=issues,
    )
    without_b = sessions_snapshot(
        session_run("a", state="running", last_activity_at="2026-08-25T00:50:00Z"),
        session_run("c", state="waiting"),
        issues=issues,
    )
    app = DashpotApp(SequenceCollector(first, reordered, without_b), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = app.dashboard.sessions_pane()
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 1)

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 0)

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 3)
        await pilot.pause()
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 2"
        assert pane.highlighted() == (row_key("session", "a"), 0)


@pytest.mark.asyncio
async def test_worktrees_pane_lists_observed_targets_and_follows_the_topology() -> None:
    first = workspace_snapshot(issue("test/repo#1", "First"))
    linked = ObservationTarget(
        path="/repo-linked",
        head="def456789",
        branch=None,
        detached=True,
        dirty=None,
        availability="unavailable",
        elapsed_ms=2,
        diagnostics=[],
        role="linked",
    )
    with_linked = workspace_snapshot(issue("test/repo#1", "First"))
    with_linked = with_first_project_snapshot(
        with_linked,
        observation_targets=(
            *snapshot_of(with_linked.projects[0]).observation_targets,
            linked,
        ),
    )
    stale_with_linked = with_first_project_snapshot(with_linked, target_status="stale")
    app = DashpotApp(
        SequenceCollector(first, with_linked, stale_with_linked, first),
        refresh_seconds=0,
    )

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = app.dashboard.worktrees_pane()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        columns = list(pane.table.columns.values())
        labels = [str(column.label) for column in columns]
        assert labels == ["PATH", "KIND", "BRANCH", "TREE", "SESSIONS"]
        sessions_header = columns[-1].label
        assert isinstance(sessions_header, Text)
        assert sessions_header.justify == "center"
        main_cells = [str(cell) for cell in pane.table.get_row_at(0)]
        assert main_cells == [
            "/repo",
            "main",
            "main",
            "clean",
            "-",
        ]
        sessions_value = pane.table.get_row_at(0)[-1]
        assert isinstance(sessions_value, Text)
        assert sessions_value.justify == "center"

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 2"
        await pilot.press("tab")
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == (
            row_key("worktree", "project:test-repo", "/repo-linked"),
            1,
        )
        linked_cells = [str(cell) for cell in pane.table.get_row_at(1)]
        assert linked_cells == [
            "/repo-linked · unavailable",
            "linked",
            "detached @ def4567",
            "unknown",
            "-",
        ]
        # Highlighting a worktree leaves the Issue-driven panes alone.
        assert selected_title(app) == "#1: First"
        await pilot.press("enter")
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")
        assert not isinstance(app.screen, IssueScreen)

        # A retained topology names stale explicitly without restoring STATE.
        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 3)
        await pilot.pause()
        stale_cells = [str(cell) for cell in pane.table.get_row_at(1)]
        assert stale_cells[0] == "/repo-linked · stale"

        # The linked worktree is removed: the cursor moves to a neighbour.
        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 4)
        await pilot.pause()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        assert pane.highlighted() == (
            row_key("worktree", "project:test-repo", "/repo"),
            0,
        )
