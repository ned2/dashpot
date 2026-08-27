from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock

import pytest
from textual.content import Content
from textual.widgets import DataTable, Input, Select, Static

from dashpot.app import (
    DashpotApp,
    issue_pane_state_class,
    project_label,
    selection_detail_text,
)
from dashpot.column_editor import IssueColumnEditor
from dashpot.detail_fields import DetailFields
from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.issue_table import (
    COLUMNS_BY_KEY,
    COLUMN_KEYS,
    DEFAULT_COLUMNS,
    IssueTableCell,
    IssueTableViewState,
    SortTerm,
    build_rows,
    searchable_columns,
)
from dashpot.local_markdown_issues import parse_local_markdown_issue
from dashpot.model import (
    AgentRun,
    Diagnostic,
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


def issue(reference: str, title: str, priority: str = "P1") -> dict:
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


def workspace_snapshot(
    *issues: dict,
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

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


async def wait_until(
    predicate: Callable[[], bool], timeout: float = 1.5
) -> None:
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
            "status",
            "number",
            "title",
            "project",
            "priority",
            "assignees",
            "sessions",
        )
        assert DEFAULT_COLUMNS == (
            "status",
            "number",
            "title",
            "priority",
            "assignees",
            "sessions",
        )
        assert [str(column.label) for column in table.columns.values()] == [
            "S ↕",
            "ID ↕",
            "TITLE ↑",
            "PRI ↑",
            "ASSIGNEES ↕",
            "SESSIONS ↕",
        ]
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert "Status: fresh" in project_detail
        assert "Anchor: /repo" in project_detail
        assert "Targets: 1" in project_detail
        assert "main@abcdef12 clean" in project_detail
        assert "0 agents · /repo" in project_detail
        assert "test/repo" not in project_detail
        assert "Refresh:" not in project_detail
        assert "Reference:" not in selection_detail
        assert selection_detail.startswith("Location: ")
        assert "Status:" not in selection_detail
        assert "Assignees: unassigned" in selection_detail
        assert "Agent sessions:" in selection_detail
        assert "Declared" not in selection_detail
        assert "blocked" not in selection_detail.lower()
        assert [row.item.label for row in project_fields] == [
            "Status",
            "Workspaces",
            "Anchor",
            "Targets",
            "Agents",
        ]
        assert len({row.field_value.region.x for row in project_fields}) == 1
        assert len({row.field_value.region.x for row in issue_fields}) == 1
        assert all(row.field_name.styles.text_align == "left" for row in issue_fields)
        assert app.ALLOW_SELECT
        assert all(row.field_value.allow_select for row in project_fields + issue_fields)
        assert not table.allow_select

        location = issue_fields[0].field_value
        assert await pilot.mouse_down(location, offset=(0, 0))
        assert await pilot.mouse_up(location, offset=(5, 0))
        await pilot.pause()
        assert app.clipboard == issue_fields[0].item.value[:6]

        assert pane_title(app, "#project-pane") == "PROJECT STATUS"
        assert pane_title(app, "#selection-pane") == "#1: First"
        assert app.query_one("#selection-pane").has_class("-issue-open")
        app.query_one("#selection-pane").border_title = Content(
            "#1: [bold]literal[/bold]"
        )
        assert pane_title(app, "#selection-pane") == "#1: [bold]literal[/bold]"
        diagnostics = app.query_one("#diagnostics", Static)
        assert_context_above_full_width_queue(app)
        assert app.query_one("#queue-pane").region.bottom <= diagnostics.region.y
        assert not app.query_one("#diagnostics", Static).has_class("-has-messages")
    assert asyncio.get_running_loop()._default_executor is None


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
        selected_context = app.rows_by_key[app.selected_row_key]

        assert issue_pane_state_class(selected_context) == state_class
        assert pane.has_class(state_class)
        assert pane.styles.border_top[1].hex.casefold() == dark_color

        app.theme = "textual-light"
        await pilot.pause()

        assert pane.styles.border_top[1].hex.casefold() == light_color


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

        for _ in range(2):
            table.post_message(
                DataTable.HeaderSelected(
                    table,
                    title_key,
                    table.get_column_index(title_key),
                    table.columns[title_key].label,
                )
            )
            await pilot.pause()

        assert table.get_row_at(0)[table.get_column_index(title_key)] == "Zebra"
        assert app.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert str(table.columns[title_key].label) == "TITLE ↓"


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
async def test_visible_filters_update_rows_and_observation_count() -> None:
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

        assert str(count.render()) == "2 of 3 Issues"
        search.value = "zebra"
        await wait_until(lambda: str(count.render()) == "1 of 3 Issues")
        assert app.query_one("#queue", DataTable).row_count == 1

        state.value = "closed"
        await wait_until(
            lambda: app.selected_row_key == row_key("issue", closed_issue["id"])
        )
        assert str(count.render()) == "1 of 3 Issues"


@pytest.mark.asyncio
async def test_column_editor_applies_visibility_and_order_without_losing_selection() -> None:
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
        selections.deselect("status")
        selections.highlighted = editor.column_order.index("sessions")
        assert await pilot.click("#column-up")
        await pilot.pause()
        assert await pilot.click("#column-apply")
        await pilot.pause()

        assert app.issue_view.columns == (
            "number",
            "title",
            "priority",
            "sessions",
            "assignees",
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
        assert "Status: unavailable" in detail_plain(app, "#project-detail")
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
    project.snapshot.issue_source_status = "unavailable"
    project.snapshot.issue_source_attempted_at = "2026-08-27T04:00:00Z"
    project.snapshot.issue_source_last_good_at = None
    project.snapshot.issues = []
    project.snapshot.diagnostics = [
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
        assert "Status: stale" in detail_plain(app, "#project-detail")
        assert "GitHub unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert "Ⅱ1" in app.query_one("#queue", DataTable).get_row_at(0)


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
    target = snapshot.projects[0].snapshot.observation_targets[0]
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
        assert "unavailable" in detail_plain(app, "#project-detail")
        assert "unknown@abcdef12" in detail_plain(app, "#project-detail")


@pytest.mark.asyncio
async def test_unmatched_agent_is_visible_as_its_own_row() -> None:
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="main",
        issue_id="I_raw_identity",
        issue_reference_hint="owner/repository#404",
    )
    snapshot = workspace_snapshot(runs=[run])
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        assert app.selected_row_key == row_key("run", "codex-session:42")
        assert "Unmatched codex run" in detail_plain(app, "#selection-detail")
        detail = detail_plain(app, "#selection-detail")
        assert "owner/repository#404" in detail
        assert "I_raw_identity" not in detail
        assert pane_title(app, "#selection-pane") == "AGENT RUN"
        assert not any(
            app.query_one("#selection-pane").has_class(class_name)
            for class_name in (
                "-issue-open",
                "-issue-completed",
                "-issue-not-planned",
                "-issue-duplicate",
            )
        )


@pytest.mark.asyncio
async def test_layout_switches_at_horizontal_breakpoint() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(60, 20)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        assert app.screen.has_class("-compact")

        await pilot.resize_terminal(120, 32)
        await pilot.pause()
        assert app.screen.has_class("-wide")
        assert_context_above_full_width_queue(app)


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


def test_issue_id_column_uses_the_project_local_number() -> None:
    selected_issue = issue("test/repo#17", "Reference test")

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("number",),
    )

    assert cells[row_key("issue", selected_issue["id"])] == (
        "#17",
    )


def test_local_markdown_number_is_the_table_id() -> None:
    document = (
        ROOT / "tests" / "fixtures" / "local-markdown" / "ISSUES.md"
    ).read_text()
    document = document.replace(
        '"id": "I_kwDOUEerrs8AAAABOSTptQ"', '"id": "I_local_17"'
    ).replace(
        '"number": 9', '"number": 17'
    ).replace(
        '"reference": "ned2/dashpot#9"', '"reference": "local-17"'
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

    assert cells[row_key("issue", "I_local_17")] == ("#17",)


def test_selecting_a_sort_column_replaces_the_default_then_toggles_direction() -> None:
    view = IssueTableViewState()

    ascending = view.toggle_sort("title")
    descending = ascending.toggle_sort("title")

    assert ascending.sort == (SortTerm("title"),)
    assert descending.sort == (SortTerm("title", descending=True),)


def test_table_view_rejects_empty_or_duplicate_column_layouts() -> None:
    view = IssueTableViewState()

    with pytest.raises(ValueError, match="at least one"):
        view.with_columns(())
    with pytest.raises(ValueError, match="duplicates"):
        view.with_columns(("title", "title"))


def test_column_catalogue_owns_searchability_and_typed_sort_keys() -> None:
    assert searchable_columns() == frozenset(
        {"number", "project", "assignees", "title"}
    )
    sessions = [
        IssueTableCell("Ⅱ10", (10, 0, 10, 0)),
        IssueTableCell("Ⅱ2", (2, 0, 2, 0)),
    ]

    ordered = sorted(sessions, key=COLUMNS_BY_KEY["sessions"].sort_key)

    assert ordered == ["Ⅱ2", "Ⅱ10"]
    numbers = [IssueTableCell("#10", 10), IssueTableCell("#2", 2)]

    assert sorted(numbers, key=COLUMNS_BY_KEY["number"].sort_key) == [
        "#2",
        "#10",
    ]


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
    assert len(cells[selected_key]) == len(DEFAULT_COLUMNS) == 6
    assert cells[selected_key][1] == "#1"
    assert cells[selected_key][4] == "ned2"
    assert cells[selected_key][5] == "Ⅱ1"
    detail = selection_detail_text(contexts[selected_key])
    assert "Assignees: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


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
    second.snapshot.project_id = second.project_id
    second.snapshot.display_label = second.display_label
    second.snapshot.repository_id = second.repository_id
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
    assert cells[row_key("issue", open_issue["id"])][
        DEFAULT_COLUMNS.index("title")
    ] == "Open"


def test_project_with_only_closed_issues_has_no_open_issues_row() -> None:
    closed_issue = issue("test/repo#2", "Closed")
    closed_issue.update(
        {
            "state": "closed",
            "stateReason": "completed",
            "closedAt": "2026-08-27T01:00:00Z",
        }
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(closed_issue))
    )

    project_key = row_key("project", "project:test-repo")
    assert set(contexts) == set(cells) == {project_key}
    assert cells[project_key][DEFAULT_COLUMNS.index("title")] == (
        "no open Issues"
    )


def test_opaque_issue_identity_cannot_collide_with_unmatched_run_row() -> None:
    colliding_run_id = "codex-session:42"
    colliding_issue = issue(f"run:{colliding_run_id}", "Collision proof")
    colliding_issue["id"] = f"run:{colliding_run_id}"
    run = AgentRun(
        id=colliding_run_id,
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="main",
        issue_id=None,
        issue_reference_hint=None,
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(colliding_issue, runs=[run]))
    )

    assert set(contexts) == set(cells) == {
        row_key("issue", colliding_issue["id"]),
        row_key("run", colliding_run_id),
    }
    assert cells[row_key("run", colliding_run_id)][
        DEFAULT_COLUMNS.index("number")
    ] == "-"


