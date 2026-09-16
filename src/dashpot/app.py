from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, ClassVar, TypeVar, cast

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
from textual.widgets import DataTable, Footer, Input, Select, Static
from textual.worker import get_current_worker
from typing_extensions import override

from .alerts import (
    SEVERITY_GLYPH,
    SEVERITY_RANK,
    AlertSeverity,
    summarize_alerts,
)
from .cleanup import (
    CleanupAdapter,
)
from .cleanup_flow import CleanupFlow, CleanupSelection
from .cleanup_view import CleanupScreen
from .collect import ObservationScheduler
from .column_editor import IssueColumnEditor
from .fetch import RemoteFetcher
from .fetch_flow import RemoteFetchFlow
from .focus_table import FocusCursorTable
from .issue_cells import TableCell, issue_state_colors
from .issue_list import (
    issue_result_count_text,
    next_issue_states,
)
from .issue_table import COLUMNS_BY_KEY, ColumnKey, shown_columns
from .issue_table_controller import IssueTableController
from .issue_view import IssueScreen
from .item_filter import (
    LIFECYCLE_STATUSES,
    ItemFilterBar,
    lifecycle_states,
    lifecycle_value,
)
from .legend import LegendScreen
from .list_pane import ISSUE_PANE_LABEL, ListPane
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
from .observation_runner import (
    Acceptance,
    DroppedObservation,
    FailedObservation,
    ObservationRunner,
)
from .page_runner import PageRunner
from .paged_store import PagedObservationStore
from .pane_layout import fit_panes, pane_wish
from .panes import LIST_PANE_SPECS, PaneContext
from .pull_request_list import DEFAULT_PULL_REQUEST_QUERY, PullRequestListQuery
from .queries.page_navigation import totals_text
from .queries.source_queries import QuerySource, ResolvedIssue, ResourceKind
from .spread_table import SpreadTable
from .worktree_launcher import LauncherConfiguration
from .worktree_table import WorktreeTable

T = TypeVar("T")


class DashboardBody(Container):
    """The pane stack; its height is the budget the list panes fit into."""

    def on_resize(self, event: events.Resize) -> None:
        self.post_message(BodyResized(event.size))


