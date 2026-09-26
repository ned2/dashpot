"""Aggregate a running dashboard's recent Runtime Events into its Runtime Stats.

Every figure is computed when read, from the events a dashboard keeps in
memory: nothing here keeps a running total, and nothing is counted beside
the events (ADR 0059). The buffer holds every event at full detail whatever
the level in force, so every event in it counts. Each aggregation is a pure
function over events, so a section is one function more.
"""

from __future__ import annotations

import os
import resource
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from .runtime_events import (
    CommandAttributes,
    EventLogWriteFailed,
    RuntimeEvent,
    SpanEnded,
)
from .timestamps import observed_instant, utc_stamp

# Where Linux reports this process's memory, in pages.
PROC_STATM = Path("/proc/self/statm")


def events_since(
    events: Iterable[RuntimeEvent], moment: datetime
) -> tuple[RuntimeEvent, ...]:
    """The events stamped at or after ``moment``, in the order given."""
    cutoff = utc_stamp(moment)
    # Stamps are fixed-width UTC, so they order as text.
    return tuple(event for event in events if event.time >= cutoff)


def covered_since(
    events: Sequence[RuntimeEvent],
    *,
    now: datetime,
    window: timedelta,
    limit: int | None,
) -> datetime:
    """How far back a full buffer of ``events`` reaches within ``window`` of ``now``.

    A buffer holding ``limit`` events has let go of older ones by count, not
    age, so its figures reach back only to its oldest event.
    """
    start = now - window
    if limit is None or len(events) < limit or not events:
        return start
    return max(start, min(observed_instant(event.time) for event in events))


@dataclass(frozen=True, slots=True)
class CommandStats:
    """The external commands of one program: how many, how long, how many failed.

    ``typical_seconds`` is the median duration and ``worst_seconds`` the
    longest. A failure is a command that could not be run, never a non-zero
    exit read as an answer.
    """

    program: str
    count: int
    typical_seconds: float
    worst_seconds: float
    failures: int


def command_stats(events: Iterable[RuntimeEvent]) -> tuple[CommandStats, ...]:
    """Every program's command spans, the most run first."""
    durations: dict[str, list[float]] = {}
    failures: dict[str, int] = {}
    for event in events:
        body = event.body
        if not isinstance(body, SpanEnded) or body.span_name != "command":
            continue
        attributes = body.attributes
        if not isinstance(attributes, CommandAttributes):
            continue
        durations.setdefault(attributes.program, []).append(body.duration_seconds)
        failures[attributes.program] = failures.get(attributes.program, 0) + int(
            body.status == "ERROR"
        )
    stats = (
        CommandStats(
            program=program,
            count=len(taken),
            typical_seconds=median(taken),
            worst_seconds=max(taken),
            failures=failures[program],
        )
        for program, taken in durations.items()
    )
    return tuple(sorted(stats, key=lambda stat: (-stat.count, stat.program)))


def write_failures(events: Iterable[RuntimeEvent]) -> int:
    """How many Runtime Events were dropped because the Event Log could not take them."""
    return sum(isinstance(event.body, EventLogWriteFailed) for event in events)


@dataclass(frozen=True, slots=True)
class ResidentMemory:
    """This process's resident set size; ``peak`` when only the peak is known."""

    bytes: int
    peak: bool


def resident_memory(statm: Path = PROC_STATM) -> ResidentMemory:
    """The process's current resident set size, else the peak it has reached.

    Linux reports the current size in ``/proc/self/statm`` without starting
    a process; elsewhere ``getrusage`` reports only the peak, which macOS
    counts in bytes and Linux in KiB.
    """
    try:
        pages = int(statm.read_text().split()[1])
    except (OSError, ValueError, IndexError):
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ResidentMemory(peak if sys.platform == "darwin" else peak * 1024, True)
    return ResidentMemory(pages * os.sysconf("SC_PAGE_SIZE"), False)
