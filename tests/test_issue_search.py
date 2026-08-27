from __future__ import annotations

from dashpot.issue_search import IssueSearchSort, parse_issue_search


def test_unquoted_words_are_implicit_and_terms() -> None:
    parsed = parse_issue_search("clipboard failure")

    assert parsed.terms == ("clipboard", "failure")
    assert parsed.sort is None
    assert parsed.diagnostics == ()


def test_quoted_phrase_remains_one_lexical_term() -> None:
    parsed = parse_issue_search('"clipboard failure" sort:updated-desc')

    assert parsed.terms == ("clipboard failure",)
    assert parsed.sort == IssueSearchSort("updated", descending=True)
    assert parsed.diagnostics == ()


def test_created_and_updated_sort_forms_match_github_direction_defaults() -> None:
    assert parse_issue_search("sort:created").sort == IssueSearchSort(
        "created", descending=True
    )
    assert parse_issue_search("sort:created-asc").sort == IssueSearchSort(
        "created", descending=False
    )
    assert parse_issue_search("sort:updated-asc").sort == IssueSearchSort(
        "updated", descending=False
    )


def test_unsupported_sort_is_removed_from_terms_and_reported() -> None:
    parsed = parse_issue_search("navigation sort:comments-desc")

    assert parsed.terms == ("navigation",)
    assert parsed.sort is None
    assert parsed.diagnostics == (
        "Unsupported sort 'sort:comments-desc'; use created or updated, "
        "optionally followed by -asc or -desc",
    )


def test_incomplete_quote_is_non_fatal_while_editing() -> None:
    parsed = parse_issue_search('"clipboard failure')

    assert parsed.terms == ('"clipboard', "failure")
    assert parsed.diagnostics == ("No closing quotation",)
