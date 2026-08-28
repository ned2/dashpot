from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from dashpot.issue_table import ColumnKey
from dashpot.model import Issue
from helpers import required, snapshot_of

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock

import pytest
from rich.text import Text
from textual.content import Content
from textual.widgets import DataTable, Footer, Input, Markdown, Select, Static

from dashpot.app import (
    DashpotApp,
    issue_pane_state_class,
    project_label,
    selection_detail_items,
    selection_detail_text,
)
from dashpot.column_editor import IssueColumnEditor
from dashpot.detail_fields import DetailFields, detail_items_text
from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.issue_table import (
    COLUMN_KEYS,
    COLUMNS_BY_KEY,
    DEFAULT_COLUMNS,
    DEFAULT_SORT,
    IssueNumberCell,
    IssueStateCell,
    IssueTableViewState,
    LabelsCell,
    SortTerm,
    agent_state_cell,
    build_rows,
    date_cell,
    searchable_columns,
    sort_key_for_terms,
)
from dashpot.issue_view import IssueScreen, issue_metadata_items
from dashpot.local_markdown_issues import parse_local_markdown_issue
from dashpot.model import (
    AgentRun,
    Diagnostic,
    IssueActivity,
    LinkedPullRequest,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    SourceStatus,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore

NOW = "2026-08-25T01:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def issue(reference: str, title: str, priority: str = "P1") -> Issue:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["id"] = f"I_{reference}"
    number_text = reference.rpartition("#")[2]
    if number_text.isdigit() and int(number_text) > 0:
        value["number"] = int(number_text)
    value["reference"] = reference
    value["title"] = title
    value["labels"] = [f"priority/{priority.lower()}"]
    value["assignees"] = []
    return value


def column_sort_key(column: ColumnKey) -> Callable[[object], SupportsRichComparison]:
    """A column's own ordering, for cells that all carry a sort value."""
    spec = COLUMNS_BY_KEY[column]
    return lambda cell: required(spec.sort_key(cell))


def workspace_snapshot(
    *issues: Issue,
    runs: list[AgentRun] | None = None,
    status: SourceStatus = "fresh",
    diagnostics: list[Diagnostic] | None = None,
    elapsed_ms: int = 12,
) -> WorkspaceSnapshot:
    target = ObservationTarget(
        path="/repo",
        head="abcdef123456",
        branch="main",
        detached=False,
        dirty=False,
        availability="available",
        elapsed_ms=3,
        diagnostics=[],
    )
    project_snapshot = ProjectSnapshot(
        project_id="project:test-repo",
        display_label="Test Repository",
        repository_id="repository:test-repo",
        collected_at=NOW,
        issue_source_status=status,
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW if status != "unavailable" else None,
        observation_targets=[target],
        issues=list(issues),
        diagnostics=diagnostics or [],
    )
    project = ProjectObservation(
        project_id="project:test-repo",
        display_label="Test Repository",
        repository_id="repository:test-repo",
        workspaces=["test"],
        anchors=["/repo"],
        primary_anchor="/repo",
        status=status,
        elapsed_ms=elapsed_ms,
        snapshot=project_snapshot,
        diagnostics=[],
    )
    return WorkspaceSnapshot(
        NOW,
        elapsed_ms,
        [project],
        agent_runs=runs or [],
        issue_runs={item["id"]: [] for item in issues},
    )


class SequenceCollector:
    def __init__(self, *results: WorkspaceSnapshot | Exception) -> None:
        self.results = list(results)
        self.lock = Lock()
        self.calls = 0

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            result = self.results.pop(0)
            self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


async def wait_until(predicate: Callable[[], bool], timeout: float = 1.5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not met before timeout")
        await asyncio.sleep(0.01)


def assert_context_above_full_width_queue(app: DashpotApp) -> None:
    body = app.query_one("#body")
    detail_row = app.query_one("#detail-row")
    project_pane = app.query_one("#project-pane")
    selection_pane = app.query_one("#selection-pane")
    queue_pane = app.query_one("#queue-pane")

    assert project_pane.region.y == selection_pane.region.y == detail_row.region.y
    assert project_pane.region.x < selection_pane.region.x
    assert project_pane.region.bottom <= queue_pane.region.y
    assert selection_pane.region.bottom <= queue_pane.region.y
    assert queue_pane.region.x == body.region.x
    assert queue_pane.region.width == body.region.width
    assert project_pane.region.height >= 4
    assert selection_pane.region.height >= 4
    assert queue_pane.region.height >= 6
    assert abs(detail_row.region.height - queue_pane.region.height) <= 2


def detail_plain(app: DashpotApp, selector: str) -> str:
    return app.query_one(selector, DetailFields).plain


def pane_title(app: DashpotApp, selector: str) -> str:
    title = app.query_one(selector)._border_title
    assert title is not None
    return title.plain


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)) as pilot:
        # Before the first observation the pane carries only its label, never
        # a fabricated ``Open 0 · Closed 0`` inventory.
        assert pane_title(app, "#queue-pane") == "ISSUES"
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        table = app.query_one("#queue", DataTable)
        project_detail = detail_plain(app, "#project-detail")
        selection_detail = detail_plain(app, "#selection-detail")
        project_fields = [
            row
            for row in app.query_one("#project-detail", DetailFields).rows
            if row.item.kind == "field"
        ]
        issue_fields = [
            row
            for row in app.query_one("#selection-detail", DetailFields).rows
            if row.item.kind == "field"
        ]

        assert table.row_count == 2
        assert not hasattr(app, "snapshot")
        assert COLUMN_KEYS == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "labels",
            "project",
            "priority",
            "assignees",
            "author",
            "milestone",
            "type",
            "comments",
            "created",
            "last_action",
        )
        assert DEFAULT_COLUMNS == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "last_action",
        )
        assert (SortTerm("last_action", descending=True),) == DEFAULT_SORT
        assert [str(column.label) for column in table.columns.values()] == [
            "◉",
            "◈",
            "# ↕",
            "TITLE",
            "LAST ACTION ↓",
        ]
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert "Status:" not in project_detail
        assert "Anchor: /repo" in project_detail
        assert "Targets:" not in project_detail
        assert "main@abcdef12 clean" not in project_detail
        assert "test/repo" not in project_detail
        assert "Refresh:" not in project_detail
        assert "Reference:" not in selection_detail
        byline, _, rest = selection_detail.partition("\n")
        assert byline.startswith("opened ") and byline.endswith(" by ned2")
        assert rest.startswith("Location: ")
        assert "Status:" not in selection_detail
        assert "Assignees: unassigned" in selection_detail
        assert "Labels: -" in selection_detail
        assert "priority/p1" not in selection_detail
        assert "Agent sessions:" in selection_detail
        assert "Declared" not in selection_detail
        assert "blocked" not in selection_detail.lower()
        assert [row.item.label for row in project_fields] == [
            "Workspaces",
            "Anchor",
            "Agents",
        ]
        assert len({row.field_value.region.x for row in project_fields}) == 1
        assert len({row.field_value.region.x for row in issue_fields}) == 1
        assert all(row.field_name.styles.text_align == "left" for row in issue_fields)
        assert app.ALLOW_SELECT
        assert all(
            row.field_value.allow_select for row in project_fields + issue_fields
        )
        assert not table.allow_select

        location = issue_fields[0].field_value
        assert await pilot.mouse_down(location, offset=(0, 0))
        assert await pilot.mouse_up(location, offset=(5, 0))
        await pilot.pause()
        assert app.clipboard == issue_fields[0].item.value[:6]

        assert pane_title(app, "#project-pane") == "PROJECT STATUS"
        assert pane_title(app, "#selection-pane") == "#1: First"
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 0"
        assert str(app.query_one("#issue-count", Static).render()) == "2 issues"
        assert not app.query("#queue-controls .pane-title")
        assert app.query_one("#selection-pane").has_class("-issue-open")
        app.query_one("#selection-pane").border_title = Content(
            "#1: [bold]literal[/bold]"
        )
        assert pane_title(app, "#selection-pane") == "#1: [bold]literal[/bold]"
        diagnostics = app.query_one("#diagnostics", Static)
        assert_context_above_full_width_queue(app)
        # With nothing to report the Diagnostics box is hidden rather than
        # spending a line on a placeholder.
        assert not diagnostics.has_class("-has-messages")
        assert not diagnostics.display
        assert diagnostics.region.height == 0
    # Private loop state is the only witness that the executor was released.
    assert asyncio.get_running_loop()._default_executor is None  # ty: ignore[unresolved-attribute]


