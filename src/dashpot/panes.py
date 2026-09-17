"""Declare the list panes once: what each shows, reads, controls and relates.

``LIST_PANE_SPECS`` drives the dashboard's composition, its accessors, the
focus cycle and every refresh, so adding a pane is adding a spec here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .branch_cells import BRANCH_COLUMNS, branch_note, build_branch_rows
from .focus_table import FocusCursorTable
from .issue_list import row_key
from .item_filter import LIFECYCLE_STATUSES, ItemFilterBar, lifecycle_value
from .list_pane import (
    BRANCHES_PANE_LABEL,
    PULL_REQUESTS_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
    ListCell,
    ListColumn,
    ListRow,
)
from .paged_store import PagedObservationStore
from .pull_request_cells import PULL_REQUEST_COLUMNS, build_pull_request_rows
from .pull_request_list import (
    DEFAULT_PULL_REQUEST_QUERY,
    PullRequestListResult,
    PullRequestListRow,
    pull_request_result_count_text,
)
from .queries.page_navigation import PageNavigation, page_text, totals_text
from .queries.source_queries import ResourceKind
from .related_rows import FocusedSource, RelatedRows
from .session_cells import SESSION_COLUMNS, build_session_rows, session_columns
from .worktree_cells import WORKTREE_COLUMNS, build_worktree_rows
from .worktree_table import WorktreeTable


@dataclass(frozen=True, slots=True)
class PaneRows:
    """What one refresh hands a list pane: records and the per-refresh extras.

    ``columns`` re-declares the pane's columns when the read model varies
    them; ``note`` is a pane-level fact for the frame's subtitle;
    ``filter_count`` is the matched count the pane's controls show; and
    ``records`` are the read-model rows the list rows were built from, kept
    for relationship emphasis so a cursor move never queries the store.
    """

    rows: tuple[ListRow, ...]
    columns: tuple[ListColumn, ...] | None = None
    note: str | None = None
    empty_message: str | None = None
    title_count: int | None = None
    title_summary: str | None = None
    filter_count: str | None = None
    records: tuple[FocusedSource, ...] = ()


@dataclass(frozen=True, slots=True)
class PaneContext:
    """Hold what one list-pane refresh reads: store, navigation, theme, time."""

    store: PagedObservationStore
    navigation: Mapping[ResourceKind, PageNavigation]
    dark: bool
    now: datetime


class PaneRowsSource(Protocol):
    """Derive one pane's records from what the refresh reads."""

    def __call__(self, context: PaneContext) -> PaneRows: ...


@dataclass(frozen=True, slots=True)
class PaneSpec:
    """Everything one list pane varies by, declared once.

    ``controls`` composes the pane's filtering controls, one per screen,
    and ``controls_height`` is the height they take. ``related`` picks the
    relationship set that holds this pane's keys, and ``related_columns``
    the columns that emphasise a related row; a pane without either takes
    no part in relationship emphasis.
    """

    pane_id: str
    table_id: str
    label: str
    columns: tuple[ListColumn, ...]
    empty_message: str
    rows: PaneRowsSource
    table_type: type[FocusCursorTable[ListCell]] = FocusCursorTable
    controls: Callable[[], ItemFilterBar] | None = None
    controls_height: int = 0
    related: Callable[[RelatedRows], frozenset[str]] | None = None
    related_columns: frozenset[str] = frozenset()


def session_pane_rows(context: PaneContext) -> PaneRows:
    """List every active Agent Session, with the columns its result shows."""
    sessions = context.store.query_sessions()
    return PaneRows(
        build_session_rows(sessions, dark=context.dark),
        columns=session_columns(sessions),
        records=sessions.rows,
    )


def branch_pane_rows(context: PaneContext) -> PaneRows:
    """List every observed Branch, noting when the remotes were last fetched."""
    branches = context.store.query_branches()
    return PaneRows(
        build_branch_rows(branches, dark=context.dark, now=context.now),
        note=branch_note(branches.integration_refs, branches.fetched_at, context.now),
        records=branches.rows,
    )


def worktree_pane_rows(context: PaneContext) -> PaneRows:
    """List every observed Worktree in the Repository's topology order."""
    worktrees = context.store.query_worktrees()
    return PaneRows(
        build_worktree_rows(worktrees, dark=context.dark), records=worktrees.rows
    )


def pull_request_pane_rows(context: PaneContext) -> PaneRows:
    """List the accepted Pull Request page with the Project's totals."""
    store = context.store
    page = store.pages.get("pull-requests")
    projects = store.projects()
    summary = totals_text(store.totals.get("pull-requests"))
    if page is None or not projects:
        return PaneRows((), title_summary=summary, empty_message="Loading page")
    result = PullRequestListResult(
        tuple(
            PullRequestListRow(row_key("pull-request", pr.id), projects[0], pr)
            for pr in page.pull_requests
        ),
        page.matched_count or 0,
        page.returned_count,
        page.status,
        page.attempted_at,
        page.last_good_at,
        0,
        0,
    )
    rows = build_pull_request_rows(result, dark=context.dark, now=context.now)
    return PaneRows(
        rows,
        title_summary=summary,
        note=page_text(context.navigation["pull-requests"]),
        empty_message="No matching Pull Requests"
        if page.status == "fresh"
        else "Pull Requests unavailable",
        filter_count=pull_request_result_count_text(len(rows)),
    )


def pull_request_filter_bar() -> ItemFilterBar:
    """The Pull Requests pane's controls, starting from the default query."""
    query = DEFAULT_PULL_REQUEST_QUERY
    return ItemFilterBar(
        "pull-request",
        statuses=LIFECYCLE_STATUSES,
        status=lifecycle_value(query.states),
        query=query.text,
        placeholder="Search Pull Requests",
        count=pull_request_result_count_text(0),
    )


# The list panes in reading order, each declared once.
LIST_PANE_SPECS: tuple[PaneSpec, ...] = (
    PaneSpec(
        "sessions-pane",
        "sessions",
        SESSIONS_PANE_LABEL,
        SESSION_COLUMNS,
        "no active sessions",
        session_pane_rows,
        related=lambda related: related.sessions,
        related_columns=frozenset({"harness", "target"}),
    ),
    PaneSpec(
        "worktrees-pane",
        "worktrees",
        WORKTREES_PANE_LABEL,
        WORKTREE_COLUMNS,
        "no worktrees observed yet",
        worktree_pane_rows,
        table_type=WorktreeTable,
        related=lambda related: related.worktrees,
        related_columns=frozenset({"path"}),
    ),
    PaneSpec(
        "branches-pane",
        "branches",
        BRANCHES_PANE_LABEL,
        BRANCH_COLUMNS,
        "no branches observed yet",
        branch_pane_rows,
        related=lambda related: related.branches,
        related_columns=frozenset({"name"}),
    ),
    PaneSpec(
        "pull-requests-pane",
        "pull-requests",
        PULL_REQUESTS_PANE_LABEL,
        PULL_REQUEST_COLUMNS,
        "pull requests unavailable",
        pull_request_pane_rows,
        controls=pull_request_filter_bar,
        controls_height=ItemFilterBar.HEIGHT,
    ),
)
