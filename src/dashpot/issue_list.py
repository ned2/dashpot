"""The Issues pane read model: every visible Issue of the Project, once.

A row is one Issue joined to its Project, its bound Agent Runs and their
states. The Issue facts a row sorts by — priority, comment activity, dates —
are derived here so the query and the rendered table order alike; the
rendered values themselves live in ``issue_cells``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeGuard

from .issue_profile import IssueProfile
from .model import (
    AgentRun,
    IssueActivity,
    ProjectObservation,
    RunState,
    WorkspaceSnapshot,
)
from .search import parse_search
from .source_queries import AuxiliaryObservation

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

IssueState = Literal["open", "closed"]
RowKind = Literal["issue"]
# What a column yields for ordering: something Python can compare, or nothing.
SortValue: TypeAlias = "SupportsRichComparison | None"
# The compact P-level a recognized priority label stands for.
PriorityLevel = Literal["P0", "P1", "P2", "P3"]
PRIORITY_BY_LABEL: dict[str, PriorityLevel] = {
    "priority/p0": "P0",
    "priority/p1": "P1",
    "priority/p2": "P2",
    "priority/p3": "P3",
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}
# The Issue facts a list can be ordered by, named as the table's columns.
IssueSortColumn = Literal[
    "number",
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
]
ISSUE_SORT_COLUMNS: tuple[IssueSortColumn, ...] = (
    "number",
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


class IssueSearchField(StrEnum):
    PROJECT = "project"
    NUMBER = "number"
    ASSIGNEES = "assignees"
    LABELS = "labels"
    AUTHOR = "author"
    MILESTONE = "milestone"
    TYPE = "type"
    TITLE = "title"

    def values(
        self, issue: IssueProfile, project: ProjectObservation
    ) -> tuple[str, ...]:
        if self is IssueSearchField.PROJECT:
            return (project.display_label,)
        if self is IssueSearchField.NUMBER:
            return (f"#{issue.number}",)
        if self is IssueSearchField.ASSIGNEES:
            return issue.assignees
        if self is IssueSearchField.LABELS:
            return issue.labels
        if self is IssueSearchField.AUTHOR:
            return _optional_value(issue.author)
        if self is IssueSearchField.MILESTONE:
            return _optional_value(issue.milestone)
        if self is IssueSearchField.TYPE:
            return _optional_value(issue.issue_type)
        return (issue.title,)


def _optional_value(value: str | None) -> tuple[str, ...]:
    return (value,) if value else ()


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    states: frozenset[IssueState] = frozenset({"open"})
    text: str = ""
    search_fields: frozenset[IssueSearchField] = frozenset(IssueSearchField)


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    kind: RowKind
    project: ProjectObservation
    issue: IssueProfile
    observed_runs: tuple[AgentRun, ...] = ()
    project_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[RunState, ...] = ()
    queried: bool = False
    auxiliary: AuxiliaryObservation | None = None
    related_issues: tuple[IssueProfile, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueListResult:
    rows: tuple[IssueListRow, ...]
    matched_issue_count: int
    observed_issue_count: int
    revision: int = 0
    # Lifecycle split of every observed Issue, before any filter, so the
    # Issue pane title can show the complete inventory regardless of the
    # active lifecycle or search filter.
    open_issue_count: int = 0
    closed_issue_count: int = 0


def query_issue_list(
    snapshot: WorkspaceSnapshot,
    query: IssueListQuery = IssueListQuery(),
    *,
    revision: int = 0,
) -> IssueListResult:
    """Query source-neutral Issue-list rows from complete observed state."""
    projects: dict[str, ProjectObservation] = {}
    issues: dict[tuple[str, str], IssueProfile] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            key = (project.project_id, issue.id)
            if key in issues:
                raise ValueError(
                    f"Duplicate Issue Identity {issue.id} in {project.project_id}"
                )
            issues[key] = issue
    agent_runs: dict[str, AgentRun] = {}
    for run in snapshot.agent_runs:
        if run.id in agent_runs:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        agent_runs[run.id] = run
    return query_indexed_issue_list(
        projects=projects,
        issues=issues,
        agent_runs=agent_runs,
        issue_runs=snapshot.issue_runs,
        query=query,
        revision=revision,
    )


def query_indexed_issue_list(
    *,
    projects: Mapping[str, ProjectObservation],
    issues: Mapping[tuple[str, str], IssueProfile],
    agent_runs: Mapping[str, AgentRun],
    issue_runs: Mapping[str, Sequence[str]],
    query: IssueListQuery,
    revision: int,
) -> IssueListResult:
    issue_id_counts = Counter(issue_id for _project_id, issue_id in issues)
    issues_by_project: dict[str, list[IssueProfile]] = {
        project_id: [] for project_id in projects
    }
    for (project_id, _issue_id), issue in issues.items():
        if project_id in issues_by_project:
            issues_by_project[project_id].append(issue)
    runs_by_project = {
        project.project_id: tuple(
            run
            for run in agent_runs.values()
            if run.observation_project_id == project.project_id
        )
        for project in projects.values()
    }
    rows: list[IssueListRow] = []
    observed_issue_count = 0
    matched_issue_count = 0
    open_issue_count = 0
    search_terms = tuple(term.casefold() for term in parse_search(query.text).terms)
    for project in projects.values():
        project_issues = issues_by_project[project.project_id]
        observed_issue_count += len(project_issues)
        open_issue_count += sum(1 for issue in project_issues if issue.state == "open")
        visible_issues = [
            issue
            for issue in project_issues
            if issue.state in query.states
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
            session_states: tuple[RunState, ...] = tuple(
                agent_runs[run_id].state if run_id in agent_runs else "unknown"
                for run_id in bound_run_ids
            )
            rows.append(
                IssueListRow(
                    key,
                    "issue",
                    project,
                    issue=issue,
                    observed_runs=observed_runs,
                    project_runs=runs_by_project[project.project_id],
                    session_states=session_states,
                )
            )
    # Agent Runs without an Issue Binding are not Work rows; they remain
    # visible through each Project's observed-run facts (project_runs).
    return IssueListResult(
        tuple(rows),
        matched_issue_count,
        observed_issue_count,
        revision,
        open_issue_count=open_issue_count,
        closed_issue_count=observed_issue_count - open_issue_count,
    )


ISSUE_STATE_CYCLE: tuple[frozenset[IssueState], ...] = (
    frozenset({"open"}),
    frozenset({"closed"}),
    frozenset({"open", "closed"}),
)


def next_issue_states(states: frozenset[IssueState]) -> frozenset[IssueState]:
    """Flip the lifecycle filter open -> closed -> all -> open."""
    if states in ISSUE_STATE_CYCLE:
        index = ISSUE_STATE_CYCLE.index(states)
        return ISSUE_STATE_CYCLE[(index + 1) % len(ISSUE_STATE_CYCLE)]
    return ISSUE_STATE_CYCLE[0]


def issue_result_count_text(count: int) -> str:
    """Describe the filtered result: ``0 issues``, ``1 issue``, ``6 issues``.

    ``count`` is the matched Issue total after every active filter, which is
    also the rendered row count while the table is not paginated. The copy is
    lifecycle-neutral and never a ``M of N`` total.
    """
    return "1 issue" if count == 1 else f"{count} issues"


def issue_inventory_text(result: IssueListResult) -> str:
    """Describe the complete lifecycle inventory: ``Open 6 · Closed 19``.

    Both totals are shown whatever the query, with labels before numbers so
    the copy never reads as a pagination status.
    """
    return f"Open {result.open_issue_count} · Closed {result.closed_issue_count}"


def row_key(kind: str, *identities: str) -> str:
    """Encode opaque identities into an unambiguous row key."""
    return json.dumps([kind, *identities], ensure_ascii=False, separators=(",", ":"))


def empty_issue_message(query: IssueListQuery) -> str:
    """Explain an empty Issue list in terms of the active query."""
    if parse_search(query.text).terms:
        return "no Issues match the current filters"
    if query.states == frozenset({"open"}):
        return "no open Issues"
    if query.states == frozenset({"closed"}):
        return "no closed Issues"
    if query.states == frozenset({"open", "closed"}):
        return "no Issues"
    return "no Issues match the current filters"


def _searchable_issue_text(
    issue: IssueProfile,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
) -> str:
    values = [value for field in fields for value in field.values(issue, project)]
    return "\n".join(values).casefold()


def matches_issue_search(
    issue: IssueProfile,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
    terms: tuple[str, ...],
) -> bool:
    if not terms:
        return True
    searchable = _searchable_issue_text(issue, project, fields)
    return all(term in searchable for term in terms)


def is_priority_label(label: str) -> bool:
    """Tell whether a label declares an Issue priority."""
    return label.casefold() in PRIORITY_BY_LABEL


def issue_priority_label(issue: IssueProfile) -> str | None:
    """The recognized label that sets the Issue's priority: the most urgent one."""
    labels = [label for label in issue.labels if is_priority_label(label)]
    if not labels:
        return None
    return min(labels, key=lambda label: PRIORITY_BY_LABEL[label.casefold()])


