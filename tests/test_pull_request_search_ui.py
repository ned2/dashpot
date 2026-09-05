"""Submitted GitHub searches through the public Textual seam."""

from __future__ import annotations

import threading

import pytest
from textual.widgets import Input, Select, Static

import factories
from app_harness import SequenceCollector, pane_subtitle, pane_title, workspace_snapshot
from dashpot.app import DashpotApp
from dashpot.observation_store import WorkspaceObservationStore
from helpers import wait_until


class Searcher:
    def __init__(self, *answers):
        self.answers = iter(answers)
        self.calls = []

    def __call__(self, project, text):
        self.calls.append((project.project_id, text))
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_app(searcher):
    snapshot = workspace_snapshot(
        pull_requests=(factories.pull_request(1, title="Observed"),)
    )
    return DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
        pull_request_searcher=searcher,
    )


@pytest.mark.asyncio
async def test_enter_submits_full_query_and_lifecycle_filters_preserve_server_order():
    searcher = Searcher(
        (
            factories.pull_request(3, title="Remote merged", state="merged"),
            factories.pull_request(2, title="Remote draft", is_draft=True),
            factories.pull_request(4, title="Remote open"),
        )
    )
    app = make_app(searcher)
    async with app.run_test(size=(140, 40)) as pilot:
        search = app.query_one("#pull-request-search", Input)
        pane = app.dashboard.pull_requests_pane()
        query = '(label:"bug fix" OR author:@me) comments:>=2 sort:reactions'
        search.value = query
        await pilot.pause()
        assert searcher.calls == []
        assert "Observed" in str(pane.table.get_row_at(0)[2])
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 2)
        assert searcher.calls[0][1] == query
        assert [str(pane.table.get_row_at(i)[1]) for i in range(2)] == ["2", "4"]
        assert (
            pane_title(app, "#pull-requests-pane")
            == "PULL REQUESTS · Open 2 · Closed 1"
        )
        assert (
            str(app.query_one("#pull-request-count", Static).render())
            == "2 pull requests"
        )
        assert (
            app.store.checkpoint().projects[0].snapshot.pull_requests[0].title
            == "Observed"
        )

        app.query_one("#pull-request-state", Select).value = "all"
        await wait_until(lambda: pane.table.row_count == 3)
        assert [str(pane.table.get_row_at(i)[1]) for i in range(3)] == ["3", "2", "4"]
        assert len(searcher.calls) == 1
        search.value = ""
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 1)
        assert "Observed" in str(pane.table.get_row_at(0)[2])
        assert len(searcher.calls) == 1


@pytest.mark.asyncio
async def test_search_failure_retains_only_same_query_and_recovers():
    searcher = Searcher(
        (factories.pull_request(2, title="Last good"),),
        RuntimeError("offline"),
        RuntimeError("offline"),
        (factories.pull_request(3, title="Recovered"),),
    )
    app = make_app(searcher)
    async with app.run_test(size=(140, 40)) as pilot:
        search = app.query_one("#pull-request-search", Input)
        pane = app.dashboard.pull_requests_pane()
        search.value = "label:bug"
        search.focus()
        await pilot.press("enter")
        await wait_until(lambda: "Last good" in str(pane.table.get_row_at(0)[2]))
        await pilot.press("enter")
        await wait_until(lambda: bool(app.dashboard.pull_request_search_diagnostics))
        assert "Last good" in str(pane.table.get_row_at(0)[2])
        assert pane_subtitle(app, "#pull-requests-pane").startswith("stale")
        assert "offline" in str(app.query_one("#diagnostics", Static).render())

        search.value = "label:new"
        await pilot.press("enter")
        await wait_until(
            lambda: len(searcher.calls) == 3 and not app.pull_request_search_running
        )
        assert pane.table.row_count == 0
        assert pane_title(app, "#pull-requests-pane") == "PULL REQUESTS · unavailable"
        await pilot.press("enter")
        await wait_until(lambda: pane.table.row_count == 1)
        assert "Recovered" in str(pane.table.get_row_at(0)[2])
        assert app.dashboard.pull_request_search_diagnostics == ()
        assert (
            app.store.checkpoint().projects[0].snapshot.issue_source_status == "fresh"
        )


@pytest.mark.asyncio
async def test_superseded_query_never_publishes_and_searches_are_serialized():
    started = threading.Event()
    release = threading.Event()
    calls = []

    def searcher(project, text):
        calls.append(text)
        if text == "label:first":
            started.set()
            assert release.wait(10)
        return (factories.pull_request(2, title=text),)

    app = make_app(searcher)
    try:
        async with app.run_test(size=(140, 40)) as pilot:
            search = app.query_one("#pull-request-search", Input)
            pane = app.dashboard.pull_requests_pane()
            search.value = "label:first"
            search.focus()
            await pilot.press("enter")
            await wait_until(started.is_set)
            search.value = "label:second"
            await pilot.press("enter")
            search.value = "label:latest"
            await pilot.press("enter")
            assert calls == ["label:first"]
            assert pane.table.row_count == 0
            release.set()
            await wait_until(lambda: pane.table.row_count == 1)
            assert "label:latest" in str(pane.table.get_row_at(0)[2])
            assert calls == ["label:first", "label:latest"]
    finally:
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("preloaded", [False, True])
async def test_initial_query_runs_after_project_is_observed(preloaded):
    from dashpot.pull_request_list import PullRequestListQuery

    snapshot = workspace_snapshot(pull_requests=(factories.pull_request(1),))
    searcher = Searcher((factories.pull_request(2, title="Initial query"),))
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot) if preloaded else None,
        pull_request_searcher=searcher,
        pull_request_query=PullRequestListQuery(text="label:bug"),
    )
    async with app.run_test(size=(120, 40)):
        await wait_until(
            lambda: len(searcher.calls) == 1 and not app.pull_request_search_running
        )
        pane = app.dashboard.pull_requests_pane()
        assert "Initial query" in str(pane.table.get_row_at(0)[2])
