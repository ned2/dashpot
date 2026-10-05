"""Refuse ``dashpot integrate`` arguments that name no one action, and total its harnesses.

These are ADR 0111's rules: harnesses named or ``--installed``, never both;
``--remove`` with exactly one named harness; and the exit status and
``command.outcome`` of a command across harnesses, read from each
harness's report.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ...core.model import Harness
from .across import HarnessReport
from .writes import IntegrationError


def refuse_integrate_arguments(
    named: Sequence[Harness], *, installed: bool, status: bool, remove: bool
) -> None:
    """Raise ``IntegrationError`` unless the arguments name one integrate action."""
    if installed and named:
        raise IntegrationError(
            "name the harnesses to integrate or pass --installed, not both"
        )
    if remove and len(named) != 1:
        raise IntegrationError(
            "--remove takes exactly one named harness, as in "
            "'dashpot integrate codex --remove'"
        )
    if not named and not installed and not status:
        raise IntegrationError(
            "name a harness to integrate, or pass --installed to refresh "
            "every integrated harness"
        )


@dataclass(frozen=True, slots=True)
class IntegrationTotals:
    """What an install or refresh across harnesses came to, over every harness."""

    # The harnesses refused, which the outcome counts as its refusals.
    refusals: int
    # Whether any harness was left incomplete.
    incomplete: bool
    # Whether any harness was written, completely or not.
    installed: bool

    @property
    def failed(self) -> bool:
        """Whether any harness was refused or left incomplete: the command exits 2."""
        return bool(self.refusals) or self.incomplete


def integration_totals(reports: Iterable[HarnessReport]) -> IntegrationTotals:
    """Total the harnesses' reports of an install or refresh across harnesses."""
    outcomes = [report.outcome for report in reports]
    return IntegrationTotals(
        refusals=sum(outcome == "refused" for outcome in outcomes),
        incomplete="incomplete" in outcomes,
        installed=any(outcome in ("installed", "incomplete") for outcome in outcomes),
    )
