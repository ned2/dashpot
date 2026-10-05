"""Compose observation and Cleanup operations for application entry points."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .core.git import GitError
from .core.model import Diagnostic
from .core.state_paths import is_configured_checkout
from .core.working_directory import current_directory
from .core.worktree_paths import worktree_root
from .github.github import LatestRateLimit
from .observation.collect import ObservationCoordinator
from .project.project_config import PROJECT_CONFIG_NAME, ProjectConfigError
from .project.settings import Settings, SettingsError, load_settings
from .project.workspace import (
    RepositoryAnchor,
    Workspace,
    WorkspaceConfigError,
    default_workspace_config,
    load_workspaces,
    merge_workspaces,
    resolve_workspace_projects,
)
from .queries.query_source import UnresolvedQuerySource, configured_query_source
from .queries.source_queries import QUERY_SOURCE_KEYS, QuerySource
from .repository.cleanup import (
    NO_ACKNOWLEDGEMENT,
    Acknowledgement,
    CleanupConfirmation,
    CleanupError,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    cleanup_git,
    inspect_cleanup,
    listed_in,
    perform_cleanup,
    protected_checkouts,
)

DEFAULT_REFRESH_SECONDS = 15.0
DEFAULT_GITHUB_REFRESH_SECONDS = 60.0
DEFAULT_UNATTENDED_SECONDS = 7200.0


@dataclass(frozen=True, slots=True)
class RefreshPeriods:
    """How often a dashboard refreshes by itself, in seconds; 0 switches a period off.

    ``local`` paces local observation: Worktrees, Branches, Agent Sessions and
    Agent Runs. ``github`` paces the queries GitHub meters against the hourly
    allowance. ``unattended`` is how long without a key or mouse event
    pauses the GitHub period (ADR 0068).
    """

    local: float = DEFAULT_REFRESH_SECONDS
    github: float = DEFAULT_GITHUB_REFRESH_SECONDS
    unattended: float = DEFAULT_UNATTENDED_SECONDS

    def query_seconds(self, sources: Mapping[str, QuerySource]) -> float:
        """The period of the dashboard's Query Sources.

        Only a GitHub Query Source takes the GitHub period; a local one costs
        nothing, so it keeps pace with local observation.
        """
        return self.github if reads_github(sources) else self.local


def reads_github(sources: Mapping[str, QuerySource]) -> bool:
    """Whether any of the dashboard's Query Sources asks GitHub."""
    return any(
        source.context is not None and source.context.source == "github"
        for source in sources.values()
    )


def refresh_periods(
    refresh_seconds: float | None = None,
    github_refresh_seconds: float | None = None,
    unattended_seconds: float | None = None,
    *,
    settings_path: Path | None = None,
) -> RefreshPeriods:
    """Take each period from its flag, then its setting, then its default."""
    try:
        settings = load_settings(settings_path)
    except SettingsError:
        # The launcher configuration reports an unreadable settings file as a
        # Diagnostic on the dashboard (ADR 0035); the periods keep their
        # defaults rather than stopping it opening.
        settings = Settings()
    return RefreshPeriods(
        local=_first_given(
            refresh_seconds, settings.refresh_seconds, DEFAULT_REFRESH_SECONDS
        ),
        github=_first_given(
            github_refresh_seconds,
            settings.github_refresh_seconds,
            DEFAULT_GITHUB_REFRESH_SECONDS,
        ),
        unattended=_first_given(
            unattended_seconds,
            settings.unattended_seconds,
            DEFAULT_UNATTENDED_SECONDS,
        ),
    )


def _first_given(flag: float | None, setting: float | None, default: float) -> float:
    if flag is not None:
        return flag
    return setting if setting is not None else default


@dataclass(frozen=True, slots=True)
class ObservationOptions:
    """Describe what one Dashpot run observes and how patiently."""

    workspaces: tuple[Workspace, ...] = ()
    config: Path | None = None
    timeout: float = 10.0
    refresh_seconds: float = DEFAULT_REFRESH_SECONDS
    state_dir: Path | None = None


def run_cleanup(
    request: CleanupRequest,
    *,
    select: Callable[[CleanupPreview], tuple[str, ...]],
    delete_ignored: bool = False,
    despite_subagents: Acknowledgement = NO_ACKNOWLEDGEMENT,
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
        despite_subagents=despite_subagents,
        listed=listed_in(preview) if despite_subagents else None,
    )
    return perform_cleanup(
        confirmation,
        protected=protected,
        timeout=timeout,
        git=git,
        dry_run=dry_run,
    )


def cleanup_protection() -> list[Path]:
    """The checkouts a Cleanup command never removes, by the rule the dashboard applies.

    A command observes no Project, so the Repository Anchors it protects
    are every anchor of the Workspace inventory, beside this checkout and
    its Worktree root, which a configured checkout's own anchor is
    (``protected_checkouts``). An inventory that cannot be read refuses the
    Cleanup rather than proceeding unaware.
    """
    anchors: list[Path] = []
    inventory = default_workspace_config()
    if inventory.is_file():
        try:
            workspaces = load_workspaces(inventory).workspaces
        except WorkspaceConfigError as exc:
            raise CleanupError(
                f"cannot tell which Repository Anchors to protect: {exc}"
            ) from exc
        anchors = [
            Path(anchor.path)
            for workspace in workspaces
            for anchor in workspace.anchors
        ]
    return protected_checkouts(anchors)


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
        current = current_directory()
        try:
            project_root = worktree_root(current)
            in_repository = True
        except GitError:
            project_root = current
            in_repository = False
        if is_configured_checkout(project_root):
            workspaces = [
                Workspace(
                    project_root.name,
                    (RepositoryAnchor(str(project_root)),),
                )
            ]
        else:
            inventory = default_workspace_config()
            if in_repository and not inventory.is_file():
                raise ProjectConfigError(
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


def create_query_sources(
    collector: ObservationCoordinator,
    latest_rate_limit: LatestRateLimit | None = None,
) -> dict[str, QuerySource]:
    """Build the configured Query Source behind each of the dashboard's queries.

    ``latest_rate_limit`` is the reading they share, given when the dashboard
    shows it too. With no Project resolved there is nothing to query: each
    query is an ``UnresolvedQuerySource``, and the dashboard opens with the
    anchor Diagnostics that say why.
    """
    if not collector.projects:
        return {key: UnresolvedQuerySource() for key in QUERY_SOURCE_KEYS}
    root = Path(collector.projects[0].primary_anchor)
    # The rate limit is the account's: every source records into one
    # reading, so each reports the most recent any of them received.
    latest_rate_limit = latest_rate_limit or LatestRateLimit()
    return {
        key: configured_query_source(
            root, timeout=collector.timeout, latest_rate_limit=latest_rate_limit
        )
        for key in QUERY_SOURCE_KEYS
    }
