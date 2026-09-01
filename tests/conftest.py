"""Shared pytest fixtures over the factories in ``factories.py``."""

from __future__ import annotations

from pathlib import Path

import pytest

from factories import init_repository


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    """An empty Git repository at ``tmp_path / "repo"``."""
    return init_repository(tmp_path / "repo")
