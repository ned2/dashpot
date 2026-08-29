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
from datetime import UTC, datetime
from pathlib import Path

from rich.text import Text

from .issue_list import row_key
from .issue_table import relative_age
from .list_pane import ListCell, ListColumn, ListRow, truncate_end, truncate_start
from .model import (
    AgentRun,
    Branch,
    ObservationTarget,
    ProjectObservation,
    WorkspaceSnapshot,
)
from .session_list import PATH_LIMIT, abbreviate_path
from .worktree_list import (
    DIRTY_COLORS,
    SHORT_HEAD,
    UNAVAILABLE_COLORS,
    freshness_cell,
    sessions_cell,
)

NAME_LIMIT = 48
LOCAL_TEXT = "local"
IN_SYNC_TEXT = "in sync"
UNPUSHED_TEXT = "unpushed"
UPSTREAM_GONE_TEXT = "upstream gone"

BRANCH_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("name", "BRANCH"),
    ListColumn("where", "WHERE"),
    ListColumn("sync", "SYNC"),
    ListColumn("head", "HEAD"),
    ListColumn("worktree", "WORKTREE"),
    ListColumn("sessions", "SESSIONS"),
    ListColumn("state", "STATE"),
    ListColumn("commit", "LAST COMMIT"),
)


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

    @property
    def freshness(self) -> str:
        """``available``, or ``stale`` when a failed refresh retained the refs."""
        snapshot = self.project.snapshot
        if snapshot is not None and snapshot.target_status == "stale":
            return "stale"
        return "available"


@dataclass(frozen=True, slots=True)
class BranchListResult:
    rows: tuple[BranchListRow, ...]
    revision: int = 0
    # When the Remote-Tracking Branches were last fetched; Dashpot reports
    # the age rather than fetching.
    fetched_at: str | None = None

    @property
    def count(self) -> int:
        return len(self.rows)


def query_branch_list(
    snapshot: WorkspaceSnapshot, *, revision: int = 0
) -> BranchListResult:
    """Query the Branches pane rows from complete observed state."""
    projects: dict[str, ProjectObservation] = {}
    branches: dict[tuple[str, str], Branch] = {}
    targets: dict[tuple[str, str], ObservationTarget] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for branch in project.snapshot.branches:
            key = (project.project_id, branch.refname)
            if key in branches:
                raise ValueError(
                    f"Duplicate Branch {branch.refname} in {project.project_id}"
                )
            branches[key] = branch
        for target in project.snapshot.observation_targets:
            targets[project.project_id, target.path] = target
    agent_runs: dict[str, AgentRun] = {}
    for run in snapshot.agent_runs:
        if run.id in agent_runs:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        agent_runs[run.id] = run
    return _query_indexed_branch_list(
        projects=projects,
        branches=branches,
        observation_targets=targets,
        agent_runs=agent_runs,
        revision=revision,
    )


def _query_indexed_branch_list(
    *,
    projects: Mapping[str, ProjectObservation],
    branches: Mapping[tuple[str, str], Branch],
    observation_targets: Mapping[tuple[str, str], ObservationTarget],
    agent_runs: Mapping[str, AgentRun],
    revision: int,
) -> BranchListResult:
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
    # Stable sorts, last key first: checked-out branches lead, then the most
    # recent commit, then the name.
    rows.sort(key=lambda row: row.name)
    rows.sort(key=lambda row: row.committed_at, reverse=True)
    rows.sort(key=lambda row: 0 if row.worktrees else 1)
    fetched = [
        project.snapshot.fetched_at
        for project in projects.values()
        if project.snapshot is not None and project.snapshot.fetched_at is not None
    ]
    return BranchListResult(
        tuple(rows), revision, fetched_at=max(fetched, default=None)
    )


def build_branch_rows(
    result: BranchListResult,
    *,
    dark: bool,
    now: datetime | None = None,
    home: Path | None = None,
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    current = now or datetime.now(UTC)
    return tuple(
        ListRow(row.key, branch_cells(row, dark=dark, now=current, home=home))
        for row in result.rows
    )


def branch_cells(
    row: BranchListRow,
    *,
    dark: bool,
    now: datetime,
    home: Path | None = None,
) -> tuple[ListCell, ...]:
    head = row.refs[0].head
    worktree = row.worktrees[0].path if row.worktrees else None
    if worktree is None:
        worktree = next(
            (ref.checked_out_at for ref in row.refs if ref.checked_out_at), None
        )
    return (
        truncate_end(row.name, NAME_LIMIT),
        where_text(row),
        sync_cell(row.local, dark=dark),
        head[:SHORT_HEAD] if head else "-",
        truncate_start(abbreviate_path(worktree, home=home), PATH_LIMIT)
        if worktree
        else "-",
        sessions_cell(tuple(session.state for session in row.sessions), dark=dark),
        freshness_cell(row.freshness, dark=dark),
        relative_age(row.committed_at, now) or "-",
    )


def where_text(row: BranchListRow) -> str:
    """Where the branch exists: ``local``, ``local · origin`` or ``origin``."""
    places: list[str] = [LOCAL_TEXT] if row.local is not None else []
    places.extend(ref.remote or "" for ref in row.remotes)
    return " · ".join(places)


def sync_cell(local: Branch | None, *, dark: bool) -> ListCell:
    """How the local branch relates to its upstream; remote-only rows have none."""
    if local is None:
        return "-"
    if local.upstream_gone:
        return Text(UPSTREAM_GONE_TEXT, style=UNAVAILABLE_COLORS[dark])
    if local.upstream is None:
        return Text(UNPUSHED_TEXT, style=DIRTY_COLORS[dark])
    parts: list[str] = []
    if local.ahead:
        parts.append(f"↑{local.ahead}")
    if local.behind:
        parts.append(f"↓{local.behind}")
    if not parts:
        return IN_SYNC_TEXT
    return Text(" ".join(parts), style=DIRTY_COLORS[dark])


def fetch_age_text(fetched_at: str | None, now: datetime) -> str:
    """``remote as of 3h ago``, or that the repository never fetched."""
    age = relative_age(fetched_at, now)
    return f"remote as of {age}" if age else "never fetched"
