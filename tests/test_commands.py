"""The command runner: one bounded child per command, interruptible at shutdown."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from contextvars import copy_context
from pathlib import Path
from threading import Thread
from typing import Any, Literal
from unittest import mock

import pytest

from dashpot.core import commands
from dashpot.core.commands import (
    CommandError,
    CommandResult,
    RunningCommands,
    adopted_commands,
    run_command,
)

# Long enough that only an interruption can end it inside the test.
SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]
# Long enough to outlast an interruption, short enough to wait out.
BRIEF = [sys.executable, "-c", "import time; time.sleep(0.3); print('done')"]
PROMPT = 5.0


def start_command(
    args: list[str],
    running: RunningCommands,
    *,
    interruptible: bool = True,
    non_interactive: bool = False,
) -> tuple[Thread, list[CommandResult | CommandError]]:
    """Run ``args`` on a thread that adopted ``running``, keeping its outcome."""
    outcomes: list[CommandResult | CommandError] = []

    def run() -> None:
        running.adopt()
        try:
            outcomes.append(
                run_command(
                    args,
                    Path.cwd(),
                    30,
                    interruptible=interruptible,
                    non_interactive=non_interactive,
                )
            )
        except CommandError as exc:
            outcomes.append(exc)

    thread = Thread(target=run, name="test-command")
    thread.start()
    return thread, outcomes


def adopting(running: RunningCommands, call: Callable[[], Any]) -> Any:
    """Run ``call`` with ``running`` adopted, in a context of this thread's own."""

    def run() -> Any:
        running.adopt()
        return call()

    return copy_context().run(run)


def popen_recording(started: list[subprocess.Popen[Any]]) -> Callable[..., Any]:
    """A ``Popen`` that starts each command for real and keeps it in ``started``."""
    real_popen = subprocess.Popen

    def record(*args: Any, **kwargs: Any) -> Any:
        started.append(process := real_popen(*args, **kwargs))
        return process

    return record


def exited_unreaped(process: subprocess.Popen[Any]) -> bool:
    """Whether ``process`` has exited and is left for its ``Popen`` to reap."""
    flags = os.WEXITED | os.WNOHANG | os.WNOWAIT
    return os.waitid(os.P_PID, process.pid, flags) is not None


