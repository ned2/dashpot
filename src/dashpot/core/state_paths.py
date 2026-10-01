"""Locate Dashpot's own state: a configured checkout's, or the machine-local fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# What makes a checkout configured: the Project configuration at its root.
PROJECT_CONFIG_PATH = Path(".dashpot") / "config.json"

# How a linked Worktree's ``.git`` file opens: a pointer to its Git directory.
GITFILE_PREFIX = b"gitdir: "


def is_configured_checkout(root: Path) -> bool:
    """Whether the Worktree rooted at ``root`` carries a Project configuration."""
    return (root / PROJECT_CONFIG_PATH).is_file()


def enclosing_checkout(directory: Path) -> Path | None:
    """The root of the Worktree containing ``directory``, found without running Git.

    The nearest directory holding a plausible ``.git`` — a directory with a
    ``HEAD`` in a main working tree, a ``gitdir:`` file in a linked Worktree —
    is the root ``git rev-parse --show-toplevel`` reports for an ordinary
    checkout. The check is shallower than Git's own, but the search follows
    Git's: it passes over any other ``.git`` directory, ends at a ``.git``
    file it cannot read as a pointer, and never reaches a directory
    ``GIT_CEILING_DIRECTORIES`` names above ``directory``.
    """
    ceilings = _git_ceiling_directories()
    for candidate in (directory, *directory.parents):
        if candidate != directory and candidate in ceilings:
            return None
        dot_git = candidate / ".git"
        if dot_git.is_file():
            # Git refuses a malformed or unreadable ``.git`` file rather than
            # look above it.
            try:
                with dot_git.open("rb") as gitfile:
                    pointer = gitfile.read(len(GITFILE_PREFIX)) == GITFILE_PREFIX
            except OSError:
                pointer = False
            return candidate if pointer else None
        if (dot_git / "HEAD").is_file():
            return candidate
    return None


def _git_ceiling_directories() -> frozenset[Path]:
    """The directories ``GIT_CEILING_DIRECTORIES`` stops Git's search below.

    Git ignores a relative entry and one it cannot resolve, and resolves no
    entry that follows an empty one.
    """
    ceilings: set[Path] = set()
    resolve = True
    for entry in os.environ.get("GIT_CEILING_DIRECTORIES", "").split(os.pathsep):
        if not entry:
            resolve = False
            continue
        path = Path(os.path.normpath(entry))
        if not path.is_absolute():
            continue
        if resolve:
            try:
                path = path.resolve(strict=True)
            except (OSError, RuntimeError):
                # ``RuntimeError``: a symlink loop under ``resolve`` on Python 3.12.
                continue
        ceilings.add(path)
    return frozenset(ceilings)


def configured_checkout(directory: Path) -> Path | None:
    """The configured checkout containing ``directory``, if there is one."""
    root = enclosing_checkout(directory)
    return root if root is not None and is_configured_checkout(root) else None


def machine_state_directory() -> Path:
    """Dashpot's machine-local state, for what belongs to no configured checkout.

    ``$XDG_STATE_HOME/dashpot``, else ``~/Library/Application Support/dashpot``
    on macOS and ``~/.local/state/dashpot`` elsewhere.
    """
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "dashpot"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dashpot"
    return Path.home() / ".local" / "state" / "dashpot"
