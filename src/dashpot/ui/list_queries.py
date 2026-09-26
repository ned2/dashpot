"""Own the queries the Issue and Pull Request filter bars submit.

Each filter bar's Enter submits its whole search text to the Query Source
behind its page, and its lifecycle choice submits the page's state; editing
the text alone changes nothing. Both kinds are recorded here in one shape,
so the Issue table filters its accepted page by the same owner's query a
Pull Request page is submitted from.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ..observation.issue_list import IssueListQuery
from ..observation.pull_request_list import (
    DEFAULT_PULL_REQUEST_QUERY,
    PullRequestListQuery,
)
from ..queries.source_queries import ResourceKind
from .item_filter import issue_lifecycle, lifecycle_states, lifecycle_value


class SubmitPage(Protocol):
    """Submit a page for one paged kind with the fields that changed."""

    def __call__(self, kind: ResourceKind, /, **updates: str) -> None: ...


class ListQueries:
    """Record each filter bar's submitted query and submit its page when it changes."""

    def __init__(self, submit_page: SubmitPage) -> None:
        self.submit_page = submit_page
        self.issues = IssueListQuery()
        self.pull_requests = DEFAULT_PULL_REQUEST_QUERY

    def query(self, kind: ResourceKind) -> IssueListQuery | PullRequestListQuery:
        """The query last submitted for one paged kind."""
        return self.issues if kind == "issues" else self.pull_requests

    def lifecycle(self, kind: ResourceKind) -> str:
        """The lifecycle choice last submitted for one paged kind."""
        if kind == "issues":
            return self.issues.lifecycle
        return lifecycle_value(self.pull_requests.states)

    def submit_search(self, kind: ResourceKind, text: str) -> None:
        """Submit the whole search text on Enter; editing alone changes nothing."""
        self.record(kind, text=text)
        self.submit_page(kind, query=text)

    def change_lifecycle(self, kind: ResourceKind, value: object) -> None:
        """Record the chosen lifecycle, which submits a page when it differs."""
        if kind == "issues":
            lifecycle = issue_lifecycle(value)
            if lifecycle is None or lifecycle == self.issues.lifecycle:
                return
            self.record(kind, lifecycle=lifecycle)
            self.submit_page(kind, state=lifecycle)
            return
        states = lifecycle_states(value)
        if states is None or states == self.pull_requests.states:
            return
        self.record(kind, states=states)
        self.submit_page(kind, state=lifecycle_value(states))

    def record(self, kind: ResourceKind, **changes: object) -> None:
        """Replace the recorded query's changed fields without submitting."""
        if kind == "issues":
            self.issues = replace(self.issues, **changes)
        else:
            self.pull_requests = replace(self.pull_requests, **changes)
