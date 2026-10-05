"""Parse the lexical and date-sort subset shared by item-list searches, and match Issues.

The search fields and matching live beside the parser so a source that
searches locally consults them without loading the Issues pane read model.
"""

from __future__ import annotations

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
    """The terms and sort a search names, and what it could not use.

    ``warnings`` describe text that is still being edited, such as a quote
    not yet closed, which a search still answers. ``refusals`` name a
    qualifier the search cannot answer, such as an unsupported ``sort:``,
    which fails a query that honours it.
    """

    terms: tuple[str, ...] = ()
    sort: SearchSort | None = None
    warnings: tuple[str, ...] = ()
    refusals: tuple[str, ...] = ()


def parse_search(text: str) -> ParsedSearch:
    """Parse quoted terms and GitHub-shaped created or updated sorting."""
    tokens, quote_open = _search_tokens(text)
    warnings = ("No closing quotation",) if quote_open else ()
    terms: list[str] = []
    refusals: list[str] = []
    sort: SearchSort | None = None
    for token in tokens:
        if not token.casefold().startswith("sort:"):
            terms.append(token)
            continue
        parsed_sort = _parse_sort(token.partition(":")[2])
        if parsed_sort is None:
            refusals.append(
                f"Unsupported sort {token!r}; use created or updated, "
                "optionally followed by -asc or -desc"
            )
        elif sort is not None:
            refusals.append("Only one sort: qualifier is supported")
        else:
            sort = parsed_sort
    return ParsedSearch(tuple(terms), sort, warnings, tuple(refusals))


def _search_tokens(text: str) -> tuple[tuple[str, ...], bool]:
    """Split search text on whitespace, a double-quoted phrase staying one token.

    As in GitHub's search syntax, only a double quote groups words: an
    apostrophe and a backslash are ordinary characters of their word. A
    quote still open at the end of the text runs to its end, so a phrase
    being typed searches as typed; the second value says one was left open.
    """
    tokens: list[str] = []
    current: list[str] = []
    quoted = False
    for character in text:
        if character == '"':
            quoted = not quoted
        elif character.isspace() and not quoted:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(character)
    if current:
        tokens.append("".join(current))
    return tuple(tokens), quoted


def _parse_sort(value: str) -> SearchSort | None:
    normalized = value.casefold()
    for field in ("created", "updated"):
        if normalized in {field, f"{field}-desc"}:
            return SearchSort(field, descending=True)
        if normalized == f"{field}-asc":
            return SearchSort(field, descending=False)
    return None
