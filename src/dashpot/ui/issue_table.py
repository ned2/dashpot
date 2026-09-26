"""The Issue table's shape: its column catalogue and view state.

The rendered values themselves — cell types, Glyphs and chip formatting —
live in ``issue_cells``; this module decides which columns are shown, heads
them for the ordering the source accepted, and assembles each queried row
into cells. The source orders every page, so nothing here sorts. Each
column carries its own Column Description and the Glyphs its cells render,
from which its header tooltip and Legend section are built, as every list
pane's columns do.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import ClassVar, Literal, override

from rich.text import Text
from textual.binding import BindingType

from ..issues.ordering import (
    PRIORITY_BY_LABEL,
    PriorityLevel,
    issue_activity,
    issue_priority,
)
from ..issues.search import IssueSearchField
from ..observation.issue_list import (
    IssueListRow,
    IssueListSummary,
    is_waiting,
    row_open_blockers,
    unobserved_auxiliary,
)
from ..observation.list_result import ListResult
from .glyphs import Glyph
from .issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    LEGEND_AGENT_STATE,
    LEGEND_ISSUE_STATE,
    SORT_GLYPHS,
    WAITING_ON_LIMIT,
    IssueNumberCell,
    TableCell,
    agent_state_cell,
    comments_cell,
    date_cell,
    issue_state_cell,
    labels_cell,
    muted_cell,
    optional_text_cell,
    priority_cell,
    waiting_on_cell,
)
from .list_rows import truncate_end
from .spread_table import SpreadTable

ColumnKey = Literal[
    "issue_state",
    "agent_state",
    "number",
    "title",
    "waiting_on",
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


class IssueTable(SpreadTable[TableCell]):
    """The Issue query table with its contextual activation binding."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "select_cursor", "Open Issue"),
    ]

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "select_cursor":
            return True if self.row_count else None
        return True


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One Issue table column: its identity, heading, layout, and what it means.

    ``description`` and ``glyphs`` are the column's Column Description, as
    ``list_rows.DescribedColumn`` reads it for the header tooltip and the
    Legend; every column has one, optional or not.
    """

    key: ColumnKey
    label: str
    description: str
    glyphs: tuple[Glyph, ...] = ()
    sortable: bool = True
    update_width: bool = False
    header_justify: Literal["left", "center", "right", "full"] | None = None
    # Share of the table's spare width: ``None`` follows the content width,
    # ``0`` keeps the column at its content, as for a one-glyph icon.
    spread_weight: int | None = None
    search_field: IssueSearchField | None = None
    # A conditional column is shown only while some row satisfies this; a
    # column without one is shown whenever it is chosen.
    shown_when: Callable[[IssueListRow], bool] | None = None


# The TITLE cell keeps this many characters of an Issue's title, so the
# default columns fit a terminal at a glance instead of scrolling sideways
# behind one long title; the Issue view shows the whole title.
TITLE_LIMIT = 70


def _has_priority(row: IssueListRow) -> bool:
    return issue_priority(row.issue) is not None


# What each column shows, said once for the header tooltip and the Legend.
# The agent-activity column here summarizes the Agent Runs bound to the
# Issue, which is a different fact from the Sessions, Worktrees and
# Branches columns of the same Glyph, so its description says so.
AGENT_STATE_DESCRIPTION = (
    "the liveliest Agent Run explicitly bound to this Issue by an accepted "
    "Issue Binding, running before waiting before orphaned before unknown, "
    "or blank when "
    "none is; an Agent Session located on a Worktree or Branch named for the "
    "Issue does not count until it opts in with work start"
)
ISSUE_STATE_DESCRIPTION = (
    "the Issue's state on its Issue Source, as a block in the state's colour: "
    "open, or closed as completed, not planned, or duplicate; the same colour "
    "frames the Issue view, and o cycles which states the table lists"
)
NUMBER_DESCRIPTION = "the Issue's number in its Issue Source"
TITLE_DESCRIPTION = (
    f"the Issue's title, clipped past {TITLE_LIMIT} characters; Enter opens "
    "the Issue view with the whole of it"
)


def _priority_labels() -> str:
    """Which labels set which priority level, most urgent first."""
    by_level: dict[PriorityLevel, list[str]] = {}
    for label, level in PRIORITY_BY_LABEL.items():
        by_level.setdefault(level, []).append(label)
    return ", ".join(
        f"{' or '.join(labels)} for {level}"
        for level, labels in sorted(by_level.items())
    )


WAITING_ON_DESCRIPTION = (
    "the open Issue's blockers that are still open, by number, or by "
    f"Reference outside its Repository; the first {WAITING_ON_LIMIT} and how "
    "many more, and the row is dimmed. Blank when none is, so the Issue is "
    "Ready, and for a closed Issue. Shown only while some listed Issue waits; "
    "not fetched or unavailable as for COMMENTS"
)
PRIORITY_DESCRIPTION = (
    "the Issue's priority as a chip in the colour of the label that sets it, "
    "the most urgent of its priority labels, which are "
    f"{_priority_labels()}; shown only while some listed Issue carries one, "
    "and blank for an Issue that does not"
)
LABELS_DESCRIPTION = (
    "the Issue's labels as chips in the tracker's colours, a priority label "
    "excepted because it is the PRIORITY cell; - when none"
)
PROJECT_DESCRIPTION = "the Project the Issue belongs to, by its configured label"
ASSIGNEES_DESCRIPTION = "the logins assigned to the Issue, or unassigned"
AUTHOR_DESCRIPTION = (
    "the login that opened the Issue, or - when the Issue Source reports none"
)
MILESTONE_DESCRIPTION = "the Issue's milestone, or - when it has none"
TYPE_DESCRIPTION = (
    "the Issue's type as its Issue Source classifies it, or - when it has none"
)
COMMENTS_DESCRIPTION = (
    "how many comments the Issue Source reports on the Issue, or - when none; "
    "not fetched while the page carried no engagement facts, and unavailable "
    "when fetching them failed"
)
CREATED_DESCRIPTION = "the date the Issue was opened, or - when unknown"
LAST_ACTION_DESCRIPTION = (
    "the date of the Issue's last update on its Issue Source, which any edit, "
    "comment, or state change moves; - when unknown"
)

COLUMN_SPECS = (
    ColumnSpec(
        "agent_state",
        AGENT_STATE_COLUMN_GLYPH.symbol,
        AGENT_STATE_DESCRIPTION,
        glyphs=LEGEND_AGENT_STATE,
        sortable=False,
        spread_weight=0,
    ),
    ColumnSpec(
        "issue_state",
        ISSUE_STATE_COLUMN_GLYPH.symbol,
        ISSUE_STATE_DESCRIPTION,
        glyphs=LEGEND_ISSUE_STATE,
        sortable=False,
        spread_weight=0,
    ),
    ColumnSpec(
        "number",
        "#",
        NUMBER_DESCRIPTION,
        header_justify="right",
        search_field=IssueSearchField.NUMBER,
    ),
    ColumnSpec(
        "title",
        "TITLE",
        TITLE_DESCRIPTION,
        sortable=False,
        update_width=True,
        search_field=IssueSearchField.TITLE,
    ),
    ColumnSpec(
        "waiting_on",
        "WAITING ON",
        WAITING_ON_DESCRIPTION,
        sortable=False,
        update_width=True,
        shown_when=is_waiting,
    ),
    ColumnSpec("priority", "PRIORITY", PRIORITY_DESCRIPTION, shown_when=_has_priority),
    ColumnSpec(
        "labels",
        "LABELS",
        LABELS_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.LABELS,
    ),
    ColumnSpec(
        "project",
        "PROJECT",
        PROJECT_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.PROJECT,
    ),
    ColumnSpec(
        "assignees",
        "ASSIGNEES",
        ASSIGNEES_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.ASSIGNEES,
    ),
    ColumnSpec(
        "author",
        "AUTHOR",
        AUTHOR_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.AUTHOR,
    ),
    ColumnSpec(
        "milestone",
        "MILESTONE",
        MILESTONE_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.MILESTONE,
    ),
    ColumnSpec(
        "type",
        "TYPE",
        TYPE_DESCRIPTION,
        update_width=True,
        search_field=IssueSearchField.TYPE,
    ),
    ColumnSpec("comments", "COMMENTS", COMMENTS_DESCRIPTION),
    ColumnSpec("created", "CREATED", CREATED_DESCRIPTION),
    ColumnSpec("last_action", "LAST ACTION", LAST_ACTION_DESCRIPTION),
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
    """One column of the ordering the source accepted, as its header shows it."""

    column: ColumnKey
    descending: bool = False


@dataclass(frozen=True, slots=True)
class IssueTableViewState:
    """The columns the Issue table shows; its query is the screen's ``ListQueries``."""

    columns: tuple[ColumnKey, ...] = DEFAULT_COLUMNS

    def __post_init__(self) -> None:
        others = tuple(column for column in self.columns if column != "agent_state")
        _validate_columns(("agent_state", *others))
        object.__setattr__(self, "columns", ("agent_state", *others))

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
    result: ListResult[IssueListRow, IssueListSummary],
    *,
    columns: tuple[ColumnKey, ...] = DEFAULT_COLUMNS,
    dark: bool = True,
) -> tuple[dict[str, IssueListRow], dict[str, tuple[TableCell, ...]]]:
    """Render queried rows into the requested presentation schema, in the source's order."""
    contexts: dict[str, IssueListRow] = {}
    cells_by_key: dict[str, tuple[TableCell, ...]] = {}
    for row in result.rows:
        values = _row_values(row, dark=dark)
        contexts[row.key] = row
        cells_by_key[row.key] = tuple(values[column] for column in columns)
    return contexts, cells_by_key


