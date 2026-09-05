"""Delegate Pull Request search syntax to GitHub within one Project."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import Field, ValidationError

from .commands import CommandRunner, run_command
from .github import (
    DEFAULT_REFRESH_BUDGET,
    RATE_LIMIT_SELECTION,
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    RefreshBudget,
)
from .github_pull_requests import normalize_github_pull_request
from .model import ProjectObservation, PullRequest
from .models import ConfigModel, LaxSequence, NonEmptyString
from .project_config import GitHubIssueSourceConfig, load_project_config
from .pull_request_sources import PullRequestSourceRefreshError


class PullRequestSearcher(Protocol):
    def __call__(
        self, project: ProjectObservation, text: str
    ) -> tuple[PullRequest, ...]:
        """Return every matching Pull Request in GitHub's search order."""
        ...


_REPOSITORY_QUERY = """
query DashpotSearchRepository($repositoryId: ID!) {
  node(id: $repositoryId) { ... on Repository { id nameWithOwner } }
}
""".strip()

_SEARCH_QUERY = f"""
query DashpotPullRequestSearch($searchQuery: String!, $cursor: String) {{
  {RATE_LIMIT_SELECTION}
  search(query: $searchQuery, type: ISSUE_ADVANCED, first: 100, after: $cursor) {{
    issueCount
    nodes {{
      ... on PullRequest {{
        id number title url state isDraft headRefName baseRefName
        author {{ login }}
        reviewDecision
        statusCheckRollup {{ state }}
        mergeable createdAt updatedAt
        repository {{ id }}
      }}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
""".strip()


class _Repository(ConfigModel):
    id: NonEmptyString
    name_with_owner: NonEmptyString


class _RepositoryResponse(ConfigModel):
    node: _Repository


class _PageInfo(ConfigModel):
    has_next_page: bool
    end_cursor: str | None


class _RepositoryIdentity(ConfigModel):
    id: NonEmptyString


class _SearchConnection(ConfigModel):
    issue_count: int = Field(ge=0)
    nodes: LaxSequence[dict[str, object]]
    page_info: _PageInfo


class GitHubPullRequestSearcher:
    """Search the configured Repository through GitHub's advanced parser."""

    def __init__(
        self,
        *,
        timeout: float = 10,
        runner: CommandRunner = run_command,
        budget: RefreshBudget = DEFAULT_REFRESH_BUDGET,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.timeout = timeout
        self.runner = runner
        self.budget = budget
        self.monotonic = monotonic

    def __call__(
        self, project: ProjectObservation, text: str
    ) -> tuple[PullRequest, ...]:
        """Observe a complete GitHub search scoped to the configured Repository."""
        _validate_grouping(text)
        root = Path(project.primary_anchor)
        config = load_project_config(root)
        if (
            not isinstance(config.issue_source, GitHubIssueSourceConfig)
            or config.repository_id != project.repository_id
            or config.project_id != project.project_id
        ):
            raise PullRequestSourceRefreshError(
                "pull-request-search-not-configured",
                "Pull Request search requires this Project's configured GitHub Repository",
            )
        gateway = GitHubGateway(root, timeout=self.timeout, runner=self.runner)
        meter = (
            self.budget.start(self.monotonic) if self.monotonic else self.budget.start()
        )
        try:
            meter.next_request("Repository identity")
            repository = _RepositoryResponse.model_validate(
                gateway.graphql(
                    _REPOSITORY_QUERY, {"repositoryId": project.repository_id}
                )
            ).node
            if repository.id != project.repository_id:
                raise PullRequestSourceRefreshError(
                    "github-repository",
                    "GitHub answered a different Repository identity",
                )
            query = f"repo:{repository.name_with_owner} is:pr ({text})"
            return self._search(
                gateway, meter.next_request, project.repository_id, query
            )
        except GitHubRequestError as exc:
            raise PullRequestSourceRefreshError(exc.code, str(exc)) from exc
        except ValidationError as exc:
            raise PullRequestSourceRefreshError(
                "github-malformed-response",
                f"GitHub Pull Request search is malformed: {exc}",
            ) from exc

    @staticmethod
    def _search(
        gateway: GitHubGateway,
        next_request: Callable[[str], None],
        repository_id: str,
        query: str,
    ) -> tuple[PullRequest, ...]:
        records: list[PullRequest] = []
        identities: set[str] = set()
        numbers: set[int] = set()
        count: int | None = None
        cursor: str | None = None
        trail = CursorTrail("Pull Request search")
        while True:
            next_request(f"{len(records)} matching Pull Requests")
            variables = {"searchQuery": query}
            if cursor is not None:
                variables["cursor"] = cursor
            data = gateway.graphql(_SEARCH_QUERY, variables)
            connection = _SearchConnection.model_validate(data.get("search"))
            if connection.issue_count > 1000:
                raise PullRequestSourceRefreshError(
                    "github-search-limit",
                    "GitHub search returns at most 1,000 results; narrow the Pull Request query",
                )
            if count is not None and connection.issue_count != count:
                raise PullRequestSourceRefreshError(
                    "github-search-count",
                    "GitHub search count changed during collection; retry search",
                )
            count = connection.issue_count
            for raw in connection.nodes:
                record = dict(raw)
                repository = _RepositoryIdentity.model_validate(
                    record.pop("repository", None)
                )
                if repository.id != repository_id:
                    raise PullRequestSourceRefreshError(
                        "github-repository",
                        "GitHub search returned a Pull Request from another Repository",
                    )
                pr = normalize_github_pull_request(record)
                if pr.id in identities or pr.number in numbers:
                    raise PullRequestSourceRefreshError(
                        "github-search-duplicate",
                        "GitHub search returned a duplicate Pull Request; retry search",
                    )
                identities.add(pr.id)
                numbers.add(pr.number)
                records.append(pr)
            if not connection.page_info.has_next_page:
                break
            cursor = trail.follow(connection.page_info.end_cursor)
        if len(records) != count:
            raise PullRequestSourceRefreshError(
                "github-search-count",
                "GitHub search returned an incomplete collection; retry search",
            )
        return tuple(records)


def _validate_grouping(text: str) -> None:
    """Keep the submitted expression inside the Repository scope wrapper."""
    depth = 0
    quote: str | None = None
    escaped = False
    for character in text:
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif quote is not None:
            if character == quote:
                quote = None
        elif character == '"':
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                break
    if depth != 0 or quote is not None or escaped:
        raise PullRequestSourceRefreshError(
            "github-search-syntax",
            "Close every quote and parenthesis before submitting the Pull Request search",
        )
