"""Read the Project configuration tracked at a Worktree's root."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, ValidationError

from .models import ConfigModel, NonBlankString, translate_validation_error

PROJECT_CONFIG_NAME = ".dashpot/config.json"
DEFAULT_RECONCILIATION_SECONDS = 300.0


def _repository_relative(value: str) -> str:
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError("must be repository-relative")
    return value


class GitHubIssueSourceConfig(ConfigModel):
    """Issues come from the GitHub repository at the Worktree's origin."""

    kind: Literal["github"]
    reconciliation_seconds: float = Field(default=DEFAULT_RECONCILIATION_SECONDS, gt=0)


class LocalMarkdownIssueSourceConfig(ConfigModel):
    """Issues come from Markdown files under a repository-relative path."""

    kind: Literal["markdown"]
    path: Annotated[NonBlankString, AfterValidator(_repository_relative)]


IssueSourceConfig = Annotated[
    GitHubIssueSourceConfig | LocalMarkdownIssueSourceConfig,
    Field(discriminator="kind"),
]


class ProjectConfig(ConfigModel):
    """What ``.dashpot/config.json`` declares about one Project."""

    project_id: NonBlankString
    display_label: NonBlankString
    repository_id: NonBlankString
    issue_source: IssueSourceConfig


_FIELD_ORDER = ("projectId", "displayLabel", "repositoryId", "issueSource")


def load_project_config(
    root: Path, *, polling_seconds: float | None = None
) -> ProjectConfig:
    """Read the Project configuration tracked at a Worktree's root."""
    path = root / PROJECT_CONFIG_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Project configuration not found: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"cannot read Project configuration {path}: {exc}") from exc
    return parse_project_config(text, path, polling_seconds=polling_seconds)


def parse_project_config(
    text: str, path: Path, *, polling_seconds: float | None = None
) -> ProjectConfig:
    """Validate Project configuration text; ``path`` names it in diagnostics."""
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot read Project configuration {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    try:
        config = ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        message = translate_validation_error(
            exc,
            root="",
            field_order=_FIELD_ORDER,
            union_tags=frozenset({"github", "markdown"}),
            union_message="kind must be 'github' or 'markdown'",
        )
        raise RuntimeError(f"{path} {message.lstrip()}") from exc
    if (
        polling_seconds is not None
        and isinstance(config.issue_source, GitHubIssueSourceConfig)
        and config.issue_source.reconciliation_seconds < polling_seconds
    ):
        raise RuntimeError(
            f"{path} issueSource.reconciliationSeconds must be at least the "
            f"polling interval of {polling_seconds:g} seconds"
        )
    return config
