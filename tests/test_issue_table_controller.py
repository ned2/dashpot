"""The Issue table controller's pure parts, without a running app."""

from __future__ import annotations

from dashpot.queries.source_queries import QueryRequest
from dashpot.ui.issue_table_controller import issue_column_label


def test_column_label_shows_the_submitted_ordering_only_where_the_source_orders() -> (
    None
):
    ordered = QueryRequest(ordering="number:desc")
    assert str(issue_column_label("number", ordered, orderable=True)) == "# ↓"
    assert str(issue_column_label("number", ordered, orderable=False)) == "#"
    assert str(issue_column_label("title", ordered, orderable=True)) == "TITLE"
    ascending = QueryRequest(ordering="number:asc")
    assert str(issue_column_label("number", ascending, orderable=True)) == "# ↑"
