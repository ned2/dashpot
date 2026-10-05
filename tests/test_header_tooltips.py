"""Header tooltips follow the hovered header and read the column's own help.

Every table family — the Sessions, Worktrees, Branches and Pull Requests
panes and the Issue table — is hovered header by header through the shipped
dashboard; a bare ``FocusCursorTable`` covers the mechanics the families
share: an empty table, redeclared columns and a scrolled header.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, override

import pytest
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import DataTable, Static, Tooltip

import factories
from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    observation_landed,
    serve_snapshot,
    show_query_peer,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.core.model import Branch
from dashpot.ui.app import DashpotApp
from dashpot.ui.branch_cells import BRANCH_COLUMNS
from dashpot.ui.focus_table import FocusCursorTable
from dashpot.ui.issue_table import (
    COLUMN_KEYS,
    COLUMNS_BY_KEY,
    DEFAULT_COLUMNS,
    ColumnKey,
    column_specs,
    shown_columns,
)
from dashpot.ui.list_pane import ListPane
from dashpot.ui.list_rows import DescribedColumn, column_help
from dashpot.ui.pull_request_cells import PULL_REQUEST_COLUMNS
from dashpot.ui.session_cells import SESSION_COLUMNS
from dashpot.ui.worktree_cells import WORKTREE_COLUMNS
from helpers import required, settled, snapshot_of, wait_until
from test_dashboard_panes import session_run

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


def painted_headers(app: App[Any], table: DataTable[Any]) -> list[tuple[int, object]]:
    """Each header's start x and column, as the table paints its header row now.

    The segment meta is read the way a hover reads it, so painting the row
    is a side effect, as it is for a hover.
    """
    region = table.region
    starts: dict[object, int] = {}
    for x in range(region.width):
        meta = app.screen.get_style_at(region.x + x, region.y).meta
        if meta.get("row") == -1:
            starts.setdefault(meta.get("column"), x)
    return sorted((x, column) for column, x in starts.items())


async def settled_header_offsets(
    pilot: Pilot[Any], table: DataTable[Any], what: str
) -> list[int]:
    """Settle the x offset at which each header starts, as the table paints it.

    A hover reads the column from the segment meta of the header row as the
    table paints it, and a change of columns or of the terminal's size
    reaches that paint a few frames after the table reports it. The offsets
    are therefore read the way a hover reads them rather than summed from
    the columns' widths: Textual can paint a redeclared table's header
    before it measures the cells, and that header keeps its labels' widths
    while the columns report their measured ones, until the table next
    redraws it, as the first hover does. Read them again before each hover.
    """
    cells = await settled(pilot, lambda: painted_headers(pilot.app, table), what)
    # Every column is painted once, in order, before any is hovered.
    assert [column for _x, column in cells] == list(range(len(table.columns))), (
        what,
        cells,
    )
    return [x for x, _column in cells]


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
    await hover_settled(pilot, tooltip, selector)


async def hover_header(
    pilot: Pilot[Any], tooltip: Tooltip, selector: str, index: int
) -> None:
    """Enter the table from outside it over the header of column ``index``.

    The header is found after leaving, just before the mouse enters, so it
    is where the entering move will read it.
    """
    table = pilot.app.screen.query_one(selector, DataTable)
    await leave(pilot, tooltip)
    offsets = await settled_header_offsets(pilot, table, f"the {selector} headers")
    assert await pilot.hover(selector, offset=(offsets[index], 0))
    await hover_settled(pilot, tooltip, selector)


async def move_to_header(
    pilot: Pilot[Any], tooltip: Tooltip, selector: str, index: int
) -> None:
    """Move the mouse onto the header of column ``index`` without leaving the table."""
    table = pilot.app.screen.query_one(selector, DataTable)
    offsets = await settled_header_offsets(pilot, table, f"the {selector} headers")
    await move_within(pilot, tooltip, selector, offsets[index], 0)


async def hover_settled(pilot: Pilot[Any], tooltip: Tooltip, selector: str) -> None:
    """Wait for a hover's outcome: the table's tooltip shown, or none offered.

    The table sets its own ``tooltip`` as the mouse moves; the screen's timer
    then shows it. A table offering none leaves the box hidden, which is
    already so after leaving, so there is nothing further to wait for.
    """
    table = pilot.app.screen.query_one(selector, DataTable)
    await wait_until(lambda: tooltip.display or table.tooltip is None)


async def leave(pilot: Pilot[Any], tooltip: Tooltip) -> None:
    """Rest the mouse in the screen's top-left corner, which no table owns.

    A tooltip opens downward from the mouse, so a tall one can cover a
    widget below the table; the corner above it is never covered.
    """
    assert await pilot.hover(None, offset=(0, 0))
    await wait_until(lambda: not tooltip.display)


async def assert_every_header_shows_its_help(
    pilot: Pilot[Any],
    tooltip: Tooltip,
    selector: str,
    table: DataTable[Any],
    columns: Sequence[DescribedColumn],
) -> None:
    """Hover each header in turn and read the column's own help from the box.

    Then switch between headers without leaving, clear the box over a body
    cell and on leaving, and read the last header again after the terminal
    widens. The table must fit its pane, so every header is under the mouse
    without scrolling; the scrolled case has its own test.
    """
    offsets = await settled_header_offsets(pilot, table, f"the {selector} headers")
    assert len(offsets) == len(columns)
    assert table.virtual_size.width <= table.size.width
    for index, column in enumerate(columns):
        await hover_header(pilot, tooltip, selector, index)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(column)), column.label
        # A box a person can take in beside the header, not a page: the
        # help stays a short paragraph at the widened tooltip.
        box = await settled(pilot, lambda: tooltip.region, f"the {column.label} help")
        assert box.height <= 20, column.label

    # Moving between headers without leaving follows the mouse, and a body
    # cell clears it: the cell is at the far right, clear of the box the
    # first header opened beneath itself.
    await move_to_header(pilot, tooltip, selector, 0)
    await wait_until(lambda: tooltip.display)
    assert str(tooltip.content) == required(column_help(columns[0]))
    await move_within(pilot, tooltip, selector, table.size.width - 3, 1)
    assert not tooltip.display
    assert table.tooltip is None

    # The help follows a resize, and leaving clears it.
    await leave(pilot, tooltip)
    width, height = pilot.app.size
    before = table.size.width
    await pilot.resize_terminal(width + 20, height)
    await wait_until(lambda: table.size.width > before)
    await hover_header(pilot, tooltip, selector, len(columns) - 1)
    await wait_until(lambda: tooltip.display)
    assert str(tooltip.content) == required(column_help(columns[-1]))
    await leave(pilot, tooltip)
    await wait_until(lambda: table.tooltip is None)


def table_labels(table: DataTable[Any]) -> list[str]:
    return [str(column.label) for column in table.columns.values()]


async def move_within(
    pilot: Pilot[Any], tooltip: Tooltip, selector: str, x: int, y: int
) -> None:
    """Move the mouse to ``(x, y)`` without leaving the table.

    The first move hides whatever the table was showing, as Textual does for
    any move within the tooltip's widget; the second restarts the timer, as
    the next tick of a real mouse would.
    """
    assert await pilot.hover(selector, offset=(x, y))
    assert await pilot.hover(selector, offset=(x, y))
    await hover_settled(pilot, tooltip, selector)


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
        offsets = await settled_header_offsets(pilot, table, "the #branches headers")
        assert len(offsets) == len(BRANCH_COLUMNS)

        for index, column in enumerate(BRANCH_COLUMNS):
            await hover_header(pilot, tooltip, "#branches", index)
            await wait_until(lambda: tooltip.display)
            assert str(tooltip.content) == required(column_help(column))
            assert required(column.description) in str(tooltip.content)
            # A box a person can take in beside the header, not a page:
            # the help stays a short paragraph at the widened tooltip.
            box = await settled(pilot, lambda: tooltip.region, f"the {column.key} help")
            assert box.height <= 20, column.key

        # Moving between headers without leaving follows the mouse.
        await move_to_header(pilot, tooltip, "#branches", 6)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(BRANCH_COLUMNS[6]))
        await move_to_header(pilot, tooltip, "#branches", 3)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(BRANCH_COLUMNS[3]))

        # A body cell clears it, and so does leaving. The cell is one to the
        # right of the box the LOCAL header opened beneath itself, since a
        # mouse inside that box rests on the tooltip rather than the table.
        offsets = await settled_header_offsets(pilot, table, "the #branches headers")
        await move_within(pilot, tooltip, "#branches", offsets[7] + 30, 1)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_header(pilot, tooltip, "#branches", 6)
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

        # Nothing beneath the headers, and they still explain themselves; a
        # header without help offers none.
        await hover_header(pilot, tooltip, "#table", 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "the first column"
        await hover_header(pilot, tooltip, "#table", 1)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_header(pilot, tooltip, "#table", 2)
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
async def test_a_header_painted_before_its_cells_are_measured_explains_its_column() -> (
    None
):
    """The help is the column's under the mouse, wherever the header is painted.

    Textual paints a redeclared table's header at its labels' widths when it
    paints before measuring the new row, and keeps that header, while the
    columns report their measured widths, until it next redraws the table.
    """
    columns = [("A", "the first"), ("B", "the second"), ("C", "the third")]
    app = TableApp(columns)
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(80, 10), tooltips=True) as pilot:
        table = app.query_one("#table", FocusCursorTable)
        tooltip = app.screen.query_one(Tooltip)
        await pilot.pause()
        app.declare(columns)
        table.add_row("a-long-first-value", "a-long-second-value", "c")
        painted_headers(app, table)

        for index, (_label, help_text) in enumerate(columns):
            await hover_header(pilot, tooltip, "#table", index)
            await wait_until(lambda: tooltip.display)
            assert str(tooltip.content) == help_text


@pytest.mark.asyncio
async def test_header_help_follows_the_column_under_a_scrolled_header() -> None:
    wide = "x" * 40
    app = TableApp([(wide, "wide"), ("NARROW", "narrow"), ("LAST", "last")])
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(30, 10), tooltips=True) as pilot:
        table = app.query_one("#table", FocusCursorTable)
        tooltip = app.screen.query_one(Tooltip)
        table.add_row("a", "b", "c")
        # The table measures the new row's cells while idle.
        virtual, visible = await settled(
            pilot,
            lambda: (table.virtual_size.width, table.size.width),
            "the wide table's width",
        )
        assert virtual > visible

        await hover_afresh(pilot, tooltip, "#table", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "wide"

        # Scroll the wide column away; the header at the left edge is now
        # a later column, and so is its help.
        table.scroll_to(x=table.virtual_size.width, animate=False, force=True)
        # The scroll is applied after the next refresh, even unanimated.
        await wait_until(lambda: table.scroll_x == table.max_scroll_x > 0)
        await hover_afresh(pilot, tooltip, "#table", table.size.width - 2, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == "last"


@pytest.mark.asyncio
async def test_every_sessions_header_shows_its_help_through_a_dropped_column() -> None:
    """TARGET comes and goes with the Worktrees in view, and the help follows."""
    first = issue("test/repo#1", "First")
    spread = workspace_snapshot(
        first,
        runs=[
            session_run("codex-session:main"),
            session_run("codex-session:linked", target="/repo/wt/issue-42"),
        ],
    )
    together = workspace_snapshot(first, runs=[session_run("codex-session:main")])
    app = dashboard_app(SequenceCollector(spread, together))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(160, 40), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        pane = app.query_one("#sessions-pane", ListPane)
        table = pane.table
        tooltip = app.screen.query_one(Tooltip)
        assert pane.columns == SESSION_COLUMNS
        assert "TARGET" in table_labels(table)
        await assert_every_header_shows_its_help(
            pilot, tooltip, "#sessions", table, pane.columns
        )

        # The linked Worktree's session ends: TARGET is dropped, and the
        # third header, now BRANCH, explains BRANCH rather than the column
        # that used to be there.
        await pilot.press("r")
        await wait_until(lambda: observation_landed(app, 2))
        await wait_until(lambda: "TARGET" not in table_labels(table))
        assert [column.key for column in pane.columns] == [
            column.key for column in SESSION_COLUMNS if column.key != "target"
        ]
        await hover_header(pilot, tooltip, "#sessions", 2)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(SESSION_COLUMNS[3]))
        await assert_every_header_shows_its_help(
            pilot, tooltip, "#sessions", table, pane.columns
        )
        assert app.store.revision == 2


@pytest.mark.asyncio
async def test_every_worktrees_header_shows_its_help() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    snapshot = with_first_project_snapshot(
        snapshot,
        observation_targets=(
            *snapshot_of(snapshot.projects[0]).observation_targets,
            factories.target("/repo/wt/issue-42", role="linked", branch=None),
        ),
    )
    app = dashboard_app(SequenceCollector(snapshot))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(140, 40), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        pane = app.query_one("#worktrees-pane", ListPane)
        assert pane.count == 2
        assert pane.columns == WORKTREE_COLUMNS
        await assert_every_header_shows_its_help(
            pilot, app.screen.query_one(Tooltip), "#worktrees", pane.table, pane.columns
        )


@pytest.mark.asyncio
async def test_every_pull_requests_header_shows_its_help() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        pull_requests=(factories.pull_request(1), factories.pull_request(2)),
    )
    app = dashboard_app(SequenceCollector(snapshot))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(160, 40), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        pane = app.query_screen.query_one("#pull-requests-pane", ListPane)
        assert pane.count == 2
        assert pane.columns == PULL_REQUEST_COLUMNS
        await assert_every_header_shows_its_help(
            pilot,
            app.screen.query_one(Tooltip),
            "#pull-requests",
            pane.table,
            pane.columns,
        )


def issue_columns(app: DashpotApp) -> tuple[ColumnKey, ...]:
    """The Issue table's columns as shown, conditional ones included."""
    return app.query_screen.issue_table_controller.table_columns(
        app.query_screen.query_one("#issues", DataTable)
    )


