"""Join Query Pages and Resolved Issues without populating export inventories."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import replace

from typing_extensions import override

from .issue_list import IssueListQuery, IssueListResult, IssueListRow, row_key
from .model import Diagnostic, ProjectObservation
from .observation_store import (
    IssueContext,
    ObservedDiagnostic,
    WorkspaceObservationStore,
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
    def __init__(self) -> None:
        super().__init__()
        self.pages: dict[ResourceKind, QueryPage] = {}
        self.totals: dict[ResourceKind, ProjectTotals] = {}
        self.resolved: OrderedDict[str, ResolvedIssue] = OrderedDict()

    def accept_identities(self, outcomes: Sequence[ResolvedIssue]) -> None:
        """Retain bounded identity evidence independently of navigation history."""
        for outcome in outcomes:
            self.resolved[outcome.issue_id] = outcome
            self.resolved.move_to_end(outcome.issue_id)
        while len(self.resolved) > 256:
            self.resolved.popitem(last=False)

    def _row(self, issue_id: str) -> IssueListRow | None:
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
        project = self.project(issue.project_id)
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
                row = self._row(issue.id)
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
            self.revision,
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
            revision=self.revision,
        )

    @override
    def issue(
        self, issue_id: str, *, project_id: str | None = None
    ) -> IssueContext | None:
        row = self._row(issue_id)
        if row is None or (
            project_id is not None and row.project.project_id != project_id
        ):
            return None
        return IssueContext(row.project, row.issue, row.observed_runs)

    @override
    def detail_for(self, row: IssueListRow) -> IssueListRow | None:
        return self._row(row.issue.id)

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
