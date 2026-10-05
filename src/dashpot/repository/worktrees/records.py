"""Locate and identify Worktrees in Git topology records."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...core.git import Git
from ...core.worktree_paths import same_path
from ..repository import LOCAL_REF_PREFIX, branch_name

INITIALIZING_LOCK = "initializing"


def registered_at(records: list[dict[str, str]], path: Path) -> dict[str, str] | None:
    """Find the topology record registered at a Worktree path."""
    for record in records:
        raw = record.get("worktree")
        if raw and same_path(Path(raw), path):
            return record
    return None


BranchUse = Literal["checked out", "being rebased", "being bisected"]


@dataclass(frozen=True, slots=True)
class BranchInUse:
    """A Worktree that uses a Branch, and how: Git refuses to delete it meanwhile."""

    worktree: Path
    use: BranchUse


def branch_in_use(
    git: Git,
    records: Iterable[Mapping[str, str]],
    refname: str,
    *,
    besides: Path | None = None,
) -> BranchInUse | None:
    """Find a Worktree, other than ``besides``, that uses the Branch ``refname``.

    In use is what Git's own ``branch -d`` refuses: a Worktree whose HEAD
    is the Branch, and one rebasing or bisecting it, which ``git worktree
    list`` reports only as detached. The rebase and bisect state is read
    from each Worktree's administrative directory, as Git reads it.
    """
    listed = list(records)
    for record in listed:
        path = record.get("worktree")
        if not path or "bare" in record or record.get("branch") != refname:
            continue
        worktree = Path(path).resolve()
        if besides is None or not same_path(worktree, besides):
            return BranchInUse(worktree, "checked out")
    main = listed[0] if listed else {}
    main_path = (
        Path(main["worktree"]).resolve()
        if main.get("worktree") and "bare" not in main
        else None
    )
    for worktree, admin in _administrative_directories(git, main_path):
        if besides is not None and same_path(worktree, besides):
            continue
        for state in ("rebase-merge/head-name", "rebase-apply/head-name"):
            if _state(admin / state) == refname:
                return BranchInUse(worktree, "being rebased")
        # ``BISECT_START`` holds the short name of the Branch a bisect began on.
        bisected = _state(admin / "BISECT_START")
        if bisected and f"{LOCAL_REF_PREFIX}{bisected}" == refname:
            return BranchInUse(worktree, "being bisected")
    return None


def _administrative_directories(
    git: Git, main: Path | None
) -> Iterator[tuple[Path, Path]]:
    """Each Worktree with the directory where Git keeps its own state.

    The main Worktree's is the common directory, which a bare Repository
    has without a Worktree; a linked Worktree's is ``worktrees/<id>``
    beneath it, whose ``gitdir`` file names the Worktree's ``.git``,
    relative to that directory or absolute.
    """
    common = (git.root / git.text("rev-parse", "--git-common-dir")).resolve()
    if main is not None:
        yield main, common
    linked = common / "worktrees"
    if not linked.is_dir():
        return
    for admin in sorted(linked.iterdir()):
        gitdir = _state(admin / "gitdir")
        if gitdir is None:
            continue
        yield (admin / gitdir).resolve().parent, admin


def _state(path: Path) -> str | None:
    """A one-line Git state file's content, or None when there is none."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return text or None


def short_branch(record: Mapping[str, str]) -> str | None:
    """Read the short Branch name attached to a Worktree record."""
    branch = record.get("branch")
    if not branch:
        return None
    return branch_name(branch)
