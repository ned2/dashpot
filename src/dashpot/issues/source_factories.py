"""Build the Issue Source a Project's configuration declares.

Issue resolution builds its source here, and the coordinator checks here
that the Repository Anchor can serve the configured source, so a configured
kind is interpreted the same way at every seam and neither imports the
other.
"""

from __future__ import annotations

from pathlib import Path

from ..core.errors import DashpotError
from ..core.git import Git
from ..github.github_repository import github_repo_from_remote
from ..project.project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    ProjectConfig,
)
from .github_issues import GitHubIssuesSource
from .issue_sources import IssueSource
from .local_markdown_issues import LocalMarkdownIssuesSource


class IssueSourceError(DashpotError):
    """A configured Issue Source the Repository Anchor cannot serve."""


def check_issue_source(
    root: Path, config: ProjectConfig, *, git: Git | None = None
) -> None:
    """Refuse a configured Issue Source the Repository Anchor cannot serve.

    A GitHub Issue Source needs a GitHub origin remote. ``git`` reuses a
    caller's adapter for that check instead of probing again.
    """
    if isinstance(
        config.issue_source, GitHubIssueSourceConfig
    ) and not github_repo_from_remote(root, git):
        raise IssueSourceError(
            "A GitHub Issue Source requires the Repository Anchor to have "
            "a GitHub origin remote"
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
    check_issue_source(root, config, git=git)
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
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
