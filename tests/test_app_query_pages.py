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
from factories import agent_run
from helpers import wait_until
from test_source_queries import markdown


class LocalOnlyCollector:
    def observe_targets(self):
        return RepositoryStateInventory(targets=(), diagnostics=())

    def observe_issues(self, **kwargs):
        raise AssertionError("dashboard must not enumerate Issues")

    def observe_pull_requests(self):
        raise AssertionError("dashboard must not enumerate Pull Requests")


def application(
    tmp_path, *, launcher_configuration=None, collector=None, query_refresh_seconds=0
):
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
        query_refresh_seconds=query_refresh_seconds,
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
    page = markdown(tmp_path).query_page(navigation.request).page
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
    page = markdown(tmp_path).query_page(navigation.request).page
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
    totals = markdown(tmp_path).query_page(QueryRequest()).totals
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
                app.timer_query_refresh()
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


def count_queries(app):
    """Count each query key's requests to its Query Source."""
    counts = dict.fromkeys(QUERY_SOURCE_KEYS, 0)
    for key, source in app.queries.sources.items():
        for name in ("query_page", "resolve_identities"):
            method = getattr(source, name)

            def counted(*args, _key=key, _method=method, **kwargs):
                counts[_key] += 1
                return _method(*args, **kwargs)

            setattr(source, name, counted)
    return counts


def observe_agent_runs(app, runs):
    """Serve ``runs`` as the observed Agent Runs, recording each observation."""
    calls = []

    def observer(targets):
        calls.append(targets)
        return list(runs), []

    app.observations.scheduler.agent_observer = observer
    return calls


async def local_tick(app, observed):
    """Fire one local tick and wait until it and any query it caused land."""
    before = len(observed)
    app.timer_refresh()
    await wait_until(lambda: len(observed) > before and not app.observations.in_flight)
    await wait_until(lambda: not app.queries.busy)


@pytest.mark.asyncio
async def test_a_local_tick_observes_and_a_query_tick_queries(tmp_path):
    app = application(tmp_path)
    counts = count_queries(app)
    observed = observe_agent_runs(app, [])
    async with app.run_test(size=(150, 55)):
        await wait_until(lambda: first_load_landed(app) and bool(observed))
        await wait_until(lambda: not app.observations.in_flight)
        queried = dict(counts)

        await local_tick(app, observed)
        assert counts == queried

        ticks = len(observed)
        app.timer_query_refresh()
        await wait_until(lambda: counts["issues"] > queried["issues"])
        await wait_until(lambda: not app.queries.busy)
        assert counts == {
            **queried,
            "issues": queried["issues"] + 1,
            "pull-requests": queried["pull-requests"] + 1,
        }
        assert len(observed) == ticks


@pytest.mark.asyncio
async def test_the_query_period_requeries_without_observing(tmp_path):
    app = application(tmp_path, query_refresh_seconds=0.05)
    counts = count_queries(app)
    observed = observe_agent_runs(app, [])
    async with app.run_test(size=(150, 55)):
        # Queries that tick every 50ms are seldom all idle at once, so this
        # waits on the observation alone.
        await wait_until(lambda: bool(observed) and not app.observations.in_flight)
        runs = len(observed)
        queried = counts["issues"]

        await wait_until(lambda: counts["issues"] >= queried + 2)
        assert len(observed) == runs


@pytest.mark.asyncio
async def test_bound_issues_resolve_on_a_local_tick_only_when_they_change(tmp_path):
    app = application(tmp_path)
    project_id = app.queries.sources["issues"].context.project_id
    runs = []
    observed = observe_agent_runs(app, runs)
    resolved = []
    identities = app.queries.sources["identities"]
    resolve = identities.resolve_identities

    def recorded(requested):
        resolved.append(tuple(requested))
        return resolve(requested)

    identities.resolve_identities = recorded
    async with app.run_test(size=(150, 55)):
        await wait_until(lambda: first_load_landed(app) and bool(observed))
        await wait_until(lambda: not app.observations.in_flight)
        assert resolved == []

        # An Agent Run starting Issue work is resolved without waiting for
        # the next query refresh.
        runs.append(
            agent_run("one", project_id, issue_id="I_1", target_path=str(tmp_path))
        )
        await local_tick(app, observed)
        assert resolved == [("I_1",)]

        # The same bound Issues wait for the query refresh.
        await local_tick(app, observed)
        assert resolved == [("I_1",)]
        app.timer_query_refresh()
        await wait_until(lambda: len(resolved) == 2 and not app.queries.busy)
        assert resolved == [("I_1",), ("I_1",)]

        runs.append(
            agent_run("two", project_id, issue_id="I_2", target_path=str(tmp_path))
        )
        await local_tick(app, observed)
        assert resolved[2:] == [("I_1", "I_2")]
