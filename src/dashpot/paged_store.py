"""Join Query Pages and Resolved Issues without populating export inventories.

The accepted observations advance the inherited ``revision``; the accepted
source results — pages, totals, identities — advance ``source_revision``.
A write that changes what the store holds moves exactly one of them by one,
so their sum advances with every change, and it is what this store's read
models report as their ``revision``: the joined state each was built from.
A write that repeats what is held — a page published on every redraw, a
total or identity resolved again unchanged — moves neither.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import replace

from typing_extensions import override

from .issue_list import IssueListQuery, IssueListResult, IssueListRow, row_key
from .model import Diagnostic, ProjectObservation, WorkspaceSnapshot
from .observation_store import (
    IssueContext,
    ObservedDiagnostic,
    StoreChange,
    WorkspaceObservationStore,
    _StoreState,
)
from .session_list import SessionListResult, query_indexed_session_list
from .source_queries import (
    AuxiliaryObservation,
    ProjectTotals,
    QueryPage,
    ResolvedIssue,
    ResourceKind,
)


class PagedObservationStore(WorkspaceObservationStore):
    """Hold the accepted pages, totals and identities beside the observations."""

    def __init__(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        # The base construction commits a seeded snapshot, and a commit joins
        # the shown page's Issues, so the page state must exist before it.
        self.pages: dict[ResourceKind, QueryPage] = {}
        self.totals: dict[ResourceKind, ProjectTotals] = {}
        self.resolved: OrderedDict[str, ResolvedIssue] = OrderedDict()
        self.source_revision = 0
        # The Project each Issue on the shown page last joined with, by Issue
        # identity. A transferred Issue's refreshed page and its Project
        # observation land separately: while the page is in flight, an Issue
        # whose Project the observation no longer names keeps the Project it
        # last joined with, so its row and the selection on it survive until
        # the page lands; a landed page joins strictly.
        self.joined_projects: dict[str, ProjectObservation] = {}
        self.issues_in_flight = False
        super().__init__(snapshot)

    @property
    def result_revision(self) -> int:
        """Identify the joined state a read model was built from."""
        return self.revision + self.source_revision

    @override
    def _commit(self, candidate: _StoreState) -> StoreChange:
        change = super()._commit(candidate)
        if change.project_ids:
            self._join_projects()
        return change

    def accept_page(
        self, kind: ResourceKind, page: QueryPage | None, *, in_flight: bool = False
    ) -> None:
        """Show ``page`` as the kind's current page, or none, ``in_flight`` while queried again."""
        if page is None:
            changed = self.pages.pop(kind, None) is not None
        else:
            changed = self.pages.get(kind) != page
            self.pages[kind] = page
        # Only Issue rows join a Project; Pull Request rows read their page.
        if kind == "issues":
            self.issues_in_flight = in_flight
            self._join_projects()
        if changed:
            self.source_revision += 1

    def _join_projects(self) -> None:
        """Join each Issue on the shown page with its Project, or its last one in flight."""
        page = self.pages.get("issues")
        remembered = self.joined_projects
        self.joined_projects = {}
        for issue in page.issues if page else ():
            project = self.project(issue.project_id)
            if project is None and self.issues_in_flight:
                project = remembered.get(issue.id)
            if project is not None:
                self.joined_projects[issue.id] = project

    def accept_totals(self, totals: ProjectTotals) -> None:
        """Accept a kind's Project Totals."""
        if self.totals.get(totals.kind) != totals:
            self.totals[totals.kind] = totals
            self.source_revision += 1

    def accept_identities(self, outcomes: Sequence[ResolvedIssue]) -> None:
        """Retain bounded identity evidence independently of navigation history."""
        changed = False
        for outcome in outcomes:
            changed = changed or self.resolved.get(outcome.issue_id) != outcome
            self.resolved[outcome.issue_id] = outcome
            self.resolved.move_to_end(outcome.issue_id)
        while len(self.resolved) > 256:
            self.resolved.popitem(last=False)
        if changed:
            self.source_revision += 1

    def row_for(self, issue_id: str) -> IssueListRow | None:
        """Project one Issue by identity: resolved evidence first, then the accepted page."""
        outcome = self.resolved.get(issue_id)
        page = self.pages.get("issues")
        issue = outcome.issue if outcome else None
        auxiliary: AuxiliaryObservation | None = outcome.auxiliary if outcome else None
        if (
            issue is None
            and (outcome is None or outcome.outcome == "unavailable")
            and page
        ):
            issue = next((issue for issue in page.issues if issue.id == issue_id), None)
            auxiliary = page.auxiliary.get(issue_id)
        if issue is None:
            return None
        project = self.project(issue.project_id) or self.joined_projects.get(issue_id)
        if project is None:
            return None
        project = self._presentation_project(project, auxiliary)
        runs = tuple(
            run for run in self._state.agent_runs.values() if run.issue_id == issue_id
        )
        return IssueListRow(
            row_key("issue", issue.id),
            "issue",
            project,
            issue,
            runs,
            tuple(self._state.agent_runs.values()),
            tuple(run.state for run in runs),
            True,
            auxiliary,
            tuple(result.issue for result in self.resolved.values() if result.issue),
        )

    @staticmethod
    def _presentation_project(
        project: ProjectObservation, auxiliary: AuxiliaryObservation | None
    ) -> ProjectObservation:
        """Supply label colours to rendering without changing stored export state."""
        if project.snapshot is None or auxiliary is None:
            return project
        return project.model_copy(
            update={
                "snapshot": project.snapshot.model_copy(
                    update={"label_colors": auxiliary.label_colors or {}}
                )
            }
        )

    @override
    def query_issues(self, query: IssueListQuery = IssueListQuery()) -> IssueListResult:
        page = self.pages.get("issues")
        rows: list[IssueListRow] = []
        if page:
            for issue in page.issues:
                row = self.row_for(issue.id)
                if row:
                    # Page membership and ordering stay owned by the source.
                    rows.append(
                        replace(
                            row, issue=issue, auxiliary=page.auxiliary.get(issue.id)
                        )
                    )
        totals = self.totals.get("issues")
        return IssueListResult(
            tuple(rows),
            page.matched_count or 0 if page else 0,
            len(rows),
            self.result_revision,
            totals.open_count or 0 if totals else 0,
            totals.closed_count or 0 if totals else 0,
        )

    @override
    def query_sessions(self) -> SessionListResult:
        issues = {
            (result.context.project_id, result.issue_id): result.issue
            for result in self.resolved.values()
            if result.issue
        }
        return query_indexed_session_list(
            projects=self._state.projects,
            issues=issues,
            agent_runs=self._state.agent_runs,
            issue_runs=self._state.issue_runs,
            revision=self.result_revision,
        )

    @override
    def issue(
        self, issue_id: str, *, project_id: str | None = None
    ) -> IssueContext | None:
        row = self.row_for(issue_id)
        if row is None or (
            project_id is not None and row.project.project_id != project_id
        ):
            return None
        return IssueContext(row.project, row.issue, row.observed_runs)

    @override
    def detail_for(self, row: IssueListRow) -> IssueListRow | None:
        return self.row_for(row.issue.id)

    @override
    def diagnostics(self) -> tuple[ObservedDiagnostic, ...]:
        observations = [
            *self.pages.values(),
            *self.totals.values(),
            *self.resolved.values(),
        ]
        diagnostics = [
            ObservedDiagnostic(diagnostic)
            for value in observations
            for diagnostic in value.diagnostics
        ]
        for page in self.pages.values():
            diagnostics.extend(
                ObservedDiagnostic(d)
                for auxiliary in page.auxiliary.values()
                for d in auxiliary.diagnostics
            )
        for run in self._state.agent_runs.values():
            outcome = self.resolved.get(run.issue_id or "")
            if (
                outcome
                and outcome.issue
                and run.issue_reference_hint
                and outcome.issue.reference != run.issue_reference_hint
            ):
                diagnostics.append(
                    ObservedDiagnostic(
                        Diagnostic(
                            source=run.id,
                            severity="warning",
                            code="agent-issue-hint-stale",
                            message="The bound Issue's current Reference differs from its stored Issue Hint",
                        )
                    )
                )
        return (*super().diagnostics(), *diagnostics)
