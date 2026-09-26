"""The dashboard records to the Event Log it is given, and carries on when it cannot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from textual.widgets import Static

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    workspace_snapshot,
)
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    EventLog,
    EventLogDestination,
    current_span,
)
from dashpot.core.runtime_events import (
    EventLevel,
    EventLogWriteFailed,
    LevelChanged,
    ProcessIdentity,
    ProcessStart,
    RefreshAttributes,
    SpanEnded,
)
from dashpot.project.settings import default_settings_path
from dashpot.ui.app import DashpotApp
from helpers import wait_until

RUN = "0123456789abcdef0123456789abcdef"


def event_log(directory: Path, *, level: EventLevel = "standard") -> EventLog:
    return EventLog(
        EventLogDestination(directory),
        identity=ProcessIdentity(run_id=RUN, kind=DASHBOARD_KIND),
        level=level,
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision="unknown",
            pid=os.getpid(),
            python_version="3.14.0",
        ),
        keep_recent=100,
    )


def unwritable(tmp_path: Path) -> Path:
    blocker = tmp_path / "file"
    blocker.write_text("")
    return blocker / "events"


def diagnostics_text(app: DashpotApp) -> str:
    return str(app.query_one("#diagnostics", Static).render())


def written_lines(log: EventLog) -> list[str]:
    assert log.path is not None
    return log.path.read_text().splitlines()


def app_over(log: EventLog) -> DashpotApp:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    return dashboard_app(SequenceCollector(snapshot), event_log=log)


@pytest.mark.asyncio
async def test_a_write_failing_on_a_pool_thread_raises_one_diagnostic(
    tmp_path: Path,
) -> None:
    log = event_log(unwritable(tmp_path))
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        await app.off_loop(lambda: log.start_span("command", level="standard").end())
        await app.off_loop(lambda: log.start_span("command", level="standard").end())
        await wait_until(lambda: "event-log" in repr(app.event_log_diagnostics))

        (diagnostic,) = app.event_log_diagnostics
        assert diagnostic.code == "event-log-unavailable"
        assert diagnostic.severity == "warning"
        assert "Cannot write the Event Log" in diagnostics_text(app)
        assert "ENOTDIR" in diagnostics_text(app)
    failures = [
        event for event in log.recent if isinstance(event.body, EventLogWriteFailed)
    ]
    assert len(failures) == 2
    assert log.on_write_failure is None
    assert log.forward is None


@pytest.mark.asyncio
async def test_a_failure_before_the_dashboard_started_is_shown_once_it_does(
    tmp_path: Path,
) -> None:
    log = event_log(unwritable(tmp_path))
    log.start()
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))

        assert "Cannot write the Event Log" in diagnostics_text(app)


@pytest.mark.asyncio
async def test_changing_the_level_lasts_for_the_run_and_never_the_settings(
    tmp_path: Path,
) -> None:
    settings = default_settings_path()
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("event_level = 'standard'\n")
    log = event_log(tmp_path)
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        app.set_event_level("full")

    assert log.level == "full"
    assert settings.read_text() == "event_level = 'standard'\n"
    changes = [
        event.body for event in log.recent if isinstance(event.body, LevelChanged)
    ]
    assert changes == [LevelChanged(previous="standard", current="full")]
    assert '"event.name":"level.changed"' in written_lines(log)[-1]


@pytest.mark.asyncio
async def test_a_dashboard_without_an_event_log_keeps_its_events_in_memory() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        app.set_event_level("full")

    assert app.event_log.destination is None
    names = [event.body.name for event in app.event_log.recent]
    # The first load's spans, then the change of level.
    assert set(names[:-1]) == {"span"}
    assert names[-1] == "level.changed"


@pytest.mark.asyncio
async def test_recorded_lines_reach_textuals_console_only_while_it_is_attached(
    tmp_path: Path,
) -> None:
    log = event_log(tmp_path)
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        loop = mock.Mock()
        with mock.patch.object(app, "main_loop", loop):
            log.start()
            loop.call_soon_threadsafe.assert_not_called()
            with mock.patch.object(app, "devtools", mock.Mock(is_connected=True)):
                await app.off_loop(lambda: log.end(0))

    ((_, line),) = [call.args for call in loop.call_soon_threadsafe.call_args_list]
    assert '"event.name":"process.end"' in line
    assert line == written_lines(log)[-1]


@pytest.mark.asyncio
async def test_work_run_off_the_loop_keeps_the_span_it_was_started_in(
    tmp_path: Path,
) -> None:
    log = event_log(tmp_path, level="full")
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        with log.start_as_current_span("command") as span:
            seen = await app.off_loop(current_span)
        after = await app.off_loop(current_span)

    assert seen is span
    assert after is None


def test_a_failure_before_the_dashboard_runs_is_shown_when_it_does(
    tmp_path: Path,
) -> None:
    app = app_over(event_log(tmp_path))

    app.event_log_write_failed("EACCES")
    app.event_log_write_failed("ENOSPC")

    (diagnostic,) = app.event_log_diagnostics
    assert "(EACCES)" in diagnostic.message
    assert str(tmp_path) in diagnostic.message


def ended_spans(log: EventLog) -> list[SpanEnded]:
    return [event.body for event in log.recent if isinstance(event.body, SpanEnded)]


def refreshes(log: EventLog) -> dict[str, SpanEnded]:
    return {
        span.attributes.trigger: span
        for span in ended_spans(log)
        if isinstance(span.attributes, RefreshAttributes)
    }


def children(log: EventLog, parent: SpanEnded) -> set[str]:
    return {
        span.span_name
        for span in ended_spans(log)
        if span.parent_span_id == parent.span_id
    }


@pytest.mark.asyncio
async def test_each_refresh_is_a_span_over_the_keys_it_asked_for(
    tmp_path: Path,
) -> None:
    log = event_log(tmp_path, level="full")
    app = app_over(log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: "initial" in refreshes(log))
        app.timer_refresh()
        await wait_until(lambda: "local" in refreshes(log))
        app.timer_query_refresh()
        await wait_until(lambda: "github" in refreshes(log))

    ended = refreshes(log)
    assert {span.parent_span_id for span in ended.values()} == {None}
    # The first load observes the Workspace and queries the pages.
    assert children(log, ended["initial"]) == {"observation", "query"}
    assert children(log, ended["local"]) == {"observation"}
    assert children(log, ended["github"]) == {"query"}
    # On disk a refresh records its trigger and nothing else of its own.
    (line,) = [
        record
        for record in map(json.loads, written_lines(log))
        if record.get("span_id") == ended["initial"].span_id
    ]
    assert line["attributes"] == {"dashpot.refresh.trigger": "initial"}
