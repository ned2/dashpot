"""The Issue table controller's pure parts, without a running app."""

from __future__ import annotations

from dashpot.issue_table_controller import focused_source, issue_column_label
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.queries.source_queries import QueryRequest
from test_related_rows import records, related_snapshot


def test_column_label_shows_the_submitted_ordering_only_where_the_source_orders() -> (
    None
):
    ordered = QueryRequest(ordering="number:desc")
    assert str(issue_column_label("number", ordered, orderable=True)) == "# ↓"
    assert str(issue_column_label("number", ordered, orderable=False)) == "#"
    assert str(issue_column_label("title", ordered, orderable=True)) == "TITLE"
    ascending = QueryRequest(ordering="number:asc")
    assert str(issue_column_label("number", ascending, orderable=True)) == "# ↑"


def test_focused_source_finds_the_cursor_row_among_every_panes_records() -> None:
    store = WorkspaceObservationStore(related_snapshot())
    every = records(store)
    session = store.query_sessions().rows[0]
    branch = store.query_branches().rows[0]
    assert focused_source(session.key, every) == session
    assert focused_source(branch.key, every) == branch
    assert focused_source(None, every) is None
    assert focused_source('["pull-request","PR_1"]', every) is None
