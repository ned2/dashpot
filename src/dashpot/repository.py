from __future__ import annotations

import json
import re
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .commands import CommandRunner, run_command
from .model import (
    Branch,
    Diagnostic,
    ObservationTarget,
    ObservationTargetInventory,
    TargetRole,
)

# The fields `git for-each-ref` reports per ref, NUL-separated so a value can
# never be mistaken for a separator; a record ends with a newline.
BRANCH_REF_FIELDS = (
    "%(refname)",
    "%(objectname)",
    "%(upstream:short)",
    "%(upstream:track)",
    "%(committerdate:iso-strict)",
    "%(worktreepath)",
    "%(symref)",
)
BRANCH_REF_FORMAT = "%00".join(BRANCH_REF_FIELDS)
LOCAL_REF_PREFIX = "refs/heads/"
REMOTE_REF_PREFIX = "refs/remotes/"


def git(root: Path, *args: str, timeout: float = 5) -> str:
    result = run_command(["git", *args], root, timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def worktree_root(path: Path) -> Path:
    """Return the current Git Worktree root containing a path."""
    return Path(git(path, "rev-parse", "--show-toplevel")).resolve()


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
            f"target:{path}",
            "warning",
            f"Observation Target is locked by a process that has exited: {reason}",
            "target-locked-stale",
        )
    return Diagnostic(
        f"target:{path}",
        "info",
        f"Observation Target is locked: {reason}",
        "target-locked",
    )


def observe_observation_targets(
    anchors: Sequence[Path],
    *,
    timeout: float = 5,
    runner: CommandRunner = run_command,
    clock: Callable[[], float] = time.monotonic,
    process_lookup: LockHolderProbe | None = None,
) -> ObservationTargetInventory:
    """Discover and inspect executable Observation Targets for Repository Anchors."""
    records: list[dict[str, str]] = []
    diagnostics: list[Diagnostic] = []
    seen_paths: set[str] = set()
    # Git lists the main working tree first in every listing; that ordering,
    # not the path's name, is the observed topology role.
    main_paths: set[str] = set()
    for anchor in anchors:
        try:
            result = runner(
                ["git", "worktree", "list", "--porcelain", "-z"],
                anchor,
                timeout,
            )
        except (OSError, RuntimeError) as exc:
            diagnostics.append(
                Diagnostic(
                    f"anchor:{anchor}",
                    "warning",
                    f"Cannot discover Observation Targets: {exc}",
                    "target-discovery",
                )
            )
            continue
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            diagnostics.append(
                Diagnostic(
                    f"anchor:{anchor}",
                    "warning",
                    f"Cannot discover Observation Targets: {detail}",
                    "target-discovery",
                )
            )
            continue
        for index, record in enumerate(_parse_worktree_records(result.stdout)):
            path = record.get("worktree")
            if path and index == 0:
                main_paths.add(path)
            if not path:
                diagnostics.append(
                    Diagnostic(
                        f"anchor:{anchor}",
                        "warning",
                        "Git returned a malformed worktree record without a path",
                        "target-malformed",
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
                    f"target:{path}",
                    "info",
                    f"Git repository entry is bare and cannot be observed: {path}",
                    "target-bare",
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
                    f"target:{path}",
                    "warning",
                    f"Observation Target is prunable: {reason}",
                    "target-prunable",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        if not record.get("HEAD") or bool(branch) == detached:
            target_diagnostics.append(
                Diagnostic(
                    f"target:{path}",
                    "warning",
                    "Git returned a malformed worktree record",
                    "target-malformed",
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
                    f"target:{path}",
                    "warning",
                    f"Observation Target does not exist: {path}",
                    "target-missing",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        except OSError as exc:
            target_diagnostics.append(
                Diagnostic(
                    f"target:{path}",
                    "warning",
                    f"Cannot inspect Observation Target path: {exc}",
                    "target-inaccessible",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        if not stat.S_ISDIR(path_mode):
            target_diagnostics.append(
                Diagnostic(
                    f"target:{path}",
                    "warning",
                    f"Observation Target is not a directory: {path}",
                    "target-missing",
                )
            )
            targets.append(
                _unavailable_target(record, role, branch, detached, target_diagnostics)
            )
            continue
        started = clock()
        try:
            result = runner(
                [
                    "git",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=normal",
                ],
                Path(path),
                timeout,
            )
        except (OSError, RuntimeError) as exc:
            elapsed_ms = round((clock() - started) * 1000)
            target_diagnostics.append(
                Diagnostic(
                    f"target:{path}",
                    "warning",
                    f"Cannot inspect Observation Target: {exc}",
                    "target-inaccessible",
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
                    f"target:{path}",
                    "warning",
                    f"Cannot inspect Observation Target: {detail}",
                    "target-inaccessible",
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
    return ObservationTargetInventory(targets, diagnostics)


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


def observe_branches(
    anchors: Sequence[Path],
    *,
    timeout: float = 5,
    runner: CommandRunner = run_command,
) -> BranchObservation:
    """List every local and Remote-Tracking Branch without fetching.

    Independent clones of one repository have their own refs, so the first
    Repository Anchor that answers is authoritative, as it is for Local
    Issues; the others are only tried when it cannot be listed.
    """
    diagnostics: list[Diagnostic] = []
    for anchor in anchors:
        try:
            result = runner(
                [
                    "git",
                    "for-each-ref",
                    f"--format={BRANCH_REF_FORMAT}",
                    "refs/heads",
                    "refs/remotes",
                ],
                anchor,
                timeout,
            )
        except (OSError, RuntimeError) as exc:
            diagnostics.append(_branch_diagnostic(anchor, str(exc)))
            continue
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            diagnostics.append(_branch_diagnostic(anchor, detail))
            continue
        branches = [
            branch
            for line in result.stdout.splitlines()
            if line and (branch := _parse_branch_record(line)) is not None
        ]
        return BranchObservation(
            branches, _fetched_at(anchor, runner=runner, timeout=timeout), []
        )
    return BranchObservation([], None, diagnostics)


def _branch_diagnostic(anchor: Path, detail: str) -> Diagnostic:
    return Diagnostic(
        f"anchor:{anchor}",
        "warning",
        f"Cannot list Branches: {detail}",
        "branch-discovery",
    )


def _parse_branch_record(line: str) -> Branch | None:
    """One `for-each-ref` record, or None for a symbolic alias like origin/HEAD."""
    fields = line.split("\0")
    if len(fields) != len(BRANCH_REF_FIELDS):
        return None
    refname, head, upstream, track, committed_at, worktree_path, symref = fields
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


def _fetched_at(anchor: Path, *, runner: CommandRunner, timeout: float) -> str | None:
    """When the repository last fetched, from ``FETCH_HEAD``; None if never."""
    try:
        result = runner(["git", "rev-parse", "--git-common-dir"], anchor, timeout)
    except (OSError, RuntimeError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    common_dir = Path(result.stdout.strip())
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


def _parse_worktree_records(raw: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for field in raw.split("\0"):
        if not field:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = field.partition(" ")
        current[key] = value if separator else ""
    if current:
        records.append(current)
    return records


def github_repo_from_remote(root: Path) -> str | None:
    try:
        remote = git(root, "remote", "get-url", "origin")
    except RuntimeError:
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