@pytest.mark.asyncio
async def test_every_issues_header_shows_its_help_through_sorting_and_columns() -> None:
    """The Issue table's help follows sorting, chosen columns and the conditional ones."""
    unlabelled = issue("test/repo#1", "Alpha", labels=["bug"])
    prioritised = issue(
        "test/repo#2",
        "Zebra",
        "P0",
        relationships={
            "parent": None,
            "subIssues": [],
            "blockedBy": [unlabelled.id],
            "blocking": [],
        },
    )
    first = workspace_snapshot(unlabelled)
    second = workspace_snapshot(unlabelled, prioritised)
    app = dashboard_app(SequenceCollector(first, second))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(160, 40), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        table = app.query_screen.query_one("#issues", DataTable)
        tooltip = app.screen.query_one(Tooltip)
        # No listed Issue carries a priority or waits on a blocker, so
        # neither PRIORITY nor WAITING ON is shown yet.
        assert issue_columns(app) == tuple(
            key for key in DEFAULT_COLUMNS if key not in {"priority", "waiting_on"}
        )
        await assert_every_header_shows_its_help(
            pilot, tooltip, "#issues", table, column_specs(issue_columns(app))
        )

        # Selecting a header orders the page and marks the header, and the
        # help is still the column's own; moving between headers without
        # leaving follows the mouse, and a body cell clears the box.
        number = next(key for key in table.columns if key.value == "number")
        table.post_message(
            DataTable.HeaderSelected(
                table,
                number,
                table.get_column_index(number),
                table.columns[number].label,
            )
        )
        await wait_until(lambda: table_labels(table)[2] == "# ↑")
        await hover_header(pilot, tooltip, "#issues", 2)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(COLUMNS_BY_KEY["number"]))
        await move_to_header(pilot, tooltip, "#issues", 3)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(COLUMNS_BY_KEY["title"]))
        # A body cell clears it: one at the right edge, clear of the box the
        # TITLE header opened beneath itself.
        await move_within(pilot, tooltip, "#issues", table.size.width - 3, 1)
        assert not tooltip.display
        assert table.tooltip is None
        assert app.queries.navigation["issues"].request.ordering == "number:asc"

        # Choosing and reordering columns rebuilds the table; each header
        # explains the column now under it.
        app.query_screen.issue_table_controller.apply_issue_columns(
            ("title", "number", "author")
        )
        await pilot.pause()
        assert issue_columns(app) == ("agent_state", "title", "number", "author")
        await assert_every_header_shows_its_help(
            pilot, tooltip, "#issues", table, column_specs(issue_columns(app))
        )

        # A prioritised Issue that waits on Alpha arrives, and the
        # conditional PRIORITY and WAITING ON columns with it, explained like
        # the rest.
        app.query_screen.issue_table_controller.apply_issue_columns(DEFAULT_COLUMNS)
        serve_snapshot(app, second)
        await app.run_action("refresh")
        await wait_until(lambda: observation_landed(app, 2))
        await wait_until(lambda: "PRIORITY ↕" in table_labels(table))
        await pilot.pause()
        assert issue_columns(app) == DEFAULT_COLUMNS
        await hover_header(pilot, tooltip, "#issues", DEFAULT_COLUMNS.index("priority"))
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(column_help(COLUMNS_BY_KEY["priority"]))
        await move_to_header(
            pilot, tooltip, "#issues", DEFAULT_COLUMNS.index("waiting_on")
        )
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(
            column_help(COLUMNS_BY_KEY["waiting_on"])
        )
        await leave(pilot, tooltip)
        await wait_until(lambda: table.tooltip is None)
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_issues_headers_explain_themselves_over_an_empty_page_and_scrolled() -> (
    None
):
    """Every column, chosen at once, scrolls the empty table and keeps its help."""
    closed = issue(
        "test/repo#1",
        "Done",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-25T00:30:00Z",
    )
    app = dashboard_app(SequenceCollector(workspace_snapshot(closed)))
    app.TOOLTIP_DELAY = TOOLTIP_DELAY

    async with app.run_test(size=(100, 30), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        table = app.query_screen.query_one("#issues", DataTable)
        tooltip = app.screen.query_one(Tooltip)
        assert table.row_count == 0
        assert table.show_header
        await hover_afresh(pilot, tooltip, "#issues", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(
            column_help(COLUMNS_BY_KEY["agent_state"])
        )

        # Every column but PRIORITY, which no listed Issue gives a value.
        app.query_screen.issue_table_controller.apply_issue_columns(COLUMN_KEYS)
        assert issue_columns(app) == shown_columns(COLUMN_KEYS, ())
        assert "priority" not in issue_columns(app)
        # The redeclared table measures its columns while idle.
        virtual, visible = await settled(
            pilot,
            lambda: (table.virtual_size.width, table.size.width),
            "the Issue table's width",
        )
        assert virtual > visible
        await hover_afresh(pilot, tooltip, "#issues", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(
            column_help(COLUMNS_BY_KEY["agent_state"])
        )

        # Scrolled to the end, the header at the right edge is the last
        # column, and so is its help; the frozen first column stays.
        table.scroll_to(x=table.virtual_size.width, animate=False, force=True)
        # The scroll is applied after the next refresh, even unanimated.
        await wait_until(lambda: table.scroll_x == table.max_scroll_x > 0)
        await hover_afresh(pilot, tooltip, "#issues", table.size.width - 2, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(
            column_help(COLUMNS_BY_KEY[COLUMN_KEYS[-1]])
        )
        await hover_afresh(pilot, tooltip, "#issues", 0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == required(
            column_help(COLUMNS_BY_KEY["agent_state"])
        )
