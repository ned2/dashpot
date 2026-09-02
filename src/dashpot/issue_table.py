"""The Issue table's shape: its column catalogue, view state and sort order.

The rendered values themselves — cell types, Glyphs and chip formatting —
live in ``issue_cells``; this module decides which columns are shown, how
the table is sorted, and assembles each queried row into cells.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, cast

from rich.text import Text

from .issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    SORT_GLYPHS,
    IssueNumberCell,
    IssueTableCell,
    SortValue,
    TableCell,
    agent_state_cell,
    cell_sort_value,
    comments_cell,
    date_cell,
    issue_activity,
    issue_priority,
    issue_state_cell,
    labels_cell,
    optional_text_cell,
    priority_cell,
    text_cell,
)
from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    IssueSearchField,
)
from .list_pane import truncate_end

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

ColumnKey = Literal[
    "issue_state",
    "agent_state",
    "number",
    "title",
    "priority",
    "labels",
    "project",
    "assignees",
    "author",
    "milestone",
    "type",
    "comments",
    "created",
    "last_action",
]


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: ColumnKey
    label: str
    sortable: bool = True
    update_width: bool = False
    header_justify: Literal["left", "center", "right", "full"] | None = None
    # Share of the table's spare width: ``None`` follows the content width,
    # ``0`` keeps the column at its content, as for a one-glyph icon.
    spread_weight: int | None = None
    search_field: IssueSearchField | None = None
    sort_key: Callable[[object], SortValue] = cell_sort_value
    nulls_last: bool = False
    # What a mouse resting on the header is told, for a one-glyph heading
    # whose meaning the Legend also explains.
    tooltip: str | None = None
    # A conditional column is shown only while some row satisfies this; a
    # column without one is shown whenever it is chosen.
    shown_when: Callable[[IssueListRow], bool] | None = None


# The TITLE cell keeps this many characters of an Issue's title, so the
# default columns fit a terminal at a glance instead of scrolling sideways
# behind one long title; the Issue view shows the whole title.
TITLE_LIMIT = 70


def _has_priority(row: IssueListRow) -> bool:
    return issue_priority(row.issue) is not None


COLUMN_SPECS = (
    ColumnSpec(
        "issue_state",
        ISSUE_STATE_COLUMN_GLYPH.symbol,
        sortable=False,
        spread_weight=0,
        tooltip=ISSUE_STATE_COLUMN_GLYPH.meaning,
    ),
    ColumnSpec(
        "agent_state",
        AGENT_STATE_COLUMN_GLYPH.symbol,
        sortable=False,
        spread_weight=0,
        tooltip=AGENT_STATE_COLUMN_GLYPH.meaning,
    ),
    ColumnSpec(
        "number",
        "#",
        header_justify="right",
        search_field=IssueSearchField.NUMBER,
    ),
    ColumnSpec(
        "title",
        "TITLE",
        sortable=False,
        update_width=True,
        search_field=IssueSearchField.TITLE,
    ),
    ColumnSpec("priority", "PRIORITY", nulls_last=True, shown_when=_has_priority),
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
        "project",
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
        if not COLUMNS_BY_KEY[column].sortable:
            return self
        if len(self.sort) == 1 and self.sort[0].column == column:
            term = replace(self.sort[0], descending=not self.sort[0].descending)
        else:
            term = SortTerm(column)
        return replace(self, sort=(term,))

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


def shown_columns(
    columns: tuple[ColumnKey, ...], rows: Sequence[IssueListRow]
) -> tuple[ColumnKey, ...]:
    """The chosen columns the table shows for ``rows``.

    A conditional column is shown only while some row gives it a value, so
    an Issue Source that never sets one costs no width for it.
    """
    return tuple(key for key in columns if _is_shown(COLUMNS_BY_KEY[key], rows))


def _is_shown(spec: ColumnSpec, rows: Sequence[IssueListRow]) -> bool:
    shown_when = spec.shown_when
    return shown_when is None or any(shown_when(row) for row in rows)


def searchable_columns() -> frozenset[IssueSearchField]:
    return frozenset(
        column.search_field
        for column in COLUMN_SPECS
        if column.search_field is not None
    )


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
    if not column.sortable:
        return column.label
    term = next((term for term in sort if term.column == column.key), None)
    marker = SORT_GLYPHS[None if term is None else term.descending]
    return f"{column.label} {marker.symbol}"


def column_header(column: ColumnSpec, sort: tuple[SortTerm, ...]) -> Text:
    """Align a column heading with the values it describes."""
    return Text(column_label(column, sort), justify=column.header_justify)


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
    return row.project.project_id.casefold(), row.issue.number, row.key


def _row_values(row: IssueListRow, *, dark: bool) -> dict[ColumnKey, TableCell]:
    project = row.project
    issue = row.issue
    assignees = tuple(assignee.casefold() for assignee in issue.assignees)
    return {
        "issue_state": issue_state_cell(issue, dark=dark),
        "agent_state": agent_state_cell(row.session_states),
        "number": IssueNumberCell(issue.number),
        "title": text_cell(truncate_end(issue.title, TITLE_LIMIT)),
        "labels": labels_cell(issue, project),
        "project": text_cell(project.display_label),
        "priority": priority_cell(issue, project),
        "assignees": IssueTableCell(
            ", ".join(issue.assignees) or "unassigned", assignees
        ),
        "author": optional_text_cell(issue.author),
        "milestone": optional_text_cell(issue.milestone),
        "type": optional_text_cell(issue.issue_type),
        "comments": comments_cell(issue_activity(issue, project)),
        "created": date_cell(issue.created_at),
        "last_action": date_cell(issue.updated_at),
    }
