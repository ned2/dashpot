"""The Pull Requests pane read model and semantic rendering."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from rich.text import Text

import factories
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.observation.pull_request_list import PullRequestListQuery
from dashpot.ui.pull_request_cells import (
    APPROVED_GLYPH,
    CHECKS_FAILURE_GLYPH,
    CLOSED_GLYPH,
    CONFLICTING_GLYPH,
    DRAFT_GLYPH,
    MERGE_NOT_APPLICABLE_GLYPH,
    MERGED_GLYPH,
    build_pull_request_rows,
)
from helpers import snapshot_of

NOW = datetime(2026, 9, 4, 4, 0, tzinfo=UTC)


def snapshot(*pull_requests):
    project = factories.project(
        "project:one",
        pull_requests=pull_requests,
    )
    project_snapshot = snapshot_of(project).model_copy(
        update={"pull_request_attempted_at": "2026-09-04T04:00:00Z"}
    )
    return factories.workspace(
        project.model_copy(update={"snapshot": project_snapshot})
    )


def test_query_orders_by_update_then_number_and_keys_by_opaque_identity() -> None:
    older = factories.pull_request(
        9, pull_request_id="opaque/b", updated_at="2026-09-03T00:00:00Z"
    )
    newer_high = factories.pull_request(
        20, pull_request_id="opaque/a", updated_at="2026-09-04T00:00:00Z"
    )
    newer_low = factories.pull_request(
        2, pull_request_id="opaque/c", updated_at="2026-09-04T00:00:00Z"
    )

    result = WorkspaceObservationStore(
        snapshot(older, newer_high, newer_low)
    ).query_pull_requests()

    assert [row.pull_request.id for row in result.rows] == [
        "opaque/c",
        "opaque/a",
        "opaque/b",
    ]
    assert result.rows[0].key == '["pull-request","project:one","opaque/c"]'
    assert result.summary.status == "fresh"


def test_store_query_tracks_replacement_revision_and_rows() -> None:
    store = WorkspaceObservationStore(snapshot(factories.pull_request(7)))
    before = store.query_pull_requests()
    store.replace(snapshot(factories.pull_request(8)))
    after = store.query_pull_requests()

    assert before.revision == 1
    assert after.revision == store.revision == 2
    assert [row.pull_request.number for row in before.rows] == [7]
    assert [row.pull_request.number for row in after.rows] == [8]


def test_status_and_lexical_filters_preserve_the_complete_inventory_count() -> None:
    ready = factories.pull_request(1, title="Clipboard failure", author="alice")
    draft = factories.pull_request(2, title="Clipboard experiment", is_draft=True)
    observed = snapshot(ready, draft)

    result = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(text="clipboard alice draft:false")
    )

    assert [row.pull_request.number for row in result.rows] == [1]
    assert result.summary.matched_pull_request_count == 1
    assert result.summary.observed_pull_request_count == 2


def test_qualifiers_match_observed_pull_request_facts_with_github_semantics() -> None:
    matching = factories.pull_request(
        1,
        is_draft=True,
        head_branch="feature/search",
        base_branch="release",
        author="Alice",
        review_decision="changes-requested",
        check_status=None,
    )
    hidden = factories.pull_request(2, author="bob", check_status="success")
    observed = snapshot(matching, hidden)

    result = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(
            text="author:alice head:feature/search base:release is:draft review:changes_requested status:pending"
        )
    )

    assert [row.pull_request.number for row in result.rows] == [1]


def test_search_sort_qualifier_overrides_updated_first_order() -> None:
    created_first = factories.pull_request(
        1,
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-04T00:00:00Z",
    )
    created_last = factories.pull_request(
        2,
        created_at="2026-09-02T00:00:00Z",
        updated_at="2026-09-03T00:00:00Z",
    )
    observed = snapshot(created_first, created_last)

    default = WorkspaceObservationStore(observed).query_pull_requests()
    created = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(text="sort:created-asc")
    )

    assert [row.pull_request.number for row in default.rows] == [1, 2]
    assert [row.pull_request.number for row in created.rows] == [1, 2]
    descending = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(text="sort:created")
    )
    assert [row.pull_request.number for row in descending.rows] == [2, 1]


def test_rows_render_draft_review_checks_mergeability_and_age_in_both_themes() -> None:
    pull_request = factories.pull_request(
        83,
        is_draft=True,
        review_decision="approved",
        check_status="failure",
        mergeability="conflicting",
        updated_at="2026-09-04T03:00:00Z",
    )
    result = WorkspaceObservationStore(snapshot(pull_request)).query_pull_requests()

    dark_row = build_pull_request_rows(result, dark=True, now=NOW)[0]
    light_row = build_pull_request_rows(result, dark=False, now=NOW)[0]

    assert [str(cell) for cell in dark_row.cells] == [
        f"{DRAFT_GLYPH.symbol} draft",
        "83",
        "Add the feature",
        "feature-83",
        "main",
        "ned",
        f"{APPROVED_GLYPH.symbol} approved",
        f"{CHECKS_FAILURE_GLYPH.symbol} failing",
        f"{CONFLICTING_GLYPH.symbol} conflicts",
        "1h ago",
    ]
    for index, glyph in (
        (0, DRAFT_GLYPH),
        (6, APPROVED_GLYPH),
        (7, CHECKS_FAILURE_GLYPH),
        (8, CONFLICTING_GLYPH),
    ):
        dark_cell = dark_row.cells[index]
        light_cell = light_row.cells[index]
        assert isinstance(dark_cell, Text) and isinstance(light_cell, Text)
        assert str(dark_cell.style) == glyph.style(dark=True)
        assert str(light_cell.style) == glyph.style(dark=False)


def test_lifecycle_selection_groups_merged_with_closed_and_scopes_counters() -> None:
    observed = snapshot(
        factories.pull_request(1, author="alice"),
        factories.pull_request(2, is_draft=True, author="alice"),
        factories.pull_request(3, state="closed", is_draft=True, author="alice"),
        factories.pull_request(4, state="merged", author="alice"),
        factories.pull_request(5, state="merged", author="bob"),
    )
    default = WorkspaceObservationStore(observed).query_pull_requests()
    assert [row.pull_request.number for row in default.rows] == [1, 2]
    assert (
        default.summary.open_pull_request_count,
        default.summary.closed_pull_request_count,
    ) == (
        2,
        3,
    )

    query = PullRequestListQuery(states=frozenset({"closed"}), text="author:alice")
    closed = WorkspaceObservationStore(observed).query_pull_requests(query)
    assert [row.pull_request.number for row in closed.rows] == [3, 4]
    assert (
        closed.summary.open_pull_request_count,
        closed.summary.closed_pull_request_count,
    ) == (2, 2)
    draft = WorkspaceObservationStore(observed).query_pull_requests(
        replace(query, text="author:alice draft:true")
    )
    assert [row.pull_request.number for row in draft.rows] == [3]
    assert (
        draft.summary.open_pull_request_count,
        draft.summary.closed_pull_request_count,
    ) == (1, 1)
    all_rows = WorkspaceObservationStore(observed).query_pull_requests(
        replace(query, states=frozenset({"open", "closed"}))
    )
    assert all_rows.count == 4


def test_closed_rows_keep_lifecycle_and_draft_visible_in_both_themes() -> None:

    observed = snapshot(
        factories.pull_request(1, state="closed", is_draft=True),
        factories.pull_request(2, state="merged"),
    )
    result = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(states=frozenset({"closed"}))
    )
    for dark in (False, True):
        rows = build_pull_request_rows(result, dark=dark, now=NOW)
        for row, glyph, label in zip(
            rows, (CLOSED_GLYPH, MERGED_GLYPH), ("closed draft", "merged"), strict=True
        ):
            assert str(row.cells[0]) == f"{glyph.symbol} {label}"
            assert isinstance(row.cells[0], Text)
            assert str(row.cells[0].style) == glyph.style(dark=dark)
            assert str(row.cells[8]) == f"{MERGE_NOT_APPLICABLE_GLYPH.symbol} n/a"


def test_lifecycle_and_draft_search_qualifiers_and_negations() -> None:
    observed = snapshot(
        factories.pull_request(1),
        factories.pull_request(2, is_draft=True),
        factories.pull_request(3, state="closed", is_draft=True),
        factories.pull_request(4, state="merged"),
    )
    cases = {
        "is:open": [1, 2],
        "is:closed": [3, 4],
        "state:closed": [3, 4],
        "is:merged": [4],
        "is:unmerged": [1, 2, 3],
        "-is:unmerged": [4],
        "draft:true": [2, 3],
        "draft:false": [1, 4],
        "-draft:true": [1, 4],
        "-state:closed": [1, 2],
        "is:closed draft:true": [3],
    }
    for text, expected in cases.items():
        result = WorkspaceObservationStore(observed).query_pull_requests(
            PullRequestListQuery(states=frozenset({"open", "closed"}), text=text)
        )
        assert [row.pull_request.number for row in result.rows] == expected, text
    closed_search = WorkspaceObservationStore(observed).query_pull_requests(
        PullRequestListQuery(states=frozenset({"closed"}), text="is:closed draft:true")
    )
    assert (
        closed_search.summary.open_pull_request_count,
        closed_search.summary.closed_pull_request_count,
    ) == (1, 1)


def test_state_blocks_share_issue_character_and_use_github_foreground_colours() -> None:
    from dashpot.ui.issue_cells import ISSUE_STATE_GLYPHS

    records = (
        factories.pull_request(1),
        factories.pull_request(2, is_draft=True),
        factories.pull_request(3, state="closed", is_draft=True),
        factories.pull_request(4, state="merged"),
    )
    colours = (
        ("#1a7f37", "#3fb950"),
        ("#59636e", "#9198a1"),
        ("#d1242f", "#f85149"),
        ("#8250df", "#ab7df8"),
    )
    result = WorkspaceObservationStore(snapshot(*records)).query_pull_requests(
        PullRequestListQuery(states=frozenset({"open", "closed"}))
    )
    for dark in (False, True):
        rows = build_pull_request_rows(result, dark=dark, now=NOW)
        for row, colour in zip(rows, colours, strict=True):
            cell = row.cells[0]
            assert isinstance(cell, Text)
            assert cell.plain.startswith(ISSUE_STATE_GLYPHS["open"].symbol + " ")
            assert str(cell.style) == colour[dark]
