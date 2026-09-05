"""The dashboard's controls: focus, sorting, search, filters and counts."""

from __future__ import annotations

import pytest
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Select, Static, Tooltip

import factories
from app_harness import (
    NOW,
    SequenceCollector,
    issue,
    pane_title,
    prepare_pane,
    workspace_snapshot,
)
from dashpot.app import DashpotApp
from dashpot.issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    PriorityCell,
)
from dashpot.issue_list import row_key
from dashpot.issue_table import (
    DEFAULT_COLUMNS,
    DEFAULT_SORT,
    IssueTableViewState,
    SortTerm,
)
from dashpot.issue_view import IssueScreen
from dashpot.list_pane import ListRow
from dashpot.observation_store import WorkspaceObservationStore
from helpers import wait_until


@pytest.mark.asyncio
async def test_pull_request_filters_update_rows_matches_and_scoped_summary() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(
            factories.pull_request(1, title="Ready clipboard", author="alice"),
            factories.pull_request(2, title="Draft navigation", is_draft=True),
        ),
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(160, 40)):
        pane = app.dashboard.pull_requests_pane()
        state = app.query_one("#pull-request-state", Select)
        readiness = app.query_one("#pull-request-readiness", Select)
        search = app.query_one("#pull-request-search", Input)
        count = app.query_one("#pull-request-count", Static)

        assert state.value == "open"
        assert pane.table.row_count == 2
        assert str(count.render()) == "2 pull requests"
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 2 · Closed 0"
        )

        readiness.value = "draft"
        await wait_until(lambda: pane.table.row_count == 1)
        assert "Draft navigation" in str(pane.table.get_row_at(0)[2])
        assert str(count.render()) == "1 pull request"
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 1 · Closed 0"
        )

        readiness.value = "all"
        search.value = "author:alice"
        await wait_until(lambda: "Ready clipboard" in str(pane.table.get_row_at(0)[2]))
        assert pane.table.row_count == 1

        search.value = "no-match"
        await wait_until(lambda: pane.table.row_count == 0)
        assert str(count.render()) == "0 pull requests"
        empty = app.query_one("#pull-requests-pane .list-pane-empty", Static)
        assert str(empty.render()) == "no Pull Requests match the current filters"


@pytest.mark.asyncio
async def test_slash_focuses_the_pull_request_search_from_its_table() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(factories.pull_request(1),),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        app.dashboard.pull_requests_pane().table.focus()

        await pilot.press("slash")

        assert app.query_one("#pull-request-search", Input).has_focus


async def select_header(app: DashpotApp, pilot: Pilot[None], column: str) -> None:
    """Click the Issue table's header for ``column``, as the mouse would."""
    table = app.query_one("#queue", DataTable)
    key = next(key for key in table.columns if key.value == column)
    table.post_message(
        DataTable.HeaderSelected(
            table, key, table.get_column_index(key), table.columns[key].label
        )
    )
    await pilot.pause()


@pytest.mark.asyncio
async def test_only_focused_dashboard_table_shows_its_row_cursor() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        tables = {
            table_id: app.query_one(f"#{table_id}", DataTable)
            for table_id in (
                "queue",
                "sessions",
                "worktrees",
                "branches",
                "pull-requests",
            )
        }

        assert {
            table_id for table_id, table in tables.items() if table.show_cursor
        } == {"sessions"}
        for table_id in ("worktrees", "branches", "pull-requests", "queue"):
            await pilot.press("tab")
            assert {
                current_id for current_id, table in tables.items() if table.show_cursor
            } == {table_id}

        await pilot.press("slash")
        assert not any(table.show_cursor for table in tables.values())

        assert await pilot.click("#worktrees", offset=(1, 1))
        assert tables["worktrees"].has_focus
        assert {
            table_id for table_id, table in tables.items() if table.show_cursor
        } == {"worktrees"}


