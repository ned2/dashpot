"""Find the processes on this host whose working directory is inside a directory.

Cleanup asks this at the moment it previews, checks, or re-inspects the
removal of a Worktree, and retains nothing (ADR 0104). It reads ``/proc``
on Linux and ``lsof`` elsewhere, and only ever reads: a process it cannot
read, such as another user's, gives no evidence either way, and a scan that
could not cover every visible process says why rather than read as empty.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.commands import recording_command
from .processes import process_namespace_is_isolated

PROC_ROOT = Path("/proc")
# How many parents a descent check follows before it gives up: deeper than
# any shell, harness, and tool chain Dashpot runs under.
MAX_ANCESTRY = 64
# How long ``lsof`` may take to list every working directory on the host.
LSOF_TIMEOUT = 5.0
# Linux names a working directory that was removed with this suffix.
DELETED_SUFFIX = " (deleted)"

# Why a scan could not cover every process the person can see.
ScanGap = Literal[
    "isolated-namespace",
    "proc-unreadable",
    "lsof-unavailable",
    "lsof-timeout",
    "lsof-failed",
]


@dataclass(frozen=True, slots=True)
class ProcessDirectory:
    """One visible process and the working directory it runs in."""

    pid: int
    parent_pid: int
    command: str
    cwd: Path


@dataclass(frozen=True, slots=True)
class WorkingDirectories:
    """Processes a scan read, and why it could not read them all, if it could not.

    A host scan holds every process it could read; ``processes_inside``
    narrows one to the processes inside a directory, keeping its gap.
    ``incomplete`` is ``None`` when the scan covered every process the
    person can see.
    """

    processes: tuple[ProcessDirectory, ...] = ()
    incomplete: ScanGap | None = None


ProcessScan = Callable[[], WorkingDirectories]


def processes_inside(path: Path, scan: ProcessScan | None = None) -> WorkingDirectories:
    """Every visible process whose working directory is ``path`` or below it.

    The Dashpot process asking, and every process it started, are left out:
    they are this inspection's own probes, never an occupant. Its ancestors
    count, so the shell a person runs Dashpot from inside the directory is
    found. Without ``scan`` the host is read, at call time.
    """
    # Resolved here rather than bound as a default, so the suite can replace
    # the host reader for every caller that passes no scan of its own.
    observed = (scan or host_working_directories)()
    target = path.resolve()
    parents = {process.pid: process.parent_pid for process in observed.processes}
    own = os.getpid()
    inside = tuple(
        process
        for process in observed.processes
        if process.cwd.is_relative_to(target)
        and not _descends_from(process.pid, own, parents)
    )
    return WorkingDirectories(inside, observed.incomplete)


def _descends_from(pid: int, ancestor: int, parents: Mapping[int, int]) -> bool:
    """Whether ``pid`` is ``ancestor`` or a descendant the scan can trace to it."""
    current = pid
    for _ in range(MAX_ANCESTRY):
        if current == ancestor:
            return True
        parent = parents.get(current)
        if parent is None or parent == current or parent <= 0:
            return False
        current = parent
    return False


def host_working_directories() -> WorkingDirectories:
    """Read every visible process's working directory on this host.

    Linux's ``/proc`` is read directly; a host without it, such as macOS, is
    asked through ``lsof``. Inside a sandbox's PID namespace the processes
    outside it cannot be seen, so the scan reports what it saw as incomplete.
    """
    if (PROC_ROOT / "self").is_dir():
        observed = proc_working_directories(PROC_ROOT)
    else:
        observed = lsof_working_directories()
    if observed.incomplete is None and process_namespace_is_isolated():
        return WorkingDirectories(observed.processes, "isolated-namespace")
    return observed


def proc_working_directories(proc: Path) -> WorkingDirectories:
    """Read each process's ``cwd`` link and parent under a ``/proc`` tree.

    A process that exits mid-scan, or whose link the person may not read —
    another user's, or one that made itself undumpable — is skipped.
    """
    try:
        entries = [entry for entry in proc.iterdir() if entry.name.isdigit()]
    except OSError:
        return WorkingDirectories((), "proc-unreadable")
    processes: list[ProcessDirectory] = []
    for entry in entries:
        try:
            cwd = os.readlink(entry / "cwd")
            stat = (entry / "stat").read_text(errors="replace")
        except OSError:
            continue
        if cwd.endswith(DELETED_SUFFIX):
            continue
        parsed = _parse_stat(stat)
        if parsed is None:
            continue
        command, parent_pid = parsed
        processes.append(
            ProcessDirectory(int(entry.name), parent_pid, command, Path(cwd))
        )
    return WorkingDirectories(tuple(sorted(processes, key=lambda one: one.pid)))


def _parse_stat(stat: str) -> tuple[str, int] | None:
    """The command and parent pid of a ``/proc/<pid>/stat`` line.

    The command sits in parentheses and may itself hold spaces and
    parentheses, so the fields after it are found from the last ``)``.
    """
    head, separator, tail = stat.rpartition(")")
    _, opened, command = head.partition("(")
    fields = tail.split()
    if not separator or not opened or len(fields) < 2:
        return None
    try:
        return command, int(fields[1])
    except ValueError:
        return None


def lsof_working_directories() -> WorkingDirectories:
    """Ask ``lsof`` for every visible process's working directory.

    ``-d cwd`` selects only that descriptor, and ``-F`` prints one field a
    line: ``p`` the pid, ``R`` its parent, ``c`` its command, ``f`` the
    descriptor and ``n`` its path. ``-w`` drops the warnings about processes
    the person may not read, which ``lsof`` leaves out.
    """
    args = ["lsof", "-w", "-d", "cwd", "-F", "pRcfn"]
    with recording_command(args) as record:
        try:
            result = subprocess.run(
                args,
                text=True,
                errors="replace",
                capture_output=True,
                timeout=LSOF_TIMEOUT,
                check=False,
            )
        except OSError as exc:
            record.could_not_run(exc)
            return WorkingDirectories((), "lsof-unavailable")
        except subprocess.TimeoutExpired as exc:
            record.could_not_run(exc)
            return WorkingDirectories((), "lsof-timeout")
        record.exited(result.returncode)
    # ``lsof`` also exits 1 when a process it listed vanished or could not
    # be read; only a run that listed nothing at all has failed.
    if result.returncode != 0 and not result.stdout.strip():
        return WorkingDirectories((), "lsof-failed")
    return WorkingDirectories(parse_lsof_fields(result.stdout))


def parse_lsof_fields(output: str) -> tuple[ProcessDirectory, ...]:
    """Read the processes and working directories of ``lsof -F pRcfn`` output."""
    processes: list[ProcessDirectory] = []
    pid: int | None = None
    parent_pid = 0
    command = ""
    descriptor = ""
    for line in output.splitlines():
        field, value = line[:1], line[1:]
        if field == "p":
            pid = int(value) if value.isdigit() else None
            parent_pid, command, descriptor = 0, "", ""
        elif field == "R":
            parent_pid = int(value) if value.isdigit() else 0
        elif field == "c":
            command = value
        elif field == "f":
            descriptor = value
        elif (
            field == "n"
            and pid is not None
            and descriptor == "cwd"
            and not value.endswith(DELETED_SUFFIX)
        ):
            processes.append(ProcessDirectory(pid, parent_pid, command, Path(value)))
    return tuple(processes)
