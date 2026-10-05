"""Exercise page coverage, source scope and portable continuation at the public seam."""

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import patch

import pydantic
import pytest

from dashpot.core.model import OpenBlocker
from dashpot.github.github import (
    RATE_LIMIT_SELECTION,
    GitHubRequestError,
    LatestRateLimit,
)
from dashpot.project.project_config import load_project_config
from dashpot.queries.github_queries import GitHubQuerySource, validate_grouping
from dashpot.queries.markdown_queries import MarkdownQuerySource
from dashpot.queries.pages import InvalidContinuation, QueryPage, QueryRequest
from factories import (
    SequenceRunner,
    completed,
    local_issue_document,
    write_project_config,
)
from test_github_issues import PROJECT_ID, REPOSITORY_ID, issue_record
from test_github_pull_requests import pull_request_node


def context(principal="U_1", name="ned2/dashpot"):
    return {
        "repository": {"id": REPOSITORY_ID, "nameWithOwner": name},
        "viewer": {"id": principal},
    }


def search(
    *nodes,
    count=None,
    cursor=None,
    principal="U_1",
    name="ned2/dashpot",
    opened=3,
    closed=5,
):
    return {
        **context(principal, name),
        "totals": {
            "opened": {"totalCount": opened},
            "closed": {"totalCount": closed},
        },
        "search": {
            "issueCount": len(nodes) if count is None else count,
            "nodes": list(nodes),
            "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
        },
    }


def batch(*nodes, principal="U_1"):
    return {**context(principal), "nodes": list(nodes)}


def hit(number):
    return {
        "__typename": "Issue",
        "id": f"I_issue_{number}",
        "repository": {"id": REPOSITORY_ID},
    }


def node(number):
    raw = issue_record(number)
    raw["__typename"] = "Issue"
    return raw


def github(tmp_path, *answers, **options):
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "github"},
    )
    runner = SequenceRunner(
        *(completed(json.dumps({"data": answer})) for answer in answers)
    )
    return GitHubQuerySource(
        tmp_path, load_project_config(tmp_path), runner=runner, **options
    ), runner


def markdown(tmp_path):
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "markdown", "path": "issues"},
    )
    directory = tmp_path / "issues"
    directory.mkdir(exist_ok=True)
    for number in range(1, 4):
        (directory / f"{number}.md").write_text(
            local_issue_document(
                issue_id=f"I_{number}",
                number=number,
                reference=f"issue-{number}",
                title=f"Issue {number}",
            )
        )
    return MarkdownQuerySource(tmp_path, load_project_config(tmp_path))


def test_github_large_history_only_completes_requested_page(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(*(hit(n) for n in range(1, 51)), count=2400, cursor="next"),
        *(
            batch(*(node(n) for n in range(start, min(start + 24, 51))))
            for start in (1, 25, 49)
        ),
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "fresh", page.diagnostics
    assert page.returned_count == 50 and page.matched_count == 2400
    assert page.continuation == "more" and page.result_limit == 1000
    assert len(runner.calls) == 5
    assert [issue.number for issue in page.issues] == list(range(1, 51))
    assert QueryPage.model_validate(json.loads(page.model_dump_json())) == page
    assert not any("DashpotIssues(" in arg for args, *_ in runner.calls for arg in args)


def test_advanced_expression_preserved_and_lifecycle_scoped(tmp_path):
    expression = (
        '(label:"bug fix" OR author:@me) -is:closed comments:>2 sort:updated-desc'
    )
    source, runner = github(tmp_path, context(), search())
    page = source.query_page(QueryRequest(query=expression, state="all")).page
    assert page.status == "fresh"
    assert page.effective_ordering == "query"
    assert (
        f"searchQuery=repo:ned2/dashpot is:issue ({expression})" in runner.calls[1][0]
    )


@pytest.mark.parametrize(
    "query",
    [
        "draft:true) OR repo:elsewhere/repo (",
        'label:"unterminated',
        "(draft:true",
        "author:ned\\",
    ],
)
def test_unbalanced_expression_cannot_escape_repository_scope(tmp_path, query):
    with pytest.raises(GitHubRequestError) as error:
        validate_grouping(query)
    assert error.value.code == "github-search-syntax"
    # The page reports the refusal as its own diagnostic; nothing reached
    # GitHub, not even the context the search would have named.
    source, runner = github(tmp_path)
    page = source.query_page(QueryRequest(query=query)).page
    assert page.status == "unavailable" and not page.issues
    assert [d.code for d in page.diagnostics] == ["github-search-syntax"]
    assert not runner.calls


@pytest.mark.parametrize(
    "query", ['label:"bug (parser"', "don't", 'label:"escaped \\" quote" (a)']
)
def test_quoted_parentheses_and_apostrophes_stay_literal_in_scope_validation(query):
    validate_grouping(query)


def test_missing_page_profile_rejects_page_atomically(tmp_path):
    source, _ = github(
        tmp_path, context(), search(hit(1), hit(2)), batch(node(1), None)
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable" and not page.issues


def test_identity_batches_preserve_siblings_and_transfer_evidence(tmp_path):
    transferred = node(3)
    transferred["repository"] = {"id": "R_elsewhere", "nameWithOwner": "other/repo"}
    source, runner = github(
        tmp_path, batch(node(1), {"id": "I_issue_2"}, transferred, None)
    )
    results = source.resolve_identities(
        ["I_issue_1", "I_issue_2", "I_issue_3", "I_issue_4", "I_issue_1"]
    )
    assert [result.outcome for result in results] == [
        "resolved",
        "unavailable",
        "outside-repository",
        "not-resolved",
    ]
    assert results[2].issue is None and results[2].reference == "other/repo#3"
    # A relationship into another Repository is ordinary, not a warning.
    assert [(d.severity, d.message) for d in results[2].diagnostics] == [
        ("info", "Issue other/repo#3 is outside the configured Repository")
    ]
    assert len(runner.calls) == 1


def test_cross_process_principal_change_rejects_continuation(tmp_path):
    source, _ = github(
        tmp_path, context(), search(hit(1), count=2, cursor="c"), batch(node(1))
    )
    first = source.query_page(QueryRequest(page_size=1)).page
    other, runner = github(tmp_path, context("U_other"))
    with pytest.raises(InvalidContinuation):
        other.query_page(QueryRequest(page_size=1, cursor=first.next_cursor))
    assert len(runner.calls) == 1


def test_markdown_cross_process_continuation_and_global_sort(tmp_path):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1, ordering="number:desc")).page
    assert first.issues[0].number == 3
    second = (
        MarkdownQuerySource(tmp_path, load_project_config(tmp_path))
        .query_page(
            QueryRequest(page_size=1, ordering="number:desc", cursor=first.next_cursor)
        )
        .page
    )
    assert second.issues[0].number == 2
    totals = source.query_page(QueryRequest(query="Issue")).totals
    assert totals.open_count == 3
    assert (
        source.query_page(QueryRequest(kind="pull-requests")).page.status
        == "unavailable"
    )