def wait_for(predicate: Callable[[], bool], timeout: float = PROMPT) -> None:
    """Block until ``predicate`` holds, failing rather than hanging."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition was not met before timeout"
        time.sleep(0.01)


def test_an_interrupted_command_is_a_failure_never_an_answer() -> None:
    running = RunningCommands()
    thread, outcomes = start_command(SLEEP, running)
    wait_for(lambda: len(running) == 1)

    # Sharing Dashpot's process group, the command is signalled alone.
    with mock.patch.object(os, "killpg") as killpg:
        assert running.interrupt() == 1

    killpg.assert_not_called()

    thread.join(PROMPT)
    assert not thread.is_alive()
    (outcome,) = outcomes
    assert isinstance(outcome, CommandError)
    assert str(outcome) == f"command interrupted at shutdown: {sys.executable}"
    # The registry forgets a command once it has ended, however it ended.
    assert len(running) == 0


def test_an_interrupted_registry_refuses_every_later_command() -> None:
    # An observation runs commands in turn and tolerates one failing, so
    # the command it would start next is refused before it spawns.
    running = RunningCommands()
    outcomes: list[CommandResult | CommandError] = []

    def observe() -> None:
        running.adopt()
        for args in (SLEEP, BRIEF):
            try:
                outcomes.append(run_command(args, Path.cwd(), 30))
            except CommandError as exc:
                outcomes.append(exc)

    thread = Thread(target=observe, name="test-observation")
    thread.start()
    wait_for(lambda: len(running) == 1)

    assert running.interrupt() == 1

    thread.join(PROMPT)
    assert not thread.is_alive()
    assert running.closed
    assert [str(outcome) for outcome in outcomes] == [
        f"command interrupted at shutdown: {sys.executable}",
        f"command interrupted at shutdown: {sys.executable}",
    ]
    # The close is for good: the registry belongs to one dashboard, and
    # nothing runs on its threads after it has exited.
    assert running.interrupt() == 0
    with pytest.raises(CommandError, match="interrupted at shutdown"):
        adopting(running, lambda: run_command(BRIEF, Path.cwd(), 30))


@pytest.mark.parametrize("non_interactive", [False, True])
def test_a_command_registering_during_the_interruption_is_stopped(
    non_interactive: bool,
) -> None:
    # The window between the closed check and the registration: a process
    # already started is signalled as it registers rather than slipping past,
    # as its whole process group when it runs in a session of its own.
    running = RunningCommands()
    started: list[subprocess.Popen[Any]] = []
    signalled: list[tuple[int, int]] = []
    record = popen_recording(started)
    real_killpg = os.killpg

    def popen_then_interrupt(*args: Any, **kwargs: Any) -> Any:
        process = record(*args, **kwargs)
        assert running.interrupt() == 0
        return process

    def recording_killpg(pgid: int, signum: int) -> None:
        signalled.append((pgid, signum))
        real_killpg(pgid, signum)

    with (
        mock.patch.object(subprocess, "Popen", side_effect=popen_then_interrupt),
        mock.patch.object(os, "killpg", recording_killpg),
        pytest.raises(CommandError, match="interrupted at shutdown"),
    ):
        adopting(
            running,
            lambda: run_command(SLEEP, Path.cwd(), 30, non_interactive=non_interactive),
        )

    (process,) = started
    assert signalled == ([(process.pid, signal.SIGTERM)] if non_interactive else [])
    assert len(running) == 0
    assert running.closed


def test_a_mutation_runs_to_completion_through_an_interruption() -> None:
    running = RunningCommands()
    thread, outcomes = start_command(BRIEF, running, interruptible=False)

    # Nothing is registered, so nothing is counted or signalled.
    assert running.interrupt() == 0

    thread.join(PROMPT)
    (outcome,) = outcomes
    assert isinstance(outcome, CommandResult)
    assert outcome.returncode == 0
    assert outcome.stdout == "done\n"


def test_a_mutation_starts_after_the_interruption_too() -> None:
    running = RunningCommands()
    running.interrupt()

    result = adopting(
        running,
        lambda: run_command(
            BRIEF, Path.cwd(), 10, non_interactive=True, interruptible=False
        ),
    )

    assert result.stdout == "done\n"
    with pytest.raises(CommandError, match="interrupted at shutdown"):
        adopting(
            running,
            lambda: run_command(BRIEF, Path.cwd(), 10, non_interactive=True),
        )


def test_a_thread_that_adopted_nothing_is_never_registered() -> None:
    running = RunningCommands()
    seen: list[RunningCommands | None] = []

    def observe() -> None:
        seen.append(adopted_commands())
        run_command(BRIEF, Path.cwd(), 30)

    thread = Thread(target=observe, name="test-unadopted")
    thread.start()
    thread.join(PROMPT)

    assert seen == [None]
    assert len(running) == 0


def test_every_thread_of_the_registry_pool_adopts_it() -> None:
    running = RunningCommands()
    with running.pool(max_workers=2, thread_name_prefix="test-pool") as pool:
        adopted = {pool.submit(adopted_commands).result() for _ in range(4)}
        held = pool.submit(run_command, SLEEP, Path.cwd(), 30)
        wait_for(lambda: len(running) == 1)

        assert running.interrupt() == 1

        with pytest.raises(CommandError, match="interrupted at shutdown"):
            held.result(PROMPT)
    assert adopted == {running}
    assert adopted_commands() is None


def test_a_finished_command_is_not_counted() -> None:
    running = RunningCommands()

    result = adopting(
        running,
        lambda: run_command([sys.executable, "-c", "print('done')"], Path.cwd(), 10),
    )

    assert result.returncode == 0
    assert result.stdout == "done\n"
    assert len(running) == 0
    assert running.interrupt() == 0


def test_a_command_that_ended_while_still_held_is_not_signalled() -> None:
    # The registry learns a command has ended only when its runner lets go;
    # one that exited on its own in the meantime is neither counted nor
    # reported as interrupted.
    running = RunningCommands()
    with (
        subprocess.Popen([sys.executable, "-c", "pass"]) as process,
        running.holding(process, group=False),
    ):
        process.wait(PROMPT)

        assert running.interrupt() == 0

        assert not running.interrupted(process)
    assert process.returncode == 0


def test_a_command_let_go_during_the_interruption_is_not_signalled() -> None:
    # The window between the interruption's snapshot and its signal: a
    # runner that let go of its command in between has seen it end, so the
    # command is not marked interrupted after the fact.
    running = RunningCommands()
    with subprocess.Popen(SLEEP) as process:
        hold = running.holding(process, group=False)
        hold.__enter__()
        real_waitid = os.waitid

        def waitid_then_let_go(*args: Any) -> Any:
            hold.__exit__(None, None, None)
            return real_waitid(*args)

        with mock.patch.object(os, "waitid", waitid_then_let_go):
            assert running.interrupt() == 0

        assert not running.interrupted(process)
        assert len(running) == 0
        process.kill()


def test_an_interrupt_of_the_runner_itself_does_not_leave_the_child() -> None:
    class Unplugged(BaseException):
        pass

    running = RunningCommands()
    children: list[subprocess.Popen[Any]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args: Any, **kwargs: Any) -> Any:
        children.append(process := real_popen(*args, **kwargs))
        return process

    with (
        mock.patch.object(subprocess, "Popen", side_effect=recording_popen),
        mock.patch.object(real_popen, "communicate", side_effect=Unplugged()),
        pytest.raises(Unplugged),
    ):
        adopting(running, lambda: run_command(SLEEP, Path.cwd(), 30))

    (child,) = children
    child.wait(PROMPT)
    assert child.returncode < 0
    assert len(running) == 0


def test_a_timed_out_command_is_killed_and_reported() -> None:
    running = RunningCommands()

    with pytest.raises(CommandError, match=r"command timed out after 0\.2s"):
        adopting(running, lambda: run_command(SLEEP, Path.cwd(), 0.2))

    assert len(running) == 0


def test_a_missing_binary_is_reported() -> None:
    with pytest.raises(CommandError, match="command not found: dashpot-no-such"):
        run_command(["dashpot-no-such-binary"], Path.cwd(), 1)


def test_a_missing_working_directory_is_not_a_missing_binary(tmp_path: Path) -> None:
    gone = tmp_path / "removed-worktree"

    with pytest.raises(CommandError) as caught:
        run_command([sys.executable, "-c", "pass"], gone, 1)

    assert str(caught.value) == f"working directory does not exist: {gone}"
    assert caught.value.code == "command-directory-missing"


def test_a_missing_binary_has_its_own_code() -> None:
    with pytest.raises(CommandError) as caught:
        run_command(["dashpot-no-such-binary"], Path.cwd(), 1)

    assert caught.value.code == "command-not-found"


def test_output_that_is_not_utf8_is_replaced_not_raised() -> None:
    # A ref or path Git stores in a legacy encoding is one value among many:
    # it reads as the replacement character, and every other byte as written,
    # carriage returns included.
    script = (
        "import sys; "
        "sys.stdout.buffer.write(b'refs/heads/caf\\xe9\\0a\\rb\\n'); "
        "sys.stderr.buffer.write(b'\\xff')"
    )

    result = run_command([sys.executable, "-c", script], Path.cwd(), 10)

    assert result.returncode == 0
    assert result.stdout == "refs/heads/caf�\0a\rb\n"
    assert result.stderr == "�"


# --- Stopping a timed-out command --------------------------------------------

# A helper the command starts, as Git starts an SSH transport or a hook. It
# records its pid once it is ready, and on a termination request records that
# it was asked, then exits — unless it, or both, are told to ignore it.
HELPER = """
import os, pathlib, signal, sys, time
asked, ready, ignore = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
def stop(*_):
    asked.write_text("terminated")
    sys.exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if ignore != "honour" else stop)
