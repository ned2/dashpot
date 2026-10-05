"""Run one external command to completion through a replaceable runner.

Every command is timed as a ``command`` span of the Event Log in reach,
named by its program and subcommand and never its arguments. The span fails
only when the command could not be run; a non-zero exit is an answer the
caller reads, unless the caller says otherwise with
:func:`nonzero_exit_fails`. Output is read as UTF-8, and a byte that is not
UTF-8 is replaced rather than failing the command.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal

from .errors import DashpotError
from .event_log import Span, recorded_span
from .runtime_events import CommandAttributes, span_attributes

# Why a command could not run, as its span records it.
CommandFailure = Literal[
    "command-not-found",
    "command-directory-missing",
    "command-timed-out",
    "command-interrupted",
]

# How long a command told to stop has to stop on its own — Git removing its
# lock files and temporary packs — before whatever is left of it is killed.
STOP_GRACE = 2.0


class CommandError(DashpotError):
    """A command that could not run at all.

    Its binary or its working directory is missing, it timed out, or it was
    interrupted.

    ``code`` names which, when the runner knows it, so a Runtime Event can
    record the failure without its message.
    """

    def __init__(self, message: str, *, code: CommandFailure | None = None) -> None:
        super().__init__(message)
        self.code: CommandFailure | None = code


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
    :class:`CommandError`, never a result. A command in its own session is
    interrupted as its whole process group, as a timed-out one is stopped,
    so a helper it started stops with it. An observation that runs several
    commands in turn would start its next one as soon as the current one
    stopped, so an interruption also closes the registry for good: every
    later command on an adopted thread is refused before it starts. The
    dashboard owns one registry and its pools adopt it, so a command run
    on any other thread — a one-shot ``dashpot`` command, a test — is
    never registered.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Each running command, and whether it leads a process group of
        # its own, which an interruption then signals as a whole.
        self._running: dict[subprocess.Popen[bytes], bool] = {}
        self._interrupted: set[subprocess.Popen[bytes]] = set()
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
    def holding(
        self, process: subprocess.Popen[bytes], *, group: bool
    ) -> Iterator[None]:
        """Hold ``process`` as running for the block, whatever ends it.

        ``group`` says the command runs in its own session, so it leads a
        process group of its own that an interruption signals whole. A
        process that registers after the registry closed — started between
        its caller's check and the interruption — is stopped here, so no
        command slips past an interruption unsignalled.
        """
        with self._lock:
            self._running[process] = group
            late = self._closed
            if late:
                self._interrupted.add(process)
        if late:
            _signal(process, signal.SIGTERM, group=group)
        try:
            yield
        finally:
            with self._lock:
                self._running.pop(process, None)
                self._interrupted.discard(process)

    def interrupted(self, process: subprocess.Popen[bytes]) -> bool:
        """Whether ``process`` was told to stop by :meth:`interrupt`."""
        with self._lock:
            return process in self._interrupted

    def interrupt(self) -> int:
        """Close the registry and tell every running command to stop, without waiting.

        The signal is a termination request rather than a kill so Git can
        remove its lock files on the way out. It goes through the path a
        timeout's stop takes: a command in its own session is signalled as
        its whole process group, so the helpers it started — an SSH
        transport, ``index-pack``, a hook — are asked to stop too, while a
        command sharing Dashpot's group is signalled alone. The count is of
        the commands interrupted. One that exited on its own in the meantime
        has answered, and is neither counted nor reported interrupted; but
        in its own session a helper it started may still hold its output
        open, and with it the runner's thread, so its group is still asked
        to stop.
        """
        with self._lock:
            self._closed = True
            processes = list(self._running.items())
        interrupted = 0
        for process, group in processes:
            # Read without reaping, which is left to the command's runner. A
            # reap landing between this read and the signal is a window as
            # narrow as ``Popen.send_signal``'s own.
            state = _exit_state(process)
            if state == "reaped" or (state == "exited" and not group):
                continue
            with self._lock:
                # Let go by its runner since the snapshot: ended, not stopped.
                if process not in self._running:
                    continue
                if state == "running":
                    self._interrupted.add(process)
            _signal(process, signal.SIGTERM, group=group)
            if state == "running":
                interrupted += 1
        return interrupted


# The registry a thread's interruptible commands belong to, set by the pool
# that started the thread. A context variable rather than a thread-local so a
# thread that fans out can copy it into the threads it starts, which are as
# much the dashboard's as their parent; no thread fans out today.
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


# Git commands whose first word names a group and whose second the subcommand.
_GIT_GROUPS = frozenset({"worktree", "remote", "stash", "submodule"})
_WORD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_GRAPHQL_OPERATION = re.compile(r"^\s*(?:query|mutation)\s+([A-Za-z_][A-Za-z0-9_]*)")

# The error class a non-zero exit fails a command's span with, while the
# calling code reads one as a failure rather than an answer.
_nonzero_exit_failure: ContextVar[tuple[str, frozenset[int]] | None] = ContextVar(
    "dashpot_nonzero_exit_failure", default=None
)


@contextmanager
def nonzero_exit_fails(
    error: type[Exception], *, answers: Iterable[int] = ()
) -> Iterator[None]:
    """Fail the span of a command run in the block that exits non-zero, by ``error``.

    For a caller that treats a non-zero exit as a failure rather than an
    answer — ``Git.text`` raising ``GitError`` — so the command's span says
    so, by the error's class and never its message. ``answers`` are the
    non-zero exits the caller still reads as answers, such as
    ``merge-tree``'s 1 for a conflict.
    """
    token = _nonzero_exit_failure.set((error.__name__, frozenset(answers)))
    try:
        yield
    finally:
        _nonzero_exit_failure.reset(token)


def command_words(args: Sequence[str]) -> tuple[str, str | None]:
    """The program and subcommand a command is recorded by, never its arguments.

    Git and tmux name their subcommand first (``worktree add`` for Git's
    groups); ``gh api graphql`` adds the operation its query names. Any other
    program — ``ps``, a configured launcher — is recorded by its name alone,
    since what follows it is arguments.
    """
    program = PurePath(args[0]).name if args else ""
    rest = list(args[1:])
    words: list[str] = []
    if program in ("git", "tmux", "gh") and rest and _WORD.match(rest[0]):
        words.append(rest[0])
        if program == "git" and rest[0] in _GIT_GROUPS and len(rest) > 1:
            if _WORD.match(rest[1]):
                words.append(rest[1])
        elif program == "gh" and rest[:2] == ["api", "graphql"]:
            words.append("graphql")
            operation = graphql_operation(rest)
            if operation is not None:
                words.append(operation)
    return program, " ".join(words) or None


def graphql_operation(args: Sequence[str]) -> str | None:
    """The operation name the ``query=`` argument of a ``gh api graphql`` declares."""
    for arg in args:
        if arg.startswith("query="):
            return operation_name(arg.removeprefix("query="))
    return None


def operation_name(query: str) -> str | None:
    """The name a GraphQL document gives its operation, if it names one."""
    found = _GRAPHQL_OPERATION.match(query)
    return None if found is None else str(found.group(1))


@dataclass(frozen=True, slots=True)
class CommandRecord:
    """The span of one command as it runs, for its runner to say how it ended."""

    span: Span | None
    program: str
    subcommand: str | None

    def exited(self, returncode: int) -> None:
        """Record the exit status; a non-zero one fails the span only where the caller said."""
        if self.span is None:
            return
        attributes = span_attributes(
            CommandAttributes,
            program=self.program,
            subcommand=self.subcommand,
            exit_code=returncode,
        )
        if attributes is not None:
            self.span.set_attributes(attributes)
        failure = _nonzero_exit_failure.get()
        if returncode != 0 and failure is not None:
            error, answers = failure
            if returncode not in answers:
                self.span.fail(error)

    def could_not_run(self, error: BaseException) -> None:
        """Fail the span: the command could not start, timed out, or was interrupted.

        A runner that catches the failure itself says so here; one that
        lets it leave the block needs not.
        """
        if self.span is None:
            return
        if isinstance(error, FileNotFoundError):
            self.span.fail("command-not-found")
        elif isinstance(error, subprocess.TimeoutExpired):
            self.span.fail("command-timed-out")
        else:
            self.span.fail(error)


@contextmanager
def recording_command(args: Sequence[str]) -> Iterator[CommandRecord]:
    """Time one command as a ``command`` span, written at ``full``.

    An exception leaving the block fails the span by its code, errno or
    class, so a failure is recorded, like every Runtime Event, without its
    message.
    """
    program, subcommand = command_words(args)
    attributes = span_attributes(
        CommandAttributes, program=program, subcommand=subcommand
    )
    with recorded_span("command", attributes=attributes) as span:
        record = CommandRecord(span, program, subcommand)
        try:
            yield record
        except BaseException as exc:
            if span is not None and not span.failed:
                span.fail(exc)
            raise


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
    dashboard's exit can ask it to stop; a mutation opts out and runs to
    completion. A command that outlives ``timeout`` is stopped — asked
    first, then killed. Either way a command in its own session is
    signalled with every helper it started.
    """
    with recording_command(args) as record:
        result = _run_command(
            args,
            cwd,
            timeout,
            environment=environment,
            non_interactive=non_interactive,
            interruptible=interruptible,
        )
        record.exited(result.returncode)
    return result


