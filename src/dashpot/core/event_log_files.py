"""Find, read, measure and remove the files an Event Log keeps.

Reading merges the Event Log of every Worktree of one Repository with the
machine-local fallback, ordered by time (ADR 0059), and streams it one UTC
day at a time (ADR 0146). It is a validating seam: a line is selected by
its raw fields first, and only a line the selection may keep is validated
by the tolerant reader, so an event a newer Dashpot wrote keeps the fields
this one knows, and a line that cannot be read is reported beside the
events rather than failing the read.

Removal deletes only files named as Event Log files whose UTC day is before
both the day asked for and today, so a running writer's current file is
never touched and nothing has to decide whether a writer is still running.
Nothing here compresses or renames a file.
"""

from __future__ import annotations

import heapq
import itertools
import os
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, computed_field

from .errors import DashpotError
from .event_log import EVENTS_DIRECTORY, EventLogDestination, event_log_file_day
from .model import Diagnostic, Harness
from .pydantic import LaxSequence, PublishedModel
from .runtime_events import (
    EVENT_BODIES,
    EventBody,
    ProcessEnd,
    ProcessIdentity,
    RecordedLevel,
    RuntimeEvent,
    SpanEnded,
    runtime_event_fields,
    runtime_event_from_fields,
)
from .state_paths import (
    enclosing_checkout,
    machine_state_directory,
    project_state_directory,
)
from .timestamps import observed_instant
from .worktree_paths import repository_worktrees


def _on_disk(model: type[BaseModel], field: str) -> str:
    """The name ``field`` of ``model`` has in an Event Log line."""
    alias = model.model_fields[field].alias
    return field if alias is None else str(alias)


# The size past which a dashboard warns about its own Event Log directory.
LARGE_EVENT_LOG_BYTES = 200_000_000
EVENT_LOG_LARGE = "event-log-large"
# The fields a Runtime Event names what it worked for by, on disk.
SESSION_FIELD = _on_disk(ProcessIdentity, "session_id")
HARNESS_FIELD = _on_disk(ProcessIdentity, "harness")
ISSUE_FIELD = _on_disk(ProcessIdentity, "issue_id")
PROJECT_FIELD = _on_disk(ProcessIdentity, "project_id")
# The raw fields a selection reads before a line is validated.
_RUN_FIELD = _on_disk(ProcessIdentity, "run_id")
_TIME_FIELD = _on_disk(RuntimeEvent, "time")
_LEVEL_FIELD = _on_disk(RuntimeEvent, "level")
_NAME_FIELD = _on_disk(EventBody, "name")
_EXIT_CODE_FIELD = _on_disk(ProcessEnd, "exit_code")
_STATUS_FIELD = _on_disk(SpanEnded, "status")
# How long before the UTC day of the file it is written to an event may be
# stamped and still be read in order. A span is stamped when it started and
# written to the file of the day it ended, so the reader holds back the
# events this close to the next day's files until it has read them; only a
# span stamped longer than this before its file's day is read out of order
# (ADR 0146).
SPAN_CARRY_OVER = timedelta(days=2)
# What a process records about itself rather than about the work it did.
PROCESS_BOOKKEEPING = frozenset(
    {"process.start", "process.continued", "level.changed", "event_log.write_failed"}
)
# The fields a described event opens with, so each is not repeated after.
_HEADLINE_FIELDS = frozenset(
    {
        _on_disk(RuntimeEvent, "schema_version"),
        _on_disk(RuntimeEvent, "time"),
        _on_disk(RuntimeEvent, "level"),
        _on_disk(EventBody, "name"),
        _on_disk(ProcessIdentity, "run_id"),
        _on_disk(ProcessIdentity, "kind"),
    }
)


class EventLogError(DashpotError):
    """A refusal to remove Event Log files: nowhere to remove them from, or a directory that cannot be listed."""


@dataclass(frozen=True, slots=True)
class EventLogFile:
    """One file of an Event Log and the UTC day its name carries."""

    path: Path
    day: date


