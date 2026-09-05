"""The dashboard's pane geometry: stacking, breakpoints, fit and spread."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest
from rich.text import Text
from textual.widgets import DataTable, Footer, Input, Static

import factories
from app_harness import (
    SequenceCollector,
    assert_panes_stack_above_full_width_queue,
    footer_keys,
    issue,
    list_rows,
    pane_chrome,
    pane_subtitle,
    pane_title,
    prepare_pane,
    workspace_snapshot,
)
from dashpot.app import DashpotApp
from dashpot.item_filter import ItemFilterBar
from dashpot.list_pane import ListColumn, ListPane, ListRow
from dashpot.pane_layout import PANE_MARGIN
from helpers import wait_until


@pytest.mark.asyncio
async def test_dashboard_tables_do_not_use_zebra_stripes() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)
        tables = tuple(
            app.query_one(f"#{table_id}", DataTable)
            for table_id in (
                "queue",
                "sessions",
                "worktrees",
                "branches",
                "pull-requests",
            )
        )

        assert all(not table.zebra_stripes for table in tables)


@pytest.mark.asyncio
async def test_layout_switches_at_horizontal_breakpoint() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    def assert_counts_fit_in_queue_pane() -> None:
        queue_pane = app.query_one("#queue-pane")
        search = app.query_one("#issue-search", Input)
        count = app.query_one("#issue-count", Static)
        assert str(count.render()) == "1 issue"
        assert count.region.width >= len("1 issue")
        assert count.region.y == search.region.y
        assert count.region.x >= search.region.right
        assert count.region.right <= queue_pane.region.right - 1
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 1 · Closed 0"

    async with app.run_test(size=(60, 20)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert app.screen.has_class("-compact")
        assert_counts_fit_in_queue_pane()

        await pilot.resize_terminal(120, 32)
        await pilot.pause()
        assert app.screen.has_class("-wide")
        assert_panes_stack_above_full_width_queue(app)
        assert_counts_fit_in_queue_pane()


@pytest.mark.asyncio
async def test_list_columns_align_their_headers_and_values() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        pane = app.dashboard.sessions_pane()
        pane.declare_columns((ListColumn("value", "VALUE", justify="center"),))
        pane.show_rows((ListRow("row", (Text("styled", style="red"),)),))
        await pilot.pause()

        header = next(iter(pane.table.columns.values())).label
        value = pane.table.get_row_at(0)[0]
        assert isinstance(header, Text)
        assert header.justify == "center"
        assert isinstance(value, Text)
        assert value.justify == "center"
        assert str(value.style) == "red"


@pytest.mark.asyncio
async def test_footer_distributes_key_bindings_across_its_width() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        footer = app.query_one(Footer)
        binding_items = [
            child
            for child in footer.children
            if not child.has_class("-command-palette")
        ]
        command_palette = next(
            child for child in footer.children if child.has_class("-command-palette")
        )

        assert binding_items[0].region.x == footer.region.x
        assert all(
            left.region.right == right.region.x
            for left, right in pairwise(binding_items)
        )
        assert binding_items[-1].region.right == command_palette.region.x
        assert (
            max(item.region.width for item in binding_items)
            - min(item.region.width for item in binding_items)
            <= 1
        )
        assert all(item.styles.text_align == "center" for item in binding_items)


@pytest.mark.asyncio
async def test_dashboard_stacks_the_panes_above_the_issues() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        sessions = app.query_one("#sessions-pane", ListPane)
        worktrees = app.query_one("#worktrees-pane", ListPane)
        branches = app.query_one("#branches-pane", ListPane)
        pull_requests = app.query_one("#pull-requests-pane", ListPane)
        queue_pane = app.query_one("#queue-pane")
        assert_panes_stack_above_full_width_queue(app)
        # One blank line separates back-to-back panes.
        assert sessions.region.bottom + 1 == worktrees.region.y
        assert worktrees.region.bottom + 1 == branches.region.y
        assert branches.region.bottom + 1 == pull_requests.region.y
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 0"
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        # Remote freshness sits apart from the label and count, aligned to the
        # lower-right pane border. Dashpot never fetches, and this repository
        # never has.
        assert pane_title(app, "#branches-pane") == "BRANCHES · 0"
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 0 · Closed 0"
        )
        assert pane_subtitle(app, "#branches-pane") == (
            "integration unavailable · remote never fetched"
        )
        branches = app.query_one("#branches-pane", ListPane)
        assert branches.styles.border_subtitle_align == "right"
        # An empty pane is one honest line inside its frame, not a blank box.
        assert sessions.region.height == 3
        assert worktrees.region.height == pane_chrome(worktrees) + 1
        assert branches.region.height == 3
        # The filter stays available above the honest empty state when it fits.
        assert pull_requests.region.height == 3 + ItemFilterBar.HEIGHT
        empty_messages = [
            str(message.render())
            for message in app.query(".list-pane-empty").results(Static)
            if message.display
        ]
        assert empty_messages == [
            "no active sessions",
            "no branches observed yet",
            "no pull requests",
        ]
        assert not app.query_one("#worktrees-pane .list-pane-empty").display
        assert app.query_one("#sessions", DataTable).has_focus
        assert queue_pane.region.height >= 6
        assert "tab" in footer_keys(app)
        assert {"1", "2", "3", "4", "shift+r"}.isdisjoint(footer_keys(app))


@pytest.mark.asyncio
async def test_pane_grows_with_its_records_to_the_cap_then_scrolls() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 43)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = prepare_pane(app, "sessions-pane")

        def flex_height() -> int:
            """The Issue table's height, which is whatever the panes leave."""
            return app.query_one("#queue-pane").region.height

        def other_panes_height() -> int:
            return sum(
                other.region.height
                for other in app.dashboard.list_panes()
                if other is not pane
            )

        def stack_margins() -> int:
            """Each pane carries the blank line below it, inside `#list-row`."""
            return PANE_MARGIN * len(app.dashboard.list_panes())

        list_row = app.query_one("#list-row")
        initial_flex_height = flex_height()
        initial_row_height = list_row.region.height

        pane.show_rows(list_rows(3))
        await wait_until(lambda: pane.region.height == pane_chrome(pane) + 3)
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 3"
        # Frame, header and three records; the Issue table gives up only what
        # the pane stack grows by.
        assert pane.region.height == pane_chrome(pane) + 3
        assert list_row.region.height == (
            pane.region.height + other_panes_height() + stack_margins()
        )
        assert not pane.table.show_vertical_scrollbar
        assert not app.query_one("#sessions-pane .list-pane-empty").display
        assert flex_height() == initial_flex_height - (
            list_row.region.height - initial_row_height
        )

        pane.show_rows(list_rows(12))
        await wait_until(lambda: pane.region.height == 2 + 1 + 8)
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 12"
        # A pane never exceeds its cap; a horizontal scrollbar comes out of
        # the records shown rather than out of the Issue table.
        assert pane.region.height == 2 + 1 + 8
        assert list_row.region.height == (
            2 + 1 + 8 + other_panes_height() + stack_margins()
        )
        assert pane.table.show_vertical_scrollbar
        assert flex_height() == initial_flex_height - (
            list_row.region.height - initial_row_height
        )
        pane.table.move_cursor(row=11)
        await pilot.pause()
        assert pane.table.scroll_y > 0

        pane.show_rows(())
        await wait_until(lambda: pane.region.height == 3)
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 0"
        assert pane.region.height == 3
        assert list_row.region.height == initial_row_height
        assert flex_height() == initial_flex_height