def test_markdown_orders_only_by_a_sortable_issue_fact(tmp_path):
    source = markdown(tmp_path)

    assert source.supports_sort(QueryRequest(), "created")
    assert not source.supports_sort(QueryRequest(), "title")
    page = source.query_page(QueryRequest(page_size=1, ordering="title:asc")).page
    assert page.status == "unavailable"
    assert "Unsupported local column ordering" in page.diagnostics[0].message


def test_markdown_pull_request_query_reads_no_local_issue(tmp_path):
    source = markdown(tmp_path)
    # With the Local Issues gone, reading them would fail the query.
    for path in (tmp_path / "issues").iterdir():
        path.unlink()
    (tmp_path / "issues").rmdir()

    observation = source.query_page(QueryRequest(kind="pull-requests"))

    for observed in (observation.page, observation.totals):
        assert observed.status == "unavailable"
        assert [(d.severity, d.code) for d in observed.diagnostics] == [
            ("info", "pull-requests-not-configured")
        ]
    assert observation.page.context == source.context
    assert observation.totals.open_count is None


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("can't", "Can't paste"),
        ("user's", "The user's settings"),
        (r"C:\work", r"Path C:\work\dashpot"),
        # A quote still being typed searches the phrase as typed so far.
        ('"paste fail', "Can paste failing images"),
    ],
)
def test_markdown_searches_apostrophes_backslashes_and_open_quotes(
    tmp_path, query, title
):
    source = markdown(tmp_path)
    (tmp_path / "issues" / "4.md").write_text(
        local_issue_document(issue_id="I_4", number=4, reference="four", title=title)
    )

    page = source.query_page(QueryRequest(query=query)).page

    assert page.status == "fresh"
    assert [issue.number for issue in page.issues] == [4]


def test_markdown_refuses_a_sort_it_cannot_answer(tmp_path):
    page = markdown(tmp_path).query_page(QueryRequest(query="sort:comments")).page

    assert page.status == "unavailable"
    assert page.diagnostics[0].message.startswith("Unsupported sort 'sort:comments'")


@pytest.mark.parametrize("change", ["edit", "rename", "insert", "delete"])
def test_markdown_revision_invalidates_continuation(tmp_path, change):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1)).page
    path = tmp_path / "issues/1.md"
    if change == "edit":
        path.write_text(path.read_text() + "\nchanged\n")
    elif change == "rename":
        path.rename(path.with_name("renamed.md"))
    elif change == "delete":
        path.unlink()
    else:
        (path.parent / "4.md").write_text(
            local_issue_document(
                issue_id="I_4", number=4, reference="four", title="Four"
            )
        )
    with pytest.raises(InvalidContinuation):
        MarkdownQuerySource(tmp_path, load_project_config(tmp_path)).query_page(
            QueryRequest(page_size=1, cursor=first.next_cursor)
        )


def test_same_verified_page_can_be_stale_but_new_query_cannot_inherit(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        {},
        {},
    )
    first = source.query_page(QueryRequest()).page
    stale = source.query_page(QueryRequest()).page
    other = source.query_page(QueryRequest(query="label:other")).page
    assert stale.status == "stale" and stale.issues == first.issues
    assert stale.last_good_at == first.last_good_at
    assert other.status == "unavailable" and not other.issues


def test_context_observation_failure_does_not_assert_mismatch(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="next"),
        batch(node(1)),
    )
    first = source.query_page(QueryRequest(page_size=1)).page
    failed, _ = github(tmp_path, {})
    page = failed.query_page(QueryRequest(page_size=1, cursor=first.next_cursor)).page
    assert page.status == "unavailable"


def test_provider_limit_is_distinct_from_end(tmp_path):
    from dashpot.queries.pages import (
        Continuation,
        context_fingerprint,
        cursor_digest,
        encode_continuation,
    )

    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2400, cursor="c"),
        batch(node(1)),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    token = encode_continuation(
        Continuation(
            fingerprint=context_fingerprint(first.context, request),
            offset=999,
            provider_cursor="c999",
            trail=(cursor_digest("c999"),),
        )
    )
    final, _ = github(
        tmp_path, context(), search(hit(1000), count=2400), batch(node(1000))
    )
    last = final.query_page(request.model_copy(update={"cursor": token})).page
    assert last.status == "fresh" and last.continuation == "provider-limit"
    assert last.next_cursor is None and last.matched_count == 2400


def test_refreshing_same_page_does_not_count_as_repeated_forward_cursor(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=3, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=3, cursor="c2"),
        batch(node(2)),
        context(),
        search(hit(2), count=4, cursor="c2"),
        batch(node(2)),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    later = request.model_copy(update={"cursor": first.next_cursor})
    second = source.query_page(later).page
    refreshed = source.query_page(later).page
    assert second.status == refreshed.status == "fresh"
    assert refreshed.matched_count == 4


def test_changed_source_config_rejects_continuation(tmp_path):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1)).page
    (tmp_path / "other").mkdir()
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "markdown", "path": "other"},
    )
    with pytest.raises(InvalidContinuation):
        source.query_page(QueryRequest(page_size=1, cursor=first.next_cursor))