def event_log_files(directory: Path) -> list[EventLogFile]:
    """Every Event Log file in ``directory``, oldest day first.

    Only regular files named as an Event Log names its files are listed; a
    compressed or renamed file, or anything else beside them, is not one. A
    directory that does not exist has none.
    """
    try:
        entries = list(os.scandir(directory))
    except (FileNotFoundError, NotADirectoryError):
        return []
    files: list[EventLogFile] = []
    for entry in entries:
        day = event_log_file_day(entry.name)
        if day is None:
            continue
        try:
            regular = entry.is_file(follow_symlinks=False)
        except OSError:
            continue
        if regular:
            files.append(EventLogFile(Path(entry.path), day))
    files.sort(key=lambda file: (file.day, file.path.name))
    return files


def event_log_directories(worktrees: Iterable[Path]) -> tuple[Path, ...]:
    """The Event Log directory of each Worktree, then the machine-local fallback.

    With no home directory to hold the fallback, there is none.
    """
    directories = [
        project_state_directory(worktree) / EVENTS_DIRECTORY for worktree in worktrees
    ]
    # ``RuntimeError``: no home directory to hold the fallback.
    with suppress(RuntimeError):
        directories.append(machine_state_directory() / EVENTS_DIRECTORY)
    return tuple(dict.fromkeys(directories))


def repository_event_log_directories(
    current: Path, *, timeout: float = 5
) -> tuple[Path, ...]:
    """Every Event Log directory of the Repository enclosing ``current``, and the fallback.

    The Repository's Worktrees come in the order ``git worktree list``
    reports them. Outside every Git Repository only the fallback is read.
    Independent clones are other Repositories and are not reached.
    """
    checkout = enclosing_checkout(current.resolve())
    if checkout is None:
        return event_log_directories(())
    return event_log_directories(repository_worktrees(checkout, timeout=timeout))


def event_fields(event: RuntimeEvent) -> dict[str, Any]:
    """The event's fields as its line holds them, under their on-disk names."""
    return event.model_dump(mode="json", by_alias=True, exclude_none=True)


def published_event_fields(event: RuntimeEvent) -> dict[str, Any]:
    """The event's fields under their on-disk names, an unknown one as ``null``.

    The same names as :func:`event_fields`, but every field its kind of event
    has is present, as ``dashpot events --json`` publishes it (ADR 0064,
    ADR 0099).
    """
    return event.model_dump(mode="json", by_alias=True)


def event_instant(event: RuntimeEvent) -> datetime:
    """When the event happened, or when its span started."""
    return observed_instant(event.time)


def is_session_outcome(event: RuntimeEvent) -> bool:
    """Whether the event says what happened to a session's work, not how it ran.

    Hook and command outcomes, Agent Session and Agent Run changes and
    failures are; a process's start, a successful end, a level change and a
    successful span are not. An event a later Dashpot adds is an outcome
    when it is written at ``standard``. ``_may_be_outcome`` asks the same of
    a line's raw fields, and changes with it.
    """
    body = event.body
    if body.name in PROCESS_BOOKKEEPING:
        return False
    if isinstance(body, ProcessEnd):
        return body.exit_code != 0
    if isinstance(body, SpanEnded):
        return body.status == "ERROR"
    return event.level == "standard"


def _may_be_outcome(fields: Mapping[str, object]) -> bool:
    """Whether a line's raw fields may be an event :func:`is_session_outcome` counts."""
    name = fields.get(_NAME_FIELD)
    if name in PROCESS_BOOKKEEPING:
        return False
    body = EVENT_BODIES.get(name) if isinstance(name, str) else None
    if body is not None and issubclass(body, ProcessEnd):
        return fields.get(_EXIT_CODE_FIELD) != 0
    if body is not None and issubclass(body, SpanEnded):
        return fields.get(_STATUS_FIELD) == "ERROR"
    return fields.get(_LEVEL_FIELD) == "standard"


