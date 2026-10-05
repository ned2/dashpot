"""The default command: open the dashboard, or print a headless snapshot.

Textual and the dashboard load only when the dashboard opens, so every
other command, and a snapshot, runs without them.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter, Token, validators

from ..composition import (
    ObservationOptions,
    create_collector,
    create_query_sources,
    reads_github,
    refresh_periods,
)
from ..core.working_directory import current_directory
from ..github.github import LatestRateLimit
from ..project.workspace import RepositoryAnchor, Workspace
from ..serialization import render_json, snapshot_document
from .shared import EVENT_LOG, Timeout


def parse_workspace_argument(value: str) -> Workspace:
    """Read one ``[NAME=]PATH`` token as a single-anchor Workspace."""
    named, raw_root = value.split("=", 1) if "=" in value else ("", value)
    if not raw_root.strip():
        raise ValueError("workspace must be PATH or NAME=PATH")
    given = Path(raw_root).expanduser()
    # Only a relative path needs the working directory, which may be gone.
    root = (given if given.is_absolute() else current_directory() / given).resolve()
    name = named if "=" in value else root.name
    if not name.strip():
        raise ValueError("workspace must be PATH or NAME=PATH")
    return Workspace(name.strip(), (RepositoryAnchor(str(root)),))


def _convert_workspaces(type_: object, tokens: Sequence[Token]) -> list[Workspace]:
    # Cyclopts hands a list-typed option every repeated token in one call and
    # expects the whole list back; a ValueError here becomes the usage error.
    return [parse_workspace_argument(token.value) for token in tokens]


def _finite_seconds(_type: object, value: float | None) -> None:
    """Refuse a Refresh Period that never elapses."""
    if value is not None and not math.isfinite(value):
        raise ValueError("Must be a finite number of seconds.")


def observe(
    *,
    workspace: Annotated[
        list[Workspace] | None,
        Parameter(
            converter=_convert_workspaces,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "[NAME=]PATH: repository anchor in a named Workspace "
                "(repeatable); defaults to the Dashpot workspace config"
            ),
        ),
    ] = None,
    config: Annotated[
        Path | None,
        Parameter(
            help=(
                "Dashpot workspace config; by default, observe the configured "
                "current project or fall back to the standard workspace config"
            )
        ),
    ] = None,
    timeout: Timeout = 10.0,
    refresh_seconds: Annotated[
        float | None,
        Parameter(
            validator=(validators.Number(gte=0), _finite_seconds),
            help=(
                "seconds between automatic refreshes of Worktrees, Branches and "
                "Agent Sessions, and of a Local Markdown Issue Source; zero "
                "disables them (default: the refresh_seconds setting, else 15)"
            ),
        ),
    ] = None,
    github_refresh_seconds: Annotated[
        float | None,
        Parameter(
            validator=(validators.Number(gte=0), _finite_seconds),
            help=(
                "seconds between automatic refreshes of GitHub Issues and pull "
                "requests; zero disables them (default: the "
                "github_refresh_seconds setting, else 60)"
            ),
        ),
    ] = None,
    unattended_seconds: Annotated[
        float | None,
        Parameter(
            validator=(validators.Number(gte=0), _finite_seconds),
            help=(
                "seconds without a key or mouse event before automatic GitHub "
                "refreshes pause until the next one; zero disables that pause "
                "(default: the unattended_seconds setting, else 7200)"
            ),
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        Parameter(
            help=(
                "override the directory for agent session records outside "
                "configured Projects"
            )
        ),
    ] = None,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            show_default=False,
            help="collect once and print the headless snapshot instead of opening the TUI",
        ),
    ] = False,
    compact_json: Annotated[
        bool,
        Parameter(show_default=False, help="omit JSON indentation (implies --json)"),
    ] = False,
) -> int:
    """Open the TUI for one Project, or print a headless snapshot."""
    headless = json_output or compact_json
    periods = refresh_periods(
        refresh_seconds, github_refresh_seconds, unattended_seconds
    )
    collector = create_collector(
        ObservationOptions(
            workspaces=tuple(workspace or ()),
            config=config,
            timeout=timeout,
            refresh_seconds=periods.local,
            state_dir=state_dir,
        ),
        recurring=not headless,
    )
    if headless:
        # The coordinated barrier publishes every observation and then
        # checkpoints, so headless output stays a single complete snapshot.
        print(render_json(snapshot_document(collector.refresh()), compact=compact_json))
        return 0
    # Imported here because importing it loads Textual.
    from ..ui.launch import run_dashboard

    # Runtime Stats shows the reading the Query Sources share.
    latest_rate_limit = LatestRateLimit()
    sources = create_query_sources(collector, latest_rate_limit)
    return run_dashboard(
        collector,
        sources,
        rate_limit=latest_rate_limit,
        refresh_seconds=periods.local,
        query_refresh_seconds=periods.query_seconds(sources),
        # Only GitHub refreshes spend anything while nobody watches.
        unattended_seconds=periods.unattended if reads_github(sources) else None,
        timeout=timeout,
        event_log=EVENT_LOG.get(),
    )
