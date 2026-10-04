"""Shared pytest fixtures over the factories in ``factories.py``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dashpot.sessions.working_directories import WorkingDirectories
from factories import init_repository


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """Bound automatic local workers while reserving CPU capacity."""
    if config.option.numprocesses != "auto":
        return None
    return max(1, min(8, (os.process_cpu_count() or 1) // 2))


@pytest.fixture(autouse=True)
def isolated_settings(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep every test from reading the machine-local settings of whoever runs it."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))


@pytest.fixture(autouse=True)
def quiet_event_log(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Record no Runtime Event from any test, in this checkout or the user's state.

    The environment reaches every process a test starts too. An Event Log
    test opts in with a directory of its own; one that sets a level without
    naming a directory still writes only to a temporary directory.
    """
    monkeypatch.setenv("DASHPOT_EVENT_LEVEL", "off")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("xdg-state")))


@pytest.fixture(autouse=True)
def bounded_checkout_search(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep every search for an enclosing checkout inside the suite's temporary tree.

    Whatever holds the host's temporary directory — a stray ``.git`` there
    once made ``/tmp`` a checkout (#359) — a test's directory is outside every
    checkout it did not make, to Git and to Dashpot alike.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path_factory.getbasetemp()))


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    """An empty Git repository at ``tmp_path / "repo"``."""
    return init_repository(tmp_path / "repo")


@pytest.fixture(autouse=True)
def no_host_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read no working directory of this host's processes unless a test passes a scan.

    Every Worktree preview and check scans the host for processes inside the
    Worktree (ADR 0104). Read for real, the scan depends on what else runs:
    inside a sandbox's PID namespace it reports itself incomplete, which
    adds a line to every removable report, and on macOS it runs ``lsof``.
    A test that means to find a process passes its own scan, and the host
    reader's own tests call it directly, which this replacement never reaches.
    """
    monkeypatch.setattr(
        "dashpot.sessions.working_directories.host_working_directories",
        lambda: WorkingDirectories(),
    )
