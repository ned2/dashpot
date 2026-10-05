"""Spell the commands Dashpot shows a person, so each survives a paste into a shell."""

from __future__ import annotations

import shlex
from pathlib import Path


def shell_command(*argv: str | Path | int) -> str:
    """One command line from its arguments, each quoted only where a shell needs it.

    A Branch name, a remote, or a path is interpolated as one argument
    however it is spelled: a space stays inside its argument and a shell
    metacharacter is never run. Dashpot never executes these strings; they
    are what a person reads after ``run:``, ``Next`` or ``recover:``.
    """
    return shlex.join(str(argument) for argument in argv)


def then(*commands: str) -> str:
    """Commands a shell runs in turn, each only once the one before succeeded."""
    return " && ".join(commands)


def in_directory(path: str | Path, *argv: str | Path | int) -> str:
    """``cd PATH && COMMAND``: a command a person runs from inside a Worktree."""
    return then(shell_command("cd", path), shell_command(*argv))
