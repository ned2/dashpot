from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, ClassVar, Literal, TypeVar, cast

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
    BranchCleanupRequest,
    CleanupAdapter,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    TargetResult,
    WorktreeCleanupRequest,
)
from .cleanup_view import CleanupReportScreen, CleanupScreen
from .collect import ObservationKey, ObservationScheduler
from .column_editor import IssueColumnEditor
from .fetch import RemoteFetcher
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
from .page_navigation import totals_text
from .page_runner import PageRunner
from .paged_store import PagedObservationStore
from .pane_layout import fit_panes, pane_wish
from .panes import LIST_PANE_SPECS, PaneContext
from .pull_request_list import DEFAULT_PULL_REQUEST_QUERY, PullRequestListQuery
from .source_queries import QuerySource, ResolvedIssue, ResourceKind
from .spread_table import SpreadTable
from .worktree_launcher import LauncherConfiguration
from .worktree_table import WorktreeTable

T = TypeVar("T")


class DashboardBody(Container):
    """The pane stack; its height is the budget the list panes fit into."""

    def on_resize(self, event: events.Resize) -> None:
        self.post_message(BodyResized(event.size))


@dataclass(frozen=True, slots=True)
class CleanupSelection:
    """The pane row a person pressed ``x`` on: which list, and its row key."""

    kind: Literal["branch", "worktree"]
    key: str


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
            ("error", message) for message in self.dashpot.fetch_errors.values()
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
            fetching=tuple(app.fetching),
            source_pages=app.store.pages,
        )
        widget = self.query_one("#alert", Static)
        widget.set_class(alert is not None, "-visible")
        for severity in ("error", "warning", "info"):
            widget.set_class(
                alert is not None and alert.severity == severity, f"-{severity}"
            )
        widget.update(alert.text if alert is not None else "")


def cleanup_subject(request: CleanupRequest) -> str:
    """What a Cleanup in progress is about, for the refusals that name it."""
    if isinstance(request, BranchCleanupRequest):
        return request.name
    return str(request.path)


def cleanup_result_line(result: TargetResult) -> str:
    """Render one concise Cleanup outcome for a toast."""
    if result.outcome == "deleted":
        verb = "Removed" if result.kind == "worktree" else "Deleted"
        return f"{verb} {result.label}"
    if result.outcome == "already-absent":
        return f"{result.label} already absent"
    return f"{result.outcome.capitalize()} {result.label}"


