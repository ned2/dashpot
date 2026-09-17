"""The dashboard's controls: focus, ordering, submitted searches, filters and counts."""

from __future__ import annotations

import pytest
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Select, Static, Tooltip

import factories
from app_harness import (
    NOW,
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    page_summary,
    pane_title,
    prepare_pane,
    serve_snapshot,
    toasts,
    workspace_snapshot,
)
from dashpot.observation.issue_list import row_key
from dashpot.ui.app import DashpotApp
from dashpot.ui.issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    PriorityCell,
)
from dashpot.ui.issue_table import DEFAULT_COLUMNS
from dashpot.ui.issue_view import IssueScreen
from dashpot.ui.list_pane import ListRow
from helpers import wait_until


@pytest.mark.asyncio
async def test_pull_request_lifecycle_and_submitted_search_keep_scoped_counts() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(
            factories.pull_request(1, title="Ready clipboard", author="alice"),
            factories.pull_request(
                2, title="Draft navigation", is_draft=True, author="alice"
            ),
            factories.pull_request(3, state="closed", is_draft=True, author="alice"),
            factories.pull_request(4, state="merged", author="alice"),
            factories.pull_request(5, state="merged", author="bob"),
        ),
    )
    collector = SequenceCollector(snapshot)
    app = dashboard_app(collector)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        pane = app.dashboard.pull_requests_pane()
        lifecycle = app.query_one("#pull-request-state", Select)
        assert not app.query("#pull-request-readiness")
        search = app.query_one("#pull-request-search", Input)
        count = app.query_one("#pull-request-count", Static)
        # The pane's inventory is the Project's totals, whatever is submitted.
        inventory = "PULL REQUESTS · Open 2 · Closed 3"

        assert lifecycle.value == "open"
        assert pane.table.row_count == 2
        assert str(count.render()) == "2 pull requests"
        assert pane_title(app, "#pull-requests-pane") == inventory

        # Page keys follow the pane holding focus: the Pull Requests pane
        # pages Pull Requests, and anywhere else pages Issues.
        pane.table.focus()
        await wait_until(lambda: app.dashboard.page_kind() == "pull-requests")
        app.dashboard.queue_table().focus()
        await wait_until(lambda: app.dashboard.page_kind() == "issues")

        # Typing submits nothing; Enter submits the whole text to the source.
        search.value = "draft:true"
        await pilot.pause()
        assert pane.table.row_count == 2
        assert app.queries.navigation["pull-requests"].request.query == ""
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 1)
        assert app.queries.navigation["pull-requests"].request.query == "draft:true"
        assert app.dashboard.list_queries.pull_requests.text == "draft:true"
        assert "Draft navigation" in str(pane.table.get_row_at(0)[2])
        assert str(count.render()) == "1 pull request"
        assert pane_title(app, "#pull-requests-pane") == inventory

        lifecycle.value = "closed"
        await wait_until(
            lambda: app.queries.navigation["pull-requests"].request.state == "closed"
        )
        # The submitted page keeps listing the open draft until the closed
        # one lands, so the wait is on the row itself, not its count.
        await wait_until(
            lambda: (
                pane.table.row_count == 1
                and "closed draft" in str(pane.table.get_row_at(0)[0])
            )
        )

        search.value = "author:alice"
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 2)
        assert "merged" in str(pane.table.get_row_at(1)[0])
        assert str(count.render()) == "2 pull requests"

        lifecycle.value = "all"
        await wait_until(lambda: pane.table.row_count == 4)
        assert pane_title(app, "#pull-requests-pane") == inventory

        search.value = "no-match"
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 0)
        assert str(count.render()) == "0 pull requests"
        empty = app.query_one("#pull-requests-pane .list-pane-empty", Static)
        assert str(empty.render()) == "No matching Pull Requests"
        assert collector.calls == 1


@pytest.mark.asyncio
async def test_slash_focuses_the_pull_request_search_from_its_table() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Issue"),
        pull_requests=(factories.pull_request(1),),
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        app.dashboard.pull_requests_pane().table.focus()

        await pilot.press("slash")

        assert app.query_one("#pull-request-search", Input).has_focus


