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

from .glyphs import MUTED_COLORS, Glyph
from .navigation_summary import NavigationSummary

PeerName = Literal["dashboard", "issues-pull-requests"]
PEER_ORDER: tuple[PeerName, ...] = ("dashboard", "issues-pull-requests")
PEER_LABELS: dict[PeerName, str] = {
    "dashboard": "Dashboard",
    "issues-pull-requests": "Issues & Pull Requests",
}

FRESH_TOTALS_GLYPH = Glyph("◆", "every displayed open total is fresh", MUTED_COLORS)
STALE_TOTALS_GLYPH = Glyph(
    "◇", "at least one displayed open total is retained and stale", MUTED_COLORS
)
TOTALS_FRESHNESS_LEGEND = (FRESH_TOTALS_GLYPH, STALE_TOTALS_GLYPH)


@dataclass(eq=False)
class PeerSelected(Message):
    """Request a direct switch to one long-lived peer screen."""

    peer: PeerName


class PeerSelector(Static):
    """One complete clickable peer choice in the persistent status bar."""

    def __init__(self, peer: PeerName, label: str, *, id: str) -> None:
        super().__init__(label, id=id, markup=False)
        self.peer = peer

    def show_active(self, active: bool) -> None:
        """Mark current location without relying on colour."""
        self.set_class(active, "-active")

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
            for position, peer in enumerate(PEER_ORDER, start=1):
                yield PeerSelector(
                    peer,
                    f"{position} {PEER_LABELS[peer]}",
                    id=f"peer-{peer}",
                )
        yield Static("Open PRs: - | Open Issues: -", id="peer-summary", markup=False)

    def on_mount(self) -> None:
        self.show_active(self.active)

    def show_active(self, active: PeerName) -> None:
        """Render the same choices with only current-location encoding changed."""
        self.active = active
        for peer in PEER_ORDER:
            self.query_one(f"#peer-{peer}", PeerSelector).show_active(active == peer)

    def show_summary(self, summary: NavigationSummary) -> None:
        """Render exact open totals with their one aggregate freshness Glyph."""
        text = Text()
        glyph = {
            "fresh": FRESH_TOTALS_GLYPH,
            "stale": STALE_TOTALS_GLYPH,
            None: None,
        }[summary.freshness]
        text.append(summary.text)
        if glyph is not None:
            text.append(" | ")
            text.append(
                glyph.symbol,
                style=glyph.style(dark=self.app.current_theme.dark),
            )
        self.query_one("#peer-summary", Static).update(text)
