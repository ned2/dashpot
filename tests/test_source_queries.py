"""Exercise page coverage, source scope and portable continuation at the public seam."""

import json

import pytest

from dashpot.github.github import GitHubRequestError
from dashpot.project.project_config import load_project_config
from dashpot.queries.github_queries import GitHubQuerySource, validate_grouping
from dashpot.queries.markdown_queries import MarkdownQuerySource
from dashpot.queries.source_queries import InvalidContinuation, QueryPage, QueryRequest
from factories import (
    SequenceRunner,
    completed,
    local_issue_document,
    write_project_config,
)
from test_github_issues import PROJECT_ID, REPOSITORY_ID, issue_record


def context(principal="U_1", name="ned2/dashpot"):
    return {
        "repository": {"id": REPOSITORY_ID, "nameWithOwner": name},
        "viewer": {"id": principal},
    }


def search(*nodes, count=None, cursor=None, principal="U_1", name="ned2/dashpot"):
    return {
        **context(principal, name),
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


def github(tmp_path, *answers):
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
        tmp_path, load_project_config(tmp_path), runner=runner
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
    page = source.query_page(QueryRequest())
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
    page = source.query_page(QueryRequest(query=expression, state="all"))
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
    page = source.query_page(QueryRequest(query=query))
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
    page = source.query_page(QueryRequest())
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
    assert len(runner.calls) == 1


def test_cross_process_principal_change_rejects_continuation(tmp_path):
    source, _ = github(
        tmp_path, context(), search(hit(1), count=2, cursor="c"), batch(node(1))
    )
    first = source.query_page(QueryRequest(page_size=1))
    other, runner = github(tmp_path, context("U_other"))
    with pytest.raises(InvalidContinuation):
        other.query_page(QueryRequest(page_size=1, cursor=first.next_cursor))
    assert len(runner.calls) == 1


def test_markdown_cross_process_continuation_and_global_sort(tmp_path):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1, ordering="number:desc"))
    assert first.issues[0].number == 3
    second = MarkdownQuerySource(tmp_path, load_project_config(tmp_path)).query_page(
        QueryRequest(page_size=1, ordering="number:desc", cursor=first.next_cursor)
    )
    assert second.issues[0].number == 2
    totals = source.totals("issues")
    assert totals.open_count == 3
    assert source.query_page(QueryRequest(kind="pull-requests")).status == "unavailable"


def test_markdown_orders_only_by_a_sortable_issue_fact(tmp_path):
    source = markdown(tmp_path)

    assert source.supports_sort(QueryRequest(), "created")
    assert not source.supports_sort(QueryRequest(), "title")
    page = source.query_page(QueryRequest(page_size=1, ordering="title:asc"))
    assert page.status == "unavailable"
    assert "Unsupported local column ordering" in page.diagnostics[0].message


@pytest.mark.parametrize("change", ["edit", "rename", "insert", "delete"])
def test_markdown_revision_invalidates_continuation(tmp_path, change):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1))
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
    first = source.query_page(QueryRequest())
    stale = source.query_page(QueryRequest())
    other = source.query_page(QueryRequest(query="label:other"))
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
    first = source.query_page(QueryRequest(page_size=1))
    failed, _ = github(tmp_path, {})
    page = failed.query_page(QueryRequest(page_size=1, cursor=first.next_cursor))
    assert page.status == "unavailable"