@pytest.mark.asyncio
async def test_app_renders_the_injected_issue_list_query() -> None:
    open_issue = issue("test/repo#1", "Open")
    closed_issue = issue("test/repo#2", "Closed")
    closed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": "2026-08-27T01:00:00Z",
        }
    )
    snapshot = workspace_snapshot(open_issue, closed_issue)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"closed"}))
        ),
    )

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert app.selected_row_key == row_key("issue", closed_issue["id"])
        assert pane_title(app, "#selection-pane") == "#2: Closed"
        assert app.query_one("#selection-pane").has_class("-issue-completed")


@pytest.mark.parametrize(
    ("state", "reason", "state_class", "dark_color", "light_color"),
    [
        ("open", None, "-issue-open", "#238636", "#1f883d"),
        ("closed", "completed", "-issue-completed", "#8957e5", "#8250df"),
        (
            "closed",
            "not-planned",
            "-issue-not-planned",
            "#656c76",
            "#59636e",
        ),
        ("closed", "duplicate", "-issue-duplicate", "#656c76", "#59636e"),
    ],
)
@pytest.mark.asyncio
async def test_selection_pane_tracks_github_issue_state_colors(
    state: str,
    reason: str | None,
    state_class: str,
    dark_color: str,
    light_color: str,
) -> None:
    selected_issue = issue("test/repo#1", "Stateful")
    selected_issue.update(
        {
            "state": state,
            "stateReason": reason,
            "closedAt": NOW if state == "closed" else None,
        }
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(selected_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = app.query_one("#selection-pane")
        table = app.query_one("#queue", DataTable)
        issue_key = row_key("issue", selected_issue["id"])
        assert app.selected_row_key is not None
        selected_context = app.rows_by_key[app.selected_row_key]
        state_cell = table.get_cell(issue_key, "issue_state")

        assert issue_pane_state_class(selected_context) == state_class
        assert pane.has_class(state_class)
        assert pane.styles.border_top[1].hex.casefold() == dark_color
        assert isinstance(state_cell, IssueStateCell)
        assert state_cell.plain == "■"
        assert str(state_cell.style).casefold() == dark_color

        app.theme = "textual-light"
        await pilot.pause()

        assert pane.styles.border_top[1].hex.casefold() == light_color
        light_state_cell = table.get_cell(issue_key, "issue_state")
        assert isinstance(light_state_cell, IssueStateCell)
        assert light_state_cell.plain == "■"
        assert str(light_state_cell.style).casefold() == light_color


@pytest.mark.asyncio
async def test_selection_pane_color_switches_with_selected_issue() -> None:
    open_issue = issue("test/repo#1", "Open")
    completed_issue = issue("test/repo#2", "Completed")
    completed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": NOW,
        }
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(open_issue, completed_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: app.store.revision == 1)

        app.show_row(row_key("issue", open_issue["id"]))
        await pilot.pause()
        pane = app.query_one("#selection-pane")
        assert pane.has_class("-issue-open")
        assert pane.styles.border_top[1].hex == "#238636"

        app.show_row(row_key("issue", completed_issue["id"]))
        await pilot.pause()
        assert pane.has_class("-issue-completed")
        assert not pane.has_class("-issue-open")
        assert pane.styles.border_top[1].hex.casefold() == "#8957e5"


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
        await wait_until(lambda: app.selected_row_key == selected_key)
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
            assert app.issue_view.sort == DEFAULT_SORT
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
        assert app.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert str(table.columns[number_key].label) == "# ↓"


@pytest.mark.asyncio
async def test_keyboard_cycles_sort_column_and_reverses_direction() -> None:
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

        await pilot.press("s")
        assert app.issue_view.sort == (SortTerm("priority"),)
        assert table.get_row_at(0)[table.get_column_index(title_key)] == (
            "Higher priority"
        )

        await pilot.press("shift+s")
        assert app.issue_view.sort == (SortTerm("priority", descending=True),)
        assert table.get_row_at(0)[table.get_column_index(title_key)] == (
            "Lower priority"
        )


@pytest.mark.asyncio
async def test_default_sort_orders_last_action_newest_first_and_missing_last() -> None:
    older = issue("test/repo#1", "Older")
    older["updatedAt"] = "2026-08-25T01:00:00Z"
    missing = issue("test/repo#2", "Missing")
    missing["updatedAt"] = None
    newest = issue("test/repo#3", "Newest")
    newest["updatedAt"] = "2026-08-27T01:00:00Z"
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
    recently_active = issue("test/repo#1", "Recently active")
    recently_active["createdAt"] = "2026-08-01T01:00:00Z"
    recently_active["updatedAt"] = "2026-08-28T01:00:00Z"
    newly_created = issue("test/repo#2", "Newly created")
    newly_created["createdAt"] = "2026-08-27T01:00:00Z"
    newly_created["updatedAt"] = "2026-08-27T02:00:00Z"
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
            lambda: app.issue_view.sort == (SortTerm("created", descending=True),)
        )
        await pilot.pause()

        assert "created" not in app.issue_view.columns
        assert table.get_row_at(0)[title_column] == "Newly created"
        assert app.selected_row_key == row_key("issue", recently_active["id"])

        search.value = ""
        await wait_until(lambda: app.issue_view.sort == DEFAULT_SORT)
        await pilot.pause()

        assert table.get_row_at(0)[title_column] == "Recently active"
        assert app.selected_row_key == row_key("issue", recently_active["id"])


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
        assert app.issue_view.sort == DEFAULT_SORT


