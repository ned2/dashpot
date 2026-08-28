from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], Path, float], CommandResult]


def run_command(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout:g}s: {args[0]}") from exc
    return CommandResult(list(args), result.returncode, result.stdout, result.stderr)
