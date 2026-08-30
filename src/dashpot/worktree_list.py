"""The Worktrees pane read model: every observed Observation Target, once.

A row is one Observation Target joined to its Project and to the active Agent
Sessions located at it. Identity is `(Project Identity, target path)`: an
Observation Target is observed state, never Workspace membership, so a row
appears and disappears with the topology Git reports and is never persisted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text

from .issue_list import row_key
from .list_pane import ListCell, ListColumn, ListRow, truncate_end, truncate_start
from .model import (
    AgentRun,
    ObservationTarget,
    ProjectObservation,
    RunState,
    TargetRole,
    WorkspaceSnapshot,
)
from .session_list import PATH_LIMIT, STATE_GLYPHS, STATE_ORDER, abbreviate_path

BRANCH_LIMIT = 24
SHORT_HEAD = 7
ROLE_ORDER: dict[TargetRole, int] = {"main": 0, "linked": 1}
# GitHub Primer emphasis colours for the working-tree and availability
# states; each pair is (light theme, dark theme).
DIRTY_COLORS = ("#9a6700", "#d29922")
UNAVAILABLE_COLORS = ("#cf222e", "#f85149")
STALE_COLORS = ("#9a6700", "#d29922")

WORKTREE_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("path", "PATH"),
    ListColumn("kind", "KIND"),
    ListColumn("branch", "BRANCH"),
    ListColumn("tree", "TREE"),
    ListColumn("sessions", "SESSIONS"),
)


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
    return _query_indexed_worktree_list(
        projects=projects,
        observation_targets=targets,
        agent_runs=agent_runs,
        revision=revision,
    )


def _query_indexed_worktree_list(
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


def build_worktree_rows(
    result: WorktreeListResult, *, dark: bool, home: Path | None = None
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    return tuple(
        ListRow(
            row.key,
            worktree_cells(row, dark=dark, home=home),
        )
        for row in result.rows
    )


def worktree_cells(
    row: WorktreeListRow, *, dark: bool, home: Path | None = None
) -> tuple[ListCell, ...]:
    target = row.target
    return (
        path_cell(row, dark=dark, home=home),
        target.role,
        branch_cell(target),
        tree_cell(target.dirty, dark=dark),
        sessions_cell(tuple(session.state for session in row.sessions), dark=dark),
    )


def path_cell(
    row: WorktreeListRow, *, dark: bool, home: Path | None = None
) -> ListCell:
    """Show the path with exceptional freshness when observation failed."""
    path = truncate_start(abbreviate_path(row.target.path, home=home), PATH_LIMIT)
    freshness = row.freshness
    if freshness == "available":
        return path
    cell = Text(f"{path} · ")
    cell.append(freshness, style=freshness_color(freshness, dark=dark))
    return cell


def branch_cell(target: ObservationTarget) -> str:
    """Show a Branch name, or the useful short HEAD for a detached checkout."""
    if target.branch is not None:
        return truncate_end(target.branch, BRANCH_LIMIT)
    head = target.head[:SHORT_HEAD]
    return f"detached @ {head}" if head else "detached"


def tree_cell(dirty: bool | None, *, dark: bool) -> ListCell:
    if dirty is None:
        return Text("unknown", style="dim")
    if dirty:
        return Text("dirty", style=DIRTY_COLORS[dark])
    return "clean"


def freshness_color(freshness: str, *, dark: bool) -> str:
    """Choose emphasis for freshness that points at the target's Diagnostics."""
    if freshness == "unavailable":
        return UNAVAILABLE_COLORS[dark]
    return STALE_COLORS[dark]


def sessions_cell(states: Sequence[RunState], *, dark: bool) -> ListCell:
    """How many sessions are located here, led by the liveliest state."""
    if not states:
        return "-"
    state = min(states, key=lambda item: STATE_ORDER[item])
    glyph = STATE_GLYPHS[state]
    return Text(f"{glyph.symbol} {len(states)}", style=glyph.style(dark=dark))
