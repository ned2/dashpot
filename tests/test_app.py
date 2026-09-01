from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from dashpot.issue_profile import IssueProfile, conform_issue
from dashpot.issue_table import ColumnKey
from helpers import required, snapshot_of

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

import asyncio
import copy
import json
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from threading import Event, Lock

import pytest
from rich.text import Text
from textual.content import Content
from textual.coordinate import Coordinate
from textual.dom import DOMNode
from textual.style import Style
from textual.widget import Widget
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    Markdown,
    Select,
    Static,
    Tooltip,
)

from dashpot import session_list
from dashpot.app import DEFAULT_SUB_TITLE, PANE_MARGIN, DashpotApp, project_label
from dashpot.column_editor import IssueColumnEditor
from dashpot.detail_fields import DetailFields, detail_items_text
from dashpot.issue_list import IssueListQuery, IssueListRow, query_issue_list, row_key
from dashpot.issue_table import (
    AGENT_STATE_COLUMN_GLYPH,
    COLUMN_KEYS,
    COLUMNS_BY_KEY,
    DEFAULT_COLUMNS,
    DEFAULT_SORT,
    ISSUE_STATE_COLUMN_GLYPH,
    IssueNumberCell,
    IssueStateCell,
    IssueTableViewState,
    LabelsCell,
    PriorityCell,
    SortTerm,
    agent_state_cell,
    build_rows,
    date_cell,
    searchable_columns,
    shown_columns,
    sort_key_for_terms,
)
from dashpot.issue_view import (
    IssueScreen,
    issue_byline,
    issue_location,
    issue_metadata_items,
    issue_state_class,
    selection_title,
)
from dashpot.legend import LEGEND, LegendScreen, legend_glyphs, section_heading
from dashpot.list_pane import ListColumn, ListPane, ListRow
from dashpot.local_markdown_issues import parse_local_markdown_issue
from dashpot.model import (
    AgentRun,
    Diagnostic,
    IssueActivity,
    LinkedPullRequest,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    RunState,
    SourceStatus,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore

NOW = "2026-08-25T01:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def issue(
    reference: str, title: str, priority: str = "P1", **overrides: object
) -> IssueProfile:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["id"] = f"I_{reference}"
    number_text = reference.rpartition("#")[2]
    if number_text.isdigit() and int(number_text) > 0:
        value["number"] = int(number_text)
    value["reference"] = reference
    value["title"] = title
    value["labels"] = [f"priority/{priority.lower()}"]
    value["assignees"] = []
    value.update(overrides)
    return conform_issue(value)


def column_sort_key(column: ColumnKey) -> Callable[[object], SupportsRichComparison]:
    """A column's own ordering, for cells that all carry a sort value."""
    spec = COLUMNS_BY_KEY[column]
    return lambda cell: required(spec.sort_key(cell))


def workspace_snapshot(
    *issues: IssueProfile,
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
        role="main",
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
        issue_runs={item.id: [] for item in issues},
    )


class SequenceCollector:
    def __init__(
        self, *results: WorkspaceSnapshot | Exception, release: Event | None = None
    ) -> None:
        self.results = list(results)
        self.lock = Lock()
        self.calls = 0
        # A gated collector holds every observation until the test releases
        # it, so what the app shows before the first result is deterministic.
        self.release = release

    def refresh(self) -> WorkspaceSnapshot:
        if self.release is not None:
            self.release.wait(timeout=2)
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


def assert_panes_stack_above_full_width_queue(app: DashpotApp) -> None:
    """The list panes stack in reading order above the full-width Issue table."""
    body = app.query_one("#body")
    list_row = app.query_one("#list-row")
    sessions = app.query_one("#sessions-pane")
    branches = app.query_one("#branches-pane")
    worktrees = app.query_one("#worktrees-pane")
    queue_pane = app.query_one("#queue-pane")

    assert sessions.region.y == list_row.region.y
    assert sessions.region.bottom <= branches.region.y
    assert branches.region.bottom <= worktrees.region.y
    assert worktrees.region.bottom <= list_row.region.bottom <= queue_pane.region.y
    for pane in (sessions, branches, worktrees, queue_pane):
        assert pane.region.x == body.region.x
        assert pane.region.width == body.region.width
    assert queue_pane.region.height >= 6
    assert not app.query("#detail-row")
    assert not app.query("#project-pane")
    assert not app.query("#selection-pane")


def detail_plain(root: DOMNode, selector: str) -> str:
    return root.query_one(selector, DetailFields).plain


def selected_title(app: DashpotApp) -> str:
    """The compact label of the Issue the table cursor is on."""
    assert app.selected_row_key is not None
    return selection_title(app.rows_by_key[app.selected_row_key])


def pane_title(app: DashpotApp, selector: str) -> str:
    title = app.query_one(selector)._border_title
    assert title is not None
    return title.plain


