"""The Runtime Stats screen: what this dashboard spends and how it runs.

Laid out like the Legend, it shows sections computed when read from the
dashboard's in-memory buffer of recent Runtime Events — GitHub requests and
their points, refreshes and their keys, commands — beside the GitHub rate
limit reading the Query Sources share and what ``process.start`` recorded. It keeps no figure of its own between updates and sends no
request: it redraws from what the dashboard already holds, on a short
interval while it is open. Its one action changes the Event Level for the
rest of the run.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import ClassVar, Protocol, override

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Static

from ..core.event_log import DASHBOARD_RECENT_WINDOW, EventLog
from ..core.runtime_events import EVENT_LEVELS, EventLevel, ProcessStart
from ..core.runtime_stats import (
    CommandStats,
    KeyHealth,
    OperationSpend,
    RefreshHealth,
    RefreshSpend,
    ResidentMemory,
    account_spend,
    command_stats,
    covered_since,
    events_since,
    github_spend,
    key_health,
    last_github_refresh,
    refresh_health,
    resident_memory,
    write_failures,
)
from ..core.timestamps import observed_instant
from ..github.github import LatestRateLimit, RateLimit

ALLOWANCE_LABEL = "GITHUB ALLOWANCE"
SPEND_LABEL = "GITHUB REQUESTS"
REFRESHES_LABEL = "REFRESHES"
KEYS_LABEL = "REFRESH KEYS"
COMMANDS_LABEL = "COMMANDS"
PROCESS_LABEL = "THIS PROCESS"
# Each section's id and its heading before its window is known.
SECTIONS = (
    ("allowance", ALLOWANCE_LABEL),
    ("refresh-spend", SPEND_LABEL),
    ("window-spend", SPEND_LABEL),
    ("refreshes", REFRESHES_LABEL),
    ("keys", KEYS_LABEL),
    ("commands", COMMANDS_LABEL),
    ("process", PROCESS_LABEL),
)
# The width of a row's label column, so values line up down a section.
LABEL_WIDTH = 16


class RuntimeStatsSubject(Protocol):
    """What the screen reads from the dashboard that opened it, and its one action."""

    @property
    def event_log(self) -> EventLog:
        """This run's Event Log, whose buffer holds the recent Runtime Events."""
        ...

    @property
    def rate_limit(self) -> LatestRateLimit | None:
        """The rate limit reading the Query Sources share, if they read GitHub."""
        ...

    @property
    def event_log_bytes(self) -> int | None:
        """The Event Log directory's size when last measured, if it has been."""
        ...

    def set_event_level(self, level: EventLevel) -> None:
        """Change the level in force for the rest of the run."""
        ...

    def measure_event_log(self) -> None:
        """Measure the Event Log directory off the loop."""
        ...


