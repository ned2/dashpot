"""Load the Workspace inventory and resolve its Repository Anchors to Projects."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, ConfigDict, ValidationError

from .errors import DashpotError
from .git import Git
from .model import (
    Diagnostic,
    RepositoryAnchor,
    ResolvedProject,
    Workspace,
)
from .models import (
    LaxSequence,
    NonBlankString,
    PublishedModel,
    translate_validation_error,
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


def _non_empty(value: Sequence[str]) -> Sequence[str]:
    if not value:
        raise ValueError("must not be empty")
    return value


class _InventoryModel(PublishedModel):
    # A field written by a newer Dashpot is retained and diagnosed, never fatal.
    model_config = ConfigDict(extra="allow")


class WorkspaceEntryConfig(_InventoryModel):
    """One named Workspace and the Repository Anchors it lists."""

    name: NonBlankString
    anchors: Annotated[LaxSequence[NonBlankString], AfterValidator(_non_empty)]


class WorkspaceInventoryConfig(_InventoryModel):
    """The Workspace inventory file: an explicit list of Workspaces."""

    workspaces: LaxSequence[WorkspaceEntryConfig]


@dataclass(frozen=True, slots=True)
class WorkspaceInventory:
    """The Workspaces an inventory file declares, with what it could not use."""

    workspaces: tuple[Workspace, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceResolution:
    projects: list[ResolvedProject]
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, slots=True)
class _ResolvedAnchor:
    workspace: str
    root: str
    config: ProjectConfig


class _AnchorResolutionError(DashpotError, RuntimeError):
    """A Repository Anchor this Workspace cannot resolve, with its diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _describe_inventory_path(segments: Sequence[str]) -> str:
    # ``workspaces.0.anchors.1`` reads as ``workspace entry 0 anchor 1``.
    text = ".".join(segments)
    text = re.sub(r"^workspaces\.(\d+)", r"workspace entry \1", text)
    text = re.sub(r"\.anchors\.(\d+)$", r" anchor \1", text)
    return text.replace(".", " ")


def load_workspaces(path: Path) -> WorkspaceInventory:
    """Load named Workspaces whose membership is an explicit anchor list.

    A field this Dashpot does not know, at the top level or in an entry, is
    ignored with a Diagnostic rather than refusing the whole inventory.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"workspace config not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read workspace config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"workspace config {path} must contain a JSON object")
    try:
        inventory = WorkspaceInventoryConfig.model_validate(raw)
    except ValidationError as exc:
        message = translate_validation_error(
            exc,
            root=f"workspace config {path}",
            describe_path=_describe_inventory_path,
        )
        raise RuntimeError(message) from exc
    unknown = [f"{field}" for field in sorted(inventory.model_extra or {})]
    workspaces: list[Workspace] = []
    for index, entry in enumerate(inventory.workspaces):
        unknown.extend(
            f"workspaces[{index}].{field}" for field in sorted(entry.model_extra or {})
        )
        resolved: list[RepositoryAnchor] = []
        for raw_anchor in entry.anchors:
            # Path resolution is policy, not validation: ``~`` expands, and a
            # relative anchor is taken from the inventory file's directory.
            anchor_path = Path(raw_anchor).expanduser()
            if not anchor_path.is_absolute():
                anchor_path = path.parent / anchor_path
            resolved.append(RepositoryAnchor(str(anchor_path.resolve())))
        workspaces.append(Workspace(entry.name, tuple(resolved)))
    diagnostics = (
        (
            Diagnostic(
                source=f"workspaces:{path}",
                severity="warning",
                message=f"Ignoring unknown fields in workspace config {path}: "
                + ", ".join(unknown),
                code="workspace-config-unknown-field",
            ),
        )
        if unknown
        else ()
    )
    return WorkspaceInventory(tuple(workspaces), diagnostics)


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
    git: Git | None = None,
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
                        git,
                    )
                )
            except (OSError, RuntimeError) as exc:
                diagnostics.append(
                    Diagnostic(
                        source=f"anchor:{anchor.path}",
                        severity="error",
                        message=str(exc),
                        code=getattr(exc, "code", "repository-anchor"),
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
                    source=f"project:{project_id}",
                    severity="error",
                    message=f"Project Identity {project_id} resolves to conflicting durable "
                    f"Repository identities: {evidence}",
                    code="project-repository-conflict",
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
                    source=f"project:{project_id}",
                    severity="error",
                    message=f"Project Identity {project_id} has conflicting Issue Sources "
                    f"across Repository Anchors: {evidence}",
                    code="project-source-conflict",
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
    if len(projects) > 1:
        raise WorkspaceScopeError(projects)
    return WorkspaceResolution(projects, diagnostics)


class WorkspaceScopeError(DashpotError, RuntimeError):
    """Refuse Repository Anchors that resolve to more than one Project."""

    def __init__(self, projects: Sequence[ResolvedProject]) -> None:
        listing = "; ".join(
            f"{project.display_label} ({project.project_id}) at "
            + ", ".join(project.anchors)
            for project in projects
        )
        super().__init__(
            f"Dashpot observes one Project per run, but the configured "
            f"Repository Anchors resolve to {len(projects)} Projects: {listing}. "
            f"Configure anchors for one Project only."
        )
        self.projects = tuple(projects)


def _resolve_anchor(
    workspace: str,
    anchor: RepositoryAnchor,
    timeout: float,
    root_observer: RootObserver,
    github_identity_observer: GitHubIdentityObserver,
    git: Git | None,
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
        reference = github_repo_from_remote(root, git)
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
