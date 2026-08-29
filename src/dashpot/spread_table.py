"""A DataTable whose columns share the table's spare width."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Self

from rich.text import TextType
from textual import events
from textual.geometry import Size
from textual.render import measure
from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey, RowKey
from typing_extensions import override

if TYPE_CHECKING:
    from textual.widgets.data_table import CellType
else:  # The generic parameter is only spelled at type-check time.
    CellType = Any


class SpreadTable(DataTable[CellType]):
    """A DataTable that spreads its spare width across the columns.

    Textual sizes a column to its content or to a fixed width; neither fills
    the pane. Every column keeps its content as a minimum and receives a
    share of whatever width is left in proportion to that content, as a
    browser lays out an auto table, so the columns reach the pane's edge at
    any size and the long columns take most of the room. A column added with
    an explicit ``spread_weight`` uses that weight instead; ``0`` pins it to its
    content, as for a one-glyph icon. When the content alone is wider than
    the pane the columns fall back to their content widths and the table
    scrolls horizontally, as before.
    """

    # Explicit weights by column key; created on first use rather than in
    # ``__init__``, whose long DataTable signature would have to be repeated.
    _spread_weights: dict[ColumnKey, int] | None = None

    @override
    def add_column(
        self,
        label: TextType,
        *,
        width: int | None = None,
        key: str | None = None,
        default: CellType | None = None,
        spread_weight: int | None = None,
    ) -> ColumnKey:
        column_key = super().add_column(label, width=width, key=key, default=default)
        if spread_weight is not None:
            if self._spread_weights is None:
                self._spread_weights = {}
            self._spread_weights[column_key] = spread_weight
        return column_key

    @override
    def clear(self, columns: bool = False) -> Self:
        super().clear(columns)
        if columns:
            self._spread_weights = None
        else:
            # Textual only ever widens a column, so a cleared table would keep
            # the width of rows it no longer shows; the labels are all that
            # is left.
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
        weights = self._spread_weights or {}
        available = self.scrollable_content_region.width - self._row_label_column_width
        widths = spread_widths(
            available,
            [column.content_width for column in columns],
            [weights.get(column.key, column.content_width) for column in columns],
            padding=2 * self.cell_padding,
        )
        previous = [
            (column.auto_width, column.get_render_width(self)) for column in columns
        ]
        for column, width in zip(columns, widths, strict=True):
            column.auto_width = width is None
            if width is not None:
                column.width = width
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


def spread_widths(
    available: int,
    content_widths: Sequence[int],
    weights: Sequence[int],
    *,
    padding: int = 0,
) -> list[int | None]:
    """Widths that fill ``available``, or ``None`` per column when they cannot.

    Each column keeps its content width and gains a share of the surplus in
    proportion to its weight. When the content alone (with ``padding`` per
    column) does not fit, every width is ``None``: the column is its content
    and the table scrolls.
    """
    surplus = available - sum(width + padding for width in content_widths)
    if surplus <= 0:
        return [None] * len(content_widths)
    shares = proportional_shares(surplus, weights)
    return [width + share for width, share in zip(content_widths, shares, strict=True)]


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