def issue_priority(issue: IssueProfile) -> PriorityLevel | None:
    """The Issue's compact priority, or nothing when no label declares one."""
    label = issue_priority_label(issue)
    return None if label is None else PRIORITY_BY_LABEL[label.casefold()]


def issue_activity(issue: IssueProfile, project: ProjectObservation) -> IssueActivity:
    """The Issue's observed comment and linked Pull Request activity, if any."""
    if project.snapshot is None:
        return IssueActivity()
    return project.snapshot.issue_activity.get(issue.id, IssueActivity())


def is_issue_sort_column(column: str) -> TypeGuard[IssueSortColumn]:
    """Tell whether a submitted ordering names an Issue fact a list sorts by."""
    return column in ISSUE_SORT_COLUMNS


def issue_sort_value(row: IssueListRow, column: IssueSortColumn) -> SortValue:
    """Derive the value ``column`` orders the row by, or nothing when it has none."""
    issue = row.issue
    if column == "number":
        return issue.number
    if column == "priority":
        priority = issue_priority(issue)
        return None if priority is None else int(priority[1:])
    if column == "labels":
        labels = tuple(
            label.casefold() for label in issue.labels if not is_priority_label(label)
        )
        return labels or None
    if column == "project":
        return row.project.display_label.casefold()
    if column == "assignees":
        return tuple(assignee.casefold() for assignee in issue.assignees)
    if column == "author":
        return _optional_text_value(issue.author)
    if column == "milestone":
        return _optional_text_value(issue.milestone)
    if column == "type":
        return _optional_text_value(issue.issue_type)
    if column == "comments":
        return _comment_count(row)
    if column == "created":
        return _timestamp_value(issue.created_at)
    return _timestamp_value(issue.updated_at)


