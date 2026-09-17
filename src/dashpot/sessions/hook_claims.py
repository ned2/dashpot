"""Validate claimed Agent Session identities against hook evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..repository import repository_worktrees
from .harnesses import (
    HARNESS_DISPLAY,
    SessionIdentityClaim,
)
from .hook_scan import (
    HookRecordClassification,
    SessionLocation,
    locate_agent_session,
    reachable_hook_stores,
)
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
)


@dataclass(frozen=True, slots=True)
class ValidatedSessionIdentity:
    """A claimed Agent Session Identity its harness's hook record confirmed."""

    claim: SessionIdentityClaim
    record: HookRecordClassification
    process: ProcessIdentity | None
    location: SessionLocation | None = None

    @property
    def harness(self) -> str:
        return self.claim.harness

    @property
    def session_id(self) -> str:
        return self.claim.session_id


def validate_session_claim(
    claim: SessionIdentityClaim,
    worktree: Path,
    lookup: ProcessLookup = host_process_lookup,
    *,
    stores: Sequence[Path] | None = None,
) -> ValidatedSessionIdentity:
    """Confirm a claimed identity against its harness's freshest hook record.

    The record is the session's freshest across every hook store reachable
    from ``worktree`` — those of the Repository's Worktrees and the global
    store — and must still describe a session that is live or unknown; a
    missing, unreadable, ended, gone, cross-harness, or process-mismatched
    record raises an actionable ``RuntimeError`` so that no Issue Binding is
    created from the claim. Where that record places the session is
    returned with it; whether that is ``worktree`` is the caller's question.
    """
    display = HARNESS_DISPLAY[claim.harness]
    name = f"{display} session {claim.session_id} (from {claim.source})"
    if stores is None:
        stores = reachable_hook_stores(repository_worktrees(worktree))
    try:
        location = locate_agent_session(
            stores, lookup, harness=claim.harness, session_id=claim.session_id
        )
    except ValueError as exc:
        raise RuntimeError(
            f"the lifecycle hook record for {name} cannot be read: {exc}; "
            f"run 'dashpot integrate {claim.harness} --status'"
        ) from exc
    if location is None:
        raise RuntimeError(
            f"no lifecycle hook record for {name} at {worktree} or any other "
            f"Worktree of its Repository; the {display} hooks must be installed "
            f"and have published this session (check 'dashpot integrate "
            f"{claim.harness} --status')"
        )
    record = location.record
    if record.harness != claim.harness:
        raise RuntimeError(
            f"{name} names a hook record published by {record.display}; the "
            f"identities of two harnesses cannot be combined"
        )
    if record.outcome in {"ended", "gone"}:
        how = "ended" if record.outcome == "ended" else "whose process is gone"
        raise RuntimeError(
            f"the lifecycle hook record for {name} at {location.worktree} is "
            f"stale ({how}); it identifies no running session"
        )
    process = location.process
    if claim.pid is not None and process is not None and process.pid != claim.pid:
        raise RuntimeError(
            f"{name} attributes the harness to pid {claim.pid}, but its hook "
            f"record was published for pid {process.pid}; the identities do "
            f"not describe one session"
        )
    return ValidatedSessionIdentity(claim, record, process, location)