async def select_header(app: DashpotApp, pilot: Pilot[None], column: str) -> None:
    """Select the Issue table's header for ``column``."""
    # Posting the table's own ``HeaderSelected`` reaches the screen's handler
    # the way a mouse click does without depending on where the header cell
    # lands in the terminal, which the pane's column widths and scroll
    # offset move about.
    table = app.query_one("#queue", DataTable)
    key = next(key for key in table.columns if key.value == column)
    table.post_message(
        DataTable.HeaderSelected(
            table, key, table.get_column_index(key), table.columns[key].label
        )
    )
    await pilot.pause()


async def submit_search(app: DashpotApp, pilot: Pilot[None], text: str) -> None:
    """Type ``text`` into the Issue search and press Enter, as a person would."""
    search = app.query_one("#issue-search", Input)
    search.value = text
    search.focus()
    await pilot.press("enter")
    await wait_until(lambda: app.queries.navigation["issues"].request.query == text)


def headers(app: DashpotApp) -> list[str]:
    return [
        str(column.label)
        for column in app.query_one("#queue", DataTable).columns.values()
    ]


def titles(app: DashpotApp) -> list[str]:
    table = app.query_one("#queue", DataTable)
    title_column = table.get_column_index("title")
    return [
        str(table.get_row_at(index)[title_column]) for index in range(table.row_count)
    ]


@pytest.mark.asyncio
async def test_only_focused_dashboard_table_shows_its_row_cursor() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
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
async def test_a_header_the_source_cannot_order_by_leaves_the_query_alone() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"),
        issue("test/repo#2", "Alpha"),
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        request = app.queries.navigation["issues"].request

        for name, label in (
            ("issue_state", "◉"),
            ("agent_state", "◈"),
            ("title", "TITLE"),
        ):
            fixed_key = next(key for key in table.columns if key.value == name)
            await select_header(app, pilot, name)
            assert app.queries.navigation["issues"].request == request
            assert str(table.columns[fixed_key].label) == label
        # Each refusal is explained once, and nothing was queried for it.
        assert len(toasts(app)) == 3
        assert titles(app) == ["Zebra", "Alpha"]


@pytest.mark.asyncio
async def test_a_header_click_submits_its_ordering_and_a_second_reverses_it() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Lower priority", "P2"),
        issue("test/repo#2", "Higher priority", "P0"),
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        assert titles(app) == ["Lower priority", "Higher priority"]

        await select_header(app, pilot, "priority")
        await wait_until(lambda: titles(app) == ["Higher priority", "Lower priority"])
        assert app.queries.navigation["issues"].request.ordering == "priority:asc"
        assert headers(app)[4] == "PRIORITY ↑"

        await select_header(app, pilot, "priority")
        await wait_until(lambda: titles(app) == ["Lower priority", "Higher priority"])
        assert app.queries.navigation["issues"].request.ordering == "priority:desc"
        assert headers(app)[4] == "PRIORITY ↓"

        # Another column takes over ascending; the page is the source's.
        await select_header(app, pilot, "number")
        await wait_until(
            lambda: app.queries.navigation["issues"].request.ordering == "number:asc"
        )
        await wait_until(lambda: headers(app)[2] == "# ↑")
        assert headers(app)[4] == "PRIORITY ↕"
        assert titles(app) == ["Lower priority", "Higher priority"]


# A submitted ordering restarts the page; the page it replaces stays on screen
# until the reordered one lands, and the cursor re-finds its Issue by key.
@pytest.mark.asyncio
async def test_a_header_click_preserves_the_selected_issue() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"),
        issue("test/repo#2", "Alpha"),
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#1")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(
            lambda: app.dashboard.issue_table.selected_row_key == selected_key
        )

        await select_header(app, pilot, "number")
        await select_header(app, pilot, "number")
        await wait_until(lambda: titles(app) == ["Alpha", "Zebra"])

        assert app.dashboard.issue_table.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key