@dataclass(frozen=True, slots=True)
class EventSelection:
    """Which Runtime Events a reader keeps.

    A filter on an identity matches the field wherever the event carries it,
    in its process's identity or in its own body, so an event a later
    Dashpot adds is selected by the same names. ``level`` of ``standard``
    keeps the events that belong to it; ``full``, or none, keeps every
    event. ``exclude_run`` leaves out one process's own events, as a reader
    leaves out itself. ``outcomes_only`` keeps only what
    :func:`is_session_outcome` counts as an outcome.
    """

    session: str | None = None
    harness: Harness | None = None
    issue: str | None = None
    project: str | None = None
    since: datetime | None = None
    level: RecordedLevel | None = None
    exclude_run: str | None = None
    outcomes_only: bool = False

    @property
    def first_day(self) -> date | None:
        """The earliest UTC day whose file can hold a selected event.

        A span is stamped when it started and written when it ended, so a
        file never holds an event from after its own day.
        """
        return None if self.since is None else self.since.astimezone(UTC).date()

    def _identity_filters(self) -> dict[str, str]:
        """The identity fields this selection filters on, by their on-disk names."""
        return {
            field: value
            for field, value in (
                (SESSION_FIELD, self.session),
                (HARNESS_FIELD, self.harness),
                (ISSUE_FIELD, self.issue),
                (PROJECT_FIELD, self.project),
            )
            if value is not None
        }

    def may_admit(self, fields: Mapping[str, object]) -> bool:
        """Whether a line with these raw fields may hold an event this selection keeps.

        It reads the line as decoded, before it is validated, and says no
        only where :meth:`admits` would refuse the event the line validates
        to, so a reader validates only the lines it may keep. Validation is
        strict, so an event's values are its line's values unchanged.
        """
        if self.level == "standard" and fields.get(_LEVEL_FIELD) != "standard":
            return False
        if self.exclude_run is not None and fields.get(_RUN_FIELD) == self.exclude_run:
            return False
        stamp = fields.get(_TIME_FIELD)
        if (
            self.since is not None
            and isinstance(stamp, str)
            and observed_instant(stamp) < self.since
        ):
            return False
        if self.outcomes_only and not _may_be_outcome(fields):
            return False
        attributes = fields.get("attributes")
        # A validated span's attributes keep only the fields its kind knows,
        # so either place may be the one :meth:`admits` reads.
        return all(
            fields.get(field) == value
            or (isinstance(attributes, Mapping) and attributes.get(field) == value)
            for field, value in self._identity_filters().items()
        )

    def admits(self, event: RuntimeEvent) -> bool:
        """Whether the event is one this selection keeps.

        :meth:`may_admit` asks the same of a line's raw fields, so a filter
        added here is added there too.
        """
        if self.level == "standard" and event.level != "standard":
            return False
        if self.exclude_run is not None and event.process.run_id == self.exclude_run:
            return False
        if self.since is not None and event_instant(event) < self.since:
            return False
        if self.outcomes_only and not is_session_outcome(event):
            return False
        wanted = self._identity_filters()
        if not wanted:
            return True
        fields = event_fields(event)
        # A span carries its own identifiers — an observation's Project —
        # among its attributes, and they name its work more closely than
        # its process's identity does.
        attributes = fields.get("attributes")
        if isinstance(attributes, Mapping):
            fields = {**fields, **attributes}
        return all(fields.get(field) == value for field, value in wanted.items())


@dataclass(frozen=True, slots=True)
class UnreadableEventLog:
    """A file whose lines, or the whole of it, could not be read as events.

    ``lines`` are 1-based line numbers; ``error`` names why the file or its
    directory could not be read at all.
    """

    path: str
    lines: tuple[int, ...] = ()
    error: str | None = None


def _error_text(error: OSError) -> str:
    return error.strerror or type(error).__name__


def _read_file(
    file: Path, selection: EventSelection
) -> tuple[list[RuntimeEvent], UnreadableEventLog | None]:
    """The selected events of one file, and what of it could not be read.

    A line that is not a JSON object naming an event this Dashpot knows is
    always unreadable. A known event's line the selection leaves out by its
    raw fields is not validated, so it is never reported, readable or not.
    """
    events: list[RuntimeEvent] = []
    bad: list[int] = []
    try:
        with file.open("rb") as stream:
            for number, line in enumerate(stream, start=1):
                fields = runtime_event_fields(line)
                if fields is None:
                    bad.append(number)
                    continue
                if not selection.may_admit(fields):
                    continue
                event = runtime_event_from_fields(fields)
                if event is None:
                    bad.append(number)
                elif selection.admits(event):
                    events.append(event)
    except FileNotFoundError:
        # Removed between listing and reading: there is nothing left to read.
        return [], None
    except OSError as exc:
        return events, UnreadableEventLog(
            path=str(file), lines=tuple(bad), error=_error_text(exc)
        )
    if not bad:
        return events, None
    return events, UnreadableEventLog(path=str(file), lines=tuple(bad))


