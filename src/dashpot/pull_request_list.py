"""Read and render the Project's Pull Requests for the main screen."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from rich.text import Text

from .glyphs import Glyph
from .issue_cells import relative_age
from .issue_list import row_key
from .list_pane import ListCell, ListColumn, ListRow, truncate_end
from .model import ProjectObservation, PullRequest, SourceStatus, WorkspaceSnapshot
from .pull_request_search import PullRequestQualifier, parse_pull_request_search

PullRequestLifecycle = Literal["open", "closed"]
PullRequestReadiness = Literal["ready", "draft"]

GOOD_COLORS = ("#1a7f37", "#3fb950")
ATTENTION_COLORS = ("#9a6700", "#d29922")
BAD_COLORS = ("#cf222e", "#f85149")
MUTED_COLORS = ("#59636e", "#8b949e")

OPEN_GLYPH = Glyph("⊙", "an open Pull Request", GOOD_COLORS)
DRAFT_GLYPH = Glyph("◌", "a draft Pull Request", MUTED_COLORS)
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

CLOSED_GLYPH = Glyph("⊗", "a Pull Request closed without merging", BAD_COLORS)
MERGED_GLYPH = Glyph("⑂", "a merged Pull Request", ("#8250df", "#a371f7"))
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


@dataclass(frozen=True, slots=True)
class PullRequestListQuery:
    readiness: frozenset[PullRequestReadiness] = frozenset({"ready", "draft"})
    text: str = ""
    states: frozenset[PullRequestLifecycle] = frozenset({"open"})


DEFAULT_PULL_REQUEST_QUERY = PullRequestListQuery()


@dataclass(frozen=True, slots=True)
class PullRequestListRow:
    """Join one Pull Request to the Project whose Repository owns it."""

    key: str
    project: ProjectObservation
    pull_request: PullRequest


@dataclass(frozen=True, slots=True)
class PullRequestListResult:
    rows: tuple[PullRequestListRow, ...]
    matched_pull_request_count: int
    observed_pull_request_count: int
    status: SourceStatus
    attempted_at: str | None
    last_good_at: str | None
    open_pull_request_count: int
    closed_pull_request_count: int
    revision: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)


def query_pull_request_list(
    snapshot: WorkspaceSnapshot,
    query: PullRequestListQuery = DEFAULT_PULL_REQUEST_QUERY,
    *,
    revision: int = 0,
) -> PullRequestListResult:
    """Query Pull Request rows from one complete Workspace checkpoint."""
    projects: dict[str, ProjectObservation] = {}
    pull_requests: dict[tuple[str, str], PullRequest] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for pull_request in project.snapshot.pull_requests:
            key = (project.project_id, pull_request.id)
            if key in pull_requests:
                raise ValueError(
                    f"Duplicate Pull Request identity {pull_request.id} in "
                    f"{project.project_id}"
                )
            pull_requests[key] = pull_request
    return _query_indexed_pull_request_list(
        projects=projects,
        pull_requests=pull_requests,
        query=query,
        revision=revision,
    )


def _query_indexed_pull_request_list(
    *,
    projects: Mapping[str, ProjectObservation],
    pull_requests: Mapping[tuple[str, str], PullRequest],
    query: PullRequestListQuery,
    revision: int,
) -> PullRequestListResult:
    parsed = parse_pull_request_search(query.text)
    rows = [
        PullRequestListRow(
            row_key("pull-request", project_id, pull_request.id),
            projects[project_id],
            pull_request,
        )
        for (project_id, _pull_request_id), pull_request in pull_requests.items()
        if project_id in projects
        and _pull_request_readiness(pull_request) in query.readiness
        and _matches_search(pull_request, projects[project_id], parsed.terms)
        and all(
            _matches_qualifier(pull_request, qualifier)
            for qualifier in parsed.qualifiers
            if not _is_lifecycle_qualifier(qualifier)
        )
    ]
    open_count = sum(row.pull_request.state == "open" for row in rows)
    closed_count = len(rows) - open_count
    rows = [
        row
        for row in rows
        if _lifecycle(row.pull_request) in query.states
        and all(
            _matches_qualifier(row.pull_request, qualifier)
            for qualifier in parsed.qualifiers
            if _is_lifecycle_qualifier(qualifier)
        )
    ]
    rows.sort(key=lambda row: row.pull_request.number)
    sort = parsed.sort
    sort_field = (
        "updated_at" if sort is None or sort.field == "updated" else "created_at"
    )
    rows.sort(
        key=lambda row: getattr(row.pull_request, sort_field),
        reverse=True if sort is None else sort.descending,
    )
    snapshots = [
        project.snapshot
        for project in projects.values()
        if project.snapshot is not None
    ]
    statuses = [snapshot.pull_request_status for snapshot in snapshots]
    status: SourceStatus
    if not statuses or "unavailable" in statuses:
        status = "unavailable"
    elif "stale" in statuses:
        status = "stale"
    else:
        status = "fresh"
    attempted = [
        snapshot.pull_request_attempted_at
        for snapshot in snapshots
        if snapshot.pull_request_attempted_at is not None
    ]
    last_good = [
        snapshot.pull_request_last_good_at
        for snapshot in snapshots
        if snapshot.pull_request_last_good_at is not None
    ]
    return PullRequestListResult(
        rows=tuple(rows),
        matched_pull_request_count=len(rows),
        observed_pull_request_count=len(pull_requests),
        status=status,
        attempted_at=max(attempted, default=None),
        last_good_at=max(last_good, default=None),
        open_pull_request_count=open_count,
        closed_pull_request_count=closed_count,
        revision=revision,
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


def pull_request_note(result: PullRequestListResult, now: datetime) -> str | None:
    """Describe freshness only when the Pull Request observation is not fresh."""
    if result.status == "fresh":
        return None
    if result.status == "stale":
        age = relative_age(result.last_good_at, now)
        return f"stale · last good {age}" if age else "stale"
    return "unavailable"


def pull_request_empty_message(
    result: PullRequestListResult,
    query: PullRequestListQuery = DEFAULT_PULL_REQUEST_QUERY,
) -> str:
    """Distinguish a fresh empty collection from stale or unavailable data."""
    if result.observed_pull_request_count and not result.rows:
        parsed = parse_pull_request_search(query.text)
        if not parsed.terms and not parsed.qualifiers:
            if query.readiness == frozenset({"ready"}):
                return "no non-draft Pull Requests"
            if query.readiness == frozenset({"draft"}):
                return "no draft Pull Requests"
        return "no Pull Requests match the current filters"
    if result.status == "fresh":
        return "no pull requests"
    if result.status == "stale":
        return "no pull requests when last observed"
    return "pull requests unavailable"


def pull_request_result_count_text(count: int) -> str:
    """Describe how many Pull Requests match every current filter."""
    return "1 pull request" if count == 1 else f"{count} pull requests"


def _pull_request_readiness(pull_request: PullRequest) -> PullRequestReadiness:
    return "draft" if pull_request.is_draft else "ready"


def _matches_search(
    pull_request: PullRequest,
    project: ProjectObservation,
    terms: tuple[str, ...],
) -> bool:
    searchable = "\n".join(
        (
            f"#{pull_request.number}",
            pull_request.title,
            project.display_label,
            pull_request.head_branch,
            pull_request.base_branch,
            pull_request.author or "",
        )
    ).casefold()
    return all(term.casefold() in searchable for term in terms)


def _matches_qualifier(
    pull_request: PullRequest, qualifier: PullRequestQualifier
) -> bool:
    value = qualifier.value
    if qualifier.field == "author":
        matched = (pull_request.author or "").casefold() == value
    elif qualifier.field == "base":
        matched = pull_request.base_branch.casefold() == value
    elif qualifier.field == "head":
        matched = pull_request.head_branch.casefold() == value
    elif qualifier.field == "draft":
        matched = pull_request.is_draft == (value == "true")
    elif qualifier.field == "is":
        matched = {
            "pr": True,
            "draft": pull_request.is_draft,
            "open": pull_request.state == "open",
            "closed": pull_request.state != "open",
            "merged": pull_request.state == "merged",
            "unmerged": pull_request.state != "merged",
        }[value]
    elif qualifier.field == "state":
        matched = value == _lifecycle(pull_request)
    elif qualifier.field == "review":
        decisions = {
            "approved": "approved",
            "changes-requested": "changes-requested",
            "changes_requested": "changes-requested",
            "none": None,
            "required": "review-required",
        }
        matched = pull_request.review_decision == decisions[value]
    else:
        statuses = {
            "failure": frozenset({"error", "failure"}),
            "pending": frozenset({"expected", "pending", None}),
            "success": frozenset({"success"}),
        }
        matched = pull_request.check_status in statuses[value]
    return not matched if qualifier.negated else matched


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


def _lifecycle(pull_request: PullRequest) -> PullRequestLifecycle:
    return "open" if pull_request.state == "open" else "closed"


def _state_cell(pull_request: PullRequest, *, dark: bool) -> Text:
    if pull_request.state == "open":
        glyph = DRAFT_GLYPH if pull_request.is_draft else OPEN_GLYPH
        label = "draft" if pull_request.is_draft else "open"
    else:
        glyph = MERGED_GLYPH if pull_request.state == "merged" else CLOSED_GLYPH
        label = pull_request.state + (" draft" if pull_request.is_draft else "")
    return _glyph_text(glyph, label, dark=dark)


def pull_request_inventory_text(result: PullRequestListResult) -> str:
    """Summarize both lifecycles under the current search and draft filters."""
    if result.status == "unavailable":
        return "unavailable"
    return f"Open {result.open_pull_request_count} · Closed {result.closed_pull_request_count}"


def _is_lifecycle_qualifier(qualifier: PullRequestQualifier) -> bool:
    return qualifier.field == "state" or (
        qualifier.field == "is" and qualifier.value in {"open", "closed"}
    )
