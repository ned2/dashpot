"""Derive the Issue facts a list is ordered by: priority, comment activity, dates.

The one place a source that orders locally consults, so a Query Page a
Markdown Project orders and the Issues pane read model agree on every
column without the source loading the read model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypeGuard

from ..core.issue_profile import IssueProfile
from ..core.model import IssueActivity, ProjectObservation

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

# What a column yields for ordering: something Python can compare, or nothing.
type SortValue = SupportsRichComparison | None
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


def issue_sort_value(
    issue: IssueProfile,
    project: ProjectObservation,
    column: IssueSortColumn,
    *,
    comment_count: int | None,
) -> SortValue:
    """Derive the value ``column`` orders the Issue by, or nothing when it has none.

    The comment count is supplied because where it comes from — the Project's
    observation or a queried row's auxiliary facts — is the caller's to know.
    """
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
        return project.display_label.casefold()
    if column == "assignees":
        return tuple(assignee.casefold() for assignee in issue.assignees)
    if column == "author":
        return _optional_text_value(issue.author)
    if column == "milestone":
        return _optional_text_value(issue.milestone)
    if column == "type":
        return _optional_text_value(issue.issue_type)
    if column == "comments":
        return comment_count
    if column == "created":
        return _timestamp_value(issue.created_at)
    return _timestamp_value(issue.updated_at)


def sort_by_column[T](
    items: Iterable[T],
    *,
    value: Callable[[T], SortValue],
    tie_break: Callable[[T], SupportsRichComparison],
    descending: bool = False,
) -> list[T]:
    """Order items by one column's value, items without a value last either way.

    Ties keep ``tie_break`` order in both directions, so a list ordered here
    lists the same items in the same order whichever way it is asked for.
    """
    ordered = sorted(items, key=tie_break)
    ordered.sort(
        key=lambda item: rank_missing_last(value(item), descending=descending),
        reverse=descending,
    )
    return ordered


def sort_issues(
    issues: Iterable[IssueProfile],
    project: ProjectObservation,
    column: IssueSortColumn,
    *,
    descending: bool = False,
) -> list[IssueProfile]:
    """Order one Project's Issues by a column, ties by Issue Number then identity."""
    return sort_by_column(
        issues,
        value=lambda issue: issue_sort_value(
            issue,
            project,
            column,
            comment_count=issue_activity(issue, project).comment_count,
        ),
        tie_break=lambda issue: (project.project_id.casefold(), issue.number, issue.id),
        descending=descending,
    )


def rank_missing_last(
    value: SortValue, *, descending: bool
) -> tuple[int, SupportsRichComparison]:
    """Rank a sort value so a missing one follows every present one either way.

    The reversal a descending sort applies then only reorders the present
    values.
    """
    missing = value is None
    if descending:
        return (0 if missing else 1, 0 if missing else value)
    return (1 if missing else 0, 0 if missing else value)


def _optional_text_value(value: str | None) -> str | None:
    return None if value is None else value.casefold()


def _timestamp_value(timestamp: str | None) -> float | None:
    if timestamp is None:
        return None
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
