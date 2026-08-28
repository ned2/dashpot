from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import (
    Diagnostic,
    RepositoryAnchor,
    ResolvedProject,
    Workspace,
)
from .project_config import (
    GitHubIssueSourceConfig,
    ProjectConfig,
    load_project_config,
)
from .repository import (
    github_repo_from_remote,
    observe_github_repository_identity,
    worktree_root,
)

RootObserver = Callable[[Path], Path]
GitHubIdentityObserver = Callable[[Path, str, float], tuple[str, str]]


@dataclass(frozen=True, slots=True)
class WorkspaceResolution:
    projects: list[ResolvedProject]
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, slots=True)
class _ResolvedAnchor:
    workspace: str
    root: str
    config: ProjectConfig


class _AnchorResolutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_workspaces(path: Path) -> list[Workspace]:
    """Load named Workspaces whose membership is an explicit anchor list."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"workspace config not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read workspace config {path}: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"workspaces"}:
        raise RuntimeError(
            f"workspace config {path} must contain only a workspaces array"
        )
    items = raw["workspaces"]
    if not isinstance(items, list):
        raise RuntimeError(f"workspace config {path} must contain a workspaces array")
    workspaces: list[Workspace] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise RuntimeError(f"workspace entry {index} must be an object")
        missing = {"name", "anchors"} - set(item)
        unexpected = set(item) - {"name", "anchors"}
        if missing:
            raise RuntimeError(
                f"workspace entry {index} is missing fields: {', '.join(sorted(missing))}"
            )
        if unexpected:
            raise RuntimeError(
                f"workspace entry {index} has unexpected fields: "
                f"{', '.join(sorted(unexpected))}"
            )
        name = item["name"]
        anchors = item["anchors"]
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"workspace entry {index} needs a non-empty name")
        if not isinstance(anchors, list) or not anchors:
            raise RuntimeError(
                f"workspace entry {index} needs a non-empty anchors array"
            )
        resolved: list[RepositoryAnchor] = []
        for anchor_index, raw_anchor in enumerate(anchors):
            if not isinstance(raw_anchor, str) or not raw_anchor.strip():
                raise RuntimeError(
                    f"workspace entry {index} anchor {anchor_index} "
                    "must be a non-empty path"
                )
            anchor_path = Path(raw_anchor).expanduser()
            if not anchor_path.is_absolute():
                anchor_path = path.parent / anchor_path
            resolved.append(RepositoryAnchor(str(anchor_path.resolve())))
        workspaces.append(Workspace(name.strip(), tuple(resolved)))
    return workspaces


def default_workspace_config() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "dashpot" / "workspaces.json"


def merge_workspaces(workspaces: Sequence[Workspace]) -> list[Workspace]:
    """Merge repeated CLI Workspace names while retaining anchor order."""
    names: list[str] = []
    anchors_by_name: dict[str, list[RepositoryAnchor]] = {}
    for workspace in workspaces:
        if workspace.name not in anchors_by_name:
            names.append(workspace.name)
            anchors_by_name[workspace.name] = []
        anchors_by_name[workspace.name].extend(workspace.anchors)
    return [Workspace(name, tuple(anchors_by_name[name])) for name in names]


def resolve_workspace_projects(
    workspaces: Sequence[Workspace],
    *,
    timeout: float = 10,
    root_observer: RootObserver = worktree_root,
    github_identity_observer: GitHubIdentityObserver = observe_github_repository_identity,
) -> WorkspaceResolution:
    """Validate every anchor, then group valid clones by Project Identity."""
    resolved: list[_ResolvedAnchor] = []
    diagnostics: list[Diagnostic] = []
    for workspace in workspaces:
        for anchor in workspace.anchors:
            try:
                resolved.append(
                    _resolve_anchor(
                        workspace.name,
                        anchor,
                        timeout,
                        root_observer,
                        github_identity_observer,
                    )
                )
            except (OSError, RuntimeError) as exc:
                diagnostics.append(
                    Diagnostic(
                        f"anchor:{anchor.path}",
                        "error",
                        str(exc),
                        getattr(exc, "code", "repository-anchor"),
                    )
                )

    by_project: dict[str, list[_ResolvedAnchor]] = {}
    project_order: list[str] = []
    for anchor in resolved:
        project_id = anchor.config.project_id
        if project_id not in by_project:
            project_order.append(project_id)
            by_project[project_id] = []
        by_project[project_id].append(anchor)

    projects: list[ResolvedProject] = []
    for project_id in project_order:
        anchors = by_project[project_id]
        repository_ids = _ordered_unique(
            anchor.config.repository_id for anchor in anchors
        )
        if len(repository_ids) != 1:
            evidence = ", ".join(
                f"{anchor.root}={anchor.config.repository_id}" for anchor in anchors
            )
            diagnostics.append(
                Diagnostic(
                    f"project:{project_id}",
                    "error",
                    f"Project Identity {project_id} resolves to conflicting durable "
                    f"Repository identities: {evidence}",
                    "project-repository-conflict",
                )
            )
            continue
        issue_sources = _ordered_unique(
            anchor.config.issue_source for anchor in anchors
        )
        if len(issue_sources) != 1:
            evidence = ", ".join(anchor.root for anchor in anchors)
            diagnostics.append(
                Diagnostic(
                    f"project:{project_id}",
                    "error",
                    f"Project Identity {project_id} has conflicting Issue Sources "
                    f"across Repository Anchors: {evidence}",
                    "project-source-conflict",
                )
            )
            continue
        config = anchors[0].config
        roots = _ordered_unique(anchor.root for anchor in anchors)
        workspace_names = _ordered_unique(anchor.workspace for anchor in anchors)
        projects.append(
            ResolvedProject(
                project_id=config.project_id,
                display_label=config.display_label,
                repository_id=config.repository_id,
                workspaces=tuple(workspace_names),
                anchors=tuple(roots),
                primary_anchor=roots[0],
            )
        )
    return WorkspaceResolution(projects, diagnostics)


def _resolve_anchor(
    workspace: str,
    anchor: RepositoryAnchor,
    timeout: float,
    root_observer: RootObserver,
    github_identity_observer: GitHubIdentityObserver,
) -> _ResolvedAnchor:
    requested = Path(anchor.path)
    if not requested.is_dir():
        raise _AnchorResolutionError(
            "repository-anchor",
            f"Repository Anchor does not exist or is not a directory: {requested}",
        )
    root = root_observer(requested).resolve()
    config = load_project_config(root)
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        reference = github_repo_from_remote(root)
        if not reference:
            raise _AnchorResolutionError(
                "github-origin",
                f"Project {config.project_id} requires a GitHub origin at {root}",
            )
        observed_id, observed_reference = github_identity_observer(
            root, reference, timeout
        )
        if observed_id != config.repository_id:
            raise _AnchorResolutionError(
                "repository-identity-conflict",
                f"Project Identity {config.project_id} expects Repository identity "
                f"{config.repository_id}, but {root} resolves to {observed_id} "
                f"({observed_reference})",
            )
    return _ResolvedAnchor(workspace, str(root), config)


def _ordered_unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