def pane_subtitle(app: DashpotApp, selector: str) -> str:
    subtitle = app.query_one(selector)._border_subtitle
    assert subtitle is not None
    return subtitle.plain


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    release = Event()
    app = DashpotApp(SequenceCollector(snapshot, release=release), refresh_seconds=0)

    async with app.run_test(size=(80, 24)) as pilot:
        # Before the first observation the pane carries only its label, never
        # a fabricated ``Open 0 · Closed 0`` inventory, and the Header has no
        # anchor to name yet.
        assert pane_title(app, "#queue-pane") == "ISSUES"
        assert app.sub_title == DEFAULT_SUB_TITLE
        release.set()
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        table = app.query_one("#queue", DataTable)

        assert table.row_count == 2
        assert not hasattr(app, "snapshot")
        assert COLUMN_KEYS == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "priority",
            "labels",
            "project",
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
            "priority",
            "labels",
            "last_action",
        )
        assert (SortTerm("last_action", descending=True),) == DEFAULT_SORT
        # Both fixtures carry a priority label, so the conditional column shows.
        assert [str(column.label) for column in table.columns.values()] == [
            "◉",
            "◈",
            "# ↕",
            "TITLE",
            "PRIORITY ↕",
            "LABELS ↕",
            "LAST ACTION ↓",
        ]
        number_key = next(key for key in table.columns if key.value == "number")
        number_header = table.columns[number_key].label
        assert isinstance(number_header, Text)
        assert number_header.justify == "right"
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert selected_title(app) == "#1: First"
        # The Header names the observed Project by its Repository Anchor,
        # never by a label or an Issue Source that could be mistaken for it.
        assert app.title == "Dashpot"
        assert app.sub_title == "/repo"
        assert "test/repo" not in app.sub_title
        assert "Test Repository" not in app.sub_title
        header = str(app.query_one("HeaderTitle", Static).render())
        assert header.startswith("Dashpot")
        assert header.endswith("/repo")
        assert app.ALLOW_SELECT
        assert not table.allow_select

        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 0"
        assert str(app.query_one("#issue-count", Static).render()) == "2 issues"
        assert not app.query("#queue-controls .pane-title")
        diagnostics = app.query_one("#diagnostics", Static)
        assert_panes_stack_above_full_width_queue(app)
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
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
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
        assert app.selected_row_key == row_key("issue", closed_issue.id)
        assert selected_title(app) == "#2: Closed"


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
async def test_issue_view_tracks_github_issue_state_colors(
    state: str,
    reason: str | None,
    state_class: str,
    dark_color: str,
    light_color: str,
) -> None:
    selected_issue = issue(
        "test/repo#1",
        "Stateful",
        state=state,
        stateReason=reason,
        closedAt=NOW if state == "closed" else None,
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(selected_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        table = app.query_one("#queue", DataTable)
        issue_key = row_key("issue", selected_issue.id)
        state_cell = table.get_cell(issue_key, "issue_state")
        assert isinstance(state_cell, IssueStateCell)
        assert state_cell.plain == "■"
        assert str(state_cell.style).casefold() == dark_color

        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")

        assert issue_state_class(selected_issue) == state_class
        assert view.query_one("#issue-view").has_class(state_class)
        # Both border lines carry the state colour: in full on the focused
        # pane and dimmed on the other, so focus still reads without a bar.
        assert body.has_focus
        assert border_color(body) == dark_color
        assert body.styles.border_top[1].a == 1
        assert border_color(metadata) == dark_color
        assert 0 < metadata.styles.border_top[1].a < 1
        # The titles keep the ordinary text colour, and the State value is a
        # chip on the state colour.
        for pane in (body, metadata):
            assert pane.styles.border_title_color.a == 1
            assert pane.styles.border_title_color.hex.casefold() != dark_color
        assert state_chip_background(view) == dark_color
        assert state_chip_text(view).startswith(state)

        await pilot.press("tab")
        assert metadata.has_focus
        assert border_color(metadata) == dark_color
        assert metadata.styles.border_top[1].a == 1
        assert 0 < body.styles.border_top[1].a < 1

        app.theme = "textual-light"
        await wait_until(lambda: border_color(metadata) == light_color)

        assert border_color(body) == light_color
        assert state_chip_background(view) == light_color
        light_state_cell = table.get_cell(issue_key, "issue_state")
        assert isinstance(light_state_cell, IssueStateCell)
        assert light_state_cell.plain == "■"
        assert str(light_state_cell.style).casefold() == light_color


def border_color(pane: Widget) -> str:
    """The pane's border colour without its alpha."""
    return pane.styles.border_top[1].hex.casefold()[:7]


def state_chip(view: DOMNode) -> Text:
    row = next(
        row
        for row in view.query_one("#issue-view-metadata", DetailFields).rows
        if row.item.label == "State"
    )
    assert isinstance(row.item.value, Text)
    return row.item.value


def state_chip_text(view: DOMNode) -> str:
    return state_chip(view).plain.strip()


def state_chip_background(view: DOMNode) -> str:
    return str(state_chip(view).style).casefold().split(" on ")[1]


@pytest.mark.asyncio
async def test_main_screen_tables_do_not_use_zebra_stripes() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)
        tables = tuple(
            app.query_one(f"#{table_id}", DataTable)
            for table_id in ("queue", "sessions", "worktrees", "branches")
        )

        assert all(not table.zebra_stripes for table in tables)


@pytest.mark.asyncio
async def test_only_focused_main_screen_table_shows_its_row_cursor() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        tables = {
            table_id: app.query_one(f"#{table_id}", DataTable)
            for table_id in ("queue", "sessions", "worktrees", "branches")
        }

        assert {
            table_id for table_id, table in tables.items() if table.show_cursor
        } == {"queue"}
        for table_id in ("sessions", "branches", "worktrees"):
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
async def test_issue_view_color_follows_the_opened_issue() -> None:
    open_issue = issue("test/repo#1", "Open")
    completed_issue = issue(
        "test/repo#2",
        "Completed",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(open_issue, completed_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.store.revision == 1)

        app.open_issue(row_key("issue", open_issue.id))
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()
        view = app.screen.query_one("#issue-view")
        assert view.has_class("-issue-open")
        assert border_color(app.screen.query_one("#issue-view-body")) == "#238636"

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        app.open_issue(row_key("issue", completed_issue.id))
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()
        view = app.screen.query_one("#issue-view")
        assert view.has_class("-issue-completed")
        assert not view.has_class("-issue-open")
        assert border_color(app.screen.query_one("#issue-view-body")) == "#8957e5"


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
            lambda: app.issue_view.sort == (SortTerm("created", descending=True),)
        )
        await pilot.pause()

        assert "created" not in app.issue_view.columns
        assert table.get_row_at(0)[title_column] == "Newly created"
        assert app.selected_row_key == row_key("issue", recently_active.id)

        search.value = ""
        await wait_until(lambda: app.issue_view.sort == DEFAULT_SORT)
        await pilot.pause()

        assert table.get_row_at(0)[title_column] == "Recently active"
        assert app.selected_row_key == row_key("issue", recently_active.id)


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
        await pilot.press("s")
        chosen = app.issue_view.sort
        assert chosen != DEFAULT_SORT

        search.value = "s"
        await wait_until(lambda: app.issue_view.query.text == "s")
        assert app.issue_view.sort == chosen

        # A sort qualifier takes over while it is present, and removing it
        # restores the default rather than the earlier choice.
        search.value = "s sort:created-asc"
        await wait_until(lambda: app.issue_view.sort == (SortTerm("created"),))
        search.value = "s"
        await wait_until(lambda: app.issue_view.sort == DEFAULT_SORT)


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
            lambda: app.selected_row_key == row_key("issue", closed_issue.id)
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
            lambda: app.selected_row_key == row_key("issue", closed_issue.id)
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
    closed_issue = issue(
        "test/repo#3",
        "Done",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
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
        selected_line = selections.render_line(editor.column_order.index("title"))
        unselected_line = selections.render_line(editor.column_order.index("project"))
        assert selected_line.text.startswith("▐X▌")
        assert unselected_line.text.startswith("▐ ▌")
        assert (
            list(selected_line)[1].style.color == list(unselected_line)[1].style.color
        )
        selections.select("project")
        selections.highlighted = editor.column_order.index("last_action")
        assert await pilot.click("#column-up")
        await pilot.pause()
        assert await pilot.click("#column-apply")
        await pilot.pause()

        assert app.issue_view.columns == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "priority",
            "last_action",
            "labels",
            "project",
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
        assert selected_title(app) == "#1: Last good"
        assert app.sub_title == "/repo"
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
        assert selected_title(app) == "#1: Last good"
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
async def test_diagnostics_carry_the_severity_they_were_observed_with() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    target = snapshot_of(snapshot.projects[0]).observation_targets[0]
    target.diagnostics.append(
        Diagnostic(
            "target:/repo",
            "info",
            "Observation Target is locked: maintenance",
            "target-locked",
        )
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        diagnostics = app.query_one("#diagnostics", Static)
        rendered = str(diagnostics.render())
        # An observation reads as one, and does not colour the box amber.
        assert rendered.startswith("↻ ")
        assert diagnostics.has_class("-info")
        assert not diagnostics.has_class("-warning")

    mixed = workspace_snapshot(issue("test/repo#1", "First"))
    mixed_target = snapshot_of(mixed.projects[0]).observation_targets[0]
    mixed_target.diagnostics.extend(
        [
            Diagnostic(
                "target:/repo",
                "info",
                "Observation Target is locked: maintenance",
                "target-locked",
            ),
            Diagnostic(
                "target:/repo",
                "warning",
                "Observation Target is prunable",
                "target-prunable",
            ),
        ]
    )
    app = DashpotApp(SequenceCollector(mixed), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        diagnostics = app.query_one("#diagnostics", Static)
        rendered = str(diagnostics.render())
        assert "↻ " in rendered and "⚠ " in rendered
        # The box takes the colour of its most severe line.
        assert diagnostics.has_class("-warning")
        assert not diagnostics.has_class("-info")


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
        assert app.sub_title == "/repo"


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
        assert selected_title(app) == "#1: First"


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


def test_project_uses_display_label_independent_of_workspace_and_anchor() -> None:
    project = workspace_snapshot().projects[0]
    project.display_label = "Portable Project"
    project.workspaces = ["personal", "client"]
    project.primary_anchor = "/moved/checkout"

    assert project_label(project) == "Portable Project"


def test_row_projection_respects_visible_column_order() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        assignees=["ned2"],
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("title", "assignees", "project"),
    )

    selected_key = row_key("issue", selected_issue.id)
    assert set(contexts) == {selected_key}
    assert cells[selected_key] == ("First", "ned2", "Test Repository")


def test_author_column_is_hidden_by_default_and_sorts_missing_authors_last() -> None:
    authored = issue("test/repo#1", "Authored")
    anonymous = issue(
        "test/repo#2",
        "Anonymous",
        author=None,
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(authored, anonymous)),
        columns=("author",),
    )

    assert "author" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", authored.id)] == ("ned2",)
    assert cells[row_key("issue", anonymous.id)] == ("-",)
    values = [
        cells[row_key("issue", anonymous.id)][0],
        cells[row_key("issue", authored.id)][0],
    ]
    ascending = sorted(values, key=sort_key_for_terms((SortTerm("author"),)))
    assert [str(value) for value in ascending] == ["ned2", "-"]


def test_milestone_and_type_columns_are_hidden_by_default_and_optional() -> None:
    classified = issue("test/repo#1", "Classified")
    plain = issue(
        "test/repo#2",
        "Plain",
        milestone=None,
        issueType=None,
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(classified, plain)),
        columns=("milestone", "type"),
    )

    assert "milestone" not in DEFAULT_COLUMNS
    assert "type" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", classified.id)] == ("v1", "Feature")
    assert cells[row_key("issue", plain.id)] == ("-", "-")
    ascending = sorted(
        [
            cells[row_key("issue", plain.id)][0],
            cells[row_key("issue", classified.id)][0],
        ],
        key=sort_key_for_terms((SortTerm("milestone"),)),
    )
    assert [str(value) for value in ascending] == ["v1", "-"]


def test_comments_column_shows_engagement_only_when_present() -> None:
    discussed = issue("test/repo#1", "Discussed")
    quiet = issue("test/repo#2", "Quiet")
    snapshot = workspace_snapshot(discussed, quiet)
    snapshot_of(snapshot.projects[0]).issue_activity = {
        discussed.id: IssueActivity(
            comment_count=4,
            linked_pull_requests=[
                LinkedPullRequest(12, "https://github.com/test/repo/pull/12", "open"),
                LinkedPullRequest(41, "https://github.com/test/repo/pull/41", "merged"),
            ],
        )
    }

    contexts, cells = build_rows(query_issue_list(snapshot), columns=("comments",))

    assert "comments" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", discussed.id)] == ("4",)
    assert cells[row_key("issue", quiet.id)] == ("-",)
    ascending = sorted(
        [
            cells[row_key("issue", discussed.id)][0],
            cells[row_key("issue", quiet.id)][0],
        ],
        key=sort_key_for_terms((SortTerm("comments"),)),
    )
    assert [str(value) for value in ascending] == ["-", "4"]

    detail = issue_metadata_text(contexts[row_key("issue", discussed.id)])
    assert "Comments: 4\n" in detail
    assert (
        "Pull requests:\n"
        "  #12 open https://github.com/test/repo/pull/12\n"
        "  #41 merged https://github.com/test/repo/pull/41\n"
        "Relationships:"
    ) in detail

    quiet_detail = issue_metadata_text(contexts[row_key("issue", quiet.id)])
    assert "Comments: 0\n" in quiet_detail
    assert "Pull requests:\n  -\n" in quiet_detail


def issue_metadata_text(context: IssueListRow) -> str:
    return detail_items_text(issue_metadata_items(context))


def test_issue_byline_frames_the_issue_as_opened_by_its_author() -> None:
    now = datetime(2026, 8, 29, 5, 33, 4, tzinfo=UTC)
    selected_issue = issue(
        "test/repo#12",
        "Byline",
        createdAt="2026-08-26T05:33:04Z",
    )

    assert issue_byline(selected_issue, now=now) == "opened 3d ago by ned2"

    anonymous_issue = issue(
        "test/repo#12",
        "Byline",
        author=None,
        createdAt="2026-08-29T05:20:00Z",
    )

    assert issue_byline(anonymous_issue, now=now) == "opened 13m ago"


def test_issue_location_is_the_url_or_the_local_file_line() -> None:
    hosted = issue("test/repo#12", "Hosted")
    assert hosted.location.kind == "github"
    assert issue_location(hosted) == hosted.location.url

    local = issue(
        "test/repo#13",
        "Local",
        location={"kind": "markdown", "path": "TASKS.md", "line": 7},
    )
    assert issue_location(local) == "TASKS.md:7"


def test_issue_number_column_uses_the_bare_project_local_number() -> None:
    selected_issue = issue("test/repo#17", "Reference test")

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("number",),
    )

    number = cells[row_key("issue", selected_issue.id)][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_issue_date_columns_render_iso_dates_and_sort_by_full_timestamp() -> None:
    selected_issue = issue(
        "test/repo#17",
        "Timestamp test",
        createdAt="2026-08-25T23:30:00Z",
        updatedAt="2026-08-27T01:15:00Z",
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("created", "last_action"),
    )

    assert cells[row_key("issue", selected_issue.id)] == (
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
    labelled = issue(
        "test/repo#1",
        "Labelled",
        labels=["bug", "enhancement", "zeta"],
    )
    bare = issue(
        "test/repo#2",
        "Bare",
        labels=[],
    )
    snapshot = workspace_snapshot(labelled, bare)
    snapshot_of(snapshot.projects[0]).label_colors = {
        "bug": "d73a4a",
        "enhancement": "a2eeef",
    }

    _contexts, cells = build_rows(query_issue_list(snapshot), columns=("labels",))

    chips = cells[row_key("issue", labelled.id)][0]
    assert isinstance(chips, LabelsCell)
    assert chips.plain == " bug   enhancement   zeta "
    assert chips.sort_value == ("bug", "enhancement", "zeta")
    styles = [str(span.style) for span in chips.spans]
    assert styles == [
        "#ffffff on #d73a4a",
        "#000000 on #a2eeef",
        "#ffffff on #6e7781",
    ]
    empty = cells[row_key("issue", bare.id)][0]
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


def test_priority_column_is_a_chip_in_its_source_label_colour() -> None:
    # The most urgent recognized label sets the priority and lends its colour.
    urgent = issue(
        "test/repo#1", "Urgent", labels=["bug", "priority/p3", "priority/P0"]
    )
    routine = issue(
        "test/repo#2",
        "Routine",
        labels=["low"],
    )
    snapshot = workspace_snapshot(urgent, routine)
    snapshot_of(snapshot.projects[0]).label_colors = {
        "bug": "d73a4a",
        "priority/P0": "b60205",
        "priority/p3": "0e8a16",
    }
    result = query_issue_list(snapshot)

    assert "priority" in DEFAULT_COLUMNS
    assert shown_columns(DEFAULT_COLUMNS, result.rows) == DEFAULT_COLUMNS
    for dark in (True, False):
        _contexts, cells = build_rows(result, columns=("priority", "labels"), dark=dark)

        priority, labels = cells[row_key("issue", urgent.id)]
        assert isinstance(priority, PriorityCell)
        assert priority.plain == " P0 "
        assert priority.priority == "P0"
        assert priority.sort_value == 0
        assert [str(span.style) for span in priority.spans] == ["#ffffff on #b60205"]
        # The priority labels leave the LABELS chips rather than render twice.
        assert isinstance(labels, LabelsCell)
        assert labels.labels == ("bug",)
        assert labels.plain == " bug "
        low, bare = cells[row_key("issue", routine.id)]
        assert isinstance(low, PriorityCell)
        assert low.plain == " P3 "
        assert [str(span.style) for span in low.spans] == ["#ffffff on #6e7781"]
        assert isinstance(bare, LabelsCell)
        assert bare.plain == "-"


def test_priority_column_shows_only_while_some_issue_carries_a_priority_label() -> None:
    prioritised = issue("test/repo#1", "Prioritised", "P1")
    unlabelled = issue(
        "test/repo#2",
        "Unlabelled",
        labels=["bug"],
    )
    without_priority = tuple(key for key in DEFAULT_COLUMNS if key != "priority")

    mixed = query_issue_list(workspace_snapshot(prioritised, unlabelled))
    assert shown_columns(DEFAULT_COLUMNS, mixed.rows) == DEFAULT_COLUMNS
    for descending in (False, True):
        _contexts, cells = build_rows(
            mixed,
            columns=("priority",),
            sort=(SortTerm("priority", descending=descending),),
        )
        # An Issue without a priority label shows nothing and sorts after
        # every priority in either direction: no default is invented.
        absent = cells[row_key("issue", unlabelled.id)][0]
        assert isinstance(absent, PriorityCell)
        assert absent.plain == ""
        assert absent.priority is None
        assert absent.sort_value is None
        assert list(cells) == [
            row_key("issue", prioritised.id),
            row_key("issue", unlabelled.id),
        ]

    plain = query_issue_list(workspace_snapshot(unlabelled))
    assert shown_columns(DEFAULT_COLUMNS, plain.rows) == without_priority
    assert shown_columns(DEFAULT_COLUMNS, ()) == without_priority
    assert shown_columns(("title", "labels"), plain.rows) == ("title", "labels")


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

        assert app.issue_view.columns == DEFAULT_COLUMNS
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
        assert app.selected_row_key == row_key("issue", unlabelled.id)
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
        # Cycling the sort passes over the column the table does not show.
        await pilot.press("s")
        assert app.issue_view.sort == (SortTerm("number"),)
        assert headers()[2] == "# ↑"

        # A search change keeps the chosen sort; the column returns and takes
        # its turn in the cycle.
        search.value = ""
        await wait_until(lambda: table.row_count == 2)
        assert app.issue_view.sort == (SortTerm("number"),)
        assert headers()[2:5] == ["# ↑", "TITLE", "PRIORITY ↕"]
        await pilot.press("s")
        assert app.issue_view.sort == (SortTerm("priority"),)
        assert headers()[4] == "PRIORITY ↑"
        assert table.get_row_at(0)[3] == "Zebra"
        await pilot.press("shift+s")
        assert app.issue_view.sort == (SortTerm("priority", descending=True),)
        assert table.get_row_at(0)[3] == "Zebra"


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
    selected_issue = issue(
        "test/repo#1",
        "First",
        assignees=["ned2"],
    )
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/1",
        issue_id=selected_issue.id,
        issue_reference_hint=selected_issue.reference,
    )
    snapshot = workspace_snapshot(selected_issue, runs=[run])
    snapshot.issue_runs[selected_issue.id] = [run.id]

    contexts, cells = build_rows(query_issue_list(snapshot))

    selected_key = row_key("issue", selected_issue.id)
    assert len(cells[selected_key]) == len(DEFAULT_COLUMNS) == 7
    number_cell = cells[selected_key][DEFAULT_COLUMNS.index("number")]
    assert str(number_cell) == "1"
    assert isinstance(number_cell, IssueNumberCell)
    assert number_cell.justify == "right"
    assert cells[selected_key][DEFAULT_COLUMNS.index("agent_state")] == "Ⅱ"
    detail = issue_metadata_text(contexts[selected_key])
    assert "Assignees: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


def test_issue_metadata_excludes_labels_used_as_priority() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        labels=[
            "bug",
            "priority/p0",
            "priority/p1",
            "priority/p2",
            "priority/p3",
            "critical",
            "high",
            "medium",
            "low",
        ],
    )
    context = query_issue_list(workspace_snapshot(selected_issue)).rows[0]

    detail = issue_metadata_text(context)

    assert "Priority: P0" in detail
    assert "Labels: bug" in detail
    assert "priority/" not in detail
    assert "critical" not in detail
    assert "high" not in detail
    assert "medium" not in detail
    assert "low" not in detail
    # Without a recognized label the priority is absent, never a default.
    unprioritised = issue(
        "test/repo#2",
        "Second",
        labels=["bug"],
    )
    context = query_issue_list(workspace_snapshot(unprioritised)).rows[0]

    assert "Priority: -" in issue_metadata_text(context)