def cleanup_summary(report: CleanupReport) -> str:
    """List each target's outcome for a toast, or why nothing ran."""
    if report.refusals:
        return "\n".join(report.refusals)
    return "\n".join(cleanup_result_line(result) for result in report.results)


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
        # The explicit Cleanup seam (``x``): without one the key is refused,
        # so no observation-only construction can ever delete.
        self.cleaner = cleaner
        # Projects with a Cleanup in progress, from the preview being taken
        # until the modal is dismissed or the report is in; a fetch there
        # is refused meanwhile, and a Cleanup while a fetch is in flight.
        self.cleaning: dict[str, str] = {}
        self.cleanup_previews: dict[str, tuple[CleanupScreen, Path | None]] = {}
        self._cleanup_refresh_waiters: list[
            tuple[dict[ObservationKey, int], asyncio.Future[None]]
        ] = []
        self.cleanup_refresh_timeout = 30.0

        # The explicit fetch seam (``f``); without one the key is refused,
        # so no observation-only construction can ever fetch.
        self.fetcher = fetcher
        # Projects whose remotes are being fetched, by identity, and the last
        # fetch failure per Project until a fetch there succeeds.
        self.fetching: dict[str, str] = {}
        self.fetch_errors: dict[str, str] = {}
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
        # Fetches, Cleanups and Worktree launches share the observation pool
        # until they have flows of their own.
        return await asyncio.get_running_loop().run_in_executor(
            executor or self.observations.executor, operation
        )

    def update_alert(self) -> None:
        """Redraw the alert readout, the one path every change of its state takes."""
        # A stopped timer can already have queued a redraw; shutdown marks
        # the app not running before it removes screens or closes messages.
        if (
            not self.is_running
            or self._closing
            or self._closed
            or not self.screen_stack
        ):
            return
        self.dashboard.update_alert()

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
        """Fetch the remotes of every observed Project's authoritative anchor.

        Only the Repository Anchor whose refs supplied the Branch observation
        is fetched, so independent clones sharing a Project are left alone.
        A Project already being fetched is refused rather than fetched twice.
        """
        fetcher = self.fetcher
        if fetcher is None:
            self.notify(
                "Fetching is not available in this view",
                severity="warning",
                title="Dashpot fetch",
            )
            return
        anchors = {
            project.project_id: project.snapshot.branch_anchor
            for project in self.store.projects()
            if project.snapshot is not None
            and project.snapshot.branch_anchor is not None
        }
        if not anchors:
            self.notify(
                "No Branch observation names a Repository Anchor to fetch yet",
                severity="warning",
                title="Dashpot fetch",
            )
            return
        for project_id, anchor in anchors.items():
            if project_id in self.cleaning:
                self.notify(
                    f"Cleaning up {self.project_display_label(project_id)}; "
                    f"fetch after it finishes",
                    severity="warning",
                    title="Dashpot fetch",
                )
                continue
            if project_id in self.fetching:
                self.notify(
                    f"Already fetching {self.project_display_label(project_id)}",
                    severity="warning",
                    title="Dashpot fetch",
                )
                continue
            self.fetching[project_id] = anchor
            self.run_off_loop(
                f"fetch {project_id}",
                f"fetch:{project_id}",
                partial(fetcher, Path(anchor)),
                partial(FetchFinished, project_id),
            )
        self.update_alert()

    def on_fetch_finished(self, message: FetchFinished) -> None:
        self.record_fetch_result(message)

    def record_fetch_result(
        self, message: FetchFinished, *, release: bool = True, observe: bool = True
    ) -> None:
        """Report a Remote Fetch and optionally release its Project reservation."""
        if self._closing or self._closed or not self.screen_stack:
            return
        if release:
            self.fetching.pop(message.project_id, None)
        dashboard = self.dashboard
        label = self.project_display_label(message.project_id)
        report = message.report
        if report is None or not report.succeeded:
            detail = message.error if report is None else report.summary()
            self.fetch_errors[message.project_id] = f"Fetch failed: {label}: {detail}"
            self.notify(f"{label}: {detail}", severity="error", title="Dashpot fetch")
        else:
            self.fetch_errors.pop(message.project_id, None)
            self.notify(
                f"{label}: {report.summary()}",
                severity="information",
                title="Dashpot fetch",
            )
        dashboard.update_diagnostics()
        # Whatever a remote changed is observed the passive way: the Git state
        # is re-observed rather than inferred from the fetch, and a fetch
        # that reached no remote leaves the last good observation as it is.
        if observe and report is not None and report.fetched:
            self.observations.schedule(
                self.observations.git_keys(message.project_id), "fetch"
            )
        self.update_alert()

    def request_cleanup(self, selection: CleanupSelection | None) -> None:
        """Preview a Cleanup of the highlighted row, off the event loop.

        The row is resolved through the observation store to a Cleanup
        request at the Project's Branch anchor (a Branch) or the Repository
        the path belongs to (a Worktree). A Project being fetched, or already
        in a Cleanup, is refused rather than mutated twice.
        """
        cleaner = self.cleaner
        if cleaner is None:
            self.notify(
                "Deleting is not available in this view",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        if selection is None:
            self.notify(
                "Highlight a Branch or a Worktree to delete",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        resolved = self.resolve_cleanup_request(selection)
        if resolved is None:
            self.notify(
                "The highlighted row is no longer observed",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        project_id, request = resolved
        label = self.project_display_label(project_id)
        if project_id in self.fetching:
            self.notify(
                f"Fetching {label}; delete after it finishes",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        if project_id in self.cleaning:
            self.notify(
                f"Already cleaning up {label}",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        self.cleaning[project_id] = cleanup_subject(request)
        self.run_off_loop(
            f"inspect cleanup {project_id}",
            f"cleanup:{project_id}",
            partial(
                cleaner.inspect, request, protected=self.cleanup_protection(project_id)
            ),
            partial(CleanupInspected, project_id, request),
        )

    def resolve_cleanup_request(
        self, selection: CleanupSelection
    ) -> tuple[str, CleanupRequest] | None:
        if selection.kind == "branch":
            for branch_row in self.store.query_branches().rows:
                if branch_row.key != selection.key:
                    continue
                snapshot = branch_row.project.snapshot
                anchor = snapshot.branch_anchor if snapshot is not None else None
                if anchor is None:
                    return None
                return branch_row.project.project_id, BranchCleanupRequest(
                    Path(anchor), branch_row.name
                )
            return None
        for worktree_row in self.store.query_worktrees().rows:
            if worktree_row.key == selection.key:
                return worktree_row.project.project_id, WorktreeCleanupRequest(
                    Path(worktree_row.project.primary_anchor),
                    Path(worktree_row.target.path),
                )
        return None

    def cleanup_protection(self, project_id: str) -> tuple[Path, ...]:
        """The checkouts a Cleanup never removes: Dashpot's own and the anchors."""
        project = self.store.project(project_id)
        anchors = tuple(Path(anchor) for anchor in project.anchors) if project else ()
        return (Path.cwd().resolve(), *anchors)

    def on_cleanup_inspected(self, message: CleanupInspected) -> None:
        if self._closing or self._closed or not self.screen_stack:
            return
        if message.preview is None:
            self.cleaning.pop(message.project_id, None)
            self.cleanup_previews.pop(message.project_id, None)
            self.notify(
                f"{self.project_display_label(message.project_id)}: {message.error}",
                severity="error",
                title="Dashpot cleanup",
            )
            return
        self.show_cleanup_preview(message.project_id, message.request, message.preview)

    def show_cleanup_preview(
        self,
        project_id: str,
        request: CleanupRequest,
        preview: CleanupPreview,
        *,
        changed: bool = False,
    ) -> None:
        """Capture the preview's Project and Remote Fetch anchor once."""
        project = self.store.project(project_id)
        screen = CleanupScreen(
            request,
            preview,
            changed=changed,
            fetched_at=project.snapshot.fetched_at
            if project and project.snapshot
            else None,
        )
        anchor = (
            project.snapshot.branch_anchor if project and project.snapshot else None
        )
        captured_anchor = Path(anchor) if anchor else None
        previous = self.cleanup_previews.get(project_id)
        if changed and previous is not None:
            screen.primary_identity = previous[0].primary_identity
            captured_anchor = previous[1]
        self.cleanup_previews[project_id] = (screen, captured_anchor)
        self.push_screen(screen, partial(self.confirm_cleanup, project_id))

    def on_cleanup_screen_fetch_requested(
        self, message: CleanupScreen.FetchRequested
    ) -> None:
        screen = message.screen
        owner = next(
            (
                (project_id, anchor)
                for project_id, (current, anchor) in self.cleanup_previews.items()
                if current is screen
            ),
            None,
        )
        if owner is None or self.screen is not screen or screen.busy:
            return
        project_id, anchor = owner
        if self.fetcher is None or anchor is None:
            screen.fetch_status = (
                "Remote Fetch is unavailable in this view."
                if self.fetcher is None
                else "No Repository Anchor supplies this Project's Branch facts. Refresh and reopen the preview."
            )
            screen.refresh_state()
            return
        if project_id in self.fetching:
            screen.fetch_status = "A Remote Fetch is already running for this Project."
            screen.refresh_state()
            return
        if project_id not in self.cleaning:
            return
        screen.begin_fetch()
        self.fetching[project_id] = str(anchor)
        self.run_worker(
            partial(self.fetch_cleanup_preview, project_id, anchor, screen),
            name=f"fetch cleanup preview {project_id}",
            group=f"fetch:{project_id}",
            exit_on_error=False,
        )
        self.update_alert()

    async def fetch_cleanup_preview(
        self, project_id: str, anchor: Path, screen: CleanupScreen
    ) -> None:
        """Fetch, observe, and re-inspect one captured Cleanup without confirming it."""
        fetcher, cleaner = self.fetcher, self.cleaner
        assert fetcher is not None and cleaner is not None
        worker = get_current_worker()
        preview = None
        report = None
        error = None
        try:
            try:
                report = await self.off_loop(partial(fetcher, anchor))
            except Exception as exc:
                error = str(exc)
            if worker.is_cancelled or self._closing or self._closed:
                return
            status = (
                report.summary() if report is not None else f"Fetch failed: {error}"
            )
            screen.verified_remotes = frozenset(
                report.fetched if report is not None else ()
            )
            self.record_fetch_result(
                FetchFinished(project_id, report=report, error=error),
                release=False,
                observe=False,
            )
            screen.fetch_status = (
                status + "\nRefreshing Git facts and Cleanup evidence…"
            )
            if screen in self.screen_stack:
                screen.refresh_state()
            try:
                await self.observe_cleanup_fetch(project_id)
                project = self.store.project(project_id)
                screen.fetched_at = (
                    project.snapshot.fetched_at
                    if project and project.snapshot
                    else None
                )
                if self.cleanup_previews.get(project_id, (None, None))[0] is screen:
                    preview = await self.off_loop(
                        partial(
                            cleaner.inspect,
                            screen.request,
                            protected=self.cleanup_protection(project_id),
                        )
                    )
            except Exception as exc:
                detail = str(exc) or "Refresh timed out; retry or cancel."
                status += f"\nCould not refresh the preview: {detail}"
            if (
                self.cleanup_previews.get(project_id, (None, None))[0] is screen
                and screen in self.screen_stack
            ):
                await screen.replace_preview(preview, status)
        finally:
            self.fetching.pop(project_id, None)
            self.update_alert()

    async def observe_cleanup_fetch(self, project_id: str) -> None:
        """Wait for post-fetch Git observations before accepting refreshed evidence."""
        keys = self.observations.git_keys(project_id)
        if not keys:
            raise RuntimeError(
                "No Git observation is available; refresh and reopen the preview."
            )
        pending = {key: self.observations.in_flight.get(key, 0) for key in keys}
        future = asyncio.Future[None]()
        waiter = (pending, future)
        self._cleanup_refresh_waiters.append(waiter)
        try:
            self.observations.schedule(keys, "fetch", rerun_in_flight=True)
            await asyncio.wait_for(future, self.cleanup_refresh_timeout)
        finally:
            self._cleanup_refresh_waiters.remove(waiter)
        project = self.store.project(project_id)
        if (
            project is None
            or project.snapshot is None
            or project.snapshot.target_status != "fresh"
        ):
            raise RuntimeError(
                "Git observation is unavailable or stale; inspect Diagnostics and retry."
            )

    def finish_cleanup_observation(self, message: ObservationFinished) -> None:
        """Resolve only post-fetch observation completions after publication."""
        key = message.ticket.key
        for pending, future in self._cleanup_refresh_waiters:
            if (
                future.done()
                or key not in pending
                or message.ticket.generation <= pending[key]
            ):
                continue
            if message.error or message.outcome is None or not message.outcome.accepted:
                future.set_exception(
                    RuntimeError(message.error or "Git refresh was not accepted.")
                )
            else:
                del pending[key]
                if not pending:
                    future.set_result(None)

    def confirm_cleanup(
        self, project_id: str, confirmation: CleanupConfirmation | None
    ) -> None:
        """Perform what the modal confirmed, or release the Project on cancel."""
        if confirmation is None:
            self.cleanup_previews.pop(project_id, None)
            self.cleaning.pop(project_id, None)
            return
        if project_id in self.fetching:
            self.cleanup_previews.pop(project_id, None)
            self.cleaning.pop(project_id, None)
            self.notify(
                "Remote Fetch is still running; reopen Cleanup after it finishes.",
                severity="warning",
            )
            return
        cleaner = self.cleaner
        if cleaner is None:  # pragma: no cover - request_cleanup refuses first.
            return
        self.run_off_loop(
            f"perform cleanup {project_id}",
            f"cleanup:{project_id}",
            partial(
                cleaner.perform,
                confirmation,
                protected=self.cleanup_protection(project_id),
            ),
            partial(CleanupFinished, project_id, confirmation),
        )

    def on_cleanup_finished(self, message: CleanupFinished) -> None:
        if self._closing or self._closed or not self.screen_stack:
            return
        label = self.project_display_label(message.project_id)
        report = message.report
        if report is None:
            self.cleaning.pop(message.project_id, None)
            self.cleanup_previews.pop(message.project_id, None)
            self.notify(
                f"{label}: {message.error}", severity="error", title="Dashpot cleanup"
            )
            # The adapter may have mutated before failing: re-observe anyway.
            self.reobserve_after_cleanup(message.project_id)
            return
        if report.changed:
            # The Project stays held: the revised preview needs another
            # explicit confirmation, and nothing was performed.
            self.notify(
                f"{label}: {report.refusals[0]}",
                severity="warning",
                title="Dashpot cleanup",
            )
            self.show_cleanup_preview(
                message.project_id,
                message.confirmation.request,
                report.preview,
                changed=True,
            )
            return
        self.cleaning.pop(message.project_id, None)
        self.cleanup_previews.pop(message.project_id, None)
        self.notify(
            cleanup_summary(report),
            severity="information" if report.succeeded else "error",
            title=f"{label} cleanup",
        )
        if not report.succeeded:
            # A successful report is already complete in the toast. Keep the
            # detailed screen only where a person needs the refusal or unknown
            # outcome and its recovery context.
            self.push_screen(CleanupReportScreen(report))
        if report.performed:
            self.reobserve_after_cleanup(message.project_id)

    def reobserve_after_cleanup(self, project_id: str) -> None:
        """Observe what a Cleanup changed the passive way, never inferring it."""
        self.observations.schedule(self.observations.git_keys(project_id), "cleanup")

    def project_display_label(self, project_id: str) -> str:
        project = self.store.project(project_id)
        return project.display_label if project is not None else project_id

    def on_observation_finished(self, message: ObservationFinished) -> None:
        # A late completion can be dispatched during shutdown while widgets
        # are being unmounted one by one; any missing widget means the result
        # has nowhere to go and is dropped.
        if self._closing or self._closed or not self.screen_stack:
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
        self.finish_cleanup_observation(message)

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
