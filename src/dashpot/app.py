from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.worker import get_current_worker
from textual.widgets import DataTable, Footer, Header, Label, Static

from .model import AgentRun, ProjectObservation, Task, WorkspaceSnapshot


COLUMN_KEYS = ("status", "project", "priority", "assignee", "sessions", "title")


class SnapshotCollector(Protocol):
    def refresh(self) -> WorkspaceSnapshot: ...


@dataclass(frozen=True, slots=True)
class RowContext:
    project: ProjectObservation
    task: Task | None = None
    run: AgentRun | None = None


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
    ) -> None:
        super().__init__()
        self.collector = collector
        self.refresh_seconds = refresh_seconds
        self.snapshot = initial_snapshot
        self.refresh_generation = 0
        self.refreshing = False
        self.refresh_timer: Timer | None = None
        self.selected_row_key: str | None = None
        self.rows_by_key: dict[str, RowContext] = {}
        self.rendered_cells: dict[str, tuple[str, ...]] = {}
        self.ui_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Waiting for first refresh", id="source-status")
        with Container(id="body"):
            with Container(id="detail-row"):
                with Vertical(id="project-pane"):
                    yield Static("PROJECT STATUS", classes="pane-title")
                    yield Static("Select a row", id="project-detail")
                with Vertical(id="selection-pane"):
                    yield Static("TASK", id="selection-title", classes="pane-title")
                    yield Static("Select a row", id="selection-detail")
            with Vertical(id="queue-pane"):
                yield Static("WORK", classes="pane-title")
                yield DataTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static("No diagnostics", id="diagnostics")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#queue", DataTable)
        table.add_column("S", key="status")
        table.add_column("PROJECT", key="project")
        table.add_column("PRI", key="priority")
        table.add_column("ASSIGNEE", key="assignee")
        table.add_column("SESSIONS", key="sessions")
        table.add_column("TITLE", key="title")
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

    def action_refresh(self) -> None:
        if self.refresh_timer is not None:
            self.refresh_timer.reset()
        self.request_refresh("manual")

    def request_refresh(self, trigger: str) -> None:
        self.refresh_generation += 1
        generation = self.refresh_generation
        self.refreshing = True
        self.update_status()
        self.refresh_workspace(generation, trigger)

    @work(
        name="workspace refresh",
        group="refresh",
        thread=True,
        exclusive=True,
        exit_on_error=False,
    )
    def refresh_workspace(self, generation: int, trigger: str) -> None:
        worker = get_current_worker()
        try:
            snapshot = self.collector.refresh()
        except Exception as exc:  # UI boundary: source failures must not exit the app.
            if not worker.is_cancelled:
                self.post_message(WorkspaceRefreshFinished(generation, trigger, error=str(exc)))
            return
        if not worker.is_cancelled:
            self.post_message(WorkspaceRefreshFinished(generation, trigger, snapshot=snapshot))

    def on_workspace_refresh_finished(self, message: WorkspaceRefreshFinished) -> None:
        if message.generation != self.refresh_generation:
            return
        self.refreshing = False
        self.query_one("#queue", DataTable).loading = False
        if message.error is not None:
            self.ui_error = f"Refresh failed: {message.error}"
            self.update_status()
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
        self.update_status()
        self.update_diagnostics()

    def reconcile_rows(self, snapshot: WorkspaceSnapshot) -> None:
        table = self.query_one("#queue", DataTable)
        prior_key, prior_index = self.current_selection(table)
        desired_contexts, desired_cells = build_rows(snapshot)
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
                for column, old_value, new_value in zip(COLUMN_KEYS, previous, cells):
                    if old_value != new_value:
                        table.update_cell(
                            key,
                            column,
                            new_value,
                            update_width=column in {"project", "assignee", "title"},
                        )
            if table.row_count:
                table.sort("project", "priority", "title")

        self.rows_by_key = desired_contexts
        self.rendered_cells = desired_cells
        if not table.row_count:
            self.selected_row_key = None
            self.query_one("#project-detail", Static).update("No project selected")
            self.query_one("#selection-title", Static).update("SELECTION")
            self.query_one("#selection-detail", Static).update(
                "No tasks or observed runs"
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
            project_detail_text(context.project)
        )
        self.query_one("#selection-title", Static).update(selection_title(context))
        self.query_one("#selection-detail", Static).update(
            selection_detail_text(context)
        )

    def update_status(self) -> None:
        status = self.query_one("#source-status", Label)
        if self.snapshot is None:
            status.update("Refreshing…" if self.refreshing else "Waiting for first refresh")
            return
        projects = self.snapshot.projects
        fresh = sum(project.status == "fresh" for project in projects)
        stale = sum(project.status == "stale" for project in projects)
        unavailable = sum(project.status == "unavailable" for project in projects)
        prefix = "Refreshing…  " if self.refreshing else ""
        suffix = f"  ERROR: {self.ui_error}" if self.ui_error else ""
        project_count = len(projects)
        project_word = "project" if project_count == 1 else "projects"
        status.update(
            f"{prefix}{project_count} {project_word}  {fresh} fresh  {stale} stale  "
            f"{unavailable} unavailable  {self.snapshot.elapsed_ms} ms{suffix}"
        )

    def update_diagnostics(self) -> None:
        messages: list[str] = []
        if self.ui_error:
            messages.append(self.ui_error)
        if self.snapshot:
            for project in self.snapshot.projects:
                diagnostics = list(project.diagnostics)
                if project.snapshot:
                    diagnostics.extend(project.snapshot.diagnostics)
                messages.extend(
                    f"{project_label(project)} · {diagnostic.source}: {diagnostic.message}"
                    for diagnostic in diagnostics
                )
        diagnostics = self.query_one("#diagnostics", Static)
        diagnostics.set_class(bool(messages), "-has-messages")
        diagnostics.update(
            "\n".join(f"! {message}" for message in messages) or "No diagnostics"
        )


