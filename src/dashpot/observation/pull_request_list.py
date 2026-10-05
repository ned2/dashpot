"""The Pull Requests pane read model: its submitted query and its rows.

The source answers the query with a page already filtered and ordered; a
row joins one Pull Request on that page to the Project whose Repository
owns it. The rendering lives in ``ui/pull_request_cells``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..core.model import ProjectObservation, PullRequest

PullRequestLifecycle = Literal["open", "closed"]


@dataclass(frozen=True, slots=True)
class PullRequestListQuery:
    text: str = ""
    states: frozenset[PullRequestLifecycle] = frozenset({"open"})


DEFAULT_PULL_REQUEST_QUERY = PullRequestListQuery()


@dataclass(frozen=True, slots=True)
class PullRequestListRow:
    """Join one Pull Request to the Project whose Repository owns it."""

    key: str
    project: ProjectObservation
    pull_request: PullRequest
