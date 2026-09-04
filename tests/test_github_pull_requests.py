"""GitHub Pull Request observation through the bounded gateway seam."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dashpot.github import RefreshBudget
from dashpot.github_pull_requests import (
    GitHubPullRequestsSource,
    normalize_github_pull_request,
)
from dashpot.pull_request_sources import PullRequestSourceRefreshError
from factories import SequenceRunner, completed

NOW = "2026-09-04T04:00:00Z"


def pull_request_node(number: int = 83, **updates: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": f"PR_{number}",
        "number": number,
        "title": "Add a Pull Requests pane",
        "url": f"https://github.com/ned2/dashpot/pull/{number}",
        "state": "OPEN",
        "isDraft": False,
        "headRefName": "83-pull-requests",
        "baseRefName": "main",
        "author": {"login": "ned2"},
        "reviewDecision": "REVIEW_REQUIRED",
        "statusCheckRollup": {"state": "PENDING"},
        "mergeable": "UNKNOWN",
        "createdAt": "2026-09-01T00:00:00Z",
        "updatedAt": NOW,
    }
    node.update(updates)
    return node


def page(
    *nodes: dict[str, Any],
    has_next: bool = False,
    cursor: str | None = None,
    remaining: int = 4000,
) -> str:
    return json.dumps(
        {
            "data": {
                "rateLimit": {
                    "cost": 1,
                    "limit": 5000,
                    "remaining": remaining,
                    "resetAt": "2026-09-04T05:00:00Z",
                },
                "node": {
                    "id": "R_1",
                    "pullRequests": {
                        "nodes": list(nodes),
                        "pageInfo": {
                            "hasNextPage": has_next,
                            "endCursor": cursor,
                        },
                    },
                },
            }
        }
    )


def source(
    *answers: str,
    budget: RefreshBudget | None = None,
    clock: Callable[[], str] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> tuple[GitHubPullRequestsSource, SequenceRunner]:
    runner = SequenceRunner(*(completed(answer) for answer in answers))
    pull_requests = GitHubPullRequestsSource(
        Path("/repo"),
        repository_id="R_1",
        runner=runner,
        budget=budget or RefreshBudget(),
        clock=clock or (lambda: NOW),
        monotonic=monotonic or (lambda: 0.0),
    )
    return pull_requests, runner


def test_normalizes_every_published_fact_and_explicit_unknowns() -> None:
    observed = normalize_github_pull_request(pull_request_node())

    assert observed.id == "PR_83"
    assert observed.number == 83
    assert observed.state == "open"
    assert observed.is_draft is False
    assert observed.head_branch == "83-pull-requests"
    assert observed.base_branch == "main"
    assert observed.author == "ned2"
    assert observed.review_decision == "review-required"
    assert observed.check_status == "pending"
    assert observed.mergeability is None
    assert observed.created_at == "2026-09-01T00:00:00Z"
    assert observed.updated_at == NOW


@pytest.mark.parametrize(
    ("updates", "review", "checks", "mergeability"),
    [
        (
            {
                "author": None,
                "reviewDecision": None,
                "statusCheckRollup": None,
                "mergeable": "MERGEABLE",
            },
            None,
            None,
            "mergeable",
        ),
        (
            {
                "reviewDecision": "CHANGES_REQUESTED",
                "statusCheckRollup": {"state": "FAILURE"},
                "mergeable": "CONFLICTING",
            },
            "changes-requested",
            "failure",
            "conflicting",
        ),
    ],
)
def test_normalizes_nullable_and_blocking_states(
    updates: dict[str, Any],
    review: str | None,
    checks: str | None,
    mergeability: str | None,
) -> None:
    observed = normalize_github_pull_request(pull_request_node(**updates))

    assert observed.review_decision == review
    assert observed.check_status == checks
    assert observed.mergeability == mergeability


@pytest.mark.parametrize(
    "mutation",
    [
        lambda node: node.pop("title"),
        lambda node: node.update(number=True),
        lambda node: node.update(state="CLOSED"),
        lambda node: node.update(mergeable="NEW_ENUM_VALUE"),
        lambda node: node.update(unrequested="surprise"),
    ],
)
def test_strict_normalization_rejects_incomplete_or_unexpected_nodes(mutation) -> None:
    node = copy.deepcopy(pull_request_node())
    mutation(node)

    with pytest.raises(PullRequestSourceRefreshError) as caught:
        normalize_github_pull_request(node)

    assert caught.value.code == "github-malformed-response"


def test_collects_every_page_and_orders_newest_first() -> None:
    first = pull_request_node(1, updatedAt="2026-09-03T00:00:00Z")
    second = pull_request_node(2, updatedAt="2026-09-04T00:00:00Z")
    pull_requests, runner = source(
        page(first, has_next=True, cursor="c1"), page(second)
    )

    observation = pull_requests.refresh()

    assert observation.status == "fresh"
    assert [item.number for item in observation.pull_requests] == [2, 1]
    assert len(runner.calls) == 2
    assert not any(argument == "cursor=c1" for argument in runner.calls[0][0])
    assert any(argument == "cursor=c1" for argument in runner.calls[1][0])


@pytest.mark.parametrize(
    "answers",
    [
        (page(has_next=True, cursor=None),),
        (
            page(has_next=True, cursor="same"),
            page(has_next=True, cursor="same"),
        ),
    ],
)
def test_missing_or_repeated_cursor_fails_without_publishing_partial_data(
    answers: tuple[str, ...],
) -> None:
    pull_requests, _runner = source(*answers)

    observation = pull_requests.refresh()

    assert observation.status == "unavailable"
    assert observation.pull_requests == ()
    assert observation.diagnostics[0].code == "github-pagination"


def test_budget_exhaustion_retains_the_last_good_collection() -> None:
    ticks = iter(["2026-09-04T04:00:00Z", "2026-09-04T04:01:00Z"])
    pull_requests, _runner = source(
        page(pull_request_node()),
        page(pull_request_node(), has_next=True, cursor="next"),
        budget=RefreshBudget(seconds=60, requests=1),
        clock=lambda: next(ticks),
    )

    first = pull_requests.refresh()
    second = pull_requests.refresh()

    assert first.status == "fresh"
    assert second.status == "stale"
    assert second.pull_requests == first.pull_requests
    assert second.last_good_at == first.last_good_at
    assert second.attempted_at > first.attempted_at
    assert second.diagnostics[0].code == "github-refresh-budget"


def test_time_budget_exhaustion_never_publishes_a_partial_collection() -> None:
    ticks = iter((0.0, 0.0, 61.0))
    pull_requests, runner = source(
        page(pull_request_node(), has_next=True, cursor="next"),
        budget=RefreshBudget(seconds=60, requests=10),
        monotonic=lambda: next(ticks),
    )

    observation = pull_requests.refresh()

    assert observation.status == "unavailable"
    assert observation.pull_requests == ()
    assert observation.diagnostics[0].code == "github-refresh-budget"
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    ("first", "second", "code"),
    [
        (pull_request_node(1), pull_request_node(2, id="PR_1"), "identity"),
        (pull_request_node(1), pull_request_node(1, id="PR_other"), "number"),
    ],
)
def test_duplicate_identity_or_number_invalidates_the_complete_collection(
    first: dict[str, Any], second: dict[str, Any], code: str
) -> None:
    pull_requests, _runner = source(page(first, second))

    observation = pull_requests.refresh()

    assert observation.status == "unavailable"
    assert observation.pull_requests == ()
    assert observation.diagnostics[0].code == f"github-duplicate-{code}"


def test_empty_collection_is_fresh_and_low_rate_limit_is_a_warning() -> None:
    pull_requests, _runner = source(page(remaining=100))

    observation = pull_requests.refresh()

    assert observation.status == "fresh"
    assert observation.pull_requests == ()
    assert observation.diagnostics[0].code == "github-rate-limit-low"


def test_wrong_repository_identity_is_unavailable() -> None:
    answer = json.loads(page())
    answer["data"]["node"]["id"] = "R_other"
    pull_requests, _runner = source(json.dumps(answer))

    observation = pull_requests.refresh()

    assert observation.status == "unavailable"
    assert observation.diagnostics[0].code == "github-repository"
