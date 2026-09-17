"""The Pull Requests pane's rendered values: its columns, Glyphs and cells.

Everything here turns a queried Pull Request into what the pane shows; the
query itself lives in ``pull_request_list``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text

from .core.ages import relative_age
from .core.model import PullRequest
from .glyphs import (
    ATTENTION_COLORS,
    BAD_COLORS,
    GOOD_COLORS,
    MUTED_COLORS,
    Glyph,
)
from .list_rows import ListCell, ListColumn, ListRow, truncate_end
from .pull_request_list import PullRequestListResult

OPEN_GLYPH = Glyph("■", "an open Pull Request", GOOD_COLORS)
DRAFT_GLYPH = Glyph("■", "a draft Pull Request", ("#59636e", "#9198a1"))
APPROVED_GLYPH = Glyph("✓R", "reviews approve the Pull Request", GOOD_COLORS)
CHANGES_REQUESTED_GLYPH = Glyph(
    "✗R", "reviews request changes to the Pull Request", BAD_COLORS
)
REVIEW_REQUIRED_GLYPH = Glyph(
    "?R", "the Pull Request still requires review", ATTENTION_COLORS
)
NO_REVIEW_GLYPH = Glyph("—R", "no review decision applies", MUTED_COLORS)
CHECKS_SUCCESS_GLYPH = Glyph("✓C", "checks and statuses are passing", GOOD_COLORS)
CHECKS_PENDING_GLYPH = Glyph("…C", "checks or statuses are pending", ATTENTION_COLORS)
CHECKS_FAILURE_GLYPH = Glyph("✗C", "checks or statuses are failing", BAD_COLORS)
CHECKS_ERROR_GLYPH = Glyph("!C", "checks or statuses report an error", BAD_COLORS)
CHECKS_EXPECTED_GLYPH = Glyph(
    "○C", "checks or statuses are expected but not reported", ATTENTION_COLORS
)
NO_CHECKS_GLYPH = Glyph("—C", "no checks or statuses are reported", MUTED_COLORS)
MERGEABLE_GLYPH = Glyph("✓M", "the Pull Request has no merge conflicts", GOOD_COLORS)
CONFLICTING_GLYPH = Glyph("✗M", "the Pull Request has merge conflicts", BAD_COLORS)
MERGEABILITY_UNKNOWN_GLYPH = Glyph(
    "…M", "GitHub is still determining mergeability", MUTED_COLORS
)

CLOSED_GLYPH = Glyph(
    "■", "a Pull Request closed without merging", ("#d1242f", "#f85149")
)
MERGED_GLYPH = Glyph("■", "a merged Pull Request", ("#8250df", "#ab7df8"))
MERGE_NOT_APPLICABLE_GLYPH = Glyph("—M", "mergeability does not apply", MUTED_COLORS)

STATE_LEGEND = (OPEN_GLYPH, DRAFT_GLYPH, CLOSED_GLYPH, MERGED_GLYPH)
REVIEW_LEGEND = (
    APPROVED_GLYPH,
    CHANGES_REQUESTED_GLYPH,
    REVIEW_REQUIRED_GLYPH,
    NO_REVIEW_GLYPH,
)
CHECKS_LEGEND = (
    CHECKS_SUCCESS_GLYPH,
    CHECKS_PENDING_GLYPH,
    CHECKS_FAILURE_GLYPH,
    CHECKS_ERROR_GLYPH,
    CHECKS_EXPECTED_GLYPH,
    NO_CHECKS_GLYPH,
)
MERGE_LEGEND = (
    MERGEABLE_GLYPH,
    CONFLICTING_GLYPH,
    MERGEABILITY_UNKNOWN_GLYPH,
    MERGE_NOT_APPLICABLE_GLYPH,
)
LEGEND = STATE_LEGEND + REVIEW_LEGEND + CHECKS_LEGEND + MERGE_LEGEND

TITLE_LIMIT = 56
BRANCH_LIMIT = 32

PULL_REQUEST_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("state", "STATE"),
    ListColumn("number", "#", justify="right"),
    ListColumn("title", "TITLE"),
    ListColumn("head", "HEAD"),
    ListColumn("base", "BASE"),
    ListColumn("author", "AUTHOR"),
    ListColumn("review", "REVIEW"),
    ListColumn("checks", "CHECKS"),
    ListColumn("merge", "MERGE"),
    ListColumn("updated", "UPDATED"),
)


def build_pull_request_rows(
    result: PullRequestListResult,
    *,
    dark: bool,
    now: datetime | None = None,
) -> tuple[ListRow, ...]:
    """Render every Pull Request with its scan-level coordination facts."""
    current = now or datetime.now(UTC)
    return tuple(
        ListRow(
            row.key,
            pull_request_cells(row.pull_request, dark=dark, now=current),
        )
        for row in result.rows
    )


def pull_request_cells(
    pull_request: PullRequest, *, dark: bool, now: datetime
) -> tuple[ListCell, ...]:
    return (
        _state_cell(pull_request, dark=dark),
        str(pull_request.number),
        truncate_end(pull_request.title, TITLE_LIMIT),
        truncate_end(pull_request.head_branch, BRANCH_LIMIT),
        truncate_end(pull_request.base_branch, BRANCH_LIMIT),
        pull_request.author or "-",
        _review_cell(pull_request, dark=dark),
        _checks_cell(pull_request, dark=dark),
        _merge_cell(pull_request, dark=dark),
        relative_age(pull_request.updated_at, now) or "-",
    )


def _review_cell(pull_request: PullRequest, *, dark: bool) -> Text:
    values = {
        "approved": (APPROVED_GLYPH, "approved"),
        "changes-requested": (CHANGES_REQUESTED_GLYPH, "changes"),
        "review-required": (REVIEW_REQUIRED_GLYPH, "required"),
        None: (NO_REVIEW_GLYPH, "none"),
    }
    glyph, label = values[pull_request.review_decision]
    return _glyph_text(glyph, label, dark=dark)


def _checks_cell(pull_request: PullRequest, *, dark: bool) -> Text:
    values = {
        "success": (CHECKS_SUCCESS_GLYPH, "passing"),
        "pending": (CHECKS_PENDING_GLYPH, "pending"),
        "failure": (CHECKS_FAILURE_GLYPH, "failing"),
        "error": (CHECKS_ERROR_GLYPH, "error"),
        "expected": (CHECKS_EXPECTED_GLYPH, "expected"),
        None: (NO_CHECKS_GLYPH, "none"),
    }
    glyph, label = values[pull_request.check_status]
    return _glyph_text(glyph, label, dark=dark)


def _merge_cell(pull_request: PullRequest, *, dark: bool) -> Text:
    if pull_request.state != "open":
        return _glyph_text(MERGE_NOT_APPLICABLE_GLYPH, "n/a", dark=dark)
    values = {
        "mergeable": (MERGEABLE_GLYPH, "mergeable"),
        "conflicting": (CONFLICTING_GLYPH, "conflicts"),
        None: (MERGEABILITY_UNKNOWN_GLYPH, "calculating"),
    }
    glyph, label = values[pull_request.mergeability]
    return _glyph_text(glyph, label, dark=dark)


def _glyph_text(glyph: Glyph, label: str, *, dark: bool) -> Text:
    return Text(f"{glyph.symbol} {label}", style=glyph.style(dark=dark))


def _state_cell(pull_request: PullRequest, *, dark: bool) -> Text:
    if pull_request.state == "open":
        glyph = DRAFT_GLYPH if pull_request.is_draft else OPEN_GLYPH
        label = "draft" if pull_request.is_draft else "open"
    else:
        glyph = MERGED_GLYPH if pull_request.state == "merged" else CLOSED_GLYPH
        label = pull_request.state + (" draft" if pull_request.is_draft else "")
    return _glyph_text(glyph, label, dark=dark)
