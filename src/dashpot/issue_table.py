from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .issue_list import IssueListQuery, IssueListResult, IssueListRow
from .model import Issue, RunState


ColumnKey = Literal[
    "status",
    "project",
    "priority",
    "assignees",
    "sessions",
    "title",
]


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: ColumnKey
    label: str
    update_width: bool = False


COLUMN_SPECS = (
    ColumnSpec("status", "S"),
    ColumnSpec("project", "PROJECT", update_width=True),
    ColumnSpec("priority", "PRI"),
    ColumnSpec("assignees", "ASSIGNEES", update_width=True),
    ColumnSpec("sessions", "SESSIONS"),
    ColumnSpec("title", "TITLE", update_width=True),
)
COLUMN_KEYS: tuple[ColumnKey, ...] = tuple(spec.key for spec in COLUMN_SPECS)
COLUMNS_BY_KEY = {spec.key: spec for spec in COLUMN_SPECS}


@dataclass(frozen=True, slots=True)
class SortTerm:
    column: ColumnKey
    descending: bool = False


DEFAULT_SORT = (
    SortTerm("project"),
    SortTerm("priority"),
    SortTerm("title"),
)


@dataclass(frozen=True, slots=True)
class IssueTableViewState:
    query: IssueListQuery = IssueListQuery()
    columns: tuple[ColumnKey, ...] = COLUMN_KEYS
    sort: tuple[SortTerm, ...] = DEFAULT_SORT

    def toggle_sort(self, column: ColumnKey) -> IssueTableViewState:
        if len(self.sort) == 1 and self.sort[0].column == column:
            term = replace(self.sort[0], descending=not self.sort[0].descending)
        else:
            term = SortTerm(column)
        return replace(self, sort=(term,))


def column_specs(columns: tuple[ColumnKey, ...]) -> tuple[ColumnSpec, ...]:
    return tuple(COLUMNS_BY_KEY[key] for key in columns)


def column_label(column: ColumnSpec, sort: tuple[SortTerm, ...]) -> str:
    term = next((term for term in sort if term.column == column.key), None)
    if term is None:
        marker = "↕"
    else:
        marker = "↓" if term.descending else "↑"
    return f"{column.label} {marker}"


def build_rows(
    result: IssueListResult,
    *,
    columns: tuple[ColumnKey, ...] = COLUMN_KEYS,
) -> tuple[dict[str, IssueListRow], dict[str, tuple[str, ...]]]:
    """Render queried rows into the requested presentation schema."""
    contexts: dict[str, IssueListRow] = {}
    cells_by_key: dict[str, tuple[str, ...]] = {}
    for row in result.rows:
        contexts[row.key] = row
        values = _row_values(row)
        cells_by_key[row.key] = tuple(values[column] for column in columns)
    return contexts, cells_by_key


def _row_values(row: IssueListRow) -> dict[ColumnKey, str]:
    project = row.project
    if row.kind == "project":
        return {
            "status": status_mark(project.status),
            "project": project.display_label,
            "priority": "-",
            "assignees": "unassigned",
            "sessions": "-",
            "title": row.empty_message or "no Issues",
        }
    if row.kind == "issue":
        issue = row.issue
        if issue is None:
            raise RuntimeError("Issue-list Issue row is missing its Issue")
        return {
            "status": status_mark(project.status),
            "project": project.display_label,
            "priority": issue_priority(issue),
            "assignees": ", ".join(issue["assignees"]) or "unassigned",
            "sessions": observed_run_summary(row.session_states),
            "title": issue["title"],
        }
    run = row.run
    if run is None:
        raise RuntimeError("Issue-list Agent Run row is missing its Agent Run")
    return {
        "status": run_state_mark(run.state),
        "project": project.display_label,
        "priority": "-",
        "assignees": "unassigned",
        "sessions": run.state,
        "title": f"Unmatched {run.harness} run",
    }


def status_mark(status: str) -> str:
    return {"fresh": "●", "stale": "◐", "unavailable": "!"}.get(status, "?")


def run_state_mark(state: str) -> str:
    return {"running": "▶", "waiting": "Ⅱ", "unknown": "?"}.get(state, "?")


def observed_run_summary(states: tuple[RunState, ...]) -> str:
    counts = {"running": 0, "waiting": 0, "unknown": 0}
    for state in states:
        counts[state] += 1
    summary = " ".join(
        f"{run_state_mark(state)}{counts[state]}"
        for state in ("running", "waiting", "unknown")
        if counts[state]
    )
    return summary or "0"


def issue_priority(issue: Issue) -> str:
    priorities = {
        "priority/p0": "P0",
        "priority/p1": "P1",
        "priority/p2": "P2",
        "priority/p3": "P3",
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }
    values = [
        priorities[label.casefold()]
        for label in issue["labels"]
        if label.casefold() in priorities
    ]
    return min(values, default="P2")
