"""The app over a local Markdown Query Source: its Query Pages, totals and identities.

The one suite that builds ``DashpotApp`` with the shipped coordinator rather
than the harness, so each kind's page is published independently and
through Textual's public seam.
"""

import threading
from datetime import UTC, datetime
from typing import override

import pytest
from textual.binding import Binding
from textual.widgets import Static

from app_harness import (
    SequenceCollector,
    SnapshotScheduler,
    dashboard_app,
    first_load_landed,
    issue,
    legend_keys_text,
    show_query_peer,
    workspace_snapshot,
)
from dashpot.core.model import RepositoryStateInventory, WorkspaceSnapshot
from dashpot.observation.collect import ObservationCoordinator
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.project.workspace import ResolvedProject
from dashpot.queries.page_navigation import PageNavigation, page_text, totals_text
from dashpot.queries.source_queries import QUERY_SOURCE_KEYS, QueryRequest
from dashpot.ui.app import DashpotApp
from dashpot.ui.legend import LegendScreen
from helpers import wait_until
from test_source_queries import markdown


class LocalOnlyCollector:
    def observe_targets(self):
        return RepositoryStateInventory(targets=(), diagnostics=())

    def observe_issues(self, **kwargs):
        raise AssertionError("dashboard must not enumerate Issues")

    def observe_pull_requests(self):
        raise AssertionError("dashboard must not enumerate Pull Requests")


def application(tmp_path, *, launcher_configuration=None, collector=None):
    source = markdown(tmp_path)
    context = source.context
    project = ResolvedProject(
        context.project_id,
        "Test",
        context.repository_id,
        (),
        (str(tmp_path),),
        str(tmp_path),
    )
    coordinator = ObservationCoordinator(
        [project],
        query_driven=True,
        factory=lambda *args, **kwargs: collector or LocalOnlyCollector(),
        agent_observer=lambda targets: ([], []),
    )
    sources = {key: markdown(tmp_path) for key in QUERY_SOURCE_KEYS}
    app = DashpotApp(
        coordinator,
        sources=sources,
        refresh_seconds=0,
        launcher_configuration=launcher_configuration,
    )
    app.queries.navigation["issues"].request = QueryRequest(page_size=1)
    return app


@pytest.mark.asyncio
async def test_first_page_navigation_and_submitted_text(tmp_path):
    app = application(tmp_path)
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.query_screen.queue_table().row_count == 1)
        await show_query_peer(app, pilot)
        assert app.queries.navigation["issues"].page.issues[0].number == 1
        app.query_screen.queue_table().focus()
        await pilot.press("n")
        await wait_until(
            lambda: app.queries.navigation["issues"].page.issues[0].number == 2
        )
        # Restarting begins a new generation at page one instead of stepping back
        # through history.
        await pilot.press("g")
        await wait_until(
            lambda: (
                app.queries.navigation["issues"].page is not None
                and app.queries.navigation["issues"].page.issues[0].number == 1
            ),
        )
        assert len(app.queries.navigation["issues"].history) == 1
        await pilot.press("n")
        await wait_until(
            lambda: app.queries.navigation["issues"].page.issues[0].number == 2
        )
        await pilot.press("p")
        await wait_until(
            lambda: app.queries.navigation["issues"].page.issues[0].number == 1
        )
        await pilot.press("p")
        await wait_until(
            lambda: (
                "Already at first page"
                in str(app.query_screen.query_one("#issue-count", Static).render())
            )
        )
        search = app.query_screen.issue_filter_bar.search
        search.value = "Issue 3"
        await pilot.pause()
        assert app.queries.navigation["issues"].request.query == ""
        search.focus()
        await pilot.press("enter")
        await wait_until(
            lambda: (
                app.queries.navigation["issues"].page is not None
                and app.queries.navigation["issues"].page.issues[0].number == 3
            ),
        )
        assert not app.store.checkpoint().projects[0].snapshot.issues


