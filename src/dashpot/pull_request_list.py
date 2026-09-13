"""The Pull Requests pane read model: the Project's Pull Requests, filtered.

A row is one Pull Request joined to the Project whose Repository owns it,
selected by the pane's search and lifecycle filters; the rendering lives in
``pull_request_cells``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .issue_list import row_key
from .model import ProjectObservation, PullRequest, SourceStatus, WorkspaceSnapshot
from .pull_request_search import PullRequestQualifier, parse_pull_request_search

PullRequestLifecycle = Literal["open", "closed"]


@dataclass(frozen=True, slots=True)
class PullRequestListQuery:
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
    return query_indexed_pull_request_list(
        projects=projects,
        pull_requests=pull_requests,
        query=query,
        revision=revision,
    )


def query_indexed_pull_request_list(
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


def pull_request_empty_message(
    result: PullRequestListResult,
    query: PullRequestListQuery = DEFAULT_PULL_REQUEST_QUERY,
) -> str:
    """Distinguish a fresh empty collection from stale or unavailable data."""
    if result.observed_pull_request_count and not result.rows:
        return "no Pull Requests match the current filters"
    if result.status == "fresh":
        return "no pull requests"
    if result.status == "stale":
        return "no pull requests when last observed"
    return "pull requests unavailable"


def pull_request_result_count_text(count: int) -> str:
    """Describe how many Pull Requests match every current filter."""
    return "1 pull request" if count == 1 else f"{count} pull requests"


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


def _lifecycle(pull_request: PullRequest) -> PullRequestLifecycle:
    return "open" if pull_request.state == "open" else "closed"


def pull_request_inventory_text(result: PullRequestListResult) -> str:
    """Summarize both lifecycles under the current search and draft filters."""
    if result.status == "unavailable":
        return "unavailable"
    return f"Open {result.open_pull_request_count} · Closed {result.closed_pull_request_count}"


def _is_lifecycle_qualifier(qualifier: PullRequestQualifier) -> bool:
    return qualifier.field == "state" or (
        qualifier.field == "is" and qualifier.value in {"open", "closed"}
    )


def query_pull_request_search_results(
    project: ProjectObservation,
    pull_requests: tuple[PullRequest, ...],
    query: PullRequestListQuery,
    *,
    status: SourceStatus,
    attempted_at: str | None,
    last_good_at: str | None,
) -> PullRequestListResult:
    """Filter a complete GitHub search by lifecycle while preserving its order."""
    rows = tuple(
        PullRequestListRow(
            row_key("pull-request", project.project_id, pr.id), project, pr
        )
        for pr in pull_requests
        if _lifecycle(pr) in query.states
    )
    open_count = sum(pr.state == "open" for pr in pull_requests)
    return PullRequestListResult(
        rows=rows,
        matched_pull_request_count=len(rows),
        observed_pull_request_count=len(pull_requests),
        status=status,
        attempted_at=attempted_at,
        last_good_at=last_good_at,
        open_pull_request_count=open_count,
        closed_pull_request_count=len(pull_requests) - open_count,
    )
