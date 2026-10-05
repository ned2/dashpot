"""The Runtime screen: how it opens, its two tabs, and the Events tab's rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from textual import events
from textual.command import CommandList, CommandPalette
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.scrollbar import ScrollTo, ScrollUp
from textual.widgets import Select, Static

from app_harness import (
    PROJECT_ID,
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    footer_showing,
    issue,
    legend_keys_text,
    open_issue_view,
    settle_screen,
    show_query_peer,
    with_first_project,
    workspace_snapshot,
)
from dashpot.core.event_log import EventLog
from dashpot.core.runtime_events import (
    AgentSessionChanged,
    CommandAttributes,
    DiagnosticChanged,
    EventLogWriteFailed,
    LevelChanged,
    ObservationAttributes,
    ProcessEnd,
    ProcessIdentity,
    QueryAttributes,
    RateLimitPauseChanged,
    RuntimeEvent,
    SpanEnded,
    SubagentsAcknowledged,
    UnattendedPauseChanged,
    read_runtime_event,
)
from dashpot.core.timestamps import observed_instant
from dashpot.ui.app import DashpotApp
from dashpot.ui.detail_fields import DetailFields
from dashpot.ui.legend import LegendScreen
from dashpot.ui.marked_widgets import MarkedCheckbox
from dashpot.ui.runtime_events_view import (
    EventFilter,
    EventTable,
    accepts,
    event_outcome,
    event_summary,
)
from dashpot.ui.runtime_view import RuntimeScreen
from helpers import settled, wait_until
from test_runtime_stats import (
    Clock,
    end_after,
    key,
    refresh,
    request,
    run_command,
    squeezed,
    stats_log,
)

MIDDAY = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def runtime_app(log: EventLog) -> DashpotApp:
    """A dashboard whose Runtime screen redraws only when a test asks it to."""
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    return dashboard_app(
        SequenceCollector(snapshot), event_log=log, runtime_stats_seconds=3600
    )


async def open_runtime(
    app: DashpotApp, pilot: Pilot[None], key_name: str = "e"
) -> RuntimeScreen:
    await wait_until(lambda: first_load_landed(app))
    await pilot.press(key_name)
    await wait_until(lambda: isinstance(app.screen, RuntimeScreen))
    screen = app.screen
    assert isinstance(screen, RuntimeScreen)
    return screen


def event_table(app: DashpotApp) -> EventTable:
    return app.screen.query_one(EventTable)


def rows(app: DashpotApp) -> list[list[str]]:
    """Every row's cells as text, oldest first."""
    table = event_table(app)
    return [
        [str(cell) for cell in table.get_row(row.key)] for row in table.ordered_rows
    ]


def kinds(app: DashpotApp) -> list[str]:
    return [row[2] for row in rows(app)]


def cursor_kind(app: DashpotApp) -> str:
    table = event_table(app)
    return str(table.get_row_at(table.cursor_row)[2])


def detail(app: DashpotApp) -> dict[str, str]:
    fields = app.screen.query_one("#runtime-event-detail", DetailFields)
    return {item.label: str(item.value) for item in fields.items}


def follow_text(app: DashpotApp) -> str:
    return str(app.screen.query_one("#runtime-follow", Static).render())


def header(app: DashpotApp) -> str:
    return str(app.screen.query_one("#runtime-header", Static).render())


def local_clock(instant: datetime) -> str:
    local = instant.astimezone()
    return f"{local:%H:%M:%S}.{local.microsecond // 1000:03d}"


def event(body: object, *, level: str = "standard", **process: Any) -> RuntimeEvent:
    return RuntimeEvent.model_validate(
        {
            "time": "2026-09-27T12:00:00Z",
            "level": level,
            "process": ProcessIdentity(
                run_id="0123456789abcdef0123456789abcdef", kind="dashboard", **process
            ),
            "body": body,
        }
    )


