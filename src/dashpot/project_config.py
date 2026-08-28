from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypeAlias

PROJECT_CONFIG_NAME = ".dashpot/config.json"


@dataclass(frozen=True, slots=True)
class GitHubIssueSourceConfig:
    kind: Literal["github"]


@dataclass(frozen=True, slots=True)
class LocalMarkdownIssueSourceConfig:
    kind: Literal["markdown"]
    path: str


IssueSourceConfig: TypeAlias = GitHubIssueSourceConfig | LocalMarkdownIssueSourceConfig


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    project_id: str
    display_label: str
    repository_id: str
    issue_source: IssueSourceConfig


def load_project_config(root: Path) -> ProjectConfig:
    path = root / PROJECT_CONFIG_NAME
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Project configuration not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read Project configuration {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    _require_keys(
        raw,
        {"projectId", "displayLabel", "repositoryId", "issueSource"},
        path,
    )
    project_id = _non_empty_string(raw["projectId"], f"{path} projectId")
    display_label = _non_empty_string(raw["displayLabel"], f"{path} displayLabel")
    repository_id = _non_empty_string(raw["repositoryId"], f"{path} repositoryId")
    issue_source = raw["issueSource"]
    if not isinstance(issue_source, dict):
        raise RuntimeError(f"{path} issueSource must be an object")
    kind = issue_source.get("kind")
    if kind == "github":
        _require_keys(issue_source, {"kind"}, path)
        return ProjectConfig(
            project_id,
            display_label,
            repository_id,
            GitHubIssueSourceConfig("github"),
        )
    if kind == "markdown":
        _require_keys(issue_source, {"kind", "path"}, path)
        issues_path = _non_empty_string(
            issue_source["path"], f"{path} issueSource.path"
        )
        parsed_path = PurePosixPath(issues_path)
        if parsed_path.is_absolute() or ".." in parsed_path.parts:
            raise RuntimeError(f"{path} issueSource.path must be repository-relative")
        return ProjectConfig(
            project_id,
            display_label,
            repository_id,
            LocalMarkdownIssueSourceConfig("markdown", issues_path),
        )
    raise RuntimeError(f"{path} issueSource.kind must be 'github' or 'markdown'")


def _require_keys(value: dict[str, Any], expected: set[str], path: Path) -> None:
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing:
        raise RuntimeError(f"{path} is missing fields: {', '.join(missing)}")
    if unexpected:
        raise RuntimeError(f"{path} has unexpected fields: {', '.join(unexpected)}")


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{field} must be a non-empty string")
    return value.strip()