@pytest.mark.asyncio
async def test_visible_filters_update_result_count_but_not_inventory() -> None:
    closed_issue = issue("test/repo#3", "Archived Zebra")
    closed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": "2026-08-27T01:00:00Z",
        }
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
            lambda: app.selected_row_key == row_key("issue", closed_issue["id"])
        )
        assert str(count.render()) == "1 issue"
        assert pane_title(app, "#queue-pane") == inventory


@pytest.mark.asyncio
async def test_o_cycles_the_lifecycle_filter_through_the_select() -> None:
    closed_issue = issue("test/repo#3", "Done")
    closed_issue["state"] = "closed"
    closed_issue["stateReason"] = "completed"
    closed_issue["closedAt"] = NOW
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
            lambda: app.selected_row_key == row_key("issue", closed_issue["id"])
        )
        assert app.issue_view.query.states == frozenset({"closed"})
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
    closed_issue = issue("test/repo#3", "Done")
    closed_issue["state"] = "closed"
    closed_issue["stateReason"] = "completed"
    closed_issue["closedAt"] = NOW
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

        await pilot.press("s")
        await pilot.press("S")
        app.apply_issue_columns(("title", "number"))
        await pilot.pause()

        assert app.issue_view.sort != DEFAULT_SORT
        assert app.issue_view.columns == ("title", "number")
        assert table.row_count == 2
        assert str(count.render()) == "2 issues"
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"


@pytest.mark.asyncio
async def test_published_observation_updates_inventory_and_result_count() -> None:
    first = workspace_snapshot(issue("test/repo#1", "First"))
    closed_issue = issue("test/repo#3", "Done")
    closed_issue["state"] = "closed"
    closed_issue["stateReason"] = "completed"
    closed_issue["closedAt"] = NOW
    second = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second"), closed_issue
    )
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(100, 28)):
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 1 · Closed 0"
        assert str(count.render()) == "1 issue"
        assert table.row_count == 1

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"
        assert str(count.render()) == "2 issues"
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_column_editor_applies_visibility_and_order_without_losing_selection() -> (
    None
):
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second"),
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 30)) as pilot:
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.selected_row_key == selected_key)

        await pilot.press("c")
        editor = app.screen
        assert isinstance(editor, IssueColumnEditor)
        selections = editor.query_one("#column-editor-list")
        selections.select("priority")
        selections.highlighted = editor.column_order.index("last_action")
        assert await pilot.click("#column-up")
        await pilot.pause()
        assert await pilot.click("#column-apply")
        await pilot.pause()

        assert app.issue_view.columns == (
            "issue_state",
            "agent_state",
            "number",
            "last_action",
            "title",
            "priority",
        )
        assert [key.value for key in table.columns] == list(app.issue_view.columns)
        assert app.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key


@pytest.mark.asyncio
async def test_refresh_preserves_selection_by_stable_row_key() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    second = workspace_snapshot(
        issue("test/repo#0", "Inserted", "P0"),
        issue("test/repo#1", "First renamed"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.selected_row_key == selected_key)

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert app.selected_row_key == selected_key
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_rows_and_shows_diagnostic() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(RuntimeError("GitHub is unavailable")),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.ui_error is not None)

        assert app.store.revision == 1
        assert app.store.checkpoint() == snapshot
        assert app.query_one("#queue", DataTable).row_count == 1
        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.query_one("#diagnostics", Static).has_class("-has-messages")


@pytest.mark.asyncio
async def test_unavailable_project_observation_keeps_last_good_issue_rows() -> None:
    first = workspace_snapshot(issue("test/repo#1", "Last good"))
    unavailable = copy.deepcopy(first)
    unavailable.projects[0].status = "unavailable"
    unavailable.projects[0].snapshot = None
    unavailable.projects[0].diagnostics = [
        Diagnostic(
            "project:test-repo",
            "error",
            "repository is unavailable",
            "project-collection",
        )
    ]
    app = DashpotApp(
        SequenceCollector(unavailable),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert pane_title(app, "#selection-pane") == "#1: Last good"
        assert "Status:" not in detail_plain(app, "#project-detail")
        assert "repository is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_unavailable_issue_source_keeps_store_owned_last_good_rows() -> None:
    first = workspace_snapshot(issue("test/repo#1", "Last good"))
    observed_run = AgentRun(
        id="codex-session:16",
        harness="codex",
        process_or_session="16",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/16-observation-store",
        issue_id="I_test/repo#1",
        issue_reference_hint="test/repo#1",
    )
    first.agent_runs = [observed_run]
    first.issue_runs = {"I_test/repo#1": [observed_run.id]}
    unavailable = copy.deepcopy(first)
    unavailable.issue_runs = {}
    project = unavailable.projects[0]
    project.status = "unavailable"
    project_snapshot = snapshot_of(project)
    project_snapshot.issue_source_status = "unavailable"
    project_snapshot.issue_source_attempted_at = "2026-08-27T04:00:00Z"
    project_snapshot.issue_source_last_good_at = None
    project_snapshot.issues = []
    project_snapshot.diagnostics = [
        Diagnostic("github", "error", "GitHub unavailable", "github-command")
    ]
    app = DashpotApp(
        SequenceCollector(unavailable),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert pane_title(app, "#selection-pane") == "#1: Last good"
        assert "Status:" not in detail_plain(app, "#project-detail")
        assert "GitHub unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert "Ⅱ" in app.query_one("#queue", DataTable).get_row_at(0)


@pytest.mark.asyncio
async def test_workspace_identity_conflict_is_visible_as_a_diagnostic() -> None:
    snapshot = workspace_snapshot()
    snapshot.diagnostics.append(
        Diagnostic(
            "project:conflicted",
            "error",
            "Project Identity project:conflicted has conflicting Repository identities",
            "project-repository-conflict",
        )
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        rendered = str(app.query_one("#diagnostics", Static).render())
        assert "project:conflicted" in rendered
        assert "conflicting Repository identities" in rendered


@pytest.mark.asyncio
async def test_target_diagnostic_is_visible_without_hiding_project() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    target = snapshot_of(snapshot.projects[0]).observation_targets[0]
    target.availability = "unavailable"
    target.branch = None
    target.detached = False
    target.dirty = None
    target.diagnostics.append(
        Diagnostic(
            "target:/repo",
            "warning",
            "Observation Target is prunable",
            "target-prunable",
        )
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert "prunable" in str(app.query_one("#diagnostics", Static).render())
        assert "Anchor: /repo" in detail_plain(app, "#project-detail")
        assert "unavailable" not in detail_plain(app, "#project-detail")


@pytest.mark.asyncio
async def test_unbound_agent_is_counted_on_the_project_not_listed_as_work() -> None:
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="main",
        issue_id=None,
        issue_reference_hint=None,
    )
    snapshot = workspace_snapshot(issue("test/repo#1", "First"), runs=[run])
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        table = app.query_one("#queue", DataTable)
        assert table.row_count == 1
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert "Agents: 1" in detail_plain(app, "#project-detail")
        assert "Unmatched" not in detail_plain(app, "#selection-detail")
        assert pane_title(app, "#selection-pane") == "#1: First"


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
        assert_context_above_full_width_queue(app)
        assert_counts_fit_in_queue_pane()


def test_project_uses_display_label_independent_of_workspace_and_anchor() -> None:
    project = workspace_snapshot().projects[0]
    project.display_label = "Portable Project"
    project.workspaces = ["personal", "client"]
    project.primary_anchor = "/moved/checkout"

    assert project_label(project) == "Portable Project"


def test_row_projection_respects_visible_column_order() -> None:
    selected_issue = issue("test/repo#1", "First")
    selected_issue["assignees"] = ["ned2"]

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("title", "assignees", "project"),
    )

    selected_key = row_key("issue", selected_issue["id"])
    assert set(contexts) == {selected_key}
    assert cells[selected_key] == ("First", "ned2", "Test Repository")


def test_author_column_is_hidden_by_default_and_sorts_missing_authors_last() -> None:
    authored = issue("test/repo#1", "Authored")
    anonymous = issue("test/repo#2", "Anonymous")
    anonymous["author"] = None

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(authored, anonymous)),
        columns=("author",),
    )

    assert "author" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", authored["id"])] == ("ned2",)
    assert cells[row_key("issue", anonymous["id"])] == ("-",)
    values = [
        cells[row_key("issue", anonymous["id"])][0],
        cells[row_key("issue", authored["id"])][0],
    ]
    ascending = sorted(values, key=sort_key_for_terms((SortTerm("author"),)))
    assert [str(value) for value in ascending] == ["ned2", "-"]


