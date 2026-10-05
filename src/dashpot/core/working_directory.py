"""Read this command's working directory, refusing once it no longer exists."""

from __future__ import annotations

from pathlib import Path

from .errors import DashpotError, failure_text


class WorkingDirectoryError(DashpotError):
    """A command whose working directory is gone or cannot be read."""


def current_directory() -> Path:
    """This process's working directory, resolved, or a refusal when it cannot be read.

    A shell left in a removed Worktree still runs commands there; each one
    that needs its working directory refuses on one line rather than
    tracebacking. An Event Log, which must never fail its process, reads the
    directory leniently instead (``core.event_log.working_directory``).
    """
    try:
        return Path.cwd().resolve()
    except FileNotFoundError as exc:
        raise WorkingDirectoryError(
            "the working directory no longer exists; change to a directory "
            "that does and run the command again"
        ) from exc
    except OSError as exc:
        raise WorkingDirectoryError(
            f"cannot read the working directory: {failure_text(exc)}"
        ) from exc
