from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock

import pytest
from textual.widgets import DataTable, Static

from dashpot.app import (
    DashpotApp,
    project_label,
    selection_detail_text,
)
from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.issue_table import (
    COLUMN_KEYS,
    IssueTableViewState,
    SortTerm,
    build_rows,
)
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    SourceStatus,
    WorkspaceSnapshot,
)


NOW = "2026-08-25T01:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def issue(reference: str, title: str, priority: str = "P1") -> dict:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["id"] = f"I_{reference}"
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


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.snapshot is snapshot)
        table = app.query_one("#queue", DataTable)
        project_detail = str(app.query_one("#project-detail", Static).render())
        selection_detail = str(app.query_one("#selection-detail", Static).render())

        assert table.row_count == 2
        assert COLUMN_KEYS == (
            "status",
            "project",
            "priority",
            "assignees",
            "sessions",
            "title",
        )
        assert [str(column.label) for column in table.columns.values()] == [
            "S ↕",
            "PROJECT ↑",
            "PRI ↑",
            "ASSIGNEES ↕",
            "SESSIONS ↕",
            "TITLE ↑",
        ]
        assert app.selected_row_key == row_key("issue", "I_test/repo#1")
        assert "Status: fresh" in project_detail
        assert "Anchor: /repo" in project_detail
        assert "Observation Targets: 1" in project_detail
        assert "main@abcdef12 clean" in project_detail
        assert "0 agents · /repo" in project_detail
        assert "test/repo" not in project_detail
        assert "Refresh:" not in project_detail
        assert "First" in selection_detail
        assert "Status:" not in selection_detail
        assert "Assignees: unassigned" in selection_detail
        assert "Agent sessions:" in selection_detail
        assert "Declared" not in selection_detail
        assert "blocked" not in selection_detail.lower()
        assert str(app.query_one("#selection-title", Static).render()) == "ISSUE"
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
        await wait_until(lambda: app.snapshot is snapshot)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert app.selected_row_key == row_key("issue", closed_issue["id"])
        assert "Closed" in str(
            app.query_one("#selection-detail", Static).render()
        )


@pytest.mark.asyncio
async def test_header_selection_toggles_sort_and_preserves_selected_issue() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "Zebra"),
        issue("test/repo#2", "Alpha"),
    )
    app = DashpotApp(
        SequenceCollector(snapshot), refresh_seconds=0, initial_snapshot=snapshot
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

        assert table.get_row_at(0)[-1] == "Zebra"
        assert app.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert str(table.columns[title_key].label) == "TITLE ↓"


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
    app = DashpotApp(SequenceCollector(second), refresh_seconds=0, initial_snapshot=first)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.selected_row_key == selected_key)

        await app.run_action("refresh")
        await wait_until(lambda: app.snapshot is second)

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
        initial_snapshot=snapshot,
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.ui_error is not None)

        assert app.snapshot is snapshot
        assert app.query_one("#queue", DataTable).row_count == 1
        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.query_one("#diagnostics", Static).has_class("-has-messages")


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
        await wait_until(lambda: app.snapshot is snapshot)

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
        await wait_until(lambda: app.snapshot is snapshot)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert "prunable" in str(app.query_one("#diagnostics", Static).render())
        assert "unavailable" in str(
            app.query_one("#project-detail", Static).render()
        )
        assert "unknown@abcdef12" in str(
            app.query_one("#project-detail", Static).render()
        )


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
        await wait_until(lambda: app.snapshot is snapshot)

        assert app.selected_row_key == row_key("run", "codex-session:42")
        assert "Unmatched codex run" in str(
            app.query_one("#selection-detail", Static).render()
        )
        detail = str(app.query_one("#selection-detail", Static).render())
        assert "owner/repository#404" in detail
        assert "I_raw_identity" not in detail
        assert str(app.query_one("#selection-title", Static).render()) == "AGENT RUN"


@pytest.mark.asyncio
async def test_layout_switches_at_horizontal_breakpoint() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(60, 20)) as pilot:
        await wait_until(lambda: app.snapshot is snapshot)
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


def test_selecting_a_sort_column_replaces_the_default_then_toggles_direction() -> None:
    view = IssueTableViewState()

    ascending = view.toggle_sort("title")
    descending = ascending.toggle_sort("title")

    assert ascending.sort == (SortTerm("title"),)
    assert descending.sort == (SortTerm("title", descending=True),)


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
    assert len(cells[selected_key]) == len(COLUMN_KEYS) == 6
    assert cells[selected_key][3] == "ned2"
    assert cells[selected_key][4] == "Ⅱ1"
    detail = selection_detail_text(contexts[selected_key])
    assert "Assignees: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


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
    assert cells[row_key("issue", open_issue["id"])][-1] == "Open"


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
    assert cells[project_key][-1] == "no open Issues"


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
    second.projects[0].snapshot.issues[0]["reference"] = "new/repository#70"
    selected_key = row_key("issue", transferred["id"])
    app = DashpotApp(
        SequenceCollector(second), refresh_seconds=0, initial_snapshot=first
    )

    async with app.run_test(size=(80, 24)):
        assert app.selected_row_key == selected_key

        await app.run_action("refresh")
        await wait_until(lambda: app.snapshot is second)

        assert app.selected_row_key == selected_key
        assert "Transfer me" in str(
            app.query_one("#selection-detail", Static).render()
        )


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
    app = DashpotApp(collector, refresh_seconds=0, initial_snapshot=initial)

    try:
        async with app.run_test(size=(80, 24)):
            app.request_refresh("manual")
            await wait_until(collector.started.is_set)
            app.request_refresh("manual")
            await wait_until(lambda: app.snapshot is new)

            collector.release.set()
            await asyncio.sleep(0.1)
            assert app.snapshot is new
            assert "New result" in str(
                app.query_one("#selection-detail", Static).render()
            )
    finally:
        collector.release.set()