def _files_by_day(
    directories: Iterable[Path],
    first_day: date | None,
    report: Callable[[UnreadableEventLog], None],
) -> dict[date, list[Path]]:
    """Every Event Log file from ``first_day`` on, by its UTC day, in directory order."""
    by_day: dict[date, list[Path]] = {}
    for directory in directories:
        try:
            files = event_log_files(directory)
        except OSError as exc:
            report(UnreadableEventLog(path=str(directory), error=_error_text(exc)))
            continue
        for file in files:
            if first_day is None or file.day >= first_day:
                by_day.setdefault(file.day, []).append(file.path)
    return by_day


def _ignore(_unreadable: UnreadableEventLog) -> None:
    return None


def read_event_logs(
    directories: Sequence[Path],
    selection: EventSelection,
    *,
    unreadable: Callable[[UnreadableEventLog], None],
) -> Iterator[RuntimeEvent]:
    """Stream the selected events of every Event Log in ``directories``, oldest first.

    Files are read one UTC day at a time, each directory's files of that day
    in turn. A span is stamped when it started but written to the file of
    the day it ended, so an event is held back until it is older than
    :data:`SPAN_CARRY_OVER` before the next day's files, which then cannot
    hold an earlier one; a span stamped longer than that before its file's
    day comes out once its file is read, after later events already
    yielded. Events of one instant keep the order of their files' days,
    then their directories, files and lines. ``unreadable`` is told of each
    file, directory or line that could not be read as it is met; reading
    stops where the caller stops taking events.
    """
    by_day = _files_by_day(directories, selection.first_day, unreadable)
    days = sorted(by_day)
    held: list[tuple[datetime, int, RuntimeEvent]] = []
    order = itertools.count()
    for index, day in enumerate(days):
        for path in by_day[day]:
            selected, problem = _read_file(path, selection)
            for event in selected:
                heapq.heappush(held, (event_instant(event), next(order), event))
            if problem is not None:
                unreadable(problem)
        following = days[index + 1] if index + 1 < len(days) else None
        settled = (
            None
            if following is None
            else datetime.combine(following, time.min, UTC) - SPAN_CARRY_OVER
        )
        while held and (settled is None or held[0][0] < settled):
            yield heapq.heappop(held)[2]


def recent_events(
    directories: Sequence[Path],
    selection: EventSelection,
    *,
    limit: int,
) -> list[RuntimeEvent]:
    """The ``limit`` most recent selected events, reading back only as far as needed.

    Days are read newest first across every directory, and reading stops
    once a day's start leaves ``limit`` events after it, since no earlier
    file holds a later event. ``selection.since`` bounds how far back.
    Unreadable lines are skipped without a word: this is a summary, and
    ``dashpot events`` is where they are reported.
    """
    by_day = _files_by_day(directories, selection.first_day, _ignore)
    found: list[RuntimeEvent] = []
    for day in sorted(by_day, reverse=True):
        for path in by_day[day]:
            found.extend(_read_file(path, selection)[0])
        start = datetime.combine(day, time.min, UTC)
        if sum(1 for event in found if event_instant(event) >= start) >= limit:
            break
    found.sort(key=event_instant)
    return found[-limit:] if limit > 0 else []


def _field_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _details(fields: Mapping[str, object]) -> Iterator[str]:
    for field, value in fields.items():
        if field in _HEADLINE_FIELDS:
            continue
        if isinstance(value, Mapping):
            yield from _details(value)
        else:
            yield f"{field}={_field_text(value)}"


def describe_runtime_event(event: RuntimeEvent) -> str:
    """One line for a person: time, level, process kind, event name, then its fields."""
    fields = event_fields(event)
    return " ".join(
        (
            event.time,
            event.level,
            event.process.kind,
            str(fields["event.name"]),
            *_details(fields),
        )
    )


