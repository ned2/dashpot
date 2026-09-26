"""The page runner queues one query per key and publishes with a revision bump."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from textual.message import Message

from app_harness import SnapshotQuerySource, issue, workspace_snapshot
from dashpot.core.model import Diagnostic
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.queries.source_queries import QUERY_SOURCE_KEYS, QueryRequest
from dashpot.ui.messages import IdentitiesFinished, PageFinished
from dashpot.ui.page_runner import PageRunner


@dataclass
class QueryCall:
    """One query the runner asked the host to run, held until landed."""

    name: str
    group: str
    operation: Callable[[], object]
    on_done: Callable[[object | None, str | None], Message]

    def land(self, *, error: str | None = None) -> Message:
        return (
            self.on_done(None, error)
            if error is not None
            else self.on_done(self.operation(), None)
        )


class FakeHost:
    def __init__(self) -> None:
        self.calls: list[QueryCall] = []

    def run_off_loop(
        self,
        name: str,
        group: str,
        operation: Callable[[], object],
        on_done: Callable[[object | None, str | None], Message],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        assert executor is not None
        self.calls.append(QueryCall(name, group, operation, on_done))

    def pop_call(self, key: str) -> QueryCall:
        matching = [call for call in self.calls if call.group == f"query:{key}"]
        assert len(matching) == 1, [call.group for call in self.calls]
        self.calls.remove(matching[0])
        return matching[0]


def runner() -> tuple[PageRunner, PagedObservationStore, FakeHost]:
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"), issue("test/repo#2", "Second")
    )
    store = PagedObservationStore(snapshot)
    host = FakeHost()
    sources = {key: SnapshotQuerySource(snapshot) for key in QUERY_SOURCE_KEYS}
    return PageRunner(sources, store, host), store, host


def test_a_page_landing_changes_the_revision_the_read_models_report() -> None:
    pages, store, host = runner()
    before = store.query_issues().revision
    assert store.revision == 1
    assert "issues" not in store.pages

    pages.refresh(restart=True)
    # A page's own query counts its kind's Project Totals.
    assert pages.busy == {"issues", "pull-requests"}
    message = host.pop_call("issues").land()
    assert isinstance(message, PageFinished)
    pages.finish_page(message)
    assert set(store.totals) == {"issues"}
    assert store.totals["issues"].open_count == 2
    assert store.source_revision == 1
    pages.publish()

    assert "issues" not in pages.busy
    assert store.pages["issues"] is pages.navigation["issues"].page
    # The observation revision is untouched; the joined revision moved on.
    assert store.revision == 1
    assert store.source_revision == 2
    assert store.query_issues().revision == before + 2
    assert len(store.query_issues().rows) == 2
    # Landing and publishing the same page and totals again changes nothing.
    store.accept_totals(store.totals["issues"])
    pages.publish()
    assert store.source_revision == 2


def test_identities_land_with_a_revision_bump() -> None:
    pages, store, host = runner()
    pages.request_identities(("I_test/repo#1",))
    identities = host.pop_call("identities").land()
    assert isinstance(identities, IdentitiesFinished)
    pages.finish_identities(identities)
    assert "I_test/repo#1" in store.resolved
    assert store.source_revision == 1
    assert store.query_sessions().revision == store.revision + 1
    # Landing the same identities again changes nothing.
    store.accept_identities(tuple(store.resolved.values()))
    assert store.source_revision == 1


def test_what_the_sources_report_about_themselves_lands_once() -> None:
    pages, store, host = runner()
    low = Diagnostic(
        source="github",
        severity="warning",
        code="github-rate-limit-low",
        message="GitHub GraphQL rate limit is low: 400 of 5000 points remain",
    )
    # Sources sharing one reading report the same warning; it is one line.
    for source in pages.sources.values():
        assert isinstance(source, SnapshotQuerySource)
        source.warnings = (low,)
    pages.request_identities(("I_test/repo#1",))
    identities = host.pop_call("identities").land()
    assert isinstance(identities, IdentitiesFinished)
    pages.finish_identities(identities)
    assert [entry.diagnostic for entry in store.diagnostics()].count(low) == 1
    assert store.source_revision == 2

    # A query that failed as a whole still lands what the sources now report.
    for source in pages.sources.values():
        assert isinstance(source, SnapshotQuerySource)
        source.warnings = ()
    pages.refresh(restart=True)
    failed = host.pop_call("issues").land(error="boom")
    assert isinstance(failed, PageFinished)
    pages.finish_page(failed)
    assert low not in [entry.diagnostic for entry in store.diagnostics()]
    assert store.source_revision == 3


def test_a_failed_query_frees_its_key_without_a_store_write() -> None:
    pages, store, host = runner()
    pages.request_identities(("I_test/repo#1",))
    host.pop_call("identities")
    pages.finish_identities(IdentitiesFinished(error="boom"))
    assert pages.busy == set()
    assert store.source_revision == 0

    pages.submit("issues", query="Second")
    failed = host.pop_call("issues").land(error="Issue Source exploded")
    assert isinstance(failed, PageFinished)
    pages.finish_page(failed)
    # A query that failed as a whole counted no Project Totals either.
    assert store.totals == {}
    assert pages.navigation["issues"].error == "Issue Source exploded"
    assert pages.navigation["issues"].page is None
    assert pages.page_states["issues"].failed_without_page

    pages.submit("issues", query="First")
    assert pages.page_states["issues"].in_flight
    assert pages.page_states["issues"].status == "unavailable"
    recovered = host.pop_call("issues").land()
    assert isinstance(recovered, PageFinished)
    pages.finish_page(recovered)
    assert not pages.page_states["issues"].failed_without_page


def test_a_request_for_a_busy_key_waits_and_only_the_latest_runs() -> None:
    pages, store, host = runner()
    pages.submit("issues", query="First")
    running = host.pop_call("issues")
    pages.submit("issues", query="Second")
    pages.submit("issues", query="Sec")
    assert host.calls == []
    assert set(pages.queued) == {"issues"}

    superseded = running.land()
    assert isinstance(superseded, PageFinished)
    pages.finish_page(superseded)
    # The stale ticket's page is rejected, but not the Project Totals it
    # counted; the latest submission runs next.
    assert pages.navigation["issues"].page is None
    assert store.totals["issues"].open_count == 2
    assert pages.page_states["issues"].in_flight
    latest = host.pop_call("issues").land()
    assert isinstance(latest, PageFinished)
    assert latest.ticket.request.query == "Sec"
    pages.finish_page(latest)
    assert pages.navigation["issues"].page is not None
    assert pages.navigation["issues"].page.issues[0].title == "Second"
    assert pages.queued == {}


def test_refresh_repeats_the_displayed_page_unless_its_query_is_running() -> None:
    pages, _store, host = runner()
    pages.refresh(restart=False)
    generation = pages.navigation["issues"].generation
    for key in QUERY_SOURCE_KEYS:
        if key != "identities":
            host.pop_call(key)
    # Every key is busy, so a tick asks nothing more and mints no generation.
    pages.refresh(restart=False)
    assert host.calls == []
    assert pages.queued == {}
    assert pages.navigation["issues"].generation == generation
    # A restart supersedes the running page query and waits its turn.
    pages.refresh(restart=True)
    assert pages.navigation["issues"].generation == generation + 1
    assert set(pages.queued) == {"issues", "pull-requests"}


def test_the_navigation_starts_from_each_kind_default_request() -> None:
    pages, _store, _host = runner()
    assert pages.navigation["issues"].request == QueryRequest(kind="issues")
    assert pages.navigation["pull-requests"].request == QueryRequest(
        kind="pull-requests"
    )
    pages.shutdown()
