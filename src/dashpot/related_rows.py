"""Select visible relationships from accepted pane read models."""

from collections.abc import Sequence
from dataclasses import dataclass

from .branch_list import BranchListRow
from .issue_list import IssueListRow
from .worktree_list import WorktreeListRow


@dataclass(frozen=True, slots=True)
class RelatedRows:
    worktrees: frozenset[str]
    branches: frozenset[str]
    issues: frozenset[str]


def query_related_rows(
    run_id: str | None,
    *,
    worktrees: Sequence[WorktreeListRow],
    branches: Sequence[BranchListRow],
    issues: Sequence[IssueListRow],
) -> RelatedRows:
    """Identify rows whose accepted membership includes the inspected Agent Session."""
    return RelatedRows(
        frozenset(
            row.key
            for row in worktrees
            if any(run.id == run_id for run in row.sessions)
        ),
        frozenset(
            row.key for row in branches if any(run.id == run_id for run in row.sessions)
        ),
        frozenset(
            row.key
            for row in issues
            if any(run.id == run_id for run in row.observed_runs)
        ),
    )