@pytest.mark.asyncio
async def test_header_selection_toggles_sort_and_preserves_selected_issue() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"),
        issue("test/repo#2", "Alpha"),
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#1")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.dashboard.selected_row_key == selected_key)
        title_key = next(key for key in table.columns if key.value == "title")

        for name, label in (
            ("issue_state", "◉"),
            ("agent_state", "◈"),
            ("title", "TITLE"),
        ):
            fixed_key = next(key for key in table.columns if key.value == name)
            table.post_message(
                DataTable.HeaderSelected(
                    table,
                    fixed_key,
                    table.get_column_index(fixed_key),
                    table.columns[fixed_key].label,
                )
            )
            await pilot.pause()
            assert app.dashboard.issue_view.sort == DEFAULT_SORT
            assert str(table.columns[fixed_key].label) == label

        number_key = next(key for key in table.columns if key.value == "number")
        for _ in range(2):
            table.post_message(
                DataTable.HeaderSelected(
                    table,
                    number_key,
                    table.get_column_index(number_key),
                    table.columns[number_key].label,
                )
            )
            await pilot.pause()

        assert table.get_row_at(0)[table.get_column_index(title_key)] == "Alpha"
        assert app.dashboard.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert str(table.columns[number_key].label) == "# ↓"


@pytest.mark.asyncio
async def test_a_header_click_sorts_by_its_column_and_a_second_reverses_it() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Lower priority", "P2"),
        issue("test/repo#2", "Higher priority", "P0"),
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
        issue_view=IssueTableViewState(
            columns=("title", "priority"),
            sort=(SortTerm("title"),),
        ),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        table = app.query_one("#queue", DataTable)
        title_key = next(key for key in table.columns if key.value == "title")

        await select_header(app, pilot, "priority")
        assert app.dashboard.issue_view.sort == (SortTerm("priority"),)
        assert table.get_row_at(0)[table.get_column_index(title_key)] == (
            "Higher priority"
        )

        await select_header(app, pilot, "priority")
        assert app.dashboard.issue_view.sort == (SortTerm("priority", descending=True),)
        assert table.get_row_at(0)[table.get_column_index(title_key)] == (
            "Lower priority"
        )


@pytest.mark.asyncio
async def test_default_sort_orders_last_action_newest_first_and_missing_last() -> None:
    older = issue(
        "test/repo#1",
        "Older",
        updatedAt="2026-08-25T01:00:00Z",
    )
    missing = issue(
        "test/repo#2",
        "Missing",
        updatedAt=None,
    )
    newest = issue(
        "test/repo#3",
        "Newest",
        updatedAt="2026-08-27T01:00:00Z",
    )
    snapshot = workspace_snapshot(older, missing, newest)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        table = app.query_one("#queue", DataTable)
        title_column = table.get_column_index("title")

        assert [
            table.get_row_at(index)[title_column] for index in range(table.row_count)
        ] == ["Newest", "Older", "Missing"]


@pytest.mark.asyncio
async def test_search_sort_qualifier_can_use_hidden_created_and_clear_to_default() -> (
    None
):
    recently_active = issue(
        "test/repo#1",
        "Recently active",
        createdAt="2026-08-01T01:00:00Z",
        updatedAt="2026-08-28T01:00:00Z",
    )
    newly_created = issue(
        "test/repo#2",
        "Newly created",
        createdAt="2026-08-27T01:00:00Z",
        updatedAt="2026-08-27T02:00:00Z",
    )
    snapshot = workspace_snapshot(recently_active, newly_created)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 24)) as pilot:
        table = app.query_one("#queue", DataTable)
        search = app.query_one("#issue-search", Input)
        title_column = table.get_column_index("title")

        assert table.get_row_at(0)[title_column] == "Recently active"

        search.value = "sort:created-desc"
        await wait_until(
            lambda: (
                app.dashboard.issue_view.sort == (SortTerm("created", descending=True),)
            )
        )
        await pilot.pause()

        assert "created" not in app.dashboard.issue_view.columns
        assert table.get_row_at(0)[title_column] == "Newly created"
        assert app.dashboard.selected_row_key == row_key("issue", recently_active.id)

        search.value = ""
        await wait_until(lambda: app.dashboard.issue_view.sort == DEFAULT_SORT)
        await pilot.pause()

        assert table.get_row_at(0)[title_column] == "Recently active"
        assert app.dashboard.selected_row_key == row_key("issue", recently_active.id)


@pytest.mark.asyncio
async def test_a_chosen_sort_survives_search_keystrokes() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second")
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 24)) as pilot:
        search = app.query_one("#issue-search", Input)
        await select_header(app, pilot, "number")
        chosen = app.dashboard.issue_view.sort
        assert chosen != DEFAULT_SORT

        search.value = "s"
        await wait_until(lambda: app.dashboard.issue_view.query.text == "s")
        assert app.dashboard.issue_view.sort == chosen

        # A sort qualifier takes over while it is present, and removing it
        # restores the default rather than the earlier choice.
        search.value = "s sort:created-asc"
        await wait_until(
            lambda: app.dashboard.issue_view.sort == (SortTerm("created"),)
        )
        search.value = "s"
        await wait_until(lambda: app.dashboard.issue_view.sort == DEFAULT_SORT)


