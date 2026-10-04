"""The host readers of process working directories, and the inside-a-path query.

The suite's ``no_host_processes`` fixture replaces the host scan a Cleanup
reaches by default. These tests call the readers themselves, by the names
imported here, which that replacement never touches (ADR 0104).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from dashpot.sessions import working_directories
from dashpot.sessions.working_directories import (
    ProcessDirectory,
    ProcessesInside,
    ProcessScan,
    WorkingDirectories,
    host_working_directories,
    lsof_working_directories,
    parse_lsof_fields,
    proc_working_directories,
    processes_inside,
)

RUN = "dashpot.sessions.working_directories.subprocess.run"


def fake_proc(root: Path, pid: int, cwd: str, stat: str | None) -> None:
    """One ``/proc/<pid>`` entry: its ``cwd`` link and, when given, its ``stat``."""
    entry = root / str(pid)
    entry.mkdir(parents=True)
    os.symlink(cwd, entry / "cwd")
    if stat is not None:
        (entry / "stat").write_text(stat)


# --- /proc ------------------------------------------------------------------


def test_the_proc_reader_reads_each_process_cwd_and_parent(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    fake_proc(proc, 30, "/w/feat/src", "30 (tmux: server) S 1 30 30 0")
    # A command may itself hold parentheses; the fields follow the last one.
    fake_proc(proc, 12, "/w/feat", "12 (a) b)) S 30 12 12 0")
    (proc / "self").mkdir()
    (proc / "stat").write_text("cpu 0\n")

    observed = proc_working_directories(proc)

    assert observed == WorkingDirectories(
        (
            ProcessDirectory(12, 30, "a) b)", Path("/w/feat")),
            ProcessDirectory(30, 1, "tmux: server", Path("/w/feat/src")),
        )
    )


def test_the_proc_reader_skips_what_it_cannot_read_or_what_was_removed(
    tmp_path: Path,
) -> None:
    proc = tmp_path / "proc"
    # Another user's process: no readable link, as Linux denies it.
    (proc / "40").mkdir(parents=True)
    # A process that exited between its link and its stat.
    fake_proc(proc, 41, "/w/feat", None)
    # A process whose working directory was removed under it.
    fake_proc(proc, 42, "/w/feat/old (deleted)", "42 (bash) S 1 42 42 0")
    # A stat line too short to name a parent.
    fake_proc(proc, 43, "/w/feat", "43 (bash)")
    fake_proc(proc, 44, "/w/feat", "44 (bash) S x")
    fake_proc(proc, 45, "/w/feat", "45 bash S 1")

    assert proc_working_directories(proc) == WorkingDirectories()


def test_an_unreadable_proc_tree_is_reported_incomplete(tmp_path: Path) -> None:
    assert proc_working_directories(tmp_path / "absent") == WorkingDirectories(
        (), "proc-unreadable"
    )


# --- lsof -------------------------------------------------------------------

LSOF_OUTPUT = """\
p30
R1
ctmux: server
fcwd
n/w/feat/src
p31
R30
cbash
frtd
n/
fcwd
n/w/feat
p32
R30
cnode
fcwd
n/w/feat/old (deleted)
pnot-a-pid
fcwd
n/w/elsewhere
"""


def test_lsof_fields_give_each_process_its_cwd_and_parent() -> None:
    assert parse_lsof_fields(LSOF_OUTPUT) == (
        ProcessDirectory(30, 1, "tmux: server", Path("/w/feat/src")),
        ProcessDirectory(31, 30, "bash", Path("/w/feat")),
    )


def test_lsof_is_asked_for_the_cwd_descriptor_alone() -> None:
    completed = subprocess.CompletedProcess([], 0, LSOF_OUTPUT, "")
    with mock.patch(RUN, return_value=completed) as run:
        observed = lsof_working_directories()

    assert run.call_args.args[0] == ["lsof", "-w", "-d", "cwd", "-F", "pRcfn"]
    assert observed == WorkingDirectories(parse_lsof_fields(LSOF_OUTPUT))


def test_lsof_listing_some_processes_before_an_error_still_counts() -> None:
    # lsof exits 1 when a process it listed vanished mid-scan.
    completed = subprocess.CompletedProcess([], 1, LSOF_OUTPUT, "")
    with mock.patch(RUN, return_value=completed):
        assert lsof_working_directories().incomplete is None


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (OSError("no lsof"), "lsof-unavailable"),
        (subprocess.TimeoutExpired(["lsof"], 5), "lsof-timeout"),
        (subprocess.CompletedProcess([], 1, "", "lsof: boom"), "lsof-failed"),
    ],
)
def test_a_host_lsof_cannot_answer_for_is_reported_incomplete(
    outcome: BaseException | subprocess.CompletedProcess[str], reason: str
) -> None:
    # A mock raises an exception it finds in its side effects, else returns it.
    with mock.patch(RUN, side_effect=[outcome]):
        assert lsof_working_directories() == WorkingDirectories((), reason)


# --- choosing the reader ----------------------------------------------------


def test_a_host_without_proc_is_read_with_lsof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As on macOS, which has no /proc.
    monkeypatch.setattr(working_directories, "PROC_ROOT", tmp_path / "absent")
    monkeypatch.setattr(
        working_directories, "process_namespace_is_isolated", lambda: False
    )
    completed = subprocess.CompletedProcess([], 0, LSOF_OUTPUT, "")
    with mock.patch(RUN, return_value=completed):
        observed = host_working_directories()

    assert observed == WorkingDirectories(parse_lsof_fields(LSOF_OUTPUT))


def test_a_host_with_neither_proc_nor_lsof_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(working_directories, "PROC_ROOT", tmp_path / "absent")
    monkeypatch.setattr(
        working_directories, "process_namespace_is_isolated", lambda: False
    )
    with mock.patch(RUN, side_effect=FileNotFoundError("lsof")):
        assert host_working_directories() == WorkingDirectories((), "lsof-unavailable")


def test_a_scan_inside_a_sandbox_keeps_what_it_saw_and_says_it_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    fake_proc(proc, 7, "/w/feat", "7 (bash) S 1 7 7 0")
    monkeypatch.setattr(working_directories, "PROC_ROOT", proc)
    monkeypatch.setattr(
        working_directories, "process_namespace_is_isolated", lambda: True
    )

    assert host_working_directories() == WorkingDirectories(
        (ProcessDirectory(7, 1, "bash", Path("/w/feat")),), "isolated-namespace"
    )


def test_the_host_reader_finds_a_real_process_in_its_directory(
    tmp_path: Path,
) -> None:
    # /proc on Linux, lsof on macOS: CI runs both.
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
    )
    try:
        observed = host_working_directories()
        inside = processes_inside(tmp_path, host_working_directories)
    finally:
        child.communicate()

    found = [one for one in observed.processes if one.pid == child.pid]
    assert [one.cwd for one in found] == [tmp_path.resolve()]
    assert found[0].parent_pid == os.getpid()
    # The child is this process's own, as Dashpot's probes are, so it is no
    # occupant.
    assert child.pid not in {one.pid for one in inside.processes}


# --- processes inside a path ------------------------------------------------


def scan_of(*processes: ProcessDirectory, incomplete: str | None = None) -> ProcessScan:
    """A scan that sees exactly ``processes``."""
    return lambda: WorkingDirectories(processes, incomplete)


def test_processes_inside_a_directory_include_its_subdirectories_only(
    tmp_path: Path,
) -> None:
    worktree = (tmp_path / "feat").resolve()
    here = ProcessDirectory(101, 1, "bash", worktree)
    below = ProcessDirectory(102, 1, "node", worktree / "web")
    # A sibling whose name only starts with the Worktree's is outside it.
    sibling = ProcessDirectory(103, 1, "bash", tmp_path.resolve() / "feat-2")
    above = ProcessDirectory(104, 1, "bash", tmp_path.resolve())

    found = processes_inside(worktree, scan_of(here, below, sibling, above))

    assert found == ProcessesInside((here, below))


def test_processes_inside_resolve_the_directory_asked_about(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    shell = ProcessDirectory(101, 1, "bash", real.resolve())

    assert processes_inside(tmp_path / "link", scan_of(shell)).processes == (shell,)


def test_dashpot_and_what_it_runs_are_no_occupant_but_its_shell_is(
    tmp_path: Path,
) -> None:
    worktree = tmp_path.resolve()
    own = os.getpid()
    shell = ProcessDirectory(os.getppid(), 1, "bash", worktree)
    dashpot = ProcessDirectory(own, os.getppid(), "dashpot", worktree)
    probe = ProcessDirectory(900001, own, "git", worktree)
    nested = ProcessDirectory(900002, 900001, "git-remote", worktree / "sub")

    found = processes_inside(worktree, scan_of(shell, dashpot, probe, nested))

    assert found.processes == (shell,)


def test_a_parent_chain_that_loops_or_runs_long_ends_the_descent(
    tmp_path: Path,
) -> None:
    worktree = tmp_path.resolve()
    looped = (
        ProcessDirectory(900001, 900002, "a", worktree),
        ProcessDirectory(900002, 900001, "b", worktree),
    )
    # A chain that reaches this process only past the bound is not traced.
    depth = working_directories.MAX_ANCESTRY + 1
    deep = tuple(
        ProcessDirectory(
            910000 + step,
            os.getpid() if step == depth - 1 else 910001 + step,
            "c",
            worktree,
        )
        for step in range(depth)
    )

    assert processes_inside(worktree, scan_of(*looped)).processes == looped
    found = {one.pid for one in processes_inside(worktree, scan_of(*deep)).processes}
    assert deep[0].pid in found
    assert deep[-1].pid not in found


def test_an_incomplete_scan_still_reports_what_it_found(tmp_path: Path) -> None:
    shell = ProcessDirectory(101, 1, "bash", tmp_path.resolve())

    found = processes_inside(tmp_path, scan_of(shell, incomplete="isolated-namespace"))

    assert found == ProcessesInside((shell,), "isolated-namespace")
