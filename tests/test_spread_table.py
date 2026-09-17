from __future__ import annotations

from collections.abc import Callable
from typing import Any, override

import pytest
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from dashpot.ui.spread_table import SpreadTable, proportional_shares, spread_widths


class SpreadTableApp(App[None]):
    """One dashboard table alone on the screen."""

    @override
    def compose(self) -> ComposeResult:
        yield Static("away", id="away")
        yield SpreadTable(id="table")


def counting(monkeypatch: pytest.MonkeyPatch, calls: dict[str, int], name: str) -> None:
    # Nothing public reports how often Textual ran a handler, so the count
    # wraps DataTable's own ``_on_*`` handler that the class dispatch reads.
    original: Callable[..., Any] = getattr(DataTable, name)

    def counted(self: DataTable[Any], event: events.Event) -> None:
        calls[name] = calls.get(name, 0) + 1
        original(self, event)

    monkeypatch.setattr(DataTable, name, counted)


@pytest.mark.asyncio
async def test_a_dashboard_table_runs_each_base_handler_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Textual dispatches a handler by name on every class of the MRO, so a
    # subclass handler that also called the base would run it twice.
    calls: dict[str, int] = {}
    for name in ("_on_resize", "_on_mouse_move", "_on_leave"):
        counting(monkeypatch, calls, name)
    app = SpreadTableApp()

    async with app.run_test(size=(40, 10)) as pilot:
        table = app.query_one("#table", SpreadTable)
        table.add_column("ALPHA", key="alpha")
        table.add_row("a")
        await pilot.pause()
        calls.clear()

        await pilot.resize_terminal(60, 10)
        await pilot.hover("#table", (1, 1))
        await pilot.hover("#away")
        await pilot.pause()

        assert calls == {"_on_resize": 1, "_on_mouse_move": 1, "_on_leave": 1}


def test_shares_follow_the_weights_and_sum_exactly() -> None:
    assert proportional_shares(10, [1, 1, 3, 5]) == [1, 1, 3, 5]
    assert proportional_shares(5, [2, 2, 2]) == [2, 2, 1]
    assert proportional_shares(7, [0, 0, 0]) == [3, 2, 2]
    assert proportional_shares(0, [3, 4]) == [0, 0]
    assert proportional_shares(9, []) == []
    # A zero weight beside real ones takes nothing.
    assert proportional_shares(10, [0, 1, 4]) == [0, 2, 8]


def test_widths_keep_the_content_and_spread_only_the_surplus() -> None:
    # 40 cells, three columns of 1, 5 and 14 with padding 2 each: 26 used.
    assert spread_widths(40, [1, 5, 14], [1, 5, 14], padding=2) == [2, 8, 24]
    # An icon column with weight 0 keeps its width; the rest share the 14.
    assert spread_widths(40, [1, 5, 14], [0, 5, 14], padding=2) == [1, 9, 24]
    # Content that does not fit is left to the table to scroll.
    assert spread_widths(20, [1, 5, 14], [1, 5, 14], padding=2) == [None] * 3
    assert spread_widths(26, [1, 5, 14], [1, 5, 14], padding=2) == [None] * 3
