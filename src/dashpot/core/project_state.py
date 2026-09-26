"""Create a checkout's Project-local state directory, which ignores itself in Git."""

from __future__ import annotations

import contextlib
from pathlib import Path

PROJECT_STATE_DIRECTORY = Path(".dashpot") / "state"

# Git reads a ``.gitignore`` inside the directory it ignores, as ``.venv``
# does, so the directory stays out of Git whatever the Project's own
# ``.gitignore`` says, and ``*`` covers this file too.
STATE_GITIGNORE = "*\n"


def project_state_directory(checkout: Path) -> Path:
    """The Project-local state directory beneath one checkout."""
    return checkout / PROJECT_STATE_DIRECTORY


def ensure_state_directory(checkout: Path) -> Path:
    """Create the checkout's Project-local state directory and return it.

    The directory ignores itself in Git through its own ``.gitignore``,
    written when absent and never replaced once present. A record store that
    names its checkout calls this before every write, so an existing checkout
    gains the file the next time Dashpot writes state there. Creating the directory fails as
    any state write fails; writing the ``.gitignore`` never fails the write it
    precedes.
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
