"""Parse GitHub-shaped Pull Request search qualifiers Dashpot can answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from .search import SearchSort, parse_search

PullRequestQualifierField = Literal[
    "author", "base", "draft", "head", "is", "review", "state", "status"
]


@dataclass(frozen=True, slots=True)
class PullRequestQualifier:
    field: PullRequestQualifierField
    value: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class ParsedPullRequestSearch:
    terms: tuple[str, ...] = ()
    qualifiers: tuple[PullRequestQualifier, ...] = ()
    sort: SearchSort | None = None
    diagnostics: tuple[str, ...] = ()


_QUALIFIER_VALUES: dict[PullRequestQualifierField, frozenset[str]] = {
    "author": frozenset(),
    "base": frozenset(),
    "head": frozenset(),
    "draft": frozenset({"true", "false"}),
    "is": frozenset({"draft", "open", "closed", "merged", "pr", "unmerged"}),
    "review": frozenset(
        {"approved", "changes-requested", "changes_requested", "none", "required"}
    ),
    "state": frozenset({"open", "closed"}),
    "status": frozenset({"failure", "pending", "success"}),
}


def parse_pull_request_search(text: str) -> ParsedPullRequestSearch:
    """Parse the Pull Request qualifiers supported by its observed profile."""
    parsed = parse_search(text)
    terms: list[str] = []
    qualifiers: list[PullRequestQualifier] = []
    diagnostics = list(parsed.diagnostics)
    for token in parsed.terms:
        negated = token.startswith("-")
        candidate = token[1:] if negated else token
        field_text, separator, value = candidate.partition(":")
        field_value = field_text.casefold()
        if not separator or field_value not in _QUALIFIER_VALUES:
            terms.append(token)
            continue
        field = cast("PullRequestQualifierField", field_value)
        normalized = value.casefold()
        allowed = _QUALIFIER_VALUES[field]
        if not normalized or (allowed and normalized not in allowed):
            guidance = (
                "use " + " or ".join(f"{field}:{choice}" for choice in sorted(allowed))
                if allowed
                else f"{field}: requires a value"
            )
            diagnostics.append(
                f"Unsupported Pull Request qualifier {token!r}; {guidance}"
            )
            continue
        qualifiers.append(
            PullRequestQualifier(
                field=field,
                value=normalized,
                negated=negated,
            )
        )
    return ParsedPullRequestSearch(
        tuple(terms), tuple(qualifiers), parsed.sort, tuple(diagnostics)
    )
