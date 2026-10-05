"""Report the session record stores and the Agent Session Identity claimed here.

``--status`` closes each harness's report with these lines. None of them
is installation: they read the session records the hooks write, and the
identity this command's environment claims.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ...core.git import GitError
from ...core.model import HARNESS_DISPLAY
from ...core.state_paths import is_configured_checkout
from ...core.working_directory import current_directory
from ...core.worktree_paths import same_path, worktree_root
from ..harnesses import (
    SESSION_OVERRIDE_VARIABLE,
    HarnessError,
    OpenCodeHostMode,
    adapter,
    opencode_host_mode,
    opencode_shell_refusal,
    override_claim,
)
from ..hook_claims import SessionClaimError, validate_session_claim
from ..hook_records import session_directory, state_directory
from ..hook_scan import (
    SessionRecordSummary,
    StaleSessionRecord,
    summarize_session_records,
)
from ..processes import ProcessAbsent, ProcessLookup, ProcessUnobservable
from ..session_exits import named_subagents
from .registry import HarnessIntegration


def record_store_status(
    state_dir: Path | None, current: Path | None, lookup: ProcessLookup
) -> list[str]:
    """Report the session stores visible from here: Project-local and global.

    Each store's records are classified at this moment without being pruned;
    stale records name the session so undelivered SessionEnd hooks can be
    diagnosed here rather than on the workspace Diagnostics surface.
    """
    messages: list[str] = []
    try:
        root = worktree_root(current or current_directory())
    except GitError:
        root = None
    if root is not None and is_configured_checkout(root):
        local = session_directory(root)
        messages.extend(
            _describe_records(
                "for this Project", summarize_session_records(local, lookup)
            )
        )
    directory = state_dir or state_directory()
    if directory.is_dir():
        messages.extend(
            _describe_records(
                "outside configured Projects",
                summarize_session_records(directory, lookup),
            )
        )
    else:
        messages.append(
            f"session records outside configured Projects: none ({directory} "
            "does not exist yet)"
        )
    return messages


def claimed_identity_status(
    spec: HarnessIntegration,
    current: Path | None,
    lookup: ProcessLookup,
    environ: Mapping[str, str] | None,
) -> list[str]:
    """Report the Agent Session Identity this command's environment claims.

    This is the identity a sandboxed ``dashpot work start`` would use, so
    whether it names a live hook record here is what to check when opt-in
    from a sandbox is refused.
    """
    environment = environ if environ is not None else os.environ
    try:
        claim = override_claim(environment)
    except HarnessError as exc:
        return [f"Agent Session identity claimed here: {exc}"]
    if claim is None or claim.harness != spec.harness:
        claim = adapter(spec.harness).claim_session_identity(environment)
    if claim is None and spec.harness == "opencode":
        refusal = opencode_shell_refusal(environment, in_opencode=False) or (
            "only a shell OpenCode ran for its agent, prepared by the plugin, "
            "carries one"
        )
        return [
            f"Agent Session identity claimed here: none for {spec.display} ({refusal})"
        ]
    if claim is None:
        return [
            f"Agent Session identity claimed here: none for {spec.display} "
            f"(Issue opt-in from a sandbox needs one; {SESSION_OVERRIDE_VARIABLE}"
            f"={spec.harness}:<session id> states it explicitly)"
        ]
    prefix = (
        f"Agent Session identity claimed here: {spec.display} session "
        f"{claim.session_id} (from {claim.source})"
    )
    try:
        root = worktree_root(current or current_directory())
    except GitError:
        return [f"{prefix}, not validated: not inside a Git worktree"]
    try:
        validated = validate_session_claim(claim, root, lookup)
    except SessionClaimError as exc:
        return [f"{prefix}, rejected: {exc}"]
    # The freshest record may sit in another Worktree of the Repository, as
    # after a move whose record at the destination could not be written, and
    # then the session is not here, whatever directory this command runs in.
    location = validated.location
    if location is not None and not same_path(location.worktree, root):
        return [
            f"{prefix}, elsewhere: its freshest hook record, "
            f"{validated.record.outcome}, places it at {location.worktree}, "
            f"not here"
        ]
    confirmed = f"{prefix}, confirmed by its {validated.record.outcome} hook record"
    # Validation refuses an OpenCode claim without the plugin's pid, so every
    # confirmed OpenCode claim names its server.
    if claim.harness != "opencode" or claim.pid is None:
        return [confirmed]
    return [confirmed, _opencode_host_mode_status(claim.pid, lookup)]


def _opencode_host_mode_status(pid: int, lookup: ProcessLookup) -> str:
    """Report how the OpenCode server a confirmed session's claim names serves it.

    The server is the process ``DASHPOT_OPENCODE_PID`` names. A session moves
    itself, and leads Workers, only when this reads ``shared-service``: both
    are measured on the shared service alone (ADR 0108).
    """
    observed = lookup(pid)
    mode: OpenCodeHostMode
    if isinstance(observed, ProcessUnobservable):
        mode, detail = "unknown", f"pid {pid} could not be observed ({observed.reason})"
    elif isinstance(observed, ProcessAbsent):
        mode, detail = "unknown", f"pid {pid} has exited"
    else:
        mode = opencode_host_mode(observed.identity)
        detail = {
            "shared-service": f"pid {pid}, the shared 'opencode serve --service'",
            "standalone": (
                f"pid {pid}, a --standalone client's private 'opencode serve --stdio'"
            ),
            "unknown": (
                f"pid {pid} is neither 'opencode serve --service' nor "
                "'opencode serve --stdio'"
            ),
        }[mode]
    line = f"OpenCode Host Process mode: {mode} ({detail})"
    if mode == "shared-service":
        return line
    return (
        f"{line}; this session moves itself and leads Workers only on the "
        "shared service"
    )


def _describe_records(scope: str, summary: SessionRecordSummary) -> list[str]:
    unknown = f"{summary.unknown} unknown"
    if summary.unknown_reasons:
        reasons = ", ".join(reason for reason, _count in summary.unknown_reasons)
        unknown += f" [{reasons}]"
    messages = [
        f"session records {scope}: {summary.total} in {summary.directory} "
        f"({summary.live} live, {unknown}, {len(summary.stale)} stale, "
        f"{summary.unreadable} unreadable)"
    ]
    messages.extend(f"  stale: {_describe_stale(record)}" for record in summary.stale)
    return messages


def _describe_stale(record: StaleSessionRecord) -> str:
    display = HARNESS_DISPLAY.get(record.harness, record.harness)
    text = (
        f"{display} session {record.session_id} last event "
        f"{record.event or 'unknown'} at {record.last_activity_at or 'unknown time'}, "
    )
    if record.retained_subagents:
        return text + (
            f"ended by SessionEnd, kept for its "
            f"{named_subagents(record.retained_subagents)} until they stop or "
            f"pid {record.pid} exits"
        )
    if record.outcome == "ended":
        return text + "ended by SessionEnd (legacy record; pruned on next observation)"
    process = f"pid {record.pid}" if record.pid is not None else "process"
    return text + f"{process} gone (no SessionEnd delivered)"
