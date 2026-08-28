from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Self, TypeAlias, cast

from rich.text import Text

from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    IssueSearchField,
)
from .model import Issue, IssueActivity, ProjectObservation, RunState

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

# What a column yields for ordering: something Python can compare, or nothing.
SortValue: TypeAlias = "SupportsRichComparison | None"

ColumnKey = Literal[
    "issue_state",
    "agent_state",
    "number",
    "title",
    "labels",
    "project",
    "priority",
    "assignees",
    "author",
    "milestone",
    "type",
    "comments",
    "created",
    "last_action",
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

    sort_value: SortValue

    def __new__(cls, text: str, sort_value: SortValue) -> Self:
        cell = super().__new__(cls, text)
        cell.sort_value = sort_value
        return cell


class IssueStateCell(Text):
    """A semantic Issue-state value rendered as a colored block."""

    __slots__ = ("sort_value", "state_kind")

    sort_value: SortValue

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


# Chip colour for labels whose tracker supplies no palette.
NEUTRAL_LABEL_COLOR = "6e7781"


class LabelsCell(Text):
    """Issue labels rendered as coloured chips, like a tracker's feed."""

    __slots__ = ("labels", "sort_value")

    sort_value: SortValue

    def __init__(
        self,
        labels: tuple[str, ...],
        colors: Mapping[str, str],
    ) -> None:
        super().__init__(no_wrap=True)
        self.labels = labels
        self.sort_value = (
            tuple(label.casefold() for label in labels) if labels else None
        )
        append_label_chips(self, labels, colors)


def label_chips(labels: Sequence[str], colors: Mapping[str, str]) -> Text:
    """Labels as coloured chips that may wrap, for detail panes."""
    return append_label_chips(Text(), tuple(labels), colors)


def append_label_chips(
    text: Text, labels: tuple[str, ...], colors: Mapping[str, str]
) -> Text:
    for index, label in enumerate(labels):
        if index:
            text.append(" ")
        background = colors.get(label, NEUTRAL_LABEL_COLOR)
        text.append(
            f" {label} ",
            style=f"{chip_foreground(background)} on #{background}",
        )
    if not labels:
        text.append("-")
    return text


def chip_foreground(background: str) -> str:
    """Black or white text, whichever reads better on the chip colour."""
    red, green, blue = (
        int(background[index : index + 2], 16) / 255 for index in (0, 2, 4)
    )
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#000000" if luminance > 0.55 else "#ffffff"


TableCell = IssueTableCell | IssueStateCell | LabelsCell


def _cell_sort_key(value: object) -> SortValue:
    if isinstance(value, (IssueTableCell, IssueStateCell, LabelsCell)):
        return value.sort_value
    return cast("SortValue", value)


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: ColumnKey
    label: str
    update_width: bool = False
    search_field: IssueSearchField | None = None
    sort_key: Callable[[object], SortValue] = _cell_sort_key
    nulls_last: bool = False


COLUMN_SPECS = (
    ColumnSpec("issue_state", "◉"),
    ColumnSpec("agent_state", "AGENT"),
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
        "labels",
        "LABELS",
        update_width=True,
        search_field=IssueSearchField.LABELS,
        nulls_last=True,
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
    ColumnSpec(
        "author",
        "AUTHOR",
        update_width=True,
        search_field=IssueSearchField.AUTHOR,
        nulls_last=True,
    ),
    ColumnSpec(
        "milestone",
        "MILESTONE",
        update_width=True,
        search_field=IssueSearchField.MILESTONE,
        nulls_last=True,
    ),
    ColumnSpec(
        "type",
        "TYPE",
        update_width=True,
        search_field=IssueSearchField.TYPE,
        nulls_last=True,
    ),
    ColumnSpec("comments", "COMMENTS"),
    ColumnSpec("created", "CREATED", nulls_last=True),
    ColumnSpec("last_action", "LAST ACTION", nulls_last=True),
)
COLUMN_KEYS: tuple[ColumnKey, ...] = tuple(spec.key for spec in COLUMN_SPECS)
DEFAULT_COLUMNS: tuple[ColumnKey, ...] = tuple(
    key
    for key in COLUMN_KEYS
    if key
    not in {
        "labels",
        "project",
        "priority",
        "assignees",
        "author",
        "milestone",
        "type",
        "comments",
        "created",
    }
)
COLUMNS_BY_KEY = {spec.key: spec for spec in COLUMN_SPECS}


@dataclass(frozen=True, slots=True)
class SortTerm:
    column: ColumnKey
    descending: bool = False


DEFAULT_SORT = (SortTerm("last_action", descending=True),)


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
                COLUMN_KEYS[current_index + 1 :] + COLUMN_KEYS[: current_index + 1]
            )
            next_column = next(
                column for column in following_columns if column in self.columns
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

    def with_columns(self, columns: tuple[ColumnKey, ...]) -> IssueTableViewState:
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
    if isinstance(left, LabelsCell) and isinstance(right, LabelsCell):
        return left.labels == right.labels and left == right
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
) -> Callable[[object], SupportsRichComparison]:
    specs = tuple(COLUMNS_BY_KEY[term.column] for term in terms)

    def sort_key(value: object) -> SupportsRichComparison:
        values = value if isinstance(value, tuple) else (value,)
        return tuple(
            _term_sort_value(spec, term, cell)
            for spec, term, cell in zip(specs, terms, values, strict=False)
        )

    return sort_key


