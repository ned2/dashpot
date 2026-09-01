from __future__ import annotations

import json
import re
import stat
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .commands import CommandRunner, run_command
from .git import Git, GitError
from .model import (
    Branch,
    Diagnostic,
    ObservationTarget,
    ObservationTargetInventory,
    TargetRole,
)

# The fields `git for-each-ref` reports per ref; the Git adapter's records()
# separates them with NUL so a value can never be mistaken for a separator.
BRANCH_REF_FIELDS = (
    "%(refname)",
    "%(objectname)",
    "%(upstream:short)",
    "%(upstream:track)",
    "%(committerdate:iso-strict)",
    "%(worktreepath)",
    "%(symref)",
)
LOCAL_REF_PREFIX = "refs/heads/"
REMOTE_REF_PREFIX = "refs/remotes/"
ORIGIN_HEAD_REF = "refs/remotes/origin/HEAD"
DEFAULT_BRANCHES = ("main", "master")


def worktree_root(path: Path, git: Git | None = None) -> Path:
    """Return the current Git Worktree root containing a path."""
    adapter = git if git is not None else Git(path)
    return Path(adapter.at(path).text("rev-parse", "--show-toplevel")).resolve()


def repository_worktrees(
    root: Path, *, timeout: float = 5, git: Git | None = None
) -> list[Path]:
    """List every Worktree of the Git Repository one Worktree belongs to.

    Git reports the main working tree first and every linked one after it;
    a bare entry is not a Worktree. Independent clones are not reached
    ([ADR 0003](../../docs/adr/0003-prefer-project-local-dashpot-state.md)).
    """
    return [
        Path(record["worktree"]).resolve()
        for record in worktree_records(root, timeout=timeout, git=git)
        if record.get("worktree") and "bare" not in record
    ]


def worktree_records(
    root: Path, *, timeout: float = 5, git: Git | None = None
) -> list[dict[str, str]]:
    """Every record of ``git worktree list`` at ``root``, main working tree first.

    ``timeout`` applies only when no adapter is given; a supplied ``git``
    keeps its own.
    """
    adapter = git if git is not None else Git(root, timeout)
    return adapter.at(root).worktree_records()


# Whether the process holding a Worktree lock is still running. Dashpot asks
# the process adapter through this seam; observing processes is not this
# module's job, and a lock Git reports is only a fact about one.
LockHolder = Literal["live", "gone", "unknown"]
LockHolderProbe = Callable[[int], LockHolder]
# Every harness that locks a Worktree names the holding process the same way.
LOCK_HOLDER_PID = re.compile(r"\bpid (\d+)\b")


def lock_holder(reason: str, probe: LockHolderProbe | None) -> LockHolder:
    """Whether the process a lock reason names is still running."""
    if probe is None:
        return "unknown"
    match = LOCK_HOLDER_PID.search(reason)
    if match is None:
        return "unknown"
    return probe(int(match.group(1)))


def lock_diagnostic(
    path: str, reason: str, probe: LockHolderProbe | None
) -> Diagnostic | None:
    """Report a lock only once it stops explaining itself.

    A Worktree locked by a running session is that session working, which is
    the steady state and not worth a line. A lock whose holder has exited
    outlives the session and keeps the Worktree from being pruned, which is.
    """
    holder = lock_holder(reason, probe)
    if holder == "live":
        return None
    if holder == "gone":
        return Diagnostic(
            source=f"target:{path}",
            severity="warning",
            message=f"Observation Target is locked by a process that has exited: {reason}",
            code="target-locked-stale",
        )
    return Diagnostic(
        source=f"target:{path}",
        severity="info",
        message=f"Observation Target is locked: {reason}",
        code="target-locked",
    )


