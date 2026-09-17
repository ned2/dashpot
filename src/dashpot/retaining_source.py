"""Retain complete source observations through diagnosed refresh failures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

from .core.errors import DashpotError
from .core.model import Diagnostic, SourceStatus
from .timestamps import utc_now

Clock = Callable[[], str]


class SourceRefreshError(DashpotError, RuntimeError):
    """Diagnose a failed collection with its stable Diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Collection(Protocol):
    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]: ...


Collected = TypeVar("Collected", bound=Collection)
Observation = TypeVar("Observation")


class RetainingSource(ABC, Generic[Collected, Observation]):
    """Publish complete collections and retain their last good value on failure."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now
        self._last_good: Collected | None = None
        self._last_good_at: str | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Name this source in its Diagnostics."""

    def refresh(self) -> Observation:
        """Publish one complete cycle or retain the last good collection."""
        attempted_at = self._clock()
        try:
            collected = self._collect()
            self._check_collection_invariants(collected)
            collected = self._snapshot(collected)
        except SourceRefreshError as exc:
            return self._failed(attempted_at, exc.code, str(exc))
        except Exception as exc:
            # Collection adapters historically contain unexpected adapter faults;
            # keep that boundary while query observations catch named failures.
            return self._failed(
                attempted_at, f"{self.name}-internal", f"{type(exc).__name__}: {exc}"
            )
        self._last_good = collected
        self._last_good_at = attempted_at
        return self._observation(
            collected, "fresh", attempted_at, collected.diagnostics
        )

    def _failed(self, attempted_at: str, code: str, message: str) -> Observation:
        retained = self._last_good is not None
        return self._observation(
            self._last_good,
            "stale" if retained else "unavailable",
            attempted_at,
            (
                Diagnostic(
                    source=self.name,
                    code=code,
                    severity="warning" if retained else "error",
                    message=message,
                ),
            ),
        )

    def _snapshot(self, collected: Collected) -> Collected:
        """Retain an immutable collection value."""
        return collected

    @abstractmethod
    def _collect(self) -> Collected:
        """Observe one complete collection cycle."""

    @abstractmethod
    def _check_collection_invariants(self, collected: Collected) -> None:
        """Require collection identities and numbers to be unique."""

    @abstractmethod
    def _observation(
        self,
        collected: Collected | None,
        status: SourceStatus,
        attempted_at: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> Observation:
        """Shape the retained collection as its source observation."""