staged = ready.with_suffix(".tmp")
staged.write_text(str(os.getpid()))
staged.rename(ready)
time.sleep(30)
"""

# The command itself: starts the helper, then outlasts any test timeout,
# ignoring a termination request only when both are told to. When both honour
# it and the command leads its own group, the request reached the helper too,
# and the command waits for the helper before stopping. Dashpot kills what is
# left of the group once the leader exits, which would otherwise race the
# helper's record of the request.
COMMAND = """
import os, signal, subprocess, sys, time
helper, asked, ready, ignore = sys.argv[1:5]
def stop(*_):
    os.wait()
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.raise_signal(signal.SIGTERM)
if ignore == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
elif ignore == "honour" and os.getpgrp() == os.getpid():
    signal.signal(signal.SIGTERM, stop)
child = subprocess.Popen([sys.executable, "-c", helper, asked, ready, ignore])
time.sleep(30)
"""


def gone(pid: int) -> bool:
    """Whether ``pid`` has ended: no such process, or one only left to be reaped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    try:
        return stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return False


def timing_out_once_ready(ready: Path) -> Callable[..., Any]:
    """A ``communicate`` that times out only once the helper is running.

    The timeout is then certain to find the whole process group in place,
    however slowly the interpreters start.
    """

    def communicate(
        process: subprocess.Popen[bytes],
        input: Any = None,
        timeout: float | None = None,
    ) -> Any:
        wait_for(ready.exists, timeout=30)
        raise subprocess.TimeoutExpired(process.args, timeout or 0)

    return communicate