def sort_issue_rows(
    rows: Iterable[IssueListRow], column: IssueSortColumn, *, descending: bool = False
) -> list[IssueListRow]:
    """Order rows by one column, rows without a value last either way.

    Ties keep Project, Issue Number and key order in both directions, so a
    query page and the Issue table list the same Issues in the same order.
    """
    ordered = sorted(rows, key=row_tie_break)
    ordered.sort(
        key=lambda row: rank_missing_last(
            issue_sort_value(row, column), descending=descending
        ),
        reverse=descending,
    )
    return ordered


def row_tie_break(row: IssueListRow) -> tuple[str, int, str]:
    """Order rows that share a sort value by Project, Issue Number and key."""
    return row.project.project_id.casefold(), row.issue.number, row.key


def rank_missing_last(
    value: SortValue, *, descending: bool
) -> tuple[int, SupportsRichComparison]:
    """Rank a sort value so a missing one follows every present one either way.

    The reversal a descending sort applies then only reorders the present
    values; the Issue table ranks its cells with the same key.
    """
    missing = value is None
    if descending:
        return (0 if missing else 1, 0 if missing else value)
    return (1 if missing else 0, 0 if missing else value)


def _optional_text_value(value: str | None) -> str | None:
    return None if value is None else value.casefold()


def _comment_count(row: IssueListRow) -> int | None:
    # A queried row whose activity was never fetched has no count to order
    # by; the table shows ``not fetched`` there and, unlike this sort, would
    # compare that text with the counts of rows that were fetched.
    if not row.queried:
        return issue_activity(row.issue, row.project).comment_count
    if row.auxiliary is not None and row.auxiliary.activity is not None:
        return row.auxiliary.activity.comment_count
    return None


def _timestamp_value(timestamp: str | None) -> float | None:
    if timestamp is None:
        return None
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
