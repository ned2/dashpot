"""Name the checkouts a Cleanup never removes, by one rule for every caller."""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from pathlib import Path

from ...core.git import GitError
from ...core.working_directory import current_directory
from ...core.worktree_paths import worktree_root


def protected_checkouts(anchors: Iterable[Path]) -> list[Path]:
    """The checkout Dashpot runs from, its Worktree root, and each Repository Anchor.

    ``anchors`` are the Repository Anchors the caller knows of: the
    dashboard's observed Project's, or for a Cleanup command every anchor
    of the Workspace inventory. Each is taken at its Worktree root; one
    that is gone or not a Repository still names a path no Cleanup should
    touch. Removing any of them takes the observer's own ground away, so
    the preview blocks it as ``protected``. Every call asks Git, so the
    dashboard calls it off the event loop.
    """
    current = current_directory()
    protected = [current]
    with contextlib.suppress(GitError):
        protected.append(worktree_root(current))
    for anchor in anchors:
        try:
            protected.append(worktree_root(anchor))
        except (OSError, GitError):
            protected.append(anchor.resolve())
    return list(dict.fromkeys(protected))