class DashboardScreen(Screen[None]):
    """Own the dashboard: composition, the panes, their keys, and the Issue table's controller."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "open_issue", "Open Issue"),
        ("f", "fetch", "Fetch & prune remotes"),
        ("x", "cleanup", "Delete Branch/Worktree"),
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
        self.pull_request_query = DEFAULT_PULL_REQUEST_QUERY
        query = self.issue_table.issue_view.query
        self.issue_filter_bar = ItemFilterBar(
            "issue",
            statuses=LIFECYCLE_STATUSES,
            status=lifecycle_value(query.states),
            query=query.text,
            placeholder="Search Issues",
            count=issue_result_count_text(0),
        )
        # Each pane's controls, composed once from its spec.
        self.pane_controls: dict[str, ItemFilterBar] = {
            spec.pane_id: spec.controls()
            for spec in LIST_PANE_SPECS
            if spec.controls is not None
        }

    @property
    def dashpot(self) -> DashpotApp:
        """Narrow `self.app` once: the store and the runners live there.

        Use `dashpot` for Dashpot-owned state (the store, the observation
        and page runners, the flows) and plain `app` for the Textual API.
        """
        return cast("DashpotApp", self.app)

    def page_kind(self) -> ResourceKind:
        """Choose the page belonging to the focused query pane."""
        return (
            "pull-requests" if self.pull_requests_pane().has_focus_within else "issues"
        )

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
        with DashboardBody(id="body"):
            with Container(id="list-row"):
                for spec in LIST_PANE_SPECS:
                    yield ListPane(
                        spec.label,
                        columns=spec.columns,
                        empty_message=spec.empty_message,
                        id=spec.pane_id,
                        table_id=spec.table_id,
                        table_type=spec.table_type,
                        controls=self.pane_controls.get(spec.pane_id),
                        controls_height=spec.controls_height,
                    )
            with Vertical(id="queue-pane"):
                yield self.issue_filter_bar
                yield SpreadTable(id="queue", cursor_type="row", zebra_stripes=False)
        yield Static("", id="alert")
        yield Static("", id="diagnostics")
        yield Footer()

    def queue_table(self) -> SpreadTable[TableCell]:
        """The Issue table; `query_one` cannot name the cell type itself."""
        return cast("SpreadTable[TableCell]", self.query_one("#queue", SpreadTable))

    def list_pane(self, pane_id: str) -> ListPane:
        """One list pane by its spec's id."""
        return self.query_one(f"#{pane_id}", ListPane)

    def sessions_pane(self) -> ListPane:
        return self.list_pane("sessions-pane")

    def branches_pane(self) -> ListPane:
        return self.list_pane("branches-pane")

    def worktrees_pane(self) -> ListPane:
        return self.list_pane("worktrees-pane")

    def pull_requests_pane(self) -> ListPane:
        return self.list_pane("pull-requests-pane")

    @property
    def pull_request_filter_bar(self) -> ItemFilterBar:
        """The Pull Requests pane's controls, which its spec always composes."""
        return self.pane_controls["pull-requests-pane"]

    def list_panes(self) -> tuple[ListPane, ...]:
        """The content-sized panes in reading order."""
        return tuple(self.list_pane(spec.pane_id) for spec in LIST_PANE_SPECS)

    def focus_tables(self) -> tuple[FocusCursorTable[Any], ...]:
        """Return the dashboard tables in their composed reading order."""
        return tuple(self.query_one("#body").query(FocusCursorTable))

    def _update_widgets_mounted(self) -> bool:
        """Report whether dashboard updates can still reach every surface."""
        try:
            self.queue_table()
            for pane in self.list_panes():
                if not pane.table.is_mounted:
                    return False
            self.query_one("#alert", Static)
            self.query_one("#diagnostics", Static)
        except NoMatches:
            return False
        return True

    def action_focus_search(self) -> None:
        """Focus the search of the focused pane's controls, else the Issue search."""
        for pane in self.list_panes():
            if pane.table.has_focus and pane.controls is not None:
                pane.controls.search.focus()
                return
        self.issue_filter_bar.search.focus()

    def action_fetch(self) -> None:
        """Fetch the remotes behind the Branches pane, on this explicit key."""
        self.dashpot.request_fetch()

    def action_cleanup(self) -> None:
        """Preview deleting the highlighted Branch or Worktree; never delete here."""
        self.dashpot.request_cleanup(self.cleanup_selection())

    def cleanup_selection(self) -> CleanupSelection | None:
        """The highlighted row of the Branches or Worktrees pane, when one has focus."""
        for kind, pane in (
            ("branch", self.branches_pane()),
            ("worktree", self.worktrees_pane()),
        ):
            if self.focused is pane.table:
                key, _index = pane.highlighted()
                return None if key is None else CleanupSelection(kind, key)
        return None

    def cycle_list_focus(self, step: int) -> bool:
        """Move focus to the next list when a list has it; otherwise decline."""
        tables = self.focus_tables()
        focused = self.focused
        if focused not in tables:
            return False
        tables[(tables.index(focused) + step) % len(tables)].focus()
        return True

    def on_focus_cursor_table_row_boundary_reached(
        self, event: FocusCursorTable.RowBoundaryReached
    ) -> None:
        """Move focus when the focused table cannot move its row cursor."""
        if self.focused is event.control:
            self.cycle_list_focus(event.step)

    def on_mount(self) -> None:
        self.query_one("#queue-pane").border_title = Content(ISSUE_PANE_LABEL)
        self.issue_table.show_table_columns(
            shown_columns(self.issue_table.issue_view.columns, ())
        )
        self.sessions_pane().table.focus()
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render semantic table colors for the new theme brightness."""

        if self.dashpot.store.has_observations:
            self.issue_table.reconcile_rows()
            # The list panes render their glyphs in explicit colours chosen
            # for the theme's brightness, so they repaint with the table.
            self.reconcile_list_panes()

    def action_columns(self) -> None:
        self.app.push_screen(
            IssueColumnEditor(self.issue_table.issue_view.columns),
            self.issue_table.apply_issue_columns,
        )

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

    @on(Input.Submitted, "#issue-search")
    def submit_issue_search(self, event: Input.Submitted) -> None:
        """Submit a search on Enter; editing the text alone changes nothing."""
        event.stop()
        self.issue_table.set_issue_query(
            replace(self.issue_table.issue_view.query, text=event.value)
        )
        self.dashpot.submit_page("issues", query=event.value)

    @on(Input.Submitted, "#pull-request-search")
    def submit_pull_request_search(self, event: Input.Submitted) -> None:
        """Submit a Pull Request search on Enter, as the Issue search does."""
        event.stop()
        self.set_pull_request_query(replace(self.pull_request_query, text=event.value))
        self.dashpot.submit_page("pull-requests", query=event.value)

    def action_cycle_issue_state(self) -> None:
        states = next_issue_states(self.issue_table.issue_view.query.states)
        # Drive the control so the header, the query, and the Select agree.
        self.issue_filter_bar.state.value = lifecycle_value(states)

    @on(Select.Changed, "#issue-state")
    def change_issue_lifecycle(self, event: Select.Changed) -> None:
        """Record the chosen Issue lifecycle, which submits a page."""
        states = lifecycle_states(event.value)
        if states is not None:
            self.issue_table.set_issue_query(
                replace(self.issue_table.issue_view.query, states=states)
            )

    @on(Select.Changed, "#pull-request-state")
    def change_pull_request_lifecycle(self, event: Select.Changed) -> None:
        """Record the chosen Pull Request lifecycle, which submits a page."""
        states = lifecycle_states(event.value)
        if states is not None:
            self.set_pull_request_query(replace(self.pull_request_query, states=states))

    def set_pull_request_query(self, query: PullRequestListQuery) -> None:
        """Record the submitted Pull Request query; a lifecycle change submits a page."""
        previous = self.pull_request_query
        self.pull_request_query = query
        if query.states != previous.states:
            self.dashpot.submit_page(
                "pull-requests", state=lifecycle_value(query.states)
            )

    def update_issue_inventory(self) -> None:
        """Title the Issue pane with the Project's totals, never the page's length."""
        self.query_one("#queue-pane").border_title = Content(
            f"{ISSUE_PANE_LABEL} · {totals_text(self.dashpot.store.totals.get('issues'))}"
        )

    def on_body_resized(self, message: BodyResized) -> None:
        # The last layout of a closing app can report after the screen has
        # been torn down; the panes it would fit are already gone.
        if not self.is_mounted or not self._update_widgets_mounted():
            return
        self.fit_list_panes(message.size)
        self.issue_table.update_page_summary()

    def on_list_pane_rows_changed(self, _message: ListPane.RowsChanged) -> None:
        # A pane's share depends on what every pane wants, so any change of
        # records refits them all.
        if not self.is_mounted or not self._update_widgets_mounted():
            return
        self.refresh_bindings()
        self.fit_list_panes(self.query_one("#body").size)

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
        for spec in LIST_PANE_SPECS:
            view = spec.rows(context)
            self.issue_table.pane_records[spec.pane_id] = view.records
            self.list_pane(spec.pane_id).show_rows(
                view.rows,
                columns=view.columns,
                note=view.note,
                empty_message=view.empty_message,
                title_count=view.title_count,
                title_summary=view.title_summary,
                filter_count=view.filter_count,
            )
        self.issue_table.update_related_rows()

    @on(DataTable.RowSelected, "#queue")
    def open_selected_issue(self, event: DataTable.RowSelected) -> None:
        """Open the Issue a person selected in the Issue table."""
        self.open_issue(str(event.row_key.value))

    @on(DataTable.RowSelected, "#sessions")
    def open_session_issue(self, event: DataTable.RowSelected) -> None:
        """Open the Issue bound to the selected Agent Session, when it has one."""
        row = self.sessions_pane().row(str(event.row_key.value))
        if row is not None:
            self.open_bound_issue(row.issue_id)

    def open_bound_issue(self, issue_id: str | None) -> None:
        """Read a bound Issue full-screen, resolving it first when the page lacks it."""
        if issue_id is None:
            return
        app = self.dashpot
        app.selected_identity = issue_id
        row = app.store.row_for(issue_id)
        if row:
            self.app.push_screen(IssueScreen(row))
        else:
            self.notify("Resolving bound Issue details")
            app.open_when_resolved = issue_id
        app.request_identities()

    def action_open_issue(self) -> None:
        selected = self.issue_table.selected_row_key
        if self.queue_table().has_focus and selected is not None:
            self.open_issue(selected)

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

    @on(DataTable.RowHighlighted)
    def follow_cursor(self, event: DataTable.RowHighlighted) -> None:
        """Re-emphasise relationships when the focused table's cursor moves."""
        # A queued highlight can be dispatched during app shutdown, after the
        # screen and its panes have been unmounted.
        if not self.is_mounted:
            return
        if event.data_table.has_focus:
            self.issue_table.update_related_rows()

    @on(DataTable.RowHighlighted, "#queue")
    def select_highlighted_issue(self, event: DataTable.RowHighlighted) -> None:
        """Select the Issue under the cursor; other tables' cursors select nothing."""
        # Only the Issue table drives the Issue selection; a session or worktree
        # cursor is for scrolling, copying and refresh scope alone.
        if self.is_mounted:
            self.issue_table.show_row(str(event.row_key.value))

    def on_focus_cursor_table_focus_changed(
        self, event: FocusCursorTable.FocusChanged
    ) -> None:
        self.issue_table.update_related_rows()

    def on_screen_suspend(self, _: events.ScreenSuspend) -> None:
        self.issue_table.update_related_rows(clear=True)

    def on_screen_resume(self, _: events.ScreenResume) -> None:
        self.call_after_refresh(self.issue_table.update_related_rows)

    def update_diagnostics(self) -> None:
        # A refresh failure and a search error are the app's own errors; a
        # Project's diagnostics carry the severity they were observed with.
        entries: list[tuple[AlertSeverity, str]] = [
            ("error", message) for message in self.dashpot.observations.errors.values()
        ]
        entries.extend(
            (diagnostic.severity, diagnostic.message)
            for diagnostic in self.dashpot.launcher_configuration.diagnostics
        )
        entries.extend(
            ("error", message) for message in self.dashpot.fetches.errors.values()
        )
        entries.extend(
            (
                entry.diagnostic.severity,
                f"{entry.project_label} · {entry.diagnostic.source}: "
                f"{entry.diagnostic.message}"
                if entry.project_label is not None
                else f"{entry.diagnostic.source}: {entry.diagnostic.message}",
            )
            for entry in self.dashpot.store.diagnostics()
        )
        # The Diagnostics box takes no space at all while there is nothing to
        # report; `-has-messages` displays it, and the box is coloured by the
        # most severe line in it rather than by having any line at all.
        diagnostics = self.query_one("#diagnostics", Static)
        diagnostics.set_class(bool(entries), "-has-messages")
        severity = min(
            (item for item, _message in entries),
            key=lambda item: SEVERITY_RANK[item],
            default="info",
        )
        for candidate in ("error", "warning", "info"):
            diagnostics.set_class(
                bool(entries) and severity == candidate, f"-{candidate}"
            )
        diagnostics.update(
            "\n".join(
                f"{SEVERITY_GLYPH[item].symbol} {message}" for item, message in entries
            )
        )
        self.update_alert()

    def update_alert(self) -> None:
        """Render the exceptional-state readout, or hide it entirely."""
        app = self.dashpot
        alert = summarize_alerts(
            app.store,
            failures=app.observations.errors,
            refreshing=app.observations.refreshing,
            fetching=tuple(app.fetches.fetching),
            source_pages=app.store.pages,
        )
        widget = self.query_one("#alert", Static)
        widget.set_class(alert is not None, "-visible")
        for severity in ("error", "warning", "info"):
            widget.set_class(
                alert is not None and alert.severity == severity, f"-{severity}"
            )
        widget.update(alert.text if alert is not None else "")