@pytest.mark.asyncio
async def test_the_table_keeps_the_sources_page_order() -> None:
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()

        # The source's own order stands: nothing is re-sorted locally, and
        # no header claims an order the source did not apply.
        assert titles(app) == ["Older", "Missing", "Newest"]
        assert app.queries.navigation["issues"].request.ordering == "provider-default"
        assert headers(app)[6] == "LAST ACTION ↕"


@pytest.mark.asyncio
async def test_a_submitted_sort_qualifier_owns_the_order_until_it_is_cleared() -> None:
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        assert titles(app) == ["Recently active", "Newly created"]

        await submit_search(app, pilot, "sort:created-desc")
        await wait_until(lambda: titles(app) == ["Newly created", "Recently active"])

        # The qualifier orders the page, so no header offers to.
        assert "created" not in app.dashboard.issue_table.issue_view.columns
        assert app.dashboard.list_queries.issues.text == "sort:created-desc"
        assert headers(app) == [
            "◈",
            "◉",
            "#",
            "TITLE",
            "PRIORITY",
            "LABELS",
            "LAST ACTION",
        ]

        await submit_search(app, pilot, "")
        await wait_until(lambda: titles(app) == ["Recently active", "Newly created"])
        assert headers(app)[2] == "# ↕"


@pytest.mark.asyncio
async def test_a_chosen_ordering_survives_submitted_searches() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second")
    )
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await select_header(app, pilot, "number")
        await select_header(app, pilot, "number")
        await wait_until(lambda: titles(app) == ["Second", "First"])
        assert app.queries.navigation["issues"].request.ordering == "number:desc"

        await submit_search(app, pilot, "s")
        await wait_until(lambda: titles(app) == ["Second", "First"])
        assert app.queries.navigation["issues"].request.ordering == "number:desc"
        assert headers(app)[2] == "# ↓"

        # A sort qualifier takes over while it is present, and removing it
        # restores the chosen ordering rather than the source's default.
        await submit_search(app, pilot, "s sort:created-asc")
        await wait_until(lambda: headers(app)[2] == "#")
        await submit_search(app, pilot, "s")
        await wait_until(lambda: headers(app)[2] == "# ↓")
        assert app.queries.navigation["issues"].request.ordering == "number:desc"


@pytest.mark.asyncio
async def test_visible_filters_update_the_page_summary_but_not_the_totals() -> None:
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 28)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        state = app.query_one("#issue-state", Select)

        inventory = "ISSUES · Open 2 · Closed 1"

        assert str(count.render()) == page_summary(2)
        assert pane_title(app, "#queue-pane") == inventory

        await submit_search(app, pilot, "zebra")
        await wait_until(lambda: str(count.render()) == page_summary(1))
        assert table.row_count == 1
        assert pane_title(app, "#queue-pane") == inventory

        state.value = "closed"
        await wait_until(
            lambda: (
                app.dashboard.issue_table.selected_row_key
                == row_key("issue", closed_issue.id)
            )
        )
        assert app.queries.navigation["issues"].request.state == "closed"
        assert str(count.render()) == page_summary(1)
        assert pane_title(app, "#queue-pane") == inventory

        await submit_search(app, pilot, "no-such-issue")
        await wait_until(lambda: str(count.render()) == page_summary(0))
        assert table.row_count == 0
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 28)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        count = app.query_one("#issue-count", Static)
        state = app.query_one("#issue-state", Select)
        table = app.query_one("#queue", DataTable)
        inventory = "ISSUES · Open 1 · Closed 1"
        assert str(count.render()) == page_summary(1)
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "closed")
        await wait_until(
            lambda: (
                app.dashboard.issue_table.selected_row_key
                == row_key("issue", closed_issue.id)
            )
        )
        assert app.dashboard.list_queries.issues.states == frozenset({"closed"})
        assert app.queries.navigation["issues"].request.state == "closed"
        assert str(count.render()) == page_summary(1)
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "all")
        await wait_until(lambda: table.row_count == 2)
        assert app.queries.navigation["issues"].request.state == "all"
        assert str(count.render()) == page_summary(2)
        assert pane_title(app, "#queue-pane") == inventory

        await pilot.press("o")
        await wait_until(lambda: state.value == "open")
        await wait_until(lambda: table.row_count == 1)
        assert app.queries.navigation["issues"].request.state == "open"
        assert str(count.render()) == page_summary(1)
        assert pane_title(app, "#queue-pane") == inventory