def test_milestone_and_type_columns_are_hidden_by_default_and_optional() -> None:
    classified = issue("test/repo#1", "Classified")
    plain = issue("test/repo#2", "Plain")
    plain["milestone"] = None
    plain["issueType"] = None

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(classified, plain)),
        columns=("milestone", "type"),
    )

    assert "milestone" not in DEFAULT_COLUMNS
    assert "type" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", classified["id"])] == ("v1", "Feature")
    assert cells[row_key("issue", plain["id"])] == ("-", "-")
    ascending = sorted(
        [
            cells[row_key("issue", plain["id"])][0],
            cells[row_key("issue", classified["id"])][0],
        ],
        key=sort_key_for_terms((SortTerm("milestone"),)),
    )
    assert [str(value) for value in ascending] == ["v1", "-"]


def test_issue_detail_shows_milestone_and_type_only_when_present() -> None:
    classified = issue("test/repo#1", "Classified")
    detail = selection_detail_text(
        query_issue_list(workspace_snapshot(classified)).rows[0]
    )
    assert "Milestone: v1\nType: Feature\nAgent sessions:" in detail

    plain = issue("test/repo#2", "Plain")
    plain["milestone"] = None
    plain["issueType"] = None
    detail = selection_detail_text(query_issue_list(workspace_snapshot(plain)).rows[0])
    assert "Milestone:" not in detail
    assert "Type:" not in detail


def test_comments_column_and_detail_show_engagement_only_when_present() -> None:
    discussed = issue("test/repo#1", "Discussed")
    quiet = issue("test/repo#2", "Quiet")
    snapshot = workspace_snapshot(discussed, quiet)
    snapshot_of(snapshot.projects[0]).issue_activity = {
        discussed["id"]: IssueActivity(
            comment_count=4,
            linked_pull_requests=[
                LinkedPullRequest(12, "https://github.com/test/repo/pull/12", "open"),
                LinkedPullRequest(41, "https://github.com/test/repo/pull/41", "merged"),
            ],
        )
    }

    contexts, cells = build_rows(query_issue_list(snapshot), columns=("comments",))

    assert "comments" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", discussed["id"])] == ("4",)
    assert cells[row_key("issue", quiet["id"])] == ("-",)
    ascending = sorted(
        [
            cells[row_key("issue", discussed["id"])][0],
            cells[row_key("issue", quiet["id"])][0],
        ],
        key=sort_key_for_terms((SortTerm("comments"),)),
    )
    assert [str(value) for value in ascending] == ["-", "4"]

    detail = selection_detail_text(contexts[row_key("issue", discussed["id"])])
    assert "Comments: 4\n" in detail
    assert (
        "Pull requests:\n"
        "  #12 open https://github.com/test/repo/pull/12\n"
        "  #41 merged https://github.com/test/repo/pull/41\n"
        "Agent sessions:"
    ) in detail

    quiet_detail = selection_detail_text(contexts[row_key("issue", quiet["id"])])
    assert "Comments:" not in quiet_detail
    assert "Pull requests:" not in quiet_detail


def test_issue_detail_leads_with_the_feed_byline() -> None:
    now = datetime(2026, 8, 29, 5, 33, 4, tzinfo=UTC)
    selected_issue = issue("test/repo#12", "Byline")
    selected_issue["createdAt"] = "2026-08-26T05:33:04Z"
    context = query_issue_list(workspace_snapshot(selected_issue)).rows[0]

    detail = selection_detail_text(context, now=now)

    assert detail.startswith("opened 3d ago by ned2\n")

    selected_issue["author"] = None
    selected_issue["createdAt"] = "2026-08-29T05:20:00Z"
    context = query_issue_list(workspace_snapshot(selected_issue)).rows[0]

    assert selection_detail_text(context, now=now).startswith("opened 13m ago\n")


def test_issue_number_column_uses_the_bare_project_local_number() -> None:
    selected_issue = issue("test/repo#17", "Reference test")

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("number",),
    )

    number = cells[row_key("issue", selected_issue["id"])][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_issue_date_columns_render_iso_dates_and_sort_by_full_timestamp() -> None:
    selected_issue = issue("test/repo#17", "Timestamp test")
    selected_issue["createdAt"] = "2026-08-25T23:30:00Z"
    selected_issue["updatedAt"] = "2026-08-27T01:15:00Z"

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("created", "last_action"),
    )

    assert cells[row_key("issue", selected_issue["id"])] == (
        "2026-08-25",
        "2026-08-27",
    )
    timestamps = [
        date_cell(None),
        date_cell("2026-08-27T01:15:00Z"),
        date_cell("2026-08-27T00:30:00Z"),
    ]
    ascending = sorted(
        timestamps,
        key=sort_key_for_terms((SortTerm("last_action"),)),
    )
    descending = sorted(
        timestamps,
        key=sort_key_for_terms((SortTerm("last_action", descending=True),)),
        reverse=True,
    )
    assert ascending[0] is timestamps[2]
    assert ascending[1] is timestamps[1]
    assert ascending[2] is timestamps[0]
    assert descending[0] is timestamps[1]
    assert descending[1] is timestamps[2]
    assert descending[2] is timestamps[0]


