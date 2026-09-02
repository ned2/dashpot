"""Resolve an Issue Hint through the configured Issue Source."""

from __future__ import annotations

import re
from pathlib import Path

from .collect import build_issue_source
from .issue_profile import IssueProfile
from .issue_sources import IssueSource
from .project_config import load_project_config
from .repository import worktree_root

ISSUE_NUMBER = re.compile(r"^#?([1-9][0-9]*)$")


def configured_issue_source(root: Path, timeout: float = 10) -> IssueSource:
    """The Issue Source the Project at this Worktree declares."""
    return build_issue_source(root, load_project_config(root), timeout=timeout)


def resolve_issue(root: Path, hint: str, timeout: float = 10) -> IssueProfile:
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
        matches = [issue for issue in observation.issues if issue.number == number]
    else:
        matches = [issue for issue in observation.issues if issue.reference == hint]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise RuntimeError(f"Issue Reference {hint!r} is ambiguous")
    raise RuntimeError(
        f"Issue Reference {hint!r} did not match an Issue in this Project"
    )


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


def issue_location(issue: IssueProfile) -> str:
    """The Issue Location as one actionable string."""
    location = issue.location
    if location.kind == "github":
        return location.url
    return f"{location.path}:{location.line}"
