"""Present content-sized, read-only lists in the main screen's pane row."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Static
from typing_extensions import override

from .focus_table import FocusCursorTable
from .keyed_table import capture_selection, restore_selection
from .pane_layout import DEFAULT_ROW_CAP

ListCell = str | Text

ISSUE_PANE_LABEL = "ISSUES"
SESSIONS_PANE_LABEL = "SESSIONS"
BRANCHES_PANE_LABEL = "BRANCHES"
PULL_REQUESTS_PANE_LABEL = "PULL REQUESTS"
WORKTREES_PANE_LABEL = "WORKTREES"
ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class ListColumn:
    key: str
    label: str
    justify: Literal["left", "center", "right", "full"] | None = None


@dataclass(frozen=True, slots=True)
class ListRow:
    """One record in a list pane, keyed by the stable identity it survives by.

    ``issue_id`` is the Issue the row navigates to, when it has one.
    """

    key: str
    cells: tuple[ListCell, ...]
    issue_id: str | None = None


def truncate_end(value: str, limit: int) -> str:
    """Keep the start of an overlong value and say so with an ellipsis."""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + ELLIPSIS


def truncate_start(value: str, limit: int) -> str:
    """Keep the end of an overlong value, which is where a path is specific."""
    if len(value) <= limit:
        return value
    return ELLIPSIS + value[len(value) - max(0, limit - 1) :]


class ListPane(Vertical):
    """A titled, content-sized table of every observed record of one kind."""

    class RowsChanged(Message):
        """The pane's record count changed, so the panes' shares may too."""

        def __init__(self, pane: ListPane) -> None:
            super().__init__()
            self.pane = pane

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
        controls: Widget | None = None,
        controls_height: int = 0,
    ) -> None:
        super().__init__(id=id)
        if (controls is None) != (controls_height == 0):
            raise ValueError("List pane controls and their height must be set together")
        self.label = label
        self.columns = tuple(columns)
        self.empty_message = empty_message
        self.table_id = table_id
        self.rows_by_key: dict[str, ListRow] = {}
        self.row_cap = DEFAULT_ROW_CAP
        self.controls = controls
        self._controls_height = controls_height

    @override
    def compose(self) -> ComposeResult:
        if self.controls is not None:
            yield self.controls
        yield FocusCursorTable(id=self.table_id, cursor_type="row", zebra_stripes=False)
        yield Static(self.empty_message, classes="list-pane-empty", markup=False)

    def on_mount(self) -> None:
        self.declare_columns(self.columns)
        self.show_rows(())

    @property
    def table(self) -> DataTable[ListCell]:
        """The pane's table; `query_one` cannot name the cell type itself."""
        return cast("DataTable[ListCell]", self.query_one(DataTable))

    @property
    def count(self) -> int:
        return len(self.rows_by_key)

    @property
    def controls_height(self) -> int:
        """Report the height the pane needs whenever it shows its controls."""
        return self._controls_height

    def declare_columns(self, columns: Sequence[ListColumn]) -> None:
        """Replace the pane's columns, which a read model may vary per refresh."""
        table = self.table
        self.columns = tuple(columns)
        table.clear(columns=True)
        for column in self.columns:
            label = (
                column.label
                if column.justify is None
                else Text(column.label, justify=column.justify)
            )
            table.add_column(label, key=column.key)

    def show_rows(
        self,
        rows: Sequence[ListRow],
        *,
        columns: Sequence[ListColumn] | None = None,
        note: str | None = None,
        empty_message: str | None = None,
        title_count: int | None = None,
    ) -> None:
        """Replace the listed records, keeping the cursor by row identity.

        ``columns`` re-declares the pane's columns when the read model has
        dropped one, such as the Sessions pane's single-Observation-Target
        case. ``note`` is a separate pane-level fact, such as when the
        Branches pane's Remote-Tracking Branches were last fetched.
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
        self.border_title = Content(
            f"{self.label} · {self.count if title_count is None else title_count}"
        )
        self.border_subtitle = Content(note) if note else None
        # The empty state is the message line alone: a header over nothing
        # would only cost the Issue table a row.
        table.show_header = bool(rows)
        empty = self.query_one(".list-pane-empty", Static)
        empty.update(message)
        empty.display = not rows
        self.apply_row_cap()
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

    def fit_rows(self, row_cap: int) -> None:
        """Cap the visible records so the panes never crowd out the Issue table.

        ``row_cap`` is the number of content lines the pane may show before it
        scrolls; an empty pane uses one for its message, while zero collapses
        the table to its frame and title count.
        """
        self.row_cap = max(0, min(DEFAULT_ROW_CAP, row_cap))
        self.apply_row_cap()

    def apply_row_cap(self) -> None:
        table = self.table
        if self.controls is not None:
            self.controls.display = self.row_cap > 0
        header_height = 1 if table.show_header else 0
        table.styles.max_height = (
            header_height + self.row_cap if self.row_cap and self.rows_by_key else 0
        )
        self.query_one(".list-pane-empty", Static).display = (
            not self.rows_by_key and self.row_cap > 0
        )

    def highlighted(self) -> tuple[str | None, int]:
        """The highlighted row's key and index, or nothing when the pane is empty."""
        return capture_selection(self.table)

    def highlighted_row(self) -> ListRow | None:
        key, _index = self.highlighted()
        return self.rows_by_key.get(key) if key is not None else None

    def row(self, key: str) -> ListRow | None:
        return self.rows_by_key.get(key)
