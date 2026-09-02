from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], Path, float], CommandResult]


def run_command(
    args: Sequence[str],
    cwd: Path,
    timeout: float,
    *,
    environment: Mapping[str, str] | None = None,
    non_interactive: bool = False,
) -> CommandResult:
    """Run one command to completion with its output captured.

    ``environment`` adds to the inherited environment. A ``non_interactive``
    command gets no stdin and its own session, so neither it nor a helper it
    starts (an SSH passphrase prompt, say) can open the controlling terminal
    and take over the screen; it fails or times out instead.
    """
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, **environment} if environment else None,
            stdin=subprocess.DEVNULL if non_interactive else None,
            start_new_session=non_interactive,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout:g}s: {args[0]}") from exc
    return CommandResult(list(args), result.returncode, result.stdout, result.stderr)


def non_interactive_runner(
    environment: Mapping[str, str] | None = None,
) -> CommandRunner:
    """A runner whose every command is non-interactive, with ``environment`` added."""
    return partial(run_command, environment=environment, non_interactive=True)