@pytest.mark.asyncio
async def test_issue_view_uses_one_current_store_projection() -> None:
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
        issue_id=selected_issue.id,
        issue_reference_hint=selected_issue.reference,
    )

    async with app.run_test(size=(80, 24)) as pilot:
        selected_key = row_key("issue", selected_issue.id)
        await wait_until(lambda: app.selected_row_key == selected_key)
        await pilot.pause()
        stale_row = app.rows_by_key[selected_key]
        assert stale_row.project_runs == ()

        store.replace_agent_runs([observed_run], {selected_issue.id: [observed_run.id]})
        app.open_issue(selected_key)
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()

        assert "codex-session:current (running, issue/current)" in detail_plain(
            app.screen, "#issue-view-metadata"
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
        row_key("issue", "project:test-repo", duplicated.id),
        row_key("issue", "project:other-repo", duplicated.id),
    }
    assert set(cells) == expected
    assert set(contexts) == expected
    assert {context.project.project_id for context in contexts.values()} == {
        "project:test-repo",
        "project:other-repo",
    }


def test_default_issue_filter_shows_only_open_issues() -> None:
    open_issue = issue("test/repo#1", "Open")
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(open_issue, closed_issue))
    )

    assert set(contexts) == set(cells) == {row_key("issue", open_issue.id)}
    assert (
        cells[row_key("issue", open_issue.id)][DEFAULT_COLUMNS.index("title")] == "Open"
    )