def span(**values: Any) -> SpanEnded:
    defaults: dict[str, Any] = {
        "span_id": "0123456789abcdef",
        "duration_seconds": 0.25,
        "status": "OK",
    }
    return SpanEnded(**(defaults | values))


@pytest.mark.asyncio
async def test_e_and_s_open_one_full_screen_on_their_tab_and_switch_between_them(
    tmp_path: Path,
) -> None:
    app = runtime_app(stats_log(tmp_path, Clock()))

    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_runtime(app, pilot, "e")
        assert screen.tab == "events"
        assert not isinstance(screen, ModalScreen)
        await settle_screen(app, pilot, "the Runtime screen")
        assert screen.query_one("#runtime-view").region.width == 120
        await footer_showing(app, ["s", "l", "escape"], without=["e"])

        # A tab's own key does nothing; the other's switches to it.
        await pilot.press("e")
        assert app.screen is screen and screen.tab == "events"
        await pilot.press("s")
        await wait_until(lambda: screen.tab == "stats")
        await footer_showing(app, ["e"], without=["s"])
        await pilot.press("s")
        assert app.screen is screen and screen.tab == "stats"
        await pilot.press("e")
        await wait_until(lambda: screen.tab == "events")

        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.dashboard)

        stats = await open_runtime(app, pilot, "s")
        assert stats.tab == "stats"
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.dashboard)


@pytest.mark.asyncio
async def test_the_runtime_screen_opens_from_either_peer_screen_and_over_no_popup(
    tmp_path: Path,
) -> None:
    app = runtime_app(stats_log(tmp_path, Clock()))

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        await pilot.press("e")
        await wait_until(lambda: isinstance(app.screen, RuntimeScreen))
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)

        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        await pilot.press("e", "s")
        await pilot.pause()
        assert isinstance(app.screen, LegendScreen)
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)

        issue_view = await open_issue_view(app, pilot)
        await footer_showing(app, ["escape"], without=["e", "s"])
        await pilot.press("e", "s")
        await pilot.pause()
        assert app.screen is issue_view
        # Nor does the action open it when something calls it there directly.
        app.action_runtime_stats()
        await pilot.pause()
        assert app.screen is issue_view


@pytest.mark.asyncio
async def test_the_palette_offers_both_tabs_on_peer_screens_only(
    tmp_path: Path,
) -> None:
    app = runtime_app(stats_log(tmp_path, Clock()))

    def titles() -> set[str]:
        return {command.title for command in app.get_system_commands(app.screen)}

    runtime = {"Runtime Events", "Runtime Stats"}
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        assert runtime <= titles()
        # Textual's own commands stay.
        assert {"Theme", "Quit"} <= titles()
        await show_query_peer(app, pilot)
        assert runtime <= titles()
        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        assert not runtime & titles()
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)

        await pilot.press("ctrl+p")
        await wait_until(lambda: isinstance(app.screen, CommandPalette))
        await pilot.press(*"runtimestats")
        palette = app.screen
        assert isinstance(palette, CommandPalette)
        matches = palette.query_one(CommandList)

        def highlighted() -> str:
            index = matches.highlighted
            if index is None:
                return ""
            return str(matches.get_option_at_index(index).prompt)

        await wait_until(lambda: "Runtime Stats" in highlighted())
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, RuntimeScreen))
        screen = app.screen
        assert isinstance(screen, RuntimeScreen)
        assert screen.tab == "stats"
        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.query_screen)


