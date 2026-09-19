"""Compose the application, its long-lived peer screens, and their panes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Any, ClassVar, cast, override

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.geometry import Size
from textual.message import Message
from textual.screen import Screen
from textual.theme import Theme
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Input, Select, Static
from textual.worker import get_current_worker

from ..core.commands import RunningCommands
from ..observation.collect import ObservationScheduler
from ..observation.issue_list import issue_result_count_text, next_issue_states
from ..observation.paged_store import PagedObservationStore
from ..observation.related_rows import FocusedSource, query_related_rows
from ..observation.worktree_list import WorktreeListRow
from ..queries.page_navigation import totals_text
from ..queries.source_queries import QuerySource, ResourceKind
from ..repository.cleanup import CleanupAdapter
from ..repository.fetch import RemoteFetcher
from ..repository.worktree_launcher import LauncherConfiguration, WorktreeLaunchError
from .alerts import Alert, list_diagnostics, summarize_alerts
from .cleanup_flow import CleanupFlow, CleanupSelection
from .cleanup_view import CleanupReportScreen, CleanupScreen
from .column_editor import IssueColumnEditor
from .fetch_flow import RemoteFetchFlow
from .focus_table import FocusCursorTable
from .issue_cells import issue_state_colors
from .issue_table import COLUMNS_BY_KEY, ColumnKey, IssueTable, shown_columns
from .issue_table_controller import IssueTableController
from .issue_view import IssueScreen
from .item_filter import LIFECYCLE_STATUSES, ItemFilterBar, lifecycle_value
from .keyed_table import capture_selection
from .legend import KeyGroup, LegendScreen
from .list_pane import ISSUE_PANE_LABEL, ListPane
from .list_queries import ListQueries
from .messages import (
    BodyResized,
    CleanupFinished,
    CleanupInspected,
    FetchFinished,
    IdentitiesFinished,
    ObservationFinished,
    ObservationTrigger,
    PageFinished,
    TotalsFinished,
)
from .navigation_summary import navigation_summary
from .observation_runner import (
    Acceptance,
    DroppedObservation,
    FailedObservation,
    ObservationRunner,
)
from .page_runner import PageRunner
from .pane_layout import fit_panes, pane_wish
from .panes import (
    DASHBOARD_PANE_SPECS,
    QUERY_PANE_SPECS,
    ListPaneId,
    PaneContext,
    PaneSpec,
)
from .status_bar import PeerName, PeerSelected, PeerStatusBar
from .worktree_table import WorktreeTable

# The focus cycle is an override of Textual's own hidden Tab bindings, not a
# Binding of the dashboard's; the Legend lists it as the keys a person presses.
FOCUS_CYCLE_BINDINGS: tuple[BindingType, ...] = (
    ("tab", "focus_next", "Next list"),
    ("shift+tab", "focus_previous", "Previous list"),
)


class PeerBody(Container):
    """One peer's pane stack and the height budget its list panes fit into."""

    def on_resize(self, event: events.Resize) -> None:
        self.post_message(BodyResized(event.size))


def paint_readout(
    widget: Static,
    readout: Alert | None,
    *,
    shown: str,
    text: Callable[[Alert], str],
) -> None:
    """Show one shared readout with its severity, or hide it entirely."""
    widget.set_class(readout is not None, shown)
    for severity in ("error", "warning", "info"):
        widget.set_class(
            readout is not None and readout.severity == severity, f"-{severity}"
        )
    widget.update("" if readout is None else text(readout))


def peer_surfaces_mounted(
    screen: Screen[None],
    pane_ids: tuple[ListPaneId, ...],
    *,
    extra_selectors: tuple[str, ...] = (),
) -> bool:
    """Whether updates can still reach one peer's complete rendered surface."""
    try:
        panes = tuple(screen.query_one(f"#{pane_id}", ListPane) for pane_id in pane_ids)
        widgets = (
            screen.query_one(PeerStatusBar),
            screen.query_one("#alert", Static),
            screen.query_one("#diagnostics", Static),
            *(screen.query_one(selector, Widget) for selector in extra_selectors),
            *(pane.table for pane in panes),
        )
    except NoMatches:
        return False
    return all(widget.is_mounted for widget in widgets)


def cycle_table_focus(
    tables: tuple[FocusCursorTable[Any], ...], focused: Widget | None, step: int
) -> bool:
    """Move focus within one peer's table cycle when a table owns it."""
    if focused not in tables:
        return False
    tables[(tables.index(focused) + step) % len(tables)].focus()
    return True


def update_peer_status(screen: Screen[None], app: DashpotApp) -> None:
    """Render one peer's location and shared Project Totals summary."""
    if screen.is_mounted:
        screen.query_one(PeerStatusBar).show_summary(
            navigation_summary(app.store.totals)
        )


def update_peer_alert(screen: Screen[None], app: DashpotApp) -> None:
    """Render one peer's exceptional-state readout, or hide it."""
    alert = summarize_alerts(
        app.store,
        failures=app.observations.errors,
        refreshing=app.observations.refreshing,
        fetching=tuple(app.fetches.fetching),
        page_states=app.queries.page_states,
        first_observations_in_flight=app.observations.first_observations_in_flight,
    )
    paint_readout(
        screen.query_one("#alert", Static),
        alert,
        shown="-visible",
        text=lambda value: value.text,
    )


