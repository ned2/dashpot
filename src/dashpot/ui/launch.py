"""Assemble the dashboard around one collector and run it until it closes."""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..core.event_log import EventLog
from ..github.github import LatestRateLimit
from ..observation.collect import ObservationScheduler
from ..queries.pages import QuerySource
from ..repository.cleanup import GitCleanupAdapter
from ..repository.fetch import remote_fetcher
from ..repository.worktree_launcher import configure_worktree_launcher
from .app import DashpotApp
from .attendance import Attendance, tmux_attachment


def run_dashboard(
    collector: ObservationScheduler,
    sources: Mapping[str, QuerySource],
    *,
    rate_limit: LatestRateLimit,
    refresh_seconds: float,
    query_refresh_seconds: float,
    unattended_seconds: float | None,
    timeout: float,
    event_log: EventLog | None,
) -> int:
    """Open the dashboard on ``collector`` and return the status its run ends with.

    ``rate_limit`` is the reading the Query Sources share, which Runtime
    Stats shows. ``unattended_seconds`` is how long without a key or mouse
    event pauses the automatic GitHub refreshes, or ``None`` when no Query
    Source reads GitHub and nothing needs pausing.
    """
    # Inside tmux, a detached session also shows nobody watching.
    attendance = (
        Attendance(
            idle_seconds=unattended_seconds,
            probe=tmux_attachment(os.environ, timeout),
        )
        if unattended_seconds is not None
        else None
    )
    dashboard = DashpotApp(
        collector,
        sources=sources,
        event_log=event_log,
        rate_limit=rate_limit,
        attendance=attendance,
        refresh_seconds=refresh_seconds,
        query_refresh_seconds=query_refresh_seconds,
        fetcher=remote_fetcher(timeout),
        cleaner=GitCleanupAdapter(timeout),
        launcher_configuration=configure_worktree_launcher(timeout),
    )
    dashboard.run()
    # Textual prints the traceback of a handler that raised and returns
    # from ``run`` with return code 1 rather than raising, so the crash
    # reaches the shell and ``process.end`` only through this status.
    return dashboard.return_code or 0
