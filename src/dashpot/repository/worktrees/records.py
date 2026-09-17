"""Locate and identify Worktrees in Git topology records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ...core.worktree_paths import same_path
from ..repository import branch_name

INITIALIZING_LOCK = "initializing"


def registered_at(records: list[dict[str, str]], path: Path) -> dict[str, str] | None:
    """Find the topology record registered at a Worktree path."""
    for record in records:
        raw = record.get("worktree")
        if raw and same_path(Path(raw), path):
            return record
    return None


def checked_out_at(records: Iterable[Mapping[str, str]], refname: str) -> Path | None:
    """Find the Worktree at which a Branch ref is checked out."""
    for record in records:
        if record.get("branch") == refname and record.get("worktree"):
            return Path(record["worktree"]).resolve()
    return None


def short_branch(record: Mapping[str, str]) -> str | None:
    """Read the short Branch name attached to a Worktree record."""
    branch = record.get("branch")
    if not branch:
        return None
    return branch_name(branch)
