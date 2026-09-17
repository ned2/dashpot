"""Publish hook events to their Agent Session record stores."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.json_records import optional_string
from ..core.model import Harness
from .hook_records import (
    build_hook_record,
    session_directory,
    state_directory,
    write_hook_record,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .work_reconciliation import (
    complete_session_work_relocation,
    end_session_work,
)


def route_record_directory(record: Mapping[str, Any]) -> Path:
    """Choose the Project-local store for a configured checkout, else global."""
    root = optional_string(record.get("repositoryRoot"))
    if root and (Path(root) / ".dashpot" / "config.json").is_file():
        return session_directory(Path(root))
    return state_directory()


def publish_hook_event(
    event: dict[str, Any],
    directory: Path | None = None,
    process: ProcessIdentity | None = None,
    harness: Harness = "codex",
    lookup: ProcessLookup = host_process_lookup,
) -> Path:
    identity = process
    process_unobservable: str | None = None
    if identity is None:
        ancestry = observe_agent_ancestry(harness=harness)
        identity = None if ancestry.located is None else ancestry.located[1]
        process_unobservable = ancestry.unobservable_reason
    record = build_hook_record(
        event,
        process=identity,
        harness=harness,
        process_unobservable=process_unobservable,
    )
    if record.get("state") == "ended":
        # Reconcile the Work Store before removing the old location evidence.
        # A target hook therefore either sees the old client and waits, or
        # sees that SessionEnd has already preserved the pending run.
        end_session_work(record, identity)
    destination = write_hook_record(record, directory or route_record_directory(record))
    if record.get("state") != "ended":
        complete_session_work_relocation(
            record, identity, lookup, directory=destination.parent
        )
    return destination