def test_labels_column_renders_tracker_coloured_chips_and_sorts_by_name() -> None:
    labelled = issue("test/repo#1", "Labelled")
    labelled["labels"] = ["bug", "enhancement", "zeta"]
    bare = issue("test/repo#2", "Bare")
    bare["labels"] = []
    snapshot = workspace_snapshot(labelled, bare)
    snapshot_of(snapshot.projects[0]).label_colors = {
        "bug": "d73a4a",
        "enhancement": "a2eeef",
    }

    _contexts, cells = build_rows(query_issue_list(snapshot), columns=("labels",))

    chips = cells[row_key("issue", labelled["id"])][0]
    assert isinstance(chips, LabelsCell)
    assert chips.plain == " bug   enhancement   zeta "
    assert chips.sort_value == ("bug", "enhancement", "zeta")
    styles = [str(span.style) for span in chips.spans]
    assert styles == [
        "#ffffff on #d73a4a",
        "#000000 on #a2eeef",
        "#ffffff on #6e7781",
    ]
    empty = cells[row_key("issue", bare["id"])][0]
    assert isinstance(empty, LabelsCell)
    assert empty.plain == "-"
    assert empty.sort_value is None

    ascending = sorted([empty, chips], key=sort_key_for_terms((SortTerm("labels"),)))
    assert ascending == [chips, empty]
    descending = sorted(
        [empty, chips],
        key=sort_key_for_terms((SortTerm("labels", descending=True),)),
        reverse=True,
    )
    assert descending == [chips, empty]


def test_local_markdown_number_is_the_table_id() -> None:
    document = (
        ROOT / "tests" / "fixtures" / "local-markdown" / "ISSUES.md"
    ).read_text()
    document = (
        document.replace('"id": "I_kwDOUEerrs8AAAABOSTptQ"', '"id": "I_local_17"')
        .replace('"number": 9', '"number": 17')
        .replace('"reference": "ned2/dashpot#9"', '"reference": "local-17"')
    )
    local_issue = parse_local_markdown_issue(
        document,
        project_id="project:test-repo",
        path="issues/local-17.md",
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(local_issue)),
        columns=("number",),
    )

    number = cells[row_key("issue", "I_local_17")][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_selecting_a_sort_column_replaces_the_default_then_toggles_direction() -> None:
    view = IssueTableViewState()

    ascending = view.toggle_sort("number")
    descending = ascending.toggle_sort("number")

    assert ascending.sort == (SortTerm("number"),)
    assert descending.sort == (SortTerm("number", descending=True),)


def test_icon_and_title_columns_are_not_sortable() -> None:
    view = IssueTableViewState(
        columns=("issue_state", "agent_state", "title", "number", "priority"),
        sort=(SortTerm("title"),),
    )

    assert view.toggle_sort("issue_state") is view
    assert view.toggle_sort("agent_state") is view
    assert view.toggle_sort("title") is view
    # From an unsortable current column, cycling continues from its catalogue
    # position: priority follows title, then wraps back to number.
    assert view.cycle_sort().sort == (SortTerm("priority"),)
    assert view.cycle_sort().cycle_sort().sort == (SortTerm("number"),)
    icon_only = IssueTableViewState(
        columns=("issue_state", "agent_state", "title"),
        sort=(),
    )
    assert icon_only.cycle_sort() is icon_only
    assert icon_only.reverse_sort() is icon_only


def test_table_view_rejects_empty_or_duplicate_column_layouts() -> None:
    view = IssueTableViewState()

    with pytest.raises(ValueError, match="at least one"):
        view.with_columns(())
    with pytest.raises(ValueError, match="duplicates"):
        view.with_columns(("title", "title"))


def test_column_catalogue_owns_searchability_and_typed_sort_keys() -> None:
    assert searchable_columns() == frozenset(
        {
            "number",
            "project",
            "assignees",
            "labels",
            "author",
            "milestone",
            "type",
            "title",
        }
    )
    agent_states = [
        agent_state_cell(("running",)),
        agent_state_cell(()),
        agent_state_cell(("waiting",)),
        agent_state_cell(("unknown",)),
    ]

    ordered = sorted(agent_states, key=column_sort_key("agent_state"))

    assert ordered == ["", "?", "Ⅱ", "▶"]
    assert agent_state_cell(("running", "running")) == "▶"
    assert agent_state_cell(("waiting", "running", "unknown")) == "▶"
    assert agent_state_cell(("unknown", "waiting")) == "Ⅱ"
    numbers = [IssueNumberCell(10), IssueNumberCell(2)]

    assert sorted(numbers, key=column_sort_key("number")) == [
        IssueNumberCell(2),
        IssueNumberCell(10),
    ]
    assert all(number.justify == "right" for number in numbers)
    states = [
        IssueStateCell("duplicate", dark=True),
        IssueStateCell("open", dark=True),
        IssueStateCell("not-planned", dark=True),
        IssueStateCell("completed", dark=True),
    ]

    assert [
        cell.state_kind for cell in sorted(states, key=column_sort_key("issue_state"))
    ] == ["open", "completed", "not-planned", "duplicate"]


def test_correlated_run_state_is_visible_in_queue_and_detail() -> None:
    selected_issue = issue("test/repo#1", "First")
    selected_issue["assignees"] = ["ned2"]
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/1",
        issue_id=selected_issue["id"],
        issue_reference_hint=selected_issue["reference"],
    )
    snapshot = workspace_snapshot(selected_issue, runs=[run])
    snapshot.issue_runs[selected_issue["id"]] = [run.id]

    contexts, cells = build_rows(query_issue_list(snapshot))

    selected_key = row_key("issue", selected_issue["id"])
    assert len(cells[selected_key]) == len(DEFAULT_COLUMNS) == 5
    number_cell = cells[selected_key][DEFAULT_COLUMNS.index("number")]
    assert str(number_cell) == "1"
    assert isinstance(number_cell, IssueNumberCell)
    assert number_cell.justify == "right"
    assert cells[selected_key][DEFAULT_COLUMNS.index("agent_state")] == "Ⅱ"
    detail = selection_detail_text(contexts[selected_key])
    assert "Assignees: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


def test_selection_detail_excludes_labels_used_as_priority() -> None:
    selected_issue = issue("test/repo#1", "First")
    selected_issue["labels"] = [
        "bug",
        "priority/p0",
        "priority/p1",
        "priority/p2",
        "priority/p3",
        "critical",
        "high",
        "medium",
        "low",
    ]
    context = query_issue_list(workspace_snapshot(selected_issue)).rows[0]

    detail = selection_detail_text(context)

    assert "Priority: P0" in detail
    assert "Labels: bug" in detail
    assert "priority/" not in detail
    assert "critical" not in detail
    assert "high" not in detail
    assert "medium" not in detail
    assert "low" not in detail


