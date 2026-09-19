"""Render navigation and exact Project Totals on both Peer Screens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, override

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from .glyphs import ATTENTION_COLORS, GOOD_COLORS, Glyph
from .navigation_summary import NavigationSummary

PeerName = Literal["dashboard", "issues-pull-requests"]

FRESH_TOTALS_GLYPH = Glyph("◆", "every displayed open total is fresh", GOOD_COLORS)
STALE_TOTALS_GLYPH = Glyph(
    "◇", "at least one displayed open total is retained and stale", ATTENTION_COLORS
)
TOTALS_FRESHNESS_LEGEND = (FRESH_TOTALS_GLYPH, STALE_TOTALS_GLYPH)


@dataclass(eq=False)
class PeerSelected(Message):
    """Request a direct switch to one long-lived peer screen."""

    peer: PeerName


class PeerLink(Static):
    """One complete clickable peer label in the persistent status bar."""

    def __init__(self, peer: PeerName, label: str, *, id: str) -> None:
        super().__init__(label, id=id, markup=False)
        self.peer = peer
        self.label = label

    def show_active(self, active: bool) -> None:
        """Mark current location without relying on colour."""
        self.update(f"[{self.label}]" if active else self.label)

    def on_click(self) -> None:
        self.post_message(PeerSelected(self.peer))


class PeerStatusBar(Widget):
    """The shared screen switcher and navigation-summary chrome."""

    def __init__(self, active: PeerName) -> None:
        super().__init__(id="peer-status")
        self.active = active

    @override
    def compose(self) -> ComposeResult:
        with Horizontal(id="peer-status-screens"):
            yield PeerLink("dashboard", "1 Dashboard", id="peer-dashboard")
            yield PeerLink(
                "issues-pull-requests",
                "2 Issues & Pull Requests",
                id="peer-issues-pull-requests",
            )
        yield Static("Open Issues: - | Open PRs: -", id="peer-summary", markup=False)

    def on_mount(self) -> None:
        self.show_active(self.active)

    def show_active(self, active: PeerName) -> None:
        """Render the same choices with only current-location encoding changed."""
        self.active = active
        self.query_one("#peer-dashboard", PeerLink).show_active(active == "dashboard")
        self.query_one("#peer-issues-pull-requests", PeerLink).show_active(
            active == "issues-pull-requests"
        )

    def show_summary(self, summary: NavigationSummary) -> None:
        """Render exact open totals with their one aggregate freshness Glyph."""
        text = Text()
        glyph = {
            "fresh": FRESH_TOTALS_GLYPH,
            "stale": STALE_TOTALS_GLYPH,
            None: None,
        }[summary.freshness]
        if glyph is not None:
            text.append(
                f"{glyph.symbol} ",
                style=glyph.style(dark=self.app.current_theme.dark),
            )
        text.append(summary.text)
        self.query_one("#peer-summary", Static).update(text)
