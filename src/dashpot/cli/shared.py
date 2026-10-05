"""The options, Event Log hand-off and outcome recording every command group shares."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated

from cyclopts import Parameter, validators

from ..core.command_outcomes import OutcomeNote, record_command_outcome
from ..core.event_log import EventLog
from ..core.runtime_events import ManagementCommand
from ..project.project_config import declared_project_id

USAGE_EXIT_CODE = 2
# The Event Log of the command line's own process, while ``main`` runs it:
# the hand-off from ``main`` to the ``observe`` command Cyclopts calls, set
# and reset around one dispatch rather than configured for the process.
EVENT_LOG: ContextVar[EventLog | None] = ContextVar(
    "dashpot_cli_event_log", default=None
)

Timeout = Annotated[
    float,
    Parameter(
        validator=validators.Number(gt=0),
        help=(
            "seconds allowed for each external command, such as git and gh; "
            "a named mutation's git commands get at least 300"
        ),
    ),
]
IssueHint = Annotated[
    str,
    Parameter(
        help=(
            "Issue Hint: a bare Issue Number (12), #12, a full Issue Reference "
            "such as owner/repository#12, or a Local Issue slug"
        )
    ),
]
JsonOutput = Annotated[
    bool,
    Parameter(
        name="--json",
        show_default=False,
        help="print the result as JSON with camelCase keys instead of lines",
    ),
]


def print_lines(messages: Iterable[str]) -> None:
    """Print each message on a line of its own."""
    for message in messages:
        print(message)


@contextmanager
def command_outcome(
    command: ManagementCommand, *, dry_run: bool | None = None
) -> Iterator[OutcomeNote]:
    """Record what the management command this process runs did, when it ends.

    The outcome names the Project of the configured checkout whose Event Log
    it is written to, read once the command is done.
    """
    log = EVENT_LOG.get()
    with record_command_outcome(log, command, dry_run=dry_run) as outcome:
        try:
            yield outcome
        finally:
            destination = None if log is None else log.destination
            checkout = None if destination is None else destination.checkout
            if checkout is not None:
                outcome.identify(project_id=declared_project_id(checkout))
