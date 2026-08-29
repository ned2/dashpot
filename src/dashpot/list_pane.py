"""Content-sized, read-only list panes for the main screen's pane row.

The Sessions and Worktrees panes share one shell: a titled frame whose
`DataTable` grows with its records up to a cap, scrolls beyond it, and shows an
honest empty-state line instead of a blank frame. The pane owns its row cursor
and preserves it across refreshes by stable row identity; the records
themselves come from the read models supplied by the pane's caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import DataTable, Static
from typing_extensions import override

ListCell = str | Text

# Header plus eight records; a longer list scrolls inside the pane.
DEFAULT_ROW_CAP = 8
ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class ListColumn:
    key: str
    label: str


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
    ) -> None:
        super().__init__(id=id)
        self.label = label
        self.columns = tuple(columns)
        self.empty_message = empty_message
        self.table_id = table_id
        self.rows_by_key: dict[str, ListRow] = {}
        self.row_cap = DEFAULT_ROW_CAP

    @override
    def compose(self) -> ComposeResult:
        yield DataTable(id=self.table_id, cursor_type="row", zebra_stripes=True)
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

    def declare_columns(self, columns: Sequence[ListColumn]) -> None:
        """Replace the pane's columns, which a read model may vary per refresh."""
        table = self.table
        self.columns = tuple(columns)
        table.clear(columns=True)
        for column in self.columns:
            table.add_column(column.label, key=column.key)

    def show_rows(
        self,
        rows: Sequence[ListRow],
        *,
        columns: Sequence[ListColumn] | None = None,
        note: str | None = None,
    ) -> None:
        """Replace the listed records, keeping the cursor by row identity.

        ``columns`` re-declares the pane's columns when the read model has
        dropped one, such as the Sessions pane's single-Observation-Target
        case. ``note`` is a pane-level fact that follows the count in the
        title, such as how old the Branches pane's remote facts are.
        """
        table = self.table
        prior_key, prior_index = self.highlighted()
        desired = {row.key: row for row in rows}
        if len(desired) != len(rows):
            raise ValueError(f"Duplicate row identity in the {self.label} pane")
        with self.app.batch_update():
            if columns is not None and tuple(columns) != self.columns:
                self.declare_columns(columns)
            table.clear()
            for row in rows:
                table.add_row(*row.cells, key=row.key)
        self.rows_by_key = desired
        title = f"{self.label} · {self.count}"
        self.border_title = Content(f"{title} · {note}" if note else title)
        # The empty state is the message line alone: a header over nothing
        # would only cost the Issue table a row.
        table.show_header = bool(rows)
        self.query_one(".list-pane-empty", Static).display = not rows
        self.apply_row_cap()
        self.post_message(self.RowsChanged(self))
        if not rows:
            return
        if prior_key is not None and prior_key in desired:
            selected_index = table.get_row_index(prior_key)
        else:
            selected_index = min(prior_index, table.row_count - 1)
        table.move_cursor(row=selected_index, column=0, animate=False)

    def fit_rows(self, row_cap: int) -> None:
        """Cap the visible records so the panes never crowd out the Issue table.

        ``row_cap`` is the number of records the table may show before it
        scrolls; zero collapses the table to its frame and title count.
        """
        self.row_cap = max(0, min(DEFAULT_ROW_CAP, row_cap))
        self.apply_row_cap()

    def apply_row_cap(self) -> None:
        table = self.table
        header_height = 1 if table.show_header else 0
        table.styles.max_height = (
            header_height + self.row_cap if self.row_cap and self.rows_by_key else 0
        )

    def highlighted(self) -> tuple[str | None, int]:
        """The highlighted row's key and index, or nothing when the pane is empty."""
        table = self.table
        if not table.row_count:
            return None, 0
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return key, table.cursor_row

    def highlighted_row(self) -> ListRow | None:
        key, _index = self.highlighted()
        return self.rows_by_key.get(key) if key is not None else None

    def row(self, key: str) -> ListRow | None:
        return self.rows_by_key.get(key)
