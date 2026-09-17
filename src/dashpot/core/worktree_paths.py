"""Locate paths within the Worktree topology of a Git Repository."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .git import Git


def worktree_root(path: Path, git: Git | None = None) -> Path:
    """Return the current Git Worktree root containing a path."""
    adapter = git if git is not None else Git(path)
    return Path(adapter.at(path).text("rev-parse", "--show-toplevel")).resolve()


def repository_worktrees(
    root: Path, *, timeout: float = 5, git: Git | None = None
) -> list[Path]:
    """List every Worktree of the Git Repository one Worktree belongs to.

    Git reports the main working tree first and every linked one after it;
    a bare entry is not a Worktree. Independent clones are not reached
    ([ADR 0003](../../docs/adr/0003-prefer-project-local-dashpot-state.md)).
    """
    return worktree_paths(worktree_records(root, timeout=timeout, git=git))


def worktree_paths(records: Iterable[Mapping[str, str]]) -> list[Path]:
    """Resolve every Worktree among Git's records; a bare entry is none."""
    return [
        Path(record["worktree"]).resolve()
        for record in records
        if record.get("worktree") and "bare" not in record
    ]


def worktree_records(
    root: Path, *, timeout: float = 5, git: Git | None = None
) -> list[dict[str, str]]:
    """Every record of ``git worktree list`` at ``root``, main working tree first.

    ``timeout`` applies only when no adapter is given; a supplied ``git``
    keeps its own.
    """
    adapter = git if git is not None else Git(root, timeout)
    return adapter.at(root).worktree_records()


def main_worktree(records: Sequence[Mapping[str, str]]) -> Path:
    """Return the Repository's main working tree, which Git always lists first.

    What belongs to the Repository rather than to one checkout — the default
    Worktree Root, the environment a hook binding may live in — anchors here,
    never on the linked Worktree a command happens to run in. A bare
    Repository has no main working tree; its first record is the bare
    directory, and a caller that must tell the two apart reads its ``bare``
    key.
    """
    # ``git worktree list`` always opens with the main working tree — or the
    # bare repository when there is none — and the listing checkout itself is
    # listed, so the first record exists.
    return Path(records[0]["worktree"]).resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def same_path(candidate: Path, expected: Path) -> bool:
    """Tell whether two paths name one place; a persisted path may not resolve."""
    try:
        return candidate.resolve() == expected.resolve()
    except (OSError, RuntimeError, ValueError):
        return False
