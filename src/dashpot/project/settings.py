"""Machine-local Dashpot settings, kept beside the Workspace inventory."""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import ConfigDict, PlainValidator, ValidationError, field_validator

from ..core.errors import DashpotError
from ..core.model import Diagnostic
from ..core.pydantic import (
    LaxSequence,
    NonBlankString,
    PublishedModel,
    translate_validation_error,
)

SETTINGS_FILE_NAME = "config.toml"
WORKTREE_ROOT_VARIABLE = "DASHPOT_WORKTREE_ROOT"
WORKTREE_PATH_ARGUMENT = "{path}"


def _refresh_seconds(value: object) -> float:
    # Zero switches a period off, as TOML has no null; a boolean is not a
    # number of seconds even though Python counts it as an integer.
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    raise ValueError("must be a finite number of seconds, zero or more")


RefreshSeconds = Annotated[float, PlainValidator(_refresh_seconds)]


class SettingsError(DashpotError):
    """A settings file that cannot be read or does not validate."""


class SettingsFile(PublishedModel):
    """The settings file as written; a field this Dashpot does not know is kept.

    A field written by a newer Dashpot must not stop this one starting: a
    downgrade, or two versions sharing a home directory, keeps working, so
    unknown fields are retained here and diagnosed by the loader.
    """

    model_config = ConfigDict(extra="allow", alias_generator=None)

    worktree_root: NonBlankString | None = None
    worktree_open_command: LaxSequence[str] | None = None
    refresh_seconds: RefreshSeconds | None = None
    github_refresh_seconds: RefreshSeconds | None = None

    @field_validator("worktree_open_command")
    @classmethod
    def validate_open_command(
        cls, value: LaxSequence[str] | None
    ) -> LaxSequence[str] | None:
        """Validate a literal launcher argument list with an executable first."""
        if value is None:
            return value
        if not value or not value[0].strip():
            raise ValueError(
                "must be a nonempty argument array with a nonblank executable"
            )
        if value[0] == WORKTREE_PATH_ARGUMENT:
            raise ValueError("cannot use {path} as the executable")
        if any("\0" in arg for arg in value):
            raise ValueError("must not contain NUL characters")
        if ("/" in value[0] or "\\" in value[0]) and not Path(value[0]).is_absolute():
            raise ValueError("explicit executable paths must be absolute")
        return value


@dataclass(frozen=True, slots=True)
class Settings:
    """What one machine configures for every Project it observes."""

    worktree_root: Path | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    worktree_open_command: tuple[str, ...] | None = None
    refresh_seconds: float | None = None
    github_refresh_seconds: float | None = None


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
        raise SettingsError(
            f"cannot read Dashpot settings {settings_path}: {exc}"
        ) from exc
    try:
        file = SettingsFile.model_validate(raw)
    except ValidationError as exc:
        message = translate_validation_error(exc, root="")
        raise SettingsError(f"{settings_path} {message.lstrip()}") from exc
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
    command = (
        tuple(file.worktree_open_command)
        if file.worktree_open_command is not None
        else None
    )
    root = None
    if file.worktree_root is not None:
        # Path resolution is policy, not validation: ``~`` expands, and a
        # relative root is anchored at the settings file's own directory.
        root = Path(file.worktree_root).expanduser()
        if not root.is_absolute():
            root = settings_path.parent / root
    return Settings(
        worktree_root=root,
        diagnostics=diagnostics,
        worktree_open_command=command,
        refresh_seconds=file.refresh_seconds,
        github_refresh_seconds=file.github_refresh_seconds,
    )