def duration_text(seconds: float) -> str:
    """A command's duration, in the unit that reads best."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    return uptime_text(seconds)


def uptime_text(seconds: float) -> str:
    """A long duration in days, hours, minutes and seconds, leading unit first."""
    whole = int(seconds)
    days, rest = divmod(whole, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def size_text(size: int) -> str:
    """A size in decimal units, as the ``event-log-large`` Diagnostic counts them."""
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def window_text(since: datetime, *, now: datetime, started: datetime) -> str:
    """Name the span of time the aggregated sections cover."""
    if since <= started:
        return "since start"
    if now - since >= DASHBOARD_RECENT_WINDOW:
        return "last hour"
    # A full buffer let go of older events by count before the hour was up.
    return f"last {uptime_text((now - since).total_seconds())}, buffer full"


def rows(pairs: Sequence[tuple[str, str]]) -> Text:
    """Label and value lines, the values aligned."""
    text = Text()
    for index, (label, value) in enumerate(pairs):
        if index:
            text.append("\n")
        text.append(label.ljust(LABEL_WIDTH), style="bold")
        text.append(value)
    return text


def note(message: str) -> Text:
    return Text(message, style="dim italic")


def points_text(points: int) -> str:
    return f"{points:,} point" if points == 1 else f"{points:,} points"


def allowance_text(
    reading: RateLimit | None, *, others: int | None, window: str, now: datetime
) -> Text:
    """The latest rate limit reading any Query Source received, and the rest's spend.

    ``others`` is what the rest of the account spent within ``window``,
    beside this dashboard's own requests.
    """
    if reading is None:
        return note("no GitHub response has reported the rate limit yet")
    reset = observed_instant(reading.reset_at)
    left = max(0.0, (reset - now).total_seconds())
    return rows(
        (
            ("remaining", f"{reading.remaining:,} of {points_text(reading.limit)}"),
            ("resets", f"{reset:%H:%M:%S} UTC, in {uptime_text(left)}"),
            ("last request", points_text(reading.cost)),
            (
                "rest of account",
                "not known until two readings share a window"
                if others is None
                else f"{points_text(others)} {window}",
            ),
        )
    )


def table_text(header: Sequence[str], body: Sequence[Sequence[str]]) -> Text:
    """A table: its first column left-aligned, the figures after it right-aligned."""
    table = [tuple(header), *(tuple(row) for row in body)]
    widths = [max(len(row[column]) for row in table) for column in range(len(header))]
    text = Text()
    for index, row in enumerate(table):
        if index:
            text.append("\n")
        cells = [
            row[0].ljust(widths[0]),
            *(
                cell.rjust(width)
                for cell, width in zip(row[1:], widths[1:], strict=True)
            ),
        ]
        text.append("  ".join(cells), style="bold" if index == 0 else "")
    return text


def spend_text(spend: Sequence[OperationSpend]) -> Text:
    """Every operation's GitHub requests and the points they cost."""
    if not spend:
        return note("no GitHub requests recorded")
    return table_text(
        ("operation", "requests", "points", "failed"),
        [
            (
                each.operation,
                f"{each.requests:,}",
                f"{each.points:,}",
                f"{each.failures:,}",
            )
            for each in spend
        ],
    )


def last_refresh_heading(refresh: RefreshSpend | None) -> str:
    if refresh is None:
        return f"{SPEND_LABEL} · last refresh"
    at = observed_instant(refresh.started)
    return f"{SPEND_LABEL} · last refresh, {refresh.trigger} at {at:%H:%M:%S} UTC"


def refreshes_text(health: Sequence[RefreshHealth]) -> Text:
    """Every trigger's refreshes: how many, how long, and the keys they did not run."""
    if not health:
        return note("no refreshes recorded")
    return table_text(
        ("trigger", "count", "typical", "worst", "skipped", "dropped"),
        [
            (
                each.trigger,
                f"{each.count:,}",
                duration_text(each.typical_seconds),
                duration_text(each.worst_seconds),
                f"{each.skipped:,}",
                f"{each.dropped:,}",
            )
            for each in health
        ],
    )


def keys_text(health: Sequence[KeyHealth]) -> Text:
    """Every key's runs, how long they took, the times it was not run, and failures."""
    if not health:
        return note("no observations or queries recorded")
    return table_text(
        ("key", "runs", "typical", "worst", "skipped", "dropped", "failed"),
        [
            (
                each.key,
                f"{each.runs:,}",
                duration_text(each.typical_seconds),
                duration_text(each.worst_seconds),
                f"{each.skipped:,}",
                f"{each.dropped:,}",
                f"{each.failures:,}",
            )
            for each in health
        ],
    )


def commands_text(stats: Sequence[CommandStats]) -> Text:
    """Every program's commands: how many, how long typically and at worst, and failures."""
    if not stats:
        return note("no commands recorded")
    return table_text(
        ("program", "count", "typical", "worst", "failed"),
        [
            (
                stat.program,
                f"{stat.count:,}",
                duration_text(stat.typical_seconds),
                duration_text(stat.worst_seconds),
                f"{stat.failures:,}",
            )
            for stat in stats
        ],
    )


def source_text(facts: ProcessStart | None) -> tuple[tuple[str, str], ...]:
    """The version and commit ``process.start`` recorded."""
    if facts is None:
        return (("version", "not recorded"),)
    dirty = {True: "uncommitted changes", False: "clean", None: "not checked"}[
        facts.source_dirty
    ]
    commit = facts.revision if facts.revision == "unknown" else facts.revision[:12]
    return (
        ("version", f"{facts.version} ({facts.install_kind})"),
        ("commit", f"{commit} · {dirty}"),
    )


def memory_text(memory: ResidentMemory) -> str:
    kind = "peak resident" if memory.peak else "resident"
    return f"{size_text(memory.bytes)} {kind}"