def update_peer_diagnostics(screen: Screen[None], app: DashpotApp) -> None:
    """Render one peer's Diagnostics and exceptional-state readouts."""
    readout = list_diagnostics(
        app.store,
        failures=app.observations.errors,
        launcher_diagnostics=app.launcher_configuration.diagnostics,
        fetch_failures=app.fetches.errors,
    )
    paint_readout(
        screen.query_one("#diagnostics", Static),
        readout,
        shown="-has-messages",
        text=lambda value: value.lines,
    )
    update_peer_alert(screen, app)


class DashboardScreen(Screen[None]):
    """Present Sessions, Worktrees and Branches as the default long-lived peer."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("f", "fetch", "Fetch & prune remotes"),
        ("x", "cleanup", "Delete Branch/Worktree"),
    ]

    @property
    def dashpot(self) -> DashpotApp:
        """The application that owns shared observations and mutations."""
        return cast("DashpotApp", self.app)

    @override
    def compose(self) -> ComposeResult:
        yield PeerStatusBar("dashboard")
        with PeerBody(id="body"), Container(id="list-row"):
            for spec in DASHBOARD_PANE_SPECS:
                yield ListPane(
                    spec.label,
                    columns=spec.columns,
                    empty_message=spec.empty_message,
                    id=spec.pane_id,
                    table_id=spec.table_id,
                    table_type=spec.table_type,
                    controls_height=spec.controls_height,
                )
        yield Static("", id="alert")
        yield Static("", id="diagnostics")
        yield Footer()

    def status_bar(self) -> PeerStatusBar:
        """The persistent peer navigation chrome on this screen."""
        return self.query_one(PeerStatusBar)

    def list_pane(self, pane_id: ListPaneId) -> ListPane:
        """One Dashboard list pane by its declared id."""
        return self.query_one(f"#{pane_id}", ListPane)

    def sessions_pane(self) -> ListPane:
        return self.list_pane("sessions-pane")

    def branches_pane(self) -> ListPane:
        return self.list_pane("branches-pane")

    def worktrees_pane(self) -> ListPane:
        return self.list_pane("worktrees-pane")

    def list_panes(self) -> tuple[ListPane, ...]:
        """The Dashboard panes in reading order."""
        return tuple(self.list_pane(spec.pane_id) for spec in DASHBOARD_PANE_SPECS)

    def focus_tables(self) -> tuple[FocusCursorTable[Any], ...]:
        """The Dashboard tables in composition order."""
        return tuple(self.query_one("#body").query(FocusCursorTable))

    def surfaces_mounted(self) -> bool:
        """Report whether updates can still reach every Dashboard surface."""
        return peer_surfaces_mounted(
            self, tuple(spec.pane_id for spec in DASHBOARD_PANE_SPECS)
        )

    def on_mount(self) -> None:
        self.sessions_pane().table.focus()
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)
        self.update_status()

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render semantic colours for the new theme brightness."""
        if self.dashpot.store.has_observations:
            self.reconcile_list_panes()
        self.update_status()

    def action_fetch(self) -> None:
        """Fetch the remotes behind the Branches pane, on explicit invocation."""
        self.dashpot.request_fetch()

    def action_cleanup(self) -> None:
        """Preview a Cleanup of the selected Branch or Worktree."""
        self.dashpot.request_cleanup(self.cleanup_selection())

    def cleanup_selection(self) -> CleanupSelection | None:
        """The selected Branch or Worktree row, when either pane owns focus."""
        for kind, pane in (
            ("branch", self.branches_pane()),
            ("worktree", self.worktrees_pane()),
        ):
            if self.focused is pane.table:
                key, _index = pane.highlighted()
                return None if key is None else CleanupSelection(kind, key)
        return None

    def cycle_list_focus(self, step: int) -> bool:
        """Move focus within the Dashboard table cycle when one owns it."""
        return cycle_table_focus(self.focus_tables(), self.focused, step)

    def on_focus_cursor_table_row_boundary_reached(
        self, event: FocusCursorTable.RowBoundaryReached
    ) -> None:
        """Move focus when the current Dashboard table reaches a row boundary."""
        if self.focused is event.control:
            self.cycle_list_focus(event.step)

    def on_body_resized(self, message: BodyResized) -> None:
        if not self.is_mounted or not self.surfaces_mounted():
            return
        self.fit_list_panes(message.size)

    def on_list_pane_rows_changed(self, _message: ListPane.RowsChanged) -> None:
        if not self.is_mounted or not self.surfaces_mounted():
            return
        self.refresh_bindings()
        self.fit_list_panes(self.query_one("#body").size)

    def fit_list_panes(self, body: Size) -> None:
        """Fit Dashboard lists to their content cap within the peer body."""
        panes = self.list_panes()
        caps = fit_panes(
            body.height,
            0,
            tuple(pane_wish(pane.count) for pane in panes),
        )
        for pane, row_cap in zip(panes, caps, strict=True):
            pane.fit_rows(row_cap)

    def reconcile_list_panes(self) -> None:
        """Re-list every Dashboard record from the shared store."""
        context = PaneContext(
            self.dashpot.store,
            self.dashpot.queries.navigation,
            dark=self.app.current_theme.dark,
            now=datetime.now(UTC),
        )
        for spec in DASHBOARD_PANE_SPECS:
            view = spec.rows(context)
            self.list_pane(spec.pane_id).show_rows(
                view.rows,
                columns=view.columns,
                note=view.note,
                empty_message=view.empty_message,
                title_summary=view.title_summary,
                filter_count=view.filter_count,
                records=view.records,
            )
        self.update_related_rows()

    def records(self) -> tuple[FocusedSource, ...]:
        """The Dashboard records last rendered into its three panes."""
        return tuple(chain.from_iterable(pane.records for pane in self.list_panes()))

    def update_related_rows(self, *, clear: bool = False) -> None:
        """Emphasize relationships that stay entirely within Dashboard."""
        if not self.is_mounted or not self.surfaces_mounted():
            return
        records = self.records()
        source: FocusedSource | None = None
        focused = self.focused
        if (
            not clear
            and self.app.screen is self
            and isinstance(focused, FocusCursorTable)
        ):
            key, _index = capture_selection(focused)
            source = next((record for record in records if record.key == key), None)
        related = query_related_rows(source, records)
        for spec in DASHBOARD_PANE_SPECS:
            if spec.related is not None:
                self.list_pane(spec.pane_id).table.set_related_rows(
                    spec.related(related), spec.related_columns
                )

    @on(DataTable.RowHighlighted)
    def follow_cursor(self, event: DataTable.RowHighlighted) -> None:
        """Re-emphasise Dashboard relationships when its focused cursor moves."""
        if self.is_mounted and event.data_table.has_focus:
            self.update_related_rows()

    def on_focus_cursor_table_focus_changed(
        self, _event: FocusCursorTable.FocusChanged
    ) -> None:
        self.update_related_rows()

    def on_screen_suspend(self, _: events.ScreenSuspend) -> None:
        self.update_related_rows(clear=True)

    def on_screen_resume(self, _: events.ScreenResume) -> None:
        self.call_after_refresh(self.update_related_rows)

    def on_worktree_table_open_requested(
        self, event: WorktreeTable.OpenRequested
    ) -> None:
        """Launch the Worktree captured by keyboard activation."""
        self.dashpot.request_worktree_open(event.key)

    def on_worktree_table_copy_requested(
        self, event: WorktreeTable.CopyRequested
    ) -> None:
        """Send the complete observed Worktree path to the terminal clipboard."""
        path = self.dashpot.worktree_path(event.key)
        if path is not None:
            self.app.copy_to_clipboard(str(path))
            self.app.notify("Path sent to clipboard")

    def update_status(self) -> None:
        """Render current location and the shared Project Totals summary."""
        update_peer_status(self, self.dashpot)

    def update_diagnostics(self) -> None:
        """Render every Diagnostic and the exceptional-state alert."""
        update_peer_diagnostics(self, self.dashpot)

    def update_alert(self) -> None:
        """Render the shared exceptional-state readout, or hide it."""
        update_peer_alert(self, self.dashpot)