def test_project_with_only_closed_issues_has_no_open_issues_row() -> None:
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
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
    second_snapshot.issues[0] = issue(
        "new/repository#70",
        "Transfer me",
        id=transferred.id,
        projectId="project:new-repository",
    )
    selected_key = row_key("issue", transferred.id)
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
        assert selected_title(app) == "#70: Transfer me"


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
            assert selected_title(app) == "#1: New result"
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
async def test_refresh_fans_out_to_every_project(
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
        calls = {name: c.source.calls for name, c in collectors.items()}

        await app.run_action("refresh")
        await wait_until(lambda: collectors["alpha"].source.calls == calls["alpha"] + 1)
        await wait_until(lambda: collectors["beta"].source.calls == calls["beta"] + 1)
        await wait_until(lambda: not app.in_flight)

        assert collectors["alpha"].target_calls == 2
        assert collectors["beta"].target_calls == 2
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

        await app.run_action("refresh")
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
        # A slow runner can leave the initial refresh's own indicator showing.
        await wait_until(lambda: not alert(app).display)
        collectors["beta"].source.release.clear()

        await app.run_action("refresh")
        # On a slow runner the other Projects may still be in flight when the
        # indicator first appears ("refreshing 3 Projects"); only Beta is
        # held, so the readout converges on it.
        await wait_until(lambda: "refreshing Beta" in alert_text(app))

        assert alert(app).display
        assert alert(app).has_class("-info")
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

        await app.run_action("refresh")
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
        assert_panes_stack_above_full_width_queue(app)

        app.store.replace(workspace_snapshot(issue("test/repo#1", "First")))
        app.update_diagnostics()
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: alert(app).region.height == 0)


