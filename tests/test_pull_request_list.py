"""Render the Pull Requests pane's rows from the Pull Requests a page listed."""

from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text

import factories
from dashpot.core.model import PullRequest
from dashpot.observation.issue_list import row_key
from dashpot.observation.pull_request_list import PullRequestListRow
from dashpot.ui.glyphs import BAD_COLORS, DONE_COLORS, GOOD_COLORS, MUTED_COLORS
from dashpot.ui.list_rows import ListRow, build_list_rows
from dashpot.ui.pull_request_cells import (
    APPROVED_GLYPH,
    CHECKS_FAILURE_GLYPH,
    CLOSED_GLYPH,
    CONFLICTING_GLYPH,
    DRAFT_GLYPH,
    MERGE_NOT_APPLICABLE_GLYPH,
    MERGED_GLYPH,
    pull_request_cells,
)

NOW = datetime(2026, 9, 4, 4, 0, tzinfo=UTC)


def pull_request_rows(*pull_requests: PullRequest, dark: bool) -> tuple[ListRow, ...]:
    """The pane rows for a page listing ``pull_requests``, rendered at ``NOW``."""
    project = factories.project("project:one", pull_requests=pull_requests)
    return build_list_rows(
        [
            PullRequestListRow(
                row_key("pull-request", pull_request.id), project, pull_request
            )
            for pull_request in pull_requests
        ],
        lambda row: pull_request_cells(row.pull_request, dark=dark, now=NOW),
    )


def test_rows_render_draft_review_checks_mergeability_and_age_in_both_themes() -> None:
    pull_request = factories.pull_request(
        83,
        is_draft=True,
        review_decision="approved",
        check_status="failure",
        mergeability="conflicting",
        updated_at="2026-09-04T03:00:00Z",
    )
    dark_row = pull_request_rows(pull_request, dark=True)[0]
    light_row = pull_request_rows(pull_request, dark=False)[0]

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


def test_closed_rows_keep_lifecycle_and_draft_visible_in_both_themes() -> None:
    closed = (
        factories.pull_request(1, state="closed", is_draft=True),
        factories.pull_request(2, state="merged"),
    )
    for dark in (False, True):
        rows = pull_request_rows(*closed, dark=dark)
        for row, glyph, label in zip(
            rows, (CLOSED_GLYPH, MERGED_GLYPH), ("closed draft", "merged"), strict=True
        ):
            assert str(row.cells[0]) == f"{glyph.symbol} {label}"
            assert isinstance(row.cells[0], Text)
            assert str(row.cells[0].style) == glyph.style(dark=dark)
            assert str(row.cells[8]) == f"{MERGE_NOT_APPLICABLE_GLYPH.symbol} n/a"


def test_state_blocks_share_issue_character_and_use_github_foreground_colours() -> None:
    from dashpot.ui.issue_cells import ISSUE_STATE_GLYPHS

    records = (
        factories.pull_request(1),
        factories.pull_request(2, is_draft=True),
        factories.pull_request(3, state="closed", is_draft=True),
        factories.pull_request(4, state="merged"),
    )
    # The state block's colours are the shared Glyph palette, never its own.
    colours = (GOOD_COLORS, MUTED_COLORS, BAD_COLORS, DONE_COLORS)
    for dark in (False, True):
        rows = pull_request_rows(*records, dark=dark)
        for row, colour in zip(rows, colours, strict=True):
            cell = row.cells[0]
            assert isinstance(cell, Text)
            assert cell.plain.startswith(ISSUE_STATE_GLYPHS["open"].symbol + " ")
            assert str(cell.style) == colour[dark]