def test_malformed_auxiliary_does_not_invalidate_complete_profile(tmp_path):
    raw = node(1)
    raw.pop("comments")
    source, _ = github(tmp_path, context(), search(hit(1)), batch(raw))
    page = source.query_page(QueryRequest()).page
    assert page.status == "fresh"
    assert page.auxiliary["I_issue_1"].status == "unavailable"
    assert page.auxiliary["I_issue_1"].activity is None


def test_export_over_search_limit_uses_repository_connections(tmp_path):
    from test_github_issues import issue_page

    answers = [
        json.loads(
            issue_page(
                [node(number) for number in range(start, min(start + 100, 1002))],
                has_next_page=start + 100 < 1002,
                end_cursor=f"c{start}",
            )
        )["data"]
        for start in range(1, 1002, 100)
    ]
    source, runner = github(tmp_path, *answers)
    export = source.enumerate_source("issues")
    assert export.status == "fresh", export.diagnostics
    assert len(export.issues) == 1001
    assert len(runner.calls) == 11
    assert not any(
        "ISSUE_ADVANCED" in argument for call in runner.calls for argument in call[0]
    )


def test_attributable_github_errors_preserve_siblings_and_auxiliary_failure(tmp_path):
    source, runner = github(tmp_path)
    first, second = node(1), node(2)
    first["comments"] = None
    second["author"] = None
    runner.results = iter(
        [
            completed(
                json.dumps(
                    {
                        "data": batch(first, second, node(3)),
                        "errors": [
                            {
                                "type": "FORBIDDEN",
                                "path": ["nodes", 0, "comments"],
                                "message": "comments unavailable",
                            },
                            {
                                "type": "FORBIDDEN",
                                "path": ["nodes", 1, "author"],
                                "message": "author unavailable",
                            },
                        ],
                    }
                ),
                returncode=1,
            ),
        ]
    )
    results = source.resolve_identities(["I_issue_1", "I_issue_2", "I_issue_3"])
    assert [result.outcome for result in results] == [
        "resolved",
        "unavailable",
        "resolved",
    ]
    assert results[0].auxiliary.status == "unavailable"
    assert results[2].auxiliary.status == "fresh"


def test_unattributable_error_never_becomes_known_absence(tmp_path):
    source, runner = github(tmp_path)
    runner.results = iter(
        [
            completed(
                json.dumps(
                    {
                        "data": batch(None, node(2)),
                        "errors": [
                            {
                                "type": "FORBIDDEN",
                                "path": ["nodes"],
                                "message": "query unavailable",
                            },
                        ],
                    }
                ),
                returncode=1,
            ),
        ]
    )
    results = source.resolve_identities(["I_issue_1", "I_issue_2"])
    assert all(result.outcome == "unavailable" for result in results)


