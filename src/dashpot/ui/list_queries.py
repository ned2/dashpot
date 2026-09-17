"""Own the queries the Issue and Pull Request filter bars submit.

Each filter bar's Enter submits its whole search text to the Query Source
behind its page, and its lifecycle choice submits the page's state; editing
the text alone changes nothing. Both kinds are recorded here in one shape,
so the Issue table filters its accepted page by the same owner's query a
Pull Request page is submitted from.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ..observation.issue_list import IssueListQuery
from ..observation.pull_request_list import (
    DEFAULT_PULL_REQUEST_QUERY,
    PullRequestListQuery,
)
from ..queries.source_queries import ResourceKind
from .item_filter import lifecycle_states, lifecycle_value

# What a submitted page is handed: its paged kind and the changed fields.
SubmitPage = Callable[..., None]


class ListQueries:
    """Record each filter bar's submitted query and submit its page when it changes."""

    def __init__(self, submit_page: SubmitPage) -> None:
        self.submit_page = submit_page
        self.issues = IssueListQuery()
        self.pull_requests = DEFAULT_PULL_REQUEST_QUERY

    def query(self, kind: ResourceKind) -> IssueListQuery | PullRequestListQuery:
        """The query last submitted for one paged kind."""
        return self.issues if kind == "issues" else self.pull_requests

    def submit_search(self, kind: ResourceKind, text: str) -> None:
        """Submit the whole search text on Enter; editing alone changes nothing."""
        self.record(kind, text=text)
        self.submit_page(kind, query=text)

    def change_lifecycle(self, kind: ResourceKind, value: object) -> None:
        """Record the chosen lifecycle, which submits a page when it differs."""
        states = lifecycle_states(value)
        if states is None or states == self.query(kind).states:
            return
        self.record(kind, states=states)
        self.submit_page(kind, state=lifecycle_value(states))

    def record(self, kind: ResourceKind, **changes: object) -> None:
        """Replace the recorded query's changed fields without submitting."""
        if kind == "issues":
            self.issues = replace(self.issues, **changes)
        else:
            self.pull_requests = replace(self.pull_requests, **changes)
