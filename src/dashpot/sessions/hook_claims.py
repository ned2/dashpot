"""Validate claimed Agent Session identities against hook evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import DashpotError
from ..core.model import HARNESS_DISPLAY, Harness
from ..core.worktree_paths import repository_worktrees
from .harnesses import SessionIdentityClaim
from .hook_scan import (
    HookRecordClassification,
    SessionLocation,
    locate_agent_session,
    reachable_hook_stores,
)
from .opencode_publishers import deleted_session, recorded_root
from .processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
)


class SessionClaimError(DashpotError):
    """A claimed Agent Session Identity no live hook record confirms."""


@dataclass(frozen=True, slots=True)
class ValidatedSessionIdentity:
    """A claimed Agent Session Identity its harness's hook record confirmed."""

    claim: SessionIdentityClaim
    record: HookRecordClassification
    process: ProcessIdentity | None
    location: SessionLocation | None = None

    @property
    def harness(self) -> Harness:
        return self.claim.harness

    @property
    def session_id(self) -> str:
        return self.claim.session_id

    @property
    def delegate(self) -> str | None:
        return self.claim.delegate


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
    record raises an actionable ``SessionClaimError`` so that no Issue Binding is
    created from the claim. Where that record places the session is
    returned with it; whether that is ``worktree`` is the caller's question.
    """
    display = HARNESS_DISPLAY[claim.harness]
    name = f"{display} session {claim.session_id} (from {claim.source})"
    if stores is None:
        stores = reachable_hook_stores(repository_worktrees(worktree))
    if claim.harness == "opencode":
        _refuse_opencode_claim(claim, name, stores)
    try:
        location = locate_agent_session(
            stores, lookup, harness=claim.harness, session_id=claim.session_id
        )
    except ValueError as exc:
        raise SessionClaimError(
            f"the lifecycle hook record for {name} cannot be read: {exc}; "
            f"run 'dashpot integrate {claim.harness} --status'"
        ) from exc
    if location is None:
        raise SessionClaimError(
            f"no lifecycle hook record for {name} at {worktree} or any other "
            f"Worktree of its Repository; the {display} hooks must be installed "
            f"and have published this session (check 'dashpot integrate "
            f"{claim.harness} --status')"
        )
    record = location.record
    if record.harness != claim.harness:
        raise SessionClaimError(
            f"{name} names a hook record published by {record.display}; the "
            f"identities of two harnesses cannot be combined"
        )
    if record.outcome in {"ended", "gone"}:
        how = "ended" if record.outcome == "ended" else "whose process is gone"
        raise SessionClaimError(
            f"the lifecycle hook record for {name} at {location.worktree} is "
            f"stale ({how}); it identifies no running session"
        )
    process = location.process
    if claim.pid is not None and process is not None and process.pid != claim.pid:
        raise SessionClaimError(
            f"{name} attributes the harness to pid {claim.pid}, but its hook "
            f"record was published for pid {process.pid}; the identities do "
            f"not describe one session"
        )
    if claim.harness == "opencode" and process is None:
        # One OpenCode server hosts every session, so only a record naming
        # it can corroborate the pid the claim carries.
        raise SessionClaimError(
            f"the lifecycle hook record for {name} names no Host Process; it "
            f"cannot corroborate the OpenCode server the command runs in"
        )
    return ValidatedSessionIdentity(claim, record, process, location)


def _refuse_opencode_claim(
    claim: SessionIdentityClaim, name: str, stores: Sequence[Path]
) -> None:
    """Refuse an OpenCode claim that is not a root session's own.

    The claim must be OpenCode's own variable on a model's shell, which
    carries the plugin's pid; an explicit ``DASHPOT_AGENT_SESSION`` never
    does. A child session is recorded with its root, so it is no Agent
    Session of its own, and a session OpenCode deleted is no session at all
    (ADR 0090).
    """
    if claim.pid is None:
        raise SessionClaimError(
            f"{name} is not OpenCode's own claim; an OpenCode session is "
            f"identified only by the session variable OpenCode sets on a shell "
            f"its agent runs, beside Dashpot's plugin's pid"
        )
    for store in stores:
        root = recorded_root(store, claim.session_id)
        if root is not None:
            raise SessionClaimError(
                f"{name} is refused (delegated-session): it is a child session "
                f"of {root}, whose Agent Run its work belongs to; run 'dashpot "
                f"work start' from session {root}"
            )
        if deleted_session(store, claim.session_id):
            raise SessionClaimError(
                f"{name} is refused: OpenCode has deleted the session"
            )
