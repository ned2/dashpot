"""Header tooltips follow the hovered header and read the column's own help."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import DataTable, Static, Tooltip
from typing_extensions import override

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.core.model import Branch
from dashpot.ui.branch_cells import BRANCH_COLUMNS
from dashpot.ui.focus_table import FocusCursorTable
from dashpot.ui.list_pane import ListPane
from dashpot.ui.list_rows import column_help
from helpers import required, wait_until

# A zero delay divides by zero inside Textual's Timer; a short one is prompt.
TOOLTIP_DELAY = 0.01


def branch(name: str, *, remote: str | None = None) -> Branch:
    prefix = "refs/heads" if remote is None else f"refs/remotes/{remote}"
    return Branch(
        refname=f"{prefix}/{name}",
        name=name,
        remote=remote,
        head="abcdef1234567",
        committed_at="2026-08-27T02:00:00Z",
        unintegrated_commits=0,
    )


def header_offsets(table: DataTable[Any]) -> list[int]:
    """The x offset at which each column's header starts."""
    offsets: list[int] = []
    x = 0
    for column in table.columns.values():
        offsets.append(x)
        x += column.get_render_width(table)
    return offsets


async def hover_afresh(
    pilot: Pilot[Any], tooltip: Tooltip, selector: str, x: int, y: int
) -> None:
    """Enter the table at ``(x, y)`` from outside it.

    Textual hides a showing tooltip on any further move within the same
    widget without restarting its timer, so a fresh entry is what shows the
    next one.
    """
    await leave(pilot, tooltip)
    assert await pilot.hover(selector, offset=(x, y))
    await pilot.pause(0.05)


async def leave(pilot: Pilot[Any], tooltip: Tooltip) -> None:
    """Rest the mouse in the screen's top-left corner, which no table owns.

    A tooltip opens downward from the mouse, so a tall one can cover a
    widget below the table; the corner above it is never covered.
    """
    assert await pilot.hover(None, offset=(0, 0))
    await wait_until(lambda: not tooltip.display)


async def move_within(pilot: Pilot[Any], selector: str, x: int, y: int) -> None:
    """Move the mouse to ``(x, y)`` without leaving the table.

    The first move hides whatever the table was showing, as Textual does for
    any move within the tooltip's widget; the second restarts the timer, as
    the next tick of a real mouse would.
    """
    assert await pilot.hover(selector, offset=(x, y))
    assert await pilot.hover(selector, offset=(x, y))
    await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_every_branches_header_shows_its_help_and_only_its_help() -> None:
    snapshot = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "First")),
        branches=[branch("main"), branch("main", remote="origin"), branch("feat")],
    )
    app = dashboard_app(SequenceCollector(snapshot))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(140, 40), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        pane = app.query_one("#branches-pane", ListPane)
        table = pane.table
        tooltip = app.screen.query_one(Tooltip)
        assert table.show_header
        offsets = header_offsets(table)
        assert len(offsets) == len(BRANCH_COLUMNS)

        for x, column in zip(offsets, BRANCH_COLUMNS, strict=True):
            await hover_afresh(pilot, tooltip, "#branches", x, 0)
            await wait_until(lambda: tooltip.display)
            assert str(tooltip.content) == required(column_help(column))
            assert required(column.description) in str(tooltip.content)
            # A box a person can take in beside the header, not a page:
            # the help stays a short paragraph at the widened tooltip.
            await pilot.pause()
            assert tooltip.region.height <= 20, column.key

        # Moving between headers without leaving follows the mouse.
        await move_within(pilot, "#branches", offsets[6], 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(BRANCH_COLUMNS[6]))
        await move_within(pilot, "#branches", offsets[3], 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(BRANCH_COLUMNS[3]))

        # A body cell clears it, and so does leaving. The cell is one to the
        # right of the box the LOCAL header opened beneath itself, since a
        # mouse inside that box rests on the tooltip rather than the table.
        await move_within(pilot, "#branches", offsets[7] + 30, 1)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_afresh(pilot, tooltip, "#branches", offsets[6], 0)
        await wait_until(lambda: tooltip.display)
        await leave(pilot, tooltip)
        await wait_until(lambda: table.tooltip is None)
        # Hovering observed nothing and mutated nothing.
        assert app.store.revision == 1
        assert pane.count == 2


class TableApp(App[None]):
    """A bare table whose columns explain themselves, without a pane around it."""

    def __init__(self, columns: Sequence[tuple[str, str | None]]) -> None:
        super().__init__()
        self.initial_columns = tuple(columns)

    @override
    def compose(self) -> ComposeResult:
        yield Static("away")
        yield FocusCursorTable[str](id="table", cursor_type="row")

    def on_mount(self) -> None:
        self.declare(self.initial_columns)

    def declare(self, columns: Sequence[tuple[str, str | None]]) -> None:
        table = self.query_one("#table", FocusCursorTable)
        table.clear(columns=True)
        for label, tooltip in columns:
            table.add_column(label, key=label.lower(), tooltip=tooltip)


@pytest.mark.asyncio
async def test_headers_explain_themselves_over_an_empty_table_and_after_changes() -> (
    None
):
    app = TableApp([("ALPHA", "the first column"), ("BETA", None), ("GAMMA", "third")])
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(60, 10), tooltips=True) as pilot:
        table = app.query_one("#table", FocusCursorTable)
        tooltip = app.screen.query_one(Tooltip)
        assert table.row_count == 0
        assert table.show_header
        offsets = header_offsets(table)

        # Nothing beneath the headers, and they still explain themselves; a
        # header without help offers none.
        await hover_afresh(pilot, tooltip, "#table", offsets[0], 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "the first column"
        await hover_afresh(pilot, tooltip, "#table", offsets[1], 0)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_afresh(pilot, tooltip, "#table", offsets[2], 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "third"

        # Redeclaring the columns replaces the help the same header offers.
        app.declare([("GAMMA", "third, now first"), ("ALPHA", "the first column")])
        await pilot.pause()
        await hover_afresh(pilot, tooltip, "#table", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "third, now first"
        assert table.header_tooltip_at({"row": -1, "column": 1}) == "the first column"
        assert table.header_tooltip_at({"row": -1, "column": 2}) is None
        assert table.header_tooltip_at({"row": 0, "column": 0}) is None
        assert table.header_tooltip_at({}) is None


@pytest.mark.asyncio
async def test_header_help_follows_the_column_under_a_scrolled_header() -> None:
    wide = "x" * 40
    app = TableApp([(wide, "wide"), ("NARROW", "narrow"), ("LAST", "last")])
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(30, 10), tooltips=True) as pilot:
        table = app.query_one("#table", FocusCursorTable)
        tooltip = app.screen.query_one(Tooltip)
        table.add_row("a", "b", "c")
        await pilot.pause()
        assert table.virtual_size.width > table.size.width

        await hover_afresh(pilot, tooltip, "#table", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "wide"

        # Scroll the wide column away; the header at the left edge is now
        # a later column, and so is its help.
        table.scroll_to(x=table.virtual_size.width, animate=False, force=True)
        await pilot.pause()
        await hover_afresh(pilot, tooltip, "#table", table.size.width - 2, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "last"