@pytest.mark.asyncio
async def test_selection_detail_uses_one_current_store_projection() -> None:
    selected_issue = issue("test/repo#1", "First")
    snapshot = workspace_snapshot(selected_issue)
    store = WorkspaceObservationStore(snapshot)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=store,
    )
    observed_run = AgentRun(
        id="codex-session:current",
        harness="codex",
        process_or_session="current",
        state="running",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/current",
        issue_id=selected_issue["id"],
        issue_reference_hint=selected_issue["reference"],
    )

    async with app.run_test(size=(80, 24)) as pilot:
        selected_key = row_key("issue", selected_issue["id"])
        await wait_until(lambda: app.selected_row_key == selected_key)
        await pilot.pause()
        stale_row = app.rows_by_key[selected_key]
        assert stale_row.project_runs == ()

        store.replace_agent_runs(
            [observed_run], {selected_issue["id"]: [observed_run.id]}
        )
        app.show_row(selected_key)

        assert "Agents: 1" in detail_plain(app, "#project-detail")
        assert "codex-session:current (running, issue/current)" in detail_plain(
            app, "#selection-detail"
        )


def test_duplicate_issue_identities_get_distinct_project_qualified_rows() -> None:
    duplicated = issue("test/repo#1", "First")
    snapshot = workspace_snapshot(duplicated)
    second = copy.deepcopy(snapshot.projects[0])
    second.project_id = "project:other-repo"
    second.display_label = "Other Repository"
    second.repository_id = "repository:other-repo"
    second_snapshot = snapshot_of(second)
    second_snapshot.project_id = second.project_id
    second_snapshot.display_label = second.display_label
    second_snapshot.repository_id = second.repository_id
    snapshot.projects.append(second)

    contexts, cells = build_rows(query_issue_list(snapshot))

    expected = {
        row_key("issue", "project:test-repo", duplicated["id"]),
        row_key("issue", "project:other-repo", duplicated["id"]),
    }
    assert set(cells) == expected
    assert set(contexts) == expected
    assert {context.project.project_id for context in contexts.values()} == {
        "project:test-repo",
        "project:other-repo",
    }


def test_default_issue_filter_shows_only_open_issues() -> None:
    open_issue = issue("test/repo#1", "Open")
    closed_issue = issue("test/repo#2", "Closed")
    closed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": "2026-08-27T01:00:00Z",
        }
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(open_issue, closed_issue))
    )

    assert set(contexts) == set(cells) == {row_key("issue", open_issue["id"])}
    assert (
        cells[row_key("issue", open_issue["id"])][DEFAULT_COLUMNS.index("title")]
        == "Open"
    )


def test_project_with_only_closed_issues_has_no_open_issues_row() -> None:
    closed_issue = issue("test/repo#2", "Closed")
    closed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": "2026-08-27T01:00:00Z",
        }
    )

    contexts, cells = build_rows(query_issue_list(workspace_snapshot(closed_issue)))

    assert contexts == {}
    assert cells == {}


@pytest.mark.asyncio
async def test_issue_transfer_preserves_selection_by_global_identity() -> None:
    transferred = issue("old/repository#7", "Transfer me")
    first = workspace_snapshot(transferred)
    second = copy.deepcopy(first)
    second.projects[0].project_id = "project:new-repository"
    second.projects[0].display_label = "New Repository"
    second_snapshot = snapshot_of(second.projects[0])
    second_snapshot.project_id = "project:new-repository"
    second_snapshot.display_label = "New Repository"
    second_snapshot.issues[0]["projectId"] = "project:new-repository"
    second_snapshot.issues[0]["number"] = 70
    second_snapshot.issues[0]["reference"] = "new/repository#70"
    selected_key = row_key("issue", transferred["id"])
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        assert app.selected_row_key == selected_key

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.selected_row_key == selected_key
        assert pane_title(app, "#selection-pane") == "#70: Transfer me"


class RacingCollector:
    def __init__(self, old: WorkspaceSnapshot, new: WorkspaceSnapshot) -> None:
        self.old = old
        self.new = new
        self.started = Event()
        self.release = Event()
        self.calls = 0
        self.lock = Lock()

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.started.set()
            self.release.wait(timeout=2)
            return self.old
        return self.new


@pytest.mark.asyncio
async def test_superseded_refresh_cannot_overwrite_newer_result() -> None:
    initial = workspace_snapshot(issue("test/repo#1", "Initial"))
    old = workspace_snapshot(issue("test/repo#1", "Old result"))
    new = workspace_snapshot(issue("test/repo#1", "New result"))
    collector = RacingCollector(old, new)
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(initial),
    )

    try:
        async with app.run_test(size=(80, 24)):
            app.request_refresh("manual")
            await wait_until(collector.started.is_set)
            app.request_refresh("manual")
            await wait_until(lambda: app.store.checkpoint() == new)

            collector.release.set()
            await asyncio.sleep(0.1)
            assert app.store.checkpoint() == new
            assert pane_title(app, "#selection-pane") == "#1: New result"
    finally:
        collector.release.set()


def coordinated_workspace(tmp_path: Path):
    """A two-Project coordinator whose sources can be paused per Project."""
    from dashpot.collect import ObservationCoordinator
    from test_coordinator import Clock, ScriptedCollector, ScriptedSource, resolved

    clock = Clock()
    projects = []
    collectors: dict[str, ScriptedCollector] = {}
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        projects.append(resolved(root, name))
        collectors[name] = ScriptedCollector(ScriptedSource(name, clock=clock), root)
    coordinator = ObservationCoordinator(
        projects,
        factory=lambda project, **_kwargs: collectors[project.project_id],
        agent_observer=lambda _targets: ([], []),
        clock=clock,
    )
    return coordinator, collectors


