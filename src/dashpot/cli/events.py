"""``dashpot events``: read the Event Log, or remove its older files."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from cyclopts import App, Parameter, Token

from ..core.event_log_files import (
    EventSelection,
    UnreadableEventLog,
    describe_event_log_removal,
    describe_runtime_event,
    read_event_logs,
    remove_event_logs,
    repository_event_log_directories,
)
from ..core.runtime_events import RecordedLevel, RuntimeEvent
from ..core.text import counted
from ..core.working_directory import current_directory
from ..event_logs import owned_event_log
from ..serialization import (
    event_log_removal_document,
    render_json,
    runtime_event_document,
)
from .shared import (
    EVENT_LOG,
    USAGE_EXIT_CODE,
    JsonOutput,
    Timeout,
    command_outcome,
    print_lines,
)

# ``30m``, ``12h``, ``7d``: an age counted back from now.
_RELATIVE_AGE = re.compile(r"(\d+)([mhd])")
_AGE_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """Read ``--since``: a UTC day, an ISO 8601 instant, or an age such as ``2h``.

    An instant without an offset is UTC, as every Runtime Event is stamped.
    """
    text = value.strip()
    age = _RELATIVE_AGE.fullmatch(text)
    if age is not None:
        moment = now if now is not None else datetime.now(UTC)
        return moment - timedelta(**{_AGE_UNITS[age.group(2)]: int(age.group(1))})
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"{value!r} is not a day (2026-09-27), an instant "
            f"(2026-09-27T14:00:00Z) or an age (30m, 12h, 7d)"
        ) from None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _convert_since(type_: object, tokens: Sequence[Token]) -> datetime:
    return parse_since(tokens[0].value)


def _convert_day(type_: object, tokens: Sequence[Token]) -> date:
    try:
        return date.fromisoformat(tokens[0].value.strip())
    except ValueError:
        raise ValueError(
            f"{tokens[0].value!r} is not a day such as 2026-09-27"
        ) from None


events = App(
    name="events",
    help=(
        "Read or remove the Event Log: the Runtime Events Dashpot records on "
        "this machine.\n\n"
        "Reading merges the Event Log of every Worktree of this Repository "
        "with the machine-local fallback, ordered by time. A dashboard records "
        "its events, including those about other Projects of its Workspace, in "
        "the checkout it was started in, so read them from there. remove "
        "mutates: only this checkout's Event Log files (or the machine-local "
        "fallback's, outside a configured checkout) dated before a day, never "
        "today's or later (ADR 0008)."
    ),
)


@events.default
def events_read(
    *,
    session: Annotated[
        str | None,
        Parameter(help="ID: only events of this Agent Session Identity"),
    ] = None,
    issue: Annotated[
        str | None,
        Parameter(
            help="ID: only events for this Issue Identity, as 'work show' prints it"
        ),
    ] = None,
    project: Annotated[
        str | None,
        Parameter(
            help=(
                "ID: only events for this Project Identity, the projectId of "
                ".dashpot/config.json"
            )
        ),
    ] = None,
    since: Annotated[
        datetime | None,
        Parameter(
            converter=_convert_since,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "only events from this UTC day (2026-09-27), instant "
                "(2026-09-27T14:00:00Z) or age (30m, 12h, 7d) on"
            ),
        ),
    ] = None,
    level: Annotated[
        RecordedLevel | None,
        Parameter(
            help=(
                "standard: only the events the default level records; full: "
                "every event (the default)"
            )
        ),
    ] = None,
    timeout: Timeout = 10.0,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            show_default=False,
            help=(
                "print the events as JSON Lines, one event per line under its "
                "Event Log field names"
            ),
        ),
    ] = False,
) -> int:
    """Read the Event Log of every Worktree of this Repository, oldest event first.

    Events print as each UTC day is read. A span is filed on the day it
    ended, so one stamped more than two days before that day prints out of
    order, once its day is read. Lines that cannot be read are reported on
    stderr and skipped, with or without --json; an event's line the filters
    leave out is not checked. Only .jsonl files are read, so a compressed
    file is not.
    """
    own = EVENT_LOG.get()
    unreadable_logs: list[UnreadableEventLog] = []
    events = read_event_logs(
        repository_event_log_directories(current_directory(), timeout=timeout),
        EventSelection(
            session=session,
            issue=issue,
            project=project,
            since=since,
            level=level,
            # This command's own start is not what anyone reads it for.
            exclude_run=None if own is None else own.identity.run_id,
        ),
        unreadable=unreadable_logs.append,
    )
    try:
        _print_events(events, json_output=json_output)
        # Flush inside the guard: a short output still sits in the buffer,
        # and the interpreter's own flush at exit would meet the closed pipe.
        sys.stdout.flush()
    except BrokenPipeError:
        _discard_stdout()
    # A reader that closed the pipe stopped the reading too, so only what
    # was read before it is reported.
    for unreadable in unreadable_logs:
        if unreadable.error is not None:
            print(
                f"dashpot: cannot read {unreadable.path}: {unreadable.error}",
                file=sys.stderr,
            )
        if unreadable.lines:
            count = len(unreadable.lines)
            print(
                f"dashpot: skipped {counted(count, 'unreadable line')} "
                f"in {unreadable.path}",
                file=sys.stderr,
            )
    return 0


def _print_events(events: Iterable[RuntimeEvent], *, json_output: bool) -> None:
    """Print each event on a line of its own, as it comes, as JSON Lines or for a person."""
    printed = False
    for event in events:
        printed = True
        if json_output:
            print(render_json(runtime_event_document(event), compact=True))
        else:
            print(describe_runtime_event(event))
    if not printed and not json_output:
        print("no matching Runtime Events")


def _discard_stdout() -> None:
    """Send what is left for stdout to the null device once its reader has gone.

    ``dashpot events --json | head`` closes the pipe once it has its lines:
    that is the reader finished, not the command failed, so the status
    stays 0 and the interpreter's last flush must not raise again.
    """
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, sys.stdout.fileno())
    finally:
        os.close(null)


@events.command(name="remove")
def events_remove(
    *,
    before: Annotated[
        date,
        Parameter(
            converter=_convert_day,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "DATE: remove the files whose UTC day is before this day "
                "(2026-09-01); today's and later are always kept"
            ),
        ),
    ],
    dry_run: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="report the files that would be removed without removing any",
        ),
    ] = False,
    json_output: JsonOutput = False,
) -> int:
    """Remove this checkout's Event Log files dated before a day.

    Only files named as the Event Log names them are removed, and none is
    compressed or renamed. Run it from the checkout whose Event Log it is;
    outside every configured checkout it acts on the machine-local fallback.
    A working directory that no longer exists, or whose checkout cannot be
    told, is refused rather than taken to be outside every checkout.
    """
    with command_outcome("events remove", dry_run=dry_run) as outcome:
        destination = owned_event_log(current_directory())
        outcome.target_path = destination.directory
        removal = remove_event_logs(destination, before, dry_run=dry_run)
        if not removal.succeeded:
            outcome.incomplete = True
        else:
            outcome.action = "previewed" if dry_run else "removed"
    if json_output:
        print(render_json(event_log_removal_document(removal)))
    else:
        print_lines(describe_event_log_removal(removal))
    return 0 if removal.succeeded else USAGE_EXIT_CODE
