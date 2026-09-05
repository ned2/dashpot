"""Complete advanced Pull Request search through fake GitHub responses."""

from __future__ import annotations

import json

import pytest

import factories
from dashpot.github import RefreshBudget
from dashpot.github_pull_request_search import GitHubPullRequestSearcher
from dashpot.pull_request_sources import PullRequestSourceRefreshError
from test_github_pull_requests import pull_request_node


def page(*nodes, count=None, cursor=None, has_next=False):
    return json.dumps(
        {
            "data": {
                "search": {
                    "issueCount": len(nodes) if count is None else count,
                    "nodes": [dict(node, repository={"id": "R_1"}) for node in nodes],
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                }
            }
        }
    )


def setup_search(tmp_path, *answers, budget=None):
    factories.write_project_config(
        tmp_path,
        project_id="project:one",
        repository_id="R_1",
        issue_source={"kind": "github"},
    )
    project = factories.project("project:one").model_copy(
        update={"primary_anchor": str(tmp_path), "repository_id": "R_1"}
    )
    repository = json.dumps(
        {"data": {"node": {"id": "R_1", "nameWithOwner": "owner/repo"}}}
    )
    runner = factories.SequenceRunner(
        *(factories.completed(answer) for answer in (repository, *answers))
    )
    search = GitHubPullRequestSearcher(
        runner=runner, budget=budget or RefreshBudget(), monotonic=lambda: 0.0
    )
    return search, runner, project


def test_forwards_advanced_operators_and_preserves_github_order(tmp_path):
    search, runner, project = setup_search(
        tmp_path,
        page(pull_request_node(8, state="MERGED"), count=2, has_next=True, cursor="c1"),
        page(pull_request_node(2, isDraft=True), count=2),
    )
    query = '(label:"bug fix" OR team-review-requested:org/team) -draft:false comments:>2 sort:reactions-desc'
    observed = search(project, query)
    assert [pr.number for pr in observed] == [8, 2]
    assert [pr.state for pr in observed] == ["merged", "open"]
    args = runner.calls[1][0]
    assert f"searchQuery=repo:owner/repo is:pr ({query})" in args
    assert any("type: ISSUE_ADVANCED" in arg for arg in args)
    assert sum(arg.startswith("query=") for arg in args) == 1
    assert "cursor=c1" in runner.calls[2][0]


@pytest.mark.parametrize(
    ("answers", "code"),
    [
        ((page(count=1001),), "github-search-limit"),
        ((page(pull_request_node(), count=2),), "github-search-count"),
        (
            (
                page(pull_request_node(), count=2, has_next=True, cursor="c"),
                page(pull_request_node(2), count=3),
            ),
            "github-search-count",
        ),
        ((page(pull_request_node(), pull_request_node()),), "github-search-duplicate"),
        ((page(has_next=True, cursor=None),), "github-pagination"),
        (
            (page(has_next=True, cursor="same"), page(has_next=True, cursor="same")),
            "github-pagination",
        ),
        ((page(pull_request_node(state="UNEXPECTED")),), "github-malformed-response"),
    ],
)
def test_never_returns_partial_or_malformed_searches(tmp_path, answers, code):
    search, _, project = setup_search(tmp_path, *answers)
    with pytest.raises(PullRequestSourceRefreshError) as error:
        search(project, "draft:true")
    assert error.value.code == code


def test_budget_includes_identity_and_every_search_page(tmp_path):
    search, runner, project = setup_search(
        tmp_path,
        page(pull_request_node(), has_next=True, cursor="next", count=2),
        budget=RefreshBudget(requests=2, seconds=60),
    )
    with pytest.raises(PullRequestSourceRefreshError) as error:
        search(project, "author:@me")
    assert error.value.code == "github-refresh-budget"
    assert len(runner.calls) == 2


def test_refuses_results_from_another_repository(tmp_path):
    response = json.loads(page(pull_request_node()))
    response["data"]["search"]["nodes"][0]["repository"]["id"] = "R_other"
    search, _, project = setup_search(tmp_path, json.dumps(response))
    with pytest.raises(PullRequestSourceRefreshError) as error:
        search(project, "repo:other/repo OR draft:true")
    assert error.value.code == "github-repository"


def test_local_markdown_never_inferrs_github_search_from_remotes(tmp_path):
    search, runner, project = setup_search(tmp_path)
    factories.write_project_config(
        tmp_path, project_id="project:one", repository_id="R_1"
    )
    with pytest.raises(PullRequestSourceRefreshError) as error:
        search(project, "draft:true")
    assert error.value.code == "pull-request-search-not-configured"
    assert runner.calls == []


@pytest.mark.parametrize(
    "query",
    [
        "draft:true) OR repo:elsewhere/repo (",
        'label:"unterminated',
        "(draft:true",
        "author:ned\\",
    ],
)
def test_rejects_unbalanced_expression_before_it_can_escape_repository_scope(
    tmp_path, query
):
    search, runner, project = setup_search(tmp_path)
    with pytest.raises(PullRequestSourceRefreshError) as error:
        search(project, query)
    assert error.value.code == "github-search-syntax"
    assert runner.calls == []


def test_quoted_parentheses_stay_literal_in_scope_validation(tmp_path):
    search, runner, project = setup_search(tmp_path, page())
    assert search(project, 'label:"bug (parser"') == ()
    assert len(runner.calls) == 2


def test_apostrophes_in_words_do_not_open_quoted_groups(tmp_path):
    search, runner, project = setup_search(tmp_path, page())
    assert search(project, "don't") == ()
    assert len(runner.calls) == 2
