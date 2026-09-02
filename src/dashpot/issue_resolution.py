"""Resolve an Issue Hint through the configured Issue Source."""

from __future__ import annotations

from pathlib import Path

from .collect import build_issue_source
from .issue_profile import IssueProfile, issue_location
from .issue_sources import IssueSource, parse_issue_hint
from .project_config import load_project_config
from .repository import worktree_root


def configured_issue_source(root: Path, timeout: float = 10) -> IssueSource:
    """The Issue Source the Project at this Worktree declares."""
    return build_issue_source(root, load_project_config(root), timeout=timeout)


def resolve_issue(root: Path, hint: str, timeout: float = 10) -> IssueProfile:
    """Resolve an Issue Hint to exactly one fresh Issue of this Project.

    The hint is stripped and parsed once: a bare or ``#``-prefixed Issue
    Number matches by number; a pasted GitHub Issue URL — the form
    ``issue_location`` prints — matches the repository-qualified Reference it
    names; any other hint matches an Issue Reference exactly and
    case-sensitively, so a full GitHub reference resolves only in the GitHub
    Project whose repository it names and a slug only in a Local Issue
    Markdown one. A source that cannot answer freshly, a detectable
    ambiguity, and a miss are each refused with the reason; nothing is
    written.
    """
    source = configured_issue_source(root, timeout)
    issue = source.find(parse_issue_hint(hint))
    if issue is None:
        raise RuntimeError(
            f"Issue Reference {hint!r} did not match an Issue in this Project"
        )
    return issue


def show_issue(current: Path, hint: str, *, timeout: float = 10) -> IssueProfile:
    """Resolve an Issue Hint from any directory of a configured Worktree."""
    return resolve_issue(worktree_root(current), hint, timeout)


def describe_issue(issue: IssueProfile) -> list[str]:
    """Render the Issue facts a caller needs before acting on it."""
    state: str = issue.state
    if issue.state_reason:
        state = f"{state} ({issue.state_reason})"
    return [
        f"{issue.reference}: {issue.title}",
        f"number: #{issue.number}",
        f"state: {state}",
        f"location: {issue_location(issue)}",
        f"id: {issue.id}",
    ]