@pytest.mark.asyncio
async def test_first_published_project_renders_before_a_slow_one(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    collectors["beta"].source.release.clear()
    app = DashpotApp(coordinator, refresh_seconds=0)

    try:
        async with app.run_test(size=(80, 24)):
            table = app.query_one("#queue", DataTable)
            await wait_until(lambda: table.row_count == 1)

            assert not table.loading
            assert row_key("issue", "I_alpha#1") in app.rows_by_key
            assert [p.project_id for p in app.store.checkpoint().projects] == ["alpha"]

            collectors["beta"].source.release.set()
            await wait_until(lambda: table.row_count == 2)

            assert row_key("issue", "I_beta#1") in app.rows_by_key
            await wait_until(
                lambda: (
                    app.store.checkpoint().issue_runs
                    == {"I_alpha#1": [], "I_beta#1": []}
                )
            )
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_refresh_targets_the_selected_project_and_shift_r_fans_out(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        beta_key = row_key("issue", "I_beta#1")
        table.move_cursor(row=table.get_row_index(beta_key), animate=False)
        await wait_until(lambda: app.selected_row_key == beta_key)
        assert app.current_project_id() == "beta"
        calls = {name: c.source.calls for name, c in collectors.items()}

        await app.run_action("refresh")
        await wait_until(lambda: collectors["beta"].source.calls == calls["beta"] + 1)
        await asyncio.sleep(0.05)

        assert collectors["alpha"].source.calls == calls["alpha"]
        assert collectors["beta"].target_calls == 2
        assert collectors["alpha"].target_calls == 1

        await app.run_action("refresh_workspace")
        await wait_until(lambda: collectors["alpha"].source.calls == calls["alpha"] + 1)
        await wait_until(lambda: collectors["beta"].source.calls == calls["beta"] + 2)
        assert app.selected_row_key == beta_key


@pytest.mark.asyncio
async def test_one_failed_observation_kind_does_not_hide_the_other(
    tmp_path: Path,
) -> None:
    from dashpot.issue_sources import IssueSourceRefreshError

    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        collectors["alpha"].source.collections = [
            IssueSourceRefreshError("github-down", "GitHub is unavailable")
        ]
        collectors["alpha"].head = "fresh00"
        revision = app.store.revision

        def alpha_snapshot():
            project = app.store.project("alpha")
            assert project is not None and project.snapshot is not None
            return project.snapshot

        await app.run_action("refresh_workspace")
        # Each half lands on its own; wait for both to have been published.
        await wait_until(
            lambda: (
                app.store.revision > revision
                and alpha_snapshot().issue_source_status == "stale"
                and alpha_snapshot().observation_targets[0].head == "fresh00"
            )
        )

        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert alpha_snapshot().target_status == "fresh"
        assert table.row_count == 2
        assert app.ui_error is None


def alert(app: DashpotApp) -> Static:
    return app.query_one("#alert", Static)


def alert_text(app: DashpotApp) -> str:
    return str(alert(app).render())


@pytest.mark.asyncio
async def test_alert_is_hidden_and_takes_no_space_when_healthy() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert not alert(app).display
        assert alert(app).region.height == 0
        assert not alert(app).has_class("-visible")
        # Neither the alert nor the empty Diagnostics box spends a line, so
        # the Issue pane reaches all the way to the footer.
        diagnostics = app.query_one("#diagnostics", Static)
        assert diagnostics.region.height == 0
        footer = app.query_one(Footer)
        assert app.query_one("#queue-pane").region.bottom == footer.region.y


@pytest.mark.asyncio
async def test_slow_refresh_shows_an_indicator_after_the_threshold(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0, refresh_indicator_seconds=0.2)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        assert not alert(app).display
        collectors["beta"].source.release.clear()

        await app.run_action("refresh_workspace")
        await wait_until(lambda: alert(app).display)

        assert alert(app).has_class("-info")
        assert "refreshing Beta" in alert_text(app)
        await wait_until(lambda: alert(app).region.height == 1)

        collectors["beta"].source.release.set()
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: not app.in_flight)
        assert not alert(app).display


@pytest.mark.asyncio
async def test_quick_refresh_never_flickers_the_indicator(tmp_path: Path) -> None:
    coordinator, _collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0, refresh_indicator_seconds=1.0)
    shown: list[bool] = []

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)

        await app.run_action("refresh_workspace")
        for _ in range(20):
            shown.append(bool(alert(app).display))
            await asyncio.sleep(0.01)
        await wait_until(lambda: not app.in_flight)

        assert not any(shown)
        assert app.refresh_indicator_timer is None


@pytest.mark.asyncio
async def test_refresh_failure_is_a_persistent_alert_that_recovers() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(
        RuntimeError("GitHub is unavailable"),
        RuntimeError("GitHub is unavailable"),
        snapshot,
    )
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: alert(app).display)

        assert alert(app).has_class("-error")
        assert alert_text(app) == "✖ Refresh failed: Test Repository"
        assert len(app._notifications) == 1

        # A repeated identical failure keeps the alert without another toast.
        # Wait for the observation to actually run and settle: requesting the
        # next refresh too early would supersede it before it started.
        await app.run_action("refresh")
        await wait_until(lambda: collector.calls == 2 and not app.in_flight)
        assert len(app._notifications) == 1
        assert alert(app).display

        await app.run_action("refresh")
        await wait_until(lambda: not alert(app).display)

        assert app.ui_error is None
        assert "GitHub is unavailable" not in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_simultaneous_states_share_one_line_in_priority_order() -> None:
    stale = workspace_snapshot(issue("test/repo#1", "First"), status="stale")
    snapshot_of(stale.projects[0]).observation_targets[0].availability = "unavailable"
    app = DashpotApp(
        SequenceCollector(RuntimeError("boom")),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(stale),
    )

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: alert(app).display)
        assert alert_text(app).startswith(
            "⚠ Unavailable worktrees: Test Repository /repo"
        )

        await app.run_action("refresh")
        await wait_until(lambda: alert(app).has_class("-error"))

        text = alert_text(app)
        assert text.index("✖ Refresh failed") < text.index("⚠ Unavailable worktrees")
        assert text.index("⚠ Unavailable worktrees") < text.index("⚠ Stale Issues")
        await wait_until(lambda: alert(app).region.height == 1)
        assert "boom" in str(app.query_one("#diagnostics", Static).render())


@pytest.mark.asyncio
async def test_alert_stays_one_line_in_a_compact_terminal() -> None:
    stale = workspace_snapshot(issue("test/repo#1", "First"), status="stale")
    app = DashpotApp(
        SequenceCollector(stale),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(stale),
    )

    async with app.run_test(size=(60, 18)):
        assert app.screen.has_class("-compact")
        await wait_until(lambda: alert(app).display)

        await wait_until(lambda: alert(app).region.height == 1)
        assert alert(app).region.width == 60
        assert_context_above_full_width_queue(app)

        app.store.replace(workspace_snapshot(issue("test/repo#1", "First")))
        app.update_diagnostics()
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: alert(app).region.height == 0)


# --- Full-screen Issue view (#27) -------------------------------------------


def _issue_view_app(*issues: Issue, runs: list[AgentRun] | None = None) -> DashpotApp:
    snapshot = workspace_snapshot(*issues, runs=runs)
    return DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )


