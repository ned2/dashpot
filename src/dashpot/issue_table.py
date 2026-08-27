from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from rich.text import Text

from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    IssueSearchField,
)
from .model import Issue, RunState


ColumnKey = Literal[
    "status",
    "issue_state",
    "number",
    "title",
    "project",
    "priority",
    "assignees",
    "created",
    "last_action",
    "sessions",
]

IssueStateKind = Literal[
    "open",
    "completed",
    "not-planned",
    "duplicate",
]

GITHUB_ISSUE_STATE_COLORS: dict[IssueStateKind, tuple[str, str]] = {
    "open": ("#1f883d", "#238636"),
    "completed": ("#8250df", "#8957e5"),
    "not-planned": ("#59636e", "#656c76"),
    "duplicate": ("#59636e", "#656c76"),
}


class IssueTableCell(str):
    """A rendered table value that retains its domain sort value."""

    sort_value: object

    def __new__(cls, text: str, sort_value: object) -> IssueTableCell:
        cell = super().__new__(cls, text)
        cell.sort_value = sort_value
        return cell


class IssueStateCell(Text):
    """A semantic Issue-state value rendered as a colored block."""

    __slots__ = ("sort_value", "state_kind")

    def __init__(self, state_kind: IssueStateKind, *, dark: bool) -> None:
        light_color, dark_color = GITHUB_ISSUE_STATE_COLORS[state_kind]
        super().__init__("■", style=dark_color if dark else light_color)
        self.state_kind = state_kind
        self.sort_value = (
            "open",
            "completed",
            "not-planned",
            "duplicate",
        ).index(state_kind)


TableCell = IssueTableCell | IssueStateCell


def _cell_sort_key(value: object) -> object:
    if isinstance(value, (IssueTableCell, IssueStateCell)):
        return value.sort_value
    return value


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: ColumnKey
    label: str
    update_width: bool = False
    search_field: IssueSearchField | None = None
    sort_key: Callable[[object], object] = _cell_sort_key
    nulls_last: bool = False


COLUMN_SPECS = (
    ColumnSpec("status", "S"),
    ColumnSpec("issue_state", "STATUS"),
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
    ColumnSpec("created", "CREATED", nulls_last=True),
    ColumnSpec("last_action", "LAST ACTION", nulls_last=True),
    ColumnSpec("sessions", "SESSIONS"),
)
COLUMN_KEYS: tuple[ColumnKey, ...] = tuple(spec.key for spec in COLUMN_SPECS)
DEFAULT_COLUMNS: tuple[ColumnKey, ...] = tuple(
    key for key in COLUMN_KEYS if key not in {"project", "created"}
)
COLUMNS_BY_KEY = {spec.key: spec for spec in COLUMN_SPECS}


@dataclass(frozen=True, slots=True)
class SortTerm:
    column: ColumnKey
    descending: bool = False


DEFAULT_SORT = (
    SortTerm("last_action", descending=True),
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


def cells_match(left: TableCell, right: TableCell) -> bool:
    if isinstance(left, IssueStateCell) and isinstance(right, IssueStateCell):
        return (
            left.state_kind == right.state_kind
            and left.style == right.style
            and left.sort_value == right.sort_value
        )
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
            _term_sort_value(spec, term, cell)
            for spec, term, cell in zip(specs, terms, values)
        )

    return sort_key


def _term_sort_value(
    spec: ColumnSpec, term: SortTerm, cell: object
) -> object:
    value = spec.sort_key(cell)
    if not spec.nulls_last:
        return value
    missing = value is None
    if term.descending:
        return (0 if missing else 1, 0 if missing else value)
    return (1 if missing else 0, 0 if missing else value)


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
    sort: tuple[SortTerm, ...] = (),
    dark: bool = True,
) -> tuple[dict[str, IssueListRow], dict[str, tuple[TableCell, ...]]]:
    """Render queried rows into the requested presentation schema."""
    projected = [
        (row, _row_values(row, dark=dark)) for row in result.rows
    ]
    if sort:
        directions = {term.descending for term in sort}
        if len(directions) != 1:
            raise ValueError("Issue table sort terms must share one direction")
        projected.sort(key=lambda item: _row_tie_break(item[0]))
        projected.sort(
            key=lambda item: sort_key_for_terms(sort)(
                tuple(item[1][term.column] for term in sort)
            ),
            reverse=sort[0].descending,
        )

    contexts: dict[str, IssueListRow] = {}
    cells_by_key: dict[str, tuple[TableCell, ...]] = {}
    for row, values in projected:
        contexts[row.key] = row
        cells_by_key[row.key] = tuple(values[column] for column in columns)
    return contexts, cells_by_key


def _row_tie_break(row: IssueListRow) -> tuple[str, int, str]:
    number = row.issue["number"] if row.issue is not None else 2**63 - 1
    return row.project.project_id.casefold(), number, row.key


def _row_values(row: IssueListRow, *, dark: bool) -> dict[ColumnKey, TableCell]:
    project = row.project
    if row.kind == "project":
        return {
            "status": status_cell(project.status),
            "issue_state": IssueTableCell("-", 99),
            "number": IssueTableCell("-", float("inf")),
            "title": text_cell(row.empty_message or "no Issues"),
            "project": text_cell(project.display_label),
            "priority": IssueTableCell("-", 99),
            "assignees": IssueTableCell("unassigned", ()),
            "created": date_cell(None),
            "last_action": date_cell(None),
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
            "issue_state": issue_state_cell(issue, dark=dark),
            "number": IssueTableCell(
                f"#{issue['number']}", issue["number"]
            ),
            "title": text_cell(issue["title"]),
            "project": text_cell(project.display_label),
            "priority": IssueTableCell(priority, int(priority[1:])),
            "assignees": IssueTableCell(
                ", ".join(issue["assignees"]) or "unassigned", assignees
            ),
            "created": date_cell(issue["createdAt"]),
            "last_action": date_cell(issue["updatedAt"]),
            "sessions": run_summary_cell(row.session_states),
        }
    run = row.run
    if run is None:
        raise RuntimeError("Issue-list Agent Run row is missing its Agent Run")
    return {
        "status": run_state_cell(run.state),
        "issue_state": IssueTableCell("-", 99),
        "number": IssueTableCell("-", float("inf")),
        "title": text_cell(f"Unmatched {run.harness} run"),
        "project": text_cell(project.display_label),
        "priority": IssueTableCell("-", 99),
        "assignees": IssueTableCell("unassigned", ()),
        "created": date_cell(None),
        "last_action": date_cell(None),
        "sessions": IssueTableCell(run.state, run_state_counts((run.state,))),
    }


def text_cell(value: str) -> IssueTableCell:
    return IssueTableCell(value, value.casefold())


def date_cell(timestamp: str | None) -> IssueTableCell:
    if timestamp is None:
        return IssueTableCell("-", None)
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return IssueTableCell(instant.date().isoformat(), instant.timestamp())


def status_cell(status: str) -> IssueTableCell:
    rank = {"fresh": 0, "stale": 1, "unavailable": 2}.get(status, 3)
    return IssueTableCell(status_mark(status), rank)


def issue_state_kind(issue: Issue) -> IssueStateKind:
    if issue["state"] == "open":
        return "open"
    return {
        "not-planned": "not-planned",
        "duplicate": "duplicate",
    }.get(issue["stateReason"], "completed")


def issue_state_cell(issue: Issue, *, dark: bool) -> IssueStateCell:
    return IssueStateCell(issue_state_kind(issue), dark=dark)


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
