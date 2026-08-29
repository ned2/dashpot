"""A DataTable whose columns share the table's spare width evenly."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
    the pane. Every column keeps its content as a minimum and receives a
    share of whatever width is left in proportion to that content, as a
    browser lays out an auto table, so the columns reach the pane's edge at
    any size and the long columns take most of the room. When the content alone is wider than the pane the
    columns fall back to their content widths and the table scrolls
    horizontally, as before.
    """

    _spread_weights: dict[str, int] | None = None

    @property
    def spread_weights(self) -> dict[str, int]:
        """Explicit share weights by column key, replacing the content width.

        ``0`` pins a column to its content, as for a one-glyph icon.
        """
        # Created on first use rather than in ``__init__``, whose long
        # DataTable signature would otherwise have to be repeated here.
        if self._spread_weights is None:
            self._spread_weights = {}
        return self._spread_weights

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
        """Give each column its content width plus a weighted share of the rest."""
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
            shares = proportional_shares(
                surplus,
                [
                    self.spread_weights.get(str(column.key.value), column.content_width)
                    for column in columns
                ],
            )
            for column, share in zip(columns, shares, strict=True):
                column.auto_width = False
                column.width = column.content_width + share
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


def proportional_shares(total: int, weights: Sequence[int]) -> list[int]:
    """Split ``total`` in proportion to ``weights``, so the parts sum exactly.

    This is the browsers' rule for a table wider than its content: the excess
    goes to the columns in proportion to their content width, so a title
    column absorbs most of it and a chip column stays tight. Rounding follows
    the largest remainders; all-zero weights share evenly.
    """
    if not weights:
        return []
    if not any(weights):
        weights = [1] * len(weights)
    scale = sum(weights)
    exact = [total * weight / scale for weight in weights]
    shares = [int(part) for part in exact]
    remainders = sorted(
        range(len(weights)),
        key=lambda index: exact[index] - shares[index],
        reverse=True,
    )
    for index in remainders[: total - sum(shares)]:
        shares[index] += 1
    return shares