def event_log_rows(log: EventLog, size: int | None) -> tuple[tuple[str, str], ...]:
    """Where the Event Log goes and how large its directory was when last measured."""
    destination = log.destination
    if destination is None:
        return (("Event Log", "none; events are kept in memory only"),)
    return (
        ("Event Log", str(destination.directory)),
        ("size", "not measured yet" if size is None else size_text(size)),
    )


def process_text(
    log: EventLog,
    *,
    failures: int,
    window: str,
    size: int | None,
    memory: ResidentMemory,
) -> Text:
    """What the process is, how long it has run, and where its Event Log goes.

    ``failures`` counts the writes dropped within ``window``; the first
    failure's error stays named however long ago it was.
    """
    first = "" if log.write_failure is None else f", first {log.write_failure}"
    return rows(
        (
            *source_text(log.facts),
            ("uptime", uptime_text(log.uptime_seconds())),
            ("memory", memory_text(memory)),
            *event_log_rows(log, size),
            ("level", f"{log.level} · l changes it for this run"),
            ("write failures", f"{failures:,} {window}{first}"),
        )
    )


def next_level(level: EventLevel) -> EventLevel:
    """The level after ``level``, wrapping from ``full`` back to ``off``."""
    return EVENT_LEVELS[(EVENT_LEVELS.index(level) + 1) % len(EVENT_LEVELS)]


class RuntimeStatsScreen(ModalScreen[None]):
    """Show what this dashboard spends and how it runs, updating while open."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "close", "Close"),
        ("s", "close", "Close"),
        ("l", "cycle_level", "Change Event Level"),
    ]

    def __init__(self, subject: RuntimeStatsSubject, *, update_seconds: float) -> None:
        super().__init__()
        self.subject = subject
        self.update_seconds = update_seconds
        self.update_timer: Timer | None = None

    @override
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="runtime-stats-dialog"):
            yield Static("RUNTIME STATS", id="runtime-stats-title")
            for name, label in SECTIONS:
                yield Static(
                    label, classes="legend-heading", id=f"stats-{name}-heading"
                )
                yield Static("", classes="legend-section", id=f"stats-{name}")

    def on_mount(self) -> None:
        self.subject.measure_event_log()
        self.update_stats()
        self.update_timer = self.set_interval(self.update_seconds, self.update_stats)

    def show(self, name: str, content: Text, heading: str | None = None) -> None:
        """Replace one section, and its heading when the heading names a window."""
        self.query_one(f"#stats-{name}", Static).update(content)
        if heading is not None:
            self.query_one(f"#stats-{name}-heading", Static).update(heading)

    def update_stats(self) -> None:
        """Recompute every section from what the dashboard holds now."""
        log = self.subject.event_log
        now = log.clock()
        buffered = log.recent_events()
        since = covered_since(
            buffered,
            now=now,
            window=DASHBOARD_RECENT_WINDOW,
            limit=log.recent.maxlen,
        )
        window = events_since(buffered, since)
        covered = window_text(
            since, now=now, started=now - timedelta(seconds=log.uptime_seconds())
        )
        shared = self.subject.rate_limit
        self.show(
            "allowance",
            allowance_text(
                None if shared is None else shared.reading,
                others=account_spend(window),
                window=covered,
                now=now,
            ),
        )
        last = last_github_refresh(buffered)
        self.show(
            "refresh-spend",
            spend_text(github_spend(() if last is None else last.requests)),
            last_refresh_heading(last),
        )
        self.show(
            "window-spend",
            spend_text(github_spend(window)),
            f"{SPEND_LABEL} · {covered}",
        )
        self.show(
            "refreshes",
            refreshes_text(refresh_health(window)),
            f"{REFRESHES_LABEL} · {covered}",
        )
        self.show("keys", keys_text(key_health(window)), f"{KEYS_LABEL} · {covered}")
        self.show(
            "commands",
            commands_text(command_stats(window)),
            f"{COMMANDS_LABEL} · {covered}",
        )
        self.show(
            "process",
            process_text(
                log,
                failures=write_failures(window),
                window=covered,
                size=self.subject.event_log_bytes,
                memory=resident_memory(),
            ),
        )

    def action_cycle_level(self) -> None:
        """Move to the next Event Level for the rest of this run, never the settings."""
        self.subject.set_event_level(next_level(self.subject.event_log.level))
        self.update_stats()

    def action_close(self) -> None:
        self.dismiss(None)