def test_page_text_reports_the_provider_limit_and_a_navigation_error(tmp_path):
    navigation = PageNavigation(QueryRequest(page_size=1))
    page = markdown(tmp_path).query_page(navigation.request)
    limited = page.model_copy(update={"matched_count": 2000, "result_limit": 1000})
    assert navigation.accept(navigation.restart(), limited)

    # A fixed instant, like the sibling age test: nothing here reads the age,
    # and a frozen clock keeps that true if one of these pages ever goes stale.
    now = datetime(2026, 8, 27, 3, 0, 0, tzinfo=UTC)
    text = page_text(navigation, now)
    assert text.startswith("1 shown · 2000 matches · fresh")
    assert text.endswith(" · first 1,000 accessible; narrow query")

    navigation.previous()
    assert page_text(navigation, now).endswith(" · Already at first page")


def test_page_text_dates_a_stale_page_and_leaves_a_fresh_one_undated(tmp_path):
    """Only retained records carry an age, as an age inline and exact in full."""
    navigation = PageNavigation(QueryRequest(page_size=1))
    page = markdown(tmp_path).query_page(navigation.request)
    now = datetime(2026, 8, 27, 3, 0, 0, tzinfo=UTC)
    observed = "2026-08-27T00:00:00Z"

    # A fresh page was answered by the attempt that just landed, so its own
    # observation says nothing its status has not; both details agree.
    assert navigation.accept(navigation.restart(), page)
    fresh = page_text(navigation, now)
    assert fresh.endswith(" · fresh")
    assert page_text(navigation, now, detail="exact") == fresh

    # A stale page is retained records, and how old they are is the fact to
    # report: a reader's age inline, the observation itself where there is room.
    stale = page.model_copy(update={"status": "stale", "last_good_at": observed})
    assert navigation.accept(navigation.restart(), stale)
    assert page_text(navigation, now).endswith(" · stale · observed 3h ago")
    assert page_text(navigation, now, detail="exact").endswith(
        f" · stale · observed {observed}"
    )
    # The narrow form keeps the status and drops the observation entirely.
    assert page_text(navigation, now, detail="compact").endswith(" · stale")


def test_totals_text_marks_stale_totals_and_never_substitutes_zero(tmp_path):
    totals = markdown(tmp_path).totals("issues")
    assert totals_text(totals) == "Open 3 · Closed 0"
    stale = totals.model_copy(update={"status": "stale"})
    assert totals_text(stale) == "Open 3 · Closed 0 · stale totals"
    assert totals_text(None) == "Open ? · Closed ? · totals unavailable"


@pytest.mark.asyncio
async def test_the_legend_lists_the_shipped_screen_and_worktree_keys(tmp_path):
    app = application(tmp_path)
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.query_screen.queue_table().row_count == 1)
        await pilot.press("question_mark")
        await pilot.pause()

        legend = app.screen
        assert isinstance(legend, LegendScreen)
        rendered = legend_keys_text(app)
        listed = {
            (binding.key, binding.description)
            for group in legend.legend_keys
            for binding in Binding.make_bindings(group.bindings)
        }

    # The paging keys belong to the screen that actually runs, the Worktrees
    # table binds its own, and the focus cycle is an override with no
    # Binding; the Legend must omit none of them.
    for key, description in (
        ("n", "Next page"),
        ("p", "Previous page"),
        ("g", "First page"),
        ("enter", "Open Worktree"),
        ("y", "Copy path"),
        ("tab", "Next list"),
        ("shift+tab", "Previous list"),
    ):
        assert (key, description) in listed
        assert description in rendered


