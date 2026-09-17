"""Locate and identify Worktrees in Git topology records."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..repository import (
    same_path,
)

INITIALIZING_LOCK = "initializing"


def registered_at(records: list[dict[str, str]], path: Path) -> dict[str, str] | None:
    """Find the topology record registered at a Worktree path."""
    for record in records:
        raw = record.get("worktree")
        if raw and same_path(Path(raw), path):
            return record
    return None


def short_branch(record: Mapping[str, str]) -> str | None:
    """Read the short Branch name attached to a Worktree record."""
    branch = record.get("branch")
    if not branch:
        return None
    return branch.removeprefix("refs/heads/")
