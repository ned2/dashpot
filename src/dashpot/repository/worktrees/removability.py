"""Assess whether a registered Worktree can be removed safely."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ...core.git import Git
from ...core.pydantic import LaxSequence, PublishedModel
from ...core.worktree_paths import worktree_paths, worktree_root
from ...sessions.processes import ProcessLookup, host_process_lookup
from ..cleanup.obstacles import (
    assess_branch_preservation,
    assess_detached_head_preservation,
    assess_worktree_occupancy,
    assess_worktree_safety,
    locate_worktree,
)
from ..cleanup.targets import CleanupBlocker
from ..repository import LockHolderProbe


class WorktreeRemovability(PublishedModel):
    """A read-only report of whether a Worktree can be removed, and why not."""

    path: str
    branch: str | None
    head: str
    role: Literal["main", "linked"]
    removable: bool
    obstacles: LaxSequence[CleanupBlocker] = ()
    remove_commands: LaxSequence[str] = ()


def linked_worktrees(current: Path, *, timeout: float = 10) -> list[Path]:
    """List the linked Worktrees of the Repository ``current`` belongs to.

    The main Worktree is never removable, so a check of every Worktree is a
    check of the linked ones; a bare entry is not a Worktree.
    """
    anchor = worktree_root(current)
    records = Git(anchor, timeout).worktree_records()
    return sorted(worktree_paths(records[1:]))


def check_worktree(
    current: Path,
    target: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    timeout: float = 10,
) -> WorktreeRemovability:
    """Report whether a Worktree could be removed, and each reason it cannot.

    Everything here is observed: Git's dirty state and locks, the Agent
    Sessions whose hooks place them at the Worktree, the Agent Runs recorded
    there, and commits its Branch has that no upstream or Integration Branch has.
    Dashpot removes nothing; each obstacle names the command that acts on it.
    """
    located = locate_worktree(current, target, timeout=timeout)
    git, path = located.git, located.path
    branch = located.branch
    obstacles = assess_worktree_safety(located, lock_probe)
    obstacles.extend(assess_worktree_occupancy(path, located.worktrees, lookup))
    content_integrated = False
    if branch is not None:
        branch_obstacles, content_integrated = assess_branch_preservation(
            git, path, branch
        )
        obstacles.extend(branch_obstacles)
    elif located.detached:
        obstacles.extend(assess_detached_head_preservation(git, located.head))
    remove_commands: tuple[str, ...] = ()
    if located.role == "linked":
        # ``branch -d`` refuses a squash-merged Branch, whose commits are not
        # reachable; the forced form is the command that acts on it.
        delete = "-D" if content_integrated else "-d"
        remove_commands = (f"git worktree remove {path}",) + (
            (f"git branch {delete} {branch}",) if branch else ()
        )
    return WorktreeRemovability(
        path=str(path),
        branch=branch,
        head=located.head,
        role=located.role,
        removable=not obstacles,
        obstacles=tuple(obstacles),
        remove_commands=remove_commands,
    )


def describe_removability(report: WorktreeRemovability) -> list[str]:
    """Render a removability report as lines for a person.

    Field/value lines name the Worktree, its Branch, and the verdict; the
    obstacles and the commands to run are indented beneath them so a block
    scans as one Worktree and the commands stand apart from the facts.
    """
    lines = [
        f"Worktree   {report.path}",
        f"Branch     {report.branch or '(detached)'}",
        f"Removable  {'yes' if report.removable else 'no'}",
    ]
    if report.obstacles:
        lines.append("Obstacles")
        for obstacle in report.obstacles:
            lines.append(f"  - {obstacle.kind}: {obstacle.detail}")
            if obstacle.command:
                lines.append(f"      run: {obstacle.command}")
    if report.removable and report.remove_commands:
        lines.append("Remove with")
        lines.extend(f"  $ {command}" for command in report.remove_commands)
    return lines
