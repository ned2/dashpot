"""Aggregate a running dashboard's recent Runtime Events into its Runtime Stats.

Every figure is computed when read, from the events a dashboard keeps in
memory: nothing here keeps a running total, and nothing is counted beside
the events (ADR 0059). The counting rule reads the Event Log's files; the
buffer holds every event at full detail whatever the level in force, so
every event in it counts. Each aggregation is a pure
function over events, so a section is one function more.
"""

from __future__ import annotations

import os
import resource
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import get_args

from .runtime_events import (
    CommandAttributes,
    EventLogWriteFailed,
    GitHubRequestAttributes,
    KeyOutcome,
    ObservationAttributes,
    QueryAttributes,
    RefreshAttributes,
    RefreshTrigger,
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
    longest. A failure is a failed span: the command could not be run, or
    its caller declared its exit a failure, never a non-zero exit read as an
    answer.
    """

    program: str
    count: int
    typical_seconds: float
    worst_seconds: float
    failures: int


def command_stats(events: Iterable[RuntimeEvent]) -> tuple[CommandStats, ...]:
    """Every program's command spans, the most run first."""
    commands: dict[str, list[SpanEnded]] = {}
    for span in _spans(events):
        if span.span_name == "command" and isinstance(
            span.attributes, CommandAttributes
        ):
            commands.setdefault(span.attributes.program, []).append(span)
    stats = (
        CommandStats(
            program,
            len(taken),
            *_typical_and_worst([span.duration_seconds for span in taken]),
            failures=sum(span.status == "ERROR" for span in taken),
        )
        for program, taken in commands.items()
    )
    return tuple(sorted(stats, key=lambda stat: (-stat.count, stat.program)))


def write_failures(events: Iterable[RuntimeEvent]) -> int:
    """How many Runtime Events were dropped because the Event Log could not take them."""
    return sum(isinstance(event.body, EventLogWriteFailed) for event in events)


def _spans(events: Iterable[RuntimeEvent]) -> Iterator[SpanEnded]:
    for event in events:
        if isinstance(event.body, SpanEnded):
            yield event.body


def _typical_and_worst(durations: Sequence[float]) -> tuple[float, float]:
    """The median and the longest of ``durations``, of which there is at least one."""
    return median(durations), max(durations)


# -- GitHub allowance ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OperationSpend:
    """The GitHub requests of one operation: how many, and the points they cost.

    ``operation`` is the GraphQL operation's name, or the API (``graphql``,
    ``rest``) of a request that names none. ``points`` sums the cost each
    response reported; a request whose response reported none adds nothing.
    """

    operation: str
    requests: int
    points: int
    failures: int


def _requests(
    events: Iterable[RuntimeEvent],
) -> Iterator[tuple[SpanEnded, GitHubRequestAttributes]]:
    for span in _spans(events):
        if span.span_name == "github.request" and isinstance(
            span.attributes, GitHubRequestAttributes
        ):
            yield span, span.attributes


def github_spend(events: Iterable[RuntimeEvent]) -> tuple[OperationSpend, ...]:
    """Every operation's GitHub requests, the costliest first."""
    requests: dict[str, list[tuple[SpanEnded, GitHubRequestAttributes]]] = {}
    for span, attributes in _requests(events):
        name = attributes.operation or attributes.api
        requests.setdefault(name, []).append((span, attributes))
    spend = (
        OperationSpend(
            operation=name,
            requests=len(taken),
            points=sum(attributes.cost or 0 for _, attributes in taken),
            failures=sum(span.status == "ERROR" for span, _ in taken),
        )
        for name, taken in requests.items()
    )
    return tuple(
        sorted(spend, key=lambda each: (-each.points, -each.requests, each.operation))
    )


@dataclass(frozen=True, slots=True)
class RefreshSpend:
    """The GitHub requests of the latest refresh that made any, and what fired it."""

    trigger: RefreshTrigger
    started: str
    requests: tuple[RuntimeEvent, ...]


def _root(span: SpanEnded, spans: dict[str, SpanEnded]) -> SpanEnded | None:
    """The outermost recorded span ``span`` runs inside, itself when it has no parent."""
    seen = {span.span_id}
    while span.parent_span_id is not None:
        parent = spans.get(span.parent_span_id)
        if parent is None or parent.span_id in seen:
            # A parent still running, or one the buffer let go of.
            return None
        seen.add(parent.span_id)
        span = parent
    return span


def last_github_refresh(events: Sequence[RuntimeEvent]) -> RefreshSpend | None:
    """The latest ended refresh that sent GitHub requests, with those requests.

    A refresh span is recorded when its last key lands, so one still running
    has not yet been counted and the one before it is the latest.
    """
    spans = {span.span_id: span for span in _spans(events)}
    started = {
        event.body.span_id: event.time
        for event in events
        if isinstance(event.body, SpanEnded)
    }
    by_refresh: dict[str, list[RuntimeEvent]] = {}
    for event in events:
        body = event.body
        if not isinstance(body, SpanEnded) or body.span_name != "github.request":
            continue
        root = _root(body, spans)
        if root is not None and isinstance(root.attributes, RefreshAttributes):
            by_refresh.setdefault(root.span_id, []).append(event)
    if not by_refresh:
        return None
    latest = max(by_refresh, key=lambda span_id: started[span_id])
    attributes = spans[latest].attributes
    assert isinstance(attributes, RefreshAttributes)
    return RefreshSpend(attributes.trigger, started[latest], tuple(by_refresh[latest]))


def account_spend(events: Iterable[RuntimeEvent]) -> int | None:
    """The points the rest of the account spent while these requests ran.

    Within one rate limit window the points only fall, so the change in
    points used between the requests' readings, less what this dashboard's
    own later requests cost, is what everything else spent. Windows are
    counted apart, since a reset refills the points; without two readings in
    any window there is nothing to compare, and ``None``.
    """
    windows: dict[str, list[tuple[int, int]]] = {}
    for _, attributes in _requests(events):
        if attributes.remaining is None or attributes.reset_at is None:
            continue
        windows.setdefault(attributes.reset_at, []).append(
            (attributes.remaining, attributes.cost or 0)
        )
    spent: int | None = None
    for readings in windows.values():
        if len(readings) < 2:
            continue
        # The reading with the most points left came first, the earliest
        # recorded among equals; its own cost was spent before it, and every
        # other request's after it.
        first = max(readings, key=lambda reading: reading[0])
        used = first[0] - min(remaining for remaining, _ in readings)
        own = sum(cost for _, cost in readings) - first[1]
        # Answers to concurrent requests can cross, so the difference is
        # never allowed below nothing.
        spent = (spent or 0) + max(0, used - own)
    return spent


# -- Refresh health -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefreshHealth:
    """The refreshes one trigger fired: how many, how long, and their keys not run.

    ``skipped`` counts keys that were not run because the key was busy, and
    ``dropped`` keys a newer request replaced while they waited.
    """

    trigger: RefreshTrigger
    count: int
    typical_seconds: float
    worst_seconds: float
    skipped: int
    dropped: int


@dataclass(frozen=True, slots=True)
class KeyHealth:
    """One observation or query key: how long it took when run, and when it was not.

    ``key`` names the kind of span and the key: ``observation targets``,
    ``query issues``. The durations are of the times it ran, ``None`` when it
    never did; ``failures`` counts runs whose work could not be done.
    """

    key: str
    runs: int
    typical_seconds: float | None
    worst_seconds: float | None
    skipped: int
    dropped: int
    failures: int


def _key_and_outcome(span: SpanEnded) -> tuple[str, KeyOutcome | None] | None:
    """The key a key span ran and how it ended, or ``None`` for any other span."""
    attributes = span.attributes
    if isinstance(attributes, ObservationAttributes):
        return f"observation {attributes.kind}", attributes.outcome
    if isinstance(attributes, QueryAttributes):
        return f"query {attributes.key}", attributes.outcome
    return None


# A key that was not run has no duration of its own worth timing.
_NOT_RUN: frozenset[KeyOutcome | None] = frozenset({"skipped", "dropped"})


def refresh_health(events: Iterable[RuntimeEvent]) -> tuple[RefreshHealth, ...]:
    """Every trigger's refreshes, in the order the triggers are named."""
    spans = list(_spans(events))
    triggers: dict[str, RefreshTrigger] = {}
    durations: dict[RefreshTrigger, list[float]] = {}
    for span in spans:
        if isinstance(span.attributes, RefreshAttributes):
            triggers[span.span_id] = span.attributes.trigger
            durations.setdefault(span.attributes.trigger, []).append(
                span.duration_seconds
            )
    not_run: dict[tuple[RefreshTrigger, KeyOutcome | None], int] = {}
    for span in spans:
        keyed = _key_and_outcome(span)
        trigger = triggers.get(span.parent_span_id or "")
        if keyed is None or trigger is None:
            continue
        _, outcome = keyed
        if outcome in _NOT_RUN:
            not_run[trigger, outcome] = not_run.get((trigger, outcome), 0) + 1
    order = get_args(RefreshTrigger)
    return tuple(
        RefreshHealth(
            trigger,
            len(taken),
            *_typical_and_worst(taken),
            skipped=not_run.get((trigger, "skipped"), 0),
            dropped=not_run.get((trigger, "dropped"), 0),
        )
        for trigger, taken in sorted(
            durations.items(), key=lambda item: order.index(item[0])
        )
    )


def key_health(events: Iterable[RuntimeEvent]) -> tuple[KeyHealth, ...]:
    """Every observation and query key, whether a refresh or a person asked for it."""
    runs: dict[str, list[SpanEnded]] = {}
    outcomes: dict[tuple[str, KeyOutcome | None], int] = {}
    for span in _spans(events):
        keyed = _key_and_outcome(span)
        if keyed is None:
            continue
        key, outcome = keyed
        runs.setdefault(key, [])
        if outcome in _NOT_RUN:
            outcomes[key, outcome] = outcomes.get((key, outcome), 0) + 1
        else:
            runs[key].append(span)
    return tuple(
        KeyHealth(
            key,
            len(ran),
            *(
                _typical_and_worst([span.duration_seconds for span in ran])
                if ran
                else (None, None)
            ),
            skipped=outcomes.get((key, "skipped"), 0),
            dropped=outcomes.get((key, "dropped"), 0),
            failures=sum(span.status == "ERROR" for span in ran),
        )
        for key, ran in sorted(runs.items())
    )


# -- This process -------------------------------------------------------------


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
