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

from pydantic import ValidationError

from .core.distribution import process_start
from .core.event_log import (
    DASHBOARD_KIND,
    DASHBOARD_RECENT_EVENTS,
    EVENTS_DIRECTORY,
    EventLog,
    EventLogDestination,
    new_run_id,
)
from .core.model import Harness
from .core.project_state import project_state_directory
from .core.runtime_events import (
    EVENT_LEVELS,
    EventLevel,
    ProcessIdentity,
)
from .core.state_paths import configured_checkout, machine_state_directory
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
    that is gone, or cannot be searched, has no configured checkout. With no
    home directory to hold the fallback there is nowhere to write: ``None``.
    """
    try:
        checkout = (
            None
            if working_directory is None
            else configured_checkout(working_directory.resolve())
        )
    except (OSError, RuntimeError):
        checkout = None
    if checkout is None:
        try:
            return EventLogDestination(machine_state_directory() / EVENTS_DIRECTORY)
        except RuntimeError:
            return None
    return EventLogDestination(
        project_state_directory(checkout) / EVENTS_DIRECTORY, checkout=checkout
    )


def process_identity(
    kind: str,
    *,
    worktree: Path | None = None,
    harness: Harness | None = None,
    session_id: str | None = None,
) -> ProcessIdentity:
    """Name this process by a new run ID, keeping only what fits its field."""
    identity: dict[str, object] = {"run_id": new_run_id(), "kind": kind}
    for field, value in (
        ("worktree", None if worktree is None else str(worktree)),
        ("harness", harness),
        ("session_id", session_id),
    ):
        if value is None:
            continue
        try:
            ProcessIdentity.model_validate({**identity, field: value})
        except ValidationError:
            continue
        identity[field] = value
    return ProcessIdentity.model_validate(identity)


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
    )