class IssuesPullRequestsScreen(Screen[None]):
    """Own the Pull Request and Issue query panes and their contextual actions."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "open_issue", "Open Issue"),
        ("slash", "focus_search", "Search"),
        ("c", "columns", "Columns"),
        ("o", "cycle_issue_state", "Open/Closed/All"),
        ("n", "next_page", "Next page"),
        ("p", "previous_page", "Previous page"),
        # Not Home: the focused table and the search Input both bind it, so
        # the screen would never see it. Neither owns a plain letter.
        ("g", "restart_page", "First page"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.issue_table = IssueTableController(self)
        # The app is looked up when a page is submitted, not held from here.
        self.list_queries = ListQueries(
            lambda kind, **updates: self.dashpot.submit_page(kind, **updates)
        )
        query = self.list_queries.issues
        self.issue_filter_bar = ItemFilterBar(
            "issue",
            statuses=LIFECYCLE_STATUSES,
            status=lifecycle_value(query.states),
            query=query.text,
            placeholder="Search Issues",
            count=issue_result_count_text(0),
        )
        # The filter bar of each paged kind, composed once: the Issue table's
        # own and each list pane's from its spec.
        self.filter_bars: dict[ResourceKind, ItemFilterBar] = {
            "issues": self.issue_filter_bar
        }
        for spec in QUERY_PANE_SPECS:
            if spec.controls is not None and spec.query_kind is not None:
                self.filter_bars[spec.query_kind] = spec.controls()

    @property
    def dashpot(self) -> DashpotApp:
        """Narrow `self.app` once: the store and the runners live there.

        Use `dashpot` for Dashpot-owned state (the store, the observation
        and page runners, the flows) and plain `app` for the Textual API.
        """
        return cast("DashpotApp", self.app)

    def page_kind(self) -> ResourceKind:
        """The paged kind of the list pane holding focus, else the Issue table's."""
        for spec in QUERY_PANE_SPECS:
            if (
                spec.query_kind is not None
                and self.list_pane(spec.pane_id).has_focus_within
            ):
                return spec.query_kind
        return "issues"

    def action_next_page(self) -> None:
        self.dashpot.queries.next_page(self.page_kind())
        self.dashpot.render_pages()

    def action_previous_page(self) -> None:
        self.dashpot.queries.previous_page(self.page_kind())
        self.dashpot.render_pages()

    def action_restart_page(self) -> None:
        self.dashpot.queries.restart_page(self.page_kind())
        self.dashpot.render_pages()

    @override
    def compose(self) -> ComposeResult:
        yield PeerStatusBar("issues-pull-requests")
        with PeerBody(id="query-body"), Container(id="query-list-row"):
            for spec in QUERY_PANE_SPECS:
                yield ListPane(
                    spec.label,
                    columns=spec.columns,
                    empty_message=spec.empty_message,
                    id=spec.pane_id,
                    table_id=spec.table_id,
                    table_type=spec.table_type,
                    controls=self.pane_controls(spec),
                    controls_height=spec.controls_height,
                )
            with Vertical(id="queue-pane"):
                yield self.issue_filter_bar
                yield IssueTable(id="queue", cursor_type="row", zebra_stripes=False)
        yield Static("", id="alert")
        yield Static("", id="diagnostics")
        yield Footer()

    def queue_table(self) -> IssueTable:
        """The Issue table; `query_one` cannot name the cell type itself."""
        return self.query_one("#queue", IssueTable)

    def status_bar(self) -> PeerStatusBar:
        """The persistent peer navigation chrome on this screen."""
        return self.query_one(PeerStatusBar)

    def list_pane(self, pane_id: ListPaneId) -> ListPane:
        """One list pane by its spec's id."""
        return self.query_one(f"#{pane_id}", ListPane)

    def pull_requests_pane(self) -> ListPane:
        return self.list_pane("pull-requests-pane")

    def pane_controls(self, spec: PaneSpec) -> ItemFilterBar | None:
        """The filter bar composed for a pane's paged kind, when it has one."""
        return None if spec.query_kind is None else self.filter_bars[spec.query_kind]

    def filter_kind(self, control: Widget) -> ResourceKind:
        """The paged kind whose filter bar holds ``control``."""
        return next(
            kind
            for kind, bar in self.filter_bars.items()
            if control in (bar.search, bar.state)
        )

    def list_panes(self) -> tuple[ListPane, ...]:
        """The content-sized panes in reading order."""
        return tuple(self.list_pane(spec.pane_id) for spec in QUERY_PANE_SPECS)

    def focus_tables(self) -> tuple[FocusCursorTable[Any], ...]:
        """Return the query peer's tables in their composed reading order."""
        return tuple(self.query_one("#query-body").query(FocusCursorTable))

    def surfaces_mounted(self) -> bool:
        """Report whether dashboard updates can still reach every surface.

        Every entry point that renders into the panes, the alert or the
        diagnostics asks first: a late message can be dispatched during
        shutdown while the widgets are being unmounted one by one.
        """
        return peer_surfaces_mounted(
            self,
            tuple(spec.pane_id for spec in QUERY_PANE_SPECS),
            extra_selectors=("#queue",),
        )

    def action_focus_search(self) -> None:
        """Focus the search of the focused pane's controls, else the Issue search."""
        for pane in self.list_panes():
            if pane.has_focus_within and pane.controls is not None:
                pane.controls.search.focus()
                return
        self.issue_filter_bar.search.focus()

    def cycle_list_focus(self, step: int) -> bool:
        """Move focus to the next list when a list has it; otherwise decline."""
        return cycle_table_focus(self.focus_tables(), self.focused, step)

    def on_focus_cursor_table_row_boundary_reached(
        self, event: FocusCursorTable.RowBoundaryReached
    ) -> None:
        """Move focus when the focused table cannot move its row cursor."""
        if self.focused is event.control:
            self.cycle_list_focus(event.step)

    def on_focus_cursor_table_focus_changed(
        self, _event: FocusCursorTable.FocusChanged
    ) -> None:
        self.refresh_bindings()

    def on_mount(self) -> None:
        self.query_one("#queue-pane").border_title = Content(ISSUE_PANE_LABEL)
        self.issue_table.show_table_columns(
            shown_columns(self.issue_table.issue_view.columns, ())
        )
        self.pull_requests_pane().table.focus()
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)
        for kind, bar in self.filter_bars.items():
            bar.search.placeholder = self.dashpot.queries.sources[kind].search_prompt
        self.update_status()
        self.call_after_refresh(self.update_status)
        if self.dashpot.store.pages:
            self.queue_table().loading = False
            self.issue_table.reconcile_rows()
            self.update_issue_inventory()
            self.reconcile_list_panes()
            self.update_diagnostics()
        else:
            self.queue_table().loading = True

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render semantic table colors for the new theme brightness."""

        if self.dashpot.store.has_observations:
            self.issue_table.reconcile_rows()
            # The list panes render their glyphs in explicit colours chosen
            # for the theme's brightness, so they repaint with the table.
            self.reconcile_list_panes()

    def action_columns(self) -> None:
        if self.page_kind() != "issues":
            return
        self.app.push_screen(
            IssueColumnEditor(self.issue_table.issue_view.columns),
            self.issue_table.apply_issue_columns,
        )

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Expose only actions meaningful for the focused query pane."""
        if isinstance(self.focused, Input):
            return None
        if action in {"columns", "open_issue"} and not self.surfaces_mounted():
            return None
        if action == "columns":
            return True if self.query_one("#queue-pane").has_focus_within else None
        if action == "open_issue":
            available = (
                self.queue_table().has_focus
                and self.issue_table.selected_row_key is not None
            )
            return True if available else None
        return True

    @on(DataTable.HeaderSelected, "#queue")
    def submit_column_ordering(self, event: DataTable.HeaderSelected) -> None:
        """Order the Issue table by the selected column."""
        self.order_issues_by(str(event.column_key.value))

    def order_issues_by(self, column: str) -> None:
        """Submit the column's ordering to the source, or reverse it."""
        queries = self.dashpot.queries
        if not queries.supports_sort("issues", column):
            self.notify(
                "This column cannot order the submitted source query",
                severity="information",
            )
            return
        if (
            column not in COLUMNS_BY_KEY
            or not COLUMNS_BY_KEY[cast("ColumnKey", column)].sortable
        ):
            return
        ordering = queries.navigation["issues"].request.ordering
        direction = "desc" if ordering == f"{column}:asc" else "asc"
        self.dashpot.submit_page("issues", ordering=f"{column}:{direction}")

    @on(Input.Submitted, ".item-search")
    def submit_search(self, event: Input.Submitted) -> None:
        """Submit a filter bar's search on Enter, whichever paged kind it filters."""
        event.stop()
        self.list_queries.submit_search(self.filter_kind(event.input), event.value)

    @on(Select.Changed, ".item-state")
    def change_lifecycle(self, event: Select.Changed) -> None:
        """Record a filter bar's chosen lifecycle, which submits its page."""
        self.list_queries.change_lifecycle(self.filter_kind(event.select), event.value)

    def action_cycle_issue_state(self) -> None:
        kind = self.page_kind()
        query = self.list_queries.query(kind)
        states = next_issue_states(query.states)
        # Drive the owning control so the label, query and Select agree.
        self.filter_bars[kind].state.value = lifecycle_value(states)

    def update_issue_inventory(self) -> None:
        """Title the Issue pane with the Project's totals, never the page's length."""
        self.query_one("#queue-pane").border_title = Content(
            f"{ISSUE_PANE_LABEL} · {totals_text(self.dashpot.store.totals.get('issues'))}"
        )

    def on_body_resized(self, message: BodyResized) -> None:
        # The last layout of a closing app can report after the screen has
        # been torn down; the panes it would fit are already gone.
        if not self.is_mounted or not self.surfaces_mounted():
            return
        self.fit_list_panes(message.size)
        self.issue_table.update_page_summary()

    def on_list_pane_rows_changed(self, _message: ListPane.RowsChanged) -> None:
        # A pane's share depends on what every pane wants, so any change of
        # records refits them all.
        if not self.is_mounted or not self.surfaces_mounted():
            return
        self.refresh_bindings()
        self.fit_list_panes(self.query_one("#query-body").size)

    def fit_list_panes(self, body: Size) -> None:
        """Cap each list pane to the height left after the fixed minimums.

        The Issue table keeps its stylesheet minimum; Textual cannot resolve
        an over-constrained column (every `fr` row at its minimum), so the
        cap shrinks first, to a frame with a count when nothing else fits.
        The arithmetic itself is `pane_layout.fit_panes`; this method only
        gathers the widget facts and applies the caps.
        """
        minimum = self.query_one("#queue-pane").styles.min_height
        panes = self.list_panes()
        caps = fit_panes(
            body.height,
            int(minimum.value) if minimum is not None else 0,
            tuple(
                pane_wish(pane.count, controls_height=pane.controls_height)
                for pane in panes
            ),
            controls_heights=tuple(pane.controls_height for pane in panes),
        )
        for pane, row_cap in zip(panes, caps, strict=True):
            pane.fit_rows(row_cap)

    def reconcile_list_panes(self) -> None:
        """Re-list every observed record from the store."""
        context = PaneContext(
            self.dashpot.store,
            self.dashpot.queries.navigation,
            dark=self.app.current_theme.dark,
            now=datetime.now(UTC),
        )
        for spec in QUERY_PANE_SPECS:
            view = spec.rows(context)
            self.list_pane(spec.pane_id).show_rows(
                view.rows,
                columns=view.columns,
                note=view.note,
                empty_message=view.empty_message,
                title_summary=view.title_summary,
                filter_count=view.filter_count,
                records=view.records,
            )

    @on(DataTable.RowSelected, "#queue")
    def open_selected_issue(self, event: DataTable.RowSelected) -> None:
        """Open the Issue a person selected in the Issue table."""
        self.open_issue(str(event.row_key.value))

    def action_open_issue(self) -> None:
        selected = self.issue_table.selected_row_key
        if self.queue_table().has_focus and selected is not None:
            self.open_issue(selected)

    def open_issue(self, key: str) -> None:
        """Read the Issue full-screen; nothing happens without an Issue row."""
        row = self.issue_table.rows_by_key.get(key)
        if row is None:
            return
        context = self.dashpot.store.detail_for(row)
        if context is not None and context.issue is not None:
            self.app.push_screen(IssueScreen(context))
        # The selected Issue's relationships are resolved one level deep even
        # when its details are not yet available to open.
        self.dashpot.selected_identity = row.issue.id
        self.dashpot.request_identities()

    @on(DataTable.RowHighlighted, "#queue")
    def select_highlighted_issue(self, event: DataTable.RowHighlighted) -> None:
        """Select the Issue under the cursor; other tables' cursors select nothing."""
        # Only the Issue table drives the Issue selection; a session or worktree
        # cursor is for scrolling, copying and refresh scope alone.
        if self.is_mounted:
            self.issue_table.show_row(str(event.row_key.value))

    def update_status(self) -> None:
        """Render current location and the shared Project Totals summary."""
        update_peer_status(self, self.dashpot)

    def update_diagnostics(self) -> None:
        """Render every Diagnostic in the Diagnostics box, then the alert above it."""
        update_peer_diagnostics(self, self.dashpot)

    def update_alert(self) -> None:
        """Render the exceptional-state readout, or hide it entirely."""
        update_peer_alert(self, self.dashpot)


