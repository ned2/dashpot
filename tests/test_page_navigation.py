"""Check accepted history and generation behavior without remote requests."""

from dashpot.page_navigation import PageNavigation
from dashpot.source_queries import QueryRequest
from test_source_queries import markdown


def test_failed_navigation_preserves_original_page_request(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    page = source.query_page(first.request)
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
    navigation.accept(ticket, source.query_page(ticket.request))
    for _ in range(2):
        ticket = navigation.next()
        assert ticket is not None
        navigation.accept(ticket, source.query_page(ticket.request))
    navigation.previous()
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 2
    navigation.previous()
    assert "evicted" in (navigation.error or "")
    assert len(navigation.history) == 2
    ticket = navigation.refresh()
    navigation.accept(ticket, source.query_page(ticket.request))
    assert len(navigation.history) == 1
    assert navigation.next() is not None


def test_superseded_completion_cannot_replace_new_query(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest())
    old = navigation.refresh()
    new = navigation.restart(QueryRequest(query="3"))
    assert not navigation.accept(old, source.query_page(old.request))
    assert navigation.accept(new, source.query_page(new.request))
    assert navigation.page is not None
    assert navigation.page.issues[0].number == 3


def test_a_restart_keeps_showing_the_page_it_replaces_until_one_lands(tmp_path):
    source = markdown(tmp_path)
    navigation = PageNavigation(QueryRequest(page_size=1))
    first = navigation.refresh()
    shown = source.query_page(first.request)
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

    landed = source.query_page(again.request)
    assert navigation.accept(again, landed)
    assert navigation.shown == landed