def test_provider_limit_is_distinct_from_end(tmp_path):
    from dashpot.queries.source_queries import (
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
    first = source.query_page(request)
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
    last = final.query_page(request.model_copy(update={"cursor": token}))
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
    first = source.query_page(request)
    later = request.model_copy(update={"cursor": first.next_cursor})
    second = source.query_page(later)
    refreshed = source.query_page(later)
    assert second.status == refreshed.status == "fresh"
    assert refreshed.matched_count == 4


def test_changed_source_config_rejects_continuation(tmp_path):
    source = markdown(tmp_path)
    first = source.query_page(QueryRequest(page_size=1))
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
    page = source.query_page(QueryRequest())
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
    page = source.query_page(QueryRequest())
    assert page.status == "fresh"
    assert page.issues[0].relationships.sub_issues == ("related-1", "related-2")
    assert len(runner.calls) == 4
    limited, runner = github(tmp_path, context(), search(hit(1)), batch(first))
    limited.budget = RefreshBudget(requests=3, seconds=60)
    failure = limited.query_page(QueryRequest())
    assert failure.status == "unavailable" and not failure.issues
    assert len(runner.calls) == 3


def test_single_record_page_sizes_can_carry_full_search_cursor_history():
    from dashpot.queries.source_queries import (
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
        result = source.query_page(QueryRequest())
    elif operation == "totals":
        result = source.totals("issues")
    else:
        (result,) = source.resolve_identities(["I_1"])
    assert result.status == "unavailable"
    assert "cannot observe" in result.diagnostics[0].message


@pytest.mark.parametrize("operation", ["page", "totals", "identities"])
def test_query_programmer_faults_escape_instead_of_becoming_stale(tmp_path, operation):
    source, runner = github(tmp_path)
    runner.results = iter([AssertionError("adapter invariant")])
    with pytest.raises(AssertionError, match="adapter invariant"):
        if operation == "page":
            source.query_page(QueryRequest())
        elif operation == "totals":
            source.totals("issues")
        else:
            source.resolve_identities(["I_1"])


def operations(runner):
    """The GraphQL operation each recorded ``gh`` call sent, in order."""
    return [
        argument.removeprefix("query=query ").split("(")[0]
        for args, *_ in runner.calls
        for argument in args
        if argument.startswith("query=query ")
    ]


def test_repeated_page_one_verifies_context_in_its_own_response(tmp_path):
    source, runner = github(
        tmp_path,
        context(),
        search(hit(1)),
        batch(node(1)),
        search(hit(1), principal="U_2"),
        batch(node(1), principal="U_2"),
    )
    first = source.query_page(QueryRequest())
    again = source.query_page(QueryRequest())
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
    first = source.query_page(QueryRequest())
    refused = source.query_page(QueryRequest())
    assert refused.status == "stale" and refused.issues == first.issues
    assert "different Repository Identity" in refused.diagnostics[0].message


def test_page_batch_answering_another_principal_rejects_the_page(tmp_path):
    source, _ = github(
        tmp_path, context(), search(hit(1)), batch(node(1), principal="U_2")
    )
    page = source.query_page(QueryRequest())
    assert page.status == "unavailable" and not page.issues


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
    first = source.query_page(request)
    second = source.query_page(request.model_copy(update={"cursor": first.next_cursor}))
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
    page = source.query_page(QueryRequest())
    assert page.status == "fresh" and page.returned_count == 1
    searches = [
        argument
        for args, *_ in runner.calls
        for argument in args
        if argument.startswith("searchQuery=")
    ]
    assert searches == [
        "searchQuery=repo:ned2/dashpot is:issue is:open",
        "searchQuery=repo:ned2/dashpot is:issue is:open",
        "searchQuery=repo:ned2/renamed is:issue is:open",
    ]


def test_repository_renamed_again_during_its_retry_fails_the_page(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(name="ned2/renamed"),
        search(name="ned2/renamed-again"),
    )
    page = source.query_page(QueryRequest())
    assert page.status == "unavailable"
    assert "renamed" in page.diagnostics[0].message


def test_continuation_across_a_rename_restarts_from_page_one(tmp_path):
    source, _ = github(
        tmp_path,
        context(),
        search(hit(1), count=2, cursor="c1"),
        batch(node(1)),
        context(),
        search(hit(2), count=2, name="ned2/renamed"),
    )
    request = QueryRequest(page_size=1)
    first = source.query_page(request)
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
    page = source.query_page(QueryRequest())
    assert page.status == "unavailable"
    assert "configuration changed" in page.diagnostics[0].message
    assert len(runner.calls) == 3


def totals(opened, closed, principal="U_1"):
    return {
        **context(principal),
        "totals": {
            "opened": {"totalCount": opened},
            "closed": {"totalCount": closed},
        },
    }


def test_totals_verify_their_context_in_one_request(tmp_path):
    source, runner = github(tmp_path, totals(3, 5))
    result = source.totals("issues")
    assert result.status == "fresh"
    assert (result.open_count, result.closed_count) == (3, 5)
    assert result.context.principal == "U_1"
    assert operations(runner) == ["DashpotProjectTotals"]


def test_totals_answering_another_repository_are_refused(tmp_path):
    other = totals(3, 5)
    other["repository"] = {"id": "R_elsewhere", "nameWithOwner": "other/repo"}
    source, _ = github(tmp_path, other)
    result = source.totals("issues")
    assert result.status == "unavailable" and result.open_count is None


def test_failed_totals_keep_their_last_good_counts(tmp_path):
    source, runner = github(tmp_path, totals(3, 5))
    source.totals("issues")
    runner.results = iter([OSError("network down")])
    stale = source.totals("issues")
    assert stale.status == "stale"
    assert (stale.open_count, stale.closed_count) == (3, 5)


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
        totals(3, 5),
        batch(node(1)),
    )
    page = source.query_page(QueryRequest())
    source.totals("issues")
    source.resolve_identities(["I_issue_1"])
    (tmp_path / ".dashpot" / "config.json").write_text("{")
    # The request never starts, so nothing about the context is disproved.
    stale_page = source.query_page(QueryRequest())
    stale_totals = source.totals("issues")
    (stale_issue,) = source.resolve_identities(["I_issue_1"])
    assert stale_page.status == "stale" and stale_page.issues == page.issues
    assert stale_totals.status == "stale" and stale_totals.open_count == 3
    assert stale_issue.status == "stale" and stale_issue.outcome == "unavailable"
    assert len(runner.calls) == 5


def test_column_ordering_becomes_the_search_sort_qualifier(tmp_path):
    source, runner = github(tmp_path, context(), search())
    page = source.query_page(QueryRequest(ordering="created:desc"))
    assert page.status == "fresh"
    assert (
        "searchQuery=repo:ned2/dashpot is:issue is:open sort:created-desc"
        in runner.calls[1][0]
    )
    refused = source.query_page(QueryRequest(ordering="title:asc"))
    assert "no exact GitHub source ordering" in refused.diagnostics[0].message
    assert len(runner.calls) == 2


def test_markdown_source_that_cannot_observe_has_no_last_good_page(tmp_path):
    source = markdown(tmp_path)
    assert source.query_page(QueryRequest()).status == "fresh"
    for path in (tmp_path / "issues").iterdir():
        path.unlink()
    (tmp_path / "issues").rmdir()
    assert source.query_page(QueryRequest()).status == "unavailable"