FileOutcome = Literal["planned", "removed", "already-absent", "failed"]


class EventLogFileRemoval(PublishedModel):
    """One Event Log file a removal selected, and what became of it."""

    path: str
    day: date
    size_bytes: int | None
    outcome: FileOutcome
    error: str | None = None


class EventLogRemoval(PublishedModel):
    """What ``dashpot events remove`` removed from one Event Log directory.

    ``before`` is the day asked for; a file is selected only when its day is
    before both it and ``today``. A dry run lists each selected file as
    ``planned`` and removes nothing.
    """

    directory: str
    before: date
    today: date
    dry_run: bool
    files: LaxSequence[EventLogFileRemoval] = ()

    @computed_field
    @property
    def succeeded(self) -> bool:
        """Every selected file was removed, planned, or was already gone."""
        return all(file.outcome != "failed" for file in self.files)


def _size(path: Path) -> int | None:
    try:
        return path.lstat().st_size
    except OSError:
        return None


def remove_event_logs(
    destination: EventLogDestination,
    before: date,
    *,
    today: date | None = None,
    dry_run: bool = False,
) -> EventLogRemoval:
    """Remove the Event Log files of one directory dated before ``before``.

    A file dated today or later is never selected, whatever ``before`` says.
    A file that cannot be removed is reported and the rest are still tried.
    """
    current = today if today is not None else datetime.now(UTC).date()
    cutoff = min(before, current)
    directory = destination.directory
    try:
        files = [file for file in event_log_files(directory) if file.day < cutoff]
    except OSError as exc:
        raise EventLogError(
            f"cannot list the Event Log in {directory}: {_error_text(exc)}"
        ) from exc
    removals: list[EventLogFileRemoval] = []
    for file in files:
        size = _size(file.path)
        outcome: FileOutcome = "planned"
        error: str | None = None
        if not dry_run:
            try:
                file.path.unlink()
            except FileNotFoundError:
                outcome = "already-absent"
            except OSError as exc:
                outcome, error = "failed", _error_text(exc)
            else:
                outcome = "removed"
        removals.append(
            EventLogFileRemoval(
                path=str(file.path),
                day=file.day,
                size_bytes=size,
                outcome=outcome,
                error=error,
            )
        )
    return EventLogRemoval(
        directory=str(directory),
        before=before,
        today=current,
        dry_run=dry_run,
        files=removals,
    )


def describe_event_log_removal(removal: EventLogRemoval) -> list[str]:
    """One line per selected file, or one saying there was nothing to remove."""
    if not removal.files:
        return [
            f"no Event Log files dated before {min(removal.before, removal.today)} "
            f"in {removal.directory}"
        ]
    verbs: dict[FileOutcome, str] = {
        "planned": "would remove",
        "removed": "removed",
        "already-absent": "already gone",
        "failed": "could not remove",
    }
    lines: list[str] = []
    for file in removal.files:
        size = "" if file.size_bytes is None else f" ({file.size_bytes} bytes)"
        reason = "" if file.error is None else f": {file.error}"
        lines.append(f"{verbs[file.outcome]} {file.path}{size}{reason}")
    return lines


def event_log_size(directory: Path) -> int:
    """The bytes the Event Log files in ``directory`` hold together."""
    return sum(_size(file.path) or 0 for file in event_log_files(directory))


def event_log_large_diagnostic(
    destination: EventLogDestination, size: int
) -> Diagnostic | None:
    """Warn that an Event Log directory passed its size, naming how to remove old files.

    Dashpot never removes the files itself; the warning acts on nothing.
    """
    if size <= LARGE_EVENT_LOG_BYTES:
        return None
    where = (
        "outside every configured checkout"
        if destination.checkout is None
        else f"in {destination.checkout}"
    )
    return Diagnostic(
        source="event-log",
        severity="warning",
        code=EVENT_LOG_LARGE,
        message=(
            f"The Event Log in {destination.directory} holds "
            f"{size / 1_000_000:.0f} MB, past "
            f"{LARGE_EVENT_LOG_BYTES // 1_000_000} MB; remove old files with "
            f"'dashpot events remove --before DATE' run {where}"
        ),
    )
