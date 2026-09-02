from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast

from textual import events
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.content import Content
from textual.geometry import Size
from textual.message import Message
from textual.screen import Screen
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Select, Static
from textual.worker import get_current_worker
from typing_extensions import override

from .alerts import (
    SEVERITY_GLYPH,
    SEVERITY_RANK,
    AlertSeverity,
    summarize_alerts,
)
from .branch_list import BRANCH_COLUMNS, branch_note, build_branch_rows
from .cleanup import (
    BranchCleanupRequest,
    CleanupAdapter,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    WorktreeCleanupRequest,
)
from .cleanup_view import CleanupReportScreen, CleanupScreen
from .collect import (
    ObservationKey,
    ObservationOutcome,
    ObservationScheduler,
    ObservationTicket,
    SnapshotCollector,
    SnapshotScheduler,
)
from .column_editor import IssueColumnEditor
from .fetch import FetchReport, RemoteFetcher
from .issue_cells import TableCell, cells_match, issue_state_colors
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
    COLUMNS_BY_KEY,
    DEFAULT_SORT,
    ColumnKey,
    IssueTableViewState,
    SortTerm,
    build_rows,
    column_header,
    column_specs,
    searchable_columns,
    shown_columns,
    sort_key_for_terms,
)
from .issue_view import IssueScreen
from .keyed_table import capture_selection, restore_selection
from .legend import LegendScreen
from .list_pane import (
    BRANCHES_PANE_LABEL,
    ISSUE_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
    ListColumn,
    ListPane,
    ListRow,
)
from .model import ProjectObservation
from .observation_store import WorkspaceObservationStore
from .pane_layout import fit_panes, pane_wish
from .session_list import SESSION_COLUMNS, build_session_rows, session_columns
from .spread_table import SpreadTable
from .worktree_list import WORKTREE_COLUMNS, build_worktree_rows

# The Header's sub-title until an observed Project supplies its anchor.
DEFAULT_SUB_TITLE = "passive workspace view"
# Observation triggers a person asked for, whose outcome earns a toast.
MANUAL_TRIGGERS = frozenset({"manual", "fetch"})


@dataclass(frozen=True, slots=True)
class PaneRows:
    """What one refresh hands a list pane: records and the per-refresh extras.

    ``columns`` re-declares the pane's columns when the read model varies
    them; ``note`` is a pane-level fact for the frame's subtitle.
    """

    rows: tuple[ListRow, ...]
    columns: tuple[ListColumn, ...] | None = None
    note: str | None = None


class PaneRowsSource(Protocol):
    """Derive one pane's records from the store for the current theme and time."""

    def __call__(
        self, store: WorkspaceObservationStore, *, dark: bool, now: datetime
    ) -> PaneRows: ...


@dataclass(frozen=True, slots=True)
class PaneSpec:
    """Everything one list pane varies by, declared once.

    The one tuple of these drives composition, the accessors, the focus
    cycle and the store reconcile, so adding a pane is adding a spec.
    """

    pane_id: str
    table_id: str
    label: str
    columns: tuple[ListColumn, ...]
    empty_message: str
    rows: PaneRowsSource


def session_pane_rows(
    store: WorkspaceObservationStore, *, dark: bool, now: datetime
) -> PaneRows:
    """List every active Agent Session, with the columns its result shows."""
    sessions = store.query_sessions()
    return PaneRows(
        build_session_rows(sessions, dark=dark), columns=session_columns(sessions)
    )


def branch_pane_rows(
    store: WorkspaceObservationStore, *, dark: bool, now: datetime
) -> PaneRows:
    """List every observed Branch, noting when the remotes were last fetched."""
    branches = store.query_branches()
    return PaneRows(
        build_branch_rows(branches, dark=dark, now=now),
        note=branch_note(branches.integration_refs, branches.fetched_at, now),
    )


def worktree_pane_rows(
    store: WorkspaceObservationStore, *, dark: bool, now: datetime
) -> PaneRows:
    """List every observed Worktree in the Repository's topology order."""
    return PaneRows(build_worktree_rows(store.query_worktrees(), dark=dark))


