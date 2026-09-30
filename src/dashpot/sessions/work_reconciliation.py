"""Reconcile Agent Runs from published hook events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..core.git import GitError
from ..core.json_records import optional_string, require_harness, require_string
from ..core.record_store import RecordKeyError
from ..core.timestamps import observed_instant
from ..core.worktree_paths import repository_worktrees, same_path
from .harnesses import HookEvent, adapter, locates_session
from .hook_records import HookRecordStore, session_directory
from .hook_scan import (
    StoredSessionRecord,
    freshest_stored_record,
    reachable_hook_stores,
    scan_hook_stores,
    session_record_named,
    stored_session_records,
)
from .liveness import LivenessProbe, session_liveness
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
)
from .session_labels import work_session_label
from .session_matching import SessionEvidence
from .work_store import (
    ActiveWork,
    SessionProcess,
    WorkStore,
    end_session_runs,
)


def event_worktrees(record: Mapping[str, Any]) -> list[Path]:
    """Every Worktree of the Repository a hook record places its session in.

    A record outside any Repository, or one whose Repository Git cannot list
    now, has none: the hook is never failed for it.
    """
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return []
    try:
        return repository_worktrees(Path(root), timeout=2)
    except (GitError, OSError):
        return []


def hook_store_at(store: Path, worktrees: Sequence[Path]) -> HookRecordStore:
    """The hook store at ``store``, naming the Worktree whose Project-local state it is.

    Locking a Worktree's hook store may create its state directory, and the
    named checkout keeps that state out of Git.
    """
    owners = {session_directory(worktree).resolve(): worktree for worktree in worktrees}
    return HookRecordStore(store, checkout=owners.get(store.resolve()))


def end_session_work(
    record: Mapping[str, Any],
    process: ProcessIdentity | None,
    *,
    worktrees: Sequence[Path],
) -> list[tuple[Path, ActiveWork]]:
    """Reconcile the Agent Run of a gracefully ended client session.

    An undeclared end is the session's own state, so ending its run is the
    same housekeeping as removing the hook record (ADR 0015).
    It is looked for at every Worktree of the Repository the session ended
    in, since a session holds one run across them (ADR 0009). A declared Codex
    Relocation Intent instead preserves the run for target verification (ADR
    0029); a client that ends outside any Repository has no Work Store to
    reconcile. ``worktrees`` are the Repository's (``event_worktrees``).
    """
    if not worktrees:
        return []
    return end_session_runs(
        worktrees,
        require_harness(record.get("harness")),
        require_string(record.get("sessionId"), "sessionId"),
        process.key if process else None,
        ended_at=optional_string(record.get("lastActivityAt")),
    )


def continue_session_work(
    record: Mapping[str, Any],
    process: ProcessIdentity | None,
    lookup: ProcessLookup = host_process_lookup,
) -> ActiveWork | None:
    """Carry an Orphaned Agent Run over to its session's new host process.

    A session whose process ended without ``SessionEnd`` and that publishes
    again from a new process under the same Agent Session Identity is the same
    engagement continuing, so its run keeps its identity, ``startedAt``, and
    Issue Binding (ADR 0053). That holds only where the harness runs each
    session in its own process, the recorded process is proved gone rather
    than unobservable, and the hook arrives at the Worktree holding the run.
    The replacement compares the complete record under its lock, so of two
    clients resuming together only the first continues the run. Returns the
    continued run, or ``None`` when nothing was carried over.
    """
    harness = require_harness(record.get("harness"))
    if process is None or not adapter(harness).exclusive_session_process:
        return None
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return None
    store = WorkStore(Path(root))
    # Most hooks come from a session with no run here; they stop at this
    # check rather than paying for a process probe or Git.
    if not store.directory.is_dir():
        return None
    try:
        active, _diagnostics = store.active()
    except OSError:
        return None
    session_id = require_string(record.get("sessionId"), "sessionId")
    identity = SessionEvidence(harness, session_id)
    for work in active:
        if identity.match(work.evidence) != "same" or work.relocation is not None:
            continue
        recorded = work.session_process
        if recorded is None or recorded.key == process.key:
            continue
        if session_liveness(recorded.key, lookup).liveness != "gone":
            continue
        continued = replace(
            work,
            session_label=work_session_label(harness, session_id, pid=process.pid),
            session_process=SessionProcess(
                pid=process.pid, started_at=process.started_at
            ),
        )
        try:
            if store.replace_current(work, continued):
                return continued
        except (OSError, RecordKeyError, ValueError):
            return None
    return None


def complete_session_work_relocation(
    record: Mapping[str, Any],
    process: ProcessIdentity | None,
    lookup: ProcessLookup = host_process_lookup,
    *,
    directory: Path | None = None,
    worktrees: Sequence[Path] | None = None,
) -> ActiveWork | None:
    """Complete a declared Codex relocation proved by this target hook record.

    ``worktrees`` are the Repository's, when the caller has them. Returns the
    relocated Agent Run, or ``None`` when nothing moved.
    """
    if record.get("harness") != "codex":
        return None
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return None
    try:
        target = Path(root).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if worktrees is None:
        try:
            worktrees = repository_worktrees(target, timeout=2)
        except GitError:
            return None
    # Without a Work Store there can be no Relocation Intent; locking hook
    # stores would otherwise create Project-local state in an unconfigured repo.
    if not any(WorkStore(worktree).directory.exists() for worktree in worktrees):
        return None
    session_id = require_string(record.get("sessionId"), "sessionId")
    stores = reachable_hook_stores(worktrees, directory)
    hook_stores = sorted(
        (hook_store_at(store, worktrees) for store in stores),
        key=lambda store: str(store.lock_path(session_id)),
    )
    with ExitStack() as stack:
        for store in hook_stores:
            stack.enter_context(store.locked(session_id))
        if not _sequential_target_is_confirmed(stores, session_id, target, lookup):
            return None
        matching: list[tuple[Path, WorkStore, ActiveWork]] = []
        for worktree in worktrees:
            store = WorkStore(worktree)
            try:
                active, diagnostics = store.active()
            except OSError:
                return None
            if diagnostics:
                return None
            for candidate in active:
                relation = SessionEvidence("codex", session_id).match(
                    candidate.evidence
                )
                if relation == "unresolved":
                    return None
                if relation == "same":
                    matching.append((worktree, store, candidate))
        pending_matches = [
            item
            for item in matching
            if item[2].relocation is not None
            and same_path(Path(item[2].relocation.target_worktree), target)
        ]
        if len(pending_matches) != 1:
            return None
        source_worktree, source, work = pending_matches[0]
        if any(
            not same_path(candidate_worktree, target)
            or candidate.session_key != work.session_key
            for candidate_worktree, _store, candidate in matching
            if candidate != work
        ):
            return None
        intent = work.relocation
        if intent is None:
            return None
        if not same_path(Path(intent.target_worktree), target) or same_path(
            source_worktree, target
        ):
            return None
        session_process = (
            SessionProcess(pid=process.pid, started_at=process.started_at)
            if process is not None
            else None
        )
        relocated = replace(
            work,
            session_label=work_session_label(
                "codex", session_id, pid=process.pid if process is not None else None
            ),
            session_process=session_process,
            working_directory=require_string(record.get("cwd"), "cwd"),
            branch=optional_string(record.get("branch")),
            relocation=None,
        )
        try:
            moved = source.complete_relocation(work, WorkStore(target), relocated)
        except (OSError, RecordKeyError, ValueError):
            return None
        return relocated if moved else None


def _sequential_target_is_confirmed(
    stores: Sequence[Path],
    session_id: str,
    target: Path,
    lookup: ProcessLookup,
) -> bool:
    """Whether no live or unknown same-identity client remains elsewhere."""
    unreadable = False

    def named(path: Path) -> bool:
        return session_record_named(path, session_id, "codex")

    def reject_unreadable(_path: Path, _exc: Exception) -> None:
        nonlocal unreadable
        unreadable = True

    probe = LivenessProbe(lookup)
    for scanned in scan_hook_stores(
        stores, probe, select=named, on_unreadable=reject_unreadable
    ):
        if (
            SessionEvidence("codex", session_id).match(scanned.record.evidence)
            != "same"
        ):
            continue
        location = scanned.record.worktree
        if not same_path(location, target) and scanned.record.outcome not in {
            "ended",
            "gone",
        }:
            return False
    return not unreadable


def carry_live_session_work(
    record: Mapping[str, Any],
    event: HookEvent,
    process: ProcessIdentity | None,
    *,
    worktrees: Sequence[Path],
    written: Path,
    global_store: Path | None = None,
) -> ActiveWork | None:
    """Carry an active Agent Run to the Worktree its session now executes at.

    This is a Live Relocation (ADR 0067): the session kept its Agent Session
    Identity and Host Process and continues at another Worktree of the same
    Repository with no ``SessionEnd``, ``SessionStart`` or Relocation Intent
    to say so. ``record`` is the hook record H just written to the store at
    ``written``, at Worktree B; the run moves from Worktree A with its session
    key, ``run_id``, ``startedAt`` and Issue Binding, adopting B's ``cwd``
    and Branch, only under every condition the lifecycle design numbers:

    1. the run's recorded identity is H's; an unresolved legacy run never is;
    2. H's Host Process is the run's recorded one, both observed;
    3. H's event is its harness's designated, session-scoped location evidence;
    4. B is another Worktree of A's Repository;
    5. under the session's hook-store locks, H is the identity's freshest
       record, and the freshest record outside B is at A, from the same Host
       Process, and not ended;
    6. B's store has seen no ``SessionStart`` for the session since that
       record at A (``lastSessionStartAt``), so a restart is never a move;
    7. B holds no other run for the session;
    8. a pending Relocation Intent names exactly B, and the carry completes
       and clears it.

    It never creates a run, so an unbound session stays unbound. A crash
    between writing B and removing A leaves the same run at both; the next
    carry finds that pair and removes A's copy. Returns the carried run, or
    ``None`` when nothing moved.
    """
    harness = require_harness(record.get("harness"))
    if process is None or not locates_session(harness, event):
        return None
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return None
    target = next(
        (worktree for worktree in worktrees if same_path(worktree, Path(root))), None
    )
    if target is None:
        return None
    # Most designated events come from a session with no run elsewhere; they
    # stop here rather than locking and reading every store.
    if not any(
        WorkStore(worktree).directory.is_dir()
        for worktree in worktrees
        if worktree != target
    ):
        return None
    session_id = require_string(record.get("sessionId"), "sessionId")
    # The store H was written to is one of these: the publisher routes only to
    # a reachable store.
    stores = [
        store
        for store in reachable_hook_stores(worktrees, global_store)
        if store.is_dir()
    ]
    hook_stores = sorted(
        (hook_store_at(store, worktrees) for store in stores),
        key=lambda store: str(store.lock_path(session_id)),
    )
    with ExitStack() as stack:
        for store in hook_stores:
            stack.enter_context(store.locked(session_id))
        origin = _live_origin(record, process, stores, written, target)
        if origin is None:
            return None
        return _carry_run(record, process, worktrees, target, origin)


def _live_origin(
    record: Mapping[str, Any],
    process: ProcessIdentity,
    stores: Sequence[Path],
    written: Path,
    target: Path,
) -> StoredSessionRecord | None:
    """The record at A that H follows in the same incarnation (conditions 5 and 6)."""
    harness = require_harness(record.get("harness"))
    session_id = require_string(record.get("sessionId"), "sessionId")
    records, unreadable = stored_session_records(stores, harness, session_id)
    # A record that cannot be read may be the freshest; nothing moves on it.
    if unreadable:
        return None
    stamp = observed_instant(optional_string(record.get("lastActivityAt")))
    here = next((item for item in records if same_path(item.store, written)), None)
    # H must still be what the store holds: a later event decides for itself.
    if here is None or here.last_activity != stamp:
        return None
    if any(item.last_activity > stamp for item in records):
        return None
    origin = freshest_stored_record(
        item for item in records if not same_path(item.worktree, target)
    )
    if (
        origin is None
        or origin.record.state == "ended"
        or origin.process_key != process.key
    ):
        return None
    started = here.record.last_session_start_at
    if started is not None and observed_instant(started) > origin.last_activity:
        return None
    return origin


def _carry_run(
    record: Mapping[str, Any],
    process: ProcessIdentity,
    worktrees: Sequence[Path],
    target: Path,
    origin: StoredSessionRecord,
) -> ActiveWork | None:
    """Move the session's run from the origin's Worktree to ``target`` (conditions 1, 2, 7, 8)."""
    identity = SessionEvidence(
        require_harness(record.get("harness")),
        require_string(record.get("sessionId"), "sessionId"),
    )
    at_target: list[ActiveWork] = []
    elsewhere: list[tuple[Path, WorkStore, ActiveWork]] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        try:
            active, diagnostics = store.active()
        except OSError:
            return None
        if worktree == target:
            # An unreadable or unresolved record at B may be a competing run.
            if diagnostics:
                return None
            for candidate in active:
                relation = identity.match(candidate.evidence)
                if relation == "unresolved":
                    return None
                if relation == "same":
                    at_target.append(candidate)
            continue
        elsewhere.extend(
            (worktree, store, candidate)
            for candidate in active
            if identity.match(candidate.evidence) == "same"
        )
    if len(elsewhere) != 1:
        return None
    source_worktree, source, work = elsewhere[0]
    if not same_path(source_worktree, origin.worktree):
        return None
    recorded = work.session_process
    if recorded is None or recorded.key != process.key:
        return None
    intent = work.relocation
    if intent is not None and not same_path(Path(intent.target_worktree), target):
        return None
    if any(candidate.session_key != work.session_key for candidate in at_target):
        return None
    relocated = replace(
        work,
        working_directory=require_string(record.get("cwd"), "cwd"),
        branch=optional_string(record.get("branch")),
        relocation=None,
    )
    # The crash window of an earlier carry left this run at both; finishing
    # it removes A's copy and keeps B's as it is.
    repaired = next(
        (candidate for candidate in at_target if candidate.run_id == work.run_id),
        None,
    )
    if repaired is not None:
        relocated = repaired
    try:
        moved = source.complete_relocation(work, WorkStore(target), relocated)
    except (OSError, RecordKeyError, ValueError):
        return None
    return relocated if moved else None


def remove_ended_session_records(
    record: Mapping[str, Any],
    process: ProcessIdentity | None,
    *,
    worktrees: Sequence[Path],
    written: Path,
    global_store: Path | None = None,
) -> int:
    """Remove the ended session's older records elsewhere in its Repository.

    A shared Host Process such as the Codex daemon outlives the session, so a
    record a session left at the Worktree it moved on from would otherwise
    become its freshest once its ``SessionEnd`` removed the newer one, and
    read live there until the process exits (ADR 0067). ``record`` is the
    ``SessionEnd`` just published to the store at ``written``. Under the
    session's hook-store locks, a record in any other reachable store is
    removed only when it carries the session's own identity, places it at a
    Worktree of the Repository, names the Host Process the ``SessionEnd``
    itself was observed from (both observed, so another process's
    ``SessionEnd`` for the same id removes nothing), and is not newer than
    the ``SessionEnd``. Returns how many records were removed.
    """
    if process is None or not worktrees:
        return 0
    harness = require_harness(record.get("harness"))
    session_id = require_string(record.get("sessionId"), "sessionId")
    ended_at = observed_instant(optional_string(record.get("lastActivityAt")))
    stores = [
        store
        for store in reachable_hook_stores(worktrees, global_store)
        if store.is_dir() and not same_path(store, written)
    ]
    hook_stores = sorted(
        (hook_store_at(store, worktrees) for store in stores),
        key=lambda store: str(store.lock_path(session_id)),
    )
    removed = 0
    with ExitStack() as stack:
        for store in hook_stores:
            stack.enter_context(store.locked(session_id))
        records, _unreadable = stored_session_records(stores, harness, session_id)
        for item in records:
            if (
                item.process_key != process.key
                or item.last_activity > ended_at
                or not any(same_path(item.worktree, one) for one in worktrees)
            ):
                continue
            try:
                item.path.unlink()
            except OSError:
                continue
            removed += 1
    return removed
