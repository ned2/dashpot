"""The page runner queues one query per key and publishes with a revision bump."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from textual.message import Message

from app_harness import SnapshotQuerySource, issue, workspace_snapshot
from dashpot.core.event_log import EventLog
from dashpot.core.model import Diagnostic
from dashpot.core.runtime_events import ProcessIdentity, QueryAttributes, SpanEnded
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.queries.source_queries import QUERY_SOURCE_KEYS, QueryRequest
from dashpot.ui.messages import IdentitiesFinished, PageFinished
from dashpot.ui.page_runner import PageRunner
from dashpot.ui.refresh_spans import Refresh


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


# --- Refresh spans ---------------------------------------------------------


def spanned_runner() -> tuple[PageRunner, FakeHost, EventLog]:
    log = EventLog(
        None,
        identity=ProcessIdentity(run_id="0" * 32, kind="dashboard"),
        level="full",
        facts=lambda: pytest.fail("no process.start is recorded"),
        keep_recent=1000,
    )
    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    host = FakeHost()
    sources = {key: SnapshotQuerySource(snapshot) for key in QUERY_SOURCE_KEYS}
    pages = PageRunner(sources, PagedObservationStore(snapshot), host, event_log=log)
    return pages, host, log


def query_spans(log: EventLog) -> list[SpanEnded]:
    return [
        event.body
        for event in log.recent
        if isinstance(event.body, SpanEnded) and event.body.span_name == "query"
    ]


def outcomes(spans: list[SpanEnded]) -> list[tuple[str, str | None]]:
    return [
        (span.attributes.key, span.attributes.outcome)
        for span in spans
        if isinstance(span.attributes, QueryAttributes)
    ]


def test_a_query_no_refresh_asked_for_is_a_root_span() -> None:
    pages, host, log = spanned_runner()
    pages.submit("issues", query="First")
    landed = host.pop_call("issues").land()
    assert isinstance(landed, PageFinished)

    pages.finish_page(landed)

    (span,) = query_spans(log)
    assert span.parent_span_id is None
    assert (span.status, span.attributes) == (
        "OK",
        QueryAttributes(key="issues", outcome="landed"),
    )


def test_a_queued_request_that_is_replaced_is_dropped() -> None:
    pages, host, log = spanned_runner()
    pages.submit("issues", query="First")
    running = host.pop_call("issues")
    pages.submit("issues", query="Second")
    pages.submit("issues", query="Sec")
    assert outcomes(query_spans(log)) == [("issues", "dropped")]

    stale = running.land()
    assert isinstance(stale, PageFinished)
    pages.finish_page(stale)
    latest = host.pop_call("issues").land()
    assert isinstance(latest, PageFinished)
    pages.finish_page(latest)

    assert outcomes(query_spans(log)) == [
        ("issues", "dropped"),
        ("issues", "superseded"),
        ("issues", "landed"),
    ]


def test_a_refresh_tick_skips_a_busy_key_and_ends_with_its_last_query() -> None:
    pages, host, log = spanned_runner()
    first = Refresh(log, "github")
    pages.refresh(restart=False, refresh=first)
    first.seal()
    running = {
        key: host.pop_call(key) for key in QUERY_SOURCE_KEYS if key != "identities"
    }

    tick = Refresh(log, "github")
    pages.refresh(restart=False, refresh=tick)
    tick.seal()
    assert tick.ended
    assert not first.ended

    for call in running.values():
        landed = call.land()
        assert isinstance(landed, PageFinished)
        pages.finish_page(landed)
    assert first.ended

    by_parent = {
        refresh.span.span_id: sorted(
            outcomes(
                [
                    span
                    for span in query_spans(log)
                    if span.parent_span_id == refresh.span.span_id
                ]
            )
        )
        for refresh in (first, tick)
    }
    assert by_parent == {
        first.span.span_id: [("issues", "landed"), ("pull-requests", "landed")],
        tick.span.span_id: [("issues", "skipped"), ("pull-requests", "skipped")],
    }


def test_the_identities_a_refresh_asks_for_end_under_it() -> None:
    pages, host, log = spanned_runner()
    refresh = Refresh(log, "manual")
    pages.request_identities(("I_test/repo#1",), refresh=refresh)
    refresh.seal()
    host.pop_call("identities")

    pages.finish_identities(IdentitiesFinished(error="boom"))

    assert refresh.ended
    (span,) = query_spans(log)
    assert span.parent_span_id == refresh.span.span_id
    assert span.attributes == QueryAttributes(key="identities", outcome="landed")


def test_a_queued_request_keeps_the_refresh_that_asked_for_it() -> None:
    pages, host, log = spanned_runner()
    first = Refresh(log, "initial")
    pages.request_page("issues", pages.navigation["issues"].refresh(), refresh=first)
    first.seal()
    running = host.pop_call("issues")
    pressed = Refresh(log, "manual")
    pages.refresh(restart=True, refresh=pressed)
    pressed.seal()

    # The first refresh's answer releases the request the press queued.
    stale = running.land()
    assert isinstance(stale, PageFinished)
    pages.finish_page(stale)
    assert first.ended
    assert not pressed.ended
    latest = host.pop_call("issues").land()
    assert isinstance(latest, PageFinished)
    pages.finish_page(latest)
    pages.finish_page(_landed(host.pop_call("pull-requests")))

    assert pressed.ended

    def under(refresh: Refresh) -> list[tuple[str, str | None]]:
        spans = query_spans(log)
        children = [
            span for span in spans if span.parent_span_id == refresh.span.span_id
        ]
        return sorted(outcomes(children))

    assert under(first) == [("issues", "superseded")]
    assert under(pressed) == [("issues", "landed"), ("pull-requests", "landed")]


def _landed(call: QueryCall) -> PageFinished:
    message = call.land()
    assert isinstance(message, PageFinished)
    return message
