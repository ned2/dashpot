from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.worker import get_current_worker
from textual.widgets import DataTable, Footer, Header, Static

from .issue_list import (
    IssueListRow,
    query_issue_list,
)
from .issue_table import (
    IssueTableViewState,
    build_rows,
    column_specs,
    issue_priority,
)
from .model import AgentRun, Issue, ProjectObservation, WorkspaceSnapshot


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

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        collector: SnapshotCollector,
        refresh_seconds: float = 15,
        initial_snapshot: WorkspaceSnapshot | None = None,
        issue_view: IssueTableViewState = IssueTableViewState(),
    ) -> None:
        super().__init__()
        self.collector = collector
        self.refresh_seconds = refresh_seconds
        self.snapshot = initial_snapshot
        self.issue_view = issue_view
        self.refresh_generation = 0
        self.refresh_timer: Timer | None = None
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, IssueListRow] = {}
        self.rendered_cells: dict[str, tuple[str, ...]] = {}
        self.ui_error: str | None = None
        self.refresh_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="dashpot-refresh"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="body"):
            with Container(id="detail-row"):
                with Vertical(id="project-pane"):
                    yield Static("PROJECT STATUS", classes="pane-title")
                    yield Static("Select a row", id="project-detail")
                with Vertical(id="selection-pane"):
                    yield Static("ISSUE", id="selection-title", classes="pane-title")
                    yield Static("Select a row", id="selection-detail")
            with Vertical(id="queue-pane"):
                yield Static("WORK", classes="pane-title")
                yield DataTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static("No diagnostics", id="diagnostics")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#queue", DataTable)
        for column in column_specs(self.issue_view.columns):
            table.add_column(column.label, key=column.key)
        table.focus()

    def on_ready(self) -> None:
        table = self.query_one("#queue", DataTable)
        if self.snapshot is None:
            table.loading = True
            self.request_refresh("initial")
        else:
            self.accept_snapshot(self.snapshot)
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
        self.snapshot = snapshot
        self.reconcile_rows(snapshot)
        self.update_diagnostics()

    def reconcile_rows(self, snapshot: WorkspaceSnapshot) -> None:
        table = self.query_one("#queue", DataTable)
        prior_key, prior_index = self.current_selection(table)
        desired_contexts, desired_cells = build_rows(
            query_issue_list(snapshot, self.issue_view.query),
            columns=self.issue_view.columns,
        )
        old_keys = set(self.rendered_cells)
        new_keys = set(desired_cells)

        with self.batch_update():
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
                    if old_value != new_value:
                        table.update_cell(
                            key,
                            column.key,
                            new_value,
                            update_width=column.update_width,
                        )
            if table.row_count:
                sort_columns = tuple(
                    column
                    for column in ("project", "priority", "title")
                    if column in self.issue_view.columns
                )
                if sort_columns:
                    table.sort(*sort_columns)

        self.rows_by_key = desired_contexts
        self.rendered_cells = desired_cells
        if not table.row_count:
            self.selected_row_key = None
            self.query_one("#project-detail", Static).update("No project selected")
            self.query_one("#selection-title", Static).update("SELECTION")
            self.query_one("#selection-detail", Static).update(
                "No Issues or observed runs"
            )
            return
        if prior_key in desired_contexts:
            selected_index = table.get_row_index(prior_key)
        else:
            selected_index = min(prior_index, table.row_count - 1)
        table.move_cursor(row=selected_index, column=0, animate=False)
        selected_key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        self.show_row(selected_key)

    def current_selection(self, table: DataTable[str]) -> tuple[str | None, int]:
        if not table.row_count:
            return self.selected_row_key, 0
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return key, table.cursor_row

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_row(str(event.row_key.value))

    def show_row(self, key: str) -> None:
        context = self.rows_by_key.get(key)
        if context is None:
            return
        self.selected_row_key = key
        self.query_one("#project-detail", Static).update(
            project_detail_text(
                context.project,
                self.snapshot.agent_runs if self.snapshot else [],
            )
        )
        self.query_one("#selection-title", Static).update(selection_title(context))
        self.query_one("#selection-detail", Static).update(
            selection_detail_text(context)
        )

    def update_diagnostics(self) -> None:
        messages: list[str] = []
        if self.ui_error:
            messages.append(self.ui_error)
        if self.snapshot:
            messages.extend(
                f"{diagnostic.source}: {diagnostic.message}"
                for diagnostic in self.snapshot.diagnostics
            )
            for project in self.snapshot.projects:
                diagnostics = list(project.diagnostics)
                if project.snapshot:
                    diagnostics.extend(project.snapshot.diagnostics)
                    for target in project.snapshot.observation_targets:
                        diagnostics.extend(target.diagnostics)
                messages.extend(
                    f"{project_label(project)} · {diagnostic.source}: {diagnostic.message}"
                    for diagnostic in diagnostics
                )
        diagnostics = self.query_one("#diagnostics", Static)
        diagnostics.set_class(bool(messages), "-has-messages")
        diagnostics.update(
            "\n".join(f"! {message}" for message in messages) or "No diagnostics"
        )