# --- Full-screen Issue view (#27) -------------------------------------------


def _issue_view_app(
    *issues: IssueProfile, runs: list[AgentRun] | None = None
) -> DashpotApp:
    snapshot = workspace_snapshot(*issues, runs=runs)
    return DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )


@pytest.mark.asyncio
async def test_enter_opens_the_issue_view_and_escape_restores_the_table() -> None:
    first = issue("test/repo#1", "First")
    second = issue(
        "test/repo#2",
        "Second",
        body=(
            "# Heading\n\nSome *emphasis* and a [link](https://example.test).\n\n"
            "- one\n- two\n"
        ),
    )
    app = _issue_view_app(first, second)

    async with app.run_test(size=(120, 36)) as pilot:
        table = app.query_one("#queue", DataTable)
        search = app.query_one("#issue-search", Input)
        selected_key = row_key("issue", second.id)
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.selected_row_key == selected_key)
        search.value = "s"
        await pilot.pause()
        table.focus()

        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        assert isinstance(view, IssueScreen)
        assert not view.query("#issue-view-title")
        # One heading line: where the Issue lives pushed left, and when it
        # was opened pushed right.
        location_widget = view.query_one("#issue-view-location", Static)
        subtitle_widget = view.query_one("#issue-view-subtitle", Static)
        assert second.location.kind == "github"
        assert str(location_widget.render()) == second.location.url
        subtitle = str(subtitle_widget.render())
        assert subtitle.startswith("opened ")
        assert subtitle.endswith(" by ned2")
        assert " · " not in subtitle
        assert subtitle_widget.styles.text_align == "right"
        assert subtitle_widget.styles.text_style.italic
        heading = view.query_one("#issue-view-heading")
        assert heading.region.height == 1
        assert location_widget.region.y == subtitle_widget.region.y
        assert location_widget.region.x == heading.region.x
        assert location_widget.region.right <= subtitle_widget.region.x
        assert subtitle_widget.region.right == heading.region.right
        markdown = view.query_one("#issue-view-markdown", Markdown)
        assert markdown.region.y == heading.region.bottom
        assert markdown.query("MarkdownH1")
        assert markdown.query("MarkdownBulletList")
        assert not view.query("#issue-view-empty")
        assert view.query_one("#issue-view-body").has_focus
        assert not view.stacked
        # Both panes share the main screen's thin inline-title border, and
        # focus is still cued by the border colour rather than a heavier bar.
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")
        assert body._border_title is not None
        assert body._border_title.plain == "#2: Second"
        assert (
            body.styles.border_title_color
            == metadata.styles.border_title_color
            == app.main_screen.query_one("#queue-pane").styles.border_title_color
        )
        assert body.styles.border_top[0] == metadata.styles.border_top[0] == "round"
        assert body.styles.border_top[1] != metadata.styles.border_top[1]

        await pilot.press("tab")
        assert view.query_one("#issue-view-metadata").has_focus
        assert metadata.styles.border_top[1] != body.styles.border_top[1]
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
    blank = issue(
        "test/repo#1",
        "Blank",
        body="   \n",
    )
    app = _issue_view_app(blank)

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.selected_row_key == row_key("issue", blank.id))
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
    child = issue(
        "test/repo#2",
        "Child",
        relationships={
            "parent": parent.id,
            "subIssues": [],
            "blockedBy": ["I_elsewhere"],
            "blocking": [],
        },
        labels=["priority/p1", "bug"],
        assignees=["ned2"],
        createdAt="2026-08-26T12:00:00Z",
        updatedAt="2026-08-29T11:30:00Z",
    )
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
    snapshot.issue_runs[child.id] = [run.id]
    snapshot_of(snapshot.projects[0]).issue_activity = {
        child.id: IssueActivity(
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

    bare = issue(
        "test/repo#3",
        "Bare",
        author=None,
        issueType=None,
        milestone=None,
        labels=[],
        relationships={
            "parent": None,
            "subIssues": [],
            "blockedBy": [],
            "blocking": [],
        },
        state="closed",
        stateReason="not-planned",
        closedAt="2026-08-29T11:00:00Z",
    )
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


def test_issue_view_renders_labels_as_tracker_coloured_chips() -> None:
    labelled = issue(
        "test/repo#1",
        "Labelled",
        labels=["bug", "priority/p1"],
    )
    snapshot = workspace_snapshot(labelled)
    snapshot_of(snapshot.projects[0]).label_colors = {"bug": "d73a4a"}
    context = query_issue_list(snapshot).rows[0]

    items = issue_metadata_items(context)
    labels = next(item for item in items if item.label == "Labels")
    assert isinstance(labels.value, Text)
    assert labels.value.plain == " bug "
    assert [str(span.style) for span in labels.value.spans] == ["#ffffff on #d73a4a"]
    assert "Labels: bug" in detail_items_text(items)


def list_rows(
    count: int, *, prefix: str = "row", issue_id: str | None = None
) -> tuple[ListRow, ...]:
    """Generic pane records standing in for the Sessions and Worktrees rows."""
    return tuple(
        ListRow(f"{prefix}-{index}", (f"{prefix} {index}", "detail"), issue_id=issue_id)
        for index in range(count)
    )


def prepare_pane(app: DashpotApp, pane_id: str) -> ListPane:
    """A pane with the two generic columns the shell tests fill in."""
    pane = app.query_one(f"#{pane_id}", ListPane)
    if not pane.table.columns:
        pane.table.add_column("NAME", key="name")
        pane.table.add_column("DETAIL", key="detail")
    return pane


@pytest.mark.asyncio
async def test_list_columns_align_their_headers_and_values() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 32)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        pane = app.sessions_pane()
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


def pane_chrome(pane: ListPane) -> int:
    """The frame, header and any horizontal scrollbar around a pane's records."""
    return 2 + 1 + (1 if pane.table.show_horizontal_scrollbar else 0)


def footer_keys(app: DashpotApp) -> set[str]:
    return {binding.key for _, binding, *_ in app.screen.active_bindings.values()}


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
async def test_main_screen_stacks_the_panes_above_the_issues() -> None:
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
        queue_pane = app.query_one("#queue-pane")
        assert_panes_stack_above_full_width_queue(app)
        # One blank line separates back-to-back panes.
        assert sessions.region.bottom + 1 == branches.region.y
        assert branches.region.bottom + 1 == worktrees.region.y
        assert pane_title(app, "#sessions-pane") == "SESSIONS · 0"
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        # Remote freshness sits apart from the label and count, aligned to the
        # lower-right pane border. Dashpot never fetches, and this repository
        # never has.
        assert pane_title(app, "#branches-pane") == "BRANCHES · 0"
        assert pane_subtitle(app, "#branches-pane") == (
            "integration unavailable · remote never fetched"
        )
        branches = app.query_one("#branches-pane", ListPane)
        assert branches.styles.border_subtitle_align == "right"
        # An empty pane is one honest line inside its frame, not a blank box.
        assert sessions.region.height == 3
        assert worktrees.region.height == pane_chrome(worktrees) + 1
        assert branches.region.height == 3
        empty_messages = [
            str(message.render())
            for message in app.query(".list-pane-empty").results(Static)
            if message.display
        ]
        assert empty_messages == ["no active sessions", "no branches observed yet"]
        assert not app.query_one("#worktrees-pane .list-pane-empty").display
        assert app.query_one("#queue", DataTable).has_focus
        assert queue_pane.region.height >= 6
        assert "tab" in footer_keys(app)
        assert {"1", "2", "3", "4", "shift+r"}.isdisjoint(footer_keys(app))


@pytest.mark.asyncio
async def test_tab_cycles_focus_through_the_four_lists() -> None:
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
        assert queue.has_focus

        await pilot.press("tab")
        assert sessions.has_focus
        assert app.query_one("#sessions-pane").has_pseudo_class("focus-within")
        assert not app.query_one("#queue-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert branches.has_focus
        assert app.query_one("#branches-pane").has_pseudo_class("focus-within")
        await pilot.press("tab")
        assert worktrees.has_focus
        await pilot.press("tab")
        assert queue.has_focus
        await pilot.press("shift+tab")
        assert worktrees.has_focus
        await pilot.press("shift+tab")
        assert branches.has_focus
        await pilot.press("shift+tab")
        assert sessions.has_focus

        # The Issue controls stay reachable from the keyboard.
        await pilot.press("slash")
        assert app.query_one("#issue-search", Input).has_focus
        await pilot.press("tab")
        assert queue.has_focus


@pytest.mark.asyncio
async def test_pane_grows_with_its_records_to_the_cap_then_scrolls() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = prepare_pane(app, "sessions-pane")

        def flex_height() -> int:
            """The Issue table's height, which is whatever the panes leave."""
            return app.query_one("#queue-pane").region.height

        def other_panes_height() -> int:
            return sum(
                other.region.height for other in app.list_panes() if other is not pane
            )

        def stack_margins() -> int:
            """Each pane carries the blank line below it, inside `#list-row`."""
            return PANE_MARGIN * len(app.list_panes())

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

    # 22 rows: Header, Footer and the Issue table's minimum of 6 leave 14;
    # the empty Branches pane takes the 4 it wants, frame, line and margin,
    # and the two full panes split the rest into a record each.
    async with app.run_test(size=(80, 22)) as pilot:
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

        await pilot.resize_terminal(80, 28)
        await wait_until(
            lambda: sessions.region.height == worktrees.region.height == 2 + 1 + 4
        )
        assert sessions.region.height == worktrees.region.height == 2 + 1 + 4
        assert queue_pane.region.height >= 6
        assert queue_pane.region.bottom <= app.query_one(Footer).region.y

        # Too short even for a record each: the full panes collapse to their
        # counts while the empty one keeps its honest line.
        await pilot.resize_terminal(80, 20)
        await wait_until(lambda: sessions.region.height == worktrees.region.height == 2)
        assert sessions.region.height == worktrees.region.height == 2
        assert app.query_one("#branches-pane").region.height == 3
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 12"
        assert queue_pane.region.height >= 6
        assert queue_pane.region.bottom <= app.query_one(Footer).region.y


@pytest.mark.asyncio
async def test_pane_cursor_leaves_the_issue_selection_alone_and_enter_finds_it() -> (
    None
):
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second")
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert selected_title(app) == "#1: First"
        pane = prepare_pane(app, "sessions-pane")
        pane.show_rows(
            (
                ListRow("bound", ("bound", "-"), issue_id="I_test/repo#2"),
                ListRow("unbound", ("unbound", "-")),
            )
        )
        await pilot.pause()

        await pilot.press("tab")
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == ("unbound", 1)
        assert selected_title(app) == "#1: First"

        await pilot.press("enter")
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert not isinstance(app.screen, IssueScreen)

        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#2")
        assert selected_title(app) == "#2: Second"
        assert app.query_one("#queue", DataTable).cursor_row == 1
        assert not isinstance(app.screen, IssueScreen)
        assert pane.table.has_focus


@pytest.mark.asyncio
async def test_pane_selection_survives_refresh_by_identity_or_moves_to_a_neighbour() -> (
    None
):
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
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
        assert pane.highlighted_row() is None


def session_run(
    run_id: str,
    *,
    state: str = "waiting",
    issue_id: str | None = None,
    harness: str = "codex",
    last_activity_at: str | None = "2026-08-25T00:59:00Z",
    target: str = "/repo",
) -> AgentRun:
    return AgentRun(
        id=run_id,
        harness=harness,
        process_or_session=run_id,
        state=cast("RunState", state),
        observation_target=target,
        observation_project_id="project:test-repo",
        branch="main",
        issue_id=issue_id,
        issue_reference_hint=None,
        working_directory="/repo/src",
        last_activity_at=last_activity_at,
    )


def sessions_snapshot(
    *runs: AgentRun, issues: tuple[IssueProfile, ...]
) -> WorkspaceSnapshot:
    snapshot = workspace_snapshot(*issues, runs=list(runs))
    for run in runs:
        if run.issue_id is not None:
            snapshot.issue_runs.setdefault(run.issue_id, []).append(run.id)
    return snapshot


def session_pane_keys(app: DashpotApp) -> list[str]:
    table = app.sessions_pane().table
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
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        assert pane_title(app, "#sessions-pane") == "SESSIONS · 3"
        assert session_pane_keys(app) == [
            row_key("session", "claude-code-session:free"),
            row_key("session", "work:codex:bound"),
            row_key("session", "codex-session:lost"),
        ]
        table = app.sessions_pane().table
        labels = [str(column.label) for column in table.columns.values()]
        # Every session is in the one Worktree, so TARGET says nothing.
        assert labels == [
            "STATE",
            "HARNESS",
            "BRANCH",
            "ISSUE",
            "DIRECTORY",
            "ACTIVITY",
        ]
        first = [str(cell) for cell in table.get_row_at(0)]
        assert first[:2] == ["● running", "Claude Code"]
        assert first[3] == "no active Issue work"
        # With TARGET dropped, DIRECTORY locates itself in full.
        assert first[4] == "/repo/src"
        second = [str(cell) for cell in table.get_row_at(1)]
        assert second[0] == "◐ waiting"
        assert second[3] == "#2 Second"
        assert str(table.get_row_at(2)[0]) == "○ unknown"
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
    app = DashpotApp(SequenceCollector(spread, together), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        table = app.sessions_pane().table
        assert "TARGET" in [str(column.label) for column in table.columns.values()]
        assert {
            str(table.get_row_at(index)[2]) for index in range(table.row_count)
        } == {"/repo", "/repo/wt/issue-42"}

        # The linked Worktree's session ends, and the column stops earning
        # its width without waiting for a restart.
        await pilot.press("r")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()

        table = app.sessions_pane().table
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
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)
    running = session_list.STATE_GLYPHS["running"]

    def state_color() -> str:
        cell = app.sessions_pane().table.get_row_at(0)[0]
        assert isinstance(cell, Text)
        return str(cell.style).casefold()

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert state_color() == running.style(dark=True)

        app.theme = "textual-light"
        # Without a new observation, only the theme handler can repaint.
        await wait_until(lambda: state_color() == running.style(dark=False))


@pytest.mark.asyncio
async def test_enter_on_a_bound_session_highlights_its_issue_and_unbound_is_safe() -> (
    None
):
    issues = (issue("test/repo#1", "First"), issue("test/repo#2", "Second"))
    snapshot = sessions_snapshot(
        session_run("work:codex:bound", state="running", issue_id="I_test/repo#2"),
        session_run("codex-session:free", state="waiting"),
        issues=issues,
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert selected_title(app) == "#1: First"

        await pilot.press("tab")
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert selected_title(app) == "#1: First"

        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#2")
        assert selected_title(app) == "#2: Second"
        assert not isinstance(app.screen, IssueScreen)
        assert app.sessions_pane().table.has_focus


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
    app = DashpotApp(SequenceCollector(first, reordered, without_b), refresh_seconds=0)

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = app.sessions_pane()
        await pilot.press("tab")
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 1)

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()
        assert pane.highlighted() == (row_key("session", "b"), 0)

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 3)
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
    snapshot_of(with_linked.projects[0]).observation_targets.append(linked)
    stale_with_linked = copy.deepcopy(with_linked)
    snapshot_of(stale_with_linked.projects[0]).target_status = "stale"
    app = DashpotApp(
        SequenceCollector(first, with_linked, stale_with_linked, first),
        refresh_seconds=0,
    )

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        pane = app.worktrees_pane()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        columns = list(pane.table.columns.values())
        labels = [str(column.label) for column in columns]
        assert labels == ["PATH", "KIND", "BRANCH", "TREE", "SESSIONS"]
        sessions_header = columns[-1].label
        assert isinstance(sessions_header, Text)
        assert sessions_header.justify == "center"
        main_cells = [str(cell) for cell in pane.table.get_row_at(0)]
        assert main_cells == [
            "/repo",
            "main",
            "main",
            "clean",
            "-",
        ]
        sessions_value = pane.table.get_row_at(0)[-1]
        assert isinstance(sessions_value, Text)
        assert sessions_value.justify == "center"

        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 2"
        await pilot.press("tab", "tab", "tab")
        await pilot.press("down")
        await pilot.pause()
        assert pane.highlighted() == (
            row_key("worktree", "project:test-repo", "/repo-linked"),
            1,
        )
        linked_cells = [str(cell) for cell in pane.table.get_row_at(1)]
        assert linked_cells == [
            "/repo-linked · unavailable",
            "linked",
            "detached @ def4567",
            "unknown",
            "-",
        ]
        # Highlighting a worktree leaves the Issue-driven panes alone.
        assert selected_title(app) == "#1: First"
        await pilot.press("enter")
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert not isinstance(app.screen, IssueScreen)

        # A retained topology names stale explicitly without restoring STATE.
        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 3)
        await pilot.pause()
        stale_cells = [str(cell) for cell in pane.table.get_row_at(1)]
        assert stale_cells[0] == "/repo-linked · stale"

        # The linked worktree is removed: the cursor moves to a neighbour.
        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 4)
        await pilot.pause()
        assert pane_title(app, "#worktrees-pane") == "WORKTREES · 1"
        assert pane.highlighted() == (
            row_key("worktree", "project:test-repo", "/repo"),
            0,
        )


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