class DashpotApp(App[None]):
    TITLE = "Dashpot"
    CSS_PATH = "../dashpot.tcss"
    MODES: ClassVar[dict[str, str]] = {
        "dashboard": "dashboard",
        "issues-pull-requests": "issues-pull-requests",
    }
    DEFAULT_MODE = "dashboard"
    # Textual declares this as an instance attribute, so ClassVar is not an
    # option; the list is never mutated.
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (100, "-wide")]  # ruff: ignore[mutable-class-default]
    # Keep rendered detail and diagnostic text selectable. Interactive widgets
    # such as DataTable opt out independently so mouse gestures remain theirs.
    ALLOW_SELECT = True

    BINDINGS: ClassVar[list[BindingType]] = [
        ("1", "show_dashboard", "Dashboard"),
        ("2", "show_issues_pull_requests", "Issues & Pull Requests"),
        ("q", "quit", "Quit"),
        ("question_mark", "legend", "Legend"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        scheduler: ObservationScheduler,
        *,
        sources: Mapping[str, QuerySource],
        refresh_seconds: float = 15,
        refresh_indicator_seconds: float = 0.75,
        fetcher: RemoteFetcher | None = None,
        cleaner: CleanupAdapter | None = None,
        launcher_configuration: LauncherConfiguration | None = None,
    ) -> None:
        super().__init__()
        self._dashboard = DashboardScreen()
        self._query_screen = IssuesPullRequestsScreen()
        self.install_screen(self._dashboard, "dashboard")
        self.install_screen(self._query_screen, "issues-pull-requests")
        self.launcher_configuration = launcher_configuration or LauncherConfiguration()
        # The observation and query commands an exit interrupts, so a pool
        # thread inside one releases before interpreter exit joins it; both
        # pools below adopt it.
        self.running_commands = RunningCommands()
        self.refresh_seconds = refresh_seconds
        self.refresh_timer: Timer | None = None
        self.store = PagedObservationStore()
        # The observations in flight, their reruns and their indicator, and
        # the page runner: the source queries behind the pages, totals and
        # identities, and each paged kind's navigation.
        self.observations = ObservationRunner(
            scheduler,
            self.store,
            self,
            indicator_seconds=refresh_indicator_seconds,
            running=self.running_commands,
        )
        self.queries = PageRunner(
            sources, self.store, self, running=self.running_commands
        )
        # The two named mutations, each holding its Projects while it runs:
        # the Remote Fetch behind ``f`` and the Cleanup behind ``x``.
        self.fetches = RemoteFetchFlow(fetcher, self.store, self.observations, self)
        self.cleanups = CleanupFlow(
            cleaner, self.store, self.observations, self.fetches, self
        )
        self.selected_identity: str | None = None
        # A local-only coordinator composes a placeholder for every Project
        # at construction; publishing it now names the Projects before their
        # first observation lands.
        scheduler.publish(self.store)

    @property
    def dashboard(self) -> DashboardScreen:
        """The installed Dashboard peer, whether active or inactive."""
        return self._dashboard

    @property
    def query_screen(self) -> IssuesPullRequestsScreen:
        """The installed Issues & Pull Requests peer."""
        return self._query_screen

    def peer_screens(self) -> tuple[DashboardScreen, IssuesPullRequestsScreen]:
        """Both long-lived peers in direct-navigation order."""
        return self.dashboard, self.query_screen

    def show_peer(self, peer: PeerName) -> None:
        """Replace the active peer directly without adding Back history."""
        if self.screen not in self.peer_screens():
            return
        if self.current_mode != peer:
            self.switch_mode(peer)

    def action_show_dashboard(self) -> None:
        """Switch directly to Dashboard when a peer is active."""
        self.show_peer("dashboard")

    def action_show_issues_pull_requests(self) -> None:
        """Switch directly to Issues & Pull Requests when a peer is active."""
        self.show_peer("issues-pull-requests")

    def on_peer_selected(self, message: PeerSelected) -> None:
        """Switch to the complete peer label a person clicked."""
        self.show_peer(message.peer)

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide direct peer keys while they type or a temporary screen is active."""
        if action in {"show_dashboard", "show_issues_pull_requests"}:
            peer = self.screen
            available = isinstance(peer, DashboardScreen | IssuesPullRequestsScreen)
            available = available and not isinstance(peer.focused, Input)
            return True if available else None
        return True

    @override
    def get_css_variables(self) -> dict[str, str]:
        """Add the Issue state colours for the current theme's brightness."""
        return {
            **super().get_css_variables(),
            **issue_state_colors(dark=self.current_theme.dark),
        }

    @override
    def action_focus_next(self) -> None:
        # Textual's tab binding names `app.focus_next`, so list-focus cycling
        # is forwarded to the dashboard whenever it is the visible screen.
        if isinstance(self.screen, DashboardScreen | IssuesPullRequestsScreen) and (
            self.screen.cycle_list_focus(1)
        ):
            return
        super().action_focus_next()

    @override
    def action_focus_previous(self) -> None:
        if isinstance(self.screen, DashboardScreen | IssuesPullRequestsScreen) and (
            self.screen.cycle_list_focus(-1)
        ):
            return
        super().action_focus_previous()

    def on_text_selected(self, event: events.TextSelected) -> None:
        """Copy arbitrary rendered-text selections when the drag finishes."""

        selected_text = self.screen.get_selected_text()
        if selected_text:
            self.copy_to_clipboard(selected_text)

    def action_legend(self) -> None:
        """Explain every Glyph on screen; a second ``?`` is absorbed by the Legend."""
        if isinstance(self.screen, LegendScreen):
            return
        self.push_screen(LegendScreen(legend_keys()))

    async def on_ready(self) -> None:
        # Mount both installed peers before collection starts, then restore the
        # default peer. Their long-lived widgets can accept every result even
        # before a person first switches screens.
        await self.switch_mode("issues-pull-requests")
        await self.switch_mode("dashboard")
        dashboard = self.dashboard
        dashboard.query_one(WorktreeTable).launch_available = (
            self.launcher_configuration.opener is not None
        )
        # The first pages render whatever the store already holds, so a
        # seeded store needs no rendering of its own before they are asked for.
        self.request_refresh("initial")
        if self.refresh_seconds > 0:
            self.refresh_timer = self.set_interval(
                self.refresh_seconds,
                self.timer_refresh,
                name="workspace refresh",
            )

    def on_unmount(self) -> None:
        self.observations.shutdown()
        self.queries.shutdown()
        # Shutting a pool down leaves a running command to finish; the
        # command itself is what holds the thread, so it is told to stop.
        self.running_commands.interrupt()

    async def off_loop[T](
        self, operation: Callable[[], T], *, executor: ThreadPoolExecutor | None = None
    ) -> T:
        """Run one blocking operation on an executor thread and return its value."""
        # Fetches, Cleanups and Worktree launches share the observation pool;
        # each is one blocking call per Project, never enough to need its own.
        return await asyncio.get_running_loop().run_in_executor(
            executor or self.observations.executor, operation
        )

    @property
    def closing(self) -> bool:
        """Whether shutdown has begun, when a late result has nowhere to go."""
        return self._closing or self._closed or not self.screen_stack

    def update_alert(self) -> None:
        """Redraw the alert readout, the one path every change of its state takes."""
        # A stopped timer can already have queued a redraw; shutdown marks
        # the app not running before it removes screens or closes messages.
        if not self.is_running or self.closing:
            return
        for peer in self.peer_screens():
            if peer.is_mounted and peer.surfaces_mounted():
                peer.update_alert()

    def update_diagnostics(self) -> None:
        """Redraw the diagnostics readout after a flow recorded a failure."""
        for peer in self.peer_screens():
            if peer.is_mounted and peer.surfaces_mounted():
                peer.update_diagnostics()

    def run_off_loop[T](
        self,
        name: str,
        group: str,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        """Start a worker that runs ``operation`` off the loop and posts its outcome.

        ``on_done`` makes the message from the value, or from the failure's
        text: the one error boundary for off-loop work, where a failure is a
        message and never an exit. A worker cancelled at shutdown posts
        nothing, and every worker is a partial rather than a coroutine
        object, so one cancelled before it starts leaves no coroutine never
        awaited.
        """
        self.run_worker(
            partial(self._post_off_loop, operation, on_done, executor),
            name=name,
            group=group,
            exit_on_error=False,
        )

    async def _post_off_loop[T](
        self,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
        executor: ThreadPoolExecutor | None,
    ) -> None:
        worker = get_current_worker()
        try:
            value = await self.off_loop(operation, executor=executor)
        except Exception as exc:  # UI boundary: an off-loop failure must not exit.
            message = on_done(None, str(exc))
        else:
            message = on_done(value, None)
        if not worker.is_cancelled:
            self.post_message(message)

    def worktree_path(self, key: str) -> Path | None:
        """The observed path of a listed Worktree row, from the pane's own records."""
        record = self.dashboard.worktrees_pane().record(key)
        if not isinstance(record, WorktreeListRow):
            return None
        return Path(record.target.path)

    def request_worktree_open(self, key: str) -> None:
        """Capture one Worktree launch and exclude duplicate dispatch."""
        table = self.dashboard.query_one(WorktreeTable)
        opener = self.launcher_configuration.opener
        path = self.worktree_path(key)
        if table.opening or opener is None or path is None:
            return
        table.opening = True
        self.notify(f"Opening Worktree: {path}")
        self.run_worker(
            self.open_worktree(path),
            name="open Worktree",
            group="worktree-launch",
            exit_on_error=False,
        )

    async def open_worktree(self, path: Path) -> None:
        """Run the captured launch without blocking dashboard interaction."""
        opener = self.launcher_configuration.opener
        assert opener is not None
        try:
            await self.off_loop(partial(opener, path))
        except (OSError, ValueError, WorktreeLaunchError) as exc:
            self.notify(str(exc), title="Open Worktree", severity="error")
        else:
            self.notify("Worktree launch request completed")
        finally:
            if self.dashboard.is_mounted:
                self.dashboard.query_one(WorktreeTable).opening = False

    def action_refresh(self) -> None:
        """Refresh every observation in the Workspace."""
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual")

    def timer_refresh(self) -> None:
        """One automatic tick: coalesce onto whatever is still in flight."""
        self.request_refresh("timer")

    def request_refresh(self, trigger: ObservationTrigger) -> None:
        """Observe every key and re-query the pages, totals and identities.

        A manual refresh restarts each navigation at page one; any other
        trigger repeats the displayed page unless its query is still running.
        """
        self.observations.refresh(trigger)
        self.queries.refresh(restart=trigger == "manual")
        self.request_identities()
        self.render_pages()

    def submit_page(self, kind: ResourceKind, **updates: str) -> None:
        """Submit a new query context, which redraws the pages as loading."""
        self.queries.submit(kind, **updates)
        self.render_pages()

    def request_identities(self) -> None:
        """Resolve the bound Issues, the selected one and its direct relationships."""
        ids = [
            run.issue_id for run in self.store.checkpoint().agent_runs if run.issue_id
        ]
        if self.selected_identity:
            ids.append(self.selected_identity)
            row = self.store.row_for(self.selected_identity)
            if row:
                relationships = row.issue.relationships
                ids.extend(
                    (
                        *relationships.sub_issues,
                        *relationships.blocked_by,
                        *relationships.blocking,
                    )
                )
                if relationships.parent:
                    ids.append(relationships.parent)
        requested = tuple(dict.fromkeys(ids))
        if requested:
            self.queries.request_identities(requested)

    def on_page_finished(self, message: PageFinished) -> None:
        self.queries.finish_page(message)
        self.render_pages()

    def on_totals_finished(self, message: TotalsFinished) -> None:
        self.queries.finish_totals(message)
        self.render_pages()

    def on_identities_finished(self, message: IdentitiesFinished) -> None:
        self.queries.finish_identities(message)
        self.render_pages()

    def render_pages(self) -> None:
        """Publish pages and redraw every mounted peer that reads them."""
        self.queries.publish()
        if not self.is_running:
            return
        dashboard = self.dashboard
        if dashboard.is_mounted and dashboard.surfaces_mounted():
            dashboard.reconcile_list_panes()
        query_screen = self.query_screen
        if query_screen.is_mounted and query_screen.surfaces_mounted():
            query_screen.queue_table().loading = False
            query_screen.issue_table.reconcile_rows()
            query_screen.update_issue_inventory()
            query_screen.reconcile_list_panes()
        self.update_diagnostics()
        for peer in self.peer_screens():
            if peer.is_mounted and peer.surfaces_mounted():
                peer.update_status()
        if isinstance(self.screen, IssueScreen):
            context = self.store.detail_for(self.screen.context)
            if context:
                self.screen.show(context)

    def request_fetch(self) -> None:
        """Fetch every observed Project's remotes, except where a Cleanup holds one."""
        self.fetches.request(held=self.cleanups.cleaning)

    def on_fetch_finished(self, message: FetchFinished) -> None:
        self.fetches.record(message)

    def request_cleanup(self, selection: CleanupSelection | None) -> None:
        """Preview a Cleanup of the highlighted row; nothing is deleted here."""
        self.cleanups.request(selection)

    def on_cleanup_inspected(self, message: CleanupInspected) -> None:
        self.cleanups.finish_inspection(message)

    def on_cleanup_screen_fetch_requested(
        self, message: CleanupScreen.FetchRequested
    ) -> None:
        self.cleanups.fetch_requested(message.screen)

    def on_cleanup_finished(self, message: CleanupFinished) -> None:
        self.cleanups.finish_cleanup(message)

    def on_observation_finished(self, message: ObservationFinished) -> None:
        # A late completion can be dispatched during shutdown while widgets
        # are being unmounted one by one; any missing widget means the result
        # has nowhere to go and is dropped.
        if self.closing:
            return
        self.observations.finish(message, partial(self._accept_observation, message))

    def _accept_observation(
        self, message: ObservationFinished, landed: Acceptance
    ) -> None:
        self.show_observation(landed)
        # Identities are resolved against the Agent Runs just published.
        if message.ticket.key.kind == "agent-runs":
            self.request_identities()

    def show_observation(self, landed: Acceptance) -> None:
        """Render what a landed observation changed; a dropped one changes nothing."""
        if isinstance(landed, DroppedObservation):
            return
        if isinstance(landed, FailedObservation):
            self.update_diagnostics()
            if landed.announced:
                self.notify(landed.error, severity="error", title="Dashpot refresh")
            return
        if landed.announced:
            self.notify(
                "Refresh succeeded", severity="information", title="Dashpot refresh"
            )
        if landed.changes:
            if self.dashboard.is_mounted and self.dashboard.surfaces_mounted():
                self.dashboard.reconcile_list_panes()
            query_screen = self.query_screen
            if query_screen.is_mounted and query_screen.surfaces_mounted():
                query_screen.queue_table().loading = False
                query_screen.issue_table.reconcile_rows()
                query_screen.update_issue_inventory()
                query_screen.reconcile_list_panes()
        for peer in self.peer_screens():
            if peer.is_mounted and peer.surfaces_mounted():
                peer.update_status()
        self.update_diagnostics()


def legend_keys() -> tuple[KeyGroup, ...]:
    """Every shipped key, grouped by where it is pressed, for the Legend.

    The global group is the app's keys and the focus cycle. Each peer,
    the Worktrees table and each temporary screen are listed
    under their own names, wherever the Legend was opened from, so Enter on
    a Worktree is never confused with Enter on an Issue.
    """
    return (
        KeyGroup(
            "global",
            (*DashpotApp.BINDINGS, *FOCUS_CYCLE_BINDINGS),
        ),
        KeyGroup(
            "Dashboard",
            tuple(DashboardScreen.BINDINGS),
        ),
        KeyGroup(
            "Issues & Pull Requests",
            tuple(IssuesPullRequestsScreen.BINDINGS),
        ),
        KeyGroup("Worktrees pane", tuple(WorktreeTable.BINDINGS)),
        KeyGroup("Issue view", tuple(IssueScreen.BINDINGS)),
        KeyGroup("column editor", tuple(IssueColumnEditor.BINDINGS)),
        KeyGroup("Cleanup preview", tuple(CleanupScreen.BINDINGS)),
        KeyGroup("Cleanup report", tuple(CleanupReportScreen.BINDINGS)),
        KeyGroup("Legend", tuple(LegendScreen.BINDINGS)),
    )
