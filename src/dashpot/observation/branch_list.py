"""The Branches pane read model: every Branch of the Project, once by name.

A local branch and its Remote-Tracking Branches are separate observed refs;
this read model joins them into one row per branch name, so a branch that is
only local (never pushed) or only remote (pushed from elsewhere) is a fact on
the row rather than a second row or a second pane. Identity is
`(Project Identity, branch name)`: a Branch is observed state, never persisted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..core.model import (
    AgentRun,
    Branch,
    IntegrationState,
    ObservationTarget,
    ProjectObservation,
    integration_state,
)
from .issue_list import row_key
from .list_result import ListResult


@dataclass(frozen=True, slots=True)
class BranchListRow:
    """One branch name with its local ref, remote refs and locations joined."""

    key: str
    project: ProjectObservation
    name: str
    local: Branch | None
    remotes: tuple[Branch, ...] = ()
    worktrees: tuple[ObservationTarget, ...] = ()
    sessions: tuple[AgentRun, ...] = ()

    @property
    def refs(self) -> tuple[Branch, ...]:
        return ((self.local,) if self.local is not None else ()) + self.remotes

    @property
    def committed_at(self) -> str:
        """The newest commit across the refs, which is the row's recency."""
        return max(ref.committed_at for ref in self.refs)


@dataclass(frozen=True, slots=True)
class BranchListSummary:
    fetched_at: str | None = None
    integration_refs: tuple[str, ...] = ()


def query_indexed_branch_list(
    *,
    projects: Mapping[str, ProjectObservation],
    branches: Mapping[tuple[str, str], Branch],
    observation_targets: Mapping[tuple[str, str], ObservationTarget],
    agent_runs: Mapping[str, AgentRun],
    revision: int,
) -> ListResult[BranchListRow, BranchListSummary]:
    locals_by_name: dict[tuple[str, str], Branch] = {}
    remotes_by_name: dict[tuple[str, str], list[Branch]] = {}
    for (project_id, _refname), branch in branches.items():
        key = (project_id, branch.name)
        if branch.remote is None:
            locals_by_name[key] = branch
        else:
            remotes_by_name.setdefault(key, []).append(branch)
    targets_by_branch: dict[tuple[str, str | None], list[ObservationTarget]] = {}
    for (project_id, _path), target in observation_targets.items():
        targets_by_branch.setdefault((project_id, target.branch), []).append(target)
    sessions_by_branch: dict[tuple[str, str | None], list[AgentRun]] = {}
    for run in agent_runs.values():
        sessions_by_branch.setdefault(
            (run.observation_project_id, run.branch), []
        ).append(run)

    rows: list[BranchListRow] = []
    for key in locals_by_name.keys() | remotes_by_name.keys():
        project_id, name = key
        project = projects.get(project_id)
        if project is None:
            continue
        remotes = tuple(
            sorted(remotes_by_name.get(key, ()), key=lambda ref: ref.remote or "")
        )
        rows.append(
            BranchListRow(
                row_key("branch", project_id, name),
                project,
                name,
                locals_by_name.get(key),
                remotes=remotes,
                worktrees=tuple(targets_by_branch.get((project_id, name), ())),
                sessions=tuple(sessions_by_branch.get((project_id, name), ())),
            )
        )
    # Stable sorts, last key first: the Integration Branch leads, then
    # checked-out branches, the most recent commit, and the name.
    rows.sort(key=lambda row: row.name)
    rows.sort(key=lambda row: row.committed_at, reverse=True)
    rows.sort(key=lambda row: 0 if row.worktrees else 1)
    rows.sort(key=lambda row: 0 if _is_integration_branch(row) else 1)
    fetched = [
        project.snapshot.fetched_at
        for project in projects.values()
        if project.snapshot is not None and project.snapshot.fetched_at is not None
    ]
    integration_refs = sorted(
        {
            project.snapshot.integration_ref
            for project in projects.values()
            if project.snapshot is not None
            and project.snapshot.integration_ref is not None
        }
    )
    return ListResult(
        rows=tuple(rows),
        revision=revision,
        summary=BranchListSummary(
            fetched_at=max(fetched, default=None),
            integration_refs=tuple(integration_refs),
        ),
    )


def _is_integration_branch(row: BranchListRow) -> bool:
    """Identify the row carrying its Project's Integration Branch."""
    snapshot = row.project.snapshot
    return snapshot is not None and any(
        ref.refname == snapshot.integration_ref for ref in row.refs
    )


def integration_summary(row: BranchListRow) -> IntegrationState:
    """Summarize whether every ref the row represents has landed.

    The row stands for its local Branch and each same-name Remote-Tracking
    Branch, so it is integrated only when each of those refs is. Retained
    commits anywhere outrank a missing comparison, and a missing comparison
    outranks every integrated ref, so an integrated local ref never masks
    unintegrated or unknown remote work and missing evidence never reads as
    integrated. Whether the refs share a tip does not matter: refs can
    differ while all their work has landed.
    """
    states = {
        integration_state(ref.unintegrated_commits, ref.content_integrated)
        for ref in row.refs
    }
    if "unintegrated" in states:
        return "unintegrated"
    if "unknown" in states or not states:
        return "unknown"
    if "content-integrated" in states:
        return "content-integrated"
    return "integrated"