def test_nested_profile_completion_spends_page_budget_and_is_atomic(tmp_path):
    from dashpot.github.github import RefreshBudget

    first = node(1)
    first["subIssues"] = {
        "nodes": [{"id": "related-1"}],
        "pageInfo": {"hasNextPage": True, "endCursor": "nested"},
    }
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(first),
        {
            "node": {
                "connection": {
                    "nodes": [{"id": "related-2"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "fresh"
    assert page.issues[0].relationships.sub_issues == ("related-1", "related-2")
    assert len(runner.calls) == 4
    limited, runner = github(tmp_path, context(), search(hit(1)), batch(first))
    limited.budget = RefreshBudget(requests=3, seconds=60)
    failure = limited.query_page(QueryRequest()).page
    assert failure.status == "unavailable" and not failure.issues
    assert len(runner.calls) == 3


def test_single_record_page_sizes_can_carry_full_search_cursor_history():
    from dashpot.queries.pages import (
        Continuation,
        cursor_digest,
        decode_continuation,
        encode_continuation,
    )

    continuation = Continuation(
        fingerprint="context",
        offset=999,
        provider_cursor="last",
        trail=(
            *(cursor_digest(str(index)) for index in range(998)),
            cursor_digest("last"),
        ),
    )
    assert decode_continuation(encode_continuation(continuation)) == continuation


@pytest.mark.parametrize("operation", ["page", "totals", "identities"])
@pytest.mark.parametrize(
    "failure", [OSError, RuntimeError, ValueError, KeyError, TypeError]
)
def test_expected_query_failures_publish_unavailable(tmp_path, operation, failure):
    source, runner = github(tmp_path)
    runner.results = iter([failure("cannot observe")])
    if operation == "page":
        result = source.query_page(QueryRequest()).page
    elif operation == "totals":
        result = source.query_page(QueryRequest()).totals
    else:
        (result,) = source.resolve_identities(["I_1"])
    assert result.status == "unavailable"
    assert "cannot observe" in result.diagnostics[0].message


@pytest.mark.parametrize("operation", ["page", "identities"])
def test_query_programmer_faults_escape_instead_of_becoming_stale(tmp_path, operation):
    source, runner = github(tmp_path)
    runner.results = iter([AssertionError("adapter invariant")])
    with pytest.raises(AssertionError, match="adapter invariant"):
        if operation == "page":
            source.query_page(QueryRequest())
        else:
            source.resolve_identities(["I_1"])


def arguments(runner, prefix):
    """Every recorded ``gh`` argument starting with ``prefix``, without it, in order."""
    return [
        argument.removeprefix(prefix)
        for args, *_ in runner.calls
        for argument in args
        if argument.startswith(prefix)
    ]


def operations(runner):
    """The GraphQL operation each recorded ``gh`` call sent, in order."""
    return [query.split("(")[0] for query in arguments(runner, "query=query ")]


def test_repeated_page_one_verifies_context_in_its_own_response(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        search(hit(1), principal="U_2"),
        batch(node(1), principal="U_2"),
    )
    first = source.query_page(QueryRequest()).page
    again = source.query_page(QueryRequest()).page
    assert first.status == again.status == "fresh"
    # Only the first page a source asks for learns the Repository's name
    # separately; the refresh after it sends no context request.
    assert operations(runner) == [
        "DashpotQueryContext",
        "DashpotQueryPage",
        "DashpotResolvedIssues",
        "DashpotQueryPage",
        "DashpotResolvedIssues",
    ]
    assert first.context.principal == "U_1"
    assert again.context.principal == "U_2"


def test_page_one_answering_another_repository_is_refused(tmp_path):
    other = search(hit(1))
    other["repository"] = {"id": "R_elsewhere", "nameWithOwner": "other/repo"}
    source, _ = github(tmp_path, context(), search(hit(1)), batch(node(1)), other)
    first = source.query_page(QueryRequest()).page
    refused = source.query_page(QueryRequest()).page
    assert refused.status == "stale" and refused.issues == first.issues
    assert "different Repository Identity" in refused.diagnostics[0].message


def test_page_batch_answering_another_principal_rejects_the_page(tmp_path):
    source, _ = github(
        tmp_path, context(), search(hit(1)), batch(node(1), principal="U_2")
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable" and not page.issues
    assert "different principal" in page.diagnostics[0].message


def test_continuation_answered_for_another_principal_is_discarded(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2, principal="U_2"),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    second = source.query_page(
        request.model_copy(update={"cursor": first.next_cursor})
    ).page
    assert second.status == "unavailable" and not second.issues
    assert "different principal" in second.diagnostics[0].message


def test_renamed_repository_is_searched_again_under_its_new_name(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        search(name="ned2/renamed"),
        search(hit(1), name="ned2/renamed"),
        batch(node(1)),
    )
    source.query_page(QueryRequest())
    page = source.query_page(QueryRequest()).page
    assert page.status == "fresh" and page.returned_count == 1
    assert arguments(runner, "searchQuery=") == [
        "repo:ned2/dashpot is:issue is:open",
        "repo:ned2/dashpot is:issue is:open",
        "repo:ned2/renamed is:issue is:open",
    ]


def test_a_search_erring_under_the_old_name_is_retried_under_the_new(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    source.query_page(QueryRequest())
    stale_name = search(None, name="ned2/renamed", opened=4)
    runner.results = iter(
        [
            refused(
                stale_name,
                {
                    "type": "FORBIDDEN",
                    "path": ["search", "nodes", 0],
                    "message": "not accessible",
                },
            ),
            completed(json.dumps({"data": search(hit(1), name="ned2/renamed")})),
            completed(json.dumps({"data": batch(node(1))})),
        ]
    )
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "fresh"
    assert observation.totals.status == "fresh"
    assert arguments(runner, "searchQuery=")[-2:] == [
        "repo:ned2/dashpot is:issue is:open",
        "repo:ned2/renamed is:issue is:open",
    ]


def test_a_request_github_answers_without_data_counts_nothing(tmp_path):
    # ``search`` is non-null in GitHub's schema, so an error on the field
    # itself nulls the whole response, totals included.
    source, runner = github(tmp_path, context())
    answers = runner.results
    runner.results = iter(
        [
            *answers,
            refused(None, {"type": "INVALID", "path": ["search"], "message": "down"}),
        ]
    )
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "unavailable"
    assert observation.totals.status == "unavailable"
    assert "down" in observation.totals.diagnostics[0].message


def test_continuation_searches_under_the_name_its_context_reported(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(name="ned2/renamed"),
        search(hit(2), count=2, name="ned2/renamed"),
        batch(node(2)),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    second = source.query_page(
        request.model_copy(update={"cursor": first.next_cursor})
    ).page
    assert second.status == "fresh" and second.issues[0].number == 2
    assert arguments(runner, "searchQuery=")[-1] == "repo:ned2/renamed is:issue is:open"


def test_repository_renamed_again_during_its_retry_fails_the_page(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(name="ned2/renamed"),
        search(name="ned2/renamed-again"),
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable"
    assert "renamed" in page.diagnostics[0].message


def test_rename_between_continuation_context_and_search_restarts(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2, name="ned2/renamed"),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    with pytest.raises(InvalidContinuation, match="renamed"):
        source.query_page(request.model_copy(update={"cursor": first.next_cursor}))


def test_edited_configuration_is_detected_before_any_request(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    source.query_page(QueryRequest())
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "github"},
        display_label="Edited",
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable"
    assert "configuration changed" in page.diagnostics[0].message
    assert len(runner.calls) == 3


def test_a_query_page_counts_its_totals_in_its_own_request(tmp_path):
    source, runner = github(
        tmp_path, context(), search(hit(1), opened=3, closed=5), batch(node(1))
    )
    observation = source.query_page(QueryRequest(query="label:bug", state="closed"))
    assert observation.page.status == "fresh"
    totals = observation.totals
    assert totals.status == "fresh" and totals.kind == "issues"
    # The counts are the whole Project's, whatever the page asked for.
    assert (totals.open_count, totals.closed_count) == (3, 5)
    assert totals.context.principal == "U_1"
    assert totals.context == observation.page.context
    assert operations(runner) == [
        "DashpotQueryContext",
        "DashpotQueryPage",
        "DashpotResolvedIssues",
    ]
    (query,) = [q for q in arguments(runner, "query=") if "DashpotQueryPage" in q]
    assert "opened: issues(states: [OPEN])" in query
    assert "closed: issues(states: [CLOSED])" in query


def test_a_pull_request_page_counts_merged_pull_requests_as_closed(tmp_path):
    pull = {
        **pull_request_node(1),
        "__typename": "PullRequest",
        "repository": {"id": REPOSITORY_ID},
    }
    source, runner = github(tmp_path, context(), search(pull, opened=2, closed=7))
    observation = source.query_page(QueryRequest(kind="pull-requests"))
    assert observation.page.status == "fresh"
    assert observation.totals.kind == "pull-requests"
    assert (observation.totals.open_count, observation.totals.closed_count) == (2, 7)
    (query,) = [q for q in arguments(runner, "query=") if "DashpotQueryPage" in q]
    assert "opened: pullRequests(states: [OPEN])" in query
    assert "closed: pullRequests(states: [CLOSED, MERGED])" in query


def refused(answer, *errors):
    """A ``gh`` result carrying ``answer`` beside GraphQL ``errors``, as gh exits."""
    return completed(json.dumps({"data": answer, "errors": list(errors)}), returncode=1)


def test_an_error_inside_the_search_results_still_counts_the_totals(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    first = source.query_page(QueryRequest())
    runner.results = iter(
        [
            refused(
                search(None, opened=4, closed=6),
                {
                    "type": "FORBIDDEN",
                    "path": ["search", "nodes", 0],
                    "message": "not accessible",
                },
            )
        ]
    )
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "stale"
    assert observation.page.issues == first.page.issues
    assert "not accessible" in observation.page.diagnostics[0].message
    assert observation.totals.status == "fresh"
    assert (observation.totals.open_count, observation.totals.closed_count) == (4, 6)


def test_an_error_beside_the_search_fails_the_page_and_its_totals(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    source.query_page(QueryRequest())
    runner.results = iter(
        [
            refused(
                search(hit(1), opened=4, closed=6),
                {"type": "FORBIDDEN", "path": ["totals"], "message": "no counts"},
            )
        ]
    )
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "stale"
    assert observation.totals.status == "stale"
    assert (observation.totals.open_count, observation.totals.closed_count) == (3, 5)
    assert "no counts" in observation.totals.diagnostics[0].message


def test_a_page_failing_after_its_search_keeps_the_totals_it_counted(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1), opened=4, closed=6))
    answers = runner.results
    # The Issue batch that completes the page fails after the search counted.
    runner.results = iter([*answers, RuntimeError("gone")])
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "unavailable"
    assert observation.totals.status == "fresh"
    assert observation.totals.open_count == 4


def test_page_one_answering_another_repository_counts_nothing(tmp_path):
    other = search(hit(1))
    other["repository"] = {"id": "R_elsewhere", "nameWithOwner": "other/repo"}
    source, _ = github(tmp_path, context(), other)
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "unavailable"
    assert observation.totals.status == "unavailable"
    assert observation.totals.open_count is None


def test_failed_totals_keep_their_last_good_counts(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    source.query_page(QueryRequest())
    runner.results = iter([OSError("network down")])
    stale = source.query_page(QueryRequest(query="other")).totals
    # The page is a new query with nothing to keep, but the totals are the
    # same Project's under the same principal.
    assert stale.status == "stale"
    assert (stale.open_count, stale.closed_count) == (3, 5)


def test_a_source_must_count_totals_with_its_page(tmp_path):
    class Uncounted(MarkdownQuerySource):
        @override
        def fetch_page(self, context, request, token, attempted, count_totals):
            return super().fetch_page(
                context, request, token, attempted, lambda _totals: None
            )

    source = Uncounted(tmp_path, markdown(tmp_path).config)
    with pytest.raises(AssertionError, match="count Project Totals"):
        source.query_page(QueryRequest())


def test_markdown_counts_totals_for_a_search_it_refuses(tmp_path):
    observation = markdown(tmp_path).query_page(QueryRequest(query="sort:bogus"))
    assert observation.page.status == "unavailable"
    assert observation.totals.status == "fresh"
    assert (observation.totals.open_count, observation.totals.closed_count) == (3, 0)


def test_markdown_counts_no_totals_under_a_changed_configuration(tmp_path):
    source = markdown(tmp_path)
    assert source.query_page(QueryRequest()).totals.status == "fresh"
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "markdown", "path": "issues"},
        display_label="Edited",
    )
    observation = source.query_page(QueryRequest())
    assert "configuration changed" in observation.page.diagnostics[0].message
    # The records were read under the old configuration, so they are not
    # counted as the new one's.
    assert observation.totals.status == "unavailable"
    assert observation.totals.open_count is None


def test_identity_batches_take_one_principal_from_their_answers(tmp_path):
    source, runner = github(
        tmp_path,
        batch(*(node(n) for n in range(1, 25))),
        batch(node(25), principal="U_2"),
    )
    results = source.resolve_identities([f"I_issue_{n}" for n in range(1, 26)])
    assert operations(runner) == ["DashpotResolvedIssues", "DashpotResolvedIssues"]
    assert all(result.outcome == "resolved" for result in results[:24])
    assert results[0].context.principal == "U_1"
    assert results[24].outcome == "unavailable"
    assert "different principal" in results[24].diagnostics[0].message


def test_failed_identities_keep_their_last_good_resolution(tmp_path):
    source, runner = github(tmp_path, batch(node(1)))
    (first,) = source.resolve_identities(["I_issue_1"])
    runner.results = iter([OSError("network down")])
    (stale,) = source.resolve_identities(["I_issue_1"])
    assert stale.status == "stale" and stale.issue == first.issue


def test_unreadable_configuration_keeps_every_last_good_observation(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        batch(node(1)),
    )
    page = source.query_page(QueryRequest()).page
    source.resolve_identities(["I_issue_1"])
    (tmp_path / ".dashpot" / "config.json").write_text("{")
    # The request never starts, so nothing about the context is disproved.
    stale = source.query_page(QueryRequest())
    (stale_issue,) = source.resolve_identities(["I_issue_1"])
    assert stale.page.status == "stale" and stale.page.issues == page.issues
    assert stale.totals.status == "stale" and stale.totals.open_count == 3
    assert stale_issue.status == "stale" and stale_issue.outcome == "unavailable"
    assert len(runner.calls) == 4


def test_column_ordering_becomes_the_search_sort_qualifier(tmp_path):
    source, runner = github(tmp_path, context(), search())
    page = source.query_page(QueryRequest(ordering="created:desc")).page
    assert page.status == "fresh"
    assert (
        "searchQuery=repo:ned2/dashpot is:issue is:open sort:created-desc"
        in runner.calls[1][0]
    )
    refused = source.query_page(QueryRequest(ordering="title:asc")).page
    assert "no exact GitHub source ordering" in refused.diagnostics[0].message
    assert len(runner.calls) == 2


def test_ready_searches_open_issues_github_does_not_count_as_blocked(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    page = source.query_page(QueryRequest(state="ready")).page
    assert page.status == "fresh", page.diagnostics
    assert (
        "searchQuery=repo:ned2/dashpot is:issue is:open -is:blocked"
        in runner.calls[1][0]
    )
    # The fixture's open blocker travels beside the Profile, named by its
    # Reference; its closed one is not a blocker any more.
    assert page.auxiliary["I_issue_1"].open_blockers == (
        OpenBlocker(id="I_blocker_2", reference="ned2/dashpot#7", number=7),
    )
    assert page.issues[0].relationships.blocked_by == ("I_blocker_1", "I_blocker_2")


def test_only_an_issue_query_can_ask_for_ready_issues():
    with pytest.raises(pydantic.ValidationError, match="Only an Issue query"):
        QueryRequest(kind="pull-requests", state="ready")
    assert QueryRequest(kind="issues", state="ready").state == "ready"


def resolve_with_blocker_error(tmp_path, *path):
    """Resolve Issue 1 while GitHub reports an error at one blockedBy path."""
    raw = node(1)
    node_path = ["nodes", 0, "blockedBy", *path]
    target = raw["blockedBy"]
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = None
    source, runner = github(tmp_path)
    runner.results = iter(
        [
            completed(
                json.dumps(
                    {
                        "data": batch(raw),
                        "errors": [
                            {
                                "type": "FORBIDDEN",
                                "path": node_path,
                                "message": "blocker unavailable",
                            }
                        ],
                    }
                ),
                returncode=1,
            ),
        ]
    )
    [result] = source.resolve_identities(["I_issue_1"])
    return result


@pytest.mark.parametrize(
    "path",
    [
        ("nodes", 0, "state"),
        ("nodes", 0, "number"),
        ("nodes", 0, "repository"),
        ("nodes", 0, "repository", "nameWithOwner"),
    ],
)
def test_an_unreadable_blocker_fact_fails_only_the_auxiliary_facts(tmp_path, path):
    result = resolve_with_blocker_error(tmp_path, *path)
    assert result.outcome == "resolved"
    assert result.auxiliary.status == "unavailable"
    assert result.auxiliary.open_blockers is None


@pytest.mark.parametrize(
    "path", [("nodes", 0, "id"), ("nodes", 0), ("pageInfo", "hasNextPage")]
)
def test_an_unreadable_blocker_relationship_fails_the_issue(tmp_path, path):
    # The blocker's identity belongs to the Profile, so losing it is not an
    # auxiliary failure.
    result = resolve_with_blocker_error(tmp_path, *path)
    assert result.outcome == "unavailable"
    assert result.issue is None


def test_blockers_past_the_first_page_carry_their_facts(tmp_path):
    first = node(1)
    first["blockedBy"]["pageInfo"] = {"hasNextPage": True, "endCursor": "blockers"}
    later = {
        "id": "I_blocker_3",
        "number": 11,
        "state": "OPEN",
        "repository": {"nameWithOwner": "ned2/dashpot"},
    }
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(first),
        {
            "node": {
                "connection": {
                    "nodes": [later],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "fresh", page.diagnostics
    assert "nodes { id number state repository { nameWithOwner } }" in str(
        runner.calls[3]
    )
    assert page.auxiliary["I_issue_1"].open_blockers == (
        OpenBlocker(id="I_blocker_2", reference="ned2/dashpot#7", number=7),
        OpenBlocker(id="I_blocker_3", reference="ned2/dashpot#11", number=11),
    )


def markdown_issue(directory, number, *, state="open", blocked_by=()):
    closed = state == "closed"
    (directory / f"{number}.md").write_text(
        local_issue_document(
            issue_id=f"I_{number}",
            number=number,
            reference=f"issue-{number}",
            title=f"Issue {number}",
            state=state,
            stateReason="completed" if closed else None,
            closedAt="2026-08-27T00:00:00Z" if closed else None,
            relationships={
                "parent": None,
                "subIssues": [],
                "blockedBy": list(blocked_by),
                "blocking": [],
            },
        )
    )


def test_markdown_ready_judges_blockers_against_the_local_issues(tmp_path):
    source = markdown(tmp_path)
    directory = tmp_path / "issues"
    for path in directory.iterdir():
        path.unlink()
    markdown_issue(directory, 1)
    markdown_issue(directory, 2, state="closed")
    markdown_issue(directory, 3, blocked_by=["I_2"])
    markdown_issue(directory, 4, blocked_by=["I_1", "I_2"])
    markdown_issue(directory, 5, blocked_by=["I_elsewhere"])

    observed = source.query_page(QueryRequest(state="ready"))
    ready = observed.page
    assert ready.status == "fresh", ready.diagnostics
    # Project Totals count the whole Project, waiting Issues included.
    assert (observed.totals.open_count, observed.totals.closed_count) == (4, 1)
    assert [issue.number for issue in ready.issues] == [1, 3]
    assert ready.auxiliary["I_3"].open_blockers == ()

    everything = source.query_page(QueryRequest(state="all")).page
    assert everything.auxiliary["I_4"].open_blockers == (
        OpenBlocker(id="I_1", reference="issue-1", number=1),
    )
    # A blocker no local Issue is counts as open, named by its identity.
    assert everything.auxiliary["I_5"].open_blockers == (OpenBlocker(id="I_elsewhere"),)
    assert everything.auxiliary["I_1"].activity is None


def test_markdown_source_that_cannot_observe_has_no_last_good_page(tmp_path):
    source = markdown(tmp_path)
    assert source.query_page(QueryRequest()).page.status == "fresh"
    for path in (tmp_path / "issues").iterdir():
        path.unlink()
    (tmp_path / "issues").rmdir()
    assert source.query_page(QueryRequest()).page.status == "unavailable"


def _refuse_markdown_collection(tmp_path, refusal):
    """Leave ``markdown(tmp_path)``'s collection in the state ``refusal`` names.

    A refusal the files cannot produce returns the read failure to raise.
    """
    directory = tmp_path / "issues"
    if refusal == "missing":
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
    elif refusal == "outside":
        outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
        outside.write_text(
            local_issue_document(issue_id="I_9", number=9, reference="out", title="Out")
        )
        (directory / "outside.md").symlink_to(outside)
    elif refusal == "malformed":
        (directory / "4.md").write_text("no front matter\n")
    elif refusal == "undecodable":
        (directory / "4.md").write_bytes(b"---\n\xff\n---\n")
    elif refusal == "profile":
        (directory / "4.md").write_text(
            local_issue_document(
                issue_id="I_4", number=4, reference="four", title="Four", state="lost"
            )
        )
    elif refusal in {"duplicate-identity", "duplicate-number"}:
        identity, number = ("I_1", 4) if refusal == "duplicate-identity" else ("I_4", 1)
        (directory / "4.md").write_text(
            local_issue_document(
                issue_id=identity, number=number, reference="four", title="Four"
            )
        )
    elif refusal == "vanished":
        return FileNotFoundError("issues/1.md vanished while it was read")
    elif refusal == "unreadable":
        return PermissionError("permission denied")
    elif refusal == "failing-disk":
        return OSError("Input/output error")
    else:
        raise AssertionError(f"no such refusal: {refusal}")
    return None


@pytest.mark.parametrize(
    ("refusal", "code"),
    [
        ("missing", "markdown-not-found"),
        ("outside", "markdown-path"),
        ("malformed", "markdown-malformed"),
        ("undecodable", "markdown-malformed"),
        ("profile", "markdown-profile"),
        ("duplicate-identity", "markdown-duplicate-identity"),
        ("duplicate-number", "markdown-duplicate-number"),
        ("vanished", "markdown-not-found"),
        ("unreadable", "markdown-permission"),
        ("failing-disk", "markdown-io"),
    ],
)
def test_markdown_pages_and_export_refuse_a_collection_alike(tmp_path, refusal, code):
    # One enumeration serves both paths, so a page reports the code and the
    # message the export reports for the same collection.
    source = markdown(tmp_path)
    failure = _refuse_markdown_collection(tmp_path, refusal)
    exporter = MarkdownQuerySource(tmp_path, load_project_config(tmp_path))

    reading = (
        patch.object(Path, "read_bytes", side_effect=failure)
        if failure
        else nullcontext()
    )
    with reading:
        page = source.query_page(QueryRequest()).page
        export = exporter.enumerate_source("issues")

    assert page.status == export.status == "unavailable"
    assert [(d.code, d.message) for d in page.diagnostics] == [
        (d.code, d.message) for d in export.diagnostics
    ]
    assert page.diagnostics[0].code == code


def test_markdown_pages_and_export_read_a_crlf_document_alike(tmp_path):
    source = markdown(tmp_path)
    (tmp_path / "issues" / "4.md").write_bytes(
        local_issue_document(
            issue_id="I_4",
            number=4,
            reference="four",
            title="Four",
            body="First line.\n\nSecond line.",
        )
        .replace("\n", "\r\n")
        .encode()
    )

    page = source.query_page(QueryRequest(page_size=10)).page
    export = source.enumerate_source("issues")

    paged = {issue.id: issue for issue in page.issues}
    exported = {issue.id: issue for issue in export.issues}
    assert paged == exported
    assert paged["I_4"].body == "First line.\n\nSecond line."


def test_page_failing_after_a_new_principal_never_shows_the_old_one(tmp_path):
    source, runner = github(tmp_path, context(), search(hit(1)), batch(node(1)))
    source.query_page(QueryRequest())
    runner.results = iter(
        [
            completed(json.dumps({"data": search(hit(1), principal="U_2")})),
            OSError("network down"),
        ]
    )
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable" and not page.issues


def test_totals_failing_after_a_new_principal_never_show_the_old_one(tmp_path):
    malformed = search(hit(1), principal="U_2", opened=-1)
    source, _ = github(tmp_path, context(), search(hit(1)), batch(node(1)), malformed)
    source.query_page(QueryRequest())
    result = source.query_page(QueryRequest()).totals
    assert result.status == "unavailable" and result.open_count is None


def test_identities_failing_after_a_new_principal_never_show_the_old_one(tmp_path):
    identities = [f"I_issue_{n}" for n in range(1, 26)]
    source, runner = github(
        tmp_path, batch(*(node(n) for n in range(1, 25))), batch(node(25))
    )
    source.resolve_identities(identities)
    runner.results = iter(
        [
            completed(
                json.dumps(
                    {"data": batch(*(node(n) for n in range(1, 25)), principal="U_2")}
                )
            ),
            OSError("network down"),
        ]
    )
    results = source.resolve_identities(identities)
    assert all(result.context.principal == "U_2" for result in results[:24])
    assert results[24].status == "unavailable" and results[24].issue is None


def test_refused_principal_never_leaves_the_old_page_stale(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        search(hit(1)),
        batch(node(1), principal="U_2"),
    )
    source.query_page(QueryRequest())
    page = source.query_page(QueryRequest()).page
    assert page.status == "unavailable" and not page.issues


def test_refused_continuation_never_leaves_the_old_page_stale(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2),
        batch(node(2)),
        context(),
        search(hit(2), count=2, principal="U_2"),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    later = request.model_copy(update={"cursor": first.next_cursor})
    assert source.query_page(later).page.status == "fresh"
    page = source.query_page(later).page
    assert page.status == "unavailable" and not page.issues
    assert "different principal" in page.diagnostics[0].message


def test_continuation_under_an_edited_configuration_keeps_no_old_page(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2),
        batch(node(2)),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request).page
    later = request.model_copy(update={"cursor": first.next_cursor})
    assert source.query_page(later).page.status == "fresh"
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "github"},
        display_label="Edited",
    )
    runner.results = iter([OSError("network down")])
    assert source.query_page(later).page.status == "unavailable"


def reading(answer, remaining, *, limit=5000, reset_at="2026-09-27T13:00:00Z"):
    """``answer`` with the rate limit GitHub reports beside it."""
    return {
        **answer,
        "rateLimit": {
            "cost": 1,
            "limit": limit,
            "remaining": remaining,
            "resetAt": reset_at,
        },
    }


def test_every_query_a_github_source_sends_selects_the_rate_limit(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2),
        batch(node(2)),
        batch(node(1)),
    )
    first = source.query_page(QueryRequest(page_size=1)).page
    source.query_page(QueryRequest(page_size=1, cursor=first.next_cursor))
    source.resolve_identities(["I_issue_1"])
    queries = arguments(runner, "query=")
    assert {query.split("(")[0] for query in queries} == {
        "query DashpotQueryContext",
        "query DashpotQueryPage",
        "query DashpotResolvedIssues",
    }
    assert all(RATE_LIMIT_SELECTION in query for query in queries)


def test_a_low_rate_limit_warns_from_the_latest_response(tmp_path):
    source, _ = github(
        tmp_path,
        reading(context(), 4000),
        reading(search(hit(1)), 499),
        reading(batch(node(1)), 480),
        reading(batch(node(1)), 470, reset_at="2026-09-27T14:00:00Z"),
        reading(batch(node(1)), 5000, reset_at="2026-09-27T15:00:00Z"),
    )
    assert source.source_diagnostics() == ()
    observation = source.query_page(QueryRequest())
    # The warning is the source's, not the page's: the page reports only
    # what observing it found.
    assert observation.page.status == "fresh" and observation.page.diagnostics == ()
    (warning,) = source.source_diagnostics()
    assert (warning.source, warning.code, warning.severity) == (
        "github",
        "github-rate-limit-low",
        "warning",
    )
    assert "480 of 5000 points remain until 2026-09-27T13:00:00Z" in warning.message
    # A Resolved Issues response is read the same way.
    source.resolve_identities(["I_issue_1"])
    (warning,) = source.source_diagnostics()
    assert "470 of 5000 points remain until 2026-09-27T14:00:00Z" in warning.message
    # The next hour's reading, with its points restored, clears the warning.
    source.resolve_identities(["I_issue_1"])
    assert source.source_diagnostics() == ()


def test_github_sources_sharing_a_reading_warn_from_the_latest_of_any(tmp_path):
    shared = LatestRateLimit()
    pages, _ = github(
        tmp_path,
        reading(context(), 460),
        reading(search(hit(1)), 450),
        reading(batch(node(1)), 440),
        latest_rate_limit=shared,
    )
    identities, _ = github(
        tmp_path, reading(batch(node(1)), 300), latest_rate_limit=shared
    )
    pages.query_page(QueryRequest())
    identities.resolve_identities(["I_issue_1"])
    # Whichever source is asked reports the one most recent reading.
    assert pages.source_diagnostics() == identities.source_diagnostics()
    (warning,) = pages.source_diagnostics()
    assert "300 of 5000 points remain" in warning.message


def test_a_failed_page_still_warns_from_the_reading_before_it(tmp_path):
    source, runner = github(
        tmp_path, reading(context(), 450), reading(search(hit(1)), 440)
    )
    # The Issue batch that completes the page is refused.
    runner.results = iter([*runner.results, OSError("rate limited")])
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "unavailable"
    # The refusal also pauses the source's queries; the warning stays.
    warning, paused = source.source_diagnostics()
    assert "440 of 5000 points remain" in warning.message
    assert paused.code == "github-rate-limit-paused"


def test_a_partial_answer_that_fails_the_page_still_warns_from_its_reading(
    tmp_path,
):
    # The page search is a partial answer: its error fails the page, but the
    # rate limit GitHub reported beside it is still the latest reading.
    source, runner = github(tmp_path, reading(context(), 4000))
    runner.results = iter(
        [
            *runner.results,
            refused(
                reading(search(None), 420),
                {
                    "type": "FORBIDDEN",
                    "path": ["search", "nodes", 0],
                    "message": "not accessible",
                },
            ),
        ]
    )
    observation = source.query_page(QueryRequest())
    assert observation.page.status == "unavailable"
    (warning,) = source.source_diagnostics()
    assert "420 of 5000 points remain" in warning.message


def test_a_rate_limit_refusal_pauses_every_sharing_source_until_the_reset(
    tmp_path,
):
    now = datetime(2026, 9, 27, 12, 30, tzinfo=UTC)
    shared = LatestRateLimit(clock=lambda: now)
    pages, page_runner = github(
        tmp_path,
        reading(context(), 4000),
        reading(search(hit(1)), 40),
        reading(batch(node(1)), 30),
        latest_rate_limit=shared,
    )
    identities, identity_runner = github(tmp_path, latest_rate_limit=shared)
    pages.query_page(QueryRequest())
    page_runner.results = iter(
        [
            refused(
                None,
                {"type": "RATE_LIMITED", "message": "API rate limit already exceeded"},
            )
        ]
    )

    refused_page = pages.query_page(QueryRequest()).page
    held_page = pages.query_page(QueryRequest()).page
    (resolved,) = identities.resolve_identities(["I_issue_1"])

    # One request was refused; nothing was sent after it.
    assert len(page_runner.calls) == 4 and identity_runner.calls == []
    assert [page.status for page in (refused_page, held_page)] == ["stale", "stale"]
    assert resolved.status == "unavailable"
    (held,) = held_page.diagnostics
    assert held.code == resolved.diagnostics[0].code == "github-rate-limit"
    assert "not sent" in held.message
    assert "paused until 2026-09-27T13:00:00Z" in held.message
    # Both sources say so once, beside the low-allowance warning.
    assert pages.source_diagnostics() == identities.source_diagnostics()
    low, paused = pages.source_diagnostics()
    assert (low.code, paused.code) == (
        "github-rate-limit-low",
        "github-rate-limit-paused",
    )
    now = datetime(2026, 9, 27, 13, tzinfo=UTC)
    assert [warning.code for warning in pages.source_diagnostics()] == [
        "github-rate-limit-low"
    ]


def test_markdown_source_reports_no_source_diagnostics(tmp_path):
    source = markdown(tmp_path)
    source.query_page(QueryRequest())
    assert source.source_diagnostics() == ()
