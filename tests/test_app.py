"""The app's lifecycle: observation acceptance, refresh scheduling, alerts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event, Lock
from unittest import mock

import pytest
from rich.text import Text
from textual import events
from textual.widgets import DataTable, Footer, Static

import factories
from app_harness import (
    NOW,
    SequenceCollector,
    assert_panes_stack_above_full_width_queue,
    dashboard_app,
    first_load_landed,
    hold_sources,
    issue,
    observation_landed,
    page_summary,
    pane_title,
    selected_title,
    serve_snapshot,
    with_first_project,
    with_first_project_snapshot,
    with_first_target,
    workspace_snapshot,
)
from dashpot.app import DashboardScreen, DashpotApp
from dashpot.collect import ObservationKey, ObservationOutcome, ObservationTicket
from dashpot.issue_list import row_key
from dashpot.issue_table import COLUMN_KEYS, DEFAULT_COLUMNS
from dashpot.issue_view import selection_title
from dashpot.messages import ObservationFinished, ObservationTrigger
from dashpot.model import AgentRun, Diagnostic, WorkspaceSnapshot
from helpers import snapshot_of, wait_until


@pytest.mark.asyncio
async def test_initial_refresh_populates_queue_and_detail() -> None:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    release = Event()
    app = dashboard_app(SequenceCollector(snapshot, release=release), release=release)

    async with app.run_test(size=(80, 24)) as pilot:
        # Before the first totals land the pane says so, never a fabricated
        # ``Open 0 · Closed 0`` inventory.
        await wait_until(
            lambda: (
                pane_title(app, "#queue-pane")
                == "ISSUES · Open ? · Closed ? · totals unavailable"
            )
        )
        release.set()
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        table = app.query_one("#queue", DataTable)

        assert table.row_count == 2
        assert not hasattr(app, "snapshot")
        assert COLUMN_KEYS == (
            "agent_state",
            "issue_state",
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
            "agent_state",
            "issue_state",
            "number",
            "title",
            "priority",
            "labels",
            "last_action",
        )
        # Both fixtures carry a priority label, so the conditional column
        # shows; the source's own order carries no arrow.
        assert [str(column.label) for column in table.columns.values()] == [
            "◈",
            "◉",
            "# ↕",
            "TITLE",
            "PRIORITY ↕",
            "LABELS ↕",
            "LAST ACTION ↕",
        ]
        number_key = next(key for key in table.columns if key.value == "number")
        number_header = table.columns[number_key].label
        assert isinstance(number_header, Text)
        assert number_header.justify == "right"
        assert app.dashboard.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )
        assert selected_title(app) == "#1: First"
        # No Header: the panes start on the first row of the screen.
        assert app.title == "Dashpot"
        assert not app.query("Header")
        assert app.query_one("#sessions-pane").region.y == 0
        assert app.ALLOW_SELECT
        assert not table.allow_select

        assert pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 0"
        assert (
            str(app.query_one("#issue-count", Static).render()) == "2/2 matches · fresh"
        )
        assert not app.query("#issue-filters .pane-title")
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
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(100, 28)):
        await wait_until(lambda: first_load_landed(app))
        count = app.query_one("#issue-count", Static)
        table = app.query_one("#queue", DataTable)
        assert pane_title(app, "#queue-pane") == "ISSUES · Open 1 · Closed 0"
        assert str(count.render()) == page_summary(1)
        assert table.row_count == 1

        serve_snapshot(app, second)
        await app.run_action("refresh")
        await wait_until(
            lambda: (
                app.store.revision == 2
                and pane_title(app, "#queue-pane") == "ISSUES · Open 2 · Closed 1"
                and table.row_count == 2
            )
        )

        assert str(count.render()) == page_summary(2)


async def refresh_over_a_grown_page(
    app: DashpotApp, trigger: ObservationTrigger
) -> None:
    """Select the last Issue, then observe a page with one inserted before it."""
    second = workspace_snapshot(
        issue("test/repo#0", "Inserted", "P0"),
        issue("test/repo#1", "First renamed"),
        issue("test/repo#2", "Second", "P2"),
    )
    table = app.query_one("#queue", DataTable)
    selected_key = row_key("issue", "I_test/repo#2")
    await wait_until(lambda: first_load_landed(app))
    table.move_cursor(row=table.get_row_index(selected_key), animate=False)
    await wait_until(lambda: app.dashboard.issue_table.selected_row_key == selected_key)

    serve_snapshot(app, second)
    app.request_refresh(trigger)
    await wait_until(lambda: app.store.revision == 2 and table.row_count == 3)

    selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
    assert selected == selected_key
    assert app.dashboard.issue_table.selected_row_key == selected_key


@pytest.mark.asyncio
async def test_timer_refresh_preserves_selection_by_stable_row_key() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = dashboard_app(SequenceCollector(first, first))

    async with app.run_test(size=(80, 24)):
        await refresh_over_a_grown_page(app, "timer")


# A manual refresh restarts the page from one; the page it replaces stays on
# screen until the restarted one lands, so the selection survives as it does
# across the timer path above.
@pytest.mark.asyncio
async def test_manual_refresh_preserves_selection_by_stable_row_key() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = dashboard_app(SequenceCollector(first, first))

    async with app.run_test(size=(80, 24)):
        await refresh_over_a_grown_page(app, "manual")


@pytest.mark.asyncio
async def test_a_restarted_page_stays_shown_without_an_unavailable_alert() -> None:
    first = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second", "P2"),
    )
    app = dashboard_app(SequenceCollector(first, first))

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(
            lambda: app.dashboard.issue_table.selected_row_key == selected_key
        )

        # While the restarted pages are held in flight, the shown rows, the
        # selection and the page summary stay, and no alert calls the Issues
        # unavailable for a page that is merely restarting.
        gate = hold_sources(app)
        try:
            await app.run_action("refresh")
            await wait_until(lambda: app.store.revision == 2)
            await pilot.pause()
            assert table.row_count == 2
            assert app.dashboard.issue_table.selected_row_key == selected_key
            assert selected_title(app) == "#2: Second"
            assert "Unavailable Issues" not in alert_text(app)
            assert not alert(app).display
        finally:
            gate.set()
        await wait_until(lambda: observation_landed(app, 2))
        assert app.dashboard.issue_table.selected_row_key == selected_key


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_rows_and_shows_diagnostic() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(
        SequenceCollector(snapshot, RuntimeError("GitHub is unavailable"))
    )

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await app.run_action("refresh")
        # The restarted pages land independently of the failed observation.
        await wait_until(
            lambda: bool(app.observations.errors) and first_load_landed(app)
        )

        assert app.store.revision == 1
        assert app.store.checkpoint() == snapshot
        assert app.query_one("#queue", DataTable).row_count == 1
        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.query_one("#diagnostics", Static).has_class("-has-messages")


@pytest.mark.asyncio
async def test_unavailable_project_observation_keeps_the_pages_rows() -> None:
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
    # The Query Source still answers: only the Project observation failed.
    app = dashboard_app(SequenceCollector(first, unavailable))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await app.run_action("refresh")
        await wait_until(lambda: observation_landed(app, 2))

        assert app.query_one("#queue", DataTable).row_count == 1
        assert selected_title(app) == "#1: Last good"
        assert "repository is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_unavailable_issue_source_empties_the_page_but_not_the_store() -> None:
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
    app = dashboard_app(SequenceCollector(first, unavailable))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        assert "◐" in [str(cell) for cell in table.get_row_at(0)]

        serve_snapshot(app, unavailable)
        await app.run_action("refresh")
        await wait_until(lambda: observation_landed(app, 2) and table.row_count == 0)

        # The page owns the rows, so an unavailable source shows none; the
        # store still holds the last good Issue the observed run is bound to.
        count = app.query_one("#issue-count", Static)
        assert str(count.render()) == "0/? matches · unavailable"
        assert "GitHub unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert "Unavailable Issues: Test Repository" in alert_text(app)
        assert [item.id for item in snapshot_of(app.store.projects()[0]).issues] == [
            "I_test/repo#1"
        ]
        assert app.store.checkpoint().agent_runs[0].issue_id == "I_test/repo#1"


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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))

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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))

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
    app = dashboard_app(SequenceCollector(mixed))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))

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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))

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
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))

        table = app.query_one("#queue", DataTable)
        assert table.row_count == 1
        assert app.dashboard.issue_table.selected_row_key == row_key(
            "issue", "I_test/repo#1"
        )
        assert selected_title(app) == "#1: First"


def transferred_snapshots() -> tuple[WorkspaceSnapshot, WorkspaceSnapshot, str]:
    """Two observations across which one Issue moves to a new Project."""
    transferred = issue("old/repository#7", "Transfer me")
    first = workspace_snapshot(issue("old/repository#1", "Stays"), transferred)
    second_snapshot = snapshot_of(first.projects[0]).model_copy(
        update={
            "project_id": "project:new-repository",
            "display_label": "New Repository",
            "issues": (
                issue(
                    "new/repository#1",
                    "Stays",
                    id="I_old/repository#1",
                    projectId="project:new-repository",
                ),
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
    return first, second, row_key("issue", transferred.id)


@pytest.mark.asyncio
async def test_issue_transfer_follows_the_issue_to_its_new_project() -> None:
    first, second, selected_key = transferred_snapshots()
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        assert selection_title(app.dashboard.issue_table.rows_by_key[selected_key]) == (
            "#7: Transfer me"
        )

        serve_snapshot(app, second)
        app.timer_refresh()
        await wait_until(
            lambda: (
                observation_landed(app, 2)
                and table.row_count == 2
                and selected_key in app.dashboard.issue_table.rows_by_key
            )
        )

        assert selection_title(app.dashboard.issue_table.rows_by_key[selected_key]) == (
            "#70: Transfer me"
        )


# A page row needs its Project in the store, and a transfer changes both:
# whichever of the refreshed page and the Project observation lands first
# names a Project the other does not yet know. The row keeps the Project it
# last joined with until the other lands, and the selection with it.
@pytest.mark.asyncio
async def test_issue_transfer_preserves_selection_by_global_identity() -> None:
    first, second, selected_key = transferred_snapshots()
    app = dashboard_app(SequenceCollector(first, second))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one("#queue", DataTable)
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(
            lambda: app.dashboard.issue_table.selected_row_key == selected_key
        )
        assert selected_title(app) == "#7: Transfer me"

        # The order is pinned so the outcome is: the Project lands, then the
        # page that names it.
        serve_snapshot(app, second)
        gate = hold_sources(app)
        app.timer_refresh()
        await wait_until(lambda: app.store.revision == 2)
        gate.set()
        await wait_until(lambda: observation_landed(app, 2) and table.row_count == 2)

        assert app.dashboard.issue_table.selected_row_key == selected_key
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
    old = workspace_snapshot(issue("test/repo#1", "Old result"))
    new = workspace_snapshot(issue("test/repo#1", "New result"))
    collector = RacingCollector(old, new)
    app = dashboard_app(collector, snapshot=new)

    try:
        async with app.run_test(size=(80, 24)) as pilot:
            # The initial observation is the one the collector holds.
            await wait_until(collector.started.is_set)
            # Two presses while the observation runs: neither discards the
            # running work, and together they queue exactly one rerun.
            app.request_refresh("manual")
            app.request_refresh("manual")
            await pilot.pause()
            assert collector.calls == 1
            assert list(app.observations.pending_rerun.values()) == ["manual"]

            collector.release.set()
            # The held observation lands first, then the rerun observes anew.
            await wait_until(lambda: app.store.checkpoint() == new)
            await wait_until(lambda: not app.observations.in_flight)
            assert app.store.revision == 2
            assert collector.calls == 2
            assert not app.observations.pending_rerun
    finally:
        collector.release.set()


@pytest.mark.asyncio
async def test_timer_ticks_coalesce_onto_a_slow_observation(tmp_path: Path) -> None:
    app, collectors = coordinated_app(tmp_path, refresh_seconds=0.05)
    collectors["beta"].source.release.clear()

    try:
        async with app.run_test(size=(80, 24)):
            table = app.query_one("#queue", DataTable)
            await wait_until(lambda: table.row_count == 1)
            # Ticks keep observing the Project that answers while the held
            # one is left to finish: its source is asked exactly once.
            await wait_until(lambda: collectors["alpha"].source.calls >= 3)
            assert collectors["beta"].source.calls == 1
            assert not app.observations.pending_rerun

            collectors["beta"].source.release.set()
            await wait_until(
                lambda: (
                    app.store.checkpoint().issue_runs
                    == {"I_alpha#1": (), "I_beta#1": ()}
                )
            )
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_only_a_timer_tick_coalesces_without_a_rerun(tmp_path: Path) -> None:
    app, collectors = coordinated_app(tmp_path, refresh_indicator_seconds=10)
    beta_issues = ObservationKey("issues", "beta")

    try:
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_until(lambda: not app.observations.in_flight)
            collectors["beta"].source.release.clear()
            app.observations.schedule([beta_issues], "manual")
            await wait_until(collectors["beta"].source.started.is_set)
            assert not app.observations.refreshing_visible

            app.observations.schedule([beta_issues], "timer")
            await pilot.pause()
            assert not app.observations.pending_rerun
            assert not app.observations.refreshing_visible

            # A Cleanup that changed the Repository while it was being
            # observed must be observed again; the latest trigger wins.
            app.observations.schedule([beta_issues], "cleanup")
            app.observations.schedule([beta_issues], "manual")
            await pilot.pause()
            assert app.observations.pending_rerun == {beta_issues: "manual"}
            # The press is acknowledged at once, ahead of the indicator delay.
            assert app.observations.refreshing_visible
            assert "refreshing Beta" in alert_text(app)

            collectors["beta"].source.release.set()
            await wait_until(
                lambda: (
                    not app.observations.in_flight
                    and not app.observations.pending_rerun
                )
            )
            assert collectors["beta"].source.calls == 3
            assert not app.observations.refreshing_visible
    finally:
        collectors["beta"].source.release.set()


@pytest.mark.asyncio
async def test_a_key_press_observes_the_issue_source_again(tmp_path: Path) -> None:
    app, collectors = coordinated_app(tmp_path)
    beta = collectors["beta"].source

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: not app.observations.in_flight)
        app.observations.schedule([ObservationKey("issues", "beta")], "timer")
        await wait_until(lambda: beta.calls == 2 and not app.observations.in_flight)
        await pilot.press("r")
        # The press's own observation, after the initial one and the tick.
        await wait_until(lambda: beta.calls == 3 and not app.observations.in_flight)


@pytest.mark.asyncio
async def test_a_timer_tick_failure_never_toasts() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(
        snapshot,
        RuntimeError("GitHub is unavailable"),
        RuntimeError("GitHub is forbidden"),
    )
    app = dashboard_app(collector)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await wait_until(lambda: not app.observations.in_flight)
        app.request_refresh("timer")
        await wait_until(lambda: alert(app).display)
        assert alert(app).has_class("-error")
        assert len(app._notifications) == 0
        # The failed key is schedulable again: a person's refresh runs and,
        # having changed the failure, earns the toast the tick did not.
        await wait_until(lambda: not app.observations.in_flight)
        await app.run_action("refresh")
        await wait_until(
            lambda: (
                collector.calls == 3
                and not app.observations.in_flight
                and len(app._notifications) == 1
            )
        )
        assert len(app._notifications) == 1
        assert any("forbidden" in error for error in app.observations.errors.values())


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


def coordinated_app(
    tmp_path: Path,
    *,
    refresh_seconds: float = 0,
    refresh_indicator_seconds: float = 0.75,
):
    """The shipped app over a coordinated workspace, its pages served for Alpha.

    The coordinator observes both Projects; the Query Sources answer for the
    first one, as the shipped app consults one Project's source.
    """
    from test_coordinator import issue as coordinated_issue
    from test_coordinator import target as coordinated_target

    coordinator, collectors = coordinated_workspace(tmp_path)
    alpha = factories.project(
        "alpha",
        coordinated_issue("alpha#1", "alpha"),
        targets=[coordinated_target(tmp_path / "alpha")],
        anchors=(str(tmp_path / "alpha"),),
    )
    app = dashboard_app(
        coordinator,
        snapshot=factories.workspace(alpha),
        refresh_seconds=refresh_seconds,
        refresh_indicator_seconds=refresh_indicator_seconds,
    )
    return app, collectors


@pytest.mark.asyncio
async def test_first_published_project_renders_before_a_slow_one(
    tmp_path: Path,
) -> None:
    app, collectors = coordinated_app(tmp_path)
    collectors["beta"].source.release.clear()

    try:
        async with app.run_test(size=(80, 24)):
            table = app.query_one("#queue", DataTable)
            await wait_until(lambda: table.row_count == 1)
            await wait_until(
                lambda: (
                    [p.project_id for p in app.store.checkpoint().projects] == ["alpha"]
                )
            )

            assert not table.loading
            assert (
                row_key("issue", "I_alpha#1") in app.dashboard.issue_table.rows_by_key
            )

            collectors["beta"].source.release.set()
            await wait_until(
                lambda: (
                    [p.project_id for p in app.store.checkpoint().projects]
                    == ["alpha", "beta"]
                )
            )
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
    app, collectors = coordinated_app(tmp_path)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 1)
        await wait_until(lambda: not app.observations.in_flight)
        alpha_key = row_key("issue", "I_alpha#1")
        await wait_until(
            lambda: app.dashboard.issue_table.selected_row_key == alpha_key
        )
        calls = {name: c.source.calls for name, c in collectors.items()}
        pull_request_calls = {
            name: collector.pull_request_calls for name, collector in collectors.items()
        }

        await app.run_action("refresh")
        await wait_until(lambda: collectors["alpha"].source.calls == calls["alpha"] + 1)
        await wait_until(lambda: collectors["beta"].source.calls == calls["beta"] + 1)
        await wait_until(
            lambda: all(
                collector.pull_request_calls == pull_request_calls[name] + 1
                for name, collector in collectors.items()
            )
        )
        # The refresh restarts the pages too; the table is empty until the
        # restarted Issue page has landed and its one row is selected again.
        await wait_until(
            lambda: not app.observations.in_flight and observation_landed(app, 2)
        )
        await wait_until(lambda: table.row_count == 1)

        assert collectors["alpha"].target_calls == 2
        assert collectors["beta"].target_calls == 2
        assert app.dashboard.issue_table.selected_row_key == alpha_key


@pytest.mark.asyncio
async def test_one_failed_observation_kind_does_not_hide_the_other(
    tmp_path: Path,
) -> None:
    from dashpot.issue_sources import IssueSourceRefreshError

    app, collectors = coordinated_app(tmp_path)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 1)
        await wait_until(lambda: not app.observations.in_flight)
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
        # Each half lands on its own; wait for both to have been published,
        # and for the restarted pages behind them.
        await wait_until(
            lambda: (
                app.store.revision > revision
                and alpha_snapshot().issue_source_status == "stale"
                and alpha_snapshot().observation_targets[0].head == "fresh00"
                and first_load_landed(app)
            )
        )

        assert "GitHub is unavailable" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert alpha_snapshot().target_status == "fresh"
        assert table.row_count == 1
        assert not app.observations.errors


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "removed",
    (
        "#body",
        "#sessions-pane",
        "#sessions-pane FocusCursorTable",
        "#worktrees-pane FocusCursorTable",
        "#branches-pane FocusCursorTable",
        "#queue",
    ),
)
async def test_late_observation_is_dropped_after_dashboard_children_unmount(
    removed: str,
) -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await app.query_one(removed).remove()
        assert app.dashboard.is_mounted

        # A resume callback can outlive the dashboard's child panes.
        resumed = asyncio.Event()
        app.dashboard.post_message(events.ScreenResume())
        app.dashboard.call_later(lambda: app.dashboard.call_after_refresh(resumed.set))
        await wait_until(resumed.is_set)

        ticket = ObservationTicket(ObservationKey("issues", "project:test-repo"), 99)
        app.on_observation_finished(
            ObservationFinished(
                ticket,
                "timer",
                outcome=ObservationOutcome(ticket, accepted=True),
            )
        )


def alert(app: DashpotApp) -> Static:
    return app.query_one("#alert", Static)


def alert_text(app: DashpotApp) -> str:
    return str(alert(app).render())


@pytest.mark.asyncio
async def test_alert_is_hidden_and_takes_no_space_when_healthy() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot, snapshot))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await app.run_action("refresh")
        await wait_until(lambda: observation_landed(app, 2))
        # The refresh redraws the alert; its region follows on the next layout.
        await wait_until(lambda: alert(app).region.height == 0)

        assert not alert(app).display
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
    app, collectors = coordinated_app(tmp_path, refresh_indicator_seconds=0.2)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 1)
        await wait_until(lambda: not app.observations.in_flight)
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
        await wait_until(lambda: not app.observations.in_flight)
        assert not alert(app).display


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ("shutdown-start", "dashboard-removed", "closed"))
async def test_queued_refresh_indicator_is_harmless_during_shutdown(
    delivery: str,
) -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    started = Event()
    release = Event()

    def collect() -> WorkspaceSnapshot:
        started.set()
        release.wait()
        return snapshot

    collector = SequenceCollector(snapshot)
    app = dashboard_app(collector, refresh_indicator_seconds=0.01)
    delayed_indicator = app.observations.show_refreshing
    close_all = app._close_all
    delivered = False

    def deliver() -> None:
        nonlocal delivered
        assert app.observations.in_flight
        assert not app.is_running
        with mock.patch.object(DashboardScreen, "update_alert") as redraw:
            delayed_indicator()
        # The runner still notes the keys in flight; the app draws nothing.
        redraw.assert_not_called()
        assert app.observations.indicator_timer is None
        delivered = True

    async def close_dashboard() -> None:
        # Textual has no public hook between shutdown starting and screen removal.
        if delivery == "shutdown-start":
            assert app.screen_stack
            deliver()
        await close_all()
        if delivery == "dashboard-removed":
            assert not app.screen_stack
            deliver()

    try:
        # Hold delivery after the real timer fires, even if shutdown stops it.
        with (
            mock.patch.object(collector, "refresh", side_effect=collect),
            mock.patch.object(app.observations, "show_refreshing") as queued_indicator,
            mock.patch.object(app, "_close_all", side_effect=close_dashboard),
        ):
            async with app.run_test(size=(80, 24)):
                await wait_until(started.is_set)
                await wait_until(lambda: queued_indicator.call_count == 1)
                assert app.observations.in_flight
                assert not app.observations.refreshing_visible

            assert not app.screen_stack
            if delivery == "closed":
                deliver()
            assert delivered
    finally:
        release.set()


@pytest.mark.asyncio
async def test_quick_refresh_never_flickers_the_indicator(tmp_path: Path) -> None:
    app, _collectors = coordinated_app(tmp_path, refresh_indicator_seconds=1.0)

    async with app.run_test(size=(80, 24)):
        table = app.query_one("#queue", DataTable)
        await wait_until(lambda: table.row_count == 1)
        # The initial refresh settles first so its own indicator timer cannot
        # bleed into what the manual refresh is being measured for.
        await wait_until(lambda: not app.observations.in_flight)
        assert app.observations.indicator_timer is None

        # The refresh schedules its indicator timer while the spy is in
        # place, so a timer that fires is counted rather than raced against.
        with mock.patch.object(
            app.observations,
            "show_refreshing",
            wraps=app.observations.show_refreshing,
        ) as indicator:
            await app.run_action("refresh")
            await wait_until(lambda: not app.observations.in_flight)

            # A completed refresh stops the pending timer, so the indicator
            # callback never ran and nothing was ever shown to flicker.
            assert indicator.call_count == 0
        assert not alert(app).display
        assert app.observations.indicator_timer is None


@pytest.mark.asyncio
async def test_refresh_failure_is_a_persistent_alert_that_recovers() -> None:
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    collector = SequenceCollector(
        snapshot,
        RuntimeError("GitHub is unavailable"),
        RuntimeError("GitHub is unavailable"),
        snapshot,
    )
    app = dashboard_app(collector)

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await wait_until(lambda: not app.observations.in_flight)
        await app.run_action("refresh")
        # The alert reads the failure as soon as the observation lands; the
        # toast follows once its message is handled, so the wait covers both.
        await wait_until(
            lambda: (
                alert_text(app) == "✖ Refresh failed: Test Repository"
                and len(app._notifications) == 1
            )
        )

        assert alert(app).has_class("-error")

        # A repeated identical failure keeps the alert without another toast.
        # Wait for the observation to actually run and settle: requesting the
        # next refresh too early would coalesce onto it and rerun once.
        await app.run_action("refresh")
        await wait_until(
            lambda: collector.calls == 3 and not app.observations.in_flight
        )
        assert len(app._notifications) == 1
        assert alert(app).display

        await app.run_action("refresh")
        await wait_until(lambda: not alert(app).display)

        assert not app.observations.errors
        assert "GitHub is unavailable" not in str(
            app.query_one("#diagnostics", Static).render()
        )


@pytest.mark.asyncio
async def test_simultaneous_states_share_one_line_in_priority_order() -> None:
    stale = with_first_target(
        workspace_snapshot(issue("test/repo#1", "First"), status="stale"),
        availability="unavailable",
    )
    app = dashboard_app(SequenceCollector(stale, RuntimeError("boom")))

    async with app.run_test(size=(80, 24)):
        await wait_until(lambda: first_load_landed(app))
        await wait_until(lambda: alert(app).display)
        assert alert_text(app).startswith(
            "⚠ Unavailable worktrees: Test Repository /repo"
        )

        await app.run_action("refresh")
        await wait_until(
            lambda: (
                "✖ Refresh failed" in alert_text(app)
                and "Unavailable Issues" not in alert_text(app)
            )
        )

        assert alert(app).has_class("-error")
        text = alert_text(app)
        assert text.index("✖ Refresh failed") < text.index("⚠ Unavailable worktrees")
        assert text.index("⚠ Unavailable worktrees") < text.index("⚠ Stale Issues")
        await wait_until(lambda: alert(app).region.height == 1)
        assert "boom" in str(app.query_one("#diagnostics", Static).render())


@pytest.mark.asyncio
async def test_alert_stays_one_line_in_a_compact_terminal() -> None:
    stale = workspace_snapshot(issue("test/repo#1", "First"), status="stale")
    fresh = workspace_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(stale, fresh))

    async with app.run_test(size=(60, 18)):
        assert app.screen.has_class("-compact")
        await wait_until(lambda: first_load_landed(app))
        await wait_until(lambda: alert(app).display)

        await wait_until(lambda: alert(app).region.height == 1)
        assert alert(app).region.width == 60
        assert_panes_stack_above_full_width_queue(app)

        serve_snapshot(app, fresh)
        await app.run_action("refresh")
        await wait_until(lambda: not alert(app).display)
        await wait_until(lambda: alert(app).region.height == 0)
