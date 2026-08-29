from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from typing import Any, ClassVar, Literal, cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.geometry import Size
from textual.message import Message
from textual.screen import Screen
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Select, Static
from textual.worker import get_current_worker
from typing_extensions import override

from .alerts import summarize_alerts
from .branch_list import BRANCH_COLUMNS, build_branch_rows, fetch_age_text
from .collect import (
    ObservationKey,
    ObservationOutcome,
    ObservationScheduler,
    ObservationTicket,
    SnapshotCollector,
    SnapshotScheduler,
)
from .column_editor import IssueColumnEditor
from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    issue_inventory_text,
    issue_result_count_text,
    next_issue_states,
)
from .issue_search import IssueSearchSort, parse_issue_search
from .issue_table import (
    DEFAULT_SORT,
    ColumnKey,
    IssueTableViewState,
    SortTerm,
    TableCell,
    build_rows,
    cells_match,
    column_label,
    column_specs,
    issue_state_colors,
    searchable_columns,
    sort_key_for_terms,
)
from .issue_view import IssueScreen
from .list_pane import DEFAULT_ROW_CAP, ListPane, ListRow
from .model import ProjectObservation
from .observation_store import WorkspaceObservationStore
from .session_list import SESSION_COLUMNS, build_session_rows
from .spread_table import SpreadTable
from .worktree_list import WORKTREE_COLUMNS, build_worktree_rows

ISSUE_PANE_LABEL = "ISSUES"
SESSIONS_PANE_LABEL = "SESSIONS"
WORKTREES_PANE_LABEL = "WORKTREES"
BRANCHES_PANE_LABEL = "BRANCHES"
# Focus cycles through the four lists in reading order; the Header and
# the Issue controls are not part of the cycle.
LIST_TABLE_IDS = ("queue", "sessions", "worktrees", "branches")
# The blank line between the pane stack and the Issue table, and a list
# pane's frame and header, all of which come out of the height a pane's
# records get. An empty pane is its frame and one message line.
ROW_MARGINS = 1
PANE_FRAME = 2
PANE_HEADER = 1
EMPTY_PANE_HEIGHT = PANE_FRAME + 1
# The Header's sub-title until an observed Project supplies its anchor.
DEFAULT_SUB_TITLE = "passive workspace view"


