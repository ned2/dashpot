"""The app's lifecycle: observation acceptance, refresh scheduling, alerts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event, Lock
from unittest import mock

import pytest
from rich.text import Text
from textual.widgets import DataTable, Footer, Static

from app_harness import (
    NOW,
    SequenceCollector,
    assert_panes_stack_above_full_width_queue,
    issue,
    pane_title,
    selected_title,
    with_first_project,
    with_first_project_snapshot,
    with_first_target,
    workspace_snapshot,
)
from dashpot.app import DashpotApp, project_label
from dashpot.collect import ObservationKey
from dashpot.issue_list import IssueListQuery, row_key
from dashpot.issue_table import (
    COLUMN_KEYS,
    DEFAULT_COLUMNS,
    DEFAULT_SORT,
    IssueTableViewState,
    SortTerm,
)
from dashpot.model import AgentRun, Diagnostic, WorkspaceSnapshot
from dashpot.observation_store import WorkspaceObservationStore
from helpers import snapshot_of, wait_until


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    release = Event()
    app = DashpotApp(SequenceCollector(snapshot, release=release), refresh_seconds=0)

    async with app.run_test(size=(80, 24)) as pilot:
        # Before the first observation the pane carries only its label, never
        # a fabricated ``Open 0 · Closed 0`` inventory.
        assert pane_title(app, "#queue-pane") == "ISSUES"
        release.set()
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        table = app.query_one("#queue", DataTable)

        assert table.row_count == 2
        assert not hasattr(app, "snapshot")
        assert COLUMN_KEYS == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "priority",
            "labels",
            "project",
            "assignees",
            "author",
            "milestone",
            "type",
            "comments",
            "created",
            "last_action",
        )
        assert DEFAULT_COLUMNS == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "priority",
            "labels",
            "last_action",
        )
        assert (SortTerm("last_action", descending=True),) == DEFAULT_SORT
        # Both fixtures carry a priority label, so the conditional column shows.
        assert [str(column.label) for column in table.columns.values()] == [
            "◉",
            "◈",
            "# ↕",
            "TITLE",
            "PRIORITY ↕",
            "LABELS ↕",
            "LAST ACTION ↓",
        ]
        number_key = next(key for key in table.columns if key.value == "number")
        number_header = table.columns[number_key].label
        assert isinstance(number_header, Text)
        assert number_header.justify == "right"
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")
        assert selected_title(app) == "#1: First"
        # No Header: the panes start on the first row of the screen.
        assert app.title == "Dashpot"
        assert not app.query("Header")
        assert app.query_one("#sessions-pane").region.y == 0
        assert app.ALLOW_SELECT
        assert not table.allow_select

        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 0"
        assert str(app.query_one("#issue-count", Static).render()) == "2 issues"
        assert not app.query("#queue-controls .pane-title")
        diagnostics = app.query_one("#diagnostics", Static)
        assert_panes_stack_above_full_width_queue(app)
        # With nothing to report the Diagnostics box is hidden rather than
        # spending a line on a placeholder.
        assert not diagnostics.has_class("-has-messages")
        assert not diagnostics.display
        assert diagnostics.region.height == 0
    # Private loop state is the only witness that the executor was released.
    assert asyncio.get_running_loop()._default_executor is None  # ty: ignore[unresolved-attribute]


@pytest.mark.asyncio
async def test_app_renders_the_injected_issue_list_query() -> None:
    open_issue = issue("test/repo#1", "Open")
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
    )
    snapshot = workspace_snapshot(open_issue, closed_issue)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"closed"}))
        ),
    )

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert app.dashboard.selected_row_key == row_key("issue", closed_issue.id)
        assert selected_title(app) == "#2: Closed"


@pytest.mark.asyncio
async def test_published_observation_updates_inventory_and_result_count() -> None:
    first = workspace_snapshot(issue("test/repo#1", "First"))
    closed_issue = issue(
        "test/repo#3",
        "Done",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
    second = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second"), closed_issue
    )
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(100, 28)):
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 1 · Closed 0"
        assert str(count.render()) == "1 issue"
        assert table.row_count == 1

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"
        assert str(count.render()) == "2 issues"
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_refresh_preserves_selection_by_stable_row_key() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    second = workspace_snapshot(
        issue("test/repo#0", "Inserted", "P0"),
        issue("test/repo#1", "First renamed"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.dashboard.selected_row_key == selected_key)

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key
        assert app.dashboard.selected_row_key == selected_key
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_rows_and_shows_diagnostic() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(RuntimeError("GitHub is unavailable")),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.ui_error is not None)

        assert app.store.revision == 1
        assert app.store.checkpoint() == snapshot
        assert app.query_one("#queue", DataTable).row_count == 1
        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.query_one("#diagnostics", Static).has_class("-has-messages")


@pytest.mark.asyncio
async def test_unavailable_project_observation_keeps_last_good_issue_rows() -> None:
    first = workspace_snapshot(issue("test/repo#1", "Last good"))
    unavailable = with_first_project(
        first,
        status="unavailable",
        snapshot=None,
        diagnostics=(
            Diagnostic(
                source="project:test-repo",
                severity="error",
                message="repository is unavailable",
                code="project-collection",
            ),
        ),
    )
    app = DashpotApp(
        SequenceCollector(unavailable),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert selected_title(app) == "#1: Last good"
        assert "repository is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_unavailable_issue_source_keeps_store_owned_last_good_rows() -> None:
    first = workspace_snapshot(issue("test/repo#1", "Last good"))
    observed_run = AgentRun(
        id="codex-session:16",
        harness="codex",
        process_or_session="16",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/16-observation-store",
        issue_id="I_test/repo#1",
        issue_reference_hint="test/repo#1",
    )
    first = first.model_copy(
        update={
            "agent_runs": (observed_run,),
            "issue_runs": {"I_test/repo#1": (observed_run.id,)},
        }
    )
    unavailable = with_first_project_snapshot(
        first.model_copy(update={"issue_runs": {}}),
        issue_source_status="unavailable",
        issue_source_attempted_at="2026-08-27T04:00:00Z",
        issue_source_last_good_at=None,
        issues=(),
        diagnostics=(
            Diagnostic(
                source="github",
                severity="error",
                message="GitHub unavailable",
                code="github-command",
            ),
        ),
    )
    unavailable = with_first_project(unavailable, status="unavailable")
    app = DashpotApp(
        SequenceCollector(unavailable),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert selected_title(app) == "#1: Last good"
        assert "GitHub unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert "Ⅱ" in app.query_one("#queue", DataTable).get_row_at(0)


@pytest.mark.asyncio
async def test_workspace_identity_conflict_is_visible_as_a_diagnostic() -> None:
    snapshot = workspace_snapshot()
    snapshot = snapshot.model_copy(
        update={
            "diagnostics": (
                *snapshot.diagnostics,
                Diagnostic(
                    source="project:conflicted",
                    severity="error",
                    message="Project Identity project:conflicted has conflicting Repository identities",
                    code="project-repository-conflict",
                ),
            )
        }
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        rendered = str(app.query_one("#diagnostics", Static).render())
        assert "project:conflicted" in rendered
        assert "conflicting Repository identities" in rendered


@pytest.mark.asyncio
async def test_diagnostics_carry_the_severity_they_were_observed_with() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    target = snapshot_of(snapshot.projects[0]).observation_targets[0]
    snapshot = with_first_target(
        snapshot,
        diagnostics=(
            *target.diagnostics,
            Diagnostic(
                source="target:/repo",
                severity="info",
                message="Observation Target is locked: maintenance",
                code="target-locked",
            ),
        ),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        diagnostics = app.query_one("#diagnostics", Static)
        rendered = str(diagnostics.render())
        # An observation reads as one, and does not colour the box amber.
        assert rendered.startswith("↻ ")
        assert diagnostics.has_class("-info")
        assert not diagnostics.has_class("-warning")

    mixed = workspace_snapshot(issue("test/repo#1", "First"))
    mixed_target = snapshot_of(mixed.projects[0]).observation_targets[0]
    mixed = with_first_target(
        mixed,
        diagnostics=(
            *mixed_target.diagnostics,
            Diagnostic(
                source="target:/repo",
                severity="info",
                message="Observation Target is locked: maintenance",
                code="target-locked",
            ),
            Diagnostic(
                source="target:/repo",
                severity="warning",
                message="Observation Target is prunable",
                code="target-prunable",
            ),
        ),
    )
    app = DashpotApp(SequenceCollector(mixed), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        diagnostics = app.query_one("#diagnostics", Static)
        rendered = str(diagnostics.render())
        assert "↻ " in rendered and "⚠ " in rendered
        # The box takes the colour of its most severe line.
        assert diagnostics.has_class("-warning")
        assert not diagnostics.has_class("-info")


@pytest.mark.asyncio
async def test_target_diagnostic_is_visible_without_hiding_project() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    target = snapshot_of(snapshot.projects[0]).observation_targets[0]
    snapshot = with_first_target(
        snapshot,
        availability="unavailable",
        branch=None,
        detached=False,
        dirty=None,
        diagnostics=(
            *target.diagnostics,
            Diagnostic(
                source="target:/repo",
                severity="warning",
                message="Observation Target is prunable",
                code="target-prunable",
            ),
        ),
    )
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        assert app.query_one("#queue", DataTable).row_count == 1
        assert "prunable" in str(app.query_one("#diagnostics", Static).render())


@pytest.mark.asyncio
async def test_unbound_agent_is_counted_on_the_project_not_listed_as_work() -> None:
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="main",
        issue_id=None,
        issue_reference_hint=None,
    )
    snapshot = workspace_snapshot(issue("test/repo#1", "First"), runs=[run])
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: app.store.revision == 1)

        table = app.query_one("#queue", DataTable)
        assert table.row_count == 1
        assert app.dashboard.selected_row_key == row_key("issue", "I_test/repo#1")
        assert selected_title(app) == "#1: First"


def test_project_uses_display_label_independent_of_workspace_and_anchor() -> None:
    project = (
        workspace_snapshot()
        .projects[0]
        .model_copy(
            update={
                "display_label": "Portable Project",
                "workspaces": ("personal", "client"),
                "primary_anchor": "/moved/checkout",
            }
        )
    )

    assert project_label(project) == "Portable Project"


@pytest.mark.asyncio
async def test_issue_transfer_preserves_selection_by_global_identity() -> None:
    transferred = issue("old/repository#7", "Transfer me")
    first = workspace_snapshot(transferred)
    second_snapshot = snapshot_of(first.projects[0]).model_copy(
        update={
            "project_id": "project:new-repository",
            "display_label": "New Repository",
            "issues": (
                issue(
                    "new/repository#70",
                    "Transfer me",
                    id=transferred.id,
                    projectId="project:new-repository",
                ),
            ),
        }
    )
    second = with_first_project(
        first,
        project_id="project:new-repository",
        display_label="New Repository",
        snapshot=second_snapshot,
    )
    selected_key = row_key("issue", transferred.id)
    app = DashpotApp(
        SequenceCollector(second),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(first),
    )

    async with app.run_test(size=(80, 24)):
        assert app.dashboard.selected_row_key == selected_key

        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert app.dashboard.selected_row_key == selected_key
        assert selected_title(app) == "#70: Transfer me"


class RacingCollector:
    def __init__(self, old: WorkspaceSnapshot, new: WorkspaceSnapshot) -> None:
        self.old = old
        self.new = new
        self.started = Event()
        self.release = Event()
        self.calls = 0
        self.lock = Lock()

    def refresh(self) -> WorkspaceSnapshot:
        with self.lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.started.set()
            self.release.wait(timeout=2)
            return self.old
        return self.new


@pytest.mark.asyncio
async def test_refresh_while_in_flight_coalesces_and_reruns_once() -> None:
    initial = workspace_snapshot(issue("test/repo#1", "Initial"))
    old = workspace_snapshot(issue("test/repo#1", "Old result"))
    new = workspace_snapshot(issue("test/repo#1", "New result"))
    collector = RacingCollector(old, new)
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(initial),
    )

    try:
        async with app.run_test(size=(80, 24)) as pilot:
            app.request_refresh("manual")
            await wait_until(collector.started.is_set)
            # Two more presses while the observation runs: neither discards
            # the running work, and together they queue exactly one rerun.
            app.request_refresh("manual")
            app.request_refresh("manual")
            await pilot.pause()
            assert collector.calls == 1
            assert list(app.pending_rerun.values()) == ["manual"]

            collector.release.set()
            # The held observation lands first, then the rerun observes anew.
            await wait_until(lambda: app.store.checkpoint() == new)
            await wait_until(lambda: not app.in_flight)
            assert collector.calls == 2
            assert not app.pending_rerun
            assert selected_title(app) == "#1: New result"
    finally:
        collector.release.set()


@pytest.mark.asyncio
async def test_timer_ticks_coalesce_onto_a_slow_observation(tmp_path: Path) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    collectors["beta"].source.release.clear()
    app = DashpotApp(coordinator, refresh_seconds=0.05)

    try:
        async with app.run_test(size=(80, 24)):
            table = app.query_one("#queue", DataTable)
            await wait_until(lambda: table.row_count == 1)
            # Ticks keep observing the Project that answers while the held
            # one is left to finish: its source is asked exactly once.
            await wait_until(lambda: collectors["alpha"].source.calls >= 3)
            assert collectors["beta"].source.calls == 1
            assert not app.pending_rerun

            collectors["beta"].source.release.set()
            await wait_until(lambda: table.row_count == 2)
            assert row_key("issue", "I_beta#1") in app.dashboard.rows_by_key
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_only_a_timer_tick_coalesces_without_a_rerun(tmp_path: Path) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0, refresh_indicator_seconds=10)
    beta_issues = ObservationKey("issues", "beta")

    try:
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_until(lambda: not app.in_flight)
            collectors["beta"].source.release.clear()
            app.schedule_observations([beta_issues], "manual")
            await wait_until(collectors["beta"].source.started.is_set)
            assert not app.refreshing_visible

            app.schedule_observations([beta_issues], "timer")
            await pilot.pause()
            assert not app.pending_rerun
            assert not app.refreshing_visible

            # A Cleanup that changed the Repository while it was being
            # observed must be observed again; the latest trigger wins.
            app.schedule_observations([beta_issues], "cleanup")
            app.schedule_observations([beta_issues], "manual")
            await pilot.pause()
            assert app.pending_rerun == {beta_issues: "manual"}
            # The press is acknowledged at once, ahead of the indicator delay.
            assert app.refreshing_visible
            assert "refreshing Beta" in alert_text(app)

            collectors["beta"].source.release.set()
            await wait_until(lambda: not app.in_flight and not app.pending_rerun)
            assert collectors["beta"].source.calls == 3
            assert not app.refreshing_visible
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_a_timer_tick_failure_never_toasts() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(
        RuntimeError("GitHub is unavailable"),
        RuntimeError("GitHub is forbidden"),
    )
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        app.request_refresh("timer")
        await wait_until(lambda: alert(app).display)
        assert alert(app).has_class("-error")
        assert len(app._notifications) == 0
        # The failed key is schedulable again: a person's refresh runs and,
        # having changed the failure, earns the toast the tick did not.
        await wait_until(lambda: not app.in_flight)
        await app.run_action("refresh")
        await wait_until(lambda: collector.calls == 2 and not app.in_flight)
        assert len(app._notifications) == 1
        assert "forbidden" in (app.ui_error or "")


def coordinated_workspace(tmp_path: Path):
    """A two-Project coordinator whose sources can be paused per Project."""
    from dashpot.collect import ObservationCoordinator
    from test_coordinator import Clock, ScriptedCollector, ScriptedSource, resolved

    clock = Clock()
    projects = []
    collectors: dict[str, ScriptedCollector] = {}
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        projects.append(resolved(root, name))
        collectors[name] = ScriptedCollector(ScriptedSource(name, clock=clock), root)
    coordinator = ObservationCoordinator(
        projects,
        factory=lambda project, **_kwargs: collectors[project.project_id],
        agent_observer=lambda _targets: ([], []),
        clock=clock,
    )
    return coordinator, collectors


@pytest.mark.asyncio
async def test_first_published_project_renders_before_a_slow_one(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    collectors["beta"].source.release.clear()
    app = DashpotApp(coordinator, refresh_seconds=0)

    try:
        async with app.run_test(size=(80, 24)):
            table = app.query_one("#queue", DataTable)
            await wait_until(lambda: table.row_count == 1)

            assert not table.loading
            assert row_key("issue", "I_alpha#1") in app.dashboard.rows_by_key
            assert [p.project_id for p in app.store.checkpoint().projects] == ["alpha"]

            collectors["beta"].source.release.set()
            await wait_until(lambda: table.row_count == 2)

            assert row_key("issue", "I_beta#1") in app.dashboard.rows_by_key
            await wait_until(
                lambda: (
                    app.store.checkpoint().issue_runs
                    == {"I_alpha#1": (), "I_beta#1": ()}
                )
            )
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_refresh_fans_out_to_every_project(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        beta_key = row_key("issue", "I_beta#1")
        table.move_cursor(row=table.get_row_index(beta_key), animate=False)
        await wait_until(lambda: app.dashboard.selected_row_key == beta_key)
        calls = {name: c.source.calls for name, c in collectors.items()}

        await app.run_action("refresh")
        await wait_until(lambda: collectors["alpha"].source.calls == calls["alpha"] + 1)
        await wait_until(lambda: collectors["beta"].source.calls == calls["beta"] + 1)
        await wait_until(lambda: not app.in_flight)

        assert collectors["alpha"].target_calls == 2
        assert collectors["beta"].target_calls == 2
        assert app.dashboard.selected_row_key == beta_key


@pytest.mark.asyncio
async def test_one_failed_observation_kind_does_not_hide_the_other(
    tmp_path: Path,
) -> None:
    from dashpot.issue_sources import IssueSourceRefreshError

    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        collectors["alpha"].source.collections = [
            IssueSourceRefreshError("github-down", "GitHub is unavailable")
        ]
        collectors["alpha"].head = "fresh00"
        revision = app.store.revision

        def alpha_snapshot():
            project = app.store.project("alpha")
            assert project is not None and project.snapshot is not None
            return project.snapshot

        await app.run_action("refresh")
        # Each half lands on its own; wait for both to have been published.
        await wait_until(
            lambda: (
                app.store.revision > revision
                and alpha_snapshot().issue_source_status == "stale"
                and alpha_snapshot().observation_targets[0].head == "fresh00"
            )
        )

        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert alpha_snapshot().target_status == "fresh"
        assert table.row_count == 2
        assert app.ui_error is None


def alert(app: DashpotApp) -> Static:
    return app.query_one("#alert", Static)


def alert_text(app: DashpotApp) -> str:
    return str(alert(app).render())


@pytest.mark.asyncio
async def test_alert_is_hidden_and_takes_no_space_when_healthy() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: app.store.revision == 2)

        assert not alert(app).display
        assert alert(app).region.height == 0
        assert not alert(app).has_class("-visible")
        # Neither the alert nor the empty Diagnostics box spends a line, so
        # the Issue pane reaches all the way to the footer.
        diagnostics = app.query_one("#diagnostics", Static)
        assert diagnostics.region.height == 0
        footer = app.query_one(Footer)
        assert app.query_one("#queue-pane").region.bottom == footer.region.y


@pytest.mark.asyncio
async def test_slow_refresh_shows_an_indicator_after_the_threshold(
    tmp_path: Path,
) -> None:
    coordinator, collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0, refresh_indicator_seconds=0.2)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        # A slow runner can leave the initial refresh's own indicator showing.
        await wait_until(lambda: not alert(app).display)
        collectors["beta"].source.release.clear()

        await app.run_action("refresh")
        # On a slow runner the other Projects may still be in flight when the
        # indicator first appears ("refreshing 3 Projects"); only Beta is
        # held, so the readout converges on it.
        await wait_until(lambda: "refreshing Beta" in alert_text(app))

        assert alert(app).display
        assert alert(app).has_class("-info")
        await wait_until(lambda: alert(app).region.height == 1)

        collectors["beta"].source.release.set()
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: not app.in_flight)
        assert not alert(app).display


@pytest.mark.asyncio
async def test_quick_refresh_never_flickers_the_indicator(tmp_path: Path) -> None:
    coordinator, _collectors = coordinated_workspace(tmp_path)
    app = DashpotApp(coordinator, refresh_seconds=0, refresh_indicator_seconds=1.0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 2)
        # The initial refresh settles first so its own indicator timer cannot
        # bleed into what the manual refresh is being measured for.
        await wait_until(lambda: not app.in_flight)
        assert app.refresh_indicator_timer is None

        # The refresh schedules its indicator timer while the spy is in
        # place, so a timer that fires is counted rather than raced against.
        with mock.patch.object(
            app, "show_refreshing", wraps=app.show_refreshing
        ) as indicator:
            await app.run_action("refresh")
            await wait_until(lambda: not app.in_flight)

            # A completed refresh stops the pending timer, so the indicator
            # callback never ran and nothing was ever shown to flicker.
            assert indicator.call_count == 0
        assert not alert(app).display
        assert app.refresh_indicator_timer is None


@pytest.mark.asyncio
async def test_refresh_failure_is_a_persistent_alert_that_recovers() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(
        RuntimeError("GitHub is unavailable"),
        RuntimeError("GitHub is unavailable"),
        snapshot,
    )
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(80, 24)):
        await app.run_action("refresh")
        await wait_until(lambda: alert(app).display)

        assert alert(app).has_class("-error")
        assert alert_text(app) == "✖ Refresh failed: Test Repository"
        assert len(app._notifications) == 1

        # A repeated identical failure keeps the alert without another toast.
        # Wait for the observation to actually run and settle: requesting the
        # next refresh too early would coalesce onto it and rerun once.
        await app.run_action("refresh")
        await wait_until(lambda: collector.calls == 2 and not app.in_flight)
        assert len(app._notifications) == 1
        assert alert(app).display

        await app.run_action("refresh")
        await wait_until(lambda: not alert(app).display)

        assert app.ui_error is None
        assert "GitHub is unavailable" not in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_simultaneous_states_share_one_line_in_priority_order() -> None:
    stale = with_first_target(
        workspace_snapshot(issue("test/repo#1", "First"), status="stale"),
        availability="unavailable",
    )
    app = DashpotApp(
        SequenceCollector(RuntimeError("boom")),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(stale),
    )

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: alert(app).display)
        assert alert_text(app).startswith(
            "⚠ Unavailable worktrees: Test Repository /repo"
        )

        await app.run_action("refresh")
        await wait_until(lambda: alert(app).has_class("-error"))

        text = alert_text(app)
        assert text.index("✖ Refresh failed") < text.index("⚠ Unavailable worktrees")
        assert text.index("⚠ Unavailable worktrees") < text.index("⚠ Stale Issues")
        await wait_until(lambda: alert(app).region.height == 1)
        assert "boom" in str(app.query_one("#diagnostics", Static).render())


@pytest.mark.asyncio
async def test_alert_stays_one_line_in_a_compact_terminal() -> None:
    stale = workspace_snapshot(issue("test/repo#1", "First"), status="stale")
    app = DashpotApp(
        SequenceCollector(stale),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(stale),
    )

    async with app.run_test(size=(60, 18)):
        assert app.screen.has_class("-compact")
        await wait_until(lambda: alert(app).display)

        await wait_until(lambda: alert(app).region.height == 1)
        assert alert(app).region.width == 60
        assert_panes_stack_above_full_width_queue(app)

        app.store.replace(workspace_snapshot(issue("test/repo#1", "First")))
        app.dashboard.update_diagnostics()
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: alert(app).region.height == 0)
