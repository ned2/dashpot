"""Present the status, query, and matched count of an item-list filter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast, override

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Select, Static

from ..issues.lifecycle import Lifecycle

# The lifecycle choices every item-list filter offers, in display order.
LIFECYCLE_STATUSES: tuple[tuple[str, str], ...] = (
    ("Open", "open"),
    ("Closed", "closed"),
    ("All", "all"),
)
# The Issue filter adds Ready, the open Issues with no open blocker, beside
# the Open ones it narrows.
ISSUE_LIFECYCLE_STATUSES: tuple[tuple[str, Lifecycle], ...] = (
    ("Open", "open"),
    ("Ready", "ready"),
    ("Closed", "closed"),
    ("All", "all"),
)
_LIFECYCLE_STATES: dict[str, frozenset[str]] = {
    "open": frozenset({"open"}),
    "closed": frozenset({"closed"}),
    "all": frozenset({"open", "closed"}),
}


def lifecycle_value(states: frozenset[str]) -> str:
    """Name the lifecycle a query's states select, as the filter and the source say it."""
    if states == frozenset({"open"}):
        return "open"
    if states == frozenset({"closed"}):
        return "closed"
    return "all"


def lifecycle_states(value: object) -> frozenset[str] | None:
    """The states a lifecycle choice selects; nothing for a value the filter never offers."""
    return _LIFECYCLE_STATES.get(str(value))


def issue_lifecycle(value: object) -> Lifecycle | None:
    """The Issue lifecycle a choice names; nothing for a value the filter never offers."""
    return next(
        (
            lifecycle
            for _label, lifecycle in ISSUE_LIFECYCLE_STATUSES
            if lifecycle == value
        ),
        None,
    )


def next_status(statuses: Sequence[tuple[str, str]], current: str) -> str:
    """The choice after ``current`` in a filter's statuses, wrapping to the first."""
    values = [value for _label, value in statuses]
    if current not in values:
        return values[0]
    return values[(values.index(current) + 1) % len(values)]


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
        # The count carries a page error verbatim, and a Query Source's message
        # may contain square brackets, so it must not be read as markup.
        yield Static(
            self.initial_count,
            id=f"{self.item}-count",
            classes="item-count",
            markup=False,
        )

    @property
    def state(self) -> Select[str]:
        return cast("Select[str]", self.query_one(f"#{self.item}-state", Select))

    @property
    def search(self) -> Input:
        return self.query_one(f"#{self.item}-search", Input)

    @property
    def count(self) -> Static:
        return self.query_one(f"#{self.item}-count", Static)
