"""The Worktrees pane read model: every observed Observation Target, once.

A row is one Observation Target joined to its Project and to the active Agent
Sessions located at it. Identity is `(Project Identity, target path)`: an
Observation Target is observed state, never Workspace membership, so a row
appears and disappears with the topology Git reports and is never persisted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..core.model import (
    AgentRun,
    ObservationTarget,
    ProjectObservation,
    TargetRole,
)
from .issue_list import row_key
from .list_result import ListResult

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


def query_indexed_worktree_list(
    *,
    projects: Mapping[str, ProjectObservation],
    observation_targets: Mapping[tuple[str, str], ObservationTarget],
    agent_runs: Mapping[str, AgentRun],
    revision: int,
) -> ListResult[WorktreeListRow, None]:
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
    return ListResult(rows=tuple(rows), summary=None, revision=revision)


def _sort_key(row: WorktreeListRow) -> tuple[int, str]:
    """Main before linked, then path."""
    return (ROLE_ORDER[row.target.role], row.target.path)
