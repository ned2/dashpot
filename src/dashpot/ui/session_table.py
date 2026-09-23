"""Dispatch Sessions pane keyboard actions independently of mouse selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, override

from textual.binding import BindingType
from textual.message import Message
from textual.widgets import DataTable

from ..observation.session_list import SessionListRow, resume_command
from .focus_table import FocusCursorTable
from .keyed_table import capture_selection
from .list_pane import ListPane
from .list_rows import ListCell


class SessionTable(FocusCursorTable[ListCell]):
    BINDINGS: ClassVar[list[BindingType]] = [
        ("y", "copy_resume", "Copy resume command"),
    ]

    @dataclass(eq=False)
    class ResumeCopyRequested(Message):
        """Copy the resume command of the session row ``key`` names."""

        key: str

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Only an Orphaned Agent Run has a session to resume, so the key is
        # offered on that row alone rather than crowding every row's footer.
        if action == "copy_resume":
            return self.resumable()
        return True

    def resumable(self) -> bool:
        """Whether the highlighted row is a session that can be resumed."""
        key, _ = capture_selection(self)
        if key is None or not isinstance(self.parent, ListPane):
            return False
        record = self.parent.record(key)
        return (
            isinstance(record, SessionListRow)
            and resume_command(record.session) is not None
        )

    def on_data_table_row_highlighted(self, _: DataTable.RowHighlighted) -> None:
        self.refresh_bindings()

    def action_copy_resume(self) -> None:
        """Request the resume command for the row selected by this key press."""
        key, _ = capture_selection(self)
        if key is not None:
            self.post_message(self.ResumeCopyRequested(key))
