"""Shared pytest fixtures over the factories in ``factories.py``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from factories import init_repository


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """Bound automatic local workers while reserving CPU capacity."""
    if config.option.numprocesses != "auto":
        return None
    affinity = getattr(os, "sched_getaffinity", None)
    available = len(affinity(0)) if affinity is not None else os.cpu_count()
    return max(1, min(8, (available or 1) // 2))


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    """An empty Git repository at ``tmp_path / "repo"``."""
    return init_repository(tmp_path / "repo")