@pytest.mark.asyncio
async def test_ordering_and_column_visibility_leave_both_counts_alone() -> None:
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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 28)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        assert str(count.render()) == page_summary(2)
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"

        await select_header(app, pilot, "number")
        await wait_until(lambda: headers(app)[2] == "# ↑")
        app.dashboard.issue_table.apply_issue_columns(("title", "number"))
        await pilot.pause()

        assert app.queries.navigation["issues"].request.ordering == "number:asc"
        assert app.dashboard.issue_table.issue_view.columns == (
            "agent_state",
            "title",
            "number",
        )
        assert table.row_count == 2
        assert str(count.render()) == page_summary(2)
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
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(100, 28)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)

        assert app.dashboard.issue_table.issue_view.columns == DEFAULT_COLUMNS
        assert headers(app) == ["◈", "◉", "# ↕", "TITLE", "LABELS ↕", "LAST ACTION ↕"]

        serve_snapshot(app, second)
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)
        await wait_until(lambda: "PRIORITY ↕" in headers(app))
        assert headers(app) == [
            "◈",
            "◉",
            "# ↕",
            "TITLE",
            "PRIORITY ↕",
            "LABELS ↕",
            "LAST ACTION ↕",
        ]
        assert table.row_count == 2
        priority_cells = {
            key: table.get_row(key)[4]
            for key in (
                row_key("issue", unlabelled.id),
                row_key("issue", prioritised.id),
            )
        }
        assert [cell.plain for cell in priority_cells.values()] == ["", " P0 "]
        assert all(isinstance(cell, PriorityCell) for cell in priority_cells.values())

        await submit_search(app, pilot, "alpha")
        await wait_until(lambda: table.row_count == 1)
        assert headers(app) == ["◈", "◉", "# ↕", "TITLE", "LABELS ↕", "LAST ACTION ↕"]
        await select_header(app, pilot, "number")
        await wait_until(lambda: headers(app)[2] == "# ↑")
        assert app.queries.navigation["issues"].request.ordering == "number:asc"

        # A search change keeps the chosen ordering; the column returns and
        # can be ordered by again.
        await submit_search(app, pilot, "")
        await wait_until(lambda: table.row_count == 2)
        assert app.queries.navigation["issues"].request.ordering == "number:asc"
        assert headers(app)[2:5] == ["# ↑", "TITLE", "PRIORITY ↕"]
        await select_header(app, pilot, "priority")
        await wait_until(lambda: headers(app)[4] == "PRIORITY ↑")
        assert app.queries.navigation["issues"].request.ordering == "priority:asc"
        assert titles(app)[0] == "Zebra"
        await select_header(app, pilot, "priority")
        await wait_until(lambda: headers(app)[4] == "PRIORITY ↓")
        assert app.queries.navigation["issues"].request.ordering == "priority:desc"
        # A row without a priority stays last in either direction.
        assert titles(app)[0] == "Zebra"


