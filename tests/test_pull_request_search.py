"""GitHub-shaped search parsing for the Pull Request inventory."""

from __future__ import annotations

from dashpot.pull_request_search import parse_pull_request_search
from dashpot.search import SearchSort


def test_separates_lexical_terms_from_supported_qualifiers_and_sorting() -> None:
    parsed = parse_pull_request_search(
        '"terminal failure" author:NED -is:draft sort:created-asc'
    )

    assert parsed.terms == ("terminal failure",)
    assert [(item.field, item.value, item.negated) for item in parsed.qualifiers] == [
        ("author", "ned", False),
        ("is", "draft", True),
    ]
    assert parsed.sort == SearchSort("created", descending=False)
    assert parsed.diagnostics == ()


def test_accepts_github_review_spellings_and_active_inventory_predicates() -> None:
    parsed = parse_pull_request_search(
        "is:pr is:open is:unmerged review:changes_requested status:pending"
    )

    assert [(item.field, item.value) for item in parsed.qualifiers] == [
        ("is", "pr"),
        ("is", "open"),
        ("is", "unmerged"),
        ("review", "changes_requested"),
        ("status", "pending"),
    ]
    assert parsed.diagnostics == ()


def test_invalid_supported_qualifier_is_removed_and_diagnosed() -> None:
    parsed = parse_pull_request_search("fix status:neutral")

    assert parsed.terms == ("fix",)
    assert parsed.qualifiers == ()
    assert parsed.diagnostics == (
        "Unsupported Pull Request qualifier 'status:neutral'; "
        "use status:failure or status:pending or status:success",
    )


def test_unknown_qualifier_remains_a_lexical_term() -> None:
    parsed = parse_pull_request_search("label:bug")

    assert parsed.terms == ("label:bug",)
    assert parsed.diagnostics == ()
