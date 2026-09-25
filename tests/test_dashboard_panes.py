"""The dashboard's list panes: sessions, worktrees, and their selections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from rich.text import Text
from textual.coordinate import Coordinate
from textual.pilot import Pilot

import factories
from app_harness import (
    UNAVAILABLE_PAGE_SUMMARY,
    SequenceCollector,
    await_resolved_identities,
    dashboard_app,
    first_load_landed,
    issue,
    list_rows,
    observation_landed,
    pane_subtitle,
    pane_title,
    prepare_pane,
    selected_title,
    serve_snapshot,
    show_query_peer,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.core.issue_profile import IssueProfile
from dashpot.core.model import (
    AgentRun,
    Harness,
    ObservationTarget,
    RunState,
    WorkspaceSnapshot,
)
from dashpot.observation.issue_list import row_key
from dashpot.ui import session_cells
from dashpot.ui.app import DashpotApp
from dashpot.ui.issue_view import IssueScreen
from dashpot.ui.messages import ObservationTrigger
from helpers import snapshot_of, wait_until


def refreshed_pull_request_snapshots() -> tuple[WorkspaceSnapshot, WorkspaceSnapshot]:
    """Two observations across which the second Pull Request moves to the top."""
    first_pull_request = factories.pull_request(
        1,
        pull_request_id="PR_one",
        title="First",
        updated_at="2026-08-25T00:00:00Z",
    )
    selected_pull_request = factories.pull_request(
        2,
        pull_request_id="PR_two",
        title="Selected",
        is_draft=True,
        updated_at="2026-08-24T00:00:00Z",
    )
    refreshed_pull_request = selected_pull_request.model_copy(
        update={"title": "Selected and refreshed", "updated_at": "2026-08-26T00:00:00Z"}
    )
    first = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(first_pull_request, selected_pull_request),
    )
    second = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(refreshed_pull_request, first_pull_request),
    )
    return first, second


async def refresh_over_a_moved_pull_request(
    app: DashpotApp, pilot: Pilot[None], trigger: ObservationTrigger
) -> None:
    """Select the second Pull Request, then observe a page that moves it to the top."""
    _first, second = refreshed_pull_request_snapshots()
    await wait_until(lambda: first_load_landed(app))
    await show_query_peer(app, pilot)
    pane = app.query_screen.pull_requests_pane()
    pane.table.focus()
    await pilot.pause()
    await pilot.press("down")
    selected_key, _index = pane.highlighted()
    assert selected_key is not None and "PR_two" in selected_key

    serve_snapshot(app, second)
    app.request_refresh(trigger)
    await wait_until(lambda: observation_landed(app, 2))
    await wait_until(
        lambda: "Selected and refreshed" in str(pane.table.get_row_at(0)[2])
    )

    assert pane.highlighted() == (selected_key, 0)


@pytest.mark.asyncio
async def test_pull_requests_pane_refreshes_and_keeps_its_cursor_by_identity() -> None:
    first, second = refreshed_pull_request_snapshots()
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        pane = app.query_screen.pull_requests_pane()
        await pilot.pause()
        assert (
            pane_title(app.query_screen, "#pull-requests-pane")
            == "PULL REQUESTS · Open 2 · Closed 0"
        )
        assert [str(column.label) for column in pane.table.columns.values()] == [
            "STATE",
            "#",
            "TITLE",
            "HEAD",
            "BASE",
            "AUTHOR",
            "REVIEW",
            "CHECKS",
            "MERGE",
            "UPDATED",
        ]
        pane.table.focus()
        await pilot.pause()

        # Enter is intentionally unbound for Pull Requests in the first cut.
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)
        assert pane.table.has_focus

        # A timer refresh repeats the shown page, so the cursor can follow
        # its Pull Request to the top.
        await refresh_over_a_moved_pull_request(app, pilot, "timer")


@pytest.mark.asyncio
async def test_a_manual_refresh_keeps_the_pull_request_cursor_by_identity() -> None:
    first, second = refreshed_pull_request_snapshots()
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(160, 40)) as pilot:
        # A manual refresh restarts the page; the page it replaces stays
        # listed until the restarted one lands, so the cursor follows its
        # Pull Request to the top as it does across a timer refresh.
        await refresh_over_a_moved_pull_request(app, pilot, "manual")


@pytest.mark.asyncio
async def test_an_empty_pull_request_page_names_its_status_in_the_summary() -> None:
    # The pane renders the age against the wall clock, so the last good
    # observation is anchored to it rather than to the snapshot's fixture time.
    stale = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "Issue")),
        pull_request_status="stale",
        pull_request_last_good_at=(datetime.now(UTC) - timedelta(hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    )
    unavailable = with_first_project_snapshot(
        stale,
        pull_request_status="unavailable",
        pull_request_last_good_at=None,
    )
    app = dashboard_app(SequenceCollector(stale))

    async with app.run_test(size=(120, 32)):
        await wait_until(lambda: first_load_landed(app))
        # The empty message only tells fresh from not; the page summary is
        # where a stale page keeps its last good observation apart from an
        # unavailable one.
        empty = app.query_screen.query_one("#pull-requests-pane .list-pane-empty")
        assert str(empty.render()) == "Pull Requests unavailable"
        assert (
            pane_subtitle(app.query_screen, "#pull-requests-pane")
            == "0 shown · 0 matches · stale · observed 3h ago"
        )

    unavailable_app = dashboard_app(SequenceCollector(unavailable))
    async with unavailable_app.run_test(size=(120, 32)):
        await wait_until(lambda: first_load_landed(unavailable_app))
        empty = unavailable_app.query_screen.query_one(
            "#pull-requests-pane .list-pane-empty"
        )
        assert str(empty.render()) == "Pull Requests unavailable"
        assert (
            pane_subtitle(unavailable_app.query_screen, "#pull-requests-pane")
            == UNAVAILABLE_PAGE_SUMMARY
        )


@pytest.mark.asyncio
async def test_pane_selection_survives_refresh_by_identity_or_moves_to_a_neighbour() -> (
    None
):
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First")))
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
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


def session_run(
    run_id: str,
    *,
    state: str = "waiting",
    issue_id: str | None = None,
    harness: Harness = "codex",
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        # A bound Issue is named once the Issue Source resolves its identity.
        await await_resolved_identities(app, "I_test/repo#2")
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
            "◈",
            "HARNESS",
            "BRANCH",
            "ISSUE",
            "DIRECTORY",
            "ACTIVITY",
        ]
        first = [str(cell) for cell in table.get_row_at(0)]
        assert first[:2] == ["●", "Claude Code"]
        assert first[3] == "no active Issue work"
        # With TARGET dropped, DIRECTORY locates itself in full.
        assert first[4] == "/repo/src"
        second = [str(cell) for cell in table.get_row_at(1)]
        assert second[0] == "◐"
        assert second[3] == "#2 Second"
        assert str(table.get_row_at(2)[0]) == "○"
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
    app = dashboard_app(SequenceCollector(spread, together))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()

        table = app.dashboard.sessions_pane().table
        assert "TARGET" in [str(column.label) for column in table.columns.values()]
        assert {
            str(table.get_row_at(index)[2]) for index in range(table.row_count)
        } == {"/repo", "/repo/wt/issue-42"}

        # The linked Worktree's session ends, and the column stops earning
        # its width without waiting for a restart.
        await pilot.press("r")
        await wait_until(lambda: observation_landed(app, 2))
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
    app = dashboard_app(SequenceCollector(snapshot))
    running = session_cells.STATE_GLYPHS["running"]

    def state_color() -> str:
        cell = app.dashboard.sessions_pane().table.get_row_at(0)[0]
        assert isinstance(cell, Text)
        return str(cell.style).casefold()

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        assert state_color() == running.style(dark=True)

        app.theme = "textual-light"
        # Without a new observation, only the theme handler can repaint.
        await wait_until(lambda: state_color() == running.style(dark=False))


@pytest.mark.asyncio
async def test_enter_on_a_session_does_not_open_or_select_an_issue() -> None:
    issues = (issue("test/repo#1", "First"), issue("test/repo#2", "Second"))
    snapshot = sessions_snapshot(
        session_run("work:codex:bound", state="running", issue_id="I_test/repo#2"),
        session_run("codex-session:free", state="waiting"),
        issues=issues,
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await await_resolved_identities(app, "I_test/repo#2")
        await pilot.pause()
        assert selected_title(app) == "#1: First"
        table = app.dashboard.sessions_pane().table
        assert str(table.get_row_at(0)[3]) == "#2 Second"

        # Session activation stays within the Dashboard peer. In particular,
        # it neither opens the bound Issue nor changes the query peer's own
        # native table selection.
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_screen.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )
        assert selected_title(app) == "#1: First"
        assert not isinstance(app.screen, IssueScreen)

        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is app.dashboard
        assert app.query_screen.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )


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
    app = dashboard_app(SequenceCollector(first, reordered, without_b))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        pane = app.dashboard.sessions_pane()
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 1)

        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 2))
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 0)

        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 3))
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
    app = dashboard_app(SequenceCollector(first, with_linked, stale_with_linked, first))

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        pane = app.dashboard.worktrees_pane()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        columns = list(pane.table.columns.values())
        labels = [str(column.label) for column in columns]
        assert labels == ["◈", "SESSIONS", "PATH", "KIND", "BRANCH", "TREE"]
        sessions_header = columns[1].label
        assert isinstance(sessions_header, Text)
        assert sessions_header.justify == "center"
        main_cells = [str(cell) for cell in pane.table.get_row_at(0)]
        assert main_cells == [
            "",
            "-",
            "/repo",
            "main",
            "main",
            "clean",
        ]
        sessions_value = pane.table.get_row_at(0)[1]
        assert isinstance(sessions_value, Text)
        assert sessions_value.justify == "center"

        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 2))
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
            "",
            "-",
            "/repo-linked · unavailable",
            "linked",
            "detached @ def4567",
            "unknown",
        ]
        # Highlighting a worktree leaves the Issue-driven panes alone.
        assert selected_title(app) == "#1: First"
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_screen.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )
        assert not isinstance(app.screen, IssueScreen)

        # A retained topology names stale explicitly without restoring STATE.
        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 3))
        await pilot.pause()
        stale_cells = [str(cell) for cell in pane.table.get_row_at(1)]
        assert stale_cells[2] == "/repo-linked · stale"

        # The linked worktree is removed: the cursor moves to a neighbour.
        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 4))
        await pilot.pause()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        assert pane.highlighted() == (
            row_key("worktree", "project:test-repo", "/repo"),
            0,
        )
