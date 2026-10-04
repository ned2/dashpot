"""Refreshes keep the Issue table's viewport unless the page's rows reorder."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from textual.pilot import Pilot
from textual.widgets.data_table import ColumnKey

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    observation_landed,
    serve_snapshot,
    show_query_peer,
    workspace_snapshot,
)
from dashpot.core.issue_profile import IssueProfile
from dashpot.core.model import WorkspaceSnapshot
from dashpot.observation.issue_list import row_key
from dashpot.queries.source_queries import QueryRequest
from dashpot.ui.app import DashpotApp
from dashpot.ui.issue_table import IssueTable
from helpers import wait_until

ISSUE_COUNT = 60
TITLE = ColumnKey("title")


def issues(
    title: Callable[[int], str] = lambda number: f"Issue {number}",
) -> list[IssueProfile]:
    return [
        issue(f"test/repo#{number}", title(number))
        for number in range(1, ISSUE_COUNT + 1)
    ]


PAGE = workspace_snapshot(*issues())


def tall_page_app(*snapshots: WorkspaceSnapshot) -> DashpotApp:
    """The shipped app showing every Issue of a page taller than the table."""
    app = dashboard_app(SequenceCollector(*snapshots))
    app.queries.navigation["issues"].request = QueryRequest(page_size=ISSUE_COUNT)
    return app


async def show_tall_page(app: DashpotApp, pilot: Pilot[None]) -> IssueTable:
    await wait_until(lambda: first_load_landed(app))
    table = (await show_query_peer(app, pilot)).queue_table()
    await wait_until(lambda: table.row_count == ISSUE_COUNT)
    return table


async def place_cursor_mid_viewport(table: IssueTable, row: int) -> None:
    """Scroll past the first screen, then lift the cursor off the viewport's edge."""
    table.focus()
    table.move_cursor(row=row + 5, animate=False)
    await wait_until(lambda: table.scroll_y == table.scroll_target_y > 0)
    table.move_cursor(row=row, animate=False)
    await wait_until(lambda: table.cursor_row == row)


def scroll_changes(table: IssueTable) -> list[float]:
    """Every vertical scroll offset the table takes from now on."""
    seen: list[float] = []

    def record(scroll_y: float) -> None:
        seen.append(scroll_y)

    table.watch(table, "scroll_y", record, init=False)
    return seen


def cell_text(table: IssueTable, number: int, column: str) -> str:
    return str(table.get_cell(row_key("issue", f"I_test/repo#{number}"), column))


@pytest.mark.asyncio
@pytest.mark.parametrize("tick", ["local", "query"])
async def test_an_unchanged_refresh_leaves_a_scrolled_issue_table_in_place(
    tick: str,
) -> None:
    app = tall_page_app(PAGE, PAGE)

    async with app.run_test(size=(100, 30)) as pilot:
        table = await show_tall_page(app, pilot)
        # Read further down with the wheel: the cursor stays on the first row.
        table.scroll_to(y=25, animate=False)
        await wait_until(lambda: table.scroll_y == 25)
        seen = scroll_changes(table)

        if tick == "local":
            app.timer_refresh()
            await wait_until(lambda: app.store.revision == 2)
        else:
            app.request_refresh("timer")
            await wait_until(lambda: observation_landed(app, 2))
        await pilot.pause()

        assert seen == []
        assert table.scroll_y == 25
        assert table.cursor_row == 0


@pytest.mark.asyncio
async def test_a_refresh_that_changes_cells_updates_them_where_they_are() -> None:
    renamed = workspace_snapshot(
        *issues(
            lambda number: (
                f"Issue {number} renamed with a longer title"
                if number in {40, 41}
                else f"Issue {number}"
            )
        )
    )
    app = tall_page_app(PAGE, renamed)

    async with app.run_test(size=(100, 30)) as pilot:
        table = await show_tall_page(app, pilot)
        await place_cursor_mid_viewport(table, row=40)
        selected = row_key("issue", "I_test/repo#41")
        await wait_until(
            lambda: app.query_screen.issue_table.selected_row_key == selected
        )
        scroll_y = table.scroll_y
        title_width = table.columns[TITLE].content_width
        seen = scroll_changes(table)

        serve_snapshot(app, renamed)
        app.request_refresh("timer")
        await wait_until(lambda: observation_landed(app, 2))
        await wait_until(
            lambda: cell_text(table, 41, "title").endswith("with a longer title")
        )
        await pilot.pause()

        assert cell_text(table, 40, "title") == "Issue 40 renamed with a longer title"
        assert cell_text(table, 42, "title") == "Issue 42"
        # A changed cell is measured as a rebuilt one would be.
        assert table.columns[TITLE].content_width > title_width
        assert seen == []
        assert table.scroll_y == scroll_y
        assert table.cursor_row == 40
        assert app.query_screen.issue_table.selected_row_key == selected


@pytest.mark.asyncio
async def test_a_reordered_page_is_shown_in_the_providers_new_order() -> None:
    reordered = workspace_snapshot(*reversed(issues()))
    app = tall_page_app(PAGE, reordered)

    async with app.run_test(size=(100, 30)) as pilot:
        table = await show_tall_page(app, pilot)
        await place_cursor_mid_viewport(table, row=40)
        selected = row_key("issue", "I_test/repo#41")
        await wait_until(
            lambda: app.query_screen.issue_table.selected_row_key == selected
        )

        serve_snapshot(app, reordered)
        app.request_refresh("timer")
        await wait_until(lambda: observation_landed(app, 2))
        await wait_until(lambda: table.cursor_row == ISSUE_COUNT - 41)

        assert [str(row.key.value) for row in table.ordered_rows] == [
            row_key("issue", f"I_test/repo#{number}")
            for number in range(ISSUE_COUNT, 0, -1)
        ]
        assert app.query_screen.issue_table.selected_row_key == selected
