"""Present the status, query, and matched count of an item-list filter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Select, Static
from typing_extensions import override


class ItemFilterBar(Horizontal):
    """Keep one item list's filtering controls together under stable identities."""

    HEIGHT = 3

    def __init__(
        self,
        item: str,
        *,
        statuses: Sequence[tuple[str, str]],
        status: str,
        query: str,
        placeholder: str,
        count: str,
    ) -> None:
        super().__init__(id=f"{item}-filters")
        self.item = item
        self.statuses = tuple(statuses)
        self.initial_status = status
        self.initial_query = query
        self.placeholder = placeholder
        self.initial_count = count

    @override
    def compose(self) -> ComposeResult:
        yield Select(
            self.statuses,
            value=self.initial_status,
            allow_blank=False,
            compact=True,
            id=f"{self.item}-state",
            classes="item-state",
        )
        yield Input(
            value=self.initial_query,
            placeholder=self.placeholder,
            compact=True,
            id=f"{self.item}-search",
            classes="item-search",
        )
        yield Static(self.initial_count, id=f"{self.item}-count", classes="item-count")

    @property
    def state(self) -> Select[str]:
        return cast("Select[str]", self.query_one(f"#{self.item}-state", Select))

    @property
    def search(self) -> Input:
        return self.query_one(f"#{self.item}-search", Input)

    @property
    def count(self) -> Static:
        return self.query_one(f"#{self.item}-count", Static)
