"""A DataTable whose row cursor appears only while focused."""

from __future__ import annotations

from textual import events
from textual.widgets import DataTable
from textual.widgets.data_table import CellType
from typing_extensions import override


class FocusCursorTable(DataTable[CellType]):
    """Show the table cursor only while this table has focus."""

    @override
    def on_mount(self) -> None:
        self.show_cursor = self.has_focus

    def on_focus(self, _: events.Focus) -> None:
        self.show_cursor = True

    def on_blur(self, _: events.Blur) -> None:
        self.show_cursor = False
