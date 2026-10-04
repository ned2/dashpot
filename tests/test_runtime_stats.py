"""Runtime Stats shows what a running dashboard spends and how it runs, from its own events."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest
from textual.pilot import Pilot
from textual.widgets import Static

from app_harness import (
    SequenceCollector,
    SnapshotQuerySource,
    dashboard_app,
    first_load_landed,
    issue,
    workspace_snapshot,
)
from dashpot.core import runtime_stats
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    DASHBOARD_RECENT_EVENTS,
    DASHBOARD_RECENT_WINDOW,
    EventLog,
    EventLogDestination,
    Span,
)
from dashpot.core.runtime_events import (
    CommandAttributes,
    EventLevel,
    GitHubRequestAttributes,
    KeyOutcome,
    LevelChanged,
    ObservationAttributes,
    ProcessIdentity,
    ProcessStart,
    QueryAttributes,
    RefreshAttributes,
    RefreshTrigger,
)
from dashpot.core.runtime_stats import (
    CommandStats,
    ResidentMemory,
    account_spend,
    command_stats,
    covered_since,
    events_since,
    last_github_refresh,
    resident_memory,
)
from dashpot.github.github import LatestRateLimit, RateLimit
from dashpot.project.settings import default_settings_path
from dashpot.ui.app import DashpotApp
from dashpot.ui.attendance import Attendance
from dashpot.ui.runtime_stats_view import (
    duration_text,
    keys_text,
    long_duration_text,
    memory_text,
    refreshes_text,
    size_text,
    window_text,
)
from dashpot.ui.runtime_view import RuntimeScreen
from helpers import wait_until

RUN = "0123456789abcdef0123456789abcdef"
REVISION = "0123456789abcdef0123456789abcdef01234567"
MIDDAY = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
HOUR = DASHBOARD_RECENT_WINDOW.total_seconds()
MIDDAY_STAMP = "2026-09-27T12:00:00Z"


class Clock:
    """A wall clock and a monotonic clock the test moves by hand, together."""

    def __init__(self) -> None:
        self.now = MIDDAY
        self.seconds = 100.0

    def wall(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.seconds += seconds


def stats_log(
    directory: Path | None,
    clock: Clock,
    *,
    level: EventLevel = "standard",
    keep_recent: int = DASHBOARD_RECENT_EVENTS,
) -> EventLog:
    """A dashboard's writer as the command line opens one, on the test's clock."""
    log = EventLog(
        None if directory is None else EventLogDestination(directory),
        identity=ProcessIdentity(run_id=RUN, kind=DASHBOARD_KIND),
        level=level,
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision=REVISION,
            source_dirty=True,
            pid=os.getpid(),
            python_version="3.14.0",
        ),
        keep_recent=keep_recent,
        recent_window=DASHBOARD_RECENT_WINDOW,
        clock=clock.wall,
        monotonic=clock.monotonic,
    )
    log.start()
    return log


def run_command(
    log: EventLog,
    clock: Clock,
    program: str,
    seconds: float,
    *,
    failed: bool = False,
) -> None:
    """Record one command span through the writer, taking ``seconds`` on the clock."""
    span = log.start_span(
        "command",
        attributes=CommandAttributes(program=program, subcommand="status", exit_code=0),
    )
    clock.advance(seconds)
    if failed:
        span.fail("CommandError")
    span.end()


RESET = "2026-09-27T13:00:00Z"


def refresh(log: EventLog, trigger: RefreshTrigger) -> Span:
    """Start a refresh span, as a timer or a key press fires one."""
    return log.start_span(
        "refresh", attributes=RefreshAttributes(trigger=trigger), parent=None
    )


def key(
    log: EventLog,
    parent: Span | None,
    attributes: ObservationAttributes | QueryAttributes,
) -> Span:
    """Start the span of one key a refresh, or nothing, asked for."""
    name = "observation" if isinstance(attributes, ObservationAttributes) else "query"
    return log.start_span(name, attributes=attributes, parent=parent)


def end_after(span: Span, clock: Clock, seconds: float) -> None:
    clock.advance(seconds)
    span.end()


def request(
    log: EventLog,
    clock: Clock,
    parent: Span,
    operation: str | None,
    *,
    cost: int | None = None,
    remaining: int | None = None,
    failed: bool = False,
) -> None:
    """Record one GitHub request under ``parent``, with the reading its response carried."""
    read = remaining is not None
    span = log.start_span(
        "github.request",
        attributes=GitHubRequestAttributes(
            api="rest" if operation is None else "graphql",
            operation=operation,
            cost=cost,
            limit=5000 if read else None,
            remaining=remaining,
            reset_at=RESET if read else None,
        ),
        parent=parent,
        level="standard",
    )
    if failed:
        span.fail("github-rate-limit")
    end_after(span, clock, 0.2)


def rows_starting(text: str, *prefixes: str) -> list[str]:
    return [line for line in squeezed(text) if line.startswith(prefixes)]


def stats_app(
    log: EventLog,
    *,
    rate_limit: LatestRateLimit | None = None,
    attendance: Attendance | None = None,
) -> DashpotApp:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    return dashboard_app(
        SequenceCollector(snapshot),
        event_log=log,
        rate_limit=rate_limit,
        attendance=attendance,
    )


async def open_stats(app: DashpotApp, pilot: Pilot[None]) -> RuntimeScreen:
    await wait_until(lambda: first_load_landed(app))
    await pilot.press("s")
    await wait_until(lambda: isinstance(app.screen, RuntimeScreen))
    screen = app.screen
    assert isinstance(screen, RuntimeScreen)
    assert screen.tab == "stats"
    return screen


def section(app: DashpotApp, name: str) -> str:
    return str(app.screen.query_one(f"#stats-{name}", Static).render())


def heading(app: DashpotApp, name: str) -> str:
    return str(app.screen.query_one(f"#stats-{name}-heading", Static).render())


def squeezed(text: str) -> list[str]:
    """Each line with its runs of spaces made one, so columns read as words."""
    return [" ".join(line.split()) for line in text.splitlines()]


@pytest.mark.asyncio
async def test_commands_are_counted_by_program_with_typical_and_worst_times(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    for seconds, failed in ((0.01, False), (0.02, False), (0.5, True)):
        run_command(log, clock, "git", seconds, failed=failed)
    run_command(log, clock, "gh", 2.0)
    app = stats_app(log)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)

        assert squeezed(section(app, "commands")) == [
            "program count typical worst failed",
            "git 3 20 ms 500 ms 1",
            "gh 1 2.0 s 2.0 s 0",
        ]
        assert heading(app, "commands") == "COMMANDS · since start"


@pytest.mark.asyncio
async def test_only_the_last_hours_events_are_counted(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.1)
    clock.advance(HOUR)
    run_command(log, clock, "gh", 0.1)
    app = stats_app(log)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)

        assert heading(app, "commands") == "COMMANDS · last hour"
        assert squeezed(section(app, "commands"))[1:] == ["gh 1 100 ms 100 ms 0"]
    # The buffer let the hour-old events go, so weeks of running never grow it.
    assert "process.start" not in [event.body.name for event in log.recent_events()]


def test_a_full_buffer_says_how_far_back_it_reaches() -> None:
    clock = Clock()
    log = stats_log(None, clock, keep_recent=2)
    clock.advance(2 * HOUR)
    for _ in range(3):
        run_command(log, clock, "git", 60)
    events = log.recent_events()

    since = covered_since(
        events, now=clock.now, window=DASHBOARD_RECENT_WINDOW, limit=2
    )

    assert window_text(since, now=clock.now, started=MIDDAY) == (
        "last 2m 00s, buffer full"
    )
    assert command_stats(events_since(events, since)) == (
        CommandStats("git", 2, 60.0, 60.0, 0),
    )


@pytest.mark.asyncio
async def test_the_screen_updates_while_open_and_sends_no_request(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    collector = SequenceCollector(workspace_snapshot(issue("test/repo#1", "First")))
    app = dashboard_app(collector, event_log=log, runtime_stats_seconds=0.05)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)
        observed = collector.calls
        queries = [
            mock.patch.object(source, "query_page", wraps=source.query_page)
            for source in app.queries.sources.values()
            if isinstance(source, SnapshotQuerySource)
        ]
        spies = [patch.start() for patch in queries]
        assert section(app, "commands") == "no commands recorded"

        run_command(log, clock, "git", 0.25)
        await wait_until(lambda: "git" in section(app, "commands"))

        for patch in queries:
            patch.stop()
    assert collector.calls == observed
    assert all(not spy.called for spy in spies)


@pytest.mark.asyncio
async def test_this_process_shows_its_start_uptime_memory_and_event_log(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    clock.advance(3725)
    app = stats_app(log)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)
        await wait_until(lambda: "not measured yet" not in section(app, "process"))

        text = squeezed(section(app, "process"))
        assert text[:3] == [
            "version 0.1.0 (editable)",
            "commit 0123456789ab · uncommitted changes",
            "uptime 1h 02m 05s",
        ]
        assert text[3].startswith("memory ") and text[3].endswith(" resident")
        assert f"Event Log {tmp_path}" in text
        assert any(line.startswith("size ") and "B" in line for line in text)
        assert "level standard · l changes it for this run" in text
        assert "write failures 0 last hour" in text


@pytest.mark.asyncio
async def test_dropped_writes_are_counted_from_the_buffer(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    clock = Clock()
    log = stats_log(blocker / "events", clock)
    run_command(log, clock, "git", 0.1, failed=True)
    app = stats_app(log)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)

        # ``process.start``, the failed span and the Diagnostic the unwritable
        # Event Log raises were all dropped.
        assert "write failures 3 since start, first ENOTDIR" in squeezed(
            section(app, "process")
        )


@pytest.mark.asyncio
async def test_a_dashboard_given_no_event_log_keeps_its_events_in_memory() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)

        text = squeezed(section(app, "process"))
        # Nothing started it, so no ``process.start`` described the process.
        assert text[0] == "version not recorded"
        assert "Event Log none; events are kept in memory only" in text
        assert not any(line.startswith("size ") for line in text)
        assert "level off · l changes it for this run" in text


@pytest.mark.asyncio
async def test_l_changes_the_level_for_the_run_and_never_the_settings(
    tmp_path: Path,
) -> None:
    settings = default_settings_path()
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("event_level = 'standard'\n")
    log = stats_log(tmp_path, Clock())
    app = stats_app(log)

    async with app.run_test(size=(100, 40)) as pilot:
        await open_stats(app, pilot)
        await pilot.press("l")
        await wait_until(lambda: "level full" in squeezed(section(app, "process"))[-2])
        await pilot.press("l", "l")
        await wait_until(lambda: log.level == "standard")

    assert settings.read_text() == "event_level = 'standard'\n"
    assert [
        event.body
        for event in log.recent_events()
        if isinstance(event.body, LevelChanged)
    ] == [
        LevelChanged(previous="standard", current="full"),
        LevelChanged(previous="full", current="off"),
        LevelChanged(previous="off", current="standard"),
    ]


@pytest.mark.asyncio
async def test_the_allowance_shows_the_latest_reading_the_sources_share(
    tmp_path: Path,
) -> None:
    shared = LatestRateLimit()
    app = stats_app(stats_log(tmp_path, Clock()), rate_limit=shared)

    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_stats(app, pilot)
        assert section(app, "allowance") == (
            "no GitHub response has reported the rate limit yet"
        )

        shared.record(
            RateLimit(
                cost=1, limit=5000, remaining=4321, reset_at="2026-09-27T13:00:00Z"
            )
        )
        screen.update_shown()

        assert squeezed(section(app, "allowance")) == [
            "remaining 4,321 of 5,000 points",
            "resets 13:00:00 UTC, in 1h 00m 00s",
            "last request 1 point",
            "rest of account not known until two readings share a window",
        ]


@pytest.mark.asyncio
async def test_the_allowance_leads_with_a_pause_while_one_holds_github_queries(
    tmp_path: Path,
) -> None:
    clock = Clock()
    shared = LatestRateLimit(clock=clock.wall)
    app = stats_app(stats_log(tmp_path, clock), rate_limit=shared)

    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_stats(app, pilot)
        shared.refused(shared.admit(), "secondary")
        screen.update_shown()

        # Refused before any response reported the rate limit.
        assert squeezed(section(app, "allowance")) == [
            "paused until 12:01:00 UTC, in 1m 00s (secondary rate limit)"
        ]

        shared.record(RateLimit(cost=1, limit=5000, remaining=0, reset_at=RESET))
        clock.advance(30)
        screen.update_shown()

        assert squeezed(section(app, "allowance"))[:2] == [
            "paused until 12:01:00 UTC, in 30s (secondary rate limit)",
            "remaining 0 of 5,000 points",
        ]

        clock.advance(30)
        screen.update_shown()

        assert squeezed(section(app, "allowance"))[0] == "remaining 0 of 5,000 points"


@pytest.mark.asyncio
async def test_the_allowance_says_since_when_nobody_has_attended(
    tmp_path: Path,
) -> None:
    clock = Clock()
    shared = LatestRateLimit(clock=clock.wall)
    attendance = Attendance(
        idle_seconds=600, clock=clock.monotonic, wall_clock=clock.wall
    )
    app = stats_app(
        stats_log(tmp_path, clock), rate_limit=shared, attendance=attendance
    )

    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_stats(app, pilot)
        clock.advance(600)
        attendance.check_idle()
        clock.advance(90)
        screen.update_shown()

        assert squeezed(section(app, "allowance")) == [
            "unattended since 12:10:00 UTC, 1m 30s ago (no key or mouse input for 10m)"
        ]

        # A Rate Limit Pause leads: it holds even a person's refresh.
        shared.refused(shared.admit(), "secondary")
        screen.update_shown()

        assert squeezed(section(app, "allowance")) == [
            "paused until 12:12:30 UTC, in 1m 00s (secondary rate limit)",
            "unattended since 12:10:00 UTC, 1m 30s ago (no key or mouse input for 10m)",
        ]


@pytest.mark.asyncio
async def test_github_requests_are_counted_by_operation_for_the_last_refresh_and_hour(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    shared = LatestRateLimit()
    app = stats_app(log, rate_limit=shared)

    async with app.run_test(size=(100, 60)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        clock.advance(10)
        timer = refresh(log, "github")
        issues = key(log, timer, QueryAttributes(key="issues", outcome="landed"))
        request(log, clock, issues, "DashpotQueryPage", cost=1, remaining=4990)
        request(log, clock, issues, "DashpotQueryPage", cost=1, remaining=4985)
        issues.end()
        prs = key(log, timer, QueryAttributes(key="pull-requests", outcome="landed"))
        request(log, clock, prs, "DashpotPullRequestPage", cost=2, remaining=4980)
        prs.end()
        end_after(timer, clock, 0.1)
        clock.advance(10)
        manual = refresh(log, "manual")
        page = key(log, manual, QueryAttributes(key="issues", outcome="landed"))
        request(log, clock, page, "DashpotQueryPage", cost=1, remaining=4979)
        request(log, clock, page, None, failed=True)
        page.end()
        # Still running, so not yet the last refresh.
        running = refresh(log, "github")
        request(log, clock, running, "DashpotQueryPage", cost=1)
        shared.record(RateLimit(cost=1, limit=5000, remaining=4979, reset_at=RESET))
        manual.end()
        await open_stats(app, pilot)

        assert heading(app, "refresh-spend") == (
            "GITHUB REQUESTS · last refresh, manual at 12:00:20 UTC"
        )
        assert squeezed(section(app, "refresh-spend")) == [
            "operation requests points failed",
            "DashpotQueryPage 1 1 0",
            "rest 1 0 1",
        ]
        assert heading(app, "window-spend") == "GITHUB REQUESTS · since start"
        assert squeezed(section(app, "window-spend")) == [
            "operation requests points failed",
            "DashpotQueryPage 4 4 0",
            "DashpotPullRequestPage 1 2 0",
            "rest 1 0 1",
        ]
        # 11 points used between the first reading and the last, 4 of them
        # by this dashboard's later requests.
        assert "rest of account 7 points since start" in squeezed(
            section(app, "allowance")
        )


@pytest.mark.asyncio
async def test_refresh_health_is_shown_by_trigger_and_by_key(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    app = stats_app(log)

    async with app.run_test(size=(100, 60)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        outcomes: list[tuple[str, KeyOutcome, float]] = [
            ("targets", "landed", 0.5),
            ("targets", "skipped", 0.0),
            ("agent-runs", "dropped", 0.0),
        ]
        for seconds, keys in ((1.0, outcomes), (3.0, outcomes[:1])):
            local = refresh(log, "local")
            for kind, outcome, taking in keys:
                observed = key(
                    log, local, ObservationAttributes(kind=kind, outcome=outcome)
                )
                end_after(observed, clock, taking)
            end_after(local, clock, seconds)
        # A query a person asked for belongs to no refresh.
        query = key(log, None, QueryAttributes(key="identities", outcome="landed"))
        query.fail("github-rate-limit")
        end_after(query, clock, 2.0)
        await open_stats(app, pilot)

        assert heading(app, "refreshes") == "REFRESHES · since start"
        assert rows_starting(section(app, "refreshes"), "trigger", "local") == [
            "trigger count typical worst skipped dropped",
            "local 2 2.5 s 3.5 s 1 1",
        ]
        assert rows_starting(
            section(app, "keys"),
            "key",
            "observation targets",
            "observation agent-runs",
            "query identities",
        ) == [
            "key runs typical worst skipped dropped failed",
            "observation agent-runs 0 — — 0 1 0",
            "observation targets 2 500 ms 500 ms 1 0 0",
            "query identities 1 2.0 s 2.0 s 0 0 1",
        ]


# --- Aggregations and their text ---------------------------------------------


def test_a_buffer_below_its_limit_covers_the_whole_window() -> None:
    clock = Clock()
    log = stats_log(None, clock, keep_recent=5)
    events = log.recent_events()

    assert covered_since(
        events, now=clock.now, window=DASHBOARD_RECENT_WINDOW, limit=5
    ) == (clock.now - DASHBOARD_RECENT_WINDOW)
    assert covered_since(
        (), now=clock.now, window=DASHBOARD_RECENT_WINDOW, limit=0
    ) == (clock.now - DASHBOARD_RECENT_WINDOW)


def test_the_rest_of_the_account_is_counted_within_each_reset_window() -> None:
    clock = Clock()
    log = stats_log(None, clock)
    parent = refresh(log, "github")
    request(log, clock, parent, "Q", cost=1, remaining=100)
    request(log, clock, parent, "Q", cost=1, remaining=90)
    parent.end()
    one_window = log.recent_events()

    # A reading in another window compares with nothing, and a cost larger
    # than the change in points — answers that crossed — counts as nothing.
    other = log.start_span(
        "github.request",
        attributes=GitHubRequestAttributes(
            api="graphql", cost=5, limit=5000, remaining=4000, reset_at=MIDDAY_STAMP
        ),
    )
    other.end()
    request(log, clock, parent, "Q", cost=50, remaining=89)

    assert account_spend(one_window) == 9
    assert account_spend(log.recent_events()) == 0
    assert account_spend(()) is None


def test_the_earliest_of_equal_readings_is_taken_as_the_first() -> None:
    clock = Clock()
    log = stats_log(None, clock)
    parent = refresh(log, "github")
    request(log, clock, parent, "Q", cost=1, remaining=100)
    request(log, clock, parent, "Q", cost=10, remaining=100)
    request(log, clock, parent, "Q", cost=5, remaining=80)
    parent.end()

    # 20 points used, of which the two later requests spent 15.
    assert account_spend(log.recent_events()) == 5


def test_a_request_whose_refresh_is_not_recorded_belongs_to_no_last_refresh() -> None:
    clock = Clock()
    log = stats_log(None, clock)
    running = refresh(log, "local")
    request(log, clock, running, "Q", cost=1)
    orphan = log.start_span("query", attributes=QueryAttributes(key="issues"))
    request(log, clock, orphan, "Q", cost=1)
    orphan.end()

    assert last_github_refresh(log.recent_events()) is None


def test_a_command_span_without_attributes_names_no_program() -> None:
    log = stats_log(None, Clock())
    log.start_span("command").end()

    assert command_stats(log.recent_events()) == ()


def test_memory_is_the_current_resident_set_where_linux_reports_it(
    tmp_path: Path,
) -> None:
    statm = tmp_path / "statm"
    statm.write_text("5000 250 100 1 0 300 0\n")

    assert resident_memory(statm) == ResidentMemory(
        250 * os.sysconf("SC_PAGE_SIZE"), peak=False
    )


@pytest.mark.parametrize(
    ("platform", "expected"), [("darwin", 2048), ("linux", 2048 * 1024)]
)
def test_memory_is_the_labelled_peak_where_the_current_size_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, expected: int
) -> None:
    monkeypatch.setattr(runtime_stats.sys, "platform", platform)
    usage = mock.Mock(ru_maxrss=2048)
    with mock.patch.object(runtime_stats.resource, "getrusage", return_value=usage):
        assert resident_memory(tmp_path / "absent") == ResidentMemory(
            expected, peak=True
        )


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0.012, "12 ms"), (2.5, "2.5 s"), (125, "2m 05s")],
)
def test_a_duration_reads_in_its_best_unit(seconds: float, text: str) -> None:
    assert duration_text(seconds) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(9, "9s"), (61, "1m 01s"), (3725, "1h 02m 05s"), (90_061, "1d 1h 01m")],
)
def test_a_long_duration_reads_leading_unit_first(seconds: float, text: str) -> None:
    assert long_duration_text(seconds) == text


@pytest.mark.parametrize(
    ("size", "text"),
    [(512, "512 B"), (1_500, "1.5 kB"), (12_300_000, "12.3 MB"), (2e9, "2.0 GB")],
)
def test_a_size_reads_in_decimal_units(size: int, text: str) -> None:
    assert size_text(int(size)) == text


def test_a_window_with_no_refreshes_says_so() -> None:
    assert refreshes_text([]).plain == "no refreshes recorded"
    assert keys_text([]).plain == "no observations or queries recorded"


def test_memory_says_when_it_is_only_the_peak() -> None:
    assert memory_text(ResidentMemory(12_300_000, peak=False)) == "12.3 MB resident"
    assert memory_text(ResidentMemory(12_300_000, peak=True)) == "12.3 MB peak resident"
