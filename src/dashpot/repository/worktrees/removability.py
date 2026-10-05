"""Assess whether a registered Worktree can be removed safely."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ...core.git import Git
from ...core.pydantic import LaxSequence, PublishedModel
from ...core.shell import shell_command
from ...core.worktree_paths import worktree_paths, worktree_root
from ...sessions.processes import ProcessLookup, host_process_lookup
from ...sessions.working_directories import ProcessScan
from ..cleanup.obstacles import (
    assess_branch_preservation,
    assess_worktree,
    locate_worktree,
)
from ..cleanup.preview import SUB_AGENT_SCOPE, ignored_consequence
from ..cleanup.targets import CleanupBlocker


class WorktreeRemovability(PublishedModel):
    """A read-only report of whether a Worktree can be removed, and why not.

    ``unchecked_processes`` says why the processes inside the Worktree could
    not all be checked, when they could not (ADR 0104). ``ignored`` lists
    the ignored paths an unforced removal deletes with it, as the Cleanup
    preview does.
    """

    path: str
    branch: str | None
    head: str
    role: Literal["main", "linked"]
    removable: bool
    obstacles: LaxSequence[CleanupBlocker] = ()
    remove_commands: LaxSequence[str] = ()
    unchecked_processes: str | None = None
    ignored: LaxSequence[str] = ()


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
    protected: Sequence[Path] = (),
    timeout: float = 10,
    scan: ProcessScan | None = None,
) -> WorktreeRemovability:
    """Report whether a Worktree could be removed, and each reason it cannot.

    The Worktree is assessed by the sequence the Cleanup preview applies,
    so ``protected`` names the checkouts a Cleanup never removes, and a
    Worktree reported removable is one a Cleanup would offer. Its Branch is
    then held to more: commits it has that no upstream or Integration
    Branch has are obstacles too, since the remove commands delete it.
    Dashpot removes nothing; each obstacle names the command that acts on it.
    """
    located = locate_worktree(current, target, timeout=timeout)
    git, path = located.git, located.path
    branch = located.branch
    assessment = assess_worktree(located, lookup=lookup, protected=protected, scan=scan)
    obstacles = list(assessment.blockers)
    content_integrated = False
    if branch is not None:
        branch_obstacles, content_integrated = assess_branch_preservation(
            git, path, branch
        )
        obstacles.extend(branch_obstacles)
    remove_commands: tuple[str, ...] = ()
    if located.role == "linked":
        # ``branch -d`` refuses a squash-merged Branch, whose commits are not
        # reachable; the forced form is the command that acts on it.
        delete = "-D" if content_integrated else "-d"
        remove_commands = (shell_command("git", "worktree", "remove", path),) + (
            (shell_command("git", "branch", delete, branch),) if branch else ()
        )
    return WorktreeRemovability(
        path=str(path),
        branch=branch,
        head=located.head,
        role=located.role,
        removable=not obstacles,
        obstacles=tuple(obstacles),
        remove_commands=remove_commands,
        unchecked_processes=assessment.unchecked_processes,
        ignored=assessment.ignored,
    )


def describe_removability(report: WorktreeRemovability) -> list[str]:
    """Render a removability report as lines for a person.

    Field/value lines name the Worktree, its Branch, and the verdict; the
    obstacles and the commands to run are indented beneath them so a block
    scans as one Worktree and the commands stand apart from the facts. A
    removable verdict carries the occupancy gaps the Cleanup preview states
    (#357, ADR 0104), aligned beneath it; a blocked one claims no absence of
    occupants.
    """
    lines = [
        f"Worktree   {report.path}",
        f"Branch     {report.branch or '(detached)'}",
        f"Removable  {'yes' if report.removable else 'no'}",
    ]
    if report.removable:
        lines.append(f"           {SUB_AGENT_SCOPE}")
        if report.unchecked_processes:
            lines.append(f"           {report.unchecked_processes}")
    if report.obstacles:
        lines.append("Obstacles")
        for obstacle in report.obstacles:
            lines.append(f"  - {obstacle.kind}: {obstacle.detail}")
            if obstacle.command:
                lines.append(f"      run: {obstacle.command}")
    if report.removable and report.remove_commands:
        lines.append("Remove with")
        lines.extend(f"  $ {command}" for command in report.remove_commands)
        if report.ignored:
            lines.append(f"  which {ignored_consequence(len(report.ignored))}")
    return lines
