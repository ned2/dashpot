"""Machine-local Dashpot settings, kept beside the Workspace inventory."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SETTINGS_FILE_NAME = "settings.json"
WORKTREE_ROOT_SETTING = "worktreeRoot"
WORKTREE_ROOT_VARIABLE = "DASHPOT_WORKTREE_ROOT"


@dataclass(frozen=True, slots=True)
class Settings:
    """What one machine configures for every Project it observes."""

    worktree_root: Path | None = None


def default_settings_path() -> Path:
    """Where this machine's settings live: ``~/.config/dashpot/settings.json``."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "dashpot" / SETTINGS_FILE_NAME


def load_settings(path: Path | None = None) -> Settings:
    """Read the machine-local settings; an absent file is the default settings."""
    settings_path = path if path is not None else default_settings_path()
    try:
        raw: Any = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"cannot read Dashpot settings {settings_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{settings_path} must contain a JSON object")
    unexpected = sorted(set(raw) - {WORKTREE_ROOT_SETTING})
    if unexpected:
        raise RuntimeError(
            f"{settings_path} has unexpected fields: {', '.join(unexpected)}"
        )
    worktree_root = raw.get(WORKTREE_ROOT_SETTING)
    if worktree_root is None:
        return Settings()
    if not isinstance(worktree_root, str) or not worktree_root.strip():
        raise RuntimeError(
            f"{settings_path} {WORKTREE_ROOT_SETTING} must be a non-empty string"
        )
    root = Path(worktree_root.strip()).expanduser()
    if not root.is_absolute():
        root = settings_path.parent / root
    return Settings(worktree_root=root)
