"""The dashboard holds automatic GitHub refreshes while nobody attends it."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from unittest import mock

import pytest
from textual import events
from textual.widgets import Input, Static

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    show_query_peer,
    workspace_snapshot,
)
from dashpot.core.event_log import DASHBOARD_KIND, EventLog, EventLogDestination
from dashpot.core.runtime_events import (
    ProcessIdentity,
    ProcessStart,
    UnattendedPauseChanged,
)
from dashpot.github.github import GitHubRequestError, LatestRateLimit
from dashpot.observation.keys import (
    ObservationKey,
    ObservationOutcome,
    ObservationTicket,
)
from dashpot.ui.app import DashpotApp
from dashpot.ui.attendance import Attendance
from dashpot.ui.messages import ObservationFinished
from helpers import wait_until

RUN = "0123456789abcdef0123456789abcdef"
NOON = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
IDLE = 600.0


class Clock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Probe:
    """A tmux attachment probe answering whatever the test last set."""

    def __init__(self, attached: bool | None) -> None:
        self.attached = attached
        self.calls = 0

    def __call__(self) -> bool | None:
        self.calls += 1
        return self.attached


def event_log(directory: Path) -> EventLog:
    return EventLog(
        EventLogDestination(directory),
        identity=ProcessIdentity(run_id=RUN, kind=DASHBOARD_KIND),
        level="standard",
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision="unknown",
            pid=os.getpid(),
            python_version="3.14.0",
        ),
        keep_recent=100,
    )


def pause_changes(app: DashpotApp) -> list[tuple[str, str]]:
    return [
        (event.body.change, event.body.signal)
        for event in app.event_log.recent_events()
        if isinstance(event.body, UnattendedPauseChanged)
    ]


def diagnostics_text(app: DashpotApp) -> str:
    return str(app.query_one("#diagnostics", Static).render())


def attended_app(
    tmp_path: Path,
    clock: Clock,
    *,
    probe: Probe | None = None,
    rate_limit: LatestRateLimit | None = None,
) -> DashpotApp:
    return dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        event_log=event_log(tmp_path),
        rate_limit=rate_limit,
        attendance=Attendance(
            idle_seconds=IDLE, probe=probe, clock=clock, wall_clock=lambda: NOON
        ),
    )


def agent_runs_landed(app: DashpotApp) -> None:
    """Deliver one landed Agent Runs observation, as the local period does."""
    ticket = ObservationTicket(ObservationKey("agent-runs", "project:test-repo"), 1)
    app.on_observation_finished(
        ObservationFinished(
            ticket, "timer", outcome=ObservationOutcome(ticket, accepted=True)
        )
    )


def idle_pause(app: DashpotApp, clock: Clock, ticks: mock.Mock) -> None:
    """Let the idle period pass, then tick: the pause starts and nothing is sent."""
    clock.now += IDLE
    app.timer_query_refresh()
    assert app.attendance is not None and app.attendance.pause is not None
    ticks.assert_not_called()


@pytest.mark.asyncio
async def test_an_attended_dashboard_refreshes_github_on_each_tick(
    tmp_path: Path,
) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        with mock.patch.object(app, "query_tick") as ticks:
            clock.now = IDLE - 1
            app.timer_query_refresh()

        ticks.assert_called_once_with()
        assert pause_changes(app) == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("local_clock_ten_hours_ahead")
async def test_an_idle_dashboard_pauses_and_a_key_resumes_with_a_refresh(
    tmp_path: Path,
) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        with mock.patch.object(app, "query_tick") as ticks:
            idle_pause(app, clock, ticks)
            # Later ticks stay paused.
            clock.now = IDLE * 3
            app.timer_query_refresh()
            ticks.assert_not_called()

            assert pause_changes(app) == [("started", "idle")]
            await wait_until(lambda: "GitHub queries paused" in diagnostics_text(app))
            assert (
                "↻ github: GitHub queries paused since 22:00:00: no key or "
                "mouse input for 10m; any key resumes"
            ) in diagnostics_text(app)

            await pilot.press("down")

            ticks.assert_called_once_with()
        assert pause_changes(app) == [("started", "idle"), ("ended", "idle")]
        await wait_until(lambda: "GitHub queries paused" not in diagnostics_text(app))


@pytest.mark.asyncio
async def test_resuming_sends_the_github_refresh_it_skipped(tmp_path: Path) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        with mock.patch.object(app, "refresh_queries") as refreshes:
            clock.now = IDLE
            app.timer_query_refresh()
            refreshes.assert_not_called()

            await pilot.press("down")

        refreshes.assert_called_once()
        assert refreshes.call_args.kwargs["restart"] is False


@pytest.mark.asyncio
async def test_the_refresh_key_resumes_and_still_refreshes_everything(
    tmp_path: Path,
) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        with (
            mock.patch.object(app, "query_tick") as ticks,
            mock.patch.object(app, "request_refresh") as manual,
        ):
            idle_pause(app, clock, ticks)

            await pilot.press("r")

            await wait_until(lambda: manual.call_count == 1)
            manual.assert_called_once_with("manual")
            ticks.assert_called_once_with()
        assert pause_changes(app) == [("started", "idle"), ("ended", "idle")]


@pytest.mark.asyncio
async def test_a_refresh_key_typed_into_search_still_resumes_with_a_refresh(
    tmp_path: Path,
) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        search = app.query_screen.query_one("#pull-request-search", Input)
        search.focus()
        await wait_until(lambda: search.has_focus)
        with (
            mock.patch.object(app, "query_tick") as ticks,
            mock.patch.object(app, "request_refresh") as manual,
        ):
            idle_pause(app, clock, ticks)

            await pilot.press("r")

            # The Input took the key, so no manual refresh stood in for
            # the resume's own.
            ticks.assert_called_once_with()
            await wait_until(lambda: search.value == "r")
            manual.assert_not_called()


@pytest.mark.asyncio
async def test_bound_issues_wait_for_the_resume_while_paused(tmp_path: Path) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        with (
            mock.patch.object(app, "query_tick") as ticks,
            mock.patch.object(app, "request_identities") as identities,
        ):
            # Attended, a local tick's Agent Runs resolve any newly bound Issue.
            agent_runs_landed(app)
            identities.assert_called_once_with(changed_only=True)
            identities.reset_mock()

            idle_pause(app, clock, ticks)
            agent_runs_landed(app)

            identities.assert_not_called()


@pytest.mark.asyncio
async def test_mouse_input_and_focus_each_resume(tmp_path: Path) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)
    moved = events.MouseMove(None, 1, 1, 0, 0, 0, False, False, False)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        with mock.patch.object(app, "query_tick") as ticks:
            idle_pause(app, clock, ticks)
            app.post_message(moved)
            await wait_until(lambda: ticks.call_count == 1)

            ticks.reset_mock()
            idle_pause(app, clock, ticks)
            app.post_message(events.AppFocus())
            await wait_until(lambda: ticks.call_count == 1)


@pytest.mark.asyncio
async def test_a_detached_tmux_session_pauses_until_a_client_reattaches(
    tmp_path: Path,
) -> None:
    clock = Clock()
    probe = Probe(attached=False)
    app = attended_app(tmp_path, clock, probe=probe)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        attendance = app.attendance
        assert attendance is not None
        with mock.patch.object(app, "query_tick") as ticks:
            # The probe runs off the loop; this tick still refreshes.
            app.timer_query_refresh()
            await wait_until(lambda: attendance.pause is not None)
            assert ticks.call_count == 1
            await wait_until(lambda: not app.probing_attachment)

            app.timer_query_refresh()
            assert ticks.call_count == 1
            assert pause_changes(app) == [("started", "detached")]
            await wait_until(lambda: "no tmux client attached" in diagnostics_text(app))

            await wait_until(lambda: not app.probing_attachment)
            probe.attached = True
            app.timer_query_refresh()
            await wait_until(lambda: attendance.pause is None)

            # Reattaching refreshes at once, not a GitHub Refresh Period later.
            assert ticks.call_count == 2
        assert pause_changes(app) == [("started", "detached"), ("ended", "detached")]


@pytest.mark.asyncio
async def test_an_unanswered_probe_leaves_the_dashboard_as_it_was(
    tmp_path: Path,
) -> None:
    clock = Clock()
    probe = Probe(attached=None)
    app = attended_app(tmp_path, clock, probe=probe)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        app.timer_query_refresh()
        await wait_until(lambda: probe.calls == 1 and not app.probing_attachment)

        assert app.attendance is not None and app.attendance.pause is None
        assert pause_changes(app) == []


@pytest.mark.asyncio
async def test_one_probe_runs_at_a_time(tmp_path: Path) -> None:
    clock = Clock()
    release = Event()

    def held() -> bool:
        release.wait(timeout=5)
        return True

    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        attendance=Attendance(idle_seconds=IDLE, probe=held, clock=clock),
    )

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
        with mock.patch.object(app, "run_off_loop", wraps=app.run_off_loop) as runs:
            app.timer_query_refresh()
            app.timer_query_refresh()
            release.set()
            await wait_until(lambda: not app.probing_attachment)

        probes = [call for call in runs.call_args_list if call.args[1] == "attendance"]
        assert len(probes) == 1


@pytest.mark.asyncio
async def test_resuming_does_not_skip_a_rate_limit_pause(tmp_path: Path) -> None:
    clock = Clock()
    shared = LatestRateLimit()
    app = attended_app(tmp_path, clock, rate_limit=shared)

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        clock.now = IDLE
        app.timer_query_refresh()
        shared.refused(shared.admit(), "primary")
        started = shared.pause

        await pilot.press("down")

        # Unlike the refresh key, attending lifts nothing: the Rate Limit
        # Pause still holds every request.
        assert shared.pause == started
        with pytest.raises(GitHubRequestError):
            shared.admit()


@pytest.mark.asyncio
async def test_resuming_restarts_the_github_refresh_period(tmp_path: Path) -> None:
    clock = Clock()
    app = dashboard_app(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        query_refresh_seconds=3_600,
        attendance=Attendance(idle_seconds=IDLE, clock=clock),
    )

    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        timer = app.query_refresh_timer
        assert timer is not None
        with (
            mock.patch.object(app, "query_tick") as ticks,
            mock.patch.object(timer, "reset") as reset,
        ):
            idle_pause(app, clock, ticks)

            await pilot.press("down")

            reset.assert_called_once_with()
            ticks.assert_called_once_with()


@pytest.mark.asyncio
async def test_a_change_after_exit_is_recorded_and_draws_nothing(
    tmp_path: Path,
) -> None:
    clock = Clock()
    app = attended_app(tmp_path, clock)

    async with app.run_test(size=(120, 30)):
        await wait_until(lambda: first_load_landed(app))
    attendance = app.attendance
    assert attendance is not None and app.closing

    with (
        mock.patch.object(app, "update_diagnostics") as redraw,
        mock.patch.object(app, "query_tick") as ticks,
    ):
        app.attendance_changed(attendance.probed(False))
        app.attendance_changed(attendance.attended())

    redraw.assert_not_called()
    ticks.assert_not_called()
    assert pause_changes(app) == [("started", "detached"), ("ended", "detached")]
