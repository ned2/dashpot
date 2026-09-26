"""Publish hook events to their Agent Session record stores."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..core.json_records import optional_string
from ..core.model import Harness
from ..core.runtime_events import HookRecordState, WorkStoreChange
from ..core.state_paths import is_configured_checkout
from .hook_records import (
    HookRecordStore,
    build_hook_record,
    project_session_store,
    state_directory,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .work_reconciliation import (
    complete_session_work_relocation,
    continue_session_work,
    end_session_work,
)
from .work_store import ActiveWork


@dataclass(frozen=True, slots=True)
class HookPublication:
    """Where one hook event was published, and what it did to its session's Agent Run.

    ``state`` is what the record says the session is doing; ``work`` names
    the Work Store change, with the Issue of the run it changed.
    """

    path: Path
    continued: ActiveWork | None = None
    state: HookRecordState | None = None
    work: WorkStoreChange = "unchanged"
    issue_id: str | None = None


def route_record_store(record: Mapping[str, Any]) -> HookRecordStore:
    """Choose the Project-local store for a configured checkout, else global."""
    root = optional_string(record.get("repositoryRoot"))
    if root and is_configured_checkout(Path(root)):
        return project_session_store(Path(root))
    return HookRecordStore(state_directory())


def publish_hook_event(
    event: dict[str, Any],
    directory: Path | None = None,
    process: ProcessIdentity | None = None,
    harness: Harness = "codex",
    lookup: ProcessLookup = host_process_lookup,
) -> HookPublication:
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
    # A built record always names the state its hook event maps to.
    state = cast("HookRecordState", record["state"])
    ended: list[tuple[Path, ActiveWork]] = []
    if state == "ended":
        # Reconcile the Work Store before removing the old location evidence.
        # A target hook therefore either sees the old client and waits, or
        # sees that SessionEnd has already preserved the pending run.
        ended = end_session_work(record, identity)
    store = (
        HookRecordStore(directory)
        if directory is not None
        else route_record_store(record)
    )
    destination = store.write(record)
    if state == "ended":
        if not ended:
            return HookPublication(destination, state=state)
        return HookPublication(
            destination, state=state, work="ended", issue_id=ended[0][1].issue_id
        )
    relocated = complete_session_work_relocation(
        record, identity, lookup, directory=destination.parent
    )
    continued = continue_session_work(record, identity, lookup)
    # A relocation completed here continues the run too; the move is the
    # change worth naming.
    if relocated is not None:
        return HookPublication(
            destination,
            continued,
            state=state,
            work="relocated",
            issue_id=relocated.issue_id,
        )
    if continued is not None:
        return HookPublication(
            destination,
            continued,
            state=state,
            work="continued",
            issue_id=continued.issue_id,
        )
    return HookPublication(destination, state=state)
