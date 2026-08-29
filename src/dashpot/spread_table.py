"""A DataTable whose columns share the table's spare width evenly."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Self

from textual import events
from textual.geometry import Size
from textual.render import measure
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey
from typing_extensions import override

if TYPE_CHECKING:
    from textual.widgets.data_table import CellType
else:  # The generic parameter is only spelled at type-check time.
    CellType = Any


class SpreadTable(DataTable[CellType]):
    """A DataTable that spreads its spare width evenly across the columns.

    Textual sizes a column to its content or to a fixed width; neither fills
    the pane. Every column keeps its content as a minimum and receives an
    equal share of whatever width is left, so the columns reach the pane's
    edge at any size. When the content alone is wider than the pane the
    columns fall back to their content widths and the table scrolls
    horizontally, as before.
    """

    @override
    def clear(self, columns: bool = False) -> Self:
        super().clear(columns)
        # Textual only ever widens a column, so a cleared table would keep the
        # width of rows it no longer shows; the labels are all that is left.
        if not columns:
            console = self.app.console
            for column in self.columns.values():
                column.content_width = measure(console, column.label, 1)
        return self

    @override
    def _on_resize(self, _: events.Resize) -> None:
        super()._on_resize(_)
        self.spread_columns()

    @override
    def _update_dimensions(self, new_rows: Iterable[RowKey]) -> None:
        # The base class measures the content of every column here, which is
        # what the shares are computed from.
        super()._update_dimensions(new_rows)
        self.spread_columns()

    def spread_columns(self) -> None:
        """Give each column its content width plus an equal share of the rest."""
        columns = list(self.columns.values())
        if not columns:
            return
        padding = 2 * self.cell_padding
        available = self.scrollable_content_region.width - self._row_label_column_width
        surplus = available - sum(column.content_width + padding for column in columns)
        previous = [
            (column.auto_width, column.get_render_width(self)) for column in columns
        ]
        if surplus <= 0:
            for column in columns:
                column.auto_width = True
        else:
            share, remainder = divmod(surplus, len(columns))
            for index, column in enumerate(columns):
                column.auto_width = False
                column.width = column.content_width + share + (index < remainder)
        current = [
            (column.auto_width, column.get_render_width(self)) for column in columns
        ]
        if current == previous:
            return
        total = sum(width for _, width in current) + self._row_label_column_width
        self.virtual_size = Size(total, self.virtual_size.height)
        # Rendered lines are cached by width; a new share is a new rendering.
        self._update_count += 1
        self._clear_caches()
        self.refresh()
