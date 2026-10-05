"""Whether anyone attends the dashboard, and the Unattended Pause while nobody does."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dashpot.core.commands import CommandError, CommandResult, run_command
from dashpot.ui.attendance import (
    UNATTENDED_PAUSED,
    Attendance,
    AttendanceChange,
    UnattendedPause,
    period_text,
    tmux_attachment,
)
from factories import remove_working_directory

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
@pytest.mark.usefixtures("local_clock_ten_hours_ahead")
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
        f"GitHub queries paused since 22:00:00: {reason}; any key resumes"
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
    # A grouped session is asked for its whole group's clients.
    grouped = "#{?session_grouped,#{session_group_attached},#{session_attached}}"
    assert runner.calls == [("tmux", "display-message", "-p", "-t", "%3", grouped)]


def test_the_probe_answers_from_a_removed_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stand-in for tmux, run as a real process, starts only where the probe
    # says to: a probe running at the working directory could not start it.
    remove_working_directory(tmp_path, monkeypatch)

    def stand_in(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        return run_command([sys.executable, "-c", "print(1)"], cwd, timeout)

    probe = tmux_attachment(TMUX, 5.0, run=stand_in)

    assert probe is not None
    assert probe() is True


class TmuxServer:
    """A private tmux server, with clients attached in control mode."""

    def __init__(self) -> None:
        self.prefix = (
            "tmux",
            "-L",
            f"dashpot-test-{uuid.uuid4().hex}",
            "-f",
            os.devnull,
        )
        self.environ = {
            key: value for key, value in os.environ.items() if key != "TMUX"
        }
        self.clients: list[subprocess.Popen[bytes]] = []

    def __call__(self, *args: str) -> str:
        return subprocess.run(
            [*self.prefix, *args],
            env=self.environ,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()

    def attach(self, session: str) -> None:
        """Attach a client that stays attached until the server is killed."""
        self.clients.append(
            subprocess.Popen(
                [*self.prefix, "-C", "attach-session", "-t", session],
                env=self.environ,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        self.wait_for_clients(len(self.clients))

    def wait_for_clients(self, count: int) -> None:
        deadline = time.monotonic() + 10
        while len(self("list-clients", "-F", "#{client_name}").split()) != count:
            assert time.monotonic() < deadline, f"tmux never had {count} clients"
            time.sleep(0.05)

    def run(self, args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        """Run a probe's ``tmux`` command against this server."""
        assert args[0] == "tmux"
        return run_command([*self.prefix, *args[1:]], cwd, timeout)

    def close(self) -> None:
        """Kill the server, its clients and its socket, which tmux leaves behind."""
        socket: str | None = None
        with contextlib.suppress(subprocess.SubprocessError):
            socket = self("display-message", "-p", "#{socket_path}")
            self("kill-server")
        if socket:
            Path(socket).unlink(missing_ok=True)
        for client in self.clients:
            if client.stdin is not None:
                client.stdin.close()
            try:
                client.wait(timeout=10)
            except subprocess.TimeoutExpired:
                client.kill()
                client.wait()


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_a_client_of_another_session_in_the_group_attends() -> None:
    # ``tmux new -t main -s viewer`` groups viewer with main: both hold the
    # dashboard's pane. With a client on each and main's then detached, tmux
    # resolves the pane to main, the session active last, which no client
    # holds; the client still watching viewer sees the pane all the same.
    tmux = TmuxServer()
    try:
        tmux("new-session", "-d", "-s", "main", "-x", "80", "-y", "24")
        tmux("new-session", "-d", "-t", "main", "-s", "viewer")
        pane = tmux("display-message", "-p", "-t", "main", "#{pane_id}")
        tmux.attach("viewer")
        tmux.attach("main")
        tmux("detach-client", "-s", "main")
        tmux.wait_for_clients(1)
        assert (
            tmux(
                "display-message",
                "-p",
                "-t",
                pane,
                "#{session_name} #{session_attached}",
            )
            == "main 0"
        )
        probe = tmux_attachment({"TMUX": "set", "TMUX_PANE": pane}, 5.0, run=tmux.run)

        assert probe is not None
        assert probe() is True

        tmux("detach-client", "-s", "viewer")
        tmux.wait_for_clients(0)
        assert probe() is False
    finally:
        tmux.close()


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
