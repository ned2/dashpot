"""Run one external command to completion through a replaceable runner."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from .errors import DashpotError


class CommandError(DashpotError):
    """A command that could not run at all: missing binary, timeout, or interruption."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


# A runner answers with the command's result, or raises ``CommandError`` (or
# ``OSError``) when the command could not run at all.
CommandRunner = Callable[[Sequence[str], Path, float], CommandResult]


class RunningCommands:
    """The interruptible commands running on the threads that adopted this registry.

    A pool thread blocked in a command cannot be cancelled, and interpreter
    exit joins every pool thread, so the dashboard's exit would otherwise
    wait for whatever ``git`` or ``gh`` was mid-flight. Interrupting the
    command releases the thread; the command's caller sees a
    :class:`CommandError`, never a result. An observation that runs several
    commands in turn would start its next one as soon as the current one
    stopped, so an interruption also closes the registry for good: every
    later command on an adopted thread is refused before it starts. The
    dashboard owns one registry and its pools adopt it, so a command run
    on any other thread — a one-shot ``dashpot`` command, a test — is
    never registered.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: set[subprocess.Popen[str]] = set()
        self._interrupted: set[subprocess.Popen[str]] = set()
        self._closed = False

    def __len__(self) -> int:
        with self._lock:
            return len(self._running)

    @property
    def closed(self) -> bool:
        """Whether :meth:`interrupt` has run, after which no command starts."""
        with self._lock:
            return self._closed

    def adopt(self) -> None:
        """Register the interruptible commands of the calling thread here."""
        _adopted.set(self)

    def pool(self, *, max_workers: int, thread_name_prefix: str) -> ThreadPoolExecutor:
        """A thread pool whose every thread adopts this registry."""
        return ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
            initializer=self.adopt,
        )

    @contextmanager
    def holding(self, process: subprocess.Popen[str]) -> Iterator[None]:
        """Hold ``process`` as running for the block, whatever ends it.

        A process that registers after the registry closed — started
        between its caller's check and the interruption — is stopped here,
        so no command slips past an interruption unsignalled.
        """
        with self._lock:
            self._running.add(process)
            late = self._closed
            if late:
                self._interrupted.add(process)
        if late:
            process.terminate()
        try:
            yield
        finally:
            with self._lock:
                self._running.discard(process)
                self._interrupted.discard(process)

    def interrupted(self, process: subprocess.Popen[str]) -> bool:
        """Whether ``process`` was told to stop by :meth:`interrupt`."""
        with self._lock:
            return process in self._interrupted

    def interrupt(self) -> int:
        """Close the registry and tell every running command to stop, without waiting.

        The signal is a termination request rather than a kill so Git can
        remove its lock files on the way out. The count is of the commands
        signalled; one that finished on its own in the meantime is not
        counted.
        """
        with self._lock:
            self._closed = True
            processes = list(self._running)
        signalled = 0
        for process in processes:
            if process.poll() is not None:
                continue
            with self._lock:
                # Let go by its runner since the snapshot: ended, not stopped.
                if process not in self._running:
                    continue
                self._interrupted.add(process)
            process.terminate()
            signalled += 1
        return signalled


# The registry a thread's interruptible commands belong to, set by the pool
# that started the thread. A context variable rather than a thread-local so a
# thread that fans out — ``GitHubGateway.graphql_many`` — can copy it into
# the threads it starts, which are as much the dashboard's as their parent.
_adopted: ContextVar[RunningCommands | None] = ContextVar(
    "dashpot_running_commands", default=None
)


def adopted_commands() -> RunningCommands | None:
    """The registry the calling thread's interruptible commands belong to, if any."""
    return _adopted.get()


def start_pool(
    running: RunningCommands | None, *, max_workers: int, thread_name_prefix: str
) -> ThreadPoolExecutor:
    """A thread pool whose threads adopt ``running``, or adopt nothing without one."""
    if running is None:
        return ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=thread_name_prefix
        )
    return running.pool(max_workers=max_workers, thread_name_prefix=thread_name_prefix)


def run_command(
    args: Sequence[str],
    cwd: Path,
    timeout: float,
    *,
    environment: Mapping[str, str] | None = None,
    non_interactive: bool = False,
    interruptible: bool = True,
) -> CommandResult:
    """Run one command to completion with its output captured.

    ``environment`` adds to the inherited environment. A ``non_interactive``
    command gets no stdin and its own session, so neither it nor a helper it
    starts (an SSH passphrase prompt, say) can open the controlling terminal
    and take over the screen; it fails or times out instead. An
    ``interruptible`` command — every observation and query — is held by
    the registry the calling thread adopted, when it adopted one, so the
    dashboard's exit can stop it; a mutation opts out and runs to
    completion.
    """
    registry = adopted_commands() if interruptible else None
    interrupted = f"command interrupted at shutdown: {args[0]}"
    if registry is not None and registry.closed:
        raise CommandError(interrupted)
    try:
        process = subprocess.Popen(
            list(args),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **environment} if environment else None,
            stdin=subprocess.DEVNULL if non_interactive else None,
            start_new_session=non_interactive,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"command not found: {args[0]}") from exc
    held = registry.holding(process) if registry is not None else nullcontext()
    with process, held:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise CommandError(
                f"command timed out after {timeout:g}s: {args[0]}"
            ) from exc
        except BaseException:
            # As ``subprocess.run`` does: a child in its own session never
            # saw the terminal's interrupt, so it is not left to finish.
            process.kill()
            process.wait()
            raise
        if registry is not None and registry.interrupted(process):
            raise CommandError(interrupted)
    return CommandResult(list(args), process.returncode, stdout, stderr)


def non_interactive_runner(
    environment: Mapping[str, str] | None = None,
    *,
    interruptible: bool = True,
) -> CommandRunner:
    """A runner whose every command is non-interactive, with ``environment`` added."""
    return partial(
        run_command,
        environment=environment,
        non_interactive=True,
        interruptible=interruptible,
    )
