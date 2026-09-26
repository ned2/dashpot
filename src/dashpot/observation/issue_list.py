"""The Issues pane read model: every visible Issue of the Project, once.

A row is one Issue joined to its Project, its bound Agent Runs and their
states. The Issue facts a row is searched and ordered by come from
``issues.search`` and ``issues.ordering``, which a source that orders locally
consults too; the rendered values themselves live in ``issue_cells``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..core.issue_profile import IssueProfile
from ..core.model import (
    AgentRun,
    OpenBlocker,
    ProjectObservation,
    SessionActivity,
)
from ..issues.lifecycle import Lifecycle, collection_open_blockers, in_lifecycle
from ..issues.ordering import (
    IssueSortColumn,
    SortValue,
    issue_activity,
    issue_sort_value,
    sort_by_column,
)
from ..issues.search import IssueSearchField, matches_issue_search, parse_search
from ..queries.source_queries import AuxiliaryObservation
from .list_result import ListResult


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    lifecycle: Lifecycle = "open"
    text: str = ""
    search_fields: frozenset[IssueSearchField] = frozenset(IssueSearchField)


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    project: ProjectObservation
    issue: IssueProfile
    observed_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[SessionActivity, ...] = ()
    queried: bool = False
    auxiliary: AuxiliaryObservation | None = None
    related_issues: tuple[IssueProfile, ...] = ()


def row_open_blockers(row: IssueListRow) -> tuple[OpenBlocker, ...] | None:
    """The row's Open Blockers, or nothing when they were not observed.

    A queried row carries them in its page's auxiliary facts; a row of a
    complete snapshot judges them against the Project's other Issues.
    """
    if not row.queried:
        blocked_by = frozenset(row.issue.relationships.blocked_by)
        # Most Issues name no blocker, so they skip the scan of the snapshot.
        if not blocked_by:
            return ()
        snapshot = row.project.snapshot
        issues = snapshot.issues if snapshot is not None else ()
        return collection_open_blockers(
            row.issue, {issue.id: issue for issue in issues if issue.id in blocked_by}
        )
    if row.auxiliary is None or row.auxiliary.open_blockers is None:
        return None
    return tuple(row.auxiliary.open_blockers)


def is_waiting(row: IssueListRow) -> bool:
    """Tell whether the row's Issue is open and waits on some Open Blocker."""
    return row.issue.state == "open" and bool(row_open_blockers(row))


@dataclass(frozen=True, slots=True)
class IssueListSummary:
    matched_issue_count: int
    observed_issue_count: int
    open_issue_count: int = 0
    closed_issue_count: int = 0


def query_indexed_issue_list(
    *,
    projects: Mapping[str, ProjectObservation],
    issues: Mapping[tuple[str, str], IssueProfile],
    agent_runs: Mapping[str, AgentRun],
    issue_runs: Mapping[str, Sequence[str]],
    query: IssueListQuery,
    revision: int,
) -> ListResult[IssueListRow, IssueListSummary]:
    issue_id_counts = Counter(issue_id for _project_id, issue_id in issues)
    issues_by_project: dict[str, list[IssueProfile]] = {
        project_id: [] for project_id in projects
    }
    for (project_id, _issue_id), issue in issues.items():
        if project_id in issues_by_project:
            issues_by_project[project_id].append(issue)
    rows: list[IssueListRow] = []
    observed_issue_count = 0
    matched_issue_count = 0
    open_issue_count = 0
    search_terms = tuple(term.casefold() for term in parse_search(query.text).terms)
    for project in projects.values():
        project_issues = issues_by_project[project.project_id]
        observed_issue_count += len(project_issues)
        open_issue_count += sum(1 for issue in project_issues if issue.state == "open")
        collection = {issue.id: issue for issue in project_issues}
        visible_issues = [
            issue
            for issue in project_issues
            if in_lifecycle(issue, query.lifecycle, collection)
            and matches_issue_search(issue, project, query.search_fields, search_terms)
        ]
        # Only Issues are rows, like an Issue tracker's feed: a Project with
        # nothing visible contributes no placeholder.
        for issue in visible_issues:
            matched_issue_count += 1
            key = (
                row_key("issue", issue.id)
                if issue_id_counts[issue.id] == 1
                else row_key("issue", project.project_id, issue.id)
            )
            bound_run_ids = issue_runs.get(issue.id, [])
            observed_runs = tuple(
                agent_runs[run_id] for run_id in bound_run_ids if run_id in agent_runs
            )
            session_states: tuple[SessionActivity, ...] = tuple(
                agent_runs[run_id].activity if run_id in agent_runs else "unknown"
                for run_id in bound_run_ids
            )
            rows.append(
                IssueListRow(
                    key,
                    project,
                    issue=issue,
                    observed_runs=observed_runs,
                    session_states=session_states,
                )
            )
    return ListResult(
        rows=tuple(rows),
        revision=revision,
        summary=IssueListSummary(
            matched_issue_count=matched_issue_count,
            observed_issue_count=observed_issue_count,
            open_issue_count=open_issue_count,
            closed_issue_count=observed_issue_count - open_issue_count,
        ),
    )


def issue_result_count_text(count: int) -> str:
    """Describe the filtered result: ``0 issues``, ``1 issue``, ``6 issues``.

    ``count`` is the matched Issue total after every active filter, which is
    also the rendered row count while the table is not paginated. The copy is
    lifecycle-neutral and never a ``M of N`` total.
    """
    return "1 issue" if count == 1 else f"{count} issues"


def row_key(kind: str, *identities: str) -> str:
    """Encode opaque identities into an unambiguous row key."""
    return json.dumps([kind, *identities], ensure_ascii=False, separators=(",", ":"))


def empty_issue_message(query: IssueListQuery) -> str:
    """Explain an empty Issue list in terms of the active query."""
    if parse_search(query.text).terms:
        return "no Issues match the current filters"
    if query.lifecycle == "all":
        return "no Issues"
    if query.lifecycle == "ready":
        return "no Ready Issues"
    return f"no {query.lifecycle} Issues"


def unobserved_auxiliary(row: IssueListRow) -> str:
    """Say why a row lacks an auxiliary fact: never fetched, or failed."""
    if row.auxiliary is not None and row.auxiliary.status == "unavailable":
        return "unavailable"
    return "not fetched"


def row_sort_value(row: IssueListRow, column: IssueSortColumn) -> SortValue:
    """Derive the value ``column`` orders the row by, or nothing when it has none."""
    return issue_sort_value(
        row.issue, row.project, column, comment_count=_comment_count(row)
    )


def sort_issue_rows(
    rows: Iterable[IssueListRow], column: IssueSortColumn, *, descending: bool = False
) -> list[IssueListRow]:
    """Order rows by one column, ties by Project, Issue Number and key."""
    return sort_by_column(
        rows,
        value=lambda row: row_sort_value(row, column),
        tie_break=row_tie_break,
        descending=descending,
    )


def row_tie_break(row: IssueListRow) -> tuple[str, int, str]:
    """Order rows that share a sort value by Project, Issue Number and key."""
    return row.project.project_id.casefold(), row.issue.number, row.key


def _comment_count(row: IssueListRow) -> int | None:
    # A queried row whose activity was never fetched has no count to order
    # by; the table shows ``not fetched`` there.
    if not row.queried:
        return issue_activity(row.issue, row.project).comment_count
    if row.auxiliary is not None and row.auxiliary.activity is not None:
        return row.auxiliary.activity.comment_count
    return None