def run_timing_out(
    tmp_path: Path,
    *,
    non_interactive: bool,
    ignore: Literal["honour", "ignore", "helper-ignores"] = "honour",
) -> tuple[subprocess.Popen[Any], int, Path]:
    """Run the command until it times out; its process, its helper's pid, the marker."""
    asked, ready = tmp_path / "asked", tmp_path / "ready"
    args = [
        sys.executable,
        "-c",
        COMMAND,
        HELPER,
        str(asked),
        str(ready),
        ignore,
    ]
    started: list[subprocess.Popen[Any]] = []
    real_popen = subprocess.Popen

    def recording_popen(*popen_args: Any, **kwargs: Any) -> Any:
        started.append(process := real_popen(*popen_args, **kwargs))
        return process

    with (
        mock.patch.object(subprocess, "Popen", side_effect=recording_popen),
        mock.patch.object(real_popen, "communicate", timing_out_once_ready(ready)),
        pytest.raises(CommandError, match=r"command timed out after 0\.5s") as caught,
    ):
        run_command(args, tmp_path, 0.5, non_interactive=non_interactive)

    assert caught.value.code == "command-timed-out"
    (process,) = started
    return process, int(ready.read_text()), asked


def test_a_timed_out_command_is_asked_to_stop_with_every_helper_it_started(
    tmp_path: Path,
) -> None:
    process, helper, asked = run_timing_out(tmp_path, non_interactive=True)

    # The command and its helper share the command's own process group, and
    # both were sent the termination request, so Git can remove its lock
    # files rather than being killed outright.
    assert process.returncode == -signal.SIGTERM
    wait_for(lambda: gone(helper))
    assert asked.read_text() == "terminated"


def test_a_command_that_will_not_stop_is_killed_after_the_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commands, "STOP_GRACE", 0.2)

    process, helper, asked = run_timing_out(
        tmp_path, non_interactive=True, ignore="ignore"
    )

    assert process.returncode == -signal.SIGKILL
    wait_for(lambda: gone(helper))
    assert not asked.exists()


def test_a_helper_that_outlives_its_command_is_killed_after_the_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A hook that traps the termination request while Git itself stops.
    monkeypatch.setattr(commands, "STOP_GRACE", 0.2)

    process, helper, asked = run_timing_out(
        tmp_path, non_interactive=True, ignore="helper-ignores"
    )

    assert process.returncode == -signal.SIGTERM
    wait_for(lambda: gone(helper))
    assert not asked.exists()


def test_a_timed_out_command_sharing_dashpot_s_group_is_stopped_alone(
    tmp_path: Path,
) -> None:
    # Without its own session the command is in Dashpot's process group,
    # which must never be signalled; its helper is left to end on its own.
    process, helper, _asked = run_timing_out(tmp_path, non_interactive=False)

    assert process.returncode == -signal.SIGTERM
    assert not gone(helper)
    os.kill(helper, signal.SIGKILL)


def test_a_command_already_reaped_is_never_signalled() -> None:
    # Once reaped, a command's pid may name another process, so stopping a
    # command that has already ended sends nothing at all.
    class Unplugged(BaseException):
        pass

    def reaped_then_unplugged(
        process: subprocess.Popen[bytes],
        input: Any = None,
        timeout: float | None = None,
    ) -> Any:
        process.wait(PROMPT)
        raise Unplugged

    with (
        mock.patch.object(subprocess.Popen, "communicate", reaped_then_unplugged),
        mock.patch.object(os, "killpg") as killpg,
        pytest.raises(Unplugged),
    ):
        run_command(
            [sys.executable, "-c", "pass"], Path.cwd(), 10, non_interactive=True
        )

    killpg.assert_not_called()


def test_a_command_sharing_dashpot_s_group_that_will_not_stop_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commands, "STOP_GRACE", 0.2)

    process, helper, _asked = run_timing_out(
        tmp_path, non_interactive=False, ignore="ignore"
    )

    # The kill, like the request before it, reaches the command alone.
    assert process.returncode == -signal.SIGKILL
    assert not gone(helper)
    os.kill(helper, signal.SIGKILL)


def test_a_group_left_only_its_stopped_leader_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # macOS refuses a signal to a group of zombies as not permitted, where
    # Linux accepts it; either way the stop completes.
    real_killpg = os.killpg

    def refusing_the_kill(pgid: int, signum: int) -> None:
        if signum == signal.SIGKILL:
            raise PermissionError(1, "Operation not permitted")
        real_killpg(pgid, signum)

    monkeypatch.setattr(os, "killpg", refusing_the_kill)

    process, helper, asked = run_timing_out(tmp_path, non_interactive=True)

    assert process.returncode == -signal.SIGTERM
    wait_for(lambda: gone(helper))
    assert asked.read_text() == "terminated"


