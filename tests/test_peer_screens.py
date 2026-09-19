"""The two long-lived peer screens and their shared navigation chrome."""

from __future__ import annotations

from typing import Any

import pytest
from textual.widgets import Input, Static

import factories
from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    observation_landed,
    serve_snapshot,
    workspace_snapshot,
)
from dashpot.ui.app import DashboardScreen, IssuesPullRequestsScreen
from dashpot.ui.issue_view import IssueScreen
from dashpot.ui.legend import LegendScreen
from helpers import wait_until


def shown_footer_keys(app: Any) -> set[str]:
    """The keys the Footer renders after unavailable bindings are hidden."""
    return {widget.key for widget in app.screen.query("FooterKey") if widget.display}


@pytest.mark.asyncio
async def test_number_keys_switch_long_lived_peers_with_their_own_content() -> None:
    app = dashboard_app(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "Issue"),
                pull_requests=(factories.pull_request(1),),
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        assert isinstance(app.screen, DashboardScreen)
        assert app.screen.query_one("#sessions").has_focus
        assert not app.screen.query("#pull-requests-pane")
        assert not app.screen.query("#queue-pane")
        assert str(app.screen.query_one("#peer-dashboard").render()) == "[1 Dashboard]"

        await pilot.press("2")
        await wait_until(lambda: isinstance(app.screen, IssuesPullRequestsScreen))
        assert app.screen.query_one("#pull-requests").has_focus
        assert app.screen.query_one("#pull-requests").row_count == 1
        assert app.screen.query_one("#queue").row_count == 1
        assert not app.screen.query("#sessions-pane")
        assert str(app.screen.query_one("#peer-issues-pull-requests").render()) == (
            "[2 Issues & Pull Requests]"
        )

        await pilot.press("1")
        await wait_until(lambda: isinstance(app.screen, DashboardScreen))
        assert app.screen.query_one("#sessions").has_focus


@pytest.mark.asyncio
async def test_status_bar_is_identical_across_peers_and_labels_are_clickable() -> None:
    app = dashboard_app(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "Issue"),
                pull_requests=(factories.pull_request(1),),
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        dashboard_summary = str(app.screen.query_one("#peer-summary", Static).render())
        assert dashboard_summary == "◆ Open Issues: 1 | Open PRs: 1"

        assert await pilot.click("#peer-issues-pull-requests")
        await wait_until(lambda: isinstance(app.screen, IssuesPullRequestsScreen))
        assert str(app.screen.query_one("#peer-summary", Static).render()) == (
            dashboard_summary
        )

        assert await pilot.click("#peer-dashboard")
        await wait_until(lambda: isinstance(app.screen, DashboardScreen))


@pytest.mark.asyncio
async def test_number_keys_type_into_query_inputs_instead_of_switching() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "Issue"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.press("2")
        await wait_until(lambda: isinstance(app.screen, IssuesPullRequestsScreen))
        search = app.screen.query_one("#issue-search", Input)
        search.focus()

        await pilot.press("1", "2")

        assert app.screen is app.query_screen
        assert search.value == "12"
        assert {"1", "2", "c", "o", "n", "p", "g", "slash"}.isdisjoint(
            shown_footer_keys(app)
        )


@pytest.mark.asyncio
async def test_switching_preserves_each_peers_native_focus_cursor_and_draft() -> None:
    app = dashboard_app(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"),
                issue("test/repo#2", "Second"),
                pull_requests=(factories.pull_request(1), factories.pull_request(2)),
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.press("2")
        await wait_until(lambda: app.screen is app.query_screen)
        queue = app.query_screen.queue_table()
        draft = app.query_screen.issue_filter_bar.search
        draft.value = "not submitted"
        queue.focus()
        await pilot.press("down")
        await pilot.pause()
        assert queue.cursor_row == 1

        await pilot.press("1")
        await wait_until(lambda: app.screen is app.dashboard)
        worktrees = app.dashboard.worktrees_pane().table
        worktrees.focus()
        await pilot.pause()

        await pilot.press("2")
        await wait_until(lambda: app.screen is app.query_screen)
        assert queue.has_focus
        assert queue.cursor_row == 1
        assert draft.value == "not submitted"

        await pilot.press("1")
        await wait_until(lambda: app.screen is app.dashboard)
        assert worktrees.has_focus


@pytest.mark.asyncio
async def test_temporary_screens_return_to_origin_and_disable_peer_keys() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "Issue"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.press("2", "question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))

        await pilot.press("1", "2")
        assert isinstance(app.screen, LegendScreen)
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)

        app.query_screen.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.press("1")
        assert isinstance(app.screen, IssueScreen)
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)


@pytest.mark.asyncio
async def test_refresh_updates_the_inactive_peer_and_both_status_bars() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        pull_requests=(factories.pull_request(1),),
    )
    second = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second"),
        pull_requests=(factories.pull_request(1), factories.pull_request(2)),
    )
    app = dashboard_app(SequenceCollector(first, second), refresh_seconds=0)

    async with app.run_test(size=(120, 32)):
        await wait_until(lambda: first_load_landed(app))
        assert app.screen is app.dashboard
        serve_snapshot(app, second)
        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 2))
        await wait_until(lambda: app.query_screen.queue_table().row_count == 2)
        await wait_until(
            lambda: (
                str(app.dashboard.query_one("#peer-summary", Static).render())
                == "◆ Open Issues: 2 | Open PRs: 2"
            )
        )
        assert str(app.query_screen.query_one("#peer-summary", Static).render()) == (
            "◆ Open Issues: 2 | Open PRs: 2"
        )


@pytest.mark.asyncio
async def test_status_bar_wraps_without_hiding_labels_or_summary() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "Issue"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        bar = app.dashboard.status_bar()
        screens = bar.query_one("#peer-status-screens")
        summary = bar.query_one("#peer-summary", Static)
        assert bar.region.height == 1
        assert screens.region.y == summary.region.y

        await pilot.resize_terminal(60, 24)
        await wait_until(lambda: app.screen.has_class("-compact"))
        assert bar.region.height == 2
        assert summary.region.y == screens.region.bottom
        assert "Issues & Pull Requests" in str(
            bar.query_one("#peer-issues-pull-requests").render()
        )
        assert "Open Issues: 1 | Open PRs: 0" in str(summary.render())


@pytest.mark.asyncio
async def test_footer_tracks_the_active_peer_and_focused_query_pane() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "Issue"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        assert {"f", "x"} <= shown_footer_keys(app)
        assert {"c", "o", "n", "p", "g", "slash"}.isdisjoint(shown_footer_keys(app))

        await pilot.press("2")
        await wait_until(lambda: app.screen is app.query_screen)
        await pilot.pause()
        assert {"o", "n", "p", "g", "slash"} <= shown_footer_keys(app)
        assert {"f", "x", "c", "enter"}.isdisjoint(shown_footer_keys(app))

        app.query_screen.queue_table().focus()
        await pilot.pause()
        assert {"c", "enter"} <= shown_footer_keys(app)
