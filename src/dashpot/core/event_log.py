"""Append a process's Runtime Events to its Event Log, and time its work as spans.

One :class:`EventLog` per process holds its destination, its level and its
identity; nothing is configured process-wide, so tests and several apps in
one process never share a writer. Each event is one JSON line appended with
a single ``os.write`` on an ``O_APPEND`` descriptor under a lock the
writer's threads share, which keeps concurrent writers' lines whole on a
local filesystem. A write that fails is dropped: recording the work must
never fail it (ADR 0059).

The span helper mirrors OpenTelemetry's API — :meth:`EventLog.start_span`
returns a span its owner ends, :meth:`EventLog.start_as_current_span` times
a block of synchronous work — so a later exporter would change one module.
The current span lives in a context variable. A span started in one message
and ended in another is held by its owner, which names it as the parent of
the work it schedules.
"""

from __future__ import annotations

import errno
import os
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .distribution import process_start
from .project_state import ensure_state_directory
from .runtime_events import (
    MAX_EVENT_BYTES,
    EventBody,
    EventLevel,
    EventLogWriteFailed,
    LevelChanged,
    ProcessContinued,
    ProcessEnd,
    ProcessIdentity,
    ProcessStart,
    RecordedLevel,
    RuntimeEvent,
    SpanAttributes,
    SpanEnded,
    SpanName,
    is_recorded,
)

DASHBOARD_KIND = "dashboard"
# How many recent events a dashboard keeps in memory for Runtime Stats.
DASHBOARD_RECENT_EVENTS = 10_000
# The error type of an event too long to append whole.
EVENT_TOO_LARGE = "EventTooLarge"


@dataclass(frozen=True, slots=True)
class EventLogDestination:
    """Where one process's Event Log files go.

    ``checkout`` is the configured checkout whose ``.dashpot/state/`` holds
    ``directory``, or ``None`` for the machine-local fallback.
    """

    directory: Path
    checkout: Path | None = None

    def create(self) -> None:
        """Create the directory, and a checkout's self-ignoring state directory before it."""
        if self.checkout is not None:
            ensure_state_directory(self.checkout)
        self.directory.mkdir(parents=True, exist_ok=True)


