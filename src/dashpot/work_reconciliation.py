"""Reconcile Agent Runs from published hook events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

from .core.git import GitError
from .core.json_records import optional_string, require_string
from .hook_records import HookRecordStore
from .hook_scan import (
    reachable_hook_stores,
    scan_hook_stores,
    session_record_named,
)
from .liveness import LivenessProbe
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
)
from .repository import repository_worktrees, same_path
from .session_matching import SessionEvidence
from .work_store import (
    ActiveWork,
    SessionProcess,
    WorkStore,
    end_session_runs,
)


def end_session_work(
    record: Mapping[str, Any], process: ProcessIdentity | None
) -> list[tuple[Path, ActiveWork]]:
    """Reconcile the Agent Run of a gracefully ended client session.

    An undeclared end is the session's own state, so ending its run is the
    same housekeeping as removing the hook record (ADR 0015).
    It is looked for at every Worktree of the Repository the session ended
    in, since a session holds one run across them (ADR 0009). A declared Codex
    Relocation Intent instead preserves the run for target verification (ADR
    0029); a client that ends outside any Repository has no Work Store to
    reconcile.
    """
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return []
    try:
        worktrees = repository_worktrees(Path(root), timeout=2)
    except GitError:
        return []
    return end_session_runs(
        worktrees,
        require_string(record.get("harness"), "harness"),
        require_string(record.get("sessionId"), "sessionId"),
        process.key if process else None,
        ended_at=optional_string(record.get("lastActivityAt")),
    )


def complete_session_work_relocation(
    record: Mapping[str, Any],
    process: ProcessIdentity | None,
    lookup: ProcessLookup = host_process_lookup,
    *,
    directory: Path | None = None,
) -> bool:
    """Complete a declared Codex relocation proved by this target hook record."""
    if record.get("harness") != "codex":
        return False
    root = optional_string(record.get("repositoryRoot"))
    if root is None:
        return False
    try:
        target = Path(root).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        worktrees = repository_worktrees(target, timeout=2)
    except GitError:
        return False
    # Without a Work Store there can be no Relocation Intent; locking hook
    # stores would otherwise create Project-local state in an unconfigured repo.
    if not any(WorkStore(worktree).directory.exists() for worktree in worktrees):
        return False
    session_id = require_string(record.get("sessionId"), "sessionId")
    stores = reachable_hook_stores(worktrees, directory)
    hook_stores = sorted(
        (HookRecordStore(store) for store in stores),
        key=lambda store: str(store.lock_path(session_id)),
    )
    with ExitStack() as stack:
        for store in hook_stores:
            stack.enter_context(store.locked(session_id))
        if not _sequential_target_is_confirmed(stores, session_id, target, lookup):
            return False
        matching: list[tuple[Path, WorkStore, ActiveWork]] = []
        for worktree in worktrees:
            store = WorkStore(worktree)
            try:
                active, diagnostics = store.active()
            except OSError:
                return False
            if diagnostics:
                return False
            for candidate in active:
                relation = SessionEvidence("codex", session_id).match(
                    candidate.evidence
                )
                if relation == "unresolved":
                    return False
                if relation == "same":
                    matching.append((worktree, store, candidate))
        pending_matches = [
            item
            for item in matching
            if item[2].relocation is not None
            and same_path(Path(item[2].relocation.target_worktree), target)
        ]
        if len(pending_matches) != 1:
            return False
        source_worktree, source, work = pending_matches[0]
        if any(
            not same_path(candidate_worktree, target)
            or candidate.session_key != work.session_key
            for candidate_worktree, _store, candidate in matching
            if candidate != work
        ):
            return False
        intent = work.relocation
        if intent is None:
            return False
        if not same_path(Path(intent.target_worktree), target) or same_path(
            source_worktree, target
        ):
            return False
        session_process = (
            SessionProcess(pid=process.pid, started_at=process.started_at)
            if process is not None
            else None
        )
        relocated = replace(
            work,
            session_label=(
                f"codex pid {process.pid}"
                if process is not None
                else f"codex session {session_id}"
            ),
            session_process=session_process,
            working_directory=require_string(record.get("cwd"), "cwd"),
            branch=optional_string(record.get("branch")),
            relocation=None,
        )
        try:
            return source.complete_relocation(work, WorkStore(target), relocated)
        except (OSError, RuntimeError, ValueError):
            return False


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
