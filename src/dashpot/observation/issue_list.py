"""The Issues pane read model: every visible Issue of the Project, once.

A row is one Issue of an accepted Query Page or Resolved Issue, joined to
its Project, its bound Agent Runs and their states, with the auxiliary facts
its source observed beside it. The Issue facts a row is ordered by come
from ``issues.ordering``, which a source that orders locally consults too;
the rendered values themselves live in ``issue_cells``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from ..core.issue_profile import IssueProfile
from ..core.model import (
    AgentRun,
    OpenBlocker,
    ProjectObservation,
    SessionActivity,
)
from ..issues.lifecycle import Lifecycle
from ..issues.ordering import (
    IssueSortColumn,
    SortValue,
    issue_sort_value,
    sort_by_column,
)
from ..issues.search import parse_search
from ..queries.pages import AuxiliaryObservation


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    lifecycle: Lifecycle = "open"
    text: str = ""


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    project: ProjectObservation
    issue: IssueProfile
    observed_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[SessionActivity, ...] = ()
    auxiliary: AuxiliaryObservation | None = None
    related_issues: tuple[IssueProfile, ...] = ()


def row_open_blockers(row: IssueListRow) -> tuple[OpenBlocker, ...] | None:
    """The row's Open Blockers, or nothing when they were not observed.

    A row carries them in the auxiliary facts its source observed.
    """
    if row.auxiliary is None or row.auxiliary.open_blockers is None:
        return None
    return tuple(row.auxiliary.open_blockers)


def is_waiting(row: IssueListRow) -> bool:
    """Tell whether the row's Issue is open and waits on some Open Blocker."""
    return row.issue.state == "open" and bool(row_open_blockers(row))


@dataclass(frozen=True, slots=True)
class IssueListSummary:
    matched_issue_count: int
    observed_issue_count: int
    open_issue_count: int = 0
    closed_issue_count: int = 0


def worker_states(
    agent_runs: Iterable[AgentRun], issue_id: str
) -> tuple[SessionActivity, ...]:
    """The observed states of every Worker assigned to the Issue, by any Lead.

    A Worker counts toward the Issue it was assigned to, never its Lead's,
    and only while its Lead's hook records report it (ADR 0096): an
    assignment alone shows nothing.
    """
    return tuple(
        worker.state
        for run in agent_runs
        for worker in run.workers
        if worker.issue_id == issue_id and worker.state is not None
    )


def row_key(kind: str, *identities: str) -> str:
    """Encode opaque identities into an unambiguous row key."""
    return json.dumps([kind, *identities], ensure_ascii=False, separators=(",", ":"))


def empty_issue_message(query: IssueListQuery) -> str:
    """Explain an empty Issue list in terms of the active query."""
    if parse_search(query.text).terms:
        return "no Issues match the current filters"
    if query.lifecycle == "all":
        return "no Issues"
    if query.lifecycle == "ready":
        return "no Ready Issues"
    return f"no {query.lifecycle} Issues"


def unobserved_auxiliary(row: IssueListRow) -> str:
    """Say why a row lacks an auxiliary fact: never fetched, or failed."""
    if row.auxiliary is not None and row.auxiliary.status == "unavailable":
        return "unavailable"
    return "not fetched"


def row_sort_value(row: IssueListRow, column: IssueSortColumn) -> SortValue:
    """Derive the value ``column`` orders the row by, or nothing when it has none."""
    return issue_sort_value(
        row.issue, row.project, column, comment_count=_comment_count(row)
    )


def sort_issue_rows(
    rows: Iterable[IssueListRow], column: IssueSortColumn, *, descending: bool = False
) -> list[IssueListRow]:
    """Order rows by one column, ties by Project, Issue Number and key."""
    return sort_by_column(
        rows,
        value=lambda row: row_sort_value(row, column),
        tie_break=row_tie_break,
        descending=descending,
    )


def row_tie_break(row: IssueListRow) -> tuple[str, int, str]:
    """Order rows that share a sort value by Project, Issue Number and key."""
    return row.project.project_id.casefold(), row.issue.number, row.key


def _comment_count(row: IssueListRow) -> int | None:
    # A row whose activity was never fetched has no count to order by; the
    # table shows ``not fetched`` there.
    if row.auxiliary is not None and row.auxiliary.activity is not None:
        return row.auxiliary.activity.comment_count
    return None
