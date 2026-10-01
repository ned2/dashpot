"""Whether anyone attends the dashboard, and the Unattended Pause while nobody does."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dashpot.core.commands import CommandError, CommandResult
from dashpot.ui.attendance import (
    UNATTENDED_PAUSED,
    Attendance,
    AttendanceChange,
    UnattendedPause,
    period_text,
    tmux_attachment,
)

NOON = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class Clock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def attendance(clock: Clock, *, idle_seconds: float = 600.0) -> Attendance:
    return Attendance(idle_seconds=idle_seconds, clock=clock, wall_clock=lambda: NOON)


def test_idleness_starts_a_pause_only_once_the_idle_period_passes() -> None:
    clock = Clock()
    watched = attendance(clock)

    clock.now = 599.0
    assert watched.check_idle() is None
    assert watched.pause is None

    clock.now = 600.0
    change = watched.check_idle()

    assert change == AttendanceChange("started", UnattendedPause("idle", NOON))
    assert watched.pause == UnattendedPause("idle", NOON)
    # A pause already held is not started again.
    clock.now = 1_200.0
    assert watched.check_idle() is None


def test_input_restarts_the_idle_period() -> None:
    clock = Clock()
    watched = attendance(clock)

    clock.now = 500.0
    assert watched.attended() is None
    clock.now = 1_000.0

    assert watched.check_idle() is None
    clock.now = 1_100.0
    assert watched.check_idle() is not None


def test_a_zero_idle_period_never_pauses_for_idleness() -> None:
    clock = Clock()
    watched = attendance(clock, idle_seconds=0)

    clock.now = 1e9

    assert watched.check_idle() is None


def test_input_ends_a_pause_and_names_what_started_it() -> None:
    clock = Clock()
    watched = attendance(clock)
    clock.now = 600.0
    watched.check_idle()

    change = watched.attended()

    assert change == AttendanceChange("ended", UnattendedPause("idle", NOON))
    assert watched.pause is None
    assert watched.diagnostics() == ()


def test_a_detached_session_pauses_until_a_client_reattaches() -> None:
    watched = attendance(Clock())

    assert watched.probed(True) is None
    assert watched.probed(False) == AttendanceChange(
        "started", UnattendedPause("detached", NOON)
    )
    # Still detached: the pause already holds.
    assert watched.probed(False) is None
    assert watched.probed(True) == AttendanceChange(
        "ended", UnattendedPause("detached", NOON)
    )
    assert watched.pause is None


def test_a_client_reattaching_after_an_unreadable_probe_resumes() -> None:
    watched = attendance(Clock())
    watched.probed(False)
    watched.probed(None)

    assert watched.probed(True) == AttendanceChange(
        "ended", UnattendedPause("detached", NOON)
    )


def test_an_unknown_answer_changes_nothing() -> None:
    watched = attendance(Clock())
    watched.probed(False)

    assert watched.probed(None) is None
    assert watched.pause == UnattendedPause("detached", NOON)


def test_an_idle_pause_outlasts_a_client_that_stayed_attached() -> None:
    clock = Clock()
    watched = attendance(clock)
    watched.probed(True)
    clock.now = 600.0
    watched.check_idle()

    assert watched.probed(True) is None
    assert watched.pause == UnattendedPause("idle", NOON)


def test_detaching_during_an_idle_pause_keeps_the_idle_signal() -> None:
    clock = Clock()
    watched = attendance(clock)
    clock.now = 600.0
    watched.check_idle()

    assert watched.probed(False) is None
    # Reattaching is someone attending, whatever started the pause.
    assert watched.probed(True) == AttendanceChange(
        "ended", UnattendedPause("idle", NOON)
    )


@pytest.mark.parametrize(
    ("idle_seconds", "signal", "reason"),
    [
        (7_200.0, "idle", "no key or mouse input for 2h"),
        (5_430.0, "idle", "no key or mouse input for 1h 30m 30s"),
        (600.0, "detached", "no tmux client attached"),
    ],
)
def test_a_pause_is_one_info_diagnostic_line(
    idle_seconds: float, signal: str, reason: str
) -> None:
    clock = Clock()
    watched = attendance(clock, idle_seconds=idle_seconds)
    if signal == "idle":
        clock.now = idle_seconds
        watched.check_idle()
    else:
        watched.probed(False)

    (diagnostic,) = watched.diagnostics()

    assert diagnostic.code == UNATTENDED_PAUSED
    assert diagnostic.severity == "info"
    assert diagnostic.source == "github"
    assert diagnostic.message == (
        f"GitHub queries paused since 12:00:00 UTC: {reason}; any key resumes"
    )


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0s"),
        (0.5, "0.5s"),
        (45, "45s"),
        (60, "1m"),
        (90.5, "1m 30s"),
        (3_600, "1h"),
        (3_661, "1h 1m 1s"),
    ],
)
def test_a_period_is_written_in_its_largest_units(seconds: float, text: str) -> None:
    assert period_text(seconds) == text


class Runner:
    """A command runner answering every command with one result or failure."""

    def __init__(self, answer: CommandResult | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        self.calls.append(tuple(args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def result(stdout: str, returncode: int = 0) -> CommandResult:
    return CommandResult(["tmux"], returncode, stdout, "")


TMUX = {"TMUX": "/tmp/tmux-1000/default,1,0", "TMUX_PANE": "%3"}


@pytest.mark.parametrize("environ", [{}, {"TMUX": TMUX["TMUX"]}, {"TMUX_PANE": "%3"}])
def test_outside_tmux_there_is_no_probe(environ: dict[str, str]) -> None:
    assert tmux_attachment(environ, 1.0, run=Runner(result("1\n"))) is None


@pytest.mark.parametrize(("stdout", "attached"), [("1\n", True), ("0\n", False)])
def test_the_probe_asks_how_many_clients_attend_the_panes_session(
    stdout: str, attached: bool
) -> None:
    runner = Runner(result(stdout))
    probe = tmux_attachment(TMUX, 1.0, run=runner)

    assert probe is not None
    assert probe() is attached
    assert runner.calls == [
        ("tmux", "display-message", "-p", "-t", "%3", "#{session_attached}")
    ]


@pytest.mark.parametrize(
    "answer",
    [
        result("1\n", returncode=1),
        result("no server running\n"),
        result(""),
        CommandError("tmux timed out", code="command-timed-out"),
        FileNotFoundError("tmux"),
    ],
)
def test_a_probe_that_cannot_tell_answers_none(
    answer: CommandResult | Exception,
) -> None:
    probe = tmux_attachment(TMUX, 1.0, run=Runner(answer))

    assert probe is not None
    assert probe() is None


def test_a_pause_starts_at_the_current_utc_time_by_default() -> None:
    watched = Attendance(idle_seconds=600)
    before = datetime.now(UTC)

    change = watched.probed(False)

    assert change is not None
    assert change.pause.since.tzinfo is UTC
    assert before <= change.pause.since <= datetime.now(UTC)
