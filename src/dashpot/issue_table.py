from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    IssueSearchField,
)
from .model import Issue, RunState


ColumnKey = Literal[
    "status",
    "number",
    "title",
    "project",
    "priority",
    "assignees",
    "sessions",
]


class IssueTableCell(str):
    """A rendered table value that retains its domain sort value."""

    sort_value: object

    def __new__(cls, text: str, sort_value: object) -> IssueTableCell:
        cell = super().__new__(cls, text)
        cell.sort_value = sort_value
        return cell


def _cell_sort_key(value: object) -> object:
    if isinstance(value, IssueTableCell):
        return value.sort_value
    return value


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: ColumnKey
    label: str
    update_width: bool = False
    search_field: IssueSearchField | None = None
    sort_key: Callable[[object], object] = _cell_sort_key


COLUMN_SPECS = (
    ColumnSpec("status", "S"),
    ColumnSpec(
        "number",
        "ID",
        search_field=IssueSearchField.NUMBER,
    ),
    ColumnSpec(
        "title",
        "TITLE",
        update_width=True,
        search_field=IssueSearchField.TITLE,
    ),
    ColumnSpec(
        "project",
        "PROJECT",
        update_width=True,
        search_field=IssueSearchField.PROJECT,
    ),
    ColumnSpec("priority", "PRI"),
    ColumnSpec(
        "assignees",
        "ASSIGNEES",
        update_width=True,
        search_field=IssueSearchField.ASSIGNEES,
    ),
    ColumnSpec("sessions", "SESSIONS"),
)
COLUMN_KEYS: tuple[ColumnKey, ...] = tuple(spec.key for spec in COLUMN_SPECS)
DEFAULT_COLUMNS: tuple[ColumnKey, ...] = tuple(
    key for key in COLUMN_KEYS if key != "project"
)
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
    columns: tuple[ColumnKey, ...] = DEFAULT_COLUMNS
    sort: tuple[SortTerm, ...] = DEFAULT_SORT

    def __post_init__(self) -> None:
        _validate_columns(self.columns)

    def toggle_sort(self, column: ColumnKey) -> IssueTableViewState:
        if len(self.sort) == 1 and self.sort[0].column == column:
            term = replace(self.sort[0], descending=not self.sort[0].descending)
        else:
            term = SortTerm(column)
        return replace(self, sort=(term,))

    def cycle_sort(self) -> IssueTableViewState:
        current = self.sort[0].column if self.sort else None
        if current in self.columns:
            current_index = self.columns.index(current)
            next_column = self.columns[(current_index + 1) % len(self.columns)]
        elif current in COLUMN_KEYS:
            current_index = COLUMN_KEYS.index(current)
            following_columns = (
                COLUMN_KEYS[current_index + 1 :]
                + COLUMN_KEYS[: current_index + 1]
            )
            next_column = next(
                column
                for column in following_columns
                if column in self.columns
            )
        else:
            next_column = self.columns[0]
        return replace(self, sort=(SortTerm(next_column),))

    def reverse_sort(self) -> IssueTableViewState:
        current = self.sort[0] if self.sort else None
        if current is None or current.column not in self.columns:
            current = SortTerm(self.columns[0])
        return replace(
            self,
            sort=(replace(current, descending=not current.descending),),
        )

    def with_columns(
        self, columns: tuple[ColumnKey, ...]
    ) -> IssueTableViewState:
        return replace(self, columns=columns)


def _validate_columns(columns: tuple[ColumnKey, ...]) -> None:
    if not columns:
        raise ValueError("Issue table requires at least one visible column")
    if len(set(columns)) != len(columns):
        raise ValueError("Issue table columns contain duplicates")
    unknown = tuple(column for column in columns if column not in COLUMNS_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown Issue table columns: {', '.join(unknown)}")


def column_specs(columns: tuple[ColumnKey, ...]) -> tuple[ColumnSpec, ...]:
    return tuple(COLUMNS_BY_KEY[key] for key in columns)


def searchable_columns() -> frozenset[IssueSearchField]:
    return frozenset(
        column.search_field
        for column in COLUMN_SPECS
        if column.search_field is not None
    )


def cells_match(left: str, right: str) -> bool:
    if left != right:
        return False
    if isinstance(left, IssueTableCell) and isinstance(right, IssueTableCell):
        return left.sort_value == right.sort_value
    return type(left) is type(right)


def sort_key_for_terms(
    terms: tuple[SortTerm, ...],
) -> Callable[[object], object]:
    specs = tuple(COLUMNS_BY_KEY[term.column] for term in terms)

    def sort_key(value: object) -> object:
        values = value if isinstance(value, tuple) else (value,)
        return tuple(
            spec.sort_key(cell) for spec, cell in zip(specs, values)
        )

    return sort_key


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
    columns: tuple[ColumnKey, ...] = DEFAULT_COLUMNS,
) -> tuple[dict[str, IssueListRow], dict[str, tuple[IssueTableCell, ...]]]:
    """Render queried rows into the requested presentation schema."""
    contexts: dict[str, IssueListRow] = {}
    cells_by_key: dict[str, tuple[IssueTableCell, ...]] = {}
    for row in result.rows:
        contexts[row.key] = row
        values = _row_values(row)
        cells_by_key[row.key] = tuple(values[column] for column in columns)
    return contexts, cells_by_key


