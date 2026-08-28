from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Protocol, cast

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.content import Content
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.theme import Theme
from textual.timer import Timer
from textual.worker import get_current_worker
from textual.widgets import DataTable, Footer, Header, Input, Select, Static

from .column_editor import IssueColumnEditor
from .detail_fields import DetailFields, DetailItem, detail_items_text
from .issue_list import IssueListQuery, IssueListRow
from .issue_search import IssueSearchSort, parse_issue_search
from .issue_table import (
    ColumnKey,
    DEFAULT_SORT,
    IssueTableViewState,
    SortTerm,
    TableCell,
    build_rows,
    cells_match,
    column_label,
    column_specs,
    issue_priority,
    issue_state_kind,
    searchable_columns,
    sort_key_for_terms,
)
from .model import AgentRun, Issue, ProjectObservation, WorkspaceSnapshot
from .observation_store import WorkspaceObservationStore


ISSUE_PANE_STATE_CLASSES = (
    "-issue-open",
    "-issue-completed",
    "-issue-not-planned",
    "-issue-duplicate",
)


class SnapshotCollector(Protocol):
    def refresh(self) -> WorkspaceSnapshot: ...


class WorkspaceRefreshFinished(Message):
    def __init__(
        self,
        generation: int,
        trigger: str,
        snapshot: WorkspaceSnapshot | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.trigger = trigger
        self.snapshot = snapshot
        self.error = error


class DashpotApp(App[None]):
    TITLE = "Dashpot"
    SUB_TITLE = "passive workspace view"
    CSS_PATH = "dashpot.tcss"
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (100, "-wide")]
    # Keep rendered detail and diagnostic text selectable. Interactive widgets
    # such as DataTable opt out independently so mouse gestures remain theirs.
    ALLOW_SELECT = True

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("c", "columns", "Columns"),
        ("s", "sort_next", "Sort column"),
        ("shift+s", "reverse_sort", "Reverse sort"),
    ]

    def __init__(
        self,
        collector: SnapshotCollector,
        refresh_seconds: float = 15,
        observation_store: WorkspaceObservationStore | None = None,
        issue_view: IssueTableViewState = IssueTableViewState(),
    ) -> None:
        super().__init__()
        self.collector = collector
        self.refresh_seconds = refresh_seconds
        self.store = observation_store or WorkspaceObservationStore()
        parsed_search = parse_issue_search(issue_view.query.text)
        explicit_sort = issue_search_sort_terms(parsed_search.sort)
        self.issue_view = (
            replace(issue_view, sort=explicit_sort)
            if explicit_sort is not None
            else issue_view
        )
        self.refresh_generation = 0
        self.refresh_timer: Timer | None = None
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, IssueListRow] = {}
        self.rendered_cells: dict[str, tuple[TableCell, ...]] = {}
        self.ui_error: str | None = None
        self.search_diagnostics = parsed_search.diagnostics
        self.refresh_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="dashpot-refresh"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="body"):
            with Container(id="detail-row"):
                with Vertical(id="project-pane"):
                    yield DetailFields(
                        DetailItem("Select a row", kind="message"),
                        id="project-detail",
                    )
                with Vertical(id="selection-pane"):
                    yield DetailFields(
                        DetailItem("Select a row", kind="message"),
                        id="selection-detail",
                    )
            with Vertical(id="queue-pane"):
                with Horizontal(id="queue-controls"):
                    yield Static("WORK", classes="pane-title")
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
                    yield Static("0 of 0 Issues", id="issue-count")
                yield DataTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static("No diagnostics", id="diagnostics")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#project-pane").border_title = Content("PROJECT STATUS")
        self.query_one("#selection-pane").border_title = Content("ISSUE")
        table = self.query_one("#queue", DataTable)
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

    def add_table_columns(self, table: DataTable[TableCell]) -> None:
        for column in column_specs(self.issue_view.columns):
            table.add_column(
                column_label(column, self.issue_view.sort), key=column.key
            )

    def action_columns(self) -> None:
        self.push_screen(
            IssueColumnEditor(self.issue_view.columns),
            self.apply_issue_columns,
        )

    def apply_issue_columns(
        self, columns: tuple[ColumnKey, ...] | None
    ) -> None:
        if columns is None or columns == self.issue_view.columns:
            return
        self.issue_view = self.issue_view.with_columns(columns)
        table = self.query_one("#queue", DataTable)
        table.clear(columns=True)
        self.rows_by_key = {}
        self.rendered_cells = {}
        self.add_table_columns(table)
        if self.store.has_observations:
            self.reconcile_rows()

    def on_data_table_header_selected(
        self, event: DataTable.HeaderSelected
    ) -> None:
        column = cast(ColumnKey, str(event.column_key.value))
        if column not in self.issue_view.columns:
            return
        self.apply_issue_sort(
            self.issue_view.toggle_sort(column), event.data_table
        )

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
            table = self.query_one("#queue", DataTable)
        prior_key, prior_index = self.current_selection(table)
        self.issue_view = issue_view
        self.update_sort_headers(table)
        self.sort_rows(table)
        if not table.row_count:
            return
        if prior_key in self.rows_by_key:
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
            self.update_sort_headers(self.query_one("#queue", DataTable))
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
        table = self.query_one("#queue", DataTable)
        if not self.store.has_observations:
            table.loading = True
            self.request_refresh("initial")
        else:
            self.reconcile_rows()
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
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual")

    def request_refresh(self, trigger: str) -> None:
        self.refresh_generation += 1
        generation = self.refresh_generation
        self.refresh_workspace(generation, trigger)

    @work(
        name="workspace refresh",
        group="refresh",
        exclusive=True,
        exit_on_error=False,
    )
    async def refresh_workspace(self, generation: int, trigger: str) -> None:
        worker = get_current_worker()
        try:
            snapshot = await asyncio.get_running_loop().run_in_executor(
                self.refresh_executor, self.collector.refresh
            )
        except Exception as exc:  # UI boundary: source failures must not exit the app.
            if not worker.is_cancelled:
                self.post_message(
                    WorkspaceRefreshFinished(generation, trigger, error=str(exc))
                )
            return
        if not worker.is_cancelled:
            self.post_message(
                WorkspaceRefreshFinished(generation, trigger, snapshot=snapshot)
            )

    def on_workspace_refresh_finished(self, message: WorkspaceRefreshFinished) -> None:
        if message.generation != self.refresh_generation:
            return
        self.query_one("#queue", DataTable).loading = False
        if message.error is not None:
            self.ui_error = f"Refresh failed: {message.error}"
            self.update_diagnostics()
            if message.trigger == "manual":
                self.notify(self.ui_error, severity="error", title="Dashpot refresh")
            return
        if message.snapshot is not None:
            self.ui_error = None
            self.accept_snapshot(message.snapshot)

    def accept_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        self.store.replace(snapshot)
        self.reconcile_rows()
        self.update_diagnostics()

    def reconcile_rows(self) -> None:
        table = self.query_one("#queue", DataTable)
        prior_key, prior_index = self.current_selection(table)
        query = replace(
            self.issue_view.query,
            search_fields=searchable_columns(),
        )
        result = self.store.query_issues(query)
        self.query_one("#issue-count", Static).update(
            f"{result.matched_issue_count} of {result.observed_issue_count} Issues"
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
            term.column not in self.issue_view.columns
            for term in self.issue_view.sort
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
                        column_specs(self.issue_view.columns), previous, cells
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
            self.query_one("#project-detail", DetailFields).update(
                DetailItem("No project selected", kind="message")
            )
            self.query_one("#selection-pane").border_title = Content("SELECTION")
            self.set_selection_pane_state(None)
            self.query_one("#selection-detail", DetailFields).update(
                DetailItem("No Issues or observed runs", kind="message")
            )
            return
        if prior_key in desired_contexts:
            selected_index = table.get_row_index(prior_key)
        else:
            selected_index = min(prior_index, table.row_count - 1)
        table.move_cursor(row=selected_index, column=0, animate=False)
        selected_key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        self.show_row(selected_key)

    def current_selection(
        self, table: DataTable[TableCell]
    ) -> tuple[str | None, int]:
        if not table.row_count:
            return self.selected_row_key, 0
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return key, table.cursor_row

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_row(str(event.row_key.value))

    def show_row(self, key: str) -> None:
        row = self.rows_by_key.get(key)
        context = self.store.detail_for(row) if row is not None else None
        if context is None:
            return
        self.selected_row_key = key
        self.set_selection_pane_state(context)
        self.query_one("#project-detail", DetailFields).update(
            *project_detail_items(
                context.project,
                context.project_runs,
            )
        )
        self.query_one("#selection-pane").border_title = Content(
            selection_title(context)
        )
        self.query_one("#selection-detail", DetailFields).update(
            *selection_detail_items(context)
        )

    def set_selection_pane_state(self, context: IssueListRow | None) -> None:
        state_class = issue_pane_state_class(context)
        pane = self.query_one("#selection-pane")
        for class_name in ISSUE_PANE_STATE_CLASSES:
            pane.set_class(class_name == state_class, class_name)

    def update_diagnostics(self) -> None:
        messages: list[str] = []
        if self.ui_error:
            messages.append(self.ui_error)
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
        diagnostics = self.query_one("#diagnostics", Static)
        diagnostics.set_class(bool(messages), "-has-messages")
        diagnostics.update(
            "\n".join(f"! {message}" for message in messages) or "No diagnostics"
        )


def project_detail_items(
    project: ProjectObservation, agent_runs: Sequence[AgentRun] = ()
) -> tuple[DetailItem, ...]:
    items = [
        DetailItem(", ".join(project.workspaces), "Workspaces"),
        DetailItem(project.primary_anchor, "Anchor"),
    ]
    if project.snapshot:
        observed_count = sum(
            run.observation_project_id == project.project_id
            for run in agent_runs
        )
        items.append(DetailItem(str(observed_count), "Agents"))
    return tuple(items)


def project_detail_text(
    project: ProjectObservation, agent_runs: Sequence[AgentRun] = ()
) -> str:
    return detail_items_text(project_detail_items(project, agent_runs))


def selection_title(context: IssueListRow) -> str:
    if context.issue:
        return f"#{context.issue['number']}: {context.issue['title']}"
    if context.run:
        return "AGENT RUN"
    return "SELECTION"


def issue_search_sort_terms(
    search_sort: IssueSearchSort | None,
) -> tuple[SortTerm, ...] | None:
    if search_sort is None:
        return None
    column: ColumnKey = (
        "created" if search_sort.field == "created" else "last_action"
    )
    return (SortTerm(column, descending=search_sort.descending),)


def issue_pane_state_class(context: IssueListRow | None) -> str | None:
    if context is None or context.issue is None:
        return None
    return f"-issue-{issue_state_kind(context.issue)}"


def selection_detail_items(context: IssueListRow) -> tuple[DetailItem, ...]:
    items: list[DetailItem] = []
    if context.issue:
        current = context.issue
        location = issue_location(current)
        items.extend(
            [
                DetailItem(location, "Location"),
                DetailItem(current["state"], "State"),
                DetailItem(issue_priority(current), "Priority"),
                DetailItem(
                    ", ".join(current["assignees"]) or "unassigned",
                    "Assignees",
                ),
                DetailItem(", ".join(current["labels"]) or "-", "Labels"),
            ]
        )
        items.append(DetailItem("Agent sessions", kind="section"))
        if not context.observed_runs:
            items.append(DetailItem("-", kind="list"))
        else:
            for run in context.observed_runs:
                location = (
                    run.branch
                    or run.observation_target
                    or run.working_directory
                    or "unknown location"
                )
                items.append(
                    DetailItem(
                        f"{run.id} ({run.state}, {location})",
                        kind="list",
                    )
                )
    if context.run:
        run = context.run
        items.extend(
            [
                DetailItem(f"Unmatched {run.harness} run", kind="heading"),
                DetailItem(run.id, "Run"),
                DetailItem(run.state, "State"),
                DetailItem(run.issue_reference_hint or "-", "Issue hint"),
                DetailItem(run.observation_target or "-", "Target"),
                DetailItem(run.branch or "-", "Branch"),
                DetailItem(run.working_directory or "-", "Directory"),
                DetailItem(run.last_activity_at or "-", "Activity"),
            ]
        )
    return tuple(items)


def selection_detail_text(context: IssueListRow) -> str:
    return detail_items_text(selection_detail_items(context))


def project_label(project: ProjectObservation) -> str:
    return project.display_label


def issue_state_filter_value(query: IssueListQuery) -> str:
    if query.states == frozenset({"open"}):
        return "open"
    if query.states == frozenset({"closed"}):
        return "closed"
    return "all"


def issue_location(issue: Issue) -> str:
    location = issue["location"]
    if location["kind"] == "github":
        return location["url"]
    return f"{location['path']}:{location['line']}"
