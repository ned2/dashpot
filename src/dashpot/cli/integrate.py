"""``dashpot integrate``: install, check or remove the opt-in harness integration."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Annotated

from cyclopts import Group, Parameter, validators

from ..core.command_outcomes import OutcomeNote
from ..core.model import HARNESS_DISPLAY, Harness
from ..core.working_directory import current_directory
from ..sessions.integrate import (
    HarnessReport,
    IncompleteIntegrationError,
    in_integration_order,
    install_integration,
    install_integrations,
    integration_status,
    integration_totals,
    integrations_status,
    refresh_integrations,
    refuse_integrate_arguments,
    remove_integration,
)
from .shared import USAGE_EXIT_CODE, command_outcome, print_lines

INTEGRATE_USAGE = "Usage: dashpot integrate [OPTIONS] [HARNESS...]"
_integrate_action = Group("Action", validator=validators.MutuallyExclusive())


def integrate(
    *harnesses: Annotated[
        Harness,
        Parameter(
            name="HARNESS",
            help=(
                "the agent harnesses to integrate; several run in the order "
                "claude-code, codex, opencode, each standing alone"
            ),
        ),
    ],
    installed: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "refresh every harness already integrated, with every lifecycle "
                "hook registered, and no other"
            ),
        ),
    ] = False,
    status: Annotated[
        bool,
        Parameter(
            group=_integrate_action,
            show_default=False,
            help=(
                "report integration state without changing anything; with no "
                "harness, of every harness"
            ),
        ),
    ] = False,
    remove: Annotated[
        bool,
        Parameter(
            group=_integrate_action,
            show_default=False,
            help=(
                "remove exactly the Dashpot hooks, managed skills and agents of "
                "one named harness"
            ),
        ),
    ] = False,
) -> int:
    """Install the opt-in agent lifecycle integration and bundled skills.

    Register, inspect, or remove the opt-in hooks that publish Agent Session
    lifecycle observations and the agent-facing skills Dashpot bundles, such
    as the Issue-work skill, and, for OpenCode, the bundled worker agent.
    Nothing is installed without running this command, and --installed
    refreshes only a harness that is integrated already.
    """
    named = in_integration_order(harnesses)
    with command_outcome("integrate") as outcome:
        refuse_integrate_arguments(
            named, installed=installed, status=status, remove=remove
        )
        if len(named) == 1:
            return _integrate_one(
                named[0], status=status, remove=remove, outcome=outcome
            )
        if status:
            combined = integrations_status(named, current=current_directory())
            _report_harnesses(combined.harnesses)
            print_lines(combined.messages)
            outcome.action = "reported"
            return 0
        reports = install_integrations(named) if named else refresh_integrations()
        _report_harnesses(reports)
        totals = integration_totals(reports)
        outcome.refusals = totals.refusals
        outcome.incomplete = totals.incomplete
        if totals.installed:
            outcome.action = "installed"
        return USAGE_EXIT_CODE if totals.failed else 0


def _integrate_one(
    harness: Harness, *, status: bool, remove: bool, outcome: OutcomeNote
) -> int:
    """Install, check or remove one named harness's integration, refusing as it does."""
    outcome.target_harness = harness
    if status:
        messages = integration_status(harness, current=current_directory())
        outcome.action = "reported"
        print_lines(messages)
        return 0
    try:
        messages = (
            remove_integration(harness) if remove else install_integration(harness)
        )
    except IncompleteIntegrationError as incomplete:
        # What was written or removed is reported before the failures it
        # carried on past, which end the command as any refusal does.
        print_lines(incomplete.messages)
        raise
    outcome.action = "removed" if remove else "installed"
    print_lines(messages)
    return 0


def _report_harnesses(reports: Iterable[HarnessReport]) -> None:
    """Print each harness's lines under its name, and its error as a refusal."""
    for report in reports:
        display = HARNESS_DISPLAY[report.harness]
        print(f"{display}: {report.note}" if report.note else f"{display}:")
        for message in report.messages:
            print(f"  {message}")
        if report.error is not None:
            print(f"dashpot: {display}: {report.error}", file=sys.stderr)
