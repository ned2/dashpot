"""Select visible relationships from accepted pane read models."""

from collections.abc import Sequence
from dataclasses import dataclass

from .branch_list import BranchListRow
from .issue_list import IssueListRow
from .session_list import SessionListRow
from .worktree_list import WorktreeListRow


@dataclass(frozen=True, slots=True)
class RelatedRows:
    worktrees: frozenset[str]
    branches: frozenset[str]
    issues: frozenset[str]
    sessions: frozenset[str]


FocusedSource = SessionListRow | WorktreeListRow | BranchListRow | IssueListRow


def query_related_rows(
    source: FocusedSource | None,
    *,
    worktrees: Sequence[WorktreeListRow],
    branches: Sequence[BranchListRow],
    issues: Sequence[IssueListRow],
    sessions: Sequence[SessionListRow],
) -> RelatedRows:
    """Identify direct destinations of the focused row within one accepted checkpoint."""
    if isinstance(source, SessionListRow):
        runs = (source.session,)
    elif isinstance(source, (WorktreeListRow, BranchListRow)):
        runs = source.sessions
    elif isinstance(source, IssueListRow):
        runs = source.observed_runs
    else:
        runs = ()
    run_ids = {run.id for run in runs}

    def topology(worktree: WorktreeListRow, branch: BranchListRow) -> bool:
        """Match accepted checked-out topology within its Project."""
        return (
            worktree.project.project_id == branch.project.project_id
            and worktree.target.availability == "available"
            and not worktree.target.detached
            and worktree.target.branch == branch.name
            and any(
                target.path == worktree.target.path
                and target.availability == "available"
                and not target.detached
                for target in branch.worktrees
            )
        )

    return RelatedRows(
        frozenset(
            row.key
            for row in worktrees
            if not isinstance(source, WorktreeListRow)
            and row.target.availability == "available"
            and (
                topology(row, source)
                if isinstance(source, BranchListRow)
                else any(run.id in run_ids for run in row.sessions)
            )
        ),
        frozenset(
            row.key
            for row in branches
            if not isinstance(source, BranchListRow)
            and (
                topology(source, row)
                if isinstance(source, WorktreeListRow)
                else any(run.id in run_ids for run in row.sessions)
            )
        ),
        frozenset(
            row.key
            for row in issues
            if not isinstance(source, IssueListRow)
            and any(run.id in run_ids for run in row.observed_runs)
        ),
        frozenset(
            row.key
            for row in sessions
            if not isinstance(source, SessionListRow) and row.session.id in run_ids
        ),
    )