class DashpotApp(App[None]):
    TITLE = "Dashpot"
    CSS_PATH = "dashpot.tcss"
    # Textual declares this as an instance attribute, so ClassVar is not an
    # option; the list is never mutated.
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (100, "-wide")]  # ruff: ignore[mutable-class-default]
    # Keep rendered detail and diagnostic text selectable. Interactive widgets
    # such as DataTable opt out independently so mouse gestures remain theirs.
    ALLOW_SELECT = True

    BINDINGS: ClassVar[list[BindingType]] = [
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
        self.launcher_configuration = launcher_configuration or LauncherConfiguration()
        self.refresh_seconds = refresh_seconds
        self.refresh_timer: Timer | None = None
        self.store = PagedObservationStore()
        # The observations in flight, their reruns and their indicator, and
        # the page runner: the source queries behind the pages, totals and
        # identities, and each paged kind's navigation.
        self.observations = ObservationRunner(
            scheduler, self.store, self, indicator_seconds=refresh_indicator_seconds
        )
        self.queries = PageRunner(sources, self.store, self)
        # The two named mutations, each holding its Projects while it runs:
        # the Remote Fetch behind ``f`` and the Cleanup behind ``x``.
        self.fetches = RemoteFetchFlow(fetcher, self.store, self.observations, self)
        self.cleanups = CleanupFlow(
            cleaner, self.store, self.observations, self.fetches, self
        )
        self.selected_identity: str | None = None
        self.open_when_resolved: str | None = None
        # A local-only coordinator composes a placeholder for every Project
        # at construction; publishing it now names the Projects before their
        # first observation lands.
        scheduler.publish(self.store)

    @override
    def get_default_screen(self) -> DashboardScreen:
        """Root the app on the dashboard, its one long-lived screen."""
        return DashboardScreen()

    @property
    def dashboard(self) -> DashboardScreen:
        """The dashboard screen, whatever is stacked above it."""
        return cast("DashboardScreen", self.screen_stack[0])

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
        if self.screen is self.dashboard and self.dashboard.cycle_list_focus(1):
            return
        super().action_focus_next()

    @override
    def action_focus_previous(self) -> None:
        if self.screen is self.dashboard and self.dashboard.cycle_list_focus(-1):
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
        # The Legend lists the app's keys, the dashboard's, and the Worktrees
        # table's own, wherever it was opened from.
        self.push_screen(
            LegendScreen(
                bindings=[
                    *self.BINDINGS,
                    *DashboardScreen.BINDINGS,
                    *WorktreeTable.BINDINGS,
                ]
            )
        )

    def on_ready(self) -> None:
        dashboard = self.dashboard
        dashboard.query_one(WorktreeTable).launch_available = (
            self.launcher_configuration.opener is not None
        )
        for kind, bar in (
            ("issues", dashboard.issue_filter_bar),
            ("pull-requests", dashboard.pull_request_filter_bar),
        ):
            bar.search.placeholder = self.queries.sources[kind].search_prompt
        if not self.store.has_observations:
            dashboard.queue_table().loading = True
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

    async def off_loop(
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
        self.dashboard.update_alert()

    def update_diagnostics(self) -> None:
        """Redraw the diagnostics readout after a flow recorded a failure."""
        self.dashboard.update_diagnostics()

    def run_off_loop(
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

    async def _post_off_loop(
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
        """Resolve a visible Worktree row against its accepted observation."""
        if self.dashboard.worktrees_pane().row(key) is None:
            return None
        row = next(
            (row for row in self.store.query_worktrees().rows if row.key == key), None
        )
        return Path(row.target.path) if row is not None else None

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
        except (OSError, RuntimeError, ValueError) as exc:
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
        if message.outcomes is not None:
            self.open_resolved_issue(message.outcomes)
        self.render_pages()

    def open_resolved_issue(self, outcomes: tuple[ResolvedIssue, ...]) -> None:
        """Open the bound Issue a person is waiting on once its identity resolves."""
        if not self.open_when_resolved or all(
            outcome.issue_id != self.open_when_resolved for outcome in outcomes
        ):
            return
        row = self.store.row_for(self.open_when_resolved)
        if row:
            self.push_screen(IssueScreen(row))
        else:
            self.notify("Bound Issue details are unavailable", severity="warning")
        self.open_when_resolved = None

    def render_pages(self) -> None:
        """Publish each navigation's page to the store and redraw the dashboard."""
        self.queries.publish()
        if not self.is_running or not self.dashboard.is_mounted:
            return
        self.dashboard.queue_table().loading = False
        self.dashboard.issue_table.reconcile_rows()
        self.dashboard.update_issue_inventory()
        self.dashboard.reconcile_list_panes()
        self.dashboard.update_diagnostics()
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
        if not self.dashboard._update_widgets_mounted():
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
        dashboard = self.dashboard
        # An accepted observation ends the cold load even when an earlier
        # publish already carried its change; the spinner must not outlive it.
        dashboard.queue_table().loading = False
        if isinstance(landed, FailedObservation):
            dashboard.update_diagnostics()
            if landed.announced:
                self.notify(landed.error, severity="error", title="Dashpot refresh")
            return
        if landed.announced:
            self.notify(
                "Refresh succeeded", severity="information", title="Dashpot refresh"
            )
        if landed.changes:
            dashboard.issue_table.reconcile_rows()
            dashboard.update_issue_inventory()
            dashboard.reconcile_list_panes()
        dashboard.update_diagnostics()