@pytest.mark.asyncio
async def test_unsupported_search_sort_is_reported_without_filtering_rows() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 24)):
        search = app.query_one("#issue-search", Input)
        diagnostics = app.query_one("#diagnostics", Static)

        search.value = "sort:comments-desc"
        await wait_until(lambda: "Unsupported sort" in str(diagnostics.render()))

        assert app.query_one("#queue", DataTable).row_count == 1
        assert app.dashboard.issue_view.sort == DEFAULT_SORT


@pytest.mark.asyncio
async def test_visible_filters_update_result_count_but_not_inventory() -> None:
    closed_issue = issue(
        "test/repo#3",
        "Archived Zebra",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
    )
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"),
        issue("test/repo#2", "Alpha"),
        closed_issue,
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 28)):
        count = app.query_one("#issue-count", Static)
        search = app.query_one("#issue-search", Input)
        state = app.query_one("#issue-state", Select)

        inventory = "ISSUES · Open 2 · Closed 1"

        assert str(count.render()) == "2 issues"
        assert pane_title(app, "#queue-pane") == inventory
        search.value = "zebra"
        await wait_until(lambda: str(count.render()) == "1 issue")
        assert app.query_one("#queue", DataTable).row_count == 1
        assert pane_title(app, "#queue-pane") == inventory

        state.value = "closed"
        await wait_until(
            lambda: app.dashboard.selected_row_key == row_key("issue", closed_issue.id)
        )
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory


@pytest.mark.asyncio
async def test_o_cycles_the_lifecycle_filter_through_the_select() -> None:
    closed_issue = issue(
        "test/repo#3",
        "Done",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
    snapshot = workspace_snapshot(issue("test/repo#1", "Alpha"), closed_issue)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 28)) as pilot:
        count = app.query_one("#issue-count", Static)
        state = app.query_one("#issue-state", Select)
        table = app.query_one("#queue", DataTable)
        inventory = "ISSUES · Open 1 · Closed 1"
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "closed")
        await wait_until(
            lambda: app.dashboard.selected_row_key == row_key("issue", closed_issue.id)
        )
        assert app.dashboard.issue_view.query.states == frozenset({"closed"})
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "all")
        await wait_until(lambda: table.row_count == 2)
        assert str(count.render()) == "2 issues"
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "open")
        await wait_until(lambda: table.row_count == 1)
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory


@pytest.mark.asyncio
async def test_result_count_handles_empty_and_singular_states() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "Only"))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 28)):
        count = app.query_one("#issue-count", Static)
        search = app.query_one("#issue-search", Input)
        table = app.query_one("#queue", DataTable)
        inventory = "ISSUES · Open 1 · Closed 0"
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory

        search.value = "no-such-issue"
        await wait_until(lambda: str(count.render()) == "0 issues")
        assert table.row_count == 0
        assert pane_title(app, "#queue-pane") == inventory

        search.value = ""
        await wait_until(lambda: str(count.render()) == "1 issue")
        assert table.row_count == 1
        assert pane_title(app, "#queue-pane") == inventory


@pytest.mark.asyncio
async def test_sorting_and_column_visibility_leave_both_counts_alone() -> None:
    closed_issue = issue(
        "test/repo#3",
        "Done",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"), issue("test/repo#2", "Alpha"), closed_issue
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 28)) as pilot:
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        assert str(count.render()) == "2 issues"
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"

        await select_header(app, pilot, "number")
        app.dashboard.apply_issue_columns(("title", "number"))
        await pilot.pause()

        assert app.dashboard.issue_view.sort != DEFAULT_SORT
        assert app.dashboard.issue_view.columns == ("title", "number")
        assert table.row_count == 2
        assert str(count.render()) == "2 issues"
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"


