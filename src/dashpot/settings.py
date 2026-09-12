"""Machine-local Dashpot settings, kept beside the Workspace inventory."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ConfigDict, ValidationError

from .model import Diagnostic
from .models import NonBlankString, PublishedModel, translate_validation_error

SETTINGS_FILE_NAME = "config.toml"
WORKTREE_ROOT_VARIABLE = "DASHPOT_WORKTREE_ROOT"


class SettingsFile(PublishedModel):
    """The settings file as written; a field this Dashpot does not know is kept.

    A field written by a newer Dashpot must not stop this one starting: a
    downgrade, or two versions sharing a home directory, keeps working, so
    unknown fields are retained here and diagnosed by the loader.
    """

    model_config = ConfigDict(extra="allow", alias_generator=None)

    worktree_root: NonBlankString | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    """What one machine configures for every Project it observes."""

    worktree_root: Path | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def default_settings_path() -> Path:
    """Locate this machine's settings at ``~/.config/dashpot/config.toml``."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "dashpot" / SETTINGS_FILE_NAME


def load_settings(path: Path | None = None) -> Settings:
    """Read machine-local TOML settings, using defaults for an absent file."""
    settings_path = path if path is not None else default_settings_path()
    try:
        with settings_path.open("rb") as stream:
            raw = tomllib.load(stream)
    except FileNotFoundError:
        return Settings()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(
            f"cannot read Dashpot settings {settings_path}: {exc}"
        ) from exc
    try:
        file = SettingsFile.model_validate(raw)
    except ValidationError as exc:
        message = translate_validation_error(exc, root="")
        raise RuntimeError(f"{settings_path} {message.lstrip()}") from exc
    unexpected = sorted(file.model_extra or {})
    diagnostics = (
        (
            Diagnostic(
                source=f"settings:{settings_path}",
                severity="warning",
                message=(
                    f"Ignoring unknown Dashpot settings fields: {', '.join(unexpected)}"
                ),
                code="settings-unknown-field",
            ),
        )
        if unexpected
        else ()
    )
    if file.worktree_root is None:
        return Settings(diagnostics=diagnostics)
    # Path resolution is policy, not validation: ``~`` expands, and a relative
    # root is anchored at the settings file's own directory.
    root = Path(file.worktree_root).expanduser()
    if not root.is_absolute():
        root = settings_path.parent / root
    return Settings(worktree_root=root, diagnostics=diagnostics)
