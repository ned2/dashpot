"""The interface each hook installer implements: the hooks file, or OpenCode's plugin."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..processes import ProcessLookup
from .registry import BundledSkill, HarnessIntegration
from .writes import Planned


@dataclass(frozen=True, slots=True)
class StatusProbe:
    """What ``--status`` observes beyond the configuration directory."""

    current: Path | None
    lookup: ProcessLookup
    environ: Mapping[str, str] | None
    version_probe: Callable[[], str | None] | None


class HookInstaller(Protocol):
    """How Dashpot's lifecycle hooks are installed, removed and reported for a harness.

    One installer serves every harness whose integration has its kind
    (``HarnessIntegration.installer``). Each method takes the harness's
    integration and the configuration directory it works in.
    """

    @property
    def noun(self) -> str:
        """What the installed hooks are called, such as ``hooks`` or ``plugin``."""
        ...

    def plan(
        self,
        spec: HarnessIntegration,
        home: Path,
        command: Path,
        *,
        version_probe: Callable[[], str | None] | None,
    ) -> list[Planned]:
        """The hooks bound to ``command``: a pending write, unless they are current.

        Raises ``IntegrationError`` when the installation is refused.
        """
        ...

    def remove(self, spec: HarnessIntegration, home: Path) -> str:
        """Remove exactly Dashpot's hooks; raises ``IntegrationError`` when it cannot."""
        ...

    def missing(self, spec: HarnessIntegration, home: Path) -> tuple[str, ...] | None:
        """Each of Dashpot's subscriptions not registered; ``None`` when none is.

        Raises ``IntegrationError`` when what holds them cannot be read.
        """
        ...

    def has_update(self, spec: HarnessIntegration, home: Path) -> bool:
        """Whether refreshing the integrated harness would rewrite its hooks."""
        ...

    def status_lines(self, spec: HarnessIntegration, home: Path) -> list[str]:
        """Report the hooks and the publisher they run.

        Raises ``IntegrationError`` when nothing more of the harness's report
        can be trusted.
        """
        ...

    def notes(
        self,
        spec: HarnessIntegration,
        home: Path,
        skills: Sequence[tuple[BundledSkill, Path]],
        probe: StatusProbe | None,
    ) -> list[str]:
        """Advice that follows an installation, or with ``probe``, a ``--status`` report."""
        ...
