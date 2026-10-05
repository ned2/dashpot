"""Open the Event Log of one Dashpot process, where and at the level it belongs.

A process writes to ``.dashpot/state/events/`` in the configured checkout
containing its working directory — the rule hook records are routed by —
and anything else writes to the machine-local fallback (ADR 0059). The
level is ``DASHPOT_EVENT_LEVEL``, else the ``event_level`` setting, else
``standard``; a settings file that fails to load leaves the default without
a word, since a hook or command must never fail over its own record.
"""

from __future__ import annotations

import os
from pathlib import Path

from .core.distribution import process_start
from .core.errors import failure_text
from .core.event_log import (
    DASHBOARD_KIND,
    DASHBOARD_RECENT_EVENTS,
    DASHBOARD_RECENT_WINDOW,
    EVENTS_DIRECTORY,
    EventLog,
    EventLogDestination,
    new_run_id,
)
from .core.event_log_files import EventLogError
from .core.model import Harness
from .core.runtime_events import (
    EVENT_LEVELS,
    EventLevel,
    ProcessIdentity,
    fitting,
)
from .core.state_paths import (
    configured_checkout,
    machine_state_directory,
    project_state_directory,
)
from .project.settings import SettingsError, load_settings

LEVEL_VARIABLE = "DASHPOT_EVENT_LEVEL"
DEFAULT_LEVEL: EventLevel = "standard"


def event_level(settings_path: Path | None = None) -> EventLevel:
    """The level in force: the environment's, else the setting's, else ``standard``.

    An unrecognised environment value is ignored rather than refused. The
    settings file is not read when the environment decides.
    """
    override = os.environ.get(LEVEL_VARIABLE, "").strip().lower()
    for level in EVENT_LEVELS:
        if override == level:
            return level
    try:
        settings = load_settings(settings_path)
    except (SettingsError, RuntimeError):
        # ``RuntimeError``: no home directory to find the settings under.
        return DEFAULT_LEVEL
    return settings.event_level or DEFAULT_LEVEL


def route_event_log(working_directory: Path | None) -> EventLogDestination | None:
    """The Event Log of the configured checkout containing ``working_directory``, else the fallback.

    The directory is resolved first, as Git reports a checkout's root. One
    that is gone, or cannot be searched, has no configured checkout: a hook
    or command never loses its record over where it ran. With no home
    directory to hold the fallback there is nowhere to write: ``None``.
    """
    try:
        checkout = (
            None
            if working_directory is None
            else configured_checkout(working_directory.resolve())
        )
    except (OSError, RuntimeError):
        checkout = None
    if checkout is not None:
        return _checkout_event_log(checkout)
    try:
        return _fallback_event_log()
    except RuntimeError:
        return None


def owned_event_log(working_directory: Path) -> EventLogDestination:
    """The Event Log a command run in ``working_directory`` acts on, found strictly.

    The configured checkout containing the directory owns it, and only a
    directory positively outside every configured checkout acts on the
    machine-local fallback. Unlike ``route_event_log``, a search that fails
    is refused rather than taken for "outside", since a mutating command
    must act only on the log it names (ADR 0008).
    """
    try:
        checkout = configured_checkout(working_directory.resolve())
    except (OSError, RuntimeError) as exc:
        # ``RuntimeError``: a symlink loop under ``resolve`` on Python 3.12.
        raise EventLogError(
            f"cannot tell which checkout's Event Log {working_directory} "
            f"belongs to: {failure_text(exc)}"
        ) from exc
    if checkout is not None:
        return _checkout_event_log(checkout)
    try:
        return _fallback_event_log()
    except RuntimeError as exc:
        raise EventLogError(
            "no Event Log for this directory: no configured checkout encloses "
            "this directory and there is no home directory for the "
            "machine-local one"
        ) from exc


def _checkout_event_log(checkout: Path) -> EventLogDestination:
    return EventLogDestination(
        project_state_directory(checkout) / EVENTS_DIRECTORY, checkout=checkout
    )


def _fallback_event_log() -> EventLogDestination:
    """The machine-local fallback; ``RuntimeError`` when there is no home directory."""
    return EventLogDestination(machine_state_directory() / EVENTS_DIRECTORY)


def process_identity(
    kind: str,
    *,
    worktree: Path | None = None,
    harness: Harness | None = None,
    session_id: str | None = None,
) -> ProcessIdentity:
    """Name this process by a new run ID, keeping only what fits its field."""
    return fitting(
        ProcessIdentity,
        {"run_id": new_run_id(), "kind": kind},
        {
            "worktree": None if worktree is None else str(worktree),
            "harness": harness,
            "session_id": session_id,
        },
    )


def open_event_log(
    kind: str,
    *,
    working_directory: Path | None,
    destination: EventLogDestination | None = None,
    subcommand: str | None = None,
    harness: Harness | None = None,
    session_id: str | None = None,
    settings_path: Path | None = None,
) -> EventLog:
    """Open one process's Event Log, routed from its working directory unless given.

    A dashboard also keeps its recent events in memory and records whether
    Dashpot's own source has uncommitted changes.
    """
    target = (
        destination if destination is not None else route_event_log(working_directory)
    )
    dashboard = kind == DASHBOARD_KIND
    return EventLog(
        target,
        identity=process_identity(
            kind,
            worktree=None if target is None else target.checkout,
            harness=harness,
            session_id=session_id,
        ),
        level=event_level(settings_path),
        facts=lambda: process_start(
            working_directory, subcommand=subcommand, check_source=dashboard
        ),
        keep_recent=DASHBOARD_RECENT_EVENTS if dashboard else 0,
        recent_window=DASHBOARD_RECENT_WINDOW if dashboard else None,
    )
