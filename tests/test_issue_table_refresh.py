"""Refreshes keep the Issue table's viewport unless the page's rows reorder."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

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
from dashpot.queries.pages import QueryRequest
from dashpot.ui.app import DashpotApp
from dashpot.ui.issue_table import COLUMN_KEYS, IssueTable
from helpers import settled, wait_until

type Viewport = Literal["focused cursor", "scrolled away"]
type Refresh = Literal["local tick", "query tick"]

ISSUE_COUNT = 60
TITLE = ColumnKey("title")
# Row 40 shows Issue #41.
CURSOR_ROW = 40
SELECTED = row_key("issue", "I_test/repo#41")


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
    """Show the page with every column, so the table scrolls both ways."""
    await wait_until(lambda: first_load_landed(app))
    screen = await show_query_peer(app, pilot)
    screen.issue_table_controller.apply_issue_columns(COLUMN_KEYS)
    table = screen.issue_table()
    await wait_until(lambda: table.row_count == ISSUE_COUNT)
    await wait_until(lambda: table.max_scroll_x > 0)
    # The column rebuild scrolls its cursor into view after the next repaint;
    # left pending, it would land during the refresh under test.
    table.refresh()
    await settled(
        pilot,
        lambda: (table.virtual_size, table.scroll_x, table.scroll_y),
        "the rebuilt Issue table",
    )
    return table


async def place_viewport(
    app: DashpotApp, table: IssueTable, viewport: Viewport
) -> None:
    """Move the viewport off the table's origin, the cursor clear of its edges."""
    if viewport == "focused cursor":
        table.focus()
        table.move_cursor(row=CURSOR_ROW + 5, animate=False)
        await wait_until(lambda: table.scroll_y == table.scroll_target_y > 0)
        table.move_cursor(row=CURSOR_ROW, animate=False)
        await wait_until(
            lambda: app.query_screen.issue_table_controller.selected_row_key == SELECTED
        )
        table.scroll_to(x=20, animate=False)
    else:
        # Read further along with the wheel: the cursor stays on the first row.
        table.scroll_to(x=20, y=25, animate=False)
    await wait_until(
        lambda: (
            (table.scroll_x, table.scroll_y)
            == (table.scroll_target_x, table.scroll_target_y)
            and table.scroll_x == 20
        )
    )


def scroll_changes(table: IssueTable) -> list[tuple[str, float]]:
    """Every scroll offset the table takes from now on, by axis."""
    seen: list[tuple[str, float]] = []

    def record_x(offset: float) -> None:
        seen.append(("x", offset))

    def record_y(offset: float) -> None:
        seen.append(("y", offset))

    table.watch(table, "scroll_x", record_x, init=False)
    table.watch(table, "scroll_y", record_y, init=False)
    return seen


async def refresh(app: DashpotApp, kind: Refresh) -> None:
    """Run one automatic refresh of ``kind`` and wait for it to land."""
    if kind == "local tick":
        app.timer_refresh()
        await wait_until(lambda: app.store.revision == 2)
    else:
        app.request_refresh("timer")
        await wait_until(lambda: observation_landed(app, 2))


def cell_text(table: IssueTable, number: int, column: str) -> str:
    return str(table.get_cell(row_key("issue", f"I_test/repo#{number}"), column))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local tick", "query tick"])
@pytest.mark.parametrize("viewport", ["focused cursor", "scrolled away"])
async def test_an_unchanged_refresh_leaves_the_issue_table_in_place(
    kind: Refresh, viewport: Viewport
) -> None:
    app = tall_page_app(PAGE, PAGE)

    async with app.run_test(size=(100, 30)) as pilot:
        table = await show_tall_page(app, pilot)
        await place_viewport(app, table, viewport)
        before = (table.scroll_x, table.scroll_y, table.cursor_row)
        seen = scroll_changes(table)

        await refresh(app, kind)
        await pilot.pause()

        assert seen == []
        assert (table.scroll_x, table.scroll_y, table.cursor_row) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("viewport", ["focused cursor", "scrolled away"])
async def test_a_refresh_that_changes_cells_updates_them_where_they_are(
    viewport: Viewport,
) -> None:
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
        await place_viewport(app, table, viewport)
        before = (table.scroll_x, table.scroll_y, table.cursor_row)
        selected = app.query_screen.issue_table_controller.selected_row_key
        title_width = table.columns[TITLE].content_width
        seen = scroll_changes(table)

        serve_snapshot(app, renamed)
        await refresh(app, "query tick")
        await wait_until(
            lambda: cell_text(table, 41, "title").endswith("with a longer title")
        )
        # A changed cell is measured as a rebuilt one would be.
        widened = await settled(
            pilot, lambda: table.columns[TITLE].content_width, "the title column"
        )
        assert widened > title_width

        assert cell_text(table, 40, "title") == "Issue 40 renamed with a longer title"
        assert cell_text(table, 42, "title") == "Issue 42"
        assert seen == []
        assert (table.scroll_x, table.scroll_y, table.cursor_row) == before
        assert app.query_screen.issue_table_controller.selected_row_key == selected


@pytest.mark.asyncio
async def test_a_reordered_page_is_shown_in_the_query_sources_new_order() -> None:
    reordered = workspace_snapshot(*reversed(issues()))
    app = tall_page_app(PAGE, reordered)

    async with app.run_test(size=(100, 30)) as pilot:
        table = await show_tall_page(app, pilot)
        await place_viewport(app, table, "focused cursor")

        serve_snapshot(app, reordered)
        await refresh(app, "query tick")
        await wait_until(lambda: table.cursor_row == ISSUE_COUNT - 1 - CURSOR_ROW)

        assert [str(row.key.value) for row in table.ordered_rows] == [
            row_key("issue", f"I_test/repo#{number}")
            for number in range(ISSUE_COUNT, 0, -1)
        ]
        assert app.query_screen.issue_table_controller.selected_row_key == SELECTED