@pytest.mark.asyncio
async def test_events_show_this_dashboards_buffer_newest_last(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.012)
    started = refresh(log, "manual")
    observed = key(
        log,
        started,
        ObservationAttributes(
            kind="worktrees", project_id=PROJECT_ID, outcome="landed"
        ),
    )
    end_after(observed, clock, 0.5)
    gone = key(
        log, started, ObservationAttributes(kind="branches", project_id="project:gone")
    )
    end_after(gone, clock, 0.1)
    request(log, clock, started, "DashpotQueryPage", cost=1, remaining=4321)
    request(log, clock, started, None, failed=True)
    end_after(started, clock, 1)
    command_time = log.recent_events()[1].time
    app = runtime_app(log)

    async with app.run_test(size=(160, 40)) as pilot:
        await open_runtime(app, pilot)
        # The dashboard's own first refresh follows what the test recorded.
        shown = rows(app)[:7]
        assert [row[2] for row in shown] == [
            "process.start",
            "command",
            "observation",
            "observation",
            "github.request",
            "github.request",
            "refresh",
        ]
        assert shown[1] == [
            local_clock(observed_instant(command_time)),
            "full",
            "command",
            "",
            "OK",
            "12 ms",
            "git status",
        ]
        assert [shown[2][column] for column in (3, 4, 6)] == [
            "Test Repository",
            "landed",
            "worktrees",
        ]
        # A Project the dashboard no longer observes is named by its identity.
        assert shown[3][3] == "project:gone"
        assert shown[4][1:5] == ["std", "github.request", "", "OK"]
        assert shown[4][6] == "graphql DashpotQueryPage · cost 1 · 4,321 left"
        assert [shown[5][column] for column in (4, 6)] == [
            "ERROR github-rate-limit",
            "rest",
        ]
        assert shown[6][6] == "trigger manual"
        table = event_table(app)
        assert table.cursor_row == table.row_count - 1
        assert follow_text(app) == "following"


@pytest.mark.asyncio
async def test_the_selected_event_shows_every_field_with_its_stored_time(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.012, failed=True)
    stored = log.recent_events()[-1]
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(160, 40)) as pilot:
        await open_runtime(app, pilot)
        await wait_until(lambda: "dashpot.span.name" in detail(app))
        fields = detail(app)
        assert fields["time"] == stored.time
        # A failed span is written at standard, whatever its kind's level.
        assert fields["dashpot.level"] == "standard"
        assert fields["dashpot.span.name"] == "command"
        assert fields["otel.status_code"] == "ERROR"
        assert fields["error.type"] == "CommandError"
        assert fields["process.executable.name"] == "git"
        assert fields["dashpot.command.subcommand"] == "status"
        assert fields["service.instance.id"] == log.identity.run_id
        assert set(fields) >= {"span_id", "dashpot.duration_seconds", "schema"}


@pytest.mark.asyncio
async def test_the_filters_narrow_the_rows_and_last_the_run(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.01)
    run_command(log, clock, "gh", 0.01, failed=True)
    started = refresh(log, "manual")
    request(log, clock, started, "DashpotQueryPage", cost=1, remaining=10)
    end_after(started, clock, 1)
    app = runtime_app(log)

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        assert kinds(app)[:5] == [
            "process.start",
            "command",
            "command",
            "github.request",
            "refresh",
        ]

        # The dashboard's own refresh spans are full-level, so standard
        # leaves only what the test recorded at standard.
        screen.query_one("#runtime-show", Select).value = "standard"
        await wait_until(
            lambda: kinds(app) == ["process.start", "command", "github.request"]
        )
        # A failed span is written at standard whatever its own level.
        assert rows(app)[1][6] == "gh status"

        screen.query_one("#runtime-show", Select).value = "all"
        screen.query_one("#runtime-kind", Select).value = "command"
        await wait_until(lambda: kinds(app) == ["command", "command"])

        screen.query_one("#runtime-errors", MarkedCheckbox).value = True
        await wait_until(lambda: [row[6] for row in rows(app)] == ["gh status"])
        assert app.runtime_event_filter == EventFilter(
            show="all", kind="command", errors_only=True
        )

        screen.query_one("#runtime-kind", Select).value = "hook.outcome"
        await wait_until(lambda: not rows(app))
        assert detail(app) == {"": "no events match these filters"}

        await pilot.press("escape")
        await wait_until(lambda: app.screen is app.dashboard)
        reopened = await open_runtime(app, pilot)
        assert reopened.query_one("#runtime-kind", Select).value == "hook.outcome"
        assert reopened.query_one("#runtime-errors", MarkedCheckbox).value
        assert not rows(app)


