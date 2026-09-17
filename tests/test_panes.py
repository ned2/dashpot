"""The pane specs and their rows sources, without a running app."""

from __future__ import annotations

from datetime import UTC, datetime

import factories
from app_harness import NOW, SnapshotQuerySource, issue, workspace_snapshot
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.observation.related_rows import RelatedRows
from dashpot.queries.page_navigation import PageNavigation
from dashpot.queries.source_queries import QueryRequest, ResourceKind
from dashpot.ui.item_filter import ItemFilterBar
from dashpot.ui.panes import (
    LIST_PANE_SPECS,
    PaneContext,
    branch_pane_rows,
    pull_request_filter_bar,
    pull_request_pane_rows,
    session_pane_rows,
    worktree_pane_rows,
)

REFRESHED_AT = datetime.fromisoformat(NOW).astimezone(UTC)


def context(
    store: PagedObservationStore, navigation: PageNavigation | None = None
) -> PaneContext:
    paged: dict[ResourceKind, PageNavigation] = {}
    if navigation is not None:
        paged["pull-requests"] = navigation
    return PaneContext(store, paged, dark=True, now=REFRESHED_AT)


def test_every_pane_is_declared_once_with_its_own_identities() -> None:
    pane_ids = [spec.pane_id for spec in LIST_PANE_SPECS]
    table_ids = [spec.table_id for spec in LIST_PANE_SPECS]
    assert len(set(pane_ids)) == len(pane_ids)
    assert len(set(table_ids)) == len(table_ids)
    for spec in LIST_PANE_SPECS:
        # Controls and their height come together, as the pane requires.
        assert (spec.controls is None) == (spec.controls_height == 0)
        # A pane in relationship emphasis names the columns that show it.
        assert (spec.related is None) == (not spec.related_columns)


def test_related_specs_pick_their_own_relationship_set() -> None:
    related = RelatedRows(
        worktrees=frozenset({"w"}),
        branches=frozenset({"b"}),
        issues=frozenset({"i"}),
        sessions=frozenset({"s"}),
    )
    picked = {
        spec.pane_id: spec.related(related)
        for spec in LIST_PANE_SPECS
        if spec.related is not None
    }
    assert picked == {
        "sessions-pane": {"s"},
        "worktrees-pane": {"w"},
        "branches-pane": {"b"},
    }


def test_list_pane_rows_carry_the_records_they_were_built_from() -> None:
    run = factories.agent_run("one", target_path="/repo")
    store = PagedObservationStore(
        workspace_snapshot(issue("test/repo#1", "First"), runs=[run])
    )
    sessions = session_pane_rows(context(store))
    worktrees = worktree_pane_rows(context(store))
    branches = branch_pane_rows(context(store))
    assert [row.key for row in sessions.rows] == [
        record.key for record in sessions.records
    ]
    assert sessions.records == store.query_sessions().rows
    assert worktrees.records == store.query_worktrees().rows
    assert branches.records == store.query_branches().rows
    assert sessions.columns is not None
    assert branches.note is not None


def test_pull_request_pane_lists_the_accepted_page_with_its_count() -> None:
    snapshot = workspace_snapshot(
        pull_requests=(factories.pull_request(1), factories.pull_request(2))
    )
    store = PagedObservationStore(snapshot)
    navigation = PageNavigation(QueryRequest(kind="pull-requests"))
    loading = pull_request_pane_rows(context(store, navigation))
    assert loading.rows == ()
    assert loading.empty_message == "Loading page"
    assert loading.filter_count is None
    assert loading.records == ()

    source = SnapshotQuerySource(snapshot)
    page = source.query_page(navigation.request)
    assert navigation.accept(navigation.restart(), page)
    store.accept_page("pull-requests", page)
    store.accept_totals(source.totals("pull-requests"))
    listed = pull_request_pane_rows(context(store, navigation))
    assert len(listed.rows) == 2
    assert listed.title_summary == "Open 2 · Closed 0"
    assert listed.note is not None and listed.note.startswith("2 shown · 2 matches")
    assert listed.filter_count is not None and listed.filter_count.startswith("2 ")
    assert listed.empty_message == "No matching Pull Requests"
    # Pull Request rows take no part in relationship emphasis.
    assert listed.records == ()


def test_pull_request_filter_bar_starts_from_the_default_query() -> None:
    bar = pull_request_filter_bar()
    assert isinstance(bar, ItemFilterBar)
    assert bar.item == "pull-request"
    assert bar.initial_status == "open"
    assert bar.initial_query == ""