def project_detail_text(
    project: ProjectObservation, agent_runs: Sequence[AgentRun] = ()
) -> str:
    lines = [
        f"Status: {project.status}",
        f"Workspaces: {', '.join(project.workspaces)}",
        f"Anchor: {project.primary_anchor}",
    ]
    snapshot = project.snapshot
    if snapshot:
        lines.append(f"Observation Targets: {len(snapshot.observation_targets)}")
        for target in snapshot.observation_targets:
            state = (
                "unavailable"
                if target.availability == "unavailable"
                else "dirty" if target.dirty else "clean"
            )
            branch = target.branch or (
                "detached" if target.detached else "unknown"
            )
            run_count = sum(
                run.observation_target == target.path
                for run in agent_runs
            )
            lines.append(
                f"  {branch}@{target.head[:8]} {state} · {target.elapsed_ms} ms · "
                f"{run_count} agent{'s' if run_count != 1 else ''} · {target.path}"
            )
        observed_count = sum(
            run.observation_project_id == project.project_id
            for run in agent_runs
        )
        lines.append(f"Observed agents: {observed_count}")
    return "\n".join(lines)


def selection_title(context: IssueListRow) -> str:
    if context.issue:
        return "ISSUE"
    if context.run:
        return "AGENT RUN"
    return "SELECTION"


def selection_detail_text(context: IssueListRow) -> str:
    lines: list[str] = []
    if context.issue:
        current = context.issue
        location = issue_location(current)
        lines.extend(
            [
                current["title"],
                f"Reference: {current['reference']}",
                f"State: {current['state']}",
                f"Priority: {issue_priority(current)}",
                f"Assignees: {', '.join(current['assignees']) or 'unassigned'}",
                f"Location: {location}",
                f"Labels: {', '.join(current['labels']) or '-'}",
            ]
        )
        lines.append("Agent sessions:")
        if not context.observed_runs:
            lines.append("  -")
        else:
            for run in context.observed_runs:
                location = (
                    run.branch
                    or run.observation_target
                    or run.working_directory
                    or "unknown location"
                )
                lines.append(f"  {run.id} ({run.state}, {location})")
    if context.run:
        run = context.run
        lines.extend(
            [
                f"Unmatched {run.harness} run",
                f"Run: {run.id}",
                f"State: {run.state}",
                f"Issue hint: {run.issue_reference_hint or '-'}",
                f"Observation target: {run.observation_target or '-'}",
                f"Branch: {run.branch or '-'}",
                f"Working directory: {run.working_directory or '-'}",
                f"Last activity: {run.last_activity_at or '-'}",
            ]
        )
    return "\n".join(lines)


def project_label(project: ProjectObservation) -> str:
    return project.display_label


def issue_location(issue: Issue) -> str:
    location = issue["location"]
    if location["kind"] == "github":
        return location["url"]
    return f"{location['path']}:{location['line']}"