def _row_values(row: IssueListRow) -> dict[ColumnKey, IssueTableCell]:
    project = row.project
    if row.kind == "project":
        return {
            "status": status_cell(project.status),
            "number": IssueTableCell("-", float("inf")),
            "title": text_cell(row.empty_message or "no Issues"),
            "project": text_cell(project.display_label),
            "priority": IssueTableCell("-", 99),
            "assignees": IssueTableCell("unassigned", ()),
            "sessions": IssueTableCell("-", (0, 0, 0, 0)),
        }
    if row.kind == "issue":
        issue = row.issue
        if issue is None:
            raise RuntimeError("Issue-list Issue row is missing its Issue")
        priority = issue_priority(issue)
        assignees = tuple(assignee.casefold() for assignee in issue["assignees"])
        return {
            "status": status_cell(project.status),
            "number": IssueTableCell(
                f"#{issue['number']}", issue["number"]
            ),
            "title": text_cell(issue["title"]),
            "project": text_cell(project.display_label),
            "priority": IssueTableCell(priority, int(priority[1:])),
            "assignees": IssueTableCell(
                ", ".join(issue["assignees"]) or "unassigned", assignees
            ),
            "sessions": run_summary_cell(row.session_states),
        }
    run = row.run
    if run is None:
        raise RuntimeError("Issue-list Agent Run row is missing its Agent Run")
    return {
        "status": run_state_cell(run.state),
        "number": IssueTableCell("-", float("inf")),
        "title": text_cell(f"Unmatched {run.harness} run"),
        "project": text_cell(project.display_label),
        "priority": IssueTableCell("-", 99),
        "assignees": IssueTableCell("unassigned", ()),
        "sessions": IssueTableCell(run.state, run_state_counts((run.state,))),
    }


def text_cell(value: str) -> IssueTableCell:
    return IssueTableCell(value, value.casefold())


def status_cell(status: str) -> IssueTableCell:
    rank = {"fresh": 0, "stale": 1, "unavailable": 2}.get(status, 3)
    return IssueTableCell(status_mark(status), rank)


def run_state_cell(state: str) -> IssueTableCell:
    rank = {"running": 0, "waiting": 1, "unknown": 2}.get(state, 3)
    return IssueTableCell(run_state_mark(state), rank)


def status_mark(status: str) -> str:
    return {"fresh": "●", "stale": "◐", "unavailable": "!"}.get(status, "?")


def run_state_mark(state: str) -> str:
    return {"running": "▶", "waiting": "Ⅱ", "unknown": "?"}.get(state, "?")


def observed_run_summary(states: tuple[RunState, ...]) -> str:
    return str(run_summary_cell(states))


def run_summary_cell(states: tuple[RunState, ...]) -> IssueTableCell:
    counts = run_state_counts(states)
    running, waiting, unknown = counts[1:]
    by_state = {"running": running, "waiting": waiting, "unknown": unknown}
    summary = " ".join(
        f"{run_state_mark(state)}{by_state[state]}"
        for state in ("running", "waiting", "unknown")
        if by_state[state]
    )
    return IssueTableCell(summary or "0", counts)


def run_state_counts(states: tuple[RunState, ...]) -> tuple[int, int, int, int]:
    counts = {"running": 0, "waiting": 0, "unknown": 0}
    for state in states:
        counts[state] += 1
    return (
        len(states),
        counts["running"],
        counts["waiting"],
        counts["unknown"],
    )


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