@pytest.mark.asyncio
async def test_tab_cycles_focus_through_every_list() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First")))
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
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
    app = dashboard_app(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"),
                issue("test/repo#2", "Second"),
            )
        )
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
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
        assert sessions.highlighted() == ("first", 0)

        await pilot.press("up")
        assert app.dashboard.queue_table().has_focus


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["tab", "shift+tab", "up", "down", "mouse"])
async def test_entering_each_pane_selects_and_reveals_its_first_row(entry: str) -> None:
    snapshot = workspace_snapshot(
        *(issue(f"test/repo#{number}", f"Issue {number}") for number in range(1, 31))
    )
    app = dashboard_app(SequenceCollector(snapshot))
    async with app.run_test(size=(120, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        for pane in app.dashboard.list_panes():
            prepare_pane(app, str(pane.id)).show_rows(
                tuple(ListRow(str(index), (str(index), "-")) for index in range(30))
            )
        tables = app.dashboard.focus_tables()
        for index, table in enumerate(tables):
            table.focus()
            await wait_until(
                lambda table=table: (
                    table.has_focus and table.show_cursor and table.cursor_row == 0
                )
            )
            await pilot.press("down")
            assert table.cursor_row == 1
            table.move_cursor(row=29, animate=False)
            await wait_until(lambda table=table: table.scroll_y > 0)
            step = -1 if entry in {"shift+tab", "up"} else 1
            source = tables[(index - step) % len(tables)]
            source.focus()
            await wait_until(
                lambda source=source: (
                    source.has_focus and source.show_cursor and source.cursor_row == 0
                )
            )
            if entry == "down":
                source.move_cursor(row=source.row_count - 1, animate=False)
            elif entry == "up":
                source.move_cursor(row=0, animate=False)
            if entry == "mouse":
                assert await pilot.click(table, offset=(1, 0))
            else:
                await pilot.press(entry)
            assert table.has_focus
            assert table.cursor_row == 0
            await wait_until(lambda table=table: table.scroll_y == 0)


@pytest.mark.asyncio
async def test_arrows_cross_empty_lists_in_composed_order() -> None:
    app = dashboard_app(SequenceCollector(workspace_snapshot()))

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: first_load_landed(app))
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
        assert all(table.row_count == 0 for table in tables)

        for table in tables[1:] + tables[:1]:
            await pilot.press("down")
            assert table.has_focus

        for table in reversed(tables):
            await pilot.press("up")
            assert table.has_focus


@pytest.mark.asyncio
async def test_hovering_a_glyph_header_shows_its_meaning() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot))
    # A zero delay divides by zero inside Textual's Timer; a short one is prompt.
    app.TOOLTIP_DELAY = 0.01

    # Tooltips are off under run_test unless asked for; without this the
    # test would pass vacuously.
    async with app.run_test(size=(100, 28), tooltips=True) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        table = app.query_one("#queue", DataTable)
        tooltip = app.screen.query_one(Tooltip)
        widths = [column.get_render_width(table) for column in table.columns.values()]
        issue_state_x = widths[0]
        number_x = widths[0] + widths[1]

        async def hover_table(x: int, y: int) -> None:
            # Leave the table first: Textual hides a showing tooltip on any
            # further move within the same widget without restarting the
            # timer, so a fresh entry is what shows the next one.
            assert await pilot.hover("#pull-request-search")
            await wait_until(lambda: not tooltip.display)
            assert await pilot.hover("#queue", offset=(x, y))
            # The table offered its header's tooltip, now shown, or none.
            await wait_until(lambda: tooltip.display or table.tooltip is None)

        await hover_table(0, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == AGENT_STATE_COLUMN_GLYPH.meaning

        await hover_table(issue_state_x, 0)
        await wait_until(lambda: tooltip.display)
        assert str(tooltip.content) == ISSUE_STATE_COLUMN_GLYPH.meaning

        # Other headers and the cells beneath carry no tooltip.
        await hover_table(number_x, 0)
        assert not tooltip.display
        assert table.tooltip is None
        await hover_table(0, 1)
        assert not tooltip.display
        assert table.tooltip is None


@pytest.mark.asyncio
async def test_a_row_the_store_cannot_detail_selects_nothing() -> None:
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First")))
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        assert app.dashboard.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )

        app.dashboard.issue_table.show_row(row_key("issue", "I_gone"))

        # Nothing is selected, so the Open Issue binding opens nothing rather
        # than the previously selected Issue.
        assert app.dashboard.issue_table.selected_row_key is None
        app.dashboard.action_open_issue()
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)