@pytest.mark.asyncio
async def test_priority_column_comes_and_goes_with_the_rows_the_table_shows() -> None:
    unlabelled = issue(
        "test/repo#1",
        "Alpha",
        labels=["bug"],
    )
    prioritised = issue("test/repo#2", "Zebra", "P0")
    first = workspace_snapshot(unlabelled)
    second = workspace_snapshot(unlabelled, prioritised)
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(100, 28)) as pilot:
        table = app.query_one("#queue", DataTable)
        search = app.query_one("#issue-search", Input)

        def headers() -> list[str]:
            return [str(column.label) for column in table.columns.values()]

        assert app.dashboard.issue_view.columns == DEFAULT_COLUMNS
        assert headers() == ["◉", "◈", "# ↕", "TITLE", "LABELS ↕", "LAST ACTION ↓"]

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)
        await wait_until(lambda: "PRIORITY ↕" in headers())
        assert headers() == [
            "◉",
            "◈",
            "# ↕",
            "TITLE",
            "PRIORITY ↕",
            "LABELS ↕",
            "LAST ACTION ↓",
        ]
        assert table.row_count == 2
        assert app.dashboard.selected_row_key == row_key("issue", unlabelled.id)
        priority_cells = {
            key: table.get_row(key)[4]
            for key in (
                row_key("issue", unlabelled.id),
                row_key("issue", prioritised.id),
            )
        }
        assert [cell.plain for cell in priority_cells.values()] == ["", " P0 "]
        assert all(isinstance(cell, PriorityCell) for cell in priority_cells.values())

        search.value = "alpha"
        await wait_until(lambda: table.row_count == 1)
        assert headers() == ["◉", "◈", "# ↕", "TITLE", "LABELS ↕", "LAST ACTION ↓"]
        await select_header(app, pilot, "number")
        assert app.dashboard.issue_view.sort == (SortTerm("number"),)
        assert headers()[2] == "# ↑"

        # A search change keeps the chosen sort; the column returns and can
        # be sorted by again.
        search.value = ""
        await wait_until(lambda: table.row_count == 2)
        assert app.dashboard.issue_view.sort == (SortTerm("number"),)
        assert headers()[2:5] == ["# ↑", "TITLE", "PRIORITY ↕"]
        await select_header(app, pilot, "priority")
        assert app.dashboard.issue_view.sort == (SortTerm("priority"),)
        assert headers()[4] == "PRIORITY ↑"
        assert table.get_row_at(0)[3] == "Zebra"
        await select_header(app, pilot, "priority")
        assert app.dashboard.issue_view.sort == (SortTerm("priority", descending=True),)
        assert table.get_row_at(0)[3] == "Zebra"