# --- Interrupting a command in its own session --------------------------------

# A command that starts the helper, waits until it is running, and exits,
# leaving the helper holding its output open.
LEAVES_HELPER = """
import pathlib, subprocess, sys, time
helper, asked, ready = sys.argv[1:4]
subprocess.Popen([sys.executable, "-c", helper, asked, ready, "honour"])
while not pathlib.Path(ready).exists():
    time.sleep(0.01)
"""


def test_an_interrupted_command_is_asked_to_stop_with_every_helper_it_started(
    tmp_path: Path,
) -> None:
    # A Cleanup preview's Git runs in its own session, so the dashboard's
    # exit asks the helpers it started to stop too, not Git alone.
    asked, ready = tmp_path / "asked", tmp_path / "ready"
    args = [sys.executable, "-c", COMMAND, HELPER, str(asked), str(ready), "honour"]
    started: list[subprocess.Popen[Any]] = []
    running = RunningCommands()
    with mock.patch.object(subprocess, "Popen", side_effect=popen_recording(started)):
        thread, outcomes = start_command(args, running, non_interactive=True)
        wait_for(lambda: len(running) == 1)
        wait_for(ready.exists, timeout=30)

        assert running.interrupt() == 1

        thread.join(PROMPT)
    assert not thread.is_alive()
    (outcome,) = outcomes
    assert isinstance(outcome, CommandError)
    assert outcome.code == "command-interrupted"
    (process,) = started
    assert process.returncode == -signal.SIGTERM
    # The helper holds the command's output open, so the runner returned
    # only once it had exited, and only a termination request, which it
    # records before exiting, was ever sent: no kill can overtake it.
    assert asked.read_text() == "terminated"
    helper = int(ready.read_text())
    wait_for(lambda: gone(helper))


def test_a_helper_holding_an_exited_command_s_output_is_asked_to_stop(
    tmp_path: Path,
) -> None:
    # The command has answered, but its runner's thread waits on the output
    # the helper holds; the group is asked to stop, and the command's own
    # answer stands rather than being reported interrupted.
    asked, ready = tmp_path / "asked", tmp_path / "ready"
    args = [sys.executable, "-c", LEAVES_HELPER, HELPER, str(asked), str(ready)]
    started: list[subprocess.Popen[Any]] = []
    running = RunningCommands()
    with mock.patch.object(subprocess, "Popen", side_effect=popen_recording(started)):
        thread, outcomes = start_command(args, running, non_interactive=True)
        wait_for(lambda: len(running) == 1)
        (process,) = started
        wait_for(lambda: exited_unreaped(process), timeout=30)

        assert running.interrupt() == 0

        thread.join(PROMPT)
    assert not thread.is_alive()
    (outcome,) = outcomes
    assert isinstance(outcome, CommandResult)
    assert outcome.returncode == 0
    assert asked.read_text() == "terminated"
    helper = int(ready.read_text())
    wait_for(lambda: gone(helper))


@pytest.mark.parametrize("group", [False, True])
def test_a_command_that_exited_unreaped_is_not_reported_interrupted(
    group: bool,
) -> None:
    # Its runner has yet to reap it, so its pid still names it. Only in its
    # own session is anything signalled, the group a helper may linger in.
    running = RunningCommands()
    with (
        subprocess.Popen(
            [sys.executable, "-c", "pass"], start_new_session=group
        ) as process,
        running.holding(process, group=group),
    ):
        wait_for(lambda: exited_unreaped(process))

        with (
            mock.patch.object(os, "killpg") as killpg,
            mock.patch.object(process, "send_signal") as send_signal,
        ):
            assert running.interrupt() == 0

        send_signal.assert_not_called()
        if group:
            killpg.assert_called_once_with(process.pid, signal.SIGTERM)
        else:
            killpg.assert_not_called()
        assert not running.interrupted(process)
        # The interruption left the reaping to the runner.
        assert process.returncode is None
    assert process.returncode == 0


def test_a_command_reaped_behind_its_runner_is_not_signalled() -> None:
    # Reaped by something other than its ``Popen``, a command's pid may
    # already name another process, so nothing is signalled.
    running = RunningCommands()
    with (
        subprocess.Popen(
            [sys.executable, "-c", "pass"], start_new_session=True
        ) as process,
        running.holding(process, group=True),
    ):
        os.waitpid(process.pid, 0)

        with mock.patch.object(os, "killpg") as killpg:
            assert running.interrupt() == 0

        killpg.assert_not_called()
        assert not running.interrupted(process)
