from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal


IssueSearchSortField = Literal["created", "updated"]


@dataclass(frozen=True, slots=True)
class IssueSearchSort:
    field: IssueSearchSortField
    descending: bool = True


@dataclass(frozen=True, slots=True)
class ParsedIssueSearch:
    terms: tuple[str, ...] = ()
    sort: IssueSearchSort | None = None
    diagnostics: tuple[str, ...] = ()


def parse_issue_search(text: str) -> ParsedIssueSearch:
    """Parse the GitHub-shaped lexical and date-sort subset Dashpot supports."""

    diagnostics: list[str] = []
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        tokens = text.split()
        diagnostics.append(str(exc))

    terms: list[str] = []
    sort: IssueSearchSort | None = None
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
    return ParsedIssueSearch(tuple(terms), sort, tuple(diagnostics))


def _parse_sort(value: str) -> IssueSearchSort | None:
    normalized = value.casefold()
    for field in ("created", "updated"):
        if normalized in {field, f"{field}-desc"}:
            return IssueSearchSort(field, descending=True)
        if normalized == f"{field}-asc":
            return IssueSearchSort(field, descending=False)
    return None