def _run_command(
    args: Sequence[str],
    cwd: Path,
    timeout: float,
    *,
    environment: Mapping[str, str] | None,
    non_interactive: bool,
    interruptible: bool,
) -> CommandResult:
    registry = adopted_commands() if interruptible else None
    interrupted = f"command interrupted at shutdown: {args[0]}"
    if registry is not None and registry.closed:
        raise CommandError(interrupted, code="command-interrupted")
    try:
        process = subprocess.Popen(
            list(args),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **environment} if environment else None,
            stdin=subprocess.DEVNULL if non_interactive else None,
            start_new_session=non_interactive,
        )
    except FileNotFoundError as exc:
        # The child names what it could not find: the working directory when
        # its ``chdir`` failed, the program when its ``exec`` did.
        if exc.filename in (cwd, os.fspath(cwd)):
            raise CommandError(
                f"working directory does not exist: {cwd}",
                code="command-directory-missing",
            ) from exc
        raise CommandError(
            f"command not found: {args[0]}", code="command-not-found"
        ) from exc
    held = (
        registry.holding(process, group=non_interactive)
        if registry is not None
        else nullcontext()
    )
    with process, held:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _stop(process, group=non_interactive)
            raise CommandError(
                f"command timed out after {timeout:g}s: {args[0]}",
                code="command-timed-out",
            ) from exc
        except BaseException:
            # As ``subprocess.run`` does: a child in its own session never
            # saw the terminal's interrupt, so it is not left to finish.
            _stop(process, group=non_interactive)
            raise
        if registry is not None and registry.interrupted(process):
            raise CommandError(interrupted, code="command-interrupted")
    return CommandResult(
        list(args), process.returncode, _decoded(stdout), _decoded(stderr)
    )


