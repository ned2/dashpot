"""Locate Dashpot's own state: a configured checkout's, or the machine-local fallback.

It owns where a checkout's Project configuration and Project-local state
directory lie, and creates that directory so it ignores itself in Git; each
store names its own directory beneath it.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

# What Dashpot keeps in a checkout lives beneath this directory at its root.
DASHPOT_DIRECTORY = Path(".dashpot")
# What makes a checkout configured: the Project configuration at its root.
PROJECT_CONFIG_PATH = DASHPOT_DIRECTORY / "config.json"
PROJECT_STATE_DIRECTORY = DASHPOT_DIRECTORY / "state"

# Git reads a ``.gitignore`` inside the directory it ignores, as ``.venv``
# does, so the directory stays out of Git whatever the Project's own
# ``.gitignore`` says, and ``*`` covers this file too.
STATE_GITIGNORE = "*\n"

# How a linked Worktree's ``.git`` file opens: a pointer to its Git directory.
GITFILE_PREFIX = b"gitdir: "


def is_configured_checkout(root: Path) -> bool:
    """Whether the Worktree rooted at ``root`` carries a Project configuration."""
    return (root / PROJECT_CONFIG_PATH).is_file()


def project_state_directory(checkout: Path) -> Path:
    """The Project-local state directory beneath one checkout."""
    return checkout / PROJECT_STATE_DIRECTORY


def ensure_state_directory(checkout: Path) -> Path:
    """Create the checkout's Project-local state directory and return it.

    The directory ignores itself in Git through its own ``.gitignore``,
    written when absent and never replaced once present. A record store that
    names its checkout calls this before every write, so an existing checkout
    gains the file the next time Dashpot writes state there. Creating the
    directory fails as any state write fails; writing the ``.gitignore`` never
    fails the write it precedes.
    """
    directory = project_state_directory(checkout)
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / ".gitignore"
    if not ignore.exists():
        # Exclusive creation lets concurrent writers race without truncating
        # a file another has already written.
        with (
            contextlib.suppress(OSError),
            ignore.open("x", encoding="utf-8") as stream,
        ):
            stream.write(STATE_GITIGNORE)
    return directory


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
