"""A DataTable whose row cursor appears only while focused."""

from __future__ import annotations

from typing import Any, Literal

from textual import events
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets.data_table import CellType
from typing_extensions import override


class FocusCursorTable(DataTable[CellType]):
    """Show the table cursor only while this table has focus."""

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

    def on_blur(self, _: events.Blur) -> None:
        self.show_cursor = False

    @override
    def action_cursor_up(self) -> None:
        at_start = (
            self.show_cursor
            and self.cursor_type in {"cell", "row"}
            and (not self.row_count or self.cursor_row == 0)
        )
        super().action_cursor_up()
        if at_start:
            self.post_message(self.RowBoundaryReached(self, -1))

    @override
    def action_cursor_down(self) -> None:
        at_end = (
            self.show_cursor
            and self.cursor_type in {"cell", "row"}
            and (not self.row_count or self.cursor_row == self.row_count - 1)
        )
        super().action_cursor_down()
        if at_end:
            self.post_message(self.RowBoundaryReached(self, 1))