@pytest.mark.asyncio
async def test_enter_opens_the_issue_view_and_escape_restores_the_table() -> None:
    first = issue("test/repo#1", "First")
    second = issue("test/repo#2", "Second")
    second["body"] = (
        "# Heading\n\nSome *emphasis* and a [link](https://example.test).\n\n"
        "- one\n- two\n"
    )
    app = _issue_view_app(first, second)

    async with app.run_test(size=(120, 36)) as pilot:
        table = app.query_one("#queue", DataTable)
        search = app.query_one("#issue-search", Input)
        selected_key = row_key("issue", second["id"])
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.selected_row_key == selected_key)
        search.value = "s"
        await pilot.pause()
        table.focus()

        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        assert isinstance(view, IssueScreen)
        assert str(view.query_one("#issue-view-title", Static).render()) == "Second"
        subtitle = str(view.query_one("#issue-view-subtitle", Static).render())
        assert subtitle.startswith("test/repo#2 · Test Repository · open · opened ")
        assert subtitle.endswith(" by ned2")
        markdown = view.query_one("#issue-view-markdown", Markdown)
        assert markdown.query("MarkdownH1")
        assert markdown.query("MarkdownBulletList")
        assert not view.query("#issue-view-empty")
        assert view.query_one("#issue-view-body").has_focus
        assert not view.stacked

        await pilot.press("tab")
        assert view.query_one("#issue-view-metadata").has_focus
        await pilot.press("shift+tab")
        assert view.query_one("#issue-view-body").has_focus

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        assert app.selected_row_key == selected_key
        assert app.query_one("#issue-search", Input).value == "s"
        assert app.issue_view.query.text == "s"
        assert table.cursor_row == table.get_row_index(selected_key)
        assert table.has_focus


@pytest.mark.asyncio
async def test_issue_view_shows_an_intentional_empty_state_for_a_blank_body() -> None:
    blank = issue("test/repo#1", "Blank")
    blank["body"] = "   \n"
    app = _issue_view_app(blank)

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.selected_row_key == row_key("issue", blank["id"]))
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        view = app.screen
        assert not view.query("#issue-view-markdown")
        assert (
            str(view.query_one("#issue-view-empty", Static).render())
            == "This Issue has no description."
        )


@pytest.mark.asyncio
async def test_issue_view_does_nothing_without_an_issue_row() -> None:
    app = _issue_view_app()

    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert app.selected_row_key is None
        await pilot.press("enter")
        await pilot.pause()
        await app.run_action("open_issue")
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)


@pytest.mark.asyncio
async def test_issue_view_stacks_metadata_under_the_body_in_compact_terminals() -> None:
    app = _issue_view_app(issue("test/repo#1", "Compact"))

    async with app.run_test(size=(70, 30)) as pilot:
        await wait_until(lambda: app.selected_row_key is not None)
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        assert isinstance(view, IssueScreen)
        await wait_until(lambda: view.stacked)
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")
        await wait_until(
            lambda: metadata.region.y >= body.region.y + body.region.height
        )
        assert metadata.region.width == body.region.width


@pytest.mark.asyncio
async def test_refresh_while_the_issue_view_is_open_still_reaches_the_dashboard() -> (
    None
):
    before = workspace_snapshot(issue("test/repo#1", "Before"))
    after = workspace_snapshot(
        issue("test/repo#1", "Before"), issue("test/repo#2", "Arrived")
    )
    app = DashpotApp(
        SequenceCollector(after),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(before),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.selected_row_key is not None)
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        await app.run_action("refresh")
        await wait_until(
            lambda: app.main_screen.query_one("#queue", DataTable).row_count == 2
        )
        assert isinstance(app.screen, IssueScreen)

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        assert app.query_one("#queue", DataTable).row_count == 2


def test_issue_metadata_covers_the_profile_and_marks_absent_values() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    parent = issue("test/repo#1", "Parent")
    child = issue("test/repo#2", "Child")
    child["relationships"] = {
        "parent": parent["id"],
        "subIssues": [],
        "blockedBy": ["I_elsewhere"],
        "blocking": [],
    }
    child["labels"] = ["priority/p1", "bug"]
    child["assignees"] = ["ned2"]
    child["createdAt"] = "2026-08-26T12:00:00Z"
    child["updatedAt"] = "2026-08-29T11:30:00Z"
    run = AgentRun(
        id="run-1",
        harness="codex",
        process_or_session="1",
        state="running",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="feature/child",
        issue_id=None,
        issue_reference_hint=None,
    )
    snapshot = workspace_snapshot(parent, child, runs=[run])
    snapshot.issue_runs[child["id"]] = [run.id]
    snapshot_of(snapshot.projects[0]).issue_activity = {
        child["id"]: IssueActivity(
            comment_count=2,
            linked_pull_requests=[
                LinkedPullRequest(9, "https://github.com/test/repo/pull/9", "merged")
            ],
        )
    }
    context = next(row for row in query_issue_list(snapshot).rows if row.issue is child)

    text = detail_items_text(issue_metadata_items(context, now=now))

    assert text == "\n".join(
        [
            "State: open",
            "Author: ned2",
            "Assignees: ned2",
            "Labels: bug",
            "Priority: P1",
            "Type: Feature",
            "Milestone: v1",
            "Created: 2026-08-26 (3d ago)",
            "Updated: 2026-08-29 (30m ago)",
            "Closed: -",
            "Comments: 2",
            "Pull requests:",
            "  #9 merged https://github.com/test/repo/pull/9",
            "Relationships:",
            "  Parent: #1 Parent",
            "  Blocked by: I_elsewhere",
            "Agent sessions:",
            "  run-1 (running, feature/child)",
        ]
    )

    bare = issue("test/repo#3", "Bare")
    bare["author"] = None
    bare["issueType"] = None
    bare["milestone"] = None
    bare["labels"] = []
    bare["relationships"] = {
        "parent": None,
        "subIssues": [],
        "blockedBy": [],
        "blocking": [],
    }
    bare["state"] = "closed"
    bare["stateReason"] = "not-planned"
    bare["closedAt"] = "2026-08-29T11:00:00Z"
    bare_context = query_issue_list(
        workspace_snapshot(bare), IssueListQuery(states=frozenset({"closed"}))
    ).rows[0]

    bare_text = detail_items_text(issue_metadata_items(bare_context, now=now))

    assert "State: closed as not-planned" in bare_text
    assert "Author: -" in bare_text
    assert "Assignees: unassigned" in bare_text
    assert "Labels: -" in bare_text
    assert "Type: -\nMilestone: -" in bare_text
    assert "Closed: 2026-08-29 (1h ago)" in bare_text
    assert (
        "Comments: 0\nPull requests:\n  -\nRelationships:\n  -\nAgent sessions:\n  -"
    ) in bare_text


def test_detail_panes_render_labels_as_tracker_coloured_chips() -> None:
    labelled = issue("test/repo#1", "Labelled")
    labelled["labels"] = ["bug", "priority/p1"]
    snapshot = workspace_snapshot(labelled)
    snapshot_of(snapshot.projects[0]).label_colors = {"bug": "d73a4a"}
    context = query_issue_list(snapshot).rows[0]

    for items in (
        selection_detail_items(context),
        issue_metadata_items(context),
    ):
        labels = next(item for item in items if item.label == "Labels")
        assert isinstance(labels.value, Text)
        assert labels.value.plain == " bug "
        assert [str(span.style) for span in labels.value.spans] == [
            "#ffffff on #d73a4a"
        ]
        assert "Labels: bug" in detail_items_text(items)
