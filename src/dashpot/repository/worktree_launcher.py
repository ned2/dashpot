"""Open a selected Worktree through one explicit, bounded launcher request."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.commands import CommandResult, CommandRunner
from ..core.model import Diagnostic
from ..project.settings import (
    WORKTREE_PATH_ARGUMENT,
    default_settings_path,
    load_settings,
)

WorktreeOpener = Callable[[Path], None]


def run_launch_command(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
    """Bound a launch request even when a descendant retains its output pipes."""
    try:
        process = subprocess.Popen(
            list(args),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(f"cannot launch {args[0]}: {exc}") from exc
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # A persistent terminal may own these pipes after the request parent
            # exits. Reap only the request; never kill its descendant process group.
            if process.poll() is None:
                process.kill()
            process.wait()
            raise RuntimeError(
                f"launch request timed out after {timeout:g}s; it may have opened a "
                "terminal already. Wrappers must detach children and redirect their streams"
            ) from exc
        return CommandResult(list(args), process.returncode, stdout, stderr)
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


@dataclass(frozen=True, slots=True)
class WorktreeLauncher:
    command: tuple[str, ...] | None
    tmux_pane: str | None
    inside_tmux: bool
    settings_path: Path
    timeout: float = 10
    runner: CommandRunner = run_launch_command

    def __call__(self, path: Path) -> None:
        """Request a terminal at the captured Worktree path."""
        if not path.is_absolute() or not path.is_dir() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Worktree directory is unavailable: {path}")
        if self.command is not None:
            args = [
                str(path) if arg == WORKTREE_PATH_ARGUMENT else arg
                for arg in self.command
            ]
        elif self.inside_tmux:
            if self.tmux_pane is None or re.fullmatch(r"%\d+", self.tmux_pane) is None:
                raise RuntimeError(
                    "Cannot identify the originating tmux pane (TMUX_PANE)"
                )
            # tmux expands -c as a format, then its argv parser treats a final
            # semicolon as a command separator even without shell evaluation.
            literal = str(path).replace("#", "##")
            if literal.endswith(";"):
                literal = literal[:-1] + r"\;"
            args = ["tmux", "split-window", "-v", "-t", self.tmux_pane, "-c", literal]
        else:
            raise RuntimeError(
                f"Configure worktree_open_command in {self.settings_path} or run "
                "Dashpot inside tmux; press y to copy the path"
            )
        result = self.runner(args, path, self.timeout)
        if result.returncode:
            detail = " ".join((result.stderr or result.stdout).split())[:500]
            raise RuntimeError(f"{args[0]} exited {result.returncode}: {detail}")


@dataclass(frozen=True, slots=True)
class LauncherConfiguration:
    opener: WorktreeOpener | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def configure_worktree_launcher(
    timeout: float = 10,
    *,
    path: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> LauncherConfiguration:
    """Load launcher preferences once, retaining settings failures as Diagnostics."""
    source = path if path is not None else default_settings_path()
    try:
        settings = load_settings(source)
    except RuntimeError as exc:
        return LauncherConfiguration(
            diagnostics=(
                Diagnostic(
                    source=f"settings:{source}",
                    code="settings-read",
                    severity="error",
                    message=str(exc),
                ),
            )
        )
    env = environment if environment is not None else os.environ
    return LauncherConfiguration(
        WorktreeLauncher(
            tuple(settings.worktree_open_command)
            if settings.worktree_open_command is not None
            else None,
            env.get("TMUX_PANE"),
            bool(env.get("TMUX")),
            source,
            timeout,
        ),
        settings.diagnostics,
    )