def observe_observation_targets(
    anchors: Sequence[Path],
    *,
    timeout: float = 5,
    git: Git | None = None,
    clock: Callable[[], float] = time.monotonic,
    process_lookup: LockHolderProbe | None = None,
) -> ObservationTargetInventory:
    """Discover and inspect executable Observation Targets for Repository Anchors."""
    # The default root is a placeholder: every command retargets to its anchor.
    adapter = git if git is not None else Git(Path.cwd(), timeout)
    records: list[dict[str, str]] = []
    diagnostics: list[Diagnostic] = []
    seen_paths: set[str] = set()
    # Git lists the main working tree first in every listing; that ordering,
    # not the path's name, is the observed topology role.
    main_paths: set[str] = set()
    for anchor in anchors:
        try:
            anchor_records = adapter.at(anchor).worktree_records()
        except GitError as exc:
            diagnostics.append(
                Diagnostic(
                    source=f"anchor:{anchor}",
                    severity="warning",
                    message=f"Cannot discover Observation Targets: {exc.detail}",
                    code="target-discovery",
                )
            )
            continue
        for index, record in enumerate(anchor_records):
            path = record.get("worktree")
            if path and index == 0:
                main_paths.add(path)
            if not path:
                diagnostics.append(
                    Diagnostic(
                        source=f"anchor:{anchor}",
                        severity="warning",
                        message="Git returned a malformed worktree record without a path",
                        code="target-malformed",
                    )
                )
                continue
            if path not in seen_paths:
                seen_paths.add(path)
                records.append(record)

    targets: list[ObservationTarget] = []
    for record in records:
        path = record["worktree"]
        role: TargetRole = "main" if path in main_paths else "linked"
        if "bare" in record:
            diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="info",
                    message=f"Git repository entry is bare and cannot be observed: {path}",
                    code="target-bare",
                )
            )
            continue
        branch = record.get("branch")
        if branch and branch.startswith("refs/heads/"):
            branch = branch.removeprefix("refs/heads/")
        detached = "detached" in record
        target_diagnostics: list[Diagnostic] = []
        if "locked" in record:
            locked = lock_diagnostic(
                path, record["locked"] or "no reason reported", process_lookup
            )
            if locked is not None:
                target_diagnostics.append(locked)
        if "prunable" in record:
            reason = record["prunable"] or "no reason reported"
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Observation Target is prunable: {reason}",
                    code="target-prunable",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        if not record.get("HEAD") or bool(branch) == detached:
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message="Git returned a malformed worktree record",
                    code="target-malformed",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        try:
            path_mode = Path(path).stat().st_mode
        except FileNotFoundError:
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Observation Target does not exist: {path}",
                    code="target-missing",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        except OSError as exc:
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Cannot inspect Observation Target path: {exc}",
                    code="target-inaccessible",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        if not stat.S_ISDIR(path_mode):
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Observation Target is not a directory: {path}",
                    code="target-missing",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        started = clock()
        try:
            result = adapter.at(Path(path)).run(
                "status", "--porcelain=v1", "--untracked-files=normal"
            )
        except GitError as exc:
            elapsed_ms = round((clock() - started) * 1000)
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Cannot inspect Observation Target: {exc.detail}",
                    code="target-inaccessible",
                )
            )
            targets.append(
                _unavailable_target(
                    record,
                    role,
                    branch,
                    detached,
                    target_diagnostics,
                    elapsed_ms,
                )
            )
            continue
        elapsed_ms = round((clock() - started) * 1000)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            target_diagnostics.append(
                Diagnostic(
                    source=f"target:{path}",
                    severity="warning",
                    message=f"Cannot inspect Observation Target: {detail}",
                    code="target-inaccessible",
                )
            )
            availability = "unavailable"
            dirty = None
        else:
            availability = "available"
            dirty = bool(result.stdout)
        targets.append(
            ObservationTarget(
                path=path,
                head=record["HEAD"],
                branch=branch,
                detached=detached,
                dirty=dirty,
                availability=availability,
                elapsed_ms=elapsed_ms,
                diagnostics=target_diagnostics,
                role=role,
            )
        )
    return ObservationTargetInventory(targets=targets, diagnostics=diagnostics)


def _unavailable_target(
    record: dict[str, str],
    role: TargetRole,
    branch: str | None,
    detached: bool,
    diagnostics: list[Diagnostic],
    elapsed_ms: int = 0,
) -> ObservationTarget:
    return ObservationTarget(
        path=record["worktree"],
        head=record.get("HEAD", ""),
        branch=branch,
        detached=detached,
        dirty=None,
        availability="unavailable",
        elapsed_ms=elapsed_ms,
        diagnostics=diagnostics,
        role=role,
    )


