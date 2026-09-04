from __future__ import annotations

from dashpot.search import SearchSort, parse_search


def test_unquoted_words_are_implicit_and_terms() -> None:
    parsed = parse_search("clipboard failure")

    assert parsed.terms == ("clipboard", "failure")
    assert parsed.sort is None
    assert parsed.diagnostics == ()


def test_quoted_phrase_remains_one_lexical_term() -> None:
    parsed = parse_search('"clipboard failure" sort:updated-desc')

    assert parsed.terms == ("clipboard failure",)
    assert parsed.sort == SearchSort("updated", descending=True)
    assert parsed.diagnostics == ()


def test_created_and_updated_sort_forms_match_github_direction_defaults() -> None:
    assert parse_search("sort:created").sort == SearchSort("created", descending=True)
    assert parse_search("sort:created-asc").sort == SearchSort(
        "created", descending=False
    )
    assert parse_search("sort:updated-asc").sort == SearchSort(
        "updated", descending=False
    )


def test_unsupported_sort_is_removed_from_terms_and_reported() -> None:
    parsed = parse_search("navigation sort:comments-desc")

    assert parsed.terms == ("navigation",)
    assert parsed.sort is None
    assert parsed.diagnostics == (
        "Unsupported sort 'sort:comments-desc'; use created or updated, "
        "optionally followed by -asc or -desc",
    )


def test_incomplete_quote_is_non_fatal_while_editing() -> None:
    parsed = parse_search('"clipboard failure')

    assert parsed.terms == ('"clipboard', "failure")
    assert parsed.diagnostics == ("No closing quotation",)
