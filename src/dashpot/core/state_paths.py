"""Locate Dashpot's own state: a configured checkout's, or the machine-local fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# What makes a checkout configured: the Project configuration at its root.
PROJECT_CONFIG_PATH = Path(".dashpot") / "config.json"


def is_configured_checkout(root: Path) -> bool:
    """Whether the Worktree rooted at ``root`` carries a Project configuration."""
    return (root / PROJECT_CONFIG_PATH).is_file()


def enclosing_checkout(directory: Path) -> Path | None:
    """The root of the Worktree containing ``directory``, found without running Git.

    The nearest directory holding a ``.git`` entry — a directory in a main
    working tree, a file in a linked Worktree — is the root ``git rev-parse
    --show-toplevel`` reports for an ordinary checkout.
    """
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


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
