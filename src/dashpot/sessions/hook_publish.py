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
from ..core.worktree_paths import same_path
from .hook_records import (
    HookRecordStore,
    build_hook_record,
    is_child_record,
    project_session_store,
    state_directory,
)
from .hook_scan import (
    StoredSessionRecord,
    freshest_stored_record,
    reachable_hook_stores,
    stored_session_records,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .work_reconciliation import (
    carry_live_session_work,
    complete_session_work_relocation,
    continue_session_work,
    end_session_work,
    event_worktrees,
    hook_store_at,
    remove_ended_session_records,
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
    """Publish one hook event and reconcile its session's Agent Run.

    A Sub-agent's event is written to the store that holds its parent's
    freshest record, with that record's location, and reconciles nothing: it
    changes only the parent's live sub-agents (ADR 0067). ``SessionEnd`` first
    continues an orphaned run the session holds here (ADR 0075), then ends the
    session's run before its record is removed, and removes its older records
    elsewhere in the Repository. Any other event is reconciled by at
    most one route, in order: a declared relocation's completion (ADR 0029),
    a Live Relocation (ADR 0067), or an orphan continuation (ADR 0053).
    ``directory``, when given, is the one store every record is written to.
    """
    identity = process
    process_unobservable: str | None = None
    if identity is None:
        ancestry = observe_agent_ancestry(lookup, harness=harness)
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
    child = is_child_record(record)
    worktrees = event_worktrees(record)
    freshest = _freshest_elsewhere(record, worktrees, directory)
    if directory is not None:
        store = HookRecordStore(directory)
    elif child and freshest is not None:
        # The parent's freshest record routes its Sub-agent's event.
        store = hook_store_at(freshest.store, worktrees)
    else:
        store = route_record_store(record)
    ending = state == "ended" and not child
    ended: list[tuple[Path, ActiveWork]] = []
    if ending:
        # A replaced Claude Code worker can end before any other hook of its
        # new Host Process reaches the Worktree holding its orphaned run, so
        # the end continues that run first and then ends it (ADR 0075).
        continue_session_work(record, identity, lookup)
        # Reconcile the Work Store before removing the old location evidence.
        # A target hook therefore either sees the old client and waits, or
        # sees that SessionEnd has already preserved the pending run.
        ended = end_session_work(record, identity, worktrees=worktrees)
    seed = (
        None
        if child or freshest is None or same_path(freshest.store, store.directory)
        else freshest.raw
    )
    destination = store.write(record, seed=seed)
    if ending:
        remove_ended_session_records(
            record,
            identity,
            worktrees=worktrees,
            written=destination.parent,
            global_store=directory,
        )
        work: WorkStoreChange = "ended" if ended else "unchanged"
        changed = ended[0][1] if ended else None
        return HookPublication(
            destination,
            state=state,
            work=work,
            issue_id=None if changed is None else changed.issue_id,
        )
    if child:
        return HookPublication(destination, state=state)
    relocated = complete_session_work_relocation(
        record, identity, lookup, directory=destination.parent, worktrees=worktrees
    )
    carried = (
        None
        if relocated is not None
        else carry_live_session_work(
            record,
            event,
            identity,
            worktrees=worktrees,
            written=destination.parent,
            global_store=directory,
        )
    )
    moved = relocated if relocated is not None else carried
    # One event takes at most one route: a run that moved has continued.
    continued = (
        continue_session_work(record, identity, lookup) if moved is None else None
    )
    if moved is not None:
        work, changed = "relocated", moved
    elif continued is not None:
        work, changed = "continued", continued
    else:
        work, changed = "unchanged", None
    return HookPublication(
        destination,
        continued,
        state=state,
        work=work,
        issue_id=None if changed is None else changed.issue_id,
    )


def _freshest_elsewhere(
    record: dict[str, Any], worktrees: list[Path], directory: Path | None
) -> StoredSessionRecord | None:
    """The session's freshest readable record across the stores it could be in.

    Those are the stores of its Repository's Worktrees and the global one (or
    ``directory``); no process is probed. It routes a Sub-agent's event and
    seeds a session-scoped event that moves the session to another store.
    """
    records, _unreadable = stored_session_records(
        reachable_hook_stores(worktrees, directory),
        cast("Harness", record["harness"]),
        str(record["sessionId"]),
    )
    return freshest_stored_record(
        item for item in records if item.record.state != "ended"
    )