# An open Issue that waits on a blocker has these text cells muted so the
# Ready rows stand out; Glyphs and chips keep the colours that carry meaning.
_MUTED_COLUMNS: tuple[ColumnKey, ...] = (
    "number",
    "title",
    "waiting_on",
    "project",
    "assignees",
    "author",
    "milestone",
    "type",
    "comments",
    "created",
    "last_action",
)


def _row_values(row: IssueListRow, *, dark: bool) -> dict[ColumnKey, TableCell]:
    project = row.project
    issue = row.issue
    # A closed Issue waits on nothing, whatever blockers it still names.
    blockers = row_open_blockers(row) if issue.state == "open" else ()
    values: dict[ColumnKey, TableCell] = {
        "issue_state": issue_state_cell(issue, dark=dark),
        "agent_state": agent_state_cell(row.session_states, dark=dark),
        "number": IssueNumberCell(issue.number),
        "title": truncate_end(issue.title, TITLE_LIMIT),
        "waiting_on": unobserved_auxiliary(row)
        if blockers is None
        else waiting_on_cell(blockers, issue),
        "labels": labels_cell(issue, project),
        "project": project.display_label,
        "priority": priority_cell(issue, project),
        "assignees": ", ".join(issue.assignees) or "unassigned",
        "author": optional_text_cell(issue.author),
        "milestone": optional_text_cell(issue.milestone),
        "type": optional_text_cell(issue.issue_type),
        "comments": (
            comments_cell(row.auxiliary.activity)
            if row.auxiliary and row.auxiliary.activity
            else unobserved_auxiliary(row)
        )
        if row.queried
        else comments_cell(issue_activity(issue, project)),
        "created": date_cell(issue.created_at),
        "last_action": date_cell(issue.updated_at),
    }
    if blockers:
        for key in _MUTED_COLUMNS:
            values[key] = muted_cell(values[key], dark=dark)
    return values
