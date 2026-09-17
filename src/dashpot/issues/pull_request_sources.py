"""Observe complete Pull Request collections behind one small interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import override

from ..core.model import Diagnostic, PullRequest, SourceStatus
from ..core.timestamps import utc_now
from .retaining_source import Clock, RetainingSource, SourceRefreshError


@dataclass(frozen=True, slots=True)
class PullRequestSourceObservation:
    """Carry one source refresh and the complete collection it can publish."""

    status: SourceStatus
    attempted_at: str
    last_good_at: str | None
    pull_requests: tuple[PullRequest, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class CollectedPullRequests:
    """Return one complete collection cycle with any non-fatal diagnostics."""

    pull_requests: tuple[PullRequest, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


class PullRequestSourceRefreshError(SourceRefreshError):
    """Diagnose one failed Pull Request refresh with its stable code."""


class PullRequestSource(
    RetainingSource[CollectedPullRequests, PullRequestSourceObservation]
):
    """Refresh complete Pull Request collections and retain the last good one."""

    @override
    def _observation(
        self,
        collected: CollectedPullRequests | None,
        status: SourceStatus,
        attempted_at: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> PullRequestSourceObservation:
        return PullRequestSourceObservation(
            status=status,
            attempted_at=attempted_at,
            last_good_at=self._last_good_at,
            pull_requests=collected.pull_requests if collected is not None else (),
            diagnostics=diagnostics,
        )

    @override
    def _check_collection_invariants(self, collected: CollectedPullRequests) -> None:
        """Refuse a collection that repeats a Pull Request identity or Number."""
        identities: set[str] = set()
        numbers: set[int] = set()
        for pull_request in collected.pull_requests:
            if pull_request.id in identities:
                raise PullRequestSourceRefreshError(
                    f"{self.code_prefix}-duplicate-identity",
                    f"{self.name} collected duplicate Pull Request identity "
                    f"{pull_request.id}",
                )
            if pull_request.number in numbers:
                raise PullRequestSourceRefreshError(
                    f"{self.code_prefix}-duplicate-number",
                    f"{self.name} collected duplicate Pull Request Number "
                    f"#{pull_request.number}",
                )
            identities.add(pull_request.id)
            numbers.add(pull_request.number)


class UnconfiguredPullRequestSource:
    """Report that a Project has no configured GitHub Pull Request source."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now

    def refresh(self) -> PullRequestSourceObservation:
        attempted_at = self._clock()
        return PullRequestSourceObservation(
            status="unavailable",
            attempted_at=attempted_at,
            last_good_at=None,
            pull_requests=(),
            diagnostics=(
                Diagnostic(
                    source="pull-requests",
                    code="pull-requests-not-configured",
                    severity="info",
                    message=(
                        "Pull Requests are not configured for a Project whose "
                        "Issue Source is Local Markdown"
                    ),
                ),
            ),
        )