class ObservationFinished(Message):
    """One keyed observation ran; the outcome says whether it was accepted."""

    def __init__(
        self,
        ticket: ObservationTicket,
        trigger: str,
        outcome: ObservationOutcome | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.ticket = ticket
        self.trigger = trigger
        self.outcome = outcome
        self.error = error


class BodyResized(Message):
    """The dashboard body was laid out at a new size."""

    def __init__(self, size: Size) -> None:
        super().__init__()
        self.size = size


class DashboardBody(Container):
    """The pane stack; its height is the budget the list panes fit into."""

    def on_resize(self, event: events.Resize) -> None:
        self.post_message(BodyResized(event.size))


RefreshScope = Literal["current", "workspace"]


class DashpotApp(App[None]):
    TITLE = "Dashpot"
    SUB_TITLE = DEFAULT_SUB_TITLE
    CSS_PATH = "dashpot.tcss"
    # Textual declares this as an instance attribute, so ClassVar is not an
    # option; the list is never mutated.
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (100, "-wide")]  # ruff: ignore[mutable-class-default]
    # Keep rendered detail and diagnostic text selectable. Interactive widgets
    # such as DataTable opt out independently so mouse gestures remain theirs.
    ALLOW_SELECT = True

    BINDINGS: ClassVar[list[BindingType]] = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("shift+r", "refresh_workspace", "Refresh all"),
        ("enter", "open_issue", "Open Issue"),
        # The list keys sit ahead of the Issue-table controls so a narrow
        # Footer cuts off sort keys, which the column headers also offer.
        ("1", "focus_issues", "Issues"),
        ("2", "focus_sessions", "Sessions"),
        ("3", "focus_worktrees", "Worktrees"),
        ("4", "focus_branches", "Branches"),
        ("slash", "focus_search", "Search"),
        ("c", "columns", "Columns"),
        ("o", "cycle_issue_state", "Open/Closed/All"),
        ("s", "sort_next", "Sort column"),
        ("shift+s", "reverse_sort", "Reverse sort"),
    ]

    def __init__(
        self,
        collector: SnapshotCollector | ObservationScheduler,
        refresh_seconds: float = 15,
        observation_store: WorkspaceObservationStore | None = None,
        issue_view: IssueTableViewState = IssueTableViewState(),
        refresh_indicator_seconds: float = 0.75,
    ) -> None:
        super().__init__()
        # Quick background observations should not flicker an indicator; the
        # refreshing alert appears only once work has been in flight this long.
        self.refresh_indicator_seconds = refresh_indicator_seconds
        self.refresh_indicator_timer: Timer | None = None
        self.refreshing_visible = False
        self.in_flight: dict[ObservationKey, int] = {}
        self.scheduler: ObservationScheduler = (
            collector
            if isinstance(collector, ObservationScheduler)
            else SnapshotScheduler(collector)
        )
        self.refresh_seconds = refresh_seconds
        self.store = observation_store or WorkspaceObservationStore()
        parsed_search = parse_issue_search(issue_view.query.text)
        explicit_sort = issue_search_sort_terms(parsed_search.sort)
        self.issue_view = (
            replace(issue_view, sort=explicit_sort)
            if explicit_sort is not None
            else issue_view
        )
        self.refresh_timer: Timer | None = None
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, IssueListRow] = {}
        self.rendered_cells: dict[str, tuple[TableCell, ...]] = {}
        self.observation_errors: dict[ObservationKey, str] = {}
        self.search_diagnostics = parsed_search.diagnostics
        # Superseded observations keep their thread until the source returns,
        # so size the pool for every key rather than one refresh at a time.
        self.refresh_executor = ThreadPoolExecutor(
            max_workers=max(2, min(8, len(self.scheduler.keys()))),
            thread_name_prefix="dashpot-refresh",
        )

    @property
    def ui_error(self) -> str | None:
        """The current observation failures, newest last, or None."""
        if not self.observation_errors:
            return None
        return "\n".join(self.observation_errors.values())

    @override
    def get_css_variables(self) -> dict[str, str]:
        """Add the Issue state colours for the current theme's brightness."""
        return {
            **super().get_css_variables(),
            **issue_state_colors(dark=self.current_theme.dark),
        }

    @override
    def compose(self) -> ComposeResult:
        yield Header()
        with DashboardBody(id="body"):
            with Container(id="list-row"):
                yield ListPane(
                    SESSIONS_PANE_LABEL,
                    columns=SESSION_COLUMNS,
                    empty_message="no active sessions",
                    id="sessions-pane",
                    table_id="sessions",
                )
                yield ListPane(
                    WORKTREES_PANE_LABEL,
                    columns=WORKTREE_COLUMNS,
                    empty_message="no worktrees observed yet",
                    id="worktrees-pane",
                    table_id="worktrees",
                )
                yield ListPane(
                    BRANCHES_PANE_LABEL,
                    columns=BRANCH_COLUMNS,
                    empty_message="no branches observed yet",
                    id="branches-pane",
                    table_id="branches",
                )
            with Vertical(id="queue-pane"):
                with Horizontal(id="queue-controls"):
                    yield Select(
                        (("Open", "open"), ("Closed", "closed"), ("All", "all")),
                        value=issue_state_filter_value(self.issue_view.query),
                        allow_blank=False,
                        compact=True,
                        id="issue-state",
                    )
                    yield Input(
                        value=self.issue_view.query.text,
                        placeholder="Search Issues",
                        compact=True,
                        id="issue-search",
                    )
                    yield Static(issue_result_count_text(0), id="issue-count")
                yield SpreadTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static("", id="alert")
        yield Static("", id="diagnostics")
        yield Footer()

    def queue_table(self) -> SpreadTable[TableCell]:
        """The Issue table; `query_one` cannot name the cell type itself."""
        return cast(
            "SpreadTable[TableCell]", self.main_screen.query_one("#queue", SpreadTable)
        )

    def sessions_pane(self) -> ListPane:
        return self.main_screen.query_one("#sessions-pane", ListPane)

    def worktrees_pane(self) -> ListPane:
        return self.main_screen.query_one("#worktrees-pane", ListPane)

    def branches_pane(self) -> ListPane:
        return self.main_screen.query_one("#branches-pane", ListPane)

    def list_panes(self) -> tuple[ListPane, ...]:
        """The content-sized panes in reading order."""
        return (self.sessions_pane(), self.worktrees_pane(), self.branches_pane())

    def list_tables(self) -> tuple[DataTable[Any], ...]:
        """The lists in focus-cycle order: Issues, Sessions, Worktrees, Branches."""
        return tuple(
            self.main_screen.query_one(f"#{table_id}", DataTable)
            for table_id in LIST_TABLE_IDS
        )

    def action_focus_issues(self) -> None:
        self.queue_table().focus()

    def action_focus_sessions(self) -> None:
        self.sessions_pane().table.focus()

    def action_focus_worktrees(self) -> None:
        self.worktrees_pane().table.focus()

    def action_focus_branches(self) -> None:
        self.branches_pane().table.focus()

    def action_focus_search(self) -> None:
        self.main_screen.query_one("#issue-search", Input).focus()

    @override
    def action_focus_next(self) -> None:
        if not self.cycle_list_focus(1):
            super().action_focus_next()

    @override
    def action_focus_previous(self) -> None:
        if not self.cycle_list_focus(-1):
            super().action_focus_previous()

    def cycle_list_focus(self, step: int) -> bool:
        """Move focus to the next list when a list has it; otherwise decline."""
        if self.screen is not self.main_screen:
            return False
        tables = self.list_tables()
        focused = self.main_screen.focused
        if focused not in tables:
            return False
        tables[(tables.index(focused) + step) % len(tables)].focus()
        return True

    def on_mount(self) -> None:
        self.main_screen.query_one("#queue-pane").border_title = Content(
            ISSUE_PANE_LABEL
        )
        table = self.queue_table()
        self.add_table_columns(table)
        table.focus()
        self.theme_changed_signal.subscribe(self, self.on_theme_changed)

    def on_text_selected(self, event: events.TextSelected) -> None:
        """Copy arbitrary rendered-text selections when the drag finishes."""

        selected_text = self.screen.get_selected_text()
        if selected_text:
            self.copy_to_clipboard(selected_text)

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render semantic table colors for the new theme brightness."""

        if self.store.has_observations:
            self.reconcile_rows()

    def add_table_columns(self, table: SpreadTable[TableCell]) -> None:
        for column in column_specs(self.issue_view.columns):
            table.add_column(
                column_label(column, self.issue_view.sort),
                key=column.key,
                flex=column.flex,
            )

    def action_columns(self) -> None:
        self.push_screen(
            IssueColumnEditor(self.issue_view.columns),
            self.apply_issue_columns,
        )

    def apply_issue_columns(self, columns: tuple[ColumnKey, ...] | None) -> None:
        if columns is None or columns == self.issue_view.columns:
            return
        self.issue_view = self.issue_view.with_columns(columns)
        table = self.queue_table()
        table.clear(columns=True)
        self.rows_by_key = {}
        self.rendered_cells = {}
        self.add_table_columns(table)
        if self.store.has_observations:
            self.reconcile_rows()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        column = cast(ColumnKey, str(event.column_key.value))
        if column not in self.issue_view.columns:
            return
        issue_view = self.issue_view.toggle_sort(column)
        if issue_view == self.issue_view:
            return
        self.apply_issue_sort(issue_view, event.data_table)

    def action_sort_next(self) -> None:
        self.apply_issue_sort(self.issue_view.cycle_sort())

    def action_reverse_sort(self) -> None:
        self.apply_issue_sort(self.issue_view.reverse_sort())

    def apply_issue_sort(
        self,
        issue_view: IssueTableViewState,
        table: DataTable[TableCell] | None = None,
    ) -> None:
        if table is None:
            table = self.queue_table()
        prior_key, prior_index = self.current_selection(table)
        self.issue_view = issue_view
        self.update_sort_headers(table)
        self.sort_rows(table)
        if not table.row_count:
            return
        if prior_key is not None and prior_key in self.rows_by_key:
            selected_index = table.get_row_index(prior_key)
        else:
            selected_index = min(prior_index, table.row_count - 1)
        table.move_cursor(row=selected_index, column=0, animate=False)
        selected_key = str(
            table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        )
        self.show_row(selected_key)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "issue-search":
            return
        parsed_search = parse_issue_search(event.value)
        self.search_diagnostics = parsed_search.diagnostics
        self.update_diagnostics()
        self.set_issue_query(
            replace(self.issue_view.query, text=event.value),
            sort=issue_search_sort_terms(parsed_search.sort) or DEFAULT_SORT,
        )

    def action_cycle_issue_state(self) -> None:
        states = next_issue_states(self.issue_view.query.states)
        # Drive the control so the header, the query, and the Select agree.
        self.main_screen.query_one(
            "#issue-state", Select
        ).value = issue_state_filter_value(
            replace(self.issue_view.query, states=states)
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "issue-state":
            return
        states = {
            "open": frozenset({"open"}),
            "closed": frozenset({"closed"}),
            "all": frozenset({"open", "closed"}),
        }.get(str(event.value))
        if states is None:
            return
        self.set_issue_query(replace(self.issue_view.query, states=states))

    def set_issue_query(
        self,
        query: IssueListQuery,
        *,
        sort: tuple[SortTerm, ...] | None = None,
    ) -> None:
        next_sort = self.issue_view.sort if sort is None else sort
        query_changed = query != self.issue_view.query
        sort_changed = next_sort != self.issue_view.sort
        if not query_changed and not sort_changed:
            return
        self.issue_view = replace(self.issue_view, query=query, sort=next_sort)
        if sort_changed:
            self.update_sort_headers(self.queue_table())
        if self.store.has_observations:
            self.reconcile_rows()

    def update_sort_headers(self, table: DataTable[TableCell]) -> None:
        columns_by_name = {
            str(key.value): column for key, column in table.columns.items()
        }
        for spec in column_specs(self.issue_view.columns):
            columns_by_name[spec.key].label = Text(
                column_label(spec, self.issue_view.sort)
            )
        table.refresh()

    def sort_rows(self, table: DataTable[TableCell]) -> None:
        terms = tuple(
            term
            for term in self.issue_view.sort
            if term.column in self.issue_view.columns
        )
        if not terms or not table.row_count:
            return
        directions = {term.descending for term in terms}
        if len(directions) != 1:
            raise RuntimeError(
                "Textual sorting requires one direction across all sort terms"
            )
        table.sort(
            *(term.column for term in terms),
            key=sort_key_for_terms(terms),
            reverse=terms[0].descending,
        )

    def on_ready(self) -> None:
        table = self.queue_table()
        if not self.store.has_observations:
            table.loading = True
            self.request_refresh("initial")
        else:
            self.update_issue_inventory(self.reconcile_rows())
            self.reconcile_list_panes()
            self.update_diagnostics()
        if self.refresh_seconds > 0:
            self.refresh_timer = self.set_interval(
                self.refresh_seconds,
                self.action_refresh,
                name="workspace refresh",
            )

    def on_unmount(self) -> None:
        self.refresh_executor.shutdown(wait=False, cancel_futures=True)

    def action_refresh(self) -> None:
        """Refresh the current Project (the selected row's), or all if none."""
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual", scope="current")

    def action_refresh_workspace(self) -> None:
        """Fan a refresh out to every Project in the Workspace."""
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual", scope="workspace")

    def current_project_id(self) -> str | None:
        """The Project of the selected Issue row, if any."""
        row = (
            self.rows_by_key.get(self.selected_row_key)
            if self.selected_row_key is not None
            else None
        )
        return row.project.project_id if row is not None else None

    def request_refresh(self, trigger: str, scope: RefreshScope = "workspace") -> None:
        project_id = self.current_project_id() if scope == "current" else None
        self.schedule_observations(self.scheduler.keys(project_id), trigger)

    def schedule_observations(
        self, keys: Sequence[ObservationKey], trigger: str
    ) -> None:
        for ticket in self.scheduler.request(keys):
            self.in_flight[ticket.key] = ticket.generation
            # A partial rather than a coroutine object: an exclusive worker
            # cancelled before it starts would otherwise leave the coroutine
            # created but never awaited.
            self.run_worker(
                partial(self.observe, ticket, trigger),
                name=f"observe {ticket.key.group}",
                group=ticket.key.group,
                exclusive=True,
                exit_on_error=False,
            )
        if self.refresh_indicator_timer is None and self.in_flight:
            self.refresh_indicator_timer = self.set_timer(
                self.refresh_indicator_seconds,
                self.show_refreshing,
                name="refresh indicator",
            )

    def show_refreshing(self) -> None:
        self.refresh_indicator_timer = None
        if self.in_flight:
            self.refreshing_visible = True
            self.update_alert()

    def _finish_in_flight(self, ticket: ObservationTicket) -> None:
        if self.in_flight.get(ticket.key) == ticket.generation:
            del self.in_flight[ticket.key]
        if not self.in_flight:
            if self.refresh_indicator_timer is not None:
                self.refresh_indicator_timer.stop()
                self.refresh_indicator_timer = None
            self.refreshing_visible = False

    async def observe(self, ticket: ObservationTicket, trigger: str) -> None:
        worker = get_current_worker()
        try:
            outcome = await asyncio.get_running_loop().run_in_executor(
                self.refresh_executor, self.scheduler.observe, ticket
            )
        except Exception as exc:  # UI boundary: source failures must not exit the app.
            if not worker.is_cancelled:
                self.post_message(ObservationFinished(ticket, trigger, error=str(exc)))
            return
        if not worker.is_cancelled:
            self.post_message(ObservationFinished(ticket, trigger, outcome=outcome))

    def on_observation_finished(self, message: ObservationFinished) -> None:
        # A late completion can be dispatched during shutdown while widgets
        # are being unmounted one by one; any missing widget means the result
        # has nowhere to go and is dropped.
        if self._closing or self._closed or not self.screen_stack:
            return
        try:
            self._finish_in_flight(message.ticket)
            try:
                self._accept_observation(message)
            finally:
                self.update_alert()
        except NoMatches:
            return

    def _accept_observation(self, message: ObservationFinished) -> None:
        key = message.ticket.key
        if message.error is not None:
            if not self.scheduler.is_current(message.ticket):
                return
            self.queue_table().loading = False
            error = f"Refresh failed: {message.error}"
            # The persistent alert already carries a repeated failure; only a
            # new or changed failure earns a toast.
            changed = self.observation_errors.get(key) != error
            self.observation_errors[key] = error
            self.update_diagnostics()
            if message.trigger == "manual" and changed:
                self.notify(error, severity="error", title="Dashpot refresh")
            return
        outcome = message.outcome
        if outcome is None or not outcome.accepted:
            return
        recovered = self.observation_errors.pop(key, None) is not None
        if recovered and message.trigger == "manual":
            self.notify(
                "Refresh succeeded", severity="information", title="Dashpot refresh"
            )
        # Publishing happens here, on the UI thread, so the store is never
        # mutated while a read model is being rendered from it.
        changes = self.scheduler.publish(self.store)
        if not changes:
            self.update_diagnostics()
            return
        self.queue_table().loading = False
        self.update_issue_inventory(self.reconcile_rows())
        self.reconcile_list_panes()
        self.update_diagnostics()
        # Follow-ups are derived from what was published, not from this
        # ticket's key: another key's handler may already have published
        # this one's pending composition.
        follow_ups = self.scheduler.follow_ups(changes)
        if follow_ups:
            self.schedule_observations(follow_ups, message.trigger)

    def update_issue_inventory(self, result: IssueListResult) -> None:
        """Title the Issue pane with the complete lifecycle inventory.

        Only publish paths call this: filtering the table never changes the
        inventory, so the title stays put while the result count moves.
        """
        self.main_screen.query_one("#queue-pane").border_title = Content(
            f"{ISSUE_PANE_LABEL} · {issue_inventory_text(result)}"
        )

    def on_body_resized(self, message: BodyResized) -> None:
        # The last layout of a closing app can report after the screen stack
        # has been torn down; the panes it would fit are already gone.
        if self._closing or self._closed or not self.screen_stack:
            return
        self.fit_list_panes(message.size)

    def on_list_pane_rows_changed(self, _message: ListPane.RowsChanged) -> None:
        # A pane's share depends on what every pane wants, so any change of
        # records refits them all.
        if self._closing or self._closed or not self.screen_stack:
            return
        self.fit_list_panes(self.main_screen.query_one("#body").size)

    def fit_list_panes(self, body: Size) -> None:
        """Cap each list pane to the height left after the fixed minimums.

        The Issue table keeps its stylesheet minimum; whatever remains is
        shared between the stacked panes, and a pane that wants less than
        its share (an empty one, or one with few records) leaves the rest
        to the panes that want more. Textual cannot resolve an
        over-constrained column (every `fr` row at its minimum), so the cap
        shrinks first, to a frame with a count when nothing else fits.
        """
        minimum = self.main_screen.query_one("#queue-pane").styles.min_height
        fixed = ROW_MARGINS + (int(minimum.value) if minimum is not None else 0)
        remaining = body.height - fixed
        # Hand out height smallest wish first, so a pane that wants less than
        # an even share never holds back one that wants more.
        wishes = sorted(self.list_panes(), key=pane_wish)
        for index, pane in enumerate(wishes):
            granted = min(pane_wish(pane), remaining // (len(wishes) - index))
            remaining -= granted
            row_cap = granted - PANE_FRAME - PANE_HEADER
            pane.fit_rows(row_cap if row_cap >= 1 else 0)

    def reconcile_list_panes(self) -> None:
        """Re-list every observed session, worktree and branch from the store."""
        self.sessions_pane().show_rows(self.session_rows())
        self.worktrees_pane().show_rows(self.worktree_rows())
        branches = self.store.query_branches()
        now = datetime.now(UTC)
        self.branches_pane().show_rows(
            build_branch_rows(branches, dark=self.current_theme.dark, now=now),
            note=fetch_age_text(branches.fetched_at, now),
        )

    def session_rows(self) -> tuple[ListRow, ...]:
        return build_session_rows(
            self.store.query_sessions(), dark=self.current_theme.dark
        )

    def worktree_rows(self) -> tuple[ListRow, ...]:
        return build_worktree_rows(
            self.store.query_worktrees(), dark=self.current_theme.dark
        )

    def reconcile_rows(self) -> IssueListResult:
        """Rebuild the table from the store and return the query result."""
        table = self.queue_table()
        prior_key, prior_index = self.current_selection(table)
        query = replace(
            self.issue_view.query,
            search_fields=searchable_columns(),
        )
        result = self.store.query_issues(query)
        self.main_screen.query_one("#issue-count", Static).update(
            issue_result_count_text(result.matched_issue_count)
        )
        desired_contexts, desired_cells = build_rows(
            result,
            columns=self.issue_view.columns,
            sort=self.issue_view.sort,
            dark=self.current_theme.dark,
        )
        old_keys = set(self.rendered_cells)
        new_keys = set(desired_cells)
        hidden_sort = any(
            term.column not in self.issue_view.columns for term in self.issue_view.sort
        )

        with self.batch_update():
            if hidden_sort:
                table.clear()
                for key, cells in desired_cells.items():
                    table.add_row(*cells, key=key)
            else:
                for key in old_keys - new_keys:
                    table.remove_row(key)
                for key, cells in desired_cells.items():
                    if key not in old_keys:
                        table.add_row(*cells, key=key)
                        continue
                    previous = self.rendered_cells[key]
                    for column, old_value, new_value in zip(
                        column_specs(self.issue_view.columns),
                        previous,
                        cells,
                        strict=True,
                    ):
                        if not cells_match(old_value, new_value):
                            table.update_cell(
                                key,
                                column.key,
                                new_value,
                                update_width=column.update_width,
                            )
            if table.row_count:
                self.sort_rows(table)

        self.rows_by_key = desired_contexts
        self.rendered_cells = desired_cells
        if not table.row_count:
            self.selected_row_key = None
            self.update_header()
            return result
        if prior_key is not None and prior_key in desired_contexts:
            selected_index = table.get_row_index(prior_key)
        else:
            selected_index = min(prior_index, table.row_count - 1)
        table.move_cursor(row=selected_index, column=0, animate=False)
        selected_key = str(
            table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        )
        self.show_row(selected_key)
        return result

    def current_selection(self, table: DataTable[TableCell]) -> tuple[str | None, int]:
        if not table.row_count:
            return self.selected_row_key, 0
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return key, table.cursor_row

    @property
    def main_screen(self) -> Screen[Any]:
        """The dashboard screen, whatever is stacked above it."""
        return self.screen_stack[0] if self.screen_stack else self.screen

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "queue":
            self.open_issue(str(event.row_key.value))
        elif event.data_table.id == "sessions":
            row = self.sessions_pane().row(str(event.row_key.value))
            if row is not None:
                self.highlight_issue(row.issue_id)

    def highlight_issue(self, issue_id: str | None) -> None:
        """Move the Issue table's cursor to an Issue; nothing happens otherwise."""
        if issue_id is None:
            return
        table = self.queue_table()
        for key, row in self.rows_by_key.items():
            if row.issue is None or row.issue["id"] != issue_id:
                continue
            table.move_cursor(row=table.get_row_index(key), column=0, animate=False)
            self.show_row(key)
            return

    def action_open_issue(self) -> None:
        if self.selected_row_key is not None:
            self.open_issue(self.selected_row_key)

    def open_issue(self, key: str) -> None:
        """Read the Issue full-screen; nothing happens without an Issue row."""
        if isinstance(self.screen, IssueScreen):
            return
        row = self.rows_by_key.get(key)
        context = self.store.detail_for(row) if row is not None else None
        if context is None or context.issue is None:
            return
        self.push_screen(IssueScreen(context))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # A queued highlight can be dispatched during app shutdown, after the
        # screen and its panes have been unmounted.
        if self._closing or self._closed or not self.screen_stack:
            return
        # Only the Issue table drives the Issue selection; a session or worktree
        # cursor is for scrolling, copying and refresh scope alone.
        if event.data_table.id != "queue":
            return
        self.show_row(str(event.row_key.value))

    def show_row(self, key: str) -> None:
        row = self.rows_by_key.get(key)
        context = self.store.detail_for(row) if row is not None else None
        if context is None:
            return
        self.selected_row_key = key
        self.update_header(context.project)

    def update_header(self, project: ProjectObservation | None = None) -> None:
        """Sub-title the Header with the selected Project's Repository Anchor.

        Without a selected row the Header names every observed Project's
        anchor, so an empty Issue table still says what is being observed.
        """
        projects = (project,) if project is not None else self.store.projects()
        anchors = " · ".join(candidate.primary_anchor for candidate in projects)
        self.sub_title = anchors or DEFAULT_SUB_TITLE

    def update_diagnostics(self) -> None:
        messages: list[str] = list(self.observation_errors.values())
        messages.extend(f"Search: {message}" for message in self.search_diagnostics)
        messages.extend(
            (
                f"{entry.project_label} · {entry.diagnostic.source}: "
                f"{entry.diagnostic.message}"
                if entry.project_label is not None
                else f"{entry.diagnostic.source}: {entry.diagnostic.message}"
            )
            for entry in self.store.diagnostics()
        )
        # The Diagnostics box takes no space at all while there is nothing to
        # report; `-has-messages` both colours it and displays it.
        diagnostics = self.main_screen.query_one("#diagnostics", Static)
        diagnostics.set_class(bool(messages), "-has-messages")
        diagnostics.update("\n".join(f"! {message}" for message in messages))
        self.update_alert()

    def update_alert(self) -> None:
        """Render the exceptional-state readout, or hide it entirely."""
        alert = summarize_alerts(
            self.store,
            failures=self.observation_errors,
            refreshing=tuple(self.in_flight) if self.refreshing_visible else (),
        )
        widget = self.main_screen.query_one("#alert", Static)
        widget.set_class(alert is not None, "-visible")
        for severity in ("error", "warning", "info"):
            widget.set_class(
                alert is not None and alert.severity == severity, f"-{severity}"
            )
        widget.update(alert.text if alert is not None else "")


def pane_wish(pane: ListPane) -> int:
    """The height a pane would take unconstrained: frame, header and records.

    A pane with records is granted one spare row for a horizontal scrollbar:
    its table is content-sized under the cap, so the row is only ever taken
    when wide records need it.
    """
    if not pane.count:
        return EMPTY_PANE_HEIGHT
    return PANE_FRAME + PANE_HEADER + min(pane.count, DEFAULT_ROW_CAP) + 1


def issue_search_sort_terms(
    search_sort: IssueSearchSort | None,
) -> tuple[SortTerm, ...] | None:
    if search_sort is None:
        return None
    column: ColumnKey = "created" if search_sort.field == "created" else "last_action"
    return (SortTerm(column, descending=search_sort.descending),)


def project_label(project: ProjectObservation) -> str:
    return project.display_label


def issue_state_filter_value(query: IssueListQuery) -> str:
    if query.states == frozenset({"open"}):
        return "open"
    if query.states == frozenset({"closed"}):
        return "closed"
    return "all"