def test_glyph_header_tooltips_are_the_meanings_the_legend_shows() -> None:
    assert COLUMNS_BY_KEY["issue_state"].tooltip == ISSUE_STATE_COLUMN_GLYPH.meaning
    assert COLUMNS_BY_KEY["agent_state"].tooltip == AGENT_STATE_COLUMN_GLYPH.meaning
    assert {key for key, spec in COLUMNS_BY_KEY.items() if spec.tooltip} == {
        "issue_state",
        "agent_state",
    }


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
            assert await pilot.hover("#issue-search")
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
async def test_question_mark_opens_the_legend_and_escape_closes_it() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert "question_mark" in footer_keys(app)

        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        screen = app.screen
        headings = [
            str(heading.render()) for heading in screen.query(".legend-heading")
        ]
        assert headings[0] == "SESSIONS · STATE"
        assert headings[-1] == "KEYS"
        assert headings[:-1] == [section_heading(section) for section in LEGEND]
        rendered = "\n".join(
            str(section.render()) for section in screen.query(".legend-section")
        )
        for glyph in legend_glyphs():
            assert glyph.symbol in rendered
            assert glyph.meaning in rendered
        keys = rendered.splitlines()
        assert any(line.startswith("?") and line.endswith("Legend") for line in keys)
        assert any(line.startswith("q") and line.endswith("Quit") for line in keys)
        # A colour-bearing Glyph shows the swatch the cell would.
        running = session_list.STATE_GLYPHS["running"]
        sessions = screen.query_one("#legend-section-0", Static)
        content = sessions.render()
        assert isinstance(content, Content)
        span_style = content.spans[0].style
        assert isinstance(span_style, Style)
        swatch = span_style.foreground
        assert swatch is not None
        assert swatch.hex6.casefold() == running.style(dark=app.current_theme.dark)

        # A second ? is absorbed by the Legend rather than stacking another.
        await pilot.press("question_mark")
        await wait_until(lambda: not isinstance(app.screen, LegendScreen))
        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, LegendScreen))
        assert app.query_one("#queue", DataTable).has_focus


