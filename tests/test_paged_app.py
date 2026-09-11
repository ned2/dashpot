"""Exercise independently published query pages through Textual's public seam."""

import threading

import pytest

from dashpot.collect import ObservationCoordinator
from dashpot.model import RepositoryStateInventory, ResolvedProject
from dashpot.paged_app import PagedDashpotApp
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


def application(tmp_path):
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
        factory=lambda *args, **kwargs: LocalOnlyCollector(),
        agent_observer=lambda targets: ([], []),
    )
    sources = {
        key: markdown(tmp_path)
        for key in (
            "issues",
            "pull-requests",
            "totals:issues",
            "totals:pull-requests",
            "identities",
        )
    }
    app = PagedDashpotApp(coordinator, sources=sources, refresh_seconds=0)
    app.navigation["issues"].request = QueryRequest(page_size=1)
    return app


@pytest.mark.asyncio
async def test_first_page_navigation_and_submitted_text(tmp_path):
    app = application(tmp_path)
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.dashboard.queue_table().row_count == 1)
        assert app.navigation["issues"].page.issues[0].number == 1
        app.dashboard.queue_table().focus()
        await pilot.press("n")
        await wait_until(lambda: app.navigation["issues"].page.issues[0].number == 2)
        await pilot.press("p")
        await wait_until(lambda: app.navigation["issues"].page.issues[0].number == 1)
        search = app.dashboard.issue_filter_bar.search
        search.value = "Issue 3"
        await pilot.pause()
        assert app.navigation["issues"].request.query == ""
        search.focus()
        await pilot.press("enter")
        await wait_until(
            lambda: (
                app.navigation["issues"].page is not None
                and app.navigation["issues"].page.issues[0].number == 3
            ),
        )
        assert not app.paged_store.checkpoint().projects[0].snapshot.issues


@pytest.mark.asyncio
async def test_page_publishes_while_totals_are_delayed(tmp_path):
    app = application(tmp_path)
    started, release = threading.Event(), threading.Event()
    source = app.sources["totals:issues"]
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
            assert "issues" not in app.paged_store.totals
            assert app.paged_store.projects()[0].snapshot.target_status == "fresh"
            release.set()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_bound_issue_remains_visible_outside_query_and_opens_details(tmp_path):
    from dashpot.issue_view import IssueScreen
    from factories import agent_run

    app = application(tmp_path)
    project_id = app.sources["issues"].context.project_id
    run = agent_run(
        "run-140", project_id, issue_id="I_3", hint="issue-3", target_path=str(tmp_path)
    )
    app.scheduler.agent_observer = lambda targets: ([run], [])
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(
            lambda: (
                "I_3" in app.paged_store.resolved
                and app.navigation["issues"].page is not None
            )
        )
        assert app.navigation["issues"].page.issues[0].id == "I_1"
        assert app.paged_store.query_sessions().rows[0].issue.id == "I_3"
        app.dashboard.highlight_issue("I_3")
        await pilot.pause()
        assert isinstance(app.screen, IssueScreen)
        assert app.screen.issue.id == "I_3"
        assert app.paged_store.checkpoint().agent_runs[0].issue_id == "I_3"


@pytest.mark.asyncio
async def test_slow_user_query_outlasting_ticks_is_accepted(tmp_path):
    app = application(tmp_path)
    source = app.sources["issues"]
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
            generation = app.navigation["issues"].generation
            for _ in range(3):
                app.timer_refresh()
            assert app.navigation["issues"].generation == generation
            release.set()
            await wait_until(lambda: app.navigation["issues"].page is not None)
            assert app.navigation["issues"].page.status == "fresh"
            assert app.navigation["issues"].page.issues[0].number == 1
    finally:
        release.set()
