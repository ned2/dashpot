"""Observe complete Pull Request collections behind one small interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from .issue_sources import DiagnosticSeverity, utc_now
from .model import PullRequest, SourceStatus

Clock = Callable[[], str]


@dataclass(frozen=True, slots=True)
class PullRequestSourceDiagnostic:
    source: str
    code: str
    severity: DiagnosticSeverity
    message: str


@dataclass(frozen=True, slots=True)
class PullRequestSourceObservation:
    """Carry one source refresh and the complete collection it can publish."""

    status: SourceStatus
    attempted_at: str
    last_good_at: str | None
    pull_requests: tuple[PullRequest, ...]
    diagnostics: tuple[PullRequestSourceDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CollectedPullRequests:
    """Return one complete collection cycle with any non-fatal diagnostics."""

    pull_requests: tuple[PullRequest, ...]
    diagnostics: tuple[PullRequestSourceDiagnostic, ...] = ()


class PullRequestSourceRefreshError(RuntimeError):
    """Diagnose one failed Pull Request refresh with its stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PullRequestSource(ABC):
    """Refresh complete Pull Request collections and retain the last good one."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now
        self._last_good: tuple[PullRequest, ...] | None = None
        self._last_good_at: str | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Name this source in its Diagnostics."""

    def refresh(self) -> PullRequestSourceObservation:
        """Publish a complete collection or retain the last good one on failure."""
        attempted_at = self._clock()
        try:
            collected = self._collect()
            self._check_collection_invariants(collected.pull_requests)
        except PullRequestSourceRefreshError as exc:
            return self._failed(attempted_at, exc.code, str(exc))
        except Exception as exc:
            return self._failed(
                attempted_at,
                f"{self.name}-internal",
                f"{type(exc).__name__}: {exc}",
            )
        self._last_good = collected.pull_requests
        self._last_good_at = attempted_at
        return PullRequestSourceObservation(
            status="fresh",
            attempted_at=attempted_at,
            last_good_at=attempted_at,
            pull_requests=collected.pull_requests,
            diagnostics=collected.diagnostics,
        )

    def _failed(
        self, attempted_at: str, code: str, message: str
    ) -> PullRequestSourceObservation:
        return PullRequestSourceObservation(
            status="stale" if self._last_good is not None else "unavailable",
            attempted_at=attempted_at,
            last_good_at=self._last_good_at,
            pull_requests=self._last_good or (),
            diagnostics=(
                PullRequestSourceDiagnostic(
                    source=self.name,
                    code=code,
                    severity="warning" if self._last_good is not None else "error",
                    message=message,
                ),
            ),
        )

    def _check_collection_invariants(
        self, pull_requests: tuple[PullRequest, ...]
    ) -> None:
        identities: set[str] = set()
        numbers: set[int] = set()
        for pull_request in pull_requests:
            if pull_request.id in identities:
                raise PullRequestSourceRefreshError(
                    "github-duplicate-identity",
                    f"GitHub collected duplicate Pull Request identity "
                    f"{pull_request.id}",
                )
            if pull_request.number in numbers:
                raise PullRequestSourceRefreshError(
                    "github-duplicate-number",
                    f"GitHub collected duplicate Pull Request Number "
                    f"#{pull_request.number}",
                )
            identities.add(pull_request.id)
            numbers.add(pull_request.number)

    @abstractmethod
    def _collect(self) -> CollectedPullRequests:
        """Observe one complete Pull Request collection."""


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
                PullRequestSourceDiagnostic(
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