@pytest.mark.asyncio
async def test_dashboard_bindings_decline_under_the_issue_view() -> None:
    app = DashpotApp(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"), issue("test/repo#2", "Second")
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        sort = app.issue_view.sort
        states = app.issue_view.query.states
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        for key in ("c", "slash", "o", "s", "shift+s", "enter"):
            await pilot.press(key)
            await pilot.pause()

        # The hidden dashboard is untouched: no editor stacked over the Issue
        # view, its search not focused, its sort and state filter unchanged.
        assert isinstance(app.screen, IssueScreen)
        assert not app.main_screen.query_one("#issue-search", Input).has_focus
        assert app.issue_view.sort == sort
        assert app.issue_view.query.states == states
        assert len(app.screen_stack) == 2


@pytest.mark.asyncio
async def test_a_row_the_store_cannot_detail_selects_nothing() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert app.sub_title != DEFAULT_SUB_TITLE

        app.show_row(row_key("issue", "I_gone"))

        # Nothing is selected, so the Open Issue binding opens nothing rather
        # than the previously selected Issue.
        assert app.selected_row_key is None
        assert app.sub_title != DEFAULT_SUB_TITLE
        app.action_open_issue()
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)


@pytest.mark.asyncio
async def test_legend_is_reachable_from_the_issue_view() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        await pilot.press("escape")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