@pytest.mark.asyncio
async def test_pull_requests_pane_scrolls_vertically_and_horizontally_at_narrow_width() -> (
    None
):
    pull_requests = tuple(
        factories.pull_request(
            number,
            title=f"A deliberately long Pull Request title number {number}",
        )
        for number in range(1, 13)
    )
    app = DashpotApp(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"), pull_requests=pull_requests
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(60, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        pane = app.dashboard.pull_requests_pane()
        await pilot.pause()

        assert pane.count == 12
        assert pane.region.width == app.query_one("#body").region.width
        assert pane.table.show_vertical_scrollbar
        assert pane.table.show_horizontal_scrollbar
        assert app.query_one("#queue-pane").region.height >= 6


@pytest.mark.asyncio
async def test_panes_stack_full_width_at_every_breakpoint() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(80, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert app.screen.has_class("-compact")
        sessions = prepare_pane(app, "sessions-pane")
        worktrees = prepare_pane(app, "worktrees-pane")
        sessions.show_rows(list_rows(12, prefix="session"))
        worktrees.show_rows(
            list_rows(2, prefix="/very/long/path/to/a/linked/worktree/checkout/name")
        )
        await wait_until(
            lambda: (
                sessions.region.height == 2 + 1 + 8
                and worktrees.region.height == pane_chrome(worktrees) + 2
            )
        )

        body = app.query_one("#body")
        assert sessions.region.width == worktrees.region.width == body.region.width
        assert sessions.region.bottom <= worktrees.region.y
        assert sessions.region.height == 2 + 1 + 8
        assert worktrees.region.height == pane_chrome(worktrees) + 2
        assert app.query_one("#queue-pane").region.height >= 6
        assert app.query_one("#queue-pane").region.bottom <= body.region.bottom

        await pilot.resize_terminal(120, 50)
        await wait_until(lambda: app.screen.has_class("-wide"))
        await wait_until(lambda: sessions.region.width == body.region.width)
        assert_panes_stack_above_full_width_queue(app)
        assert sessions.region.height == 2 + 1 + 8
        assert worktrees.region.height == pane_chrome(worktrees) + 2


@pytest.mark.asyncio
async def test_panes_yield_height_before_the_issue_table_loses_its_minimum() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    # 25 rows: the Footer and the Issue table's minimum leave enough for the
    # two empty panes and one record in each populated pane.
    async with app.run_test(size=(80, 25)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        sessions = prepare_pane(app, "sessions-pane")
        worktrees = prepare_pane(app, "worktrees-pane")
        sessions.show_rows(list_rows(12, prefix="session"))
        worktrees.show_rows(list_rows(12, prefix="worktree"))
        await wait_until(
            lambda: sessions.region.height == worktrees.region.height == 2 + 1 + 1
        )

        body = app.query_one("#body")
        queue_pane = app.query_one("#queue-pane")
        footer = app.query_one(Footer)
        assert queue_pane.region.height >= 6
        assert queue_pane.region.bottom <= footer.region.y
        # Room for one record each; the rest scrolls behind the count.
        assert sessions.region.height == worktrees.region.height == 2 + 1 + 1
        assert sessions.table.show_vertical_scrollbar or (
            sessions.table.show_horizontal_scrollbar
        )
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 12"
        assert body.region.height >= (
            app.query_one("#list-row").region.height + queue_pane.region.height
        )

        await pilot.resize_terminal(80, 31)
        await wait_until(
            lambda: (
                sessions.region.height == 2 + 1 + 2
                and worktrees.region.height == 2 + 1 + 3
            )
        )
        # The Pull Request controls now own three of the spare rows.
        assert sessions.region.height == 2 + 1 + 2
        assert worktrees.region.height == 2 + 1 + 3
        assert queue_pane.region.height >= 6
        assert queue_pane.region.bottom <= app.query_one(Footer).region.y

        # Too short even for a content line each: every list collapses to its
        # frame and count before the Issue pane loses its minimum.
        await pilot.resize_terminal(80, 19)
        await wait_until(lambda: sessions.region.height == worktrees.region.height == 2)
        assert sessions.region.height == worktrees.region.height == 2
        assert app.query_one("#branches-pane").region.height == 2
        assert app.query_one("#pull-requests-pane").region.height == 2
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 12"
        assert queue_pane.region.height >= 6
        assert queue_pane.region.bottom <= app.query_one(Footer).region.y


def column_widths(table: DataTable[Any]) -> list[int]:
    return [column.get_render_width(table) for column in table.columns.values()]


@pytest.mark.asyncio
async def test_issue_table_spreads_its_columns_to_the_pane_edge() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(160, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        queue = app.query_one("#queue", DataTable)
        await wait_until(
            lambda: sum(column_widths(queue)) == queue.scrollable_content_region.width
        )
        columns = list(queue.columns.values())
        assert all(not column.auto_width for column in columns)
        shares = {
            str(column.key.value): column.width - column.content_width
            for column in columns
        }
        # Every column keeps its content; the surplus goes in proportion to
        # it, except the one-glyph icon columns, which opt out.
        assert min(shares.values()) >= 0
        assert shares["issue_state"] == shares["agent_state"] == 0
        assert shares["title"] > shares["agent_state"] > 0 or shares["title"] > 0
        for column in columns:
            for other in columns:
                if column.content_width < other.content_width:
                    assert shares[str(column.key.value)] <= shares[str(other.key.value)]

        # The list panes stay content-sized.
        sessions = prepare_pane(app, "sessions-pane")
        sessions.show_rows(list_rows(2, prefix="session"))
        await pilot.pause()
        for table_id in ("sessions", "worktrees", "branches"):
            table = app.query_one(f"#{table_id}", DataTable)
            assert all(column.auto_width for column in table.columns.values())
            assert sum(column_widths(table)) < table.scrollable_content_region.width

        # Too narrow to spread: the columns are their content and the table
        # scrolls sideways instead of squeezing anything.
        await pilot.resize_terminal(30, 50)
        await wait_until(
            lambda: all(column.auto_width for column in queue.columns.values())
        )
        assert sum(column_widths(queue)) > queue.scrollable_content_region.width

        await pilot.resize_terminal(160, 50)
        await wait_until(
            lambda: sum(column_widths(queue)) == queue.scrollable_content_region.width
        )
