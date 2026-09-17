"""A DataTable whose row cursor appears only while focused, with header help."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal, Self

from rich.segment import Segment
from rich.style import Style
from rich.text import TextType
from textual import events
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets.data_table import CellType, ColumnKey
from typing_extensions import override


class FocusCursorTable(DataTable[CellType]):
    """Show the table cursor only while this table has focus.

    A column added with a ``tooltip`` explains itself to a mouse resting on
    its header; the tooltip follows the hovered header and clears over the
    body and on leaving, so the table never offers a stale one.
    """

    COMPONENT_CLASSES: ClassVar[set[str]] = DataTable.COMPONENT_CLASSES | {
        "datatable--related-row"
    }
    related_rows: frozenset[str] = frozenset[str]()
    related_columns: frozenset[str] = frozenset[str]()
    # Header tooltips by column key; created on first use rather than in
    # ``__init__``, whose long DataTable signature would have to be repeated.
    _header_tooltips: dict[ColumnKey, str] | None = None

    class FocusChanged(Message):
        """Recompute relationships when the visible cursor changes focus."""

    @override
    def add_column(
        self,
        label: TextType,
        *,
        width: int | None = None,
        key: str | None = None,
        default: CellType | None = None,
        tooltip: str | None = None,
    ) -> ColumnKey:
        column_key = super().add_column(label, width=width, key=key, default=default)
        if tooltip is not None:
            if self._header_tooltips is None:
                self._header_tooltips = {}
            self._header_tooltips[column_key] = tooltip
        return column_key

    @override
    def clear(self, columns: bool = False) -> Self:
        super().clear(columns)
        if columns:
            self._header_tooltips = None
            self.tooltip = None
        return self

    # Textual runs ``DataTable._on_mouse_move`` and ``_on_leave`` by name on
    # their own class, so these handlers add to them rather than overriding
    # and calling them, which would run the base handlers twice.
    def on_mouse_move(self, event: events.MouseMove) -> None:
        # Textual resolves one tooltip per widget when its hover timer fires,
        # and the headers are painted rather than composed, so the table
        # reads the hovered column from the segment meta the header render
        # stamps and offers that column's tooltip as its own.
        self.tooltip = self.header_tooltip_at(event.style.meta)

    def on_leave(self, _: events.Leave) -> None:
        self.tooltip = None

    def header_tooltip_at(self, meta: Mapping[str, object]) -> str | None:
        """The tooltip of the header the mouse rests on, or nothing off a header."""
        if meta.get("row") != -1 or not self._header_tooltips:
            return None
        index = meta.get("column")
        if not isinstance(index, int) or not 0 <= index < len(self.ordered_columns):
            return None
        return self._header_tooltips.get(self.ordered_columns[index].key)

    def set_related_rows(self, keys: frozenset[str], columns: frozenset[str]) -> None:
        """Emphasize related rows without changing their values or selection."""
        if (keys, columns) == (self.related_rows, self.related_columns):
            return
        self.related_rows, self.related_columns = keys, columns
        self._clear_caches()
        self.refresh()

    def is_related_row(self, row_index: int) -> bool:
        return (
            0 <= row_index < self.row_count
            and self.ordered_rows[row_index].key.value in self.related_rows
        )

    @override
    def _get_row_style(self, row_index: int, base_style: Style) -> Style:
        style = super()._get_row_style(row_index, base_style)
        if self.is_related_row(row_index):
            style += self.get_component_rich_style("datatable--related-row")
        return style

    @override
    def _render_cell(
        self,
        row_index: int,
        column_index: int,
        base_style: Style,
        width: int,
        cursor: bool = False,
        hover: bool = False,
    ) -> list[list[Segment]]:
        if self.is_related_row(row_index):
            base_style += self.get_component_rich_style("datatable--related-row")
        if (
            self.is_related_row(row_index)
            and 0 <= column_index < len(self.ordered_columns)
            and self.ordered_columns[column_index].key.value in self.related_columns
        ):
            base_style += Style(bold=True)
        return super()._render_cell(
            row_index, column_index, base_style, width, cursor, hover
        )

    class RowBoundaryReached(Message):
        """Report a row move beyond this table so its screen may move focus."""

        def __init__(
            self,
            table: FocusCursorTable[Any],
            step: Literal[-1, 1],
        ) -> None:
            super().__init__()
            self.table = table
            self.step = step

        @property
        @override
        def control(self) -> FocusCursorTable[Any]:
            return self.table

    @override
    def on_mount(self) -> None:
        self.show_cursor = self.has_focus

    def on_focus(self, _: events.Focus) -> None:
        self.show_cursor = True
        if self.row_count:
            self.move_cursor(row=0, animate=False)
        self.post_message(self.FocusChanged())

    def on_blur(self, _: events.Blur) -> None:
        self.show_cursor = False
        self.post_message(self.FocusChanged())

    @override
    def action_cursor_up(self) -> None:
        at_start = (
            self.show_cursor
            and self.cursor_type in {"cell", "row"}
            and (not self.row_count or self.cursor_row == 0)
        )
        if at_start:
            self.post_message(self.RowBoundaryReached(self, -1))
        else:
            super().action_cursor_up()

    @override
    def action_cursor_down(self) -> None:
        at_end = (
            self.show_cursor
            and self.cursor_type in {"cell", "row"}
            and (not self.row_count or self.cursor_row == self.row_count - 1)
        )
        if at_end:
            self.post_message(self.RowBoundaryReached(self, 1))
        else:
            super().action_cursor_down()