def _term_sort_value(
    spec: ColumnSpec, term: SortTerm, cell: object
) -> SupportsRichComparison:
    value = spec.sort_key(cell)
    if not spec.nulls_last:
        # Columns without nulls_last never render a missing sort value.
        return cast("SupportsRichComparison", value)
    missing = value is None
    if term.descending:
        return (0 if missing else 1, 0 if missing else value)
    return (1 if missing else 0, 0 if missing else value)


def column_label(column: ColumnSpec, sort: tuple[SortTerm, ...]) -> str:
    term = next((term for term in sort if term.column == column.key), None)
    marker = "↕" if term is None else ("↓" if term.descending else "↑")
    return f"{column.label} {marker}"


def build_rows(
    result: IssueListResult,
    *,
    columns: tuple[ColumnKey, ...] = DEFAULT_COLUMNS,
    sort: tuple[SortTerm, ...] = (),
    dark: bool = True,
) -> tuple[dict[str, IssueListRow], dict[str, tuple[TableCell, ...]]]:
    """Render queried rows into the requested presentation schema."""
    projected = [(row, _row_values(row, dark=dark)) for row in result.rows]
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
    number = int(row.issue["number"]) if row.issue is not None else 2**63 - 1
    return row.project.project_id.casefold(), number, row.key


def _row_values(row: IssueListRow, *, dark: bool) -> dict[ColumnKey, TableCell]:
    project = row.project
    if row.kind == "issue":
        issue = row.issue
        if issue is None:
            raise RuntimeError("Issue-list Issue row is missing its Issue")
        priority = issue_priority(issue)
        assignees = tuple(assignee.casefold() for assignee in issue["assignees"])
        return {
            "issue_state": issue_state_cell(issue, dark=dark),
            "agent_state": agent_state_cell(row.session_states),
            "number": IssueTableCell(f"#{issue['number']}", issue["number"]),
            "title": text_cell(issue["title"]),
            "labels": labels_cell(issue, project),
            "project": text_cell(project.display_label),
            "priority": IssueTableCell(priority, int(priority[1:])),
            "assignees": IssueTableCell(
                ", ".join(issue["assignees"]) or "unassigned", assignees
            ),
            "author": optional_text_cell(issue["author"]),
            "milestone": optional_text_cell(issue["milestone"]),
            "type": optional_text_cell(issue["issueType"]),
            "comments": comments_cell(issue_activity(issue, project)),
            "created": date_cell(issue["createdAt"]),
            "last_action": date_cell(issue["updatedAt"]),
        }
    raise RuntimeError(f"unsupported Issue-list row kind: {row.kind}")


def text_cell(value: str) -> IssueTableCell:
    return IssueTableCell(value, value.casefold())


def issue_activity(issue: Issue, project: ProjectObservation) -> IssueActivity:
    if project.snapshot is None:
        return IssueActivity()
    return project.snapshot.issue_activity.get(issue["id"], IssueActivity())


def comments_cell(activity: IssueActivity) -> IssueTableCell:
    count = activity.comment_count
    return IssueTableCell(str(count) if count else "-", count)


_NO_LABEL_COLORS: Mapping[str, str] = dict[str, str]()


def label_colors(project: ProjectObservation) -> Mapping[str, str]:
    if project.snapshot is None:
        return _NO_LABEL_COLORS
    return project.snapshot.label_colors


def labels_cell(issue: Issue, project: ProjectObservation) -> LabelsCell:
    return LabelsCell(tuple(issue["labels"]), label_colors(project))


def optional_text_cell(value: str | None) -> IssueTableCell:
    if value is None:
        return IssueTableCell("-", None)
    return text_cell(value)


def relative_age(timestamp: str | None, now: datetime) -> str | None:
    """A tracker-feed style age such as ``just now``, ``5m ago`` or ``3d ago``."""
    if not timestamp:
        return None
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def date_cell(timestamp: str | None) -> IssueTableCell:
    if timestamp is None:
        return IssueTableCell("-", None)
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return IssueTableCell(instant.date().isoformat(), instant.timestamp())


_CLOSED_STATE_KINDS: dict[str, IssueStateKind] = {
    "not-planned": "not-planned",
    "duplicate": "duplicate",
}


def issue_state_kind(issue: Issue) -> IssueStateKind:
    if issue["state"] == "open":
        return "open"
    return _CLOSED_STATE_KINDS.get(issue["stateReason"], "completed")


def issue_state_cell(issue: Issue, *, dark: bool) -> IssueStateCell:
    return IssueStateCell(issue_state_kind(issue), dark=dark)


def agent_state_cell(states: tuple[RunState, ...]) -> IssueTableCell:
    """Summarize Issue work without exposing the number of Agent Runs."""
    if "running" in states:
        return IssueTableCell("▶", 3)
    if "waiting" in states:
        return IssueTableCell("Ⅱ", 2)
    if "unknown" in states:
        return IssueTableCell("?", 1)
    return IssueTableCell("", 0)


PRIORITY_BY_LABEL = {
    "priority/p0": "P0",
    "priority/p1": "P1",
    "priority/p2": "P2",
    "priority/p3": "P3",
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}


def is_priority_label(label: str) -> bool:
    return label.casefold() in PRIORITY_BY_LABEL


def issue_priority(issue: Issue) -> str:
    values = [
        PRIORITY_BY_LABEL[label.casefold()]
        for label in issue["labels"]
        if is_priority_label(label)
    ]
    return min(values, default="P2")
