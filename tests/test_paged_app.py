"""Exercise independently published query pages through Textual's public seam."""

import threading

import pytest
from textual.binding import Binding
from textual.widgets import Static

from app_harness import (
    SequenceCollector,
    SnapshotScheduler,
    dashboard_app,
    first_load_landed,
    issue,
    workspace_snapshot,
)
from dashpot.app import DashpotApp
from dashpot.collect import ObservationCoordinator
from dashpot.legend import LegendScreen
from dashpot.model import RepositoryStateInventory, ResolvedProject, WorkspaceSnapshot
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.page_navigation import PageNavigation, page_text, totals_text
from dashpot.page_runner import QUERY_SOURCE_KEYS
from dashpot.source_queries import QueryRequest
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
        local_only=True,
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
        await wait_until(lambda: app.dashboard.queue_table().row_count == 1)
        assert app.queries.navigation["issues"].page.issues[0].number == 1
        app.dashboard.queue_table().focus()
        await pilot.press("n")
        await wait_until(
            lambda: app.queries.navigation["issues"].page.issues[0].number == 2
        )
        # Restarting begins a new generation at page one instead of stepping back
        # through history. (The focused table binds Home itself, so the action is
        # driven directly here.)
        app.dashboard.action_restart_page()
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
                in str(app.dashboard.query_one("#issue-count", Static).render())
            )
        )
        search = app.dashboard.issue_filter_bar.search
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

    text = page_text(navigation)
    assert text.startswith("1 shown · 2000 matches · fresh")
    assert text.endswith(" · first 1,000 accessible; narrow query")

    navigation.previous()
    assert page_text(navigation).endswith(" · Already at first page")


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
        await wait_until(lambda: app.dashboard.queue_table().row_count == 1)
        await pilot.press("question_mark")
        await pilot.pause()

        legend = app.screen
        assert isinstance(legend, LegendScreen)
        rendered = str(legend.query_one("#legend-keys", Static).render())
        listed = {
            binding.key: binding.description
            for binding in Binding.make_bindings(legend.legend_bindings)
        }

    # The paging keys belong to the screen that actually runs, and the
    # Worktrees table binds its own; the Legend must omit neither.
    for key, description in (
        ("n", "Next page"),
        ("p", "Previous page"),
        ("home", "First page"),
        ("enter", "Open Worktree"),
        ("y", "Copy path"),
    ):
        assert listed[key] == description
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
                lambda: started.is_set() and app.dashboard.queue_table().row_count == 1,
            )
            assert "issues" not in app.store.totals
            assert app.store.projects()[0].snapshot.target_status == "fresh"
            release.set()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_bound_issue_remains_visible_outside_query_and_opens_details(tmp_path):
    from dashpot.issue_view import IssueScreen
    from factories import agent_run

    app = application(tmp_path)
    project_id = app.queries.sources["issues"].context.project_id
    run = agent_run(
        "run-140", project_id, issue_id="I_3", hint="issue-3", target_path=str(tmp_path)
    )
    app.observations.scheduler.agent_observer = lambda targets: ([run], [])
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(
            lambda: (
                "I_3" in app.store.resolved
                and app.queries.navigation["issues"].page is not None
            )
        )
        assert app.queries.navigation["issues"].page.issues[0].id == "I_1"
        assert app.store.query_sessions().rows[0].issue.id == "I_3"
        app.dashboard.open_bound_issue("I_3")
        await pilot.pause()
        assert isinstance(app.screen, IssueScreen)
        assert app.screen.issue.id == "I_3"
        assert app.store.checkpoint().agent_runs[0].issue_id == "I_3"


@pytest.mark.asyncio
async def test_bound_issue_off_the_page_opens_once_its_identity_resolves(tmp_path):
    from dashpot.issue_view import IssueScreen
    from factories import agent_run

    app = application(tmp_path)
    source = app.queries.sources["identities"]
    project_id = source.context.project_id
    run = agent_run(
        "run-141", project_id, issue_id="I_3", hint="issue-3", target_path=str(tmp_path)
    )
    app.observations.scheduler.agent_observer = lambda targets: ([run], [])
    resolve_identities = source.resolve_identities
    release = threading.Event()

    def delayed(identities):
        release.wait(5)
        return resolve_identities(identities)

    # Hold identity resolution back so the bound Issue is off the page and
    # not yet resolved when it is opened.
    source.resolve_identities = delayed
    try:
        async with app.run_test(size=(150, 55)) as pilot:
            await wait_until(lambda: app.queries.navigation["issues"].page is not None)
            assert "I_3" not in app.store.resolved
            app.dashboard.open_bound_issue("I_3")
            await pilot.pause()
            assert not isinstance(app.screen, IssueScreen)
            assert app.open_when_resolved == "I_3"
            release.set()
            await wait_until(lambda: isinstance(app.screen, IssueScreen))
            assert app.screen.issue.id == "I_3"
            assert app.open_when_resolved is None
            assert [n.message for n in app._notifications] == [
                "Resolving bound Issue details"
            ]
    finally:
        release.set()


@pytest.mark.asyncio
async def test_failing_source_query_reports_its_error_and_keeps_the_app_running(
    tmp_path,
):
    app = application(tmp_path)
    source = app.queries.sources["issues"]

    def failing(request):
        raise RuntimeError("Issue Source exploded")

    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.dashboard.queue_table().row_count == 1)
        source.query_page = failing
        app.dashboard.action_restart_page()
        await wait_until(
            lambda: app.queries.navigation["issues"].error == "Issue Source exploded"
        )
        await pilot.pause()
        assert app.is_running
        assert app.queries.navigation["issues"].page is None
        assert (
            str(app.dashboard.query_one("#issue-count", Static).render())
            == "Issue Source exploded"
        )


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
        assert app.dashboard.queue_table().row_count == 1
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
