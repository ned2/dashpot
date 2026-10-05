"""Publish hook events to their Agent Session record stores."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..core.json_records import optional_string
from ..core.model import Harness
from ..core.runtime_events import HookRecordState, WorkStoreChange
from ..core.state_paths import is_configured_checkout
from ..core.worktree_paths import same_path
from .deferred_end import (
    DeferredEnd,
    Settler,
    defers_session_end,
    pending_session_end,
    spawn_settler,
)
from .hook_records import (
    HookRecordStore,
    build_hook_record,
    hosts_subagent,
    is_child_record,
    project_session_store,
    session_start_kind,
    state_directory,
    subagent_host_processes,
    subagents_hosted_by,
    switched_from,
)
from .hook_scan import (
    StoredSessionRecord,
    freshest_stored_record,
    reachable_hook_stores,
    stored_process_records,
    stored_session_records,
)
from .liveness import session_liveness
from .processes import (
    ProcessIdentity,
    ProcessKey,
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

    ``state`` is the state the session's record was stored with, which may
    differ from the one the hook event maps to, and None when the store kept
    nothing of the event; a deferred end's settler reports ``ended`` without
    writing a record. ``work`` names the Work Store change, with the Issue of
    the run it changed.
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
    settle: Settler = spawn_settler,
    moved_from: Path | None = None,
) -> HookPublication:
    """Publish one hook event and reconcile its session's Agent Run.

    A Sub-agent's event is written to the store that holds its parent's
    freshest record, with that record's location, and reconciles nothing: it
    changes only the parent's live sub-agents (ADR 0067); a stop also leaves
    every ended record of its Host Process that kept it (ADR 0095, ADR 0101),
    and every live record its session left behind at another Worktree
    (ADR 0102). A Conversation Switch's ``SessionStart`` takes over the
    sub-agents of the session its Host Process switched from, which stop
    listing them once the new record does (ADR 0101). ``SessionEnd`` first
    continues an orphaned run the session holds here (ADR 0075), then ends the
    session's run before its record is removed, and removes its older records
    elsewhere in the Repository; a ``SessionEnd`` from a managed Codex daemon
    instead leaves its runs to a settler ``settle`` starts once the record is
    written, which ends them only if the daemon keeps running (ADR 0086).
    Any other event is reconciled by at
    most one route, in order: a declared relocation's completion (ADR 0029),
    a Live Relocation (ADR 0067), or an orphan continuation (ADR 0053).
    ``directory``, when given, is the one store every record is written to.
    ``moved_from``, when given, is the store of another Project that the
    session's move left: its records are read beside the session's own, so
    they seed this one with the sub-agents the event's Host Process runs,
    and once this record lists those they stop listing them (ADR 0109).
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
    child = is_child_record(record)
    worktrees = event_worktrees(record)
    session_records = _session_records(record, worktrees, directory, moved_from)
    freshest = _freshest_elsewhere(session_records, child=child)
    if directory is not None:
        store = HookRecordStore(directory)
    elif child and freshest is not None:
        # The parent's freshest record routes its Sub-agent's event.
        store = hook_store_at(freshest.store, worktrees)
    else:
        store = route_record_store(record)
    # The state the hook event maps to decides whether this is an end that
    # reconciles the Work Store; the publication reports the stored state.
    ending = record["state"] == "ended" and not child
    # The runs this end ended, or left to a settler when it is ``deferred``.
    reconciled: list[tuple[Path, ActiveWork]] = []
    deferred: DeferredEnd | None = None
    if ending:
        # A replaced Claude Code worker can end before any other hook of its
        # new Host Process reaches the Worktree holding its orphaned run, so
        # the end continues that run first and then ends it (ADR 0075).
        continue_session_work(record, identity, lookup)
        if identity is not None and defers_session_end(record, identity):
            # A managed daemon ends a thread the same way when it unloads it
            # and when it is stopped or restarted, and waits for this hook
            # before it exits; only a settler outliving the hook can tell.
            pending = pending_session_end(record, identity, worktrees=worktrees)
            if pending is not None:
                deferred, reconciled = pending
        else:
            # Reconcile the Work Store before removing the old location
            # evidence. A target hook therefore either sees the old client
            # and waits, or sees that SessionEnd has already preserved the
            # pending run.
            reconciled = end_session_work(record, identity, worktrees=worktrees)
    seed = (
        None
        if child or freshest is None or same_path(freshest.store, store.directory)
        else freshest.raw
    )
    if (
        seed is not None
        and freshest is not None
        and moved_from is not None
        and same_path(freshest.store, moved_from)
    ):
        seed = _own_listing(seed, record.get("sessionProcess"))
    switched = _records_switched_from(record, identity, worktrees, directory)
    adopted = sorted(
        {
            agent
            for item in switched
            for agent in subagents_hosted_by(item.raw, record.get("sessionProcess"))
        }
    )
    written = store.write(
        record,
        seed=seed,
        adopted=adopted,
        gone_hosts=_gone_hosts(session_records, identity, lookup),
    )
    destination, state = written.path, written.state
    # Released only once the new record lists them: a publisher that fails
    # between the two writes leaves them listed twice, which errs toward
    # blocking Cleanup rather than toward forgetting a working sub-agent.
    for item in switched:
        HookRecordStore(item.store).release_subagents(
            item.path.stem, adopted, record, session_id=item.record.session_id
        )
    if moved_from is not None:
        _release_moved_from(record, moved_from, session_records, destination)
    if ending:
        remove_ended_session_records(
            record,
            identity,
            worktrees=worktrees,
            written=destination.parent,
            global_store=directory,
        )
        if deferred is not None:
            # Started last, so a settler that cannot start leaves the runs
            # as they are, recoverable as orphans, and fails only the hook.
            settle(deferred)
        work: WorkStoreChange = (
            "deferred"
            if deferred is not None
            else "ended"
            if reconciled
            else "unchanged"
        )
        changed = reconciled[0][1] if reconciled else None
        return HookPublication(
            destination,
            state=state,
            work=work,
            issue_id=None if changed is None else changed.issue_id,
        )
    if child:
        if record.get("event") == "SubagentStop":
            _stop_kept_elsewhere(
                record,
                identity,
                worktrees,
                directory,
                written_to=destination,
                session_records=session_records,
            )
        return HookPublication(destination, state=state)
    relocated = complete_session_work_relocation(
        record, identity, lookup, global_store=directory, worktrees=worktrees
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


def _gone_hosts(
    records: Iterable[StoredSessionRecord],
    identity: ProcessIdentity | None,
    lookup: ProcessLookup,
) -> frozenset[ProcessKey]:
    """The Host Processes besides the event's that run a listed sub-agent and are gone.

    A sub-agent stays listed while the process running it lives, even when
    another process takes its session on (ADR 0107). Probed here, before the
    store takes its locks, so only a process proved gone is named: one a
    record names after this read is not probed, and its sub-agents carry
    until the next write probes it. A session of one Host Process probes
    nothing.
    """
    own = None if identity is None else identity.key
    hosts = {
        key: host
        for item in records
        for key, host in subagent_host_processes(item.raw).items()
        if key != own
    }
    return frozenset(
        key
        for key, host in hosts.items()
        if session_liveness(key, lookup, namespace=host.pid_namespace).liveness
        == "gone"
    )


def _stop_kept_elsewhere(
    record: dict[str, Any],
    identity: ProcessIdentity | None,
    worktrees: list[Path],
    directory: Path | None,
    written_to: Path,
    session_records: Iterable[StoredSessionRecord],
) -> None:
    """Remove a stopped Sub-agent from the other records of its Host Process that keep it.

    Those are the process's ended records and the records the stop's own
    session left behind.

    A session that ended at one Worktree and started again at another routes
    its Sub-agents' events to its live record there, while the record its
    end kept at the first still lists them (ADR 0095). A Claude Code
    Conversation Switch moves a working sub-agent to another session of the
    same process, so the stop may name a session other than the one whose
    ended record kept it (ADR 0101): an agent id names one sub-agent, so its
    stop clears it from every ended record of the process. A session that
    moved to another Worktree carried its sub-agents to the record there,
    and the record it left behind lists them too, so the stop clears it from
    the session's own live records as well (ADR 0102); another live
    session's records are left as they are. A record of the stop's own
    session that names another Host Process lists the sub-agent under its
    own process's tag, and lets it go too (ADR 0107). The record the stop
    was written to is skipped: a start of the same agent may already have
    listed it there again. Each store re-reads its record under its lock.
    """
    agent = record.get("agentId")
    if identity is None or not isinstance(agent, str):
        return
    candidates = {
        item.path: item
        for item in _process_records(record, identity, worktrees, directory)
    }
    for item in session_records:
        if hosts_subagent(item.raw, agent, record.get("sessionProcess")):
            candidates.setdefault(item.path, item)
    for item in candidates.values():
        if agent not in item.record.live_subagents or same_path(item.path, written_to):
            continue
        store = HookRecordStore(item.store)
        if item.record.state == "ended":
            store.release_subagents(
                item.path.stem, [agent], record, session_id=item.record.session_id
            )
        elif item.record.session_id == record.get("sessionId"):
            store.release_left_behind(item.path.stem, [agent], record)


def _records_switched_from(
    record: dict[str, Any],
    identity: ProcessIdentity | None,
    worktrees: list[Path],
    directory: Path | None,
) -> list[StoredSessionRecord]:
    """The ended records of the sessions a Conversation Switch's Host Process left.

    Claude Code's ``/clear``, ``/resume`` and ``/branch`` end one session and
    start another in the same process, and the sub-agents the first left
    working go on under the second (ADR 0101). Read from every store the
    session could be in, without probing a process; none for any other event.
    """
    if identity is None or session_start_kind(record) != "switch":
        return []
    return [
        item
        for item in _process_records(record, identity, worktrees, directory)
        if item.record.live_subagents and switched_from(record, item.raw)
    ]


def _process_records(
    record: dict[str, Any],
    identity: ProcessIdentity,
    worktrees: list[Path],
    directory: Path | None,
) -> list[StoredSessionRecord]:
    """Every record of ``record``'s harness and Host Process the session could reach."""
    return stored_process_records(
        reachable_hook_stores(worktrees, directory),
        cast("Harness", record["harness"]),
        identity.key,
    )


def _session_records(
    record: dict[str, Any],
    worktrees: list[Path],
    directory: Path | None,
    moved_from: Path | None,
) -> list[StoredSessionRecord]:
    """The session's readable records across the stores it could be in.

    Those are the stores of its Repository's Worktrees and the global one (or
    ``directory``), and the store of another Project its move left
    (``moved_from``); no process is probed.
    """
    stores = reachable_hook_stores(worktrees, directory)
    if moved_from is not None and not any(
        same_path(store, moved_from) for store in stores
    ):
        stores.append(moved_from)
    records, _unreadable = stored_session_records(
        stores,
        cast("Harness", record["harness"]),
        str(record["sessionId"]),
    )
    return records


def _own_listing(seed: Mapping[str, Any], process: object) -> dict[str, Any]:
    """``seed`` listing only the sub-agents the Host Process ``process`` names runs.

    A move to another Project takes along only the moving process's own
    sub-agents: another process's plugin never sees the move, so its
    sub-agents' events go on reaching the record left behind, and one listed
    in the new Project too would block there with no stop to clear it
    (ADR 0109).
    """
    own = {
        **seed,
        "liveSubagents": subagents_hosted_by(seed, process),
    }
    own.pop("subagentProcesses", None)
    return own


def _release_moved_from(
    record: dict[str, Any],
    moved_from: Path,
    session_records: Iterable[StoredSessionRecord],
    written_to: Path,
) -> None:
    """Stop listing, in the records a move to another Project left, the sub-agents this record took.

    A session moved to another Project carries its sub-agents to the record
    it begins there, seeded from the record it left (ADR 0109). The Project
    it left is out of reach of their later stops, which reach only the
    stores of the Repository the session is in now (ADR 0102), so the
    records left there let them go at once, as a Conversation Switch's do
    (ADR 0101). Only the agents the written record lists leave, and only
    those listed as run by its Host Process: ``release_left_behind`` re-reads
    each record under its lock and changes only its list.
    """
    written, _unreadable = stored_session_records(
        [written_to.parent],
        cast("Harness", record["harness"]),
        str(record["sessionId"]),
    )
    listed = {
        agent
        for item in written
        if same_path(item.path, written_to)
        for agent in item.record.live_subagents
    }
    for item in session_records:
        if not same_path(item.store, moved_from) or same_path(item.path, written_to):
            continue
        taken = [agent for agent in item.record.live_subagents if agent in listed]
        if taken:
            HookRecordStore(item.store).release_left_behind(
                item.path.stem, taken, record
            )


def _freshest_elsewhere(
    records: Iterable[StoredSessionRecord], *, child: bool
) -> StoredSessionRecord | None:
    """The session's freshest record of ``records``, the session's across its stores.

    It routes a Sub-agent's event and seeds a session-scoped event that
    moves the session to another store. An ended record seeds nothing, but
    one kept for the sub-agents its session left working routes their
    events to it (ADR 0095).
    """
    return freshest_stored_record(
        item
        for item in records
        if item.record.state != "ended" or (child and item.record.live_subagents)
    )
