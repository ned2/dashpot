from __future__ import annotations

from typing import ClassVar, cast

from rich.segment import Segment
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widgets import Button, SelectionList, Static
from typing_extensions import override

from .issue_table import COLUMN_KEYS, COLUMNS_BY_KEY, ColumnKey


class ColumnSelectionList(SelectionList[ColumnKey]):
    """Show an X only for a selected Issue-table column."""

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


class IssueColumnEditor(ModalScreen[tuple[ColumnKey, ...] | None]):
    """Edit the visible subset and order of the Issue table catalogue."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+up", "move_up", "Move up"),
        ("ctrl+down", "move_down", "Move down"),
    ]

    def __init__(self, visible_columns: tuple[ColumnKey, ...]) -> None:
        super().__init__()
        hidden_columns = tuple(
            column for column in COLUMN_KEYS if column not in visible_columns
        )
        self.column_order = [*visible_columns, *hidden_columns]
        self.initially_visible = frozenset(visible_columns)

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="column-editor-dialog"):
            yield Static("ISSUE TABLE COLUMNS", id="column-editor-title")
            yield Static(
                "Select visible columns; move the highlighted column to reorder it.",
                id="column-editor-help",
            )
            yield ColumnSelectionList(
                *self.selection_options(self.initially_visible),
                id="column-editor-list",
            )
            yield Static("", id="column-editor-error")
            with Horizontal(id="column-editor-actions"):
                yield Button("Up", id="column-up")
                yield Button("Down", id="column-down")
                yield Button("Cancel", id="column-cancel")
                yield Button("Apply", id="column-apply", variant="primary")

    def on_mount(self) -> None:
        selections = self.query_one("#column-editor-list", SelectionList)
        selections.highlighted = 0
        selections.focus()

    def selection_options(
        self, selected: frozenset[ColumnKey] | set[ColumnKey]
    ) -> tuple[tuple[str, ColumnKey, bool], ...]:
        return tuple(
            (
                COLUMNS_BY_KEY[column].label,
                column,
                column in selected,
            )
            for column in self.column_order
        )

    def action_move_up(self) -> None:
        self.move_highlighted(-1)

    def action_move_down(self) -> None:
        self.move_highlighted(1)

    def move_highlighted(self, offset: int) -> None:
        selections = self.query_one("#column-editor-list", SelectionList)
        index = selections.highlighted
        if index is None:
            return
        destination = index + offset
        if destination < 0 or destination >= len(self.column_order):
            return
        selected = {cast(ColumnKey, column) for column in selections.selected}
        self.column_order[index], self.column_order[destination] = (
            self.column_order[destination],
            self.column_order[index],
        )
        selections.clear_options()
        selections.add_options(self.selection_options(selected))
        selections.highlighted = destination
        selections.focus()

    def action_apply(self) -> None:
        selections = self.query_one("#column-editor-list", SelectionList)
        selected = {cast(ColumnKey, column) for column in selections.selected}
        columns = tuple(column for column in self.column_order if column in selected)
        if not columns:
            self.query_one("#column-editor-error", Static).update(
                "Choose at least one visible column."
            )
            return
        self.dismiss(columns)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "column-up": self.action_move_up,
            "column-down": self.action_move_down,
            "column-cancel": self.action_cancel,
            "column-apply": self.action_apply,
        }
        action = actions.get(event.button.id or "")
        if action is not None:
            action()
