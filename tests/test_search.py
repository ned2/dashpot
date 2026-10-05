from __future__ import annotations

import pytest

from dashpot.issues.search import SearchSort, parse_search


def test_unquoted_words_are_implicit_and_terms() -> None:
    parsed = parse_search("clipboard failure")

    assert parsed.terms == ("clipboard", "failure")
    assert parsed.sort is None
    assert parsed.warnings == ()
    assert parsed.refusals == ()


def test_quoted_phrase_remains_one_lexical_term() -> None:
    parsed = parse_search('"clipboard failure" sort:updated-desc')

    assert parsed.terms == ("clipboard failure",)
    assert parsed.sort == SearchSort("updated", descending=True)
    assert parsed.warnings == ()
    assert parsed.refusals == ()


@pytest.mark.parametrize(
    ("text", "terms"),
    [
        # Only a double quote groups words, as in GitHub's search syntax: an
        # apostrophe and a backslash belong to their word.
        ("can't", ("can't",)),
        ("user's 'single quoted'", ("user's", "'single", "quoted'")),
        (r"C:\work a\b", (r"C:\work", r"a\b")),
        ('label:"good first" \t  issue', ("label:good first", "issue")),
        ('"" spaced   out ', ("spaced", "out")),
    ],
)
def test_words_split_on_whitespace_and_only_double_quotes_group(
    text: str, terms: tuple[str, ...]
) -> None:
    parsed = parse_search(text)

    assert parsed.terms == terms
    assert parsed.warnings == ()
    assert parsed.refusals == ()


def test_created_and_updated_sort_forms_match_github_direction_defaults() -> None:
    assert parse_search("sort:created").sort == SearchSort("created", descending=True)
    assert parse_search("sort:created-asc").sort == SearchSort(
        "created", descending=False
    )
    assert parse_search("sort:updated-asc").sort == SearchSort(
        "updated", descending=False
    )


def test_unsupported_sort_is_removed_from_terms_and_refused() -> None:
    parsed = parse_search("navigation sort:comments-desc")

    assert parsed.terms == ("navigation",)
    assert parsed.sort is None
    assert parsed.warnings == ()
    assert parsed.refusals == (
        "Unsupported sort 'sort:comments-desc'; use created or updated, "
        "optionally followed by -asc or -desc",
    )


def test_a_second_sort_is_refused() -> None:
    parsed = parse_search("sort:created sort:updated")

    assert parsed.sort == SearchSort("created", descending=True)
    assert parsed.refusals == ("Only one sort: qualifier is supported",)


def test_incomplete_quote_is_a_warning_while_editing() -> None:
    parsed = parse_search('"clipboard failure')

    # The phrase being typed searches as typed; nothing is refused.
    assert parsed.terms == ("clipboard failure",)
    assert parsed.warnings == ("No closing quotation",)
    assert parsed.refusals == ()
