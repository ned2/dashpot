"""The Worktrees pane read model: every observed Observation Target, once.

A row is one Observation Target joined to its Project and to the active Agent
Sessions located at it. Identity is `(Project Identity, target path)`: an
Observation Target is observed state, never Workspace membership, so a row
appears and disappears with the topology Git reports and is never persisted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .issue_list import row_key
from .model import (
    AgentRun,
    ObservationTarget,
    ProjectObservation,
    TargetRole,
    WorkspaceSnapshot,
)

ROLE_ORDER: dict[TargetRole, int] = {"main": 0, "linked": 1}


@dataclass(frozen=True, slots=True)
class WorktreeListRow:
    """One Observation Target with its Project and located sessions joined."""

    key: str
    project: ProjectObservation
    target: ObservationTarget
    anchored: bool
    sessions: tuple[AgentRun, ...] = ()

    @property
    def freshness(self) -> str:
        """``available``, ``unavailable`` or ``stale`` for a retained topology."""
        snapshot = self.project.snapshot
        if snapshot is not None and snapshot.target_status == "stale":
            return "stale"
        return self.target.availability


@dataclass(frozen=True, slots=True)
class WorktreeListResult:
    rows: tuple[WorktreeListRow, ...]
    revision: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)


def query_worktree_list(
    snapshot: WorkspaceSnapshot, *, revision: int = 0
) -> WorktreeListResult:
    """Query the Worktrees pane rows from complete observed state."""
    projects: dict[str, ProjectObservation] = {}
    targets: dict[tuple[str, str], ObservationTarget] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for target in project.snapshot.observation_targets:
            key = (project.project_id, target.path)
            if key in targets:
                raise ValueError(
                    f"Duplicate Observation Target {target.path} in "
                    f"{project.project_id}"
                )
            targets[key] = target
    agent_runs: dict[str, AgentRun] = {}
    for run in snapshot.agent_runs:
        if run.id in agent_runs:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        agent_runs[run.id] = run
    return query_indexed_worktree_list(
        projects=projects,
        observation_targets=targets,
        agent_runs=agent_runs,
        revision=revision,
    )


def query_indexed_worktree_list(
    *,
    projects: Mapping[str, ProjectObservation],
    observation_targets: Mapping[tuple[str, str], ObservationTarget],
    agent_runs: Mapping[str, AgentRun],
    revision: int,
) -> WorktreeListResult:
    sessions_by_target: dict[tuple[str, str | None], list[AgentRun]] = {}
    for run in agent_runs.values():
        sessions_by_target.setdefault(
            (run.observation_project_id, run.observation_target), []
        ).append(run)
    rows: list[WorktreeListRow] = []
    for (project_id, path), target in observation_targets.items():
        project = projects.get(project_id)
        if project is None:
            continue
        rows.append(
            WorktreeListRow(
                row_key("worktree", project_id, path),
                project,
                target,
                anchored=path in project.anchors,
                sessions=tuple(sessions_by_target.get((project_id, path), ())),
            )
        )
    rows.sort(key=_sort_key)
    return WorktreeListResult(tuple(rows), revision)


def _sort_key(row: WorktreeListRow) -> tuple[int, str]:
    """Main before linked, then path."""
    return (ROLE_ORDER[row.target.role], row.target.path)
