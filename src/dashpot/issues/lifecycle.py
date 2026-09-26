"""Decide which Issues a lifecycle choice lists: open, Ready, closed, or all.

A Ready Issue is open with no open blocker. A GitHub page answers that with
GitHub's own search and reads each blocker's state from the Issue it
fetched; a source that holds its whole collection answers it here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from ..core.issue_profile import IssueProfile
from ..core.model import OpenBlocker

Lifecycle = Literal["open", "ready", "closed", "all"]


def collection_open_blockers(
    issue: IssueProfile, collection: Mapping[str, IssueProfile]
) -> tuple[OpenBlocker, ...]:
    """The Issue's blockers that ``collection``, keyed by identity, holds open.

    A blocker the collection does not hold is unknown, and counts as open.
    """
    blockers: list[OpenBlocker] = []
    for identity in issue.relationships.blocked_by:
        blocker = collection.get(identity)
        if blocker is None:
            blockers.append(OpenBlocker(id=identity))
        elif blocker.state == "open":
            blockers.append(
                OpenBlocker(
                    id=blocker.id, reference=blocker.reference, number=blocker.number
                )
            )
    return tuple(blockers)


def in_lifecycle(
    issue: IssueProfile, lifecycle: Lifecycle, collection: Mapping[str, IssueProfile]
) -> bool:
    """Tell whether the lifecycle choice lists the Issue, judged against ``collection``."""
    if lifecycle == "all":
        return True
    if lifecycle == "ready":
        return issue.state == "open" and not collection_open_blockers(issue, collection)
    return issue.state == lifecycle
