"""Check accepted history and generation behavior without remote requests."""

from datetime import UTC, datetime

from dashpot.queries.page_navigation import (
    ContinuationRefused,
    PageNavigation,
    PageQueryState,
    page_text,
)
from dashpot.queries.pages import QueryRequest
from test_query_pages import markdown

# ``page_text`` takes the time, but no assertion here depends on a page's age.
NOW = datetime(2026, 8, 27, 3, 0, 0, tzinfo=UTC)


def test_failed_navigation_preserves_original_page_request(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    page = source.query_page(first.request).page
    navigation.accept(first, page)
    next_ticket = navigation.next()
    assert next_ticket is not None
    navigation.accept(next_ticket, None, "expired continuation; restart")
    assert navigation.page == page
    assert navigation.page is not None
    assert navigation.page.request.cursor is None
    assert "restart" in (navigation.error or "")


def test_refresh_invalidates_forward_history_and_eviction_is_explicit(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1), capacity=2)
    ticket = navigation.refresh()
    navigation.accept(ticket, source.query_page(ticket.request).page)
    for _ in range(2):
        ticket = navigation.next()
        assert ticket is not None
        navigation.accept(ticket, source.query_page(ticket.request).page)
    navigation.previous()
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 2
    navigation.previous()
    assert navigation.error == "Earlier page evicted; restart from page one"
    assert len(navigation.history) == 2
    ticket = navigation.refresh()
    navigation.accept(ticket, source.query_page(ticket.request).page)
    assert len(navigation.history) == 1
    assert navigation.next() is not None


def test_superseded_completion_cannot_replace_new_query(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest())
    old = navigation.refresh()
    new = navigation.restart(QueryRequest(query="3"))
    assert not navigation.accept(old, source.query_page(old.request).page)
    assert navigation.accept(new, source.query_page(new.request).page)
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 3


def test_a_restart_keeps_showing_the_page_it_replaces_until_one_lands(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    shown = source.query_page(first.request).page
    navigation.accept(first, shown)

    # The history is forgotten at once; the shown page is not.
    restarted = navigation.restart(QueryRequest(query="3"))
    assert navigation.page is None
    assert navigation.shown == shown
    # A failed restart keeps showing it with its error, as a failed refresh
    # keeps its accepted page; a second restart keeps it too.
    assert navigation.accept(restarted, None, "Issue Source exploded")
    assert navigation.error == "Issue Source exploded"
    assert navigation.shown == shown
    again = navigation.restart()
    assert navigation.shown == shown

    landed = source.query_page(again.request).page
    assert navigation.accept(again, landed)
    assert navigation.shown == landed


def test_paging_without_an_accepted_page_refuses_without_an_error(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    navigation.accept(first, source.query_page(first.request).page)

    # A restart forgets the accepted page while its query is in flight: there
    # is nothing to page from yet, which is not the same as no next page.
    restarted = navigation.restart(QueryRequest(page_size=1, query="3"))
    assert navigation.next() is None
    navigation.previous()
    assert navigation.error is None
    assert page_text(navigation, NOW) == "Loading page"
    # Neither refusal supersedes the query, so its page still lands.
    assert navigation.accept(restarted, source.query_page(restarted.request).page)
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 3


def test_paging_after_a_failed_restart_keeps_its_error():
    navigation = PageNavigation(QueryRequest(page_size=1))
    restarted = navigation.restart()
    assert navigation.accept(restarted, None, "Issue Source exploded")
    assert navigation.next() is None
    navigation.previous()
    assert navigation.error == "Issue Source exploded"


def test_an_accepted_page_without_a_continuation_has_no_next_page(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest())
    ticket = navigation.refresh()
    page = source.query_page(ticket.request).page
    assert page is not None
    assert navigation.accept(ticket, page)
    assert navigation.next() is None
    assert navigation.error == "No next page"

    limited = page.model_copy(update={"continuation": "provider-limit"})
    assert navigation.accept(navigation.refresh(), limited)
    assert navigation.next() is None
    assert navigation.error == "Narrow the query to see more results"


def test_previous_on_page_one_supersedes_a_pending_next_page(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    navigation.accept(first, source.query_page(first.request).page)

    pending = navigation.next()
    assert pending is not None
    navigation.previous()
    assert navigation.error == "Already at first page"
    assert not navigation.accept(pending, source.query_page(pending.request).page)
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 1


def test_a_refused_continuation_restarts_but_page_one_cannot_be_refused_one(
    tmp_path,
):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    navigation.accept(first, source.query_page(first.request).page)
    second = navigation.next()
    assert second is not None
    navigation.accept(second, source.query_page(second.request).page)
    refused = ContinuationRefused("Continuation context changed or expired")

    restarted = navigation.refuse_continuation(navigation.refresh(), refused)
    assert restarted is not None and restarted.request.cursor is None
    assert navigation.page is None and navigation.error is None

    # Page one sends no continuation, so a refusal of it is a failure shown
    # as one rather than a restart that could repeat on every refresh.
    assert navigation.refuse_continuation(restarted, refused) is None
    assert navigation.error == refused.message
    assert navigation.generation == restarted.generation


def test_only_a_first_page_still_in_flight_is_loading(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    page = source.query_page(navigation.refresh().request).page

    assert PageQueryState(None, in_flight=True).loading
    # Before the first query starts, after it failed, and once a page is
    # shown, the table is drawn rather than the loading indicator.
    assert not PageQueryState(None).loading
    assert not PageQueryState(None, in_flight=True, failed_without_page=True).loading
    assert not PageQueryState(page, in_flight=True).loading
