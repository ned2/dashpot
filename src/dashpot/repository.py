from __future__ import annotations

import json
import re
import stat
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .commands import CommandRunner, run_command
from .model import (
    Diagnostic,
    ObservationTarget,
    ObservationTargetInventory,
)


def git(root: Path, *args: str, timeout: float = 5) -> str:
    result = run_command(["git", *args], root, timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def worktree_root(path: Path) -> Path:
    """Return the current Git Worktree root containing a path."""
    return Path(git(path, "rev-parse", "--show-toplevel")).resolve()


def observe_observation_targets(
    anchors: Sequence[Path],
    *,
    timeout: float = 5,
    runner: CommandRunner = run_command,
    clock: Callable[[], float] = time.monotonic,
) -> ObservationTargetInventory:
    """Discover and inspect executable Observation Targets for Repository Anchors."""
    records: list[dict[str, str]] = []
    diagnostics: list[Diagnostic] = []
    seen_paths: set[str] = set()
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
        for record in _parse_worktree_records(result.stdout):
            path = record.get("worktree")
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
            reason = record["locked"] or "no reason reported"
            target_diagnostics.append(
                Diagnostic(
                    f"target:{path}",
                    "info",
                    f"Observation Target is locked: {reason}",
                    "target-locked",
                )
            )
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
                _unavailable_target(
                    record, branch, detached, target_diagnostics
                )
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
                _unavailable_target(
                    record, branch, detached, target_diagnostics
                )
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
                _unavailable_target(
                    record, branch, detached, target_diagnostics
                )
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
                _unavailable_target(
                    record, branch, detached, target_diagnostics
                )
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
                _unavailable_target(
                    record, branch, detached, target_diagnostics
                )
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
            )
        )
    return ObservationTargetInventory(targets, diagnostics)


def _unavailable_target(
    record: dict[str, str],
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
    return match.group(1) if match else None


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
