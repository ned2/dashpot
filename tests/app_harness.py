"""The Dashboard app harness the split ``test_app`` modules share.

A ``DashpotApp`` under ``run_test`` needs the same scaffolding everywhere: an
Issue built on the conformance fixture, a one-Project Workspace Snapshot with
copy-with-update conveniences, a scriptable collector, and small readers over
the dashboard's panes.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import Event, Lock

import factories
from dashpot.app import DashpotApp
from dashpot.detail_fields import detail_items_text
from dashpot.issue_list import IssueListRow
from dashpot.issue_profile import IssueProfile, conform_issue
from dashpot.issue_view import issue_metadata_items, selection_title
from dashpot.list_pane import ListPane, ListRow
from dashpot.model import AgentRun, Diagnostic, SourceStatus, WorkspaceSnapshot
from helpers import snapshot_of

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


def workspace_snapshot(
    *issues: IssueProfile,
    runs: list[AgentRun] | None = None,
    status: SourceStatus = "fresh",
    diagnostics: list[Diagnostic] | None = None,
    elapsed_ms: int = 12,
) -> WorkspaceSnapshot:
    project = factories.project(
        "project:test-repo",
        *issues,
        label="Test Repository",
        repository_id="repository:test-repo",
        targets=[factories.target("/repo")],
        anchors=("/repo",),
        status=status,
        diagnostics=diagnostics or [],
        elapsed_ms=elapsed_ms,
        now=NOW,
    )
    return factories.workspace(
        project,
        runs=runs,
        issue_runs={item.id: [] for item in issues},
        elapsed_ms=elapsed_ms,
        now=NOW,
    )


def with_first_project(
    observed: WorkspaceSnapshot, **updates: object
) -> WorkspaceSnapshot:
    """Copy the snapshot with its first Project observation updated."""
    project = observed.projects[0].model_copy(update=updates)
    return observed.model_copy(update={"projects": (project, *observed.projects[1:])})


def with_first_project_snapshot(
    observed: WorkspaceSnapshot, **updates: object
) -> WorkspaceSnapshot:
    """Copy the snapshot with its first Project Snapshot updated."""
    project = observed.projects[0]
    return with_first_project(
        observed, snapshot=snapshot_of(project).model_copy(update=updates)
    )


def with_first_target(
    observed: WorkspaceSnapshot, **updates: object
) -> WorkspaceSnapshot:
    """Copy the snapshot with its first Observation Target updated."""
    project_snapshot = snapshot_of(observed.projects[0])
    target = project_snapshot.observation_targets[0].model_copy(update=updates)
    return with_first_project_snapshot(
        observed,
        observation_targets=(target, *project_snapshot.observation_targets[1:]),
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


def assert_panes_stack_above_full_width_queue(app: DashpotApp) -> None:
    """The list panes stack in reading order above the full-width Issue table."""
    body = app.query_one("#body")
    list_row = app.query_one("#list-row")
    sessions = app.query_one("#sessions-pane")
    branches = app.query_one("#branches-pane")
    worktrees = app.query_one("#worktrees-pane")
    queue_pane = app.query_one("#queue-pane")

    assert sessions.region.y == list_row.region.y
    assert sessions.region.bottom <= worktrees.region.y
    assert worktrees.region.bottom <= branches.region.y
    assert branches.region.bottom <= list_row.region.bottom <= queue_pane.region.y
    for pane in (sessions, worktrees, branches, queue_pane):
        assert pane.region.x == body.region.x
        assert pane.region.width == body.region.width
    assert queue_pane.region.height >= 6
    assert not app.query("#detail-row")
    assert not app.query("#project-pane")
    assert not app.query("#selection-pane")


def selected_title(app: DashpotApp) -> str:
    """The compact label of the Issue the table cursor is on."""
    assert app.dashboard.selected_row_key is not None
    return selection_title(app.dashboard.rows_by_key[app.dashboard.selected_row_key])


def pane_title(app: DashpotApp, selector: str) -> str:
    title = app.query_one(selector)._border_title
    assert title is not None
    return title.plain


def pane_subtitle(app: DashpotApp, selector: str) -> str:
    subtitle = app.query_one(selector)._border_subtitle
    assert subtitle is not None
    return subtitle.plain


def issue_metadata_text(context: IssueListRow) -> str:
    return detail_items_text(issue_metadata_items(context))


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


def pane_chrome(pane: ListPane) -> int:
    """The frame, header and any horizontal scrollbar around a pane's records."""
    return 2 + 1 + (1 if pane.table.show_horizontal_scrollbar else 0)


def footer_keys(app: DashpotApp) -> set[str]:
    return {binding.key for _, binding, *_ in app.screen.active_bindings.values()}
