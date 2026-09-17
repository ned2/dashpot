"""Parse the lexical and date-sort subset shared by item-list searches, and match Issues.

The search fields and matching live beside the parser so a source that
searches locally consults them without loading the Issues pane read model.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ..core.issue_profile import IssueProfile
from ..core.model import ProjectObservation

SearchSortField = Literal["created", "updated"]


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


def matches_issue_search(
    issue: IssueProfile,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
    terms: tuple[str, ...],
) -> bool:
    """Tell whether every casefolded term occurs in the Issue's searched fields."""
    if not terms:
        return True
    searchable = _searchable_issue_text(issue, project, fields)
    return all(term in searchable for term in terms)


def _searchable_issue_text(
    issue: IssueProfile,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
) -> str:
    values = [value for field in fields for value in field.values(issue, project)]
    return "\n".join(values).casefold()


@dataclass(frozen=True, slots=True)
class SearchSort:
    field: SearchSortField
    descending: bool = True


@dataclass(frozen=True, slots=True)
class ParsedSearch:
    terms: tuple[str, ...] = ()
    sort: SearchSort | None = None
    diagnostics: tuple[str, ...] = ()


def parse_search(text: str) -> ParsedSearch:
    """Parse quoted terms and GitHub-shaped created or updated sorting."""
    diagnostics: list[str] = []
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        tokens = text.split()
        diagnostics.append(str(exc))

    terms: list[str] = []
    sort: SearchSort | None = None
    for token in tokens:
        if not token.casefold().startswith("sort:"):
            terms.append(token)
            continue
        parsed_sort = _parse_sort(token.partition(":")[2])
        if parsed_sort is None:
            diagnostics.append(
                f"Unsupported sort {token!r}; use created or updated, "
                "optionally followed by -asc or -desc"
            )
        elif sort is not None:
            diagnostics.append("Only one sort: qualifier is supported")
        else:
            sort = parsed_sort
    return ParsedSearch(tuple(terms), sort, tuple(diagnostics))


def _parse_sort(value: str) -> SearchSort | None:
    normalized = value.casefold()
    for field in ("created", "updated"):
        if normalized in {field, f"{field}-desc"}:
            return SearchSort(field, descending=True)
        if normalized == f"{field}-asc":
            return SearchSort(field, descending=False)
    return None
