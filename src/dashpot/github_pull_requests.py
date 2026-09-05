"""Observe GitHub Pull Requests as one bounded complete collection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, HttpUrl, ValidationError
from typing_extensions import override

from .commands import CommandRunner, run_command
from .github import (
    DEFAULT_REFRESH_BUDGET,
    RATE_LIMIT_SELECTION,
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    RefreshBudget,
)
from .model import (
    PullRequest,
    PullRequestCheckStatus,
    PullRequestMergeability,
    PullRequestReviewDecision,
    PullRequestState,
)
from .models import ConfigModel, LaxSequence, NonEmptyString, Rfc3339Timestamp
from .pull_request_sources import (
    Clock,
    CollectedPullRequests,
    PullRequestSource,
    PullRequestSourceDiagnostic,
    PullRequestSourceRefreshError,
)

_STATES: Mapping[str, PullRequestState] = {
    "OPEN": "open",
    "CLOSED": "closed",
    "MERGED": "merged",
}

_PAGE_SIZE = 100
_RESPONSE_CODE = "github-malformed-response"

_REVIEW_DECISIONS: Mapping[str, PullRequestReviewDecision] = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes-requested",
    "REVIEW_REQUIRED": "review-required",
}
_CHECK_STATUSES: Mapping[str, PullRequestCheckStatus] = {
    "ERROR": "error",
    "EXPECTED": "expected",
    "FAILURE": "failure",
    "PENDING": "pending",
    "SUCCESS": "success",
}
_MERGEABILITY: Mapping[str, PullRequestMergeability | None] = {
    "CONFLICTING": "conflicting",
    "MERGEABLE": "mergeable",
    "UNKNOWN": None,
}

_PULL_REQUESTS_QUERY = f"""
query DashpotPullRequests($repositoryId: ID!, $cursor: String) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      pullRequests(
        first: {_PAGE_SIZE}
        after: $cursor
        states: [OPEN, CLOSED, MERGED]
        orderBy: {{field: CREATED_AT, direction: ASC}}
      ) {{
        totalCount
        nodes {{
          id
          number
          title
          url
          state
          isDraft
          headRefName
          baseRefName
          author {{ login }}
          reviewDecision
          statusCheckRollup {{ state }}
          mergeable
          createdAt
          updatedAt
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}
""".strip()


class _Actor(ConfigModel):
    login: NonEmptyString


class _StatusCheckRollup(ConfigModel):
    state: Literal["ERROR", "EXPECTED", "FAILURE", "PENDING", "SUCCESS"]


class _PullRequestNode(ConfigModel):
    id: NonEmptyString
    number: int = Field(gt=0)
    title: NonEmptyString
    url: HttpUrl
    state: Literal["OPEN", "CLOSED", "MERGED"]
    is_draft: bool
    head_ref_name: NonEmptyString
    base_ref_name: NonEmptyString
    author: _Actor | None
    review_decision: Literal["APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"] | None
    status_check_rollup: _StatusCheckRollup | None
    mergeable: Literal["CONFLICTING", "MERGEABLE", "UNKNOWN"]
    created_at: Rfc3339Timestamp
    updated_at: Rfc3339Timestamp


class _PageInfo(ConfigModel):
    has_next_page: bool
    end_cursor: str | None


class _PullRequestConnection(ConfigModel):
    total_count: int = Field(ge=0)
    nodes: LaxSequence[_PullRequestNode]
    page_info: _PageInfo


class _RepositoryPage(ConfigModel):
    id: NonEmptyString
    pull_requests: _PullRequestConnection


def normalize_github_pull_request(record: Mapping[str, Any]) -> PullRequest:
    """Validate one GitHub node and publish its compact Pull Request facts."""
    try:
        node = _PullRequestNode.model_validate(record)
    except ValidationError as exc:
        raise PullRequestSourceRefreshError(
            _RESPONSE_CODE, f"GitHub Pull Request is malformed: {exc}"
        ) from exc
    review = (
        _REVIEW_DECISIONS[node.review_decision]
        if node.review_decision is not None
        else None
    )
    checks = (
        _CHECK_STATUSES[node.status_check_rollup.state]
        if node.status_check_rollup is not None
        else None
    )
    mergeability = _MERGEABILITY[node.mergeable]
    return PullRequest(
        id=node.id,
        number=node.number,
        title=node.title,
        url=str(node.url),
        state=_STATES[node.state],
        is_draft=node.is_draft,
        head_branch=node.head_ref_name,
        base_branch=node.base_ref_name,
        author=node.author.login if node.author is not None else None,
        review_decision=review,
        check_status=checks,
        mergeability=mergeability,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


class GitHubPullRequestsSource(PullRequestSource):
    """Collect every Pull Request of one configured GitHub repository."""

    def __init__(
        self,
        root: Path,
        *,
        repository_id: str,
        timeout: float = 10,
        runner: CommandRunner = run_command,
        clock: Clock | None = None,
        budget: RefreshBudget = DEFAULT_REFRESH_BUDGET,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.repository_id = repository_id
        self.gateway = GitHubGateway(root, timeout=timeout, runner=runner)
        self.budget = budget
        self.monotonic = monotonic

    @property
    @override
    def name(self) -> str:
        return "github-pull-requests"

    @override
    def _collect(self) -> CollectedPullRequests:
        meter = (
            self.budget.start(self.monotonic) if self.monotonic else self.budget.start()
        )
        records: list[_PullRequestNode] = []
        total_count: int | None = None
        cursor: str | None = None
        trail = CursorTrail("Pull Request collection")
        try:
            while True:
                variables: dict[str, str | int | Sequence[str]] = {
                    "repositoryId": self.repository_id
                }
                if cursor is not None:
                    variables["cursor"] = cursor
                meter.next_request(f"{len(records)} Pull Requests")
                data = self.gateway.graphql(_PULL_REQUESTS_QUERY, variables)
                repository = self._repository_page(data)
                connection = repository.pull_requests
                if total_count is not None and connection.total_count != total_count:
                    raise PullRequestSourceRefreshError(
                        "github-pull-request-count",
                        "GitHub Pull Request count changed during collection; retry refresh",
                    )
                total_count = connection.total_count
                records.extend(connection.nodes)
                page = repository.pull_requests.page_info
                if not page.has_next_page:
                    break
                cursor = trail.follow(page.end_cursor)
        except GitHubRequestError as exc:
            raise PullRequestSourceRefreshError(exc.code, str(exc)) from exc
        if len(records) != total_count:
            raise PullRequestSourceRefreshError(
                "github-pull-request-count",
                f"GitHub reported {total_count} Pull Requests but returned {len(records)}; "
                "retry refresh",
            )
        pull_requests = tuple(
            normalize_github_pull_request(record.model_dump(by_alias=True, mode="json"))
            for record in records
        )
        pull_requests = tuple(
            sorted(pull_requests, key=lambda pull_request: pull_request.number)
        )
        pull_requests = tuple(
            sorted(
                pull_requests,
                key=lambda pull_request: pull_request.updated_at,
                reverse=True,
            )
        )
        diagnostics = self._rate_limit_diagnostics()
        return CollectedPullRequests(pull_requests, diagnostics)

    def _repository_page(self, data: Mapping[str, Any]) -> _RepositoryPage:
        node = data.get("node")
        if node is None:
            raise PullRequestSourceRefreshError(
                "github-repository",
                f"GitHub Repository identity {self.repository_id} was not found",
            )
        try:
            repository = _RepositoryPage.model_validate(node)
        except ValidationError as exc:
            raise PullRequestSourceRefreshError(
                _RESPONSE_CODE, f"GitHub Pull Request page is malformed: {exc}"
            ) from exc
        if repository.id != self.repository_id:
            raise PullRequestSourceRefreshError(
                "github-repository",
                f"GitHub answered Repository identity {repository.id} for configured "
                f"identity {self.repository_id}",
            )
        return repository

    def _rate_limit_diagnostics(self) -> tuple[PullRequestSourceDiagnostic, ...]:
        rate_limit = self.gateway.rate_limit
        if rate_limit is None or not rate_limit.low:
            return ()
        return (
            PullRequestSourceDiagnostic(
                source=self.name,
                code="github-rate-limit-low",
                severity="warning",
                message=(
                    f"GitHub GraphQL rate limit is low: {rate_limit.remaining} of "
                    f"{rate_limit.limit} points remain until {rate_limit.reset_at}; "
                    f"the last request cost {rate_limit.cost}"
                ),
            ),
        )
