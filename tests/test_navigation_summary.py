"""The peer-screen navigation summary derives only from Project Totals."""

from __future__ import annotations

import pytest

from dashpot.core.model import SourceStatus
from dashpot.queries.source_queries import ProjectTotals, ResourceKind, SourceContext
from dashpot.ui.navigation_summary import NavigationSummary, navigation_summary

NOW = "2026-09-20T00:00:00Z"
CONTEXT = SourceContext(
    project_id="project:test",
    repository_id="repository:test",
    source="github",
    location="https://github.com/test/project",
)


def totals(
    kind: ResourceKind, count: int | None, *, status: SourceStatus = "fresh"
) -> ProjectTotals:
    """Build one Project Total for the summary examples."""
    return ProjectTotals(
        context=CONTEXT,
        kind=kind,
        open_count=count,
        closed_count=0 if count is not None else None,
        status=status,
        attempted_at=NOW,
        last_good_at=NOW if status == "stale" else None,
    )


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ({}, NavigationSummary("-", "-", None)),
        (
            {"issues": totals("issues", 0)},
            NavigationSummary("0", "-", "fresh"),
        ),
        (
            {
                "issues": totals("issues", 18),
                "pull-requests": totals("pull-requests", 2),
            },
            NavigationSummary("18", "2", "fresh"),
        ),
        (
            {
                "issues": totals("issues", 18),
                "pull-requests": totals("pull-requests", 2, status="stale"),
            },
            NavigationSummary("18", "2", "stale"),
        ),
        (
            {
                "issues": totals("issues", None, status="unavailable"),
                "pull-requests": totals("pull-requests", None, status="unavailable"),
            },
            NavigationSummary("-", "-", None),
        ),
        (
            {
                "issues": totals("issues", 18),
                "pull-requests": totals("pull-requests", None, status="unavailable"),
            },
            NavigationSummary("18", "-", "fresh"),
        ),
    ],
)
def test_navigation_summary_reports_exact_open_totals_and_aggregate_freshness(
    observed: dict[ResourceKind, ProjectTotals], expected: NavigationSummary
) -> None:
    assert navigation_summary(observed) == expected
    assert navigation_summary(observed).text == (
        f"Open Issues: {expected.issues} | Open PRs: {expected.pull_requests}"
    )