@dataclass(slots=True)
class BranchObservation:
    """Every Branch of a repository plus the age of its remote facts."""

    branches: list[Branch]
    fetched_at: str | None
    diagnostics: list[Diagnostic]
    integration_ref: str | None = None


def observe_branches(
    anchors: Sequence[Path],
    *,
    timeout: float = 5,
    git: Git | None = None,
) -> BranchObservation:
    """List every local and Remote-Tracking Branch without fetching.

    Independent clones of one repository have their own refs, so the first
    Repository Anchor that answers is authoritative, as it is for Local
    Issues; the others are only tried when it cannot be listed.
    """
    # The default root is a placeholder: every command retargets to its anchor.
    adapter = git if git is not None else Git(Path.cwd(), timeout)
    diagnostics: list[Diagnostic] = []
    for anchor in anchors:
        scoped = adapter.at(anchor)
        try:
            listed = scoped.records(
                "refs/heads", "refs/remotes", fields=BRANCH_REF_FIELDS
            )
        except GitError as exc:
            diagnostics.append(_branch_diagnostic(anchor, exc.detail))
            continue
        branches = [
            branch
            for record in listed
            if (branch := _parse_branch_record(record)) is not None
        ]
        integration_ref = _integration_ref(listed, branches)
        anchor_diagnostics: list[Diagnostic] = []
        if integration_ref is not None:
            branches = _observe_integration(
                branches, integration_ref, anchor, scoped, anchor_diagnostics
            )
        return BranchObservation(
            branches,
            _fetched_at(anchor, scoped),
            anchor_diagnostics,
            integration_ref,
        )
    return BranchObservation([], None, diagnostics)


def _branch_diagnostic(anchor: Path, detail: str) -> Diagnostic:
    return Diagnostic(
        source=f"anchor:{anchor}",
        severity="warning",
        message=f"Cannot list Branches: {detail}",
        code="branch-discovery",
    )


def _parse_branch_record(record: tuple[str, ...]) -> Branch | None:
    """One `for-each-ref` record, or None for a symbolic alias like origin/HEAD."""
    refname, head, upstream, track, committed_at, worktree_path, symref = record
    if symref:
        return None
    if refname.startswith(LOCAL_REF_PREFIX):
        name = refname.removeprefix(LOCAL_REF_PREFIX)
        remote = None
    elif refname.startswith(REMOTE_REF_PREFIX):
        remote, _separator, name = refname.removeprefix(REMOTE_REF_PREFIX).partition(
            "/"
        )
        if not name:
            return None
    else:
        return None
    ahead, behind, gone = (
        _parse_upstream_track(track) if upstream else (None, None, False)
    )
    return Branch(
        refname=refname,
        name=name,
        remote=remote,
        head=head,
        committed_at=_utc_timestamp(committed_at),
        upstream=upstream or None,
        ahead=ahead,
        behind=behind,
        upstream_gone=gone,
        checked_out_at=worktree_path or None,
    )


def _integration_ref(
    records: Sequence[tuple[str, ...]], branches: Sequence[Branch]
) -> str | None:
    """Choose origin/HEAD, else the unique local main or master Branch."""
    refnames = {branch.refname for branch in branches}
    origin_head: str | None = None
    for record in records:
        refname, *_other, symref = record
        if refname == ORIGIN_HEAD_REF:
            origin_head = symref or None
            break
    return choose_integration_ref(origin_head, refnames)


def choose_integration_ref(
    origin_head: str | None, available_refs: Iterable[str]
) -> str | None:
    """Choose origin/HEAD, else the unique available local main or master ref."""
    refnames = set(available_refs)
    if origin_head is not None and origin_head in refnames:
        return origin_head
    local_defaults = [
        f"{LOCAL_REF_PREFIX}{name}"
        for name in DEFAULT_BRANCHES
        if f"{LOCAL_REF_PREFIX}{name}" in refnames
    ]
    return local_defaults[0] if len(local_defaults) == 1 else None


