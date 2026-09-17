"""The filter bars' queries have one owner, whichever paged kind they filter."""

from __future__ import annotations

from typing import cast

from dashpot.queries.source_queries import ResourceKind
from dashpot.ui.app import DashboardScreen
from dashpot.ui.list_queries import ListQueries


class RecordingScreen:
    """Stand in for the dashboard: what the queries submit, in order."""

    def __init__(self) -> None:
        self.submitted: list[tuple[ResourceKind, dict[str, str]]] = []
        self.dashpot = self

    def submit_page(self, kind: ResourceKind, **updates: str) -> None:
        self.submitted.append((kind, updates))


def queries() -> tuple[ListQueries, RecordingScreen]:
    screen = RecordingScreen()
    return ListQueries(cast("DashboardScreen", screen)), screen


def test_enter_submits_the_whole_text_for_the_kind_that_was_searched() -> None:
    owner, screen = queries()

    owner.submit_search("pull-requests", "draft:true")
    owner.submit_search("issues", "sort:created-desc")

    assert owner.pull_requests.text == "draft:true"
    assert owner.issues.text == "sort:created-desc"
    assert owner.query("issues") is owner.issues
    assert owner.query("pull-requests") is owner.pull_requests
    assert screen.submitted == [
        ("pull-requests", {"query": "draft:true"}),
        ("issues", {"query": "sort:created-desc"}),
    ]


def test_a_lifecycle_change_submits_its_page_once_and_an_unknown_choice_never() -> None:
    owner, screen = queries()

    owner.change_lifecycle("issues", "closed")
    owner.change_lifecycle("issues", "closed")
    owner.change_lifecycle("pull-requests", "everything")
    owner.change_lifecycle("pull-requests", "all")

    assert owner.issues.states == frozenset({"closed"})
    assert owner.pull_requests.states == frozenset({"open", "closed"})
    assert screen.submitted == [
        ("issues", {"state": "closed"}),
        ("pull-requests", {"state": "all"}),
    ]
    # Recording a search keeps the lifecycle, and the other kind, untouched.
    owner.submit_search("issues", "bug")
    assert owner.issues.states == frozenset({"closed"})
    assert owner.pull_requests.text == ""
