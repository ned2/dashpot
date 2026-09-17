"""Dispatch Worktree keyboard activation independently of mouse selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from rich.text import Text
from textual.binding import BindingType
from textual.message import Message
from textual.reactive import reactive
from typing_extensions import override

from .focus_table import FocusCursorTable
from .keyed_table import capture_selection


class WorktreeTable(FocusCursorTable[str | Text]):
    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "open_worktree", "Open Worktree"),
        ("y", "copy_path", "Copy path"),
    ]
    opening = reactive(False, bindings=True)
    launch_available = reactive(False, bindings=True)

    @dataclass(eq=False)
    class OpenRequested(Message):
        """Open the Worktree of the row ``key`` names, on this key press."""

        key: str

    @dataclass(eq=False)
    class CopyRequested(Message):
        """Copy the path of the Worktree row ``key`` names."""

        key: str

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"open_worktree", "copy_path"}:
            available = bool(self.row_count)
            if action == "open_worktree":
                available = available and self.launch_available and not self.opening
            return True if available else None
        return True

    def action_open_worktree(self) -> None:
        """Request Open Worktree for the row selected by this key press."""
        key, _ = capture_selection(self)
        if key is not None and self.launch_available and not self.opening:
            self.post_message(self.OpenRequested(key))

    def action_copy_path(self) -> None:
        """Request copying the row selected by this key press."""
        key, _ = capture_selection(self)
        if key is not None:
            self.post_message(self.CopyRequested(key))