def _observe_integration(
    branches: Sequence[Branch],
    integration_ref: str,
    anchor: Path,
    git: Git,
    diagnostics: list[Diagnostic],
) -> list[Branch]:
    """Count each local Branch's commits not reachable from the integration ref.

    A Git failure here is diagnosed rather than swallowed: a Branch whose
    ``unintegrated_commits`` stays None because Git could not answer must be
    distinguishable from a repository with no Integration Branch at all.
    """
    try:
        merged = git.records(
            f"--merged={integration_ref}", "refs/heads", fields=("%(refname)",)
        )
    except GitError as exc:
        diagnostics.append(
            _integration_diagnostic(
                anchor,
                f"Cannot list Branches merged into {integration_ref}: {exc.detail}",
            )
        )
        return list(branches)
    integrated = {record[0] for record in merged}
    observed: list[Branch] = []
    for branch in branches:
        if branch.remote is not None:
            observed.append(branch)
            continue
        count = (
            0
            if branch.refname in integrated
            else _unintegrated_commit_count(
                anchor, integration_ref, branch.refname, git, diagnostics
            )
        )
        observed.append(branch.model_copy(update={"unintegrated_commits": count}))
    return observed


def _integration_diagnostic(anchor: Path, message: str) -> Diagnostic:
    return Diagnostic(
        source=f"anchor:{anchor}",
        severity="warning",
        message=message,
        code="branch-integration",
    )


def _unintegrated_commit_count(
    anchor: Path,
    integration_ref: str,
    branch_ref: str,
    git: Git,
    diagnostics: list[Diagnostic],
) -> int | None:
    message = f"Cannot count commits of {branch_ref} not on {integration_ref}"
    try:
        count = git.count("rev-list", "--count", f"{integration_ref}..{branch_ref}")
    except GitError as exc:
        diagnostics.append(_integration_diagnostic(anchor, f"{message}: {exc.detail}"))
        return None
    if count is None:
        diagnostics.append(_integration_diagnostic(anchor, message))
    return count


def _utc_timestamp(value: str) -> str:
    """Normalise Git's offset timestamp to UTC so timestamps sort as text."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_upstream_track(track: str) -> tuple[int | None, int | None, bool]:
    """``[ahead 1, behind 2]`` → counts; ``[gone]`` → gone; blank → in sync."""
    if "gone" in track:
        return None, None, True
    ahead_match = re.search(r"ahead (\d+)", track)
    behind_match = re.search(r"behind (\d+)", track)
    return (
        int(ahead_match.group(1)) if ahead_match else 0,
        int(behind_match.group(1)) if behind_match else 0,
        False,
    )


def _fetched_at(anchor: Path, git: Git) -> str | None:
    """When the repository last fetched, from ``FETCH_HEAD``; None if never.

    A repository that never fetched has no FETCH_HEAD; a failed lookup of
    the common directory is deliberately the same honest answer.
    """
    try:
        raw = git.maybe("rev-parse", "--git-common-dir")
    except GitError:
        return None
    if not raw:
        return None
    common_dir = Path(raw)
    if not common_dir.is_absolute():
        common_dir = anchor / common_dir
    try:
        modified = (common_dir / "FETCH_HEAD").stat().st_mtime
    except OSError:
        return None
    return (
        datetime.fromtimestamp(modified, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def github_repo_from_remote(root: Path, git: Git | None = None) -> str | None:
    """The ``owner/name`` GitHub reference of ``origin``, or None without one."""
    adapter = git if git is not None else Git(root)
    remote = adapter.at(root).maybe("remote", "get-url", "origin")
    if remote is None:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return None if match is None else str(match.group(1))


def observe_github_repository_identity(
    root: Path,
    reference: str,
    timeout: float = 10,
    runner: CommandRunner = run_command,
) -> tuple[str, str]:
    """Resolve a mutable GitHub reference to its durable Repository identity."""
    result = runner(["gh", "api", f"repos/{reference}"], root, timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"gh api exited {result.returncode}"
        raise RuntimeError(f"cannot resolve GitHub repository {reference}: {detail}")
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"GitHub returned malformed repository metadata for {reference}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"GitHub returned malformed repository metadata for {reference}"
        )
    repository_id = payload.get("node_id")
    observed_reference = payload.get("full_name")
    if not isinstance(repository_id, str) or not repository_id:
        raise RuntimeError(f"GitHub repository {reference} has no durable identity")
    if not isinstance(observed_reference, str) or not observed_reference:
        raise RuntimeError(f"GitHub repository {reference} has no full name")
    return repository_id, observed_reference


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
