"""The command runner: one bounded child per command, interruptible at shutdown."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from contextvars import copy_context
from pathlib import Path
from threading import Thread
from typing import Any
from unittest import mock

import pytest

from dashpot.core.commands import (
    CommandError,
    CommandResult,
    RunningCommands,
    adopted_commands,
    non_interactive_runner,
    run_command,
)

# Long enough that only an interruption can end it inside the test.
SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]
# Long enough to outlast an interruption, short enough to wait out.
BRIEF = [sys.executable, "-c", "import time; time.sleep(0.3); print('done')"]
PROMPT = 5.0


def start_command(
    args: list[str], running: RunningCommands, *, interruptible: bool = True
) -> tuple[Thread, list[CommandResult | CommandError]]:
    """Run ``args`` on a thread that adopted ``running``, keeping its outcome."""
    outcomes: list[CommandResult | CommandError] = []

    def run() -> None:
        running.adopt()
        try:
            outcomes.append(
                run_command(args, Path.cwd(), 30, interruptible=interruptible)
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

    assert running.interrupt() == 1

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


def test_a_command_registering_during_the_interruption_is_stopped() -> None:
    # The window between the closed check and the registration: a process
    # already started is signalled as it registers rather than slipping past.
    running = RunningCommands()
    real_popen = subprocess.Popen

    def popen_then_interrupt(*args: Any, **kwargs: Any) -> Any:
        process = real_popen(*args, **kwargs)
        assert running.interrupt() == 0
        return process

    with (
        mock.patch.object(subprocess, "Popen", side_effect=popen_then_interrupt),
        pytest.raises(CommandError, match="interrupted at shutdown"),
    ):
        adopting(running, lambda: run_command(SLEEP, Path.cwd(), 30))

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
    finishing = non_interactive_runner(interruptible=False)

    result = adopting(running, lambda: finishing(BRIEF, Path.cwd(), 10))

    assert result.stdout == "done\n"
    with pytest.raises(CommandError, match="interrupted at shutdown"):
        adopting(running, lambda: non_interactive_runner()(BRIEF, Path.cwd(), 10))


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
        subprocess.Popen([sys.executable, "-c", "pass"], text=True) as process,
        running.holding(process),
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
    with subprocess.Popen(SLEEP, text=True) as process:
        hold = running.holding(process)
        hold.__enter__()
        real_poll = process.poll

        def poll_then_let_go() -> int | None:
            hold.__exit__(None, None, None)
            return real_poll()

        with mock.patch.object(process, "poll", poll_then_let_go):
            assert running.interrupt() == 0

        assert not running.interrupted(process)
        assert len(running) == 0
        process.kill()


def test_an_interrupt_of_the_runner_itself_does_not_leave_the_child() -> None:
    class Unplugged(BaseException):
        pass

    running = RunningCommands()
    children: list[subprocess.Popen[str]] = []
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
