"""Toggles whose X is present only when they are on."""

from __future__ import annotations

from typing import TypeVar

from rich.segment import Segment
from textual.content import Content
from textual.strip import Strip
from textual.widgets import Checkbox, SelectionList
from typing_extensions import override

SelectionType = TypeVar("SelectionType")


class MarkedSelectionList(SelectionList[SelectionType]):
    """Show an X only for a selected option."""

    @override
    def render_line(self, y: int) -> Strip:
        line = super().render_line(y)
        selection_index = self.scroll_offset.y + y
        if selection_index >= self.option_count:
            return line
        selection = self.get_option_at_index(selection_index)
        if selection.value in self.selected:
            return line
        # Textual always draws an X and distinguishes selection by colour;
        # replacing its inner segment makes the boolean state readable in
        # monochrome and independently of the active theme.
        segments = list(line)
        inner = segments[1]
        segments[1] = Segment(" ", inner.style, inner.control)
        return Strip(segments, line.cell_length)


class MarkedCheckbox(Checkbox):
    """Show an X only when checked."""

    @override
    def render(self) -> Content:
        # ToggleButton reads BUTTON_INNER on the instance at render time, so
        # the mark follows the value without touching its private button.
        self.BUTTON_INNER = "X" if self.value else " "
        return super().render()
