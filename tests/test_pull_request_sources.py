"""The Pull Request source base names its Diagnostics after the concrete source."""

from __future__ import annotations

from typing import override

from dashpot.issues.pull_request_sources import (
    CollectedPullRequests,
    PullRequestSource,
)
from factories import pull_request


class ScriptedSource(PullRequestSource):
    """A source that publishes one scripted collection."""

    def __init__(self, collected: CollectedPullRequests) -> None:
        super().__init__(clock=lambda: "2026-09-17T00:00:00Z")
        self.collected = collected

    @property
    @override
    def name(self) -> str:
        return "scripted"

    @override
    def _collect(self) -> CollectedPullRequests:
        return self.collected


def test_duplicate_codes_and_wording_follow_the_source_name() -> None:
    first = pull_request(1)
    duplicate = pull_request(2, pull_request_id="PR_1")

    observation = ScriptedSource(CollectedPullRequests((first, duplicate))).refresh()

    assert observation.status == "unavailable"
    (diagnostic,) = observation.diagnostics
    assert diagnostic.source == "scripted"
    assert diagnostic.code == "scripted-duplicate-identity"
    assert diagnostic.message == (
        "scripted collected duplicate Pull Request identity PR_1"
    )


def test_a_repeated_number_is_refused_with_the_source_prefix() -> None:
    first = pull_request(1)
    duplicate = pull_request(1, pull_request_id="PR_other")

    observation = ScriptedSource(CollectedPullRequests((first, duplicate))).refresh()

    (diagnostic,) = observation.diagnostics
    assert diagnostic.code == "scripted-duplicate-number"
    assert diagnostic.message == "scripted collected duplicate Pull Request Number #1"
