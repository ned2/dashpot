from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .commands import run_command
from .model import Repository, Worktree


def git(root: Path, *args: str, timeout: float = 5) -> str:
    result = run_command(["git", *args], root, timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def observe_repository(root: Path) -> Repository:
    resolved = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    branch = git(resolved, "branch", "--show-current") or None
    return Repository(
        root=str(resolved),
        name=resolved.name,
        branch=branch,
        head=git(resolved, "rev-parse", "HEAD"),
        dirty=bool(git(resolved, "status", "--porcelain=v1", "--untracked-files=normal")),
        worktrees=parse_worktrees(git(resolved, "worktree", "list", "--porcelain")),
    )


def parse_worktrees(raw: str) -> list[Worktree]:
    worktrees: list[Worktree] = []
    current: dict[str, str] = {}
    for line in [*raw.splitlines(), ""]:
        if not line:
            if current.get("worktree") and current.get("HEAD"):
                branch = current.get("branch")
                if branch and branch.startswith("refs/heads/"):
                    branch = branch.removeprefix("refs/heads/")
                worktrees.append(Worktree(current["worktree"], current["HEAD"], branch))
            current = {}
        elif " " in line:
            key, value = line.split(" ", 1)
            current[key] = value
    return worktrees


def load_config(root: Path) -> dict[str, Any]:
    path = root / ".tasksmd.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def github_repo_from_remote(root: Path) -> str | None:
    try:
        remote = git(root, "remote", "get-url", "origin")
    except RuntimeError:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group(1) if match else None


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