@pytest.mark.asyncio
async def test_the_recorded_filter_follows_the_level_l_sets(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(show="recorded")

    async with app.run_test(size=(160, 40)) as pilot:
        await open_runtime(app, pilot)
        assert kinds(app) == ["process.start"]
        assert header(app).startswith("Event Level: standard (l changes it)")

        await pilot.press("l")
        await wait_until(lambda: log.level == "full")
        # At full, every buffered event is one the level records.
        await wait_until(lambda: kinds(app)[-1] == "level.changed")
        assert kinds(app)[:2] == ["process.start", "command"]
        assert "refresh" in kinds(app)
        assert header(app).startswith("Event Level: full (l changes it)")

        await pilot.press("l")
        await wait_until(lambda: not rows(app))


@pytest.mark.asyncio
async def test_the_table_follows_the_newest_event_until_a_person_looks_back(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    run_command(log, clock, "git", 0.01)
    run_command(log, clock, "gh", 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        table = event_table(app)
        assert table.cursor_row == 1

        run_command(log, clock, "tmux", 0.01)
        screen.update_shown()
        assert table.cursor_row == 2
        await wait_until(lambda: detail(app)["process.executable.name"] == "tmux")

        await pilot.press("up")
        await wait_until(lambda: follow_text(app) == "paused · End follows")
        await wait_until(lambda: detail(app)["process.executable.name"] == "gh")

        run_command(log, clock, "uv", 0.01)
        screen.update_shown()
        assert table.row_count == 4
        assert table.cursor_row == 1

        await pilot.press("end")
        await wait_until(lambda: follow_text(app) == "following")
        assert table.cursor_row == 3
        await wait_until(lambda: detail(app)["process.executable.name"] == "uv")

        # Moving back down to the newest event follows again.
        await pilot.press("up")
        await wait_until(lambda: follow_text(app) != "following")
        await pilot.press("down")
        await wait_until(lambda: follow_text(app) == "following")

        # Scrolling the mouse wheel back up stops it too.
        table.post_message(
            events.MouseScrollUp(
                table, 1, 1, 0, -1, 0, shift=False, meta=False, ctrl=False
            )
        )
        await wait_until(lambda: follow_text(app) != "following")


@pytest.mark.asyncio
async def test_paging_jumping_and_clicking_follow_only_on_the_newest_event(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    for program in ("git", "gh", "tmux"):
        run_command(log, clock, program, 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        table = event_table(app)
        assert follow_text(app) == "following"

        await pilot.press("ctrl+home")
        await wait_until(lambda: follow_text(app) != "following")
        assert table.cursor_row == 0
        await pilot.press("ctrl+end")
        await wait_until(lambda: follow_text(app) == "following")
        await pilot.press("pageup")
        await wait_until(lambda: follow_text(app) != "following")
        await pilot.press("pagedown")
        await wait_until(lambda: follow_text(app) == "following")

        # The header row is the table's first line, so its second is row 0.
        await settle_screen(app, pilot, "the event table")
        await pilot.click("#runtime-event-table", offset=(4, 2))
        await wait_until(lambda: follow_text(app) != "following")
        assert table.cursor_row == 0

        # A paused table that filters down to nothing has no row to keep.
        screen.query_one("#runtime-kind", Select).value = "hook.outcome"
        await wait_until(lambda: not rows(app))
        assert table.cursor_key() is None


@pytest.mark.asyncio
async def test_a_paused_table_stays_where_a_person_scrolled_it(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock, keep_recent=60)
    for number in range(60):
        run_command(log, clock, f"p{number}", 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(160, 30)) as pilot:
        screen = await open_runtime(app, pilot)
        table = event_table(app)
        bottom = await settled(pilot, lambda: table.scroll_y, "the newest event")
        assert bottom == table.max_scroll_y > 10

        for _ in range(3):
            table.post_message(
                events.MouseScrollUp(
                    table, 1, 1, 0, -1, 0, shift=False, meta=False, ctrl=False
                )
            )
        await wait_until(lambda: follow_text(app) != "following")
        scrolled = await settled(pilot, lambda: table.scroll_y, "the scroll back")
        assert scrolled < bottom

        # A tick with nothing new leaves the view where it was.
        screen.update_shown()
        assert await settled(pilot, lambda: table.scroll_y, "a tick") == scrolled

        # So does one where the buffer lets go of its oldest event: the
        # rows move up by one, and the view with them.
        top = table.scroll_y
        first_shown = rows(app)[int(top)][6]
        run_command(log, clock, "uv", 0.01)
        screen.update_shown()
        assert await settled(pilot, lambda: table.scroll_y, "a trim") == top - 1
        assert rows(app)[int(top) - 1][6] == first_shown


@pytest.mark.asyncio
async def test_the_scrollbar_moved_back_from_the_newest_event_pauses(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    for number in range(60):
        run_command(log, clock, f"p{number}", 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(160, 30)) as pilot:
        await open_runtime(app, pilot)
        table = event_table(app)
        bottom = await settled(pilot, lambda: table.scroll_y, "the newest event")

        # Dragging the thumb to the bottom is no reason to stop following.
        table.post_message(ScrollTo(y=bottom))
        await settled(pilot, lambda: table.scroll_y, "the drag to the bottom")
        assert follow_text(app) == "following"

        table.post_message(ScrollTo(y=bottom - 5))
        await wait_until(lambda: follow_text(app) != "following")

        await pilot.press("end")
        await wait_until(lambda: follow_text(app) == "following")
        # A click on the track above the thumb.
        table.post_message(ScrollUp())
        await wait_until(lambda: follow_text(app) != "following")


@pytest.mark.asyncio
async def test_following_keeps_the_table_scrolled_across_to_the_summary(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    # A summary wider than the table leaves it to scroll across to.
    run_command(log, clock, "a-program-whose-name-runs-past-the-edge", 0.01)
    app = runtime_app(log)
    app.runtime_event_filter = EventFilter(kind="command")

    async with app.run_test(size=(80, 30)) as pilot:
        screen = await open_runtime(app, pilot, "e")
        table = event_table(app)
        await settle_screen(app, pilot, "the stacked Runtime screen")
        assert table.max_scroll_x > 0

        table.scroll_to(x=table.max_scroll_x, animate=False)
        across = await settled(pilot, lambda: table.scroll_x, "the scroll across")
        assert across == table.max_scroll_x

        # Following the newest event moves down, never back across.
        run_command(log, clock, "gh", 0.01)
        screen.update_shown()
        assert await settled(pilot, lambda: table.scroll_x, "a tick") == across
        assert follow_text(app) == "following"
        assert table.cursor_row == 1


@pytest.mark.asyncio
async def test_the_detail_moves_on_when_its_event_leaves_the_buffer(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock, keep_recent=3)
    app = runtime_app(log)

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        for program in ("git", "gh", "tmux"):
            run_command(log, clock, program, 0.01)
        screen.update_shown()
        await pilot.press("ctrl+home")
        await wait_until(lambda: follow_text(app) != "following")
        await wait_until(lambda: detail(app)["process.executable.name"] == "git")

        run_command(log, clock, "uv", 0.01)
        screen.update_shown()
        # The cursor's row now holds the next event, and the detail says so.
        assert event_table(app).cursor_row == 0
        assert detail(app)["process.executable.name"] == "gh"


@pytest.mark.asyncio
async def test_events_the_buffer_lets_go_of_leave_the_table(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock, keep_recent=3)
    app = runtime_app(log)

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        # Recorded once the dashboard is idle, they fill the whole buffer.
        for program in ("git", "gh", "tmux"):
            run_command(log, clock, program, 0.01)
        screen.update_shown()
        assert [row[6] for row in rows(app)] == [
            "git status",
            "gh status",
            "tmux status",
        ]

        await pilot.press("up")
        await wait_until(lambda: follow_text(app) != "following")

        run_command(log, clock, "uv", 0.01)
        screen.update_shown()
        assert [row[6] for row in rows(app)] == [
            "gh status",
            "tmux status",
            "uv status",
        ]
        # The cursor stays on the event it was on, not on the row number.
        table = event_table(app)
        assert str(table.get_row_at(table.cursor_row)[6]) == "gh status"
        # The header says the buffer let go of events by count.
        assert ", buffer full · 3 events" in header(app)


@pytest.mark.asyncio
async def test_a_label_that_reads_as_markup_is_shown_as_written(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    started = refresh(log, "manual")
    observed = key(
        log,
        started,
        ObservationAttributes(kind="worktrees", project_id=PROJECT_ID),
    )
    end_after(observed, clock, 0.5)
    label = "repo [wip] [b]x[/b]"
    snapshot = with_first_project(
        workspace_snapshot(issue("test/repo#1", "First")), display_label=label
    )
    app = dashboard_app(
        SequenceCollector(snapshot), event_log=log, runtime_stats_seconds=3600
    )

    async with app.run_test(size=(160, 40)) as pilot:
        await open_runtime(app, pilot)
        # A Project's label is text a person wrote, never markup.
        table = event_table(app)

        def shown() -> list[str]:
            return [table.render_line(y).text for y in range(table.size.height)]

        await settled(
            pilot,
            lambda: any("repo" in line for line in shown()),
            "the observation rows",
        )
        assert any(label in line for line in shown())


@pytest.mark.asyncio
async def test_the_header_names_the_level_window_and_count(tmp_path: Path) -> None:
    clock = Clock()
    log = stats_log(tmp_path, clock)
    app = runtime_app(log)

    async with app.run_test(size=(160, 40)) as pilot:
        screen = await open_runtime(app, pilot, "s")
        run_command(log, clock, "git", 0.01)
        screen.update_shown()
        count = len(log.recent_events())
        assert header(app) == (
            "Event Level: standard (l changes it) · this dashboard · "
            f"since start · {count:,} events"
        )


@pytest.mark.asyncio
async def test_the_detail_stacks_under_the_table_on_a_narrow_terminal(
    tmp_path: Path,
) -> None:
    app = runtime_app(stats_log(tmp_path, Clock()))

    async with app.run_test(size=(80, 40)) as pilot:
        screen = await open_runtime(app, pilot)
        await settle_screen(app, pilot, "the stacked Runtime screen")
        assert screen.query_one("#runtime-view").has_class("-stacked")
        table = screen.query_one("#runtime-event-table").region
        fields = screen.query_one("#runtime-event-detail").region
        assert fields.y >= table.bottom
        assert fields.width == table.width


@pytest.mark.asyncio
async def test_the_legend_lists_the_runtime_keys(tmp_path: Path) -> None:
    app = runtime_app(stats_log(tmp_path, Clock()))

    async with app.run_test(size=(120, 60)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        keys = squeezed(legend_keys_text(app))
        assert "e Runtime Events" in keys
        assert "s Runtime Stats" in keys
        assert "l Change Event Level" in keys
        assert any(line.endswith("Follow Newest") for line in keys)


@pytest.mark.parametrize(
    ("body", "process", "summary"),
    [
        (
            AgentSessionChanged(change="appeared"),
            {"harness": "claude-code", "session_id": "3df08317-ab55-442a"},
            "appeared claude-code 3df08317",
        ),
        (
            DiagnosticChanged(
                change="appeared",
                source="github",
                code="github-rate-limit",
                severity="warning",
            ),
            {},
            "appeared github:github-rate-limit (warning)",
        ),
        (
            DiagnosticChanged(
                change="cleared", code="event-log-large", severity="info"
            ),
            {},
            "cleared event-log-large (info)",
        ),
        (
            RateLimitPauseChanged(
                change="started", limit="primary", until="2026-09-27T13:00:00Z"
            ),
            {},
            "started primary until "
            + f"{datetime(2026, 9, 27, 13, tzinfo=UTC).astimezone():%H:%M:%S}",
        ),
        (UnattendedPauseChanged(change="ended", signal="idle"), {}, "ended idle"),
        (
            SubagentsAcknowledged(agents=("a3932", "a686b12"), outcome="deleted"),
            {"harness": "claude-code", "session_id": "3df08317-ab55-442a"},
            "deleted despite 2 sub-agents of claude-code 3df08317",
        ),
        (
            SubagentsAcknowledged(agents=("a686b12",), outcome="refused"),
            {"harness": "codex"},
            "refused despite 1 sub-agent of codex",
        ),
        (LevelChanged(previous="standard", current="full"), {}, "standard → full"),
        (ProcessEnd(exit_code=0, duration_seconds=3.5), {}, "exit 0"),
        (EventLogWriteFailed(error_type="ENOSPC"), {}, "ENOSPC"),
        (
            span(span_name="query", attributes=QueryAttributes(key="issues")),
            {},
            "issues",
        ),
        (span(span_name="refresh"), {}, ""),
    ],
)
def test_each_kind_of_event_reads_as_a_short_phrase(
    body: object, process: dict[str, Any], summary: str
) -> None:
    assert event_summary(event(body, **process)) == summary


def test_an_event_without_a_phrase_lists_its_fields() -> None:
    read = read_runtime_event(
        json.dumps(
            {
                "schema": 1,
                "time": "2026-09-27T12:00:00Z",
                "dashpot.level": "standard",
                "service.instance.id": "0123456789abcdef0123456789abcdef",
                "dashpot.process.kind": "command:work-start",
                "event.name": "command.outcome",
                "dashpot.subcommand": "work start",
                "dashpot.outcome.result": "succeeded",
                "dashpot.duration_seconds": 0.5,
            }
        )
    )
    assert read is not None
    assert event_summary(read) == (
        "dashpot.subcommand=work start dashpot.outcome.result=succeeded "
        "dashpot.duration_seconds=0.5"
    )


def test_outcomes_name_a_failure_an_exit_code_or_what_became_of_a_key() -> None:
    assert str(event_outcome(event(EventLogWriteFailed(error_type="EIO")))) == (
        "dropped"
    )
    assert str(event_outcome(event(LevelChanged(previous="off", current="full")))) == ""
    skipped = span(
        span_name="query", attributes=QueryAttributes(key="issues", outcome="skipped")
    )
    assert str(event_outcome(event(skipped))) == "skipped"
    # A non-zero exit read as an answer is no failure, but its code shows.
    exited = span(
        span_name="command",
        attributes=CommandAttributes(program="git", exit_code=128),
    )
    assert str(event_outcome(event(exited))) == "exit 128"


def test_errors_only_keeps_failed_spans_and_dropped_writes() -> None:
    errors = EventFilter(errors_only=True)
    failed = span(span_name="refresh", status="ERROR", error_type="Timeout")
    ok = span(span_name="refresh", status="OK")
    assert accepts(errors, event(failed), "standard")
    assert accepts(errors, event(EventLogWriteFailed(error_type="EIO")), "standard")
    assert not accepts(errors, event(ok), "standard")
    assert not accepts(EventFilter(show="recorded"), event(ok, level="full"), "off")
