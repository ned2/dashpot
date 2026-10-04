"""The Runtime screen: this dashboard's recent Runtime Events and its Runtime Stats.

A full-screen temporary screen over the Peer Screen that opened it, with
two tabs reading the same in-memory buffer over the same window: Events,
one row per event, and Stats, their aggregation. A header above both names
the Event Level, the window and how many events it holds; ``l`` changes the
level for the rest of the run from either tab. The screen sends no request
and keeps no figure of its own: it redraws the shown tab from what the
dashboard already holds, on a short interval while it is open (ADR 0097).
"""

from __future__ import annotations

from typing import ClassVar, Literal, Protocol, override

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, Static, TabbedContent, TabPane

from ..core.event_log import DASHBOARD_RECENT_WINDOW, EventLog
from ..core.runtime_stats import covered_since
from .runtime_events_view import STACK_BELOW_WIDTH, EventsPane, EventsSubject
from .runtime_stats_view import (
    RuntimeStatsPane,
    RuntimeStatsSubject,
    covered_text,
    next_level,
)

RuntimeTab = Literal["events", "stats"]


class RuntimeSubject(RuntimeStatsSubject, EventsSubject, Protocol):
    """What the Runtime screen reads from the dashboard that opened it."""


def header_text(log: EventLog) -> str:
    """The Event Level, whose events these are, the window, and how many it holds."""
    now = log.clock()
    buffered = log.recent_events()
    since = covered_since(
        buffered, now=now, window=DASHBOARD_RECENT_WINDOW, limit=log.recent_limit
    )
    count = len(buffered)
    noun = "event" if count == 1 else "events"
    return (
        f"Event Level: {log.level} (l changes it) · this dashboard · "
        f"{covered_text(log, since, now)} · {count:,} {noun}"
    )


class RuntimeScreen(Screen[None]):
    """Show this dashboard's recent Runtime Events and Runtime Stats, updating while open."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("e", "show_tab('events')", "Events"),
        Binding("s", "show_tab('stats')", "Stats"),
        Binding("l", "cycle_level", "Change Event Level"),
    ]

    def __init__(
        self, subject: RuntimeSubject, *, tab: RuntimeTab, update_seconds: float
    ) -> None:
        super().__init__()
        self.subject = subject
        self.initial_tab: RuntimeTab = tab
        self.update_seconds = update_seconds
        self.update_timer: Timer | None = None

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="runtime-view"):
            yield Static("", id="runtime-header", markup=False)
            with TabbedContent(initial=self.initial_tab, id="runtime-tabs"):
                with TabPane("Events", id="events"):
                    yield EventsPane(self.subject, id="runtime-events")
                with TabPane("Stats", id="stats"):
                    yield RuntimeStatsPane(self.subject, id="runtime-stats")
        yield Footer()

    def on_mount(self) -> None:
        self.subject.measure_event_log()
        self.apply_layout(self.size.width)
        self.show_tab_content()
        self.update_timer = self.set_interval(self.update_seconds, self.update_shown)

    @property
    def tab(self) -> RuntimeTab:
        """The tab shown now."""
        return "stats" if self.tabs.active == "stats" else "events"

    @property
    def tabs(self) -> TabbedContent:
        return self.query_one("#runtime-tabs", TabbedContent)

    def update_shown(self) -> None:
        """Redraw the header and the shown tab from what the dashboard holds now."""
        self.query_one("#runtime-header", Static).update(
            header_text(self.subject.event_log)
        )
        if self.tab == "events":
            self.query_one(EventsPane).update_events()
        else:
            self.query_one(RuntimeStatsPane).update_stats()

    @on(TabbedContent.TabActivated, "#runtime-tabs")
    def tab_shown(self) -> None:
        self.show_tab_content()

    def show_tab_content(self) -> None:
        """Draw the tab now shown, give it focus, and offer the other tab's key."""
        self.refresh_bindings()
        self.update_shown()
        self.tab_focus(self.tab).focus()

    def tab_focus(self, tab: RuntimeTab) -> Widget:
        """The widget a tab focuses when it is shown: the event table, or the stats."""
        if tab == "events":
            return self.query_one(EventsPane).table
        return self.query_one(RuntimeStatsPane)

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Offer each tab's key only from the other tab."""
        if action == "show_tab":
            return parameters != (self.tab,)
        return True

    def action_show_tab(self, tab: RuntimeTab) -> None:
        # A focus left in the tab being hidden moves to a widget beside it,
        # and TabbedContent shows the pane that widget is in, so the tab
        # being shown takes the focus first.
        self.tab_focus(tab).focus()
        self.tabs.active = tab

    def action_cycle_level(self) -> None:
        """Move to the next Event Level for the rest of this run, never the settings."""
        self.subject.set_event_level(next_level(self.subject.event_log.level))
        self.update_shown()

    def action_close(self) -> None:
        self.dismiss(None)

    def on_resize(self, event: events.Resize) -> None:
        self.apply_layout(event.size.width)

    def apply_layout(self, width: int) -> None:
        self.query_one("#runtime-view").set_class(width < STACK_BELOW_WIDTH, "-stacked")
