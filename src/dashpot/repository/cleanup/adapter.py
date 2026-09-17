"""Adapt Cleanup inspection and execution for the dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .perform import (
    CleanupConfirmation,
    CleanupReport,
    cleanup_git,
    perform_cleanup,
)
from .preview import inspect_cleanup
from .targets import CleanupPreview, CleanupRequest


class CleanupAdapter(Protocol):
    """What the dashboard injects to preview and perform a Cleanup.

    Both calls run off the event loop. ``protected`` is the checkout Dashpot
    runs from and the Project's Repository Anchors, which are never targets.
    """

    def inspect(
        self, request: CleanupRequest, *, protected: Sequence[Path]
    ) -> CleanupPreview: ...

    def perform(
        self, confirmation: CleanupConfirmation, *, protected: Sequence[Path]
    ) -> CleanupReport: ...


@dataclass(frozen=True, slots=True)
class GitCleanupAdapter:
    """The production adapter: real Git, non-interactive, under one timeout."""

    timeout: float

    def inspect(
        self, request: CleanupRequest, *, protected: Sequence[Path]
    ) -> CleanupPreview:
        return inspect_cleanup(
            request,
            protected=protected,
            timeout=self.timeout,
            git=cleanup_git(self.timeout),
        )

    def perform(
        self, confirmation: CleanupConfirmation, *, protected: Sequence[Path]
    ) -> CleanupReport:
        return perform_cleanup(
            confirmation,
            protected=protected,
            timeout=self.timeout,
            git=cleanup_git(self.timeout),
        )
