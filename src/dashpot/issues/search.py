"""Parse the lexical and date-sort subset shared by item-list searches."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal

SearchSortField = Literal["created", "updated"]


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
