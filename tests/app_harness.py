"""The Dashboard app harness the split ``test_app`` modules share.

A ``DashpotApp`` under ``run_test`` needs the same scaffolding everywhere: an
Issue built on the conformance fixture, a one-Project Workspace Snapshot with
copy-with-update conveniences, a scriptable collector, a Query Source serving
that snapshot to the shipped paged app, and small readers over the dashboard's
panes.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from pathlib import Path
from threading import Event, Lock

import factories
from dashpot.app import DashpotApp
from dashpot.cleanup import CleanupAdapter
from dashpot.detail_fields import detail_items_text
from dashpot.fetch import RemoteFetcher
from dashpot.issue_list import IssueListRow, is_issue_sort_column
from dashpot.issue_profile import IssueProfile, conform_issue
from dashpot.issue_view import issue_metadata_items, selection_title
from dashpot.list_pane import ListPane, ListRow
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ProjectObservation,
    PullRequest,
    SourceStatus,
    WorkspaceSnapshot,
)
from dashpot.paged_app import QUERY_SOURCE_KEYS, PagedDashpotApp
from dashpot.source_queries import (
    AuxiliaryObservation,
    Continuation,
    ProjectTotals,
    QueryPage,
    QueryRequest,
    ResolvedIssue,
    ResourceKind,
    SourceContext,
    SourceEnumeration,
    context_fingerprint,
    decode_continuation,
    encode_continuation,
    verify_continuation,
)
from dashpot.worktree_launcher import LauncherConfiguration
from helpers import snapshot_of

NOW = "2026-08-25T01:00:00Z"

# The one Project every harness snapshot observes; its Issues carry the same
# identity so a Query Page built from them belongs to it.
PROJECT_ID = "project:test-repo"


ROOT = Path(__file__).resolve().parents[1]


ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def issue(
    reference: str, title: str, priority: str = "P1", **overrides: object
) -> IssueProfile:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["id"] = f"I_{reference}"
    value["projectId"] = PROJECT_ID
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
    pull_requests: tuple[PullRequest, ...] = (),
    status: SourceStatus = "fresh",
    diagnostics: list[Diagnostic] | None = None,
    elapsed_ms: int = 12,
) -> WorkspaceSnapshot:
    project = factories.project(
        PROJECT_ID,
        *issues,
        label="Test Repository",
        repository_id="repository:test-repo",
        targets=[factories.target("/repo")],
        anchors=("/repo",),
        status=status,
        pull_requests=pull_requests,
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


class SnapshotQuerySource:
    """Serve Query Pages, Project Totals and Resolved Issues from one snapshot.

    The shipped app never enumerates a Project; it asks a Query Source for
    pages. This source answers from the first Project of a Workspace Snapshot
    so a test can drive the paged app with the snapshot it hands the collector.
    """

    search_prompt = "Search Issues (Enter)"

    def __init__(self, snapshot: WorkspaceSnapshot) -> None:
        self.project: ProjectObservation = snapshot.projects[0]
        self.context = SourceContext(
            project_id=self.project.project_id,
            repository_id=self.project.repository_id,
            source="github",
            location=self.project.primary_anchor,
        )

    def supports_sort(self, request: QueryRequest, column: str) -> bool:
        return is_issue_sort_column(column)

    def _freshness(self, kind: ResourceKind) -> tuple[SourceStatus, str | None]:
        """The status and last good time the snapshot observed one kind at."""
        snapshot = self.project.snapshot
        if snapshot is None:
            return "unavailable", None
        if kind == "issues":
            return snapshot.issue_source_status, snapshot.issue_source_last_good_at
        return snapshot.pull_request_status, snapshot.pull_request_last_good_at

    def _issues(self) -> Sequence[IssueProfile]:
        return self.project.snapshot.issues if self.project.snapshot else ()

    def _pull_requests(self) -> Sequence[PullRequest]:
        return self.project.snapshot.pull_requests if self.project.snapshot else ()

    def _auxiliary(self, issue_id: str) -> AuxiliaryObservation:
        snapshot = snapshot_of(self.project)
        return AuxiliaryObservation(
            status="fresh",
            attempted_at=NOW,
            last_good_at=NOW,
            activity=snapshot.issue_activity.get(issue_id),
            label_colors=snapshot.label_colors,
        )

    def query_page(self, request: QueryRequest) -> QueryPage:
        status, last_good_at = self._freshness(request.kind)
        if status == "unavailable":
            return QueryPage(
                context=self.context,
                request=request,
                effective_ordering=request.ordering,
                status="unavailable",
                attempted_at=NOW,
                last_good_at=None,
                returned_count=0,
                matched_count=None,
                next_cursor=None,
                continuation="unavailable",
                result_limit=None,
            )
        token = decode_continuation(request.cursor) if request.cursor else None
        verify_continuation(token, self.context, request)
        offset = token.offset if token else 0
        window = slice(offset, offset + request.page_size)
        issues: Sequence[IssueProfile] = ()
        pull_requests: Sequence[PullRequest] = ()
        if request.kind == "issues":
            found_issues = [
                issue
                for issue in self._issues()
                if request.state == "all" or issue.state == request.state
            ]
            matched, issues = len(found_issues), found_issues[window]
        else:
            found_pull_requests = [
                pr
                for pr in self._pull_requests()
                if request.state == "all" or pr.state == request.state
            ]
            matched, pull_requests = (
                len(found_pull_requests),
                found_pull_requests[window],
            )
        end = offset + len(issues) + len(pull_requests)
        next_cursor = (
            encode_continuation(
                Continuation(
                    fingerprint=context_fingerprint(self.context, request), offset=end
                )
            )
            if end < matched
            else None
        )
        return QueryPage(
            context=self.context,
            request=request,
            effective_ordering=request.ordering,
            status=status,
            attempted_at=NOW,
            last_good_at=last_good_at,
            issues=issues,
            pull_requests=pull_requests,
            auxiliary={issue.id: self._auxiliary(issue.id) for issue in issues},
            returned_count=len(issues) + len(pull_requests),
            matched_count=matched,
            next_cursor=next_cursor,
            continuation="more" if next_cursor else "end",
            result_limit=None,
        )

    def totals(self, kind: ResourceKind) -> ProjectTotals:
        status, last_good_at = self._freshness(kind)
        if status == "unavailable":
            return ProjectTotals(
                context=self.context,
                kind=kind,
                open_count=None,
                closed_count=None,
                status="unavailable",
                attempted_at=NOW,
                last_good_at=None,
            )
        states = [
            record.state
            for record in (
                self._issues() if kind == "issues" else self._pull_requests()
            )
        ]
        opened = states.count("open")
        return ProjectTotals(
            context=self.context,
            kind=kind,
            open_count=opened,
            closed_count=len(states) - opened,
            status=status,
            attempted_at=NOW,
            last_good_at=last_good_at,
        )

    def resolve_identities(
        self, identities: Sequence[str]
    ) -> tuple[ResolvedIssue, ...]:
        status, last_good_at = self._freshness("issues")
        if status == "unavailable":
            return tuple(
                ResolvedIssue(
                    context=self.context,
                    issue_id=identity,
                    outcome="unavailable",
                    status="unavailable",
                    attempted_at=NOW,
                    last_good_at=None,
                )
                for identity in dict.fromkeys(identities)
            )
        issues = {issue.id: issue for issue in self._issues()}
        return tuple(
            ResolvedIssue(
                context=self.context,
                issue_id=identity,
                outcome="resolved" if identity in issues else "not-resolved",
                issue=issues.get(identity),
                auxiliary=self._auxiliary(identity) if identity in issues else None,
                status=status,
                attempted_at=NOW,
                last_good_at=last_good_at,
            )
            for identity in dict.fromkeys(identities)
        )

    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration:
        status, last_good_at = self._freshness(kind)
        return SourceEnumeration(
            context=self.context,
            kind=kind,
            issues=self._issues() if kind == "issues" else (),
            pull_requests=self._pull_requests() if kind == "pull-requests" else (),
            status=status,
            attempted_at=NOW,
            last_good_at=last_good_at,
        )


def dashboard_app(
    collector: SequenceCollector,
    *,
    snapshot: WorkspaceSnapshot | None = None,
    refresh_seconds: float = 0,
    fetcher: RemoteFetcher | None = None,
    cleaner: CleanupAdapter | None = None,
    launcher_configuration: LauncherConfiguration | None = None,
) -> PagedDashpotApp:
    """The shipped app over a scripted collector, its queries served from a snapshot.

    By default the Query Sources answer from the first snapshot the collector
    will observe; pass ``snapshot`` when the queries should see another.
    """
    if snapshot is None:
        snapshot = next(
            result
            for result in collector.results
            if isinstance(result, WorkspaceSnapshot)
        )
    return PagedDashpotApp(
        collector,
        sources={key: SnapshotQuerySource(snapshot) for key in QUERY_SOURCE_KEYS},
        refresh_seconds=refresh_seconds,
        fetcher=fetcher,
        cleaner=cleaner,
        launcher_configuration=launcher_configuration,
    )


def first_load_landed(app: PagedDashpotApp) -> bool:
    """Whether the first observation, both first pages and both totals rendered.

    The base app rendered everything from its first checkpoint; the shipped
    app also waits on its page and totals queries, so a test reads the
    dashboard only once all of them are in.
    """
    return (
        app.store.revision >= 1
        and set(app.paged_store.pages) == {"issues", "pull-requests"}
        and set(app.paged_store.totals) == {"issues", "pull-requests"}
    )


def assert_panes_stack_above_full_width_queue(app: DashpotApp) -> None:
    """The list panes stack in reading order above the full-width Issue table."""
    body = app.query_one("#body")
    list_row = app.query_one("#list-row")
    sessions = app.query_one("#sessions-pane")
    branches = app.query_one("#branches-pane")
    pull_requests = app.query_one("#pull-requests-pane")
    worktrees = app.query_one("#worktrees-pane")
    queue_pane = app.query_one("#queue-pane")

    assert sessions.region.y == list_row.region.y
    assert sessions.region.bottom <= worktrees.region.y
    assert worktrees.region.bottom <= branches.region.y
    assert branches.region.bottom <= pull_requests.region.y
    assert pull_requests.region.bottom <= list_row.region.bottom <= queue_pane.region.y
    for pane in (sessions, worktrees, branches, pull_requests, queue_pane):
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