def new_run_id() -> str:
    """An opaque, random run ID for one process."""
    return secrets.token_hex(16)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return (
        moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def error_type(error: BaseException) -> str:
    """Name an error by its errno or class, never by its message."""
    code = error.errno if isinstance(error, OSError) else None
    if code is not None and code in errno.errorcode:
        return errno.errorcode[code]
    return type(error).__name__


class _Current:
    """The parent a span takes when none is named: the current span."""


CURRENT: Final = _Current()

# The span the running code is inside, if any. A context variable, so an
# executor thread sets it in its own context and keeps the rest of that
# context — the command registry it adopted — as it is.
_current_span: ContextVar[Span | None] = ContextVar(
    "dashpot_current_span", default=None
)


def current_span() -> Span | None:
    """The span the calling code runs inside, if any."""
    return _current_span.get()


@contextmanager
def use_span(span: Span | None) -> Iterator[Span | None]:
    """Make ``span`` current for the block, without ending it."""
    token = _current_span.set(span)
    try:
        yield span
    finally:
        _current_span.reset(token)


def carry_current_span[T](operation: Callable[[], T]) -> Callable[[], T]:
    """Run ``operation`` later, on any thread, inside the span current now.

    The span is set inside the running thread's own context rather than the
    operation being run in a copy of this one, which would replace the
    command registry an executor thread adopted with this thread's.
    """
    span = current_span()

    def run() -> T:
        with use_span(span):
            return operation()

    return run


class Span:
    """A timed unit of work its owner ends, recorded once when it does."""

    def __init__(
        self,
        log: EventLog,
        name: SpanName,
        *,
        parent: Span | None,
        attributes: SpanAttributes | None,
        level: RecordedLevel,
    ) -> None:
        self.log = log
        self.name: SpanName = name
        self.span_id = secrets.token_hex(8)
        self.parent_id = None if parent is None else parent.span_id
        self.attributes = attributes
        self.level: RecordedLevel = level
        self.error_type: str | None = None
        self._started_at = log.clock()
        self._started = log.monotonic()
        self._ended = False

    def set_attributes(self, attributes: SpanAttributes) -> None:
        """Replace the span's attributes, as its work learns them."""
        self.attributes = attributes

    def fail(self, error: str | BaseException) -> None:
        """Mark the span failed: its work could not be done.

        ``error`` is a code or an exception, recorded by its errno or class.
        A non-zero exit read as an answer is not a failure; it belongs in the
        attributes.
        """
        self.error_type = error if isinstance(error, str) else error_type(error)

    @property
    def failed(self) -> bool:
        """Whether the span's work could not be done."""
        return self.error_type is not None

    def end(self) -> None:
        """Record the span; a second end records nothing more."""
        if self._ended:
            return
        self._ended = True
        body = SpanEnded(
            span_name=self.name,
            span_id=self.span_id,
            parent_span_id=self.parent_id,
            duration_seconds=max(0.0, self.log.monotonic() - self._started),
            status="ERROR" if self.failed else "OK",
            error_type=self.error_type,
            attributes=self.attributes,
        )
        # Every failed span is written at ``standard``: a failure is always
        # worth an example, though never a count (ADR 0059).
        level: RecordedLevel = "standard" if self.failed else self.level
        self.log.record(body, level=level, at=self._started_at)


class EventLog:
    """One process's writer of Runtime Events.

    ``destination`` is ``None`` for a writer that keeps events in memory
    only. ``facts`` describes the process for ``process.start`` and every
    ``process.continued``, and is read at most once, when first needed.
    ``keep_recent`` bounds the in-memory buffer of recent events a dashboard
    aggregates; zero keeps none. ``forward``, when set, receives every line
    the level in force records, as Textual's console does while attached.
    """

    def __init__(
        self,
        destination: EventLogDestination | None,
        *,
        identity: ProcessIdentity,
        level: EventLevel,
        facts: Callable[[], ProcessStart],
        keep_recent: int = 0,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        on_write_failure: Callable[[str], None] | None = None,
    ) -> None:
        self.destination = destination
        self.identity = identity
        self.clock = clock
        self.monotonic = monotonic
        self.on_write_failure = on_write_failure
        self.forward: Callable[[str], None] | None = None
        self.recent: deque[RuntimeEvent] = deque(maxlen=keep_recent)
        self.write_failure: str | None = None
        self._level: EventLevel = level
        self._facts_source = facts
        self._facts: ProcessStart | None = None
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._path: Path | None = None
        self._started = monotonic()
        prefix = (
            f"dashboard-{identity.run_id}"
            if identity.kind == DASHBOARD_KIND
            else "events"
        )
        self._prefix = prefix

    @property
    def level(self) -> EventLevel:
        """The level in force."""
        return self._level

    @property
    def path(self) -> Path | None:
        """The file the next event of today goes to, when there is a destination."""
        if self.destination is None:
            return None
        return self._file_for(self.clock())

    def set_level(self, level: EventLevel) -> None:
        """Change the level in force for the rest of the run, marking the change.

        ``level.changed`` is written at the level that records more, so a
        log switched off says so and one switched on says from where.
        """
        previous = self._level
        if level == previous:
            return
        changed = LevelChanged(previous=previous, current=level)
        if previous == "off":
            self._level = level
            self.record(changed)
        else:
            self.record(changed)
            self._level = level

    def identify(
        self,
        *,
        project_id: str | None = None,
        worktree: str | None = None,
        issue_id: str | None = None,
    ) -> None:
        """Name what later events work for, once the process knows it."""
        changes = {
            "project_id": project_id,
            "worktree": worktree,
            "issue_id": issue_id,
        }
        self.identity = ProcessIdentity.model_validate(
            {
                **self.identity.model_dump(),
                **{key: value for key, value in changes.items() if value is not None},
            }
        )

    def start(self) -> None:
        """Record ``process.start``, the process's first event."""
        if self._level == "off" and self.recent.maxlen == 0:
            return
        self.record(self._start_facts())

    def end(self, exit_code: int) -> None:
        """Record ``process.end`` with the exit status and how long the process ran."""
        self.record(
            ProcessEnd(
                exit_code=exit_code,
                duration_seconds=max(0.0, self.monotonic() - self._started),
            )
        )

    def start_span(
        self,
        name: SpanName,
        *,
        attributes: SpanAttributes | None = None,
        parent: Span | _Current | None = CURRENT,
        level: RecordedLevel = "full",
    ) -> Span:
        """Start a span its owner ends; its parent is the current span unless named."""
        return Span(
            self,
            name,
            parent=current_span() if isinstance(parent, _Current) else parent,
            attributes=attributes,
            level=level,
        )

    @contextmanager
    def start_as_current_span(
        self,
        name: SpanName,
        *,
        attributes: SpanAttributes | None = None,
        parent: Span | _Current | None = CURRENT,
        level: RecordedLevel = "full",
    ) -> Iterator[Span]:
        """Time a block of synchronous work as the current span.

        An exception leaving the block means its work could not be done, so
        the span fails with the exception's class and the exception goes on.
        """
        span = self.start_span(name, attributes=attributes, parent=parent, level=level)
        try:
            with use_span(span):
                yield span
        except Exception as exc:
            if not span.failed:
                span.fail(exc)
            raise
        finally:
            span.end()

    def record(
        self,
        body: EventBody,
        *,
        level: RecordedLevel | None = None,
        at: datetime | None = None,
    ) -> None:
        """Record one event: kept in memory, and written when the level records it."""
        event = RuntimeEvent(
            time=_stamp(at if at is not None else self.clock()),
            level=body.LEVEL if level is None else level,
            process=self.identity,
            body=body,
        )
        self.recent.append(event)
        if not is_recorded(event.level, self._level):
            return
        line = event.line()
        forward = self.forward
        if forward is not None:
            forward(line.decode().rstrip("\n"))
        if self.destination is None:
            return
        if len(line) > MAX_EVENT_BYTES:
            self._failed(EVENT_TOO_LARGE)
            return
        try:
            self._append(line, is_start=isinstance(body, ProcessStart))
        except OSError as exc:
            self._failed(error_type(exc))

    def close(self) -> None:
        """Close the open file; a later event opens one again."""
        with self._lock:
            self._close()

    def _append(self, line: bytes, *, is_start: bool) -> None:
        with self._lock:
            path = self._file_for(self.clock())
            opened = self._open(path)
            if opened and not is_start:
                continued = RuntimeEvent(
                    time=_stamp(self.clock()),
                    level="standard",
                    process=self.identity,
                    body=ProcessContinued.model_validate(
                        self._start_facts().model_dump(exclude={"name"})
                    ),
                )
                self._write(continued.line())
            self._write(line)

    def _file_for(self, moment: datetime) -> Path:
        assert self.destination is not None
        day = moment.astimezone(UTC).date().isoformat()
        return self.destination.directory / f"{self._prefix}-{day}.jsonl"

    def _open(self, path: Path) -> bool:
        """Have ``path`` open for appending; whether a file was opened for it."""
        if self._fd is not None and self._path == path and self._still_there(path):
            return False
        self._close()
        assert self.destination is not None
        self.destination.create()
        self._fd = os.open(
            path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o644
        )
        self._path = path
        return True

    def _still_there(self, path: Path) -> bool:
        # A file an outside tool moved or deleted is no longer the one at
        # ``path``; the next line starts a new one there.
        assert self._fd is not None
        try:
            named = os.stat(path)
        except FileNotFoundError:
            return False
        held = os.fstat(self._fd)
        return (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino)

    def _write(self, line: bytes) -> None:
        assert self._fd is not None
        written = os.write(self._fd, line)
        if written != len(line):
            raise OSError(errno.ENOSPC, "short write to the Event Log")

    def _close(self) -> None:
        if self._fd is not None:
            fd, self._fd, self._path = self._fd, None, None
            os.close(fd)

    def _start_facts(self) -> ProcessStart:
        if self._facts is None:
            self._facts = self._facts_source()
        return self._facts

    def _failed(self, error: str) -> None:
        with self._lock, suppress(OSError):
            self._close()
        failure = RuntimeEvent(
            time=_stamp(self.clock()),
            level="standard",
            process=self.identity,
            body=EventLogWriteFailed(error_type=error),
        )
        self.recent.append(failure)
        if self.write_failure is None:
            self.write_failure = error
        if self.on_write_failure is not None:
            self.on_write_failure(error)


def _working_directory() -> Path | None:
    try:
        return Path.cwd()
    except OSError:
        return None


def unrecorded_event_log(
    kind: str = DASHBOARD_KIND, *, keep_recent: int = 0
) -> EventLog:
    """A writer with nowhere to write, keeping only its recent events in memory."""
    return EventLog(
        None,
        identity=ProcessIdentity(run_id=new_run_id(), kind=kind),
        level="off",
        facts=lambda: process_start(_working_directory()),
        keep_recent=keep_recent,
    )