@pytest.mark.asyncio
async def test_page_publishes_while_totals_are_delayed(tmp_path):
    app = application(tmp_path)
    started, release = threading.Event(), threading.Event()
    source = app.queries.sources["totals:issues"]
    totals = source.totals

    def delayed(kind):
        started.set()
        release.wait(5)
        return totals(kind)

    source.totals = delayed
    try:
        async with app.run_test(size=(150, 55)):
            await wait_until(
                lambda: (
                    started.is_set() and app.query_screen.queue_table().row_count == 1
                ),
            )
            assert "issues" not in app.store.totals
            assert app.store.projects()[0].snapshot.target_status == "fresh"
            release.set()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_pending_repository_state_does_not_report_unavailable(tmp_path):
    started, release = threading.Event(), threading.Event()

    class HeldTargetCollector(LocalOnlyCollector):
        @override
        def observe_targets(self):
            started.set()
            release.wait(5)
            return super().observe_targets()

    app = application(tmp_path, collector=HeldTargetCollector())
    try:
        async with app.run_test(size=(150, 55)) as pilot:
            await wait_until(
                lambda: (
                    started.is_set()
                    and app.queries.navigation["issues"].page is not None
                )
            )
            await pilot.pause()

            rendered = str(app.dashboard.query_one("#alert", Static).render())
            assert "Unavailable worktrees and branches" not in rendered
    finally:
        release.set()


@pytest.mark.asyncio
async def test_failing_source_query_reports_its_error_and_keeps_the_app_running(
    tmp_path,
):
    app = application(tmp_path)
    # Square brackets, as a Pydantic validation error or a quoted identifier
    # would carry them: the text must render as typed, not parse as markup.
    error = "Issue Source exploded [type=value_error]"

    def failing(request):
        raise RuntimeError(error)

    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.query_screen.queue_table().row_count == 1)
        await show_query_peer(app, pilot)
        app.queries.sources["issues"].query_page = failing
        app.query_screen.queue_table().focus()
        await pilot.pause()
        app.query_screen.action_restart_page()
        await wait_until(lambda: app.queries.navigation["issues"].error == error)
        await pilot.pause()
        assert app.is_running
        assert app.queries.navigation["issues"].page is None
        assert str(app.query_screen.query_one("#issue-count", Static).render()) == error
        # The page the failed restart replaced stays on screen with the error.
        assert app.query_screen.queue_table().row_count == 1


@pytest.mark.asyncio
async def test_slow_user_query_outlasting_ticks_is_accepted(tmp_path):
    app = application(tmp_path)
    source = app.queries.sources["issues"]
    query_page = source.query_page
    started, release = threading.Event(), threading.Event()

    def delayed(request):
        started.set()
        release.wait(5)
        return query_page(request)

    source.query_page = delayed
    try:
        async with app.run_test(size=(150, 55)):
            await wait_until(started.is_set)
            generation = app.queries.navigation["issues"].generation
            for _ in range(3):
                app.timer_refresh()
            assert app.queries.navigation["issues"].generation == generation
            release.set()
            await wait_until(lambda: app.queries.navigation["issues"].page is not None)
            assert app.queries.navigation["issues"].page.status == "fresh"
            assert app.queries.navigation["issues"].page.issues[0].number == 1
    finally:
        release.set()


@pytest.mark.asyncio
async def test_startup_observes_a_snapshot_collector_exactly_once():
    # Exactly one initial observation must come out of ``on_ready``, or a
    # second lands on a collector with nothing more to give and fails the
    # refresh.
    collector = SequenceCollector(workspace_snapshot(issue("test/repo#1", "First")))
    app = dashboard_app(collector, refresh_seconds=0)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        assert collector.calls == 1
        assert not app.observations.pending_rerun
        assert app.observations.errors == {}
        assert app.query_screen.queue_table().row_count == 1
        assert app.store.query_issues().rows[0].issue.reference == "test/repo#1"


def test_snapshot_scheduler_publishes_a_whole_checkpoint_once() -> None:
    snapshot = WorkspaceSnapshot(
        collected_at="2026-08-28T00:00:00Z", elapsed_ms=1, projects=[]
    )

    class Collector:
        def refresh(self) -> WorkspaceSnapshot:
            return snapshot

    scheduler = SnapshotScheduler(Collector())
    store = WorkspaceObservationStore()
    (old,) = scheduler.request(scheduler.keys())
    (new,) = scheduler.request(scheduler.keys())

    assert not scheduler.observe(old).accepted
    assert scheduler.publish(store) == []
    assert scheduler.observe(new).accepted
    assert len(scheduler.publish(store)) == 1
    assert scheduler.publish(store) == []
    assert store.checkpoint().collected_at == "2026-08-28T00:00:00Z"
