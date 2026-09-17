"""Drive the Issue table: its submitted query, its rows, and what relates to the cursor.

The controller owns the Issue table's query state and rebuilds the table
from the accepted page. It drives a ``DataTable``, so it touches Textual,
but it is not a Screen: the pure parts — the column heading for a
submitted ordering and the record under a cursor — are module functions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from itertools import chain
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.widgets import DataTable

from .focus_table import FocusCursorTable
from .glyphs import ACTIVITY_WIDTH
from .issue_cells import TableCell
from .issue_list import IssueListQuery, IssueListResult, IssueListRow
from .issue_table import (
    COLUMNS_BY_KEY,
    ColumnKey,
    IssueTableViewState,
    SortTerm,
    build_rows,
    column_header,
    column_specs,
    searchable_columns,
    shown_columns,
)
from .item_filter import lifecycle_value
from .keyed_table import capture_selection, restore_selection
from .panes import LIST_PANE_SPECS
from .queries.page_navigation import page_text
from .queries.source_queries import QueryRequest
from .related_rows import FocusedSource, query_related_rows
from .spread_table import SpreadTable

if TYPE_CHECKING:
    from .app import DashboardScreen

# The Issue table's columns that emphasise a row related to the cursor.
ISSUE_RELATED_COLUMNS = frozenset({"number", "title"})


def issue_column_label(
    name: ColumnKey, request: QueryRequest, *, orderable: bool
) -> Text:
    """Head a column with the submitted ordering when the source can order by it."""
    spec = COLUMNS_BY_KEY[name]
    if not orderable:
        return Text(spec.label)
    term = (
        (SortTerm(name, request.ordering.endswith(":desc")),)
        if request.ordering.startswith(name + ":")
        else ()
    )
    return column_header(spec, term)


def focused_source(
    key: str | None, records: Iterable[FocusedSource]
) -> FocusedSource | None:
    """The record under a table cursor, by the row key every pane keeps unique."""
    if key is None:
        return None
    return next((row for row in records if row.key == key), None)


class IssueTableController:
    """Own the Issue table's query state and rebuild its rows from the accepted page."""

    def __init__(self, screen: DashboardScreen) -> None:
        self.screen = screen
        self.issue_view = IssueTableViewState()
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, IssueListRow] = {}
        # Each list pane's read-model records from its last refresh, by pane
        # id, so relationship emphasis never queries the store per cursor move.
        self.pane_records: dict[str, tuple[FocusedSource, ...]] = {}

    @property
    def table(self) -> SpreadTable[TableCell]:
        """The Issue table the controller drives."""
        return self.screen.queue_table()

    @staticmethod
    def table_columns(table: DataTable[TableCell]) -> tuple[ColumnKey, ...]:
        """The columns the table shows now: the chosen ones a conditional column may leave."""
        return tuple(cast(ColumnKey, str(key.value)) for key in table.columns)

    def show_table_columns(self, columns: tuple[ColumnKey, ...]) -> None:
        """Rebuild the table's columns when they differ from ``columns``."""
        table = self.table
        if columns == self.table_columns(table):
            return
        table.clear(columns=True)
        table.fixed_columns = 1
        for column in column_specs(columns):
            table.add_column(
                self.column_label(column.key),
                key=column.key,
                width=ACTIVITY_WIDTH if column.key == "agent_state" else None,
                spread_weight=column.spread_weight,
                tooltip=column.tooltip,
            )

    def column_label(self, name: ColumnKey) -> Text:
        """Head a column for the submitted request and what its source can order."""
        queries = self.screen.dashpot.queries
        return issue_column_label(
            name,
            queries.navigation["issues"].request,
            orderable=queries.supports_sort("issues", name),
        )

    def update_sort_headers(self) -> None:
        """Re-head every column for the ordering the source last accepted."""
        table = self.table
        for key, column in table.columns.items():
            column.label = self.column_label(cast("ColumnKey", str(key.value)))
        table.refresh()

    def apply_issue_columns(self, columns: tuple[ColumnKey, ...] | None) -> None:
        """Show the columns the editor chose; nothing changes on cancel or no change."""
        if columns is None or columns == self.issue_view.columns:
            return
        self.issue_view = self.issue_view.with_columns(columns)
        if self.screen.dashpot.store.has_observations:
            self.reconcile_rows()
            return
        self.show_table_columns(shown_columns(columns, ()))

    def set_issue_query(self, query: IssueListQuery) -> None:
        """Record the submitted Issue query; a lifecycle change submits a page."""
        previous = self.issue_view.query
        self.issue_view = replace(self.issue_view, query=query)
        if query.states != previous.states:
            self.screen.dashpot.submit_page(
                "issues", state=lifecycle_value(query.states)
            )

    def update_page_summary(self) -> None:
        """Fit the Issue page summary to the dashboard's current layout."""
        navigation = self.screen.dashpot.queries.navigation["issues"]
        self.screen.issue_filter_bar.count.update(
            page_text(navigation, compact=self.screen.has_class("-compact"))
        )
        self.screen.issue_filter_bar.count.tooltip = page_text(navigation)

    def reconcile_rows(self) -> IssueListResult:
        """Rebuild the table from the accepted page and return the query result."""
        app = self.screen.dashpot
        table = self.table
        query = replace(self.issue_view.query, search_fields=searchable_columns())
        result = app.store.query_issues(query)
        self.update_page_summary()
        shown = shown_columns(self.issue_view.columns, result.rows)
        self.show_table_columns(shown)
        contexts, cells_by_key = build_rows(
            result, columns=shown, dark=app.current_theme.dark
        )
        # Provider order can change with identical row identities. Rebuild the
        # small page so keyed-table insertion history never becomes ordering;
        # the cursor returns to its Issue by key, else to the first row.
        with app.batch_update():
            table.clear()
            for key, cells in cells_by_key.items():
                table.add_row(*cells, key=key)
        self.update_sort_headers()
        self.rows_by_key = contexts
        selected_key = restore_selection(table, self.selected_row_key, 0, contexts)
        self.update_related_rows()
        if selected_key is None:
            self.selected_row_key = None
            return result
        self.show_row(selected_key)
        return result

    def show_row(self, key: str) -> None:
        """Select the Issue under the cursor, when the store can still detail it."""
        row = self.rows_by_key.get(key)
        context = self.screen.dashpot.store.detail_for(row) if row is not None else None
        # A row the store can no longer detail selects nothing; keeping the
        # previous selection would open the wrong Issue.
        self.selected_row_key = key if context is not None else None

    def records(self) -> tuple[FocusedSource, ...]:
        """Every pane's records and the Issue rows, as last listed."""
        return (
            *chain.from_iterable(self.pane_records.values()),
            *self.rows_by_key.values(),
        )

    def update_related_rows(self, *, clear: bool = False) -> None:
        """Emphasize direct relationships of the visible focused cursor."""
        screen = self.screen
        if not screen.is_mounted or not screen._update_widgets_mounted():
            return
        records = self.records()
        source: FocusedSource | None = None
        focused = screen.focused
        if (
            not clear
            and screen.app.screen is screen
            and isinstance(focused, FocusCursorTable)
        ):
            source = focused_source(capture_selection(focused)[0], records)
        related = query_related_rows(source, records)
        for spec in LIST_PANE_SPECS:
            if spec.related is not None:
                screen.list_pane(spec.pane_id).table.set_related_rows(
                    spec.related(related), spec.related_columns
                )
        self.table.set_related_rows(related.issues, ISSUE_RELATED_COLUMNS)