def build_rows(
    snapshot: WorkspaceSnapshot,
) -> tuple[dict[str, RowContext], dict[str, tuple[str, ...]]]:
    contexts: dict[str, RowContext] = {}
    cells_by_key: dict[str, tuple[str, ...]] = {}
    for project in snapshot.projects:
        label = project_label(project)
        tasks = project.snapshot.tasks if project.snapshot else []
        runs = project.snapshot.agent_runs if project.snapshot else []
        if not tasks and not runs:
            key = f"project:{project.root}"
            contexts[key] = RowContext(project)
            cells_by_key[key] = (
                status_mark(project.status),
                label,
                "-",
                "unassigned",
                "-",
                "source unavailable" if project.status == "unavailable" else "no tasks",
            )
        matched_runs = {run_id for task in tasks for run_id in task.observed_runs}
        for task in tasks:
            key = task.key
            contexts[key] = RowContext(project, task=task)
            cells_by_key[key] = (
                status_mark(project.status),
                label,
                task.priority,
                task.declared_claimant or "unassigned",
                observed_run_summary(task, runs),
                task.title,
            )
        for run in runs:
            if run.id in matched_runs:
                continue
            key = f"run:{run.id}"
            contexts[key] = RowContext(project, run=run)
            cells_by_key[key] = (
                run_state_mark(run.state),
                label,
                "-",
                "unassigned",
                run.state,
                f"Unmatched {run.harness} run",
            )
    return contexts, cells_by_key


def project_detail_text(project: ProjectObservation) -> str:
    lines = [
        f"Status: {project.status}",
        f"Root: {project.root}",
    ]
    snapshot = project.snapshot
    if snapshot:
        repository = snapshot.repository
        lines.extend(
            [
                f"Git: {repository.branch or 'detached'}@{repository.head[:8]}"
                f" {'dirty' if repository.dirty else 'clean'}",
                f"Worktrees: {len(repository.worktrees)}",
                f"Observed agents: {len(snapshot.agent_runs)}",
            ]
        )
    return "\n".join(lines)


def selection_title(context: RowContext) -> str:
    if context.task:
        return "TASK"
    if context.run:
        return "AGENT RUN"
    return "SELECTION"


def selection_detail_text(context: RowContext) -> str:
    lines: list[str] = []
    snapshot = context.project.snapshot
    if context.task:
        current = context.task
        location = "-"
        if current.location:
            location = current.location.url or current.location.file or "-"
        lines.extend(
            [
                current.title,
                f"Key: {current.key}",
                f"Priority: {current.priority}",
                f"Assignee: {current.declared_claimant or 'unassigned'}",
                f"Location: {location}",
                f"Tags: {', '.join(current.tags) or '-'}",
            ]
        )
        observed = (
            {
                run.id: run
                for run in snapshot.agent_runs
                if run.id in current.observed_runs
            }
            if snapshot
            else {}
        )
        lines.append("Agent sessions:")
        if not current.observed_runs:
            lines.append("  -")
        else:
            for run_id in current.observed_runs:
                run = observed.get(run_id)
                if run is None:
                    lines.append(f"  {run_id} (missing observation)")
                    continue
                location = (
                    run.branch
                    or run.worktree
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
                f"Task reference: {run.declared_work_key or '-'}",
                f"Worktree: {run.worktree or '-'}",
                f"Branch: {run.branch or '-'}",
                f"Working directory: {run.working_directory or '-'}",
                f"Last activity: {run.last_activity_at or '-'}",
            ]
        )
    return "\n".join(lines)


def project_label(project: ProjectObservation) -> str:
    if project.repository == ".":
        return project.workspace
    return f"{project.workspace}/{project.repository}"


def status_mark(status: str) -> str:
    return {"fresh": "●", "stale": "◐", "unavailable": "!"}.get(status, "?")


def run_state_mark(state: str) -> str:
    return {"running": "▶", "waiting": "Ⅱ", "unknown": "?"}.get(state, "?")


def observed_run_summary(task: Task, runs: list[AgentRun]) -> str:
    by_id = {run.id: run for run in runs}
    counts = {"running": 0, "waiting": 0, "unknown": 0}
    for run_id in task.observed_runs:
        run = by_id.get(run_id)
        state = run.state if run else "unknown"
        counts[state] += 1
    summary = " ".join(
        f"{run_state_mark(state)}{counts[state]}"
        for state in ("running", "waiting", "unknown")
        if counts[state]
    )
    return summary or "0"