def test_opaque_issue_identity_cannot_collide_with_project_placeholder() -> None:
    colliding_issue = issue("owner/repository#1", "Collision proof")
    colliding_issue["id"] = "project:empty"
    snapshot = workspace_snapshot(colliding_issue)
    empty = copy.deepcopy(snapshot.projects[0])
    empty.project_id = "empty"
    empty.display_label = "Empty"
    empty.snapshot.project_id = "empty"
    empty.snapshot.display_label = "Empty"
    empty.snapshot.issues = []
    snapshot.projects.append(empty)

    contexts, cells = build_rows(query_issue_list(snapshot))

    assert set(contexts) == set(cells) == {
        row_key("issue", colliding_issue["id"]),
        row_key("project", "empty"),
    }


@pytest.mark.asyncio
async def test_issue_transfer_preserves_selection_by_global_identity() -> None:
    transferred = issue("old/repository#7", "Transfer me")
    first = workspace_snapshot(transferred)
    second = copy.deepcopy(first)
    second.projects[0].project_id = "project:new-repository"
    second.projects[0].display_label = "New Repository"
    second.projects[0].snapshot.project_id = "project:new-repository"
    second.projects[0].snapshot.display_label = "New Repository"
    second.projects[0].snapshot.issues[0]["projectId"] = "project:new-repository"
    second.projects[0].snapshot.issues[0]["number"] = 70
    second.projects[0].snapshot.issues[0]["reference"] = "new/repository#70"
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
