from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static


DetailKind = Literal["field", "heading", "section", "list", "message"]


@dataclass(frozen=True)
class DetailItem:
    value: str | Text
    label: str = ""
    kind: DetailKind = "field"


class DetailRow(Horizontal):
    """One reusable row in a read-only field/value display."""

    def __init__(self, item: DetailItem) -> None:
        super().__init__()
        self.field_name = Static(classes="field-name", markup=False)
        self.field_value = Static(classes="field-value", markup=False)
        self.item = item

    def compose(self) -> ComposeResult:
        yield self.field_name
        yield self.field_value

    def on_mount(self) -> None:
        self.update_item(self.item)

    def update_item(self, item: DetailItem) -> None:
        self.item = item
        self.set_classes(f"-{item.kind}")
        self.field_name.update(item.label)
        self.field_value.update(item.value)


class DetailFields(VerticalScroll):
    """A compact, dynamically updated description list."""

    def __init__(
        self,
        *items: DetailItem,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.items = tuple(items)
        self.rows: list[DetailRow] = []

    def compose(self) -> ComposeResult:
        for item in self.items:
            row = DetailRow(item)
            self.rows.append(row)
            yield row

    def update(self, *items: DetailItem) -> None:
        """Replace displayed items while reusing already mounted rows."""

        self.items = tuple(items)
        for index, item in enumerate(items):
            if index < len(self.rows):
                row = self.rows[index]
                row.display = True
                row.update_item(item)
            else:
                row = DetailRow(item)
                self.rows.append(row)
                self.mount(row)
        for row in self.rows[len(items) :]:
            row.display = False
        self.scroll_home(animate=False)

    @property
    def plain(self) -> str:
        """Return an unstyled projection for tests and accessibility."""

        return detail_items_text(self.items)


def detail_items_text(items: Sequence[DetailItem]) -> str:
    lines = []
    for item in items:
        if item.kind == "field":
            lines.append(f"{item.label}: {_plain(item.value)}")
        elif item.kind == "list":
            lines.append(f"  {_plain(item.value)}")
        elif item.kind == "section":
            lines.append(f"{_plain(item.value)}:")
        else:
            lines.append(_plain(item.value))
    return "\n".join(lines)


def _plain(value: str | Text) -> str:
    """Rendered chips carry padding for colour; the text form does not."""
    return value.plain.strip() if isinstance(value, Text) else value