def _decoded(output: bytes) -> str:
    """Read a command's output as UTF-8, replacing what is not.

    Git writes ref names and paths as the bytes it stores, which need not be
    UTF-8; a strict decode would fail the whole command over one name. The
    replacement character keeps every other value intact. A replaced name
    all but never resolves, so a later command given it fails rather than
    acting on something else: a Cleanup preview, for one, blocks such a
    Branch because its integration cannot be read.
    """
    return output.decode("utf-8", errors="replace")


def _stop(process: subprocess.Popen[bytes], *, group: bool) -> None:
    """Stop a command that is not to finish: ask it to, then kill what is left.

    The termination request comes first so Git removes its lock files on the
    way out; what is left is killed once the command has stopped, or after
    :data:`STOP_GRACE` if it has not. A command in its own session
    (``group``) leads its own process group, and the whole group is
    signalled, so a helper it started — an SSH transport, ``index-pack``, a
    hook — stops with it rather than running on orphaned, even one that
    outlives a leader which stopped when asked.
    """
    _signal(process, signal.SIGTERM, group=group)
    if group:
        # The leader is left unreaped through the grace, so its pid, and
        # with it the group's id, still names this group when it is killed.
        _await_exit_unreaped(process, STOP_GRACE)
        _signal(process, signal.SIGKILL, group=True)
        process.wait()
        return
    try:
        process.wait(timeout=STOP_GRACE)
    except subprocess.TimeoutExpired:
        _signal(process, signal.SIGKILL, group=False)
        process.wait()


def _await_exit_unreaped(process: subprocess.Popen[bytes], grace: float) -> None:
    """Wait up to ``grace`` for ``process`` to exit, without reaping it."""
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if _exit_state(process) != "running":
            return
        time.sleep(0.01)


def _exit_state(
    process: subprocess.Popen[bytes],
) -> Literal["running", "exited", "reaped"]:
    """How far ``process`` has ended: running, exited unreaped, or reaped.

    It is read without reaping. A reaped command's pid, and with it its
    group's id, may already name another process, so it is never
    signalled; an exited one that is not yet reaped still holds both.
    """
    if process.returncode is not None:
        return "reaped"
    try:
        exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        # Reaped behind its ``Popen``, which has not recorded the exit.
        return "reaped"
    return "running" if exited is None else "exited"


def _signal(
    process: subprocess.Popen[bytes], signum: signal.Signals, *, group: bool
) -> None:
    """Send ``signum`` to the command, or to its process group with ``group``."""
    # Once reaped, the command's pid, and with it its group's id, may already
    # name another process; an unreaped one holds both.
    if process.returncode is not None:
        return
    if not group:
        process.send_signal(signum)
        return
    # A group left with only its unreaped leader has nothing to signal: Linux
    # accepts the signal for the zombie, macOS refuses it as not permitted.
    # A group already gone answers that it is.
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signum)