@pytest.mark.asyncio
async def test_tab_cycles_focus_through_every_list() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        queue = app.query_one("#queue", DataTable)
        sessions = app.query_one("#sessions", DataTable)
        worktrees = app.query_one("#worktrees", DataTable)
        branches = app.query_one("#branches", DataTable)
        pull_requests = app.query_one("#pull-requests", DataTable)
        # The Sessions list, first on screen, starts with focus.
        assert sessions.has_focus
        assert app.query_one("#sessions-pane").has_pseudo_class("focus-within")
        assert not app.query_one("#queue-pane").has_pseudo_class("focus-within")

        await pilot.press("tab")
        assert worktrees.has_focus
        assert app.query_one("#worktrees-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert branches.has_focus
        assert app.query_one("#branches-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert pull_requests.has_focus
        assert app.query_one("#pull-requests-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert queue.has_focus
        assert app.query_one("#queue-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert sessions.has_focus
        await pilot.press("shift+tab")
        assert queue.has_focus
        await pilot.press("shift+tab")
        assert pull_requests.has_focus
        await pilot.press("shift+tab")
        assert branches.has_focus
        await pilot.press("shift+tab")
        assert worktrees.has_focus

        # The Issue controls stay reachable from the keyboard.
        await pilot.press("slash")
        assert app.query_one("#issue-search", Input).has_focus
        await pilot.press("tab")
        assert queue.has_focus


@pytest.mark.asyncio
async def test_arrows_move_between_lists_only_at_row_boundaries() -> None:
    app = DashpotApp(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"),
                issue("test/repo#2", "Second"),
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        sessions = prepare_pane(app, "sessions-pane")
        sessions.show_rows(
            (ListRow("first", ("first", "-")), ListRow("last", ("last", "-")))
        )
        await pilot.pause()

        await pilot.press("down")
        assert sessions.table.has_focus
        assert sessions.highlighted() == ("last", 1)

        await pilot.press("down")
        assert app.dashboard.worktrees_pane().table.has_focus

        await pilot.press("up")
        assert sessions.table.has_focus
        assert sessions.highlighted() == ("last", 1)

        await pilot.press("up")
        assert sessions.table.has_focus
        assert sessions.highlighted() == ("first", 0)

        await pilot.press("up")
        assert app.dashboard.queue_table().has_focus


@pytest.mark.asyncio
async def test_arrows_cross_empty_lists_in_composed_order() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        tables = tuple(app.query_one("#body").query(DataTable))
        assert [table.id for table in tables] == [
            "sessions",
            "worktrees",
            "branches",
            "pull-requests",
            "queue",
        ]
        for pane in app.dashboard.list_panes():
            pane.show_rows(())
        await pilot.pause()

        for table in tables[1:] + tables[:1]:
            await pilot.press("down")
            assert table.has_focus

        for table in reversed(tables):
            await pilot.press("up")
            assert table.has_focus


@pytest.mark.asyncio
async def test_hovering_a_glyph_header_shows_its_meaning() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )
    # A zero delay divides by zero inside Textual's Timer; a short one is prompt.
    app.TOOLTIP_DELAY = 0.01

    # Tooltips are off under run_test unless asked for; without this the
    # test would pass vacuously.
    async with app.run_test(size=(100, 28), tooltips=True) as pilot:
        table = app.query_one("#queue", DataTable)
        tooltip = app.screen.query_one(Tooltip)
        widths = [column.get_render_width(table) for column in table.columns.values()]
        agent_state_x = widths[0]
        number_x = widths[0] + widths[1]

        async def hover_table(x: int, y: int) -> None:
            # Leave the table first: Textual hides a showing tooltip on any
            # further move within the same widget without restarting the
            # timer, so a fresh entry is what shows the next one.
            assert await pilot.hover("#pull-request-search")
            await wait_until(lambda: not tooltip.display)
            assert await pilot.hover("#queue", offset=(x, y))
            await pilot.pause(0.05)

        await hover_table(0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == ISSUE_STATE_COLUMN_GLYPH.meaning

        await hover_table(agent_state_x, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == AGENT_STATE_COLUMN_GLYPH.meaning

        # Other headers and the cells beneath carry no tooltip.
        await hover_table(number_x, 0)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_table(0, 1)
        assert not tooltip.display
        assert table.tooltip is None


@pytest.mark.asyncio
async def test_a_row_the_store_cannot_detail_selects_nothing() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")

        app.dashboard.show_row(row_key("issue", "I_gone"))

        # Nothing is selected, so the Open Issue binding opens nothing rather
        # than the previously selected Issue.
        assert app.dashboard.selected_row_key is None
        app.dashboard.action_open_issue()
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)


@pytest.mark.asyncio
async def test_pull_request_lifecycle_and_draft_controls_keep_scoped_counts() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(
            factories.pull_request(1, author="alice"),
            factories.pull_request(2, is_draft=True, author="alice"),
            factories.pull_request(3, state="closed", is_draft=True, author="alice"),
            factories.pull_request(4, state="merged", author="alice"),
            factories.pull_request(5, state="merged", author="bob"),
        ),
    )
    collector = SequenceCollector(snapshot)
    app = DashpotApp(collector, refresh_seconds=0)
    async with app.run_test(size=(120, 40)):
        await wait_until(lambda: app.store.revision == 1)
        pane = app.dashboard.pull_requests_pane()
        lifecycle = app.query_one("#pull-request-state", Select)
        readiness = app.query_one("#pull-request-readiness", Select)
        search = app.query_one("#pull-request-search", Input)
        count = app.query_one("#pull-request-count", Static)
        assert lifecycle.value == "open"
        assert readiness.value == "all"
        assert pane.table.row_count == 2
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 2 · Closed 3"
        )

        lifecycle.value = "closed"
        await wait_until(lambda: pane.table.row_count == 3)
        assert str(count.render()) == "3 pull requests"
        assert "closed draft" in str(pane.table.get_row_at(0)[0])
        assert "merged" in str(pane.table.get_row_at(1)[0])
        search.value = "author:alice"
        await wait_until(lambda: pane.table.row_count == 2)
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 2 · Closed 2"
        )

        readiness.value = "draft"
        await wait_until(lambda: pane.table.row_count == 1)
        assert str(count.render()) == "1 pull request"
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 1 · Closed 1"
        )
        lifecycle.value = "all"
        await wait_until(lambda: pane.table.row_count == 2)
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 1 · Closed 1"
        )
        readiness.value = "ready"
        await wait_until(lambda: "open" in str(pane.table.get_row_at(0)[0]))
        assert pane.table.row_count == 2
        assert "merged" in str(pane.table.get_row_at(1)[0])
        assert collector.calls == 1
