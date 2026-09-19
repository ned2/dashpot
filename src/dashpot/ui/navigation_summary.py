"""Derive the peer-screen navigation summary from Project Totals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from ..queries.source_queries import ProjectTotals, ResourceKind

SummaryFreshness = Literal["fresh", "stale"]


@dataclass(frozen=True, slots=True)
class NavigationSummary:
    """The exact open counts and aggregate freshness shown on both peers."""

    issues: str
    pull_requests: str
    freshness: SummaryFreshness | None

    @property
    def text(self) -> str:
        """The status bar's fixed summary text."""
        return f"Open Issues: {self.issues} | Open PRs: {self.pull_requests}"


def navigation_summary(
    totals: Mapping[ResourceKind, ProjectTotals],
) -> NavigationSummary:
    """Derive exact values and one freshness state from Project Totals."""
    issues = totals.get("issues")
    pull_requests = totals.get("pull-requests")
    observed = tuple(
        value
        for value in (issues, pull_requests)
        if value is not None and value.open_count is not None
    )
    freshness: SummaryFreshness | None
    if not observed:
        freshness = None
    elif any(value.status == "stale" for value in observed):
        freshness = "stale"
    else:
        freshness = "fresh"
    return NavigationSummary(
        "-" if issues is None or issues.open_count is None else str(issues.open_count),
        "-"
        if pull_requests is None or pull_requests.open_count is None
        else str(pull_requests.open_count),
        freshness,
    )
