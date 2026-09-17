"""Build the Issue Source and Pull Request source a Project's configuration declares.

The module every source consumer goes through, so a configured kind is
interpreted the same way at every seam and the coordinator and Issue
resolution build the same source without either importing the other.
"""

from __future__ import annotations

from pathlib import Path

from ..core.git import Git
from ..github.github_issues import GitHubIssuesSource
from ..github.github_pull_requests import GitHubPullRequestsSource
from ..github.github_repository import github_repo_from_remote
from ..project.project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    ProjectConfig,
)
from .issue_sources import IssueSource
from .local_markdown_issues import LocalMarkdownIssuesSource
from .pull_request_sources import (
    PullRequestSource,
    UnconfiguredPullRequestSource,
)


def build_issue_source(
    root: Path,
    config: ProjectConfig,
    *,
    timeout: float,
    git: Git | None = None,
) -> IssueSource:
    """Build the Issue Source the Project's configuration declares.

    ``git`` reuses a caller's adapter for the origin-remote check instead of
    probing again.
    """
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        if not github_repo_from_remote(root, git):
            raise RuntimeError(
                "A GitHub Issue Source requires the Repository Anchor to have "
                "a GitHub origin remote"
            )
        return GitHubIssuesSource(
            root,
            project_id=config.project_id,
            repository_id=config.repository_id,
            timeout=timeout,
        )
    if isinstance(config.issue_source, LocalMarkdownIssueSourceConfig):
        return LocalMarkdownIssuesSource(
            root,
            project_id=config.project_id,
            issues_path=Path(config.issue_source.path),
        )
    raise RuntimeError(  # pragma: no cover - exhaustive guard for future kinds.
        "unsupported configured Issue Source"
    )


def build_pull_request_source(
    root: Path,
    config: ProjectConfig,
    *,
    timeout: float,
) -> PullRequestSource | UnconfiguredPullRequestSource:
    """Build the Project's GitHub source or its honest unconfigured result."""
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        return GitHubPullRequestsSource(
            root,
            repository_id=config.repository_id,
            timeout=timeout,
        )
    if isinstance(config.issue_source, LocalMarkdownIssueSourceConfig):
        return UnconfiguredPullRequestSource()
    raise RuntimeError(  # pragma: no cover - exhaustive guard for future kinds.
        "unsupported configured Issue Source"
    )
