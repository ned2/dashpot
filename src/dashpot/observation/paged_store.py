"""Join Query Pages and Resolved Issues without populating export inventories.

A page's Issues join the Projects the store holds: a Query Source answers
for the one Project it was built from, and the store never forgets a
Project, so an Issue on an accepted page always finds its Project once
that Project has been published.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import override

from ..core.issue_profile import IssueProfile
from ..core.model import Diagnostic, ProjectObservation, WorkspaceSnapshot
from ..core.timestamps import observed_instant
from ..queries.source_queries import (
    AuxiliaryObservation,
    ProjectTotals,
    QueryPage,
    ResolvedIssue,
    ResourceKind,
)
from .issue_list import (
    IssueListRow,
    IssueListSummary,
    row_key,
    worker_states,
)
from .list_result import ListResult
from .observation_store import ObservedDiagnostic, WorkspaceObservationStore
from .session_list import SessionListRow, query_indexed_session_list


def _overrules(outcome: ResolvedIssue | None, page: QueryPage) -> bool:
    """Tell whether an identity outcome is newer evidence than the page's.

    Each is compared by when it last observed its records: a stale page
    still shows what it observed then.
    """
    return (
        outcome is not None
        and outcome.outcome != "unavailable"
        and observed_instant(outcome.last_good_at) > observed_instant(page.last_good_at)
    )


class PagedObservationStore(WorkspaceObservationStore):
    """Hold the accepted pages, totals and identities beside the observations."""

    def __init__(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        # The base construction commits a seeded snapshot, and a commit joins
        # the shown page's Issues, so the page state must exist before it.
        self.pages: dict[ResourceKind, QueryPage] = {}
        self.totals: dict[ResourceKind, ProjectTotals] = {}
        self.resolved: dict[str, ResolvedIssue] = {}
        # What the Query Sources last reported about themselves rather than
        # about one observation, such as a rate limit running low.
        self.source_diagnostics: tuple[Diagnostic, ...] = ()
        super().__init__(snapshot)

    def accept_page(self, kind: ResourceKind, page: QueryPage | None) -> None:
        """Show ``page`` as the kind's current page, or none."""
        if page is None:
            self.pages.pop(kind, None)
        else:
            self.pages[kind] = page

    def accept_totals(self, totals: ProjectTotals) -> None:
        """Accept a kind's Project Totals."""
        self.totals[totals.kind] = totals

    def accept_identities(self, outcomes: Sequence[ResolvedIssue]) -> None:
        """Hold the outcomes of the identities last requested, and only those.

        The dashboard requests the bound Issues, the selected one and its
        relationships; an outcome for an identity no longer among them is
        forgotten, so it neither hides a row nor stays in the Diagnostics.
        """
        self.resolved = {outcome.issue_id: outcome for outcome in outcomes}

    def accept_source_diagnostics(self, diagnostics: Sequence[Diagnostic]) -> None:
        """Replace what the Query Sources report about themselves."""
        self.source_diagnostics = tuple(diagnostics)

    def row_for(self, issue_id: str) -> IssueListRow | None:
        """Project one Issue by identity, from the newer of its page and its outcome.

        The accepted page lists the Issue as the page observed it; its
        resolved outcome overrules that only when observed after the page,
        and an unavailable outcome observed nothing to overrule it with.
        """
        outcome = self.resolved.get(issue_id)
        page = self.pages.get("issues")
        listed = (
            next((issue for issue in page.issues if issue.id == issue_id), None)
            if page
            else None
        )
        issue: IssueProfile | None
        auxiliary: AuxiliaryObservation | None
        if page is not None and listed is not None and not _overrules(outcome, page):
            issue, auxiliary = listed, page.auxiliary.get(issue_id)
        elif outcome is not None:
            issue, auxiliary = outcome.issue, outcome.auxiliary
        else:
            return None
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
            project,
            issue,
            runs,
            tuple(run.activity for run in runs)
            + worker_states(self._state.agent_runs.values(), issue_id),
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

    def query_issues(self) -> ListResult[IssueListRow, IssueListSummary]:
        """Project the accepted Issue page's rows, in the source's order."""
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
        return ListResult(
            rows=tuple(rows),
            summary=IssueListSummary(
                matched_issue_count=page.matched_count or 0 if page else 0,
                observed_issue_count=len(rows),
                open_issue_count=totals.open_count or 0 if totals else 0,
                closed_issue_count=totals.closed_count or 0 if totals else 0,
            ),
        )

    @override
    def query_sessions(self) -> ListResult[SessionListRow]:
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
        )

    def detail_for(self, row: IssueListRow) -> IssueListRow | None:
        """Resolve a listed row's Issue against what the store holds now."""
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
        diagnostics.extend(
            ObservedDiagnostic(diagnostic) for diagnostic in self.source_diagnostics
        )
        for page in self.pages.values():
            diagnostics.extend(
                ObservedDiagnostic(d)
                for auxiliary in page.auxiliary.values()
                for d in auxiliary.diagnostics
            )
        for run in self._state.agent_runs.values():
            outcome = self.resolved.get(run.issue_id or "")
            # Outside the Repository, a relationship is ordinary, but a bound
            # Issue has left the Project its Issue work belongs to.
            if outcome and outcome.outcome == "outside-repository":
                diagnostics.append(
                    ObservedDiagnostic(
                        Diagnostic(
                            source=run.id,
                            severity="warning",
                            code="agent-issue-outside-repository",
                            message=(
                                f"The bound Issue {outcome.reference or run.issue_id}"
                                " is outside the configured Repository"
                            ),
                        )
                    )
                )
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
        # A Diagnostic several observations report alike, such as a page and
        # the totals its request counted, is one line however many report it.
        return (*super().diagnostics(), *dict.fromkeys(diagnostics))
