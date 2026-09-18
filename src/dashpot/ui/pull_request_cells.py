"""The Pull Requests pane's rendered values: its columns, Glyphs and cells.

Everything here turns a queried Pull Request into what the pane shows; the
query itself lives in ``pull_request_list``. Each column carries its own
Column Description and the Glyphs its cells render, from which its header
tooltip and Legend section are built.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from ..core.ages import relative_age
from ..core.model import PullRequest
from .glyphs import (
    ATTENTION_COLORS,
    BAD_COLORS,
    DONE_COLORS,
    GOOD_COLORS,
    MUTED_COLORS,
    Glyph,
)
from .list_rows import ListCell, ListColumn, truncate_end

OPEN_GLYPH = Glyph("■", "an open Pull Request", GOOD_COLORS)
DRAFT_GLYPH = Glyph("■", "a draft Pull Request", MUTED_COLORS)
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

CLOSED_GLYPH = Glyph("■", "a Pull Request closed without merging", BAD_COLORS)
MERGED_GLYPH = Glyph("■", "a merged Pull Request", DONE_COLORS)
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

# What each column shows, said once for the header tooltip and the Legend.
# Every fact is GitHub's answer as of the page's query, so REVIEW, CHECKS
# and MERGE each say what they establish and what they leave to the base
# Branch's protection rules, which the pane does not observe.
STATE_DESCRIPTION = (
    "the Pull Request's lifecycle as GitHub reports it: open, draft, closed "
    "without merging, or merged, a closed draft keeping the word draft; the "
    "pane's Open/Closed/All filter selects by it"
)
NUMBER_DESCRIPTION = "the Pull Request's number in its Repository"
TITLE_DESCRIPTION = f"the Pull Request's title, clipped past {TITLE_LIMIT} characters"
HEAD_DESCRIPTION = (
    "the Branch the Pull Request proposes, by the head ref name GitHub "
    "reports, which does not say whether a fork holds it; clipped past "
    f"{BRANCH_LIMIT} characters"
)
BASE_DESCRIPTION = (
    "the Branch the Pull Request would merge into, clipped past "
    f"{BRANCH_LIMIT} characters"
)
AUTHOR_DESCRIPTION = (
    "the login that opened the Pull Request, or - when GitHub reports none, "
    "as for a deleted account"
)
REVIEW_DESCRIPTION = (
    "GitHub's review decision: approved, changes requested, or review "
    "required by the base Branch's protection rules; none when GitHub "
    "reports no decision. It reports the reviews' standing, not whether "
    "the Pull Request may merge"
)
CHECKS_DESCRIPTION = (
    "the combined result of the head commit's checks and commit statuses, as "
    "GitHub rolls them up: passing, pending, failing, error, or expected but "
    "not yet reported; none when nothing reports on the commit. It is the "
    "latest result, not a gate: whether it blocks merging is the base "
    "Branch's protection"
)
MERGE_DESCRIPTION = (
    "whether GitHub can merge the head into the base without conflicts: "
    "mergeable, conflicts, or calculating while GitHub is still determining "
    "it; n/a for a closed or merged Pull Request. It says nothing about "
    "reviews, checks, or the base Branch's other rules"
)
UPDATED_DESCRIPTION = (
    "the age of the Pull Request's last update on GitHub, which any edit, "
    "comment, review, or push moves, as of the page's query, or - when the "
    "page reports no usable time; the pane border carries the page's own "
    "freshness"
)

PULL_REQUEST_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("state", "STATE", description=STATE_DESCRIPTION, glyphs=STATE_LEGEND),
    ListColumn("number", "#", justify="right", description=NUMBER_DESCRIPTION),
    ListColumn("title", "TITLE", description=TITLE_DESCRIPTION),
    ListColumn("head", "HEAD", description=HEAD_DESCRIPTION),
    ListColumn("base", "BASE", description=BASE_DESCRIPTION),
    ListColumn("author", "AUTHOR", description=AUTHOR_DESCRIPTION),
    ListColumn(
        "review", "REVIEW", description=REVIEW_DESCRIPTION, glyphs=REVIEW_LEGEND
    ),
    ListColumn(
        "checks", "CHECKS", description=CHECKS_DESCRIPTION, glyphs=CHECKS_LEGEND
    ),
    ListColumn("merge", "MERGE", description=MERGE_DESCRIPTION, glyphs=MERGE_LEGEND),
    ListColumn("updated", "UPDATED", description=UPDATED_DESCRIPTION),
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
