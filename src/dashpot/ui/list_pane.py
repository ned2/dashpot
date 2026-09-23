"""Present content-sized, read-only lists in a Peer Screen's pane row."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast, override

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Static

from ..observation.related_rows import FocusedSource
from .focus_table import FocusCursorTable
from .item_filter import ItemFilterBar
from .keyed_table import capture_selection, restore_selection
from .list_rows import ListCell, ListColumn, ListRow, column_help
from .pane_layout import content_height_wish, pane_wish

ISSUE_PANE_LABEL = "ISSUES"
SESSIONS_PANE_LABEL = "SESSIONS"
BRANCHES_PANE_LABEL = "BRANCHES"
PULL_REQUESTS_PANE_LABEL = "PULL REQUESTS"
WORKTREES_PANE_LABEL = "WORKTREES"

__all__ = [
    "BRANCHES_PANE_LABEL",
    "ISSUE_PANE_LABEL",
    "PULL_REQUESTS_PANE_LABEL",
    "SESSIONS_PANE_LABEL",
    "WORKTREES_PANE_LABEL",
    "ListCell",
    "ListColumn",
    "ListPane",
    "ListRow",
]


class ListPane(Vertical):
    """A titled, content-sized table of every observed record of one kind."""

    @dataclass(eq=False)
    class RowsChanged(Message):
        """The pane's record count changed, so the panes' shares may too."""

        pane: ListPane

        @property
        @override
        def control(self) -> ListPane:
            return self.pane

    def __init__(
        self,
        label: str,
        *,
        columns: Sequence[ListColumn] = (),
        empty_message: str,
        id: str,
        table_id: str,
        table_type: type[FocusCursorTable[ListCell]] = FocusCursorTable,
        controls: ItemFilterBar | None = None,
        controls_height: int = 0,
        visible_row_limit: int | None = None,
    ) -> None:
        super().__init__(id=id)
        if (controls is None) != (controls_height == 0):
            raise ValueError("List pane controls and their height must be set together")
        self.label = label
        self.columns = tuple(columns)
        self.empty_message = empty_message
        self.table_id = table_id
        self.table_type = table_type
        self.rows_by_key: dict[str, ListRow] = {}
        # The read-model records the listed rows were built from, kept so a
        # cursor action reads its record here and never queries the store.
        self.records: tuple[FocusedSource, ...] = ()
        self.content_height_cap = 0
        self.controls = controls
        self._controls_height = controls_height
        self.visible_row_limit = visible_row_limit

    @override
    def compose(self) -> ComposeResult:
        if self.controls is not None:
            yield self.controls
        yield self.table_type(id=self.table_id, cursor_type="row", zebra_stripes=False)
        yield Static(self.empty_message, classes="list-pane-empty", markup=False)

    def on_mount(self) -> None:
        self.declare_columns(self.columns)
        self.show_rows(())

    @property
    def table(self) -> FocusCursorTable[ListCell]:
        """The pane's table; `query_one` cannot name the cell type itself."""
        return cast("FocusCursorTable[ListCell]", self.query_one(FocusCursorTable))

    @property
    def count(self) -> int:
        return len(self.rows_by_key)

    @property
    def controls_height(self) -> int:
        """Report the height the pane needs whenever it shows its controls."""
        return self._controls_height

    def height_wish(self) -> int:
        """The pane height that would show every record its policy admits."""
        return pane_wish(
            self.count,
            controls_height=self.controls_height,
            visible_row_limit=self.visible_row_limit,
        )

    def declare_columns(self, columns: Sequence[ListColumn]) -> None:
        """Replace the pane's columns, which a read model may vary per refresh."""
        table = self.table
        self.columns = tuple(columns)
        table.clear(columns=True)
        table.fixed_columns = 0
        for index, column in enumerate(self.columns):
            if index == table.fixed_columns and column.frozen:
                table.fixed_columns += 1
            label = (
                column.label
                if column.justify is None
                else Text(column.label, justify=column.justify)
            )
            table.add_column(
                label,
                key=column.key,
                width=column.width,
                tooltip=column_help(column),
            )

    def show_rows(
        self,
        rows: Sequence[ListRow],
        *,
        columns: Sequence[ListColumn] | None = None,
        note: str | None = None,
        empty_message: str | None = None,
        title_summary: str | None = None,
        filter_count: str | None = None,
        records: tuple[FocusedSource, ...] = (),
    ) -> None:
        """Replace the listed records, keeping the cursor by row identity.

        ``columns`` re-declares the pane's columns when the read model has
        dropped one, such as the Sessions pane's single-Observation-Target
        case. ``note`` is a separate pane-level fact, such as when the
        Branches pane's Remote-Tracking Branches were last fetched.
        ``filter_count`` is the matched count the pane's controls show, and
        ``records`` are the read-model rows ``rows`` were built from.
        """
        table = self.table
        message = empty_message or self.empty_message
        prior_key, prior_index = self.highlighted()
        desired = {row.key: row for row in rows}
        if len(desired) != len(rows):
            raise ValueError(f"Duplicate row identity in the {self.label} pane")
        with self.app.batch_update():
            if columns is not None and tuple(columns) != self.columns:
                self.declare_columns(columns)
            table.clear()
            for row in rows:
                cells = tuple(
                    self._justify_cell(cell, self.columns[index].justify)
                    if index < len(self.columns)
                    else cell
                    for index, cell in enumerate(row.cells)
                )
                table.add_row(*cells, key=row.key)
        self.rows_by_key = desired
        self.records = records
        summary = str(self.count) if title_summary is None else title_summary
        self.border_title = Content(f"{self.label} · {summary}")
        self.border_subtitle = Content(note) if note else None
        if self.controls is not None and filter_count is not None:
            self.controls.count.update(filter_count)
        # The empty state is the message line alone: a header over nothing
        # would only cost the Issue table a row.
        table.show_header = bool(rows)
        empty = self.query_one(".list-pane-empty", Static)
        empty.update(message)
        empty.display = not rows
        # Keep the previous allocation through reconciliation, but apply the
        # current record policy before the screen handles ``RowsChanged``.
        self.fit_rows(self.content_height_cap)
        self.post_message(self.RowsChanged(self))
        restore_selection(table, prior_key, prior_index, desired)

    @staticmethod
    def _justify_cell(
        cell: ListCell,
        justify: Literal["left", "center", "right", "full"] | None,
    ) -> ListCell:
        """Align one cell while preserving any Glyph styling it carries."""
        if justify is None:
            return cell
        if isinstance(cell, Text):
            aligned = cell.copy()
            aligned.justify = justify
            return aligned
        return Text(cell, justify=justify)

    def fit_rows(self, content_height_cap: int) -> None:
        """Cap the table content so the pane stack fits its available height.

        The cap includes a horizontal scrollbar when present and is therefore
        not necessarily a visible-record count. An empty pane uses one content
        line for its message, while zero collapses to its frame and title.
        """
        self.content_height_cap = max(
            0,
            min(
                content_height_cap,
                content_height_wish(self.count, self.visible_row_limit),
            ),
        )
        self.apply_content_height_cap()

    def apply_content_height_cap(self) -> None:
        table = self.table
        if self.controls is not None:
            self.controls.display = self.content_height_cap > 0
        header_height = 1 if table.show_header else 0
        table.styles.max_height = (
            header_height + self.content_height_cap
            if self.content_height_cap and self.rows_by_key
            else 0
        )
        self.query_one(".list-pane-empty", Static).display = (
            not self.rows_by_key and self.content_height_cap > 0
        )

    def highlighted(self) -> tuple[str | None, int]:
        """The highlighted row's key and index, or nothing when the pane is empty."""
        return capture_selection(self.table)

    def row(self, key: str) -> ListRow | None:
        return self.rows_by_key.get(key)

    def record(self, key: str) -> FocusedSource | None:
        """The read-model record the row ``key`` names was built from."""
        return next((record for record in self.records if record.key == key), None)
