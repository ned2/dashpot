"""Compose observation and Cleanup operations for application entry points."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .core.model import Diagnostic
from .observation.collect import ObservationCoordinator
from .project.project_config import PROJECT_CONFIG_NAME
from .project.workspace import (
    RepositoryAnchor,
    Workspace,
    default_workspace_config,
    load_workspaces,
    merge_workspaces,
    resolve_workspace_projects,
)
from .queries.query_source import configured_query_source
from .queries.source_queries import QuerySource
from .repository.cleanup import (
    CleanupConfirmation,
    CleanupError,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    cleanup_git,
    inspect_cleanup,
    perform_cleanup,
)
from .repository.repository import worktree_root
from .ui.page_runner import QUERY_SOURCE_KEYS


@dataclass(frozen=True, slots=True)
class ObservationOptions:
    """Describe what one Dashpot run observes and how patiently."""

    workspaces: tuple[Workspace, ...] = ()
    config: Path | None = None
    timeout: float = 10.0
    refresh_seconds: float = 15.0
    state_dir: Path | None = None


def run_cleanup(
    request: CleanupRequest,
    *,
    select: Callable[[CleanupPreview], tuple[str, ...]],
    delete_ignored: bool = False,
    dry_run: bool,
    timeout: float,
) -> CleanupReport:
    """Compose preview, selection, and confirmed Cleanup from this checkout."""
    protected = cleanup_protection()
    git = cleanup_git(timeout)
    preview = inspect_cleanup(request, protected=protected, timeout=timeout, git=git)
    # A preview with nothing to select has already said why; ``perform``
    # repeats the refusal so the report carries it in every output shape.
    confirmation = CleanupConfirmation(
        request,
        preview.fingerprint,
        select(preview),
        delete_ignored=delete_ignored,
    )
    return perform_cleanup(
        confirmation,
        protected=protected,
        timeout=timeout,
        git=git,
        dry_run=dry_run,
    )


def cleanup_protection() -> list[Path]:
    """The checkouts a Cleanup never removes: this one and every configured Repository Anchor.

    The anchors are the ones a dashboard run from here would observe: the
    checkout's own root when it carries a Project configuration, and each
    anchor of the Workspace config, taken at its Worktree root. An inventory
    that cannot be read refuses the Cleanup rather than proceeding unaware.
    """
    current = Path.cwd().resolve()
    protected = [current]
    try:
        root = worktree_root(current)
    except RuntimeError:
        root = None
    if root is not None and (root / PROJECT_CONFIG_NAME).is_file():
        protected.append(root)
    inventory = default_workspace_config()
    if inventory.is_file():
        try:
            workspaces = load_workspaces(inventory).workspaces
        except RuntimeError as exc:
            raise CleanupError(
                f"cannot tell which Repository Anchors to protect: {exc}"
            ) from exc
        for workspace in workspaces:
            for anchor in workspace.anchors:
                path = Path(anchor.path)
                # An anchor that is gone or not a repository still names a
                # path no Cleanup should touch.
                try:
                    protected.append(worktree_root(path))
                except (OSError, RuntimeError):
                    protected.append(path)
    return list(dict.fromkeys(protected))


def create_collector(
    options: ObservationOptions, *, recurring: bool = True
) -> ObservationCoordinator:
    """Resolve the Workspaces one run observes into its coordinator."""
    polling_seconds = (
        options.refresh_seconds if recurring and options.refresh_seconds > 0 else None
    )
    inventory_diagnostics: Sequence[Diagnostic] = ()
    if options.workspaces:
        workspaces = merge_workspaces(list(options.workspaces))
    elif options.config is not None:
        inventory = load_workspaces(options.config.expanduser())
        workspaces = list(inventory.workspaces)
        inventory_diagnostics = inventory.diagnostics
    else:
        current = Path.cwd().resolve()
        try:
            project_root = worktree_root(current)
            in_repository = True
        except RuntimeError:
            project_root = current
            in_repository = False
        if (project_root / PROJECT_CONFIG_NAME).is_file():
            workspaces = [
                Workspace(
                    project_root.name,
                    (RepositoryAnchor(str(project_root)),),
                )
            ]
        else:
            inventory = default_workspace_config()
            if in_repository and not inventory.is_file():
                raise RuntimeError(
                    f"this repository has no {PROJECT_CONFIG_NAME}; run "
                    f"'dashpot init' to configure it, or define Workspaces "
                    f"in {inventory}"
                )
            loaded = load_workspaces(inventory)
            workspaces = list(loaded.workspaces)
            inventory_diagnostics = loaded.diagnostics
    resolution = resolve_workspace_projects(
        workspaces,
        timeout=options.timeout,
        polling_seconds=polling_seconds,
    )
    return ObservationCoordinator(
        resolution.projects,
        timeout=options.timeout,
        state_dir=options.state_dir.expanduser() if options.state_dir else None,
        diagnostics=[*inventory_diagnostics, *resolution.diagnostics],
        polling_seconds=polling_seconds,
        query_driven=recurring,
    )


def create_query_sources(collector: ObservationCoordinator) -> dict[str, QuerySource]:
    """Build the configured Query Source behind each of the dashboard's queries."""
    root = (
        Path(collector.projects[0].primary_anchor) if collector.projects else Path.cwd()
    )
    return {
        key: configured_query_source(root, timeout=collector.timeout)
        for key in QUERY_SOURCE_KEYS
    }
