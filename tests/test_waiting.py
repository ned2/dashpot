"""The suite's waiting seam: ``settled`` reads geometry only once it stops changing.

A scripted frame driver pins the seam's contract frame by frame, including a
deliberate under-settle; a small Textual app shows it waiting out a change
that Textual lays out over several frames.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import count
from typing import override

import pytest
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Static

from helpers import settled, wait_until


class ScriptedFrames:
    """A frame driver whose every pause shows the next scripted reading."""

    def __init__(self, readings: Sequence[int]) -> None:
        self.readings = tuple(readings)
        self.frame = 0

    async def pause(self) -> None:
        self.frame = min(self.frame + 1, len(self.readings) - 1)

    def read(self) -> int:
        return self.readings[self.frame]


@pytest.mark.asyncio
async def test_settled_waits_out_every_frame_of_a_change() -> None:
    # A pane's height as a proxy first reports its change (4), then over the
    # following frames as it is fitted (6, 7), until it holds.
    frames = ScriptedFrames([4, 6, 7, 7, 7])

    assert frames.read() == 4
    assert await settled(frames, frames.read, "the pane") == 7
    # The height held for two frames, and no frame beyond them was driven.
    assert frames.frame == 4


@pytest.mark.asyncio
async def test_an_under_settle_fails_naming_what_did_not_settle() -> None:
    # Allowed one frame fewer than the change needs to settle, the seam fails
    # rather than handing back the reading of a frame still being laid out.
    frames = ScriptedFrames([4, 6, 7, 7, 7])

    with pytest.raises(
        AssertionError, match=r"^the pane did not settle within 3 frames; last read 7$"
    ):
        await settled(frames, frames.read, "the pane", frames=3)


@pytest.mark.asyncio
async def test_a_reading_that_never_settles_fails_within_its_bound() -> None:
    frames = ScriptedFrames([0])
    readings = count()

    with pytest.raises(
        AssertionError, match=r"^a counter did not settle within 20 frames"
    ):
        await settled(frames, lambda: next(readings), "a counter")
    assert next(readings) == 21


class Grower(Static):
    """A widget that grows a row on each frame, once started, until six rows."""

    growing = False

    def on_resize(self, event: events.Resize) -> None:
        if self.growing and event.size.height < 6:
            self.styles.height = event.size.height + 1


class GrowerApp(App[None]):
    """One widget whose growth Textual lays out over several frames."""

    CSS = "#grower { height: 1; }"

    @override
    def compose(self) -> ComposeResult:
        yield Grower("grows", id="grower")


@pytest.mark.asyncio
async def test_settled_reads_a_textual_layout_once_it_is_complete() -> None:
    app = GrowerApp()

    async with app.run_test(size=(20, 10)) as pilot:
        grower = app.query_one("#grower", Grower)
        await wait_until(lambda: grower.region.height == 1)
        grower.growing = True
        grower.styles.height = 2

        # The proxy holds from the first grown frame; the height settles later.
        await wait_until(lambda: grower.region.height > 1)
        height = await settled(pilot, lambda: grower.region.height, "the grower")
        assert height == 6
        assert grower.region.height == 6
