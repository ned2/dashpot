"""Exiting the dashboard releases the pool threads before interpreter exit joins them."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from threading import Event
from unittest import mock

import pytest

from app_harness import SequenceCollector, dashboard_app, issue, workspace_snapshot
from dashpot.core.commands import CommandError, run_command
from dashpot.core.event_log import Span, current_span, unrecorded_event_log
from dashpot.core.model import WorkspaceSnapshot
from dashpot.core.runtime_events import SpanEnded
from helpers import wait_until

# An observation that would outlive the test unless the exit interrupts it.
SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


@pytest.mark.asyncio
async def test_exit_interrupts_the_observation_command_in_flight() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    finished = Event()
    outcomes: list[CommandError] = []

    def collect() -> WorkspaceSnapshot:
        # On a refresh-pool thread, which adopted the app's registry.
        try:
            run_command(SLEEP, Path.cwd(), 30)
        except CommandError as exc:
            outcomes.append(exc)
            raise
        finally:
            finished.set()
        return snapshot

    collector = SequenceCollector(snapshot)
    app = dashboard_app(collector)
    running = app.running_commands

    with mock.patch.object(collector, "refresh", side_effect=collect):
        async with app.run_test(size=(80, 24)):
            await wait_until(lambda: len(running) == 1)
            assert app.observations.in_flight

    # The app has exited while the observation's command was running; the
    # thread is released by the interruption rather than by the command.
    assert finished.wait(5)
    # The registry stays closed: the exited dashboard's threads start nothing.
    assert running.closed
    (outcome,) = outcomes
    assert str(outcome) == f"command interrupted at shutdown: {sys.executable}"
    # Nothing of the interrupted observation reached the store.
    assert not app.store.has_observations


@pytest.mark.asyncio
async def test_exit_with_nothing_in_flight_interrupts_nothing() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(snapshot)
    app = dashboard_app(collector)
    running = app.running_commands

    with mock.patch.object(running, "interrupt", wraps=running.interrupt) as interrupt:
        async with app.run_test(size=(80, 24)):
            await wait_until(lambda: app.store.has_observations)

    interrupt.assert_called_once_with()
    assert running.closed


@pytest.mark.asyncio
async def test_exit_interrupts_a_command_started_inside_a_span_off_the_loop() -> None:
    """Carrying the current span keeps the pool thread's own command registry."""
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(snapshot)
    log = unrecorded_event_log(keep_recent=10)
    log.set_level("full")
    app = dashboard_app(collector, event_log=log)
    running = app.running_commands
    seen: list[Span | None] = []
    outcomes: list[CommandError] = []

    def operation() -> None:
        seen.append(current_span())
        try:
            run_command(SLEEP, Path.cwd(), 30)
        except CommandError as exc:
            outcomes.append(exc)
            raise

    async def spanned() -> None:
        with log.start_as_current_span("command"):
            await app.off_loop(operation)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.has_observations)
        task = asyncio.create_task(spanned())
        await wait_until(lambda: len(running) == 1)

    with pytest.raises(CommandError):
        await asyncio.wait_for(task, 5)
    (outcome,) = outcomes
    assert str(outcome) == f"command interrupted at shutdown: {sys.executable}"
    (carried,) = seen
    assert carried is not None
    spans = [event.body for event in log.recent if isinstance(event.body, SpanEnded)]
    (ended,) = [span for span in spans if span.span_id == carried.span_id]
    (command,) = [span for span in spans if span.parent_span_id == carried.span_id]
    # The interruption fails both spans by its code, never by its message.
    assert (ended.status, ended.error_type) == ("ERROR", "command-interrupted")
    assert (command.status, command.error_type) == ("ERROR", "command-interrupted")
