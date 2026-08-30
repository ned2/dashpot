"""Resolve an Issue Hint through the configured Issue Source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .github_issues import GitHubIssuesSource
from .issue_sources import IssueSource
from .local_markdown_issues import LocalMarkdownIssuesSource
from .project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
)
from .repository import github_repo_from_remote, worktree_root

ISSUE_NUMBER = re.compile(r"^#?([1-9][0-9]*)$")


def configured_issue_source(root: Path, timeout: float = 10) -> IssueSource:
    """The Issue Source the Project at this Worktree declares."""
    config = load_project_config(root)
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        if not github_repo_from_remote(root):
            raise RuntimeError(
                "a GitHub Issue Source requires this Worktree to have a "
                "GitHub origin remote"
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
    raise RuntimeError("unsupported configured Issue Source")  # pragma: no cover


def resolve_issue(root: Path, hint: str, timeout: float = 10) -> dict[str, Any]:
    """Resolve an Issue Hint to exactly one fresh Issue of this Project.

    A bare or ``#``-prefixed Issue Number matches by number; any other hint
    matches an Issue Reference exactly, so a full GitHub reference resolves
    only in a GitHub Project and a slug only in a Local Issue Markdown one.
    A source that is not fresh, no match, and more than one match are each
    refused with the reason; nothing is written.
    """
    source = configured_issue_source(root, timeout)
    observation = source.refresh()
    if observation.status != "fresh":
        details = "; ".join(
            diagnostic.message for diagnostic in observation.diagnostics
        )
        raise RuntimeError(
            f"cannot resolve Issue Reference while the Issue Source is "
            f"{observation.status}: {details or 'no diagnostics'}"
        )
    number_match = ISSUE_NUMBER.fullmatch(hint)
    if number_match:
        number = int(number_match.group(1))
        matches = [issue for issue in observation.issues if issue["number"] == number]
    else:
        matches = [issue for issue in observation.issues if issue["reference"] == hint]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise RuntimeError(f"Issue Reference {hint!r} is ambiguous")
    raise RuntimeError(
        f"Issue Reference {hint!r} did not match an Issue in this Project"
    )


def show_issue(current: Path, hint: str, *, timeout: float = 10) -> dict[str, Any]:
    """Resolve an Issue Hint from any directory of a configured Worktree."""
    return resolve_issue(worktree_root(current), hint, timeout)


def describe_issue(issue: dict[str, Any]) -> list[str]:
    """Render the Issue facts a caller needs before acting on it."""
    state = issue["state"]
    if issue.get("stateReason"):
        state = f"{state} ({issue['stateReason']})"
    return [
        f"{issue['reference']}: {issue['title']}",
        f"number: #{issue['number']}",
        f"state: {state}",
        f"location: {issue_location(issue)}",
        f"id: {issue['id']}",
    ]


def issue_location(issue: dict[str, Any]) -> str:
    """The Issue Location as one actionable string."""
    location = issue["location"]
    if location["kind"] == "github":
        return str(location["url"])
    return f"{location['path']}:{location['line']}"