# The list panes in reading order, each declared once.
LIST_PANE_SPECS: tuple[PaneSpec, ...] = (
    PaneSpec(
        "sessions-pane",
        "sessions",
        SESSIONS_PANE_LABEL,
        SESSION_COLUMNS,
        "no active sessions",
        session_pane_rows,
    ),
    PaneSpec(
        "worktrees-pane",
        "worktrees",
        WORKTREES_PANE_LABEL,
        WORKTREE_COLUMNS,
        "no worktrees observed yet",
        worktree_pane_rows,
    ),
    PaneSpec(
        "branches-pane",
        "branches",
        BRANCHES_PANE_LABEL,
        BRANCH_COLUMNS,
        "no branches observed yet",
        branch_pane_rows,
    ),
)
# Focus starts in the first list and cycles through the four in reading
# order, the Issue table last; the Header and the Issue controls are not part
# of the cycle.
LIST_TABLE_IDS = (*(spec.table_id for spec in LIST_PANE_SPECS), "queue")


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


class CleanupInspected(Message):
    """One Cleanup's preview was taken off the event loop, or failed."""

    def __init__(
        self,
        project_id: str,
        request: CleanupRequest,
        preview: CleanupPreview | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.request = request
        self.preview = preview
        self.error = error


class CleanupFinished(Message):
    """One confirmed Cleanup was performed, or the adapter failed."""

    def __init__(
        self,
        project_id: str,
        confirmation: CleanupConfirmation,
        report: CleanupReport | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.confirmation = confirmation
        self.report = report
        self.error = error


class FetchFinished(Message):
    """One Project's explicit remote fetch ran; ``error`` is a fetcher failure."""

    def __init__(
        self,
        project_id: str,
        report: FetchReport | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.report = report
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


@dataclass(frozen=True, slots=True)
class CleanupSelection:
    """The pane row a person pressed ``x`` on: which list, and its row key."""

    kind: Literal["branch", "worktree"]
    key: str


class DashboardScreen(Screen[None]):
    """Own the dashboard: composition, the panes, view state and their keys."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "open_issue", "Open Issue"),
        ("f", "fetch", "Fetch & prune remotes"),
        ("x", "cleanup", "Delete Branch/Worktree"),
        ("slash", "focus_search", "Search"),
        ("c", "columns", "Columns"),
        ("o", "cycle_issue_state", "Open/Closed/All"),
        ("s", "sort_next", "Sort column"),
        ("shift+s", "reverse_sort", "Reverse sort"),
    ]

    def __init__(
        self,
        issue_view: IssueTableViewState,
        search_diagnostics: tuple[str, ...],
    ) -> None:
        super().__init__()
        self.issue_view = issue_view
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, IssueListRow] = {}
        self.rendered_cells: dict[str, tuple[TableCell, ...]] = {}
        self.search_diagnostics = search_diagnostics

    @property
    def dashpot(self) -> DashpotApp:
        """Narrow `self.app` once: the store and observation state live there.

        Use `dashpot` for Dashpot-owned state (store, observation errors,
        in-flight tickets) and plain `app` for the Textual API.
        """
        return cast("DashpotApp", self.app)

    @override
    def compose(self) -> ComposeResult:
        yield Header()
        with DashboardBody(id="body"):
            with Container(id="list-row"):
                for spec in LIST_PANE_SPECS:
                    yield ListPane(
                        spec.label,
                        columns=spec.columns,
                        empty_message=spec.empty_message,
                        id=spec.pane_id,
                        table_id=spec.table_id,
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

    def list_panes(self) -> tuple[ListPane, ...]:
        """The content-sized panes in reading order."""
        return tuple(self.list_pane(spec.pane_id) for spec in LIST_PANE_SPECS)

    def list_tables(self) -> tuple[DataTable[Any], ...]:
        """The lists in focus-cycle order: Sessions, Worktrees, Branches, Issues."""
        return tuple(
            self.query_one(f"#{table_id}", DataTable) for table_id in LIST_TABLE_IDS
        )

    def action_focus_search(self) -> None:
        self.query_one("#issue-search", Input).focus()

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
        tables = self.list_tables()
        focused = self.focused
        if focused not in tables:
            return False
        tables[(tables.index(focused) + step) % len(tables)].focus()
        return True

    def on_mount(self) -> None:
        self.query_one("#queue-pane").border_title = Content(ISSUE_PANE_LABEL)
        table = self.queue_table()
        self.show_table_columns(table, shown_columns(self.issue_view.columns, ()))
        self.sessions_pane().table.focus()
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render semantic table colors for the new theme brightness."""

        if self.dashpot.store.has_observations:
            self.reconcile_rows()
            # The list panes render their glyphs in explicit colours chosen
            # for the theme's brightness, so they repaint with the table.
            self.reconcile_list_panes()

    def table_columns(self, table: DataTable[TableCell]) -> tuple[ColumnKey, ...]:
        """The columns the table shows now: the chosen ones a conditional column may leave."""
        return tuple(cast(ColumnKey, str(key.value)) for key in table.columns)

    def show_table_columns(
        self, table: SpreadTable[TableCell], columns: tuple[ColumnKey, ...]
    ) -> None:
        """Rebuild the table's columns when they differ from ``columns``."""
        if columns == self.table_columns(table):
            return
        table.clear(columns=True)
        self.rendered_cells = {}
        for column in column_specs(columns):
            table.add_column(
                column_header(column, self.issue_view.sort),
                key=column.key,
                spread_weight=column.spread_weight,
                tooltip=column.tooltip,
            )

    def action_columns(self) -> None:
        self.app.push_screen(
            IssueColumnEditor(self.issue_view.columns),
            self.apply_issue_columns,
        )

    def apply_issue_columns(self, columns: tuple[ColumnKey, ...] | None) -> None:
        if columns is None or columns == self.issue_view.columns:
            return
        self.issue_view = self.issue_view.with_columns(columns)
        table = self.queue_table()
        if self.dashpot.store.has_observations:
            self.reconcile_rows()
            return
        self.show_table_columns(table, shown_columns(columns, ()))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        column = cast(ColumnKey, str(event.column_key.value))
        if column not in self.issue_view.columns:
            return
        issue_view = self.issue_view.toggle_sort(column)
        if issue_view == self.issue_view:
            return
        self.apply_issue_sort(issue_view, event.data_table)

    def action_sort_next(self) -> None:
        table = self.queue_table()
        self.apply_issue_sort(
            self.issue_view.cycle_sort(self.table_columns(table)), table
        )

    def action_reverse_sort(self) -> None:
        table = self.queue_table()
        self.apply_issue_sort(
            self.issue_view.reverse_sort(self.table_columns(table)), table
        )

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
        selected_key = restore_selection(
            table, prior_key, prior_index, self.rows_by_key
        )
        if selected_key is not None:
            self.show_row(selected_key)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "issue-search":
            return
        parsed_search = parse_issue_search(event.value)
        self.search_diagnostics = parsed_search.diagnostics
        self.update_diagnostics()
        # A sort qualifier in the search text owns the sort while it is
        # present, and removing it restores the default; any other keystroke
        # leaves a sort chosen by key or header click alone.
        previous_search = parse_issue_search(self.issue_view.query.text)
        sort: tuple[SortTerm, ...] | None = None
        if parsed_search.sort is not None:
            sort = issue_search_sort_terms(parsed_search.sort)
        elif previous_search.sort is not None:
            sort = DEFAULT_SORT
        self.set_issue_query(
            replace(self.issue_view.query, text=event.value), sort=sort
        )

    def action_cycle_issue_state(self) -> None:
        states = next_issue_states(self.issue_view.query.states)
        # Drive the control so the header, the query, and the Select agree.
        self.query_one("#issue-state", Select).value = issue_state_filter_value(
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
        if self.dashpot.store.has_observations:
            self.reconcile_rows()

    def update_sort_headers(self, table: DataTable[TableCell]) -> None:
        for key, column in table.columns.items():
            spec = COLUMNS_BY_KEY[cast(ColumnKey, str(key.value))]
            column.label = column_header(spec, self.issue_view.sort)
        table.refresh()

    def sort_rows(self, table: DataTable[TableCell]) -> None:
        shown = self.table_columns(table)
        terms = tuple(term for term in self.issue_view.sort if term.column in shown)
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

    def update_issue_inventory(self, result: IssueListResult) -> None:
        """Title the Issue pane with the complete lifecycle inventory.

        Only publish paths call this: filtering the table never changes the
        inventory, so the title stays put while the result count moves.
        """
        self.query_one("#queue-pane").border_title = Content(
            f"{ISSUE_PANE_LABEL} · {issue_inventory_text(result)}"
        )

    def on_body_resized(self, message: BodyResized) -> None:
        # The last layout of a closing app can report after the screen has
        # been torn down; the panes it would fit are already gone.
        if not self.is_mounted:
            return
        self.fit_list_panes(message.size)

    def on_list_pane_rows_changed(self, _message: ListPane.RowsChanged) -> None:
        # A pane's share depends on what every pane wants, so any change of
        # records refits them all.
        if not self.is_mounted:
            return
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
            tuple(pane_wish(pane.count) for pane in panes),
        )
        for pane, row_cap in zip(panes, caps, strict=True):
            pane.fit_rows(row_cap)

    def reconcile_list_panes(self) -> None:
        """Re-list every observed session, worktree and branch from the store."""
        dark = self.app.current_theme.dark
        now = datetime.now(UTC)
        for spec in LIST_PANE_SPECS:
            view = spec.rows(self.dashpot.store, dark=dark, now=now)
            self.list_pane(spec.pane_id).show_rows(
                view.rows, columns=view.columns, note=view.note
            )

    def reconcile_rows(self) -> IssueListResult:
        """Rebuild the table from the store and return the query result."""
        table = self.queue_table()
        prior_key, prior_index = self.current_selection(table)
        query = replace(
            self.issue_view.query,
            search_fields=searchable_columns(),
        )
        result = self.dashpot.store.query_issues(query)
        self.query_one("#issue-count", Static).update(
            issue_result_count_text(result.matched_issue_count)
        )
        shown = shown_columns(self.issue_view.columns, result.rows)
        self.show_table_columns(table, shown)
        desired_contexts, desired_cells = build_rows(
            result,
            columns=shown,
            sort=self.issue_view.sort,
            dark=self.app.current_theme.dark,
        )
        old_keys = set(self.rendered_cells)
        new_keys = set(desired_cells)
        hidden_sort = any(term.column not in shown for term in self.issue_view.sort)

        with self.app.batch_update():
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
                        column_specs(shown),
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
        selected_key = restore_selection(
            table, prior_key, prior_index, desired_contexts
        )
        if selected_key is None:
            self.selected_row_key = None
            self.update_header()
            return result
        self.show_row(selected_key)
        return result

    def current_selection(self, table: DataTable[TableCell]) -> tuple[str | None, int]:
        """The cursor's identity, falling back to the last selected key."""
        return capture_selection(table, self.selected_row_key)

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
            if row.issue.id != issue_id:
                continue
            table.move_cursor(row=table.get_row_index(key), column=0, animate=False)
            self.show_row(key)
            return

    def action_open_issue(self) -> None:
        if self.selected_row_key is not None:
            self.open_issue(self.selected_row_key)

    def open_issue(self, key: str) -> None:
        """Read the Issue full-screen; nothing happens without an Issue row."""
        row = self.rows_by_key.get(key)
        context = self.dashpot.store.detail_for(row) if row is not None else None
        if context is None or context.issue is None:
            return
        self.app.push_screen(IssueScreen(context))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # A queued highlight can be dispatched during app shutdown, after the
        # screen and its panes have been unmounted.
        if not self.is_mounted:
            return
        # Only the Issue table drives the Issue selection; a session or worktree
        # cursor is for scrolling, copying and refresh scope alone.
        if event.data_table.id != "queue":
            return
        self.show_row(str(event.row_key.value))

    def show_row(self, key: str) -> None:
        row = self.rows_by_key.get(key)
        context = self.dashpot.store.detail_for(row) if row is not None else None
        # A row the store can no longer detail selects nothing; keeping the
        # previous selection would open the wrong Issue.
        self.selected_row_key = key if context is not None else None
        self.update_header(context.project if context is not None else None)

    def update_header(self, project: ProjectObservation | None = None) -> None:
        """Sub-title the Header with the selected Project's Repository Anchor.

        Without a selected row the Header names every observed Project's
        anchor, so an empty Issue table still says what is being observed.
        """
        projects = (project,) if project is not None else self.dashpot.store.projects()
        anchors = " · ".join(candidate.primary_anchor for candidate in projects)
        self.app.sub_title = anchors or DEFAULT_SUB_TITLE

    def update_diagnostics(self) -> None:
        # A refresh failure and a search error are the app's own errors; a
        # Project's diagnostics carry the severity they were observed with.
        entries: list[tuple[AlertSeverity, str]] = [
            ("error", message) for message in self.dashpot.observation_errors.values()
        ]
        entries.extend(
            ("error", message) for message in self.dashpot.fetch_errors.values()
        )
        entries.extend(
            ("error", f"Search: {message}") for message in self.search_diagnostics
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
            failures=app.observation_errors,
            refreshing=tuple(app.in_flight) if app.refreshing_visible else (),
            fetching=tuple(app.fetching),
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


def cleanup_summary(report: CleanupReport) -> str:
    """One line for the toast: each target's outcome, or why nothing ran."""
    if report.refusals:
        return "; ".join(report.refusals)
    return "; ".join(f"{result.outcome} {result.label}" for result in report.results)


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
        ("question_mark", "legend", "Legend"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        collector: SnapshotCollector | ObservationScheduler,
        refresh_seconds: float = 15,
        observation_store: WorkspaceObservationStore | None = None,
        issue_view: IssueTableViewState = IssueTableViewState(),
        refresh_indicator_seconds: float = 0.75,
        fetcher: RemoteFetcher | None = None,
        cleaner: CleanupAdapter | None = None,
    ) -> None:
        super().__init__()
        # The explicit Cleanup seam (``x``): without one the key is refused,
        # so no observation-only construction can ever delete.
        self.cleaner = cleaner
        # Projects with a Cleanup in progress, from the preview being taken
        # until the modal is dismissed or the report is in; a fetch there
        # is refused meanwhile, and a Cleanup while a fetch is in flight.
        self.cleaning: dict[str, str] = {}
        # The explicit fetch seam (``f``); without one the key is refused,
        # so no observation-only construction can ever fetch.
        self.fetcher = fetcher
        # Projects whose remotes are being fetched, by identity, and the last
        # fetch failure per Project until a fetch there succeeds.
        self.fetching: dict[str, str] = {}
        self.fetch_errors: dict[str, str] = {}
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
        # The view state lives on the DashboardScreen once it exists; the app
        # only resolves the injected search's sort and hands both over.
        parsed_search = parse_issue_search(issue_view.query.text)
        explicit_sort = issue_search_sort_terms(parsed_search.sort)
        self.initial_issue_view = (
            replace(issue_view, sort=explicit_sort)
            if explicit_sort is not None
            else issue_view
        )
        self.initial_search_diagnostics = parsed_search.diagnostics
        self.refresh_timer: Timer | None = None
        self.observation_errors: dict[ObservationKey, str] = {}
        # Superseded observations keep their thread until the source returns,
        # so size the pool for every key rather than one refresh at a time.
        self.refresh_executor = ThreadPoolExecutor(
            max_workers=max(2, min(8, len(self.scheduler.keys()))),
            thread_name_prefix="dashpot-refresh",
        )

    @override
    def get_default_screen(self) -> DashboardScreen:
        """Root the app on the dashboard, its one long-lived screen."""
        return DashboardScreen(self.initial_issue_view, self.initial_search_diagnostics)

    @property
    def dashboard(self) -> DashboardScreen:
        """The dashboard screen, whatever is stacked above it."""
        return cast("DashboardScreen", self.screen_stack[0])

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
        # The Legend lists the dashboard's keys alongside the app's, wherever
        # it was opened from.
        self.push_screen(
            LegendScreen(bindings=[*self.BINDINGS, *DashboardScreen.BINDINGS])
        )

    def on_ready(self) -> None:
        dashboard = self.dashboard
        if not self.store.has_observations:
            dashboard.queue_table().loading = True
            self.request_refresh("initial")
        else:
            dashboard.update_issue_inventory(dashboard.reconcile_rows())
            dashboard.reconcile_list_panes()
            dashboard.update_diagnostics()
        if self.refresh_seconds > 0:
            self.refresh_timer = self.set_interval(
                self.refresh_seconds,
                self.action_refresh,
                name="workspace refresh",
            )

    def on_unmount(self) -> None:
        self.refresh_executor.shutdown(wait=False, cancel_futures=True)

    def action_refresh(self) -> None:
        """Refresh every observation in the Workspace."""
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual")

    def request_refresh(self, trigger: str) -> None:
        self.schedule_observations(self.scheduler.keys(), trigger)

    def request_fetch(self) -> None:
        """Fetch the remotes of every observed Project's authoritative anchor.

        Only the Repository Anchor whose refs supplied the Branch observation
        is fetched, so independent clones sharing a Project are left alone.
        A Project already being fetched is refused rather than fetched twice.
        """
        if self.fetcher is None:
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
            self.run_worker(
                partial(self.fetch, project_id, Path(anchor)),
                name=f"fetch {project_id}",
                group=f"fetch:{project_id}",
                exit_on_error=False,
            )
        self.dashboard.update_alert()

    async def fetch(self, project_id: str, anchor: Path) -> None:
        fetcher = self.fetcher
        if fetcher is None:  # pragma: no cover - request_fetch refuses first.
            return
        worker = get_current_worker()
        try:
            report = await asyncio.get_running_loop().run_in_executor(
                self.refresh_executor, fetcher, anchor
            )
        except (
            Exception
        ) as exc:  # UI boundary: a fetcher failure must not exit the app.
            if not worker.is_cancelled:
                self.post_message(FetchFinished(project_id, error=str(exc)))
            return
        if not worker.is_cancelled:
            self.post_message(FetchFinished(project_id, report=report))

    def on_fetch_finished(self, message: FetchFinished) -> None:
        if self._closing or self._closed or not self.screen_stack:
            return
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
        if report is not None and report.fetched:
            self.schedule_observations(
                [
                    key
                    for key in self.scheduler.keys(message.project_id)
                    if key.kind in ("targets", "workspace")
                ],
                "fetch",
            )
        dashboard.update_alert()

    def request_cleanup(self, selection: CleanupSelection | None) -> None:
        """Preview a Cleanup of the highlighted row, off the event loop.

        The row is resolved through the observation store to a Cleanup
        request at the Project's Branch anchor (a Branch) or the Repository
        the path belongs to (a Worktree). A Project being fetched, or already
        in a Cleanup, is refused rather than mutated twice.
        """
        if self.cleaner is None:
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
        self.run_worker(
            partial(self.inspect_cleanup, project_id, request),
            name=f"inspect cleanup {project_id}",
            group=f"cleanup:{project_id}",
            exit_on_error=False,
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

    async def inspect_cleanup(self, project_id: str, request: CleanupRequest) -> None:
        cleaner = self.cleaner
        if cleaner is None:  # pragma: no cover - request_cleanup refuses first.
            return
        worker = get_current_worker()
        protected = self.cleanup_protection(project_id)
        try:
            preview = await asyncio.get_running_loop().run_in_executor(
                self.refresh_executor,
                partial(cleaner.inspect, request, protected=protected),
            )
        except Exception as exc:  # UI boundary: an adapter failure must not exit.
            if not worker.is_cancelled:
                self.post_message(CleanupInspected(project_id, request, error=str(exc)))
            return
        if not worker.is_cancelled:
            self.post_message(CleanupInspected(project_id, request, preview=preview))

    def on_cleanup_inspected(self, message: CleanupInspected) -> None:
        if self._closing or self._closed or not self.screen_stack:
            return
        if message.preview is None:
            self.cleaning.pop(message.project_id, None)
            self.notify(
                f"{self.project_display_label(message.project_id)}: {message.error}",
                severity="error",
                title="Dashpot cleanup",
            )
            return
        self.push_screen(
            CleanupScreen(message.request, message.preview),
            partial(self.confirm_cleanup, message.project_id),
        )

    def confirm_cleanup(
        self, project_id: str, confirmation: CleanupConfirmation | None
    ) -> None:
        """Perform what the modal confirmed, or release the Project on cancel."""
        if confirmation is None:
            self.cleaning.pop(project_id, None)
            return
        self.run_worker(
            partial(self.perform_cleanup, project_id, confirmation),
            name=f"perform cleanup {project_id}",
            group=f"cleanup:{project_id}",
            exit_on_error=False,
        )

    async def perform_cleanup(
        self, project_id: str, confirmation: CleanupConfirmation
    ) -> None:
        cleaner = self.cleaner
        if cleaner is None:  # pragma: no cover - request_cleanup refuses first.
            return
        worker = get_current_worker()
        protected = self.cleanup_protection(project_id)
        try:
            report = await asyncio.get_running_loop().run_in_executor(
                self.refresh_executor,
                partial(cleaner.perform, confirmation, protected=protected),
            )
        except Exception as exc:  # UI boundary: an adapter failure must not exit.
            if not worker.is_cancelled:
                self.post_message(
                    CleanupFinished(project_id, confirmation, error=str(exc))
                )
            return
        if not worker.is_cancelled:
            self.post_message(CleanupFinished(project_id, confirmation, report=report))

    def on_cleanup_finished(self, message: CleanupFinished) -> None:
        if self._closing or self._closed or not self.screen_stack:
            return
        label = self.project_display_label(message.project_id)
        report = message.report
        if report is None:
            self.cleaning.pop(message.project_id, None)
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
            self.push_screen(
                CleanupScreen(
                    message.confirmation.request, report.preview, changed=True
                ),
                partial(self.confirm_cleanup, message.project_id),
            )
            return
        self.cleaning.pop(message.project_id, None)
        self.notify(
            f"{label}: {cleanup_summary(report)}",
            severity="information" if report.succeeded else "error",
            title="Dashpot cleanup",
        )
        self.push_screen(CleanupReportScreen(report))
        if report.performed:
            self.reobserve_after_cleanup(message.project_id)

    def reobserve_after_cleanup(self, project_id: str) -> None:
        """Observe what a Cleanup changed the passive way, never inferring it."""
        self.schedule_observations(
            [
                key
                for key in self.scheduler.keys(project_id)
                if key.kind in ("targets", "workspace")
            ],
            "cleanup",
        )

    def project_display_label(self, project_id: str) -> str:
        project = self.store.project(project_id)
        return project.display_label if project is not None else project_id

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
            self.dashboard.update_alert()

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
        self._finish_in_flight(message.ticket)
        try:
            self._accept_observation(message)
        finally:
            self.dashboard.update_alert()

    def _accept_observation(self, message: ObservationFinished) -> None:
        dashboard = self.dashboard
        key = message.ticket.key
        if message.error is not None:
            if not self.scheduler.is_current(message.ticket):
                return
            dashboard.queue_table().loading = False
            error = f"Refresh failed: {message.error}"
            # The persistent alert already carries a repeated failure; only a
            # new or changed failure earns a toast.
            changed = self.observation_errors.get(key) != error
            self.observation_errors[key] = error
            dashboard.update_diagnostics()
            if message.trigger in MANUAL_TRIGGERS and changed:
                self.notify(error, severity="error", title="Dashpot refresh")
            return
        outcome = message.outcome
        if outcome is None or not outcome.accepted:
            return
        recovered = self.observation_errors.pop(key, None) is not None
        if recovered and message.trigger in MANUAL_TRIGGERS:
            self.notify(
                "Refresh succeeded", severity="information", title="Dashpot refresh"
            )
        # Publishing happens here, on the UI thread, so the store is never
        # mutated while a read model is being rendered from it.
        changes = self.scheduler.publish(self.store)
        # An accepted observation ends the cold load even when an earlier
        # publish already carried its change; the spinner must not outlive it.
        dashboard.queue_table().loading = False
        if not changes:
            dashboard.update_diagnostics()
            return
        dashboard.update_issue_inventory(dashboard.reconcile_rows())
        dashboard.reconcile_list_panes()
        dashboard.update_diagnostics()
        # Follow-ups are derived from what was published, not from this
        # ticket's key: another key's handler may already have published
        # this one's pending composition.
        follow_ups = self.scheduler.follow_ups(changes)
        if follow_ups:
            self.schedule_observations(follow_ups, message.trigger)


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
