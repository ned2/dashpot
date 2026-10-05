"""Declare the list panes once: what each shows, reads, controls and relates.

Each Peer Screen has one spec tuple that drives its composition, accessors,
focus cycle and refresh. ``LIST_PANE_SPECS`` is their combined catalogue for
the Legend and contract tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Literal, Protocol

from ..observation.issue_list import row_key
from ..observation.paged_store import PagedObservationStore
from ..observation.pull_request_list import (
    DEFAULT_PULL_REQUEST_QUERY,
    PullRequestListRow,
)
from ..observation.related_rows import RelatedRows
from ..observation.session_list import shows_target
from ..queries.page_navigation import PageNavigation, page_text, totals_text
from ..queries.pages import ResourceKind
from .branch_cells import BRANCH_COLUMNS, branch_cells, branch_note
from .focus_table import FocusCursorTable
from .item_filter import LIFECYCLE_STATUSES, ItemFilterBar, lifecycle_value
from .list_pane import (
    BRANCHES_PANE_LABEL,
    PULL_REQUESTS_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
    ListCell,
    ListColumn,
    PaneRows,
)
from .list_rows import build_list_rows
from .pull_request_cells import PULL_REQUEST_COLUMNS, pull_request_cells
from .session_cells import SESSION_COLUMNS, session_cells, session_columns
from .session_table import SessionTable
from .worktree_cells import WORKTREE_COLUMNS, worktree_cells
from .worktree_table import WorktreeTable


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


# The widget ids of the list panes and their tables, which the stylesheet and
# the Peer Screen accessors name; a spec carries one of each.
ListPaneId = Literal[
    "sessions-pane", "worktrees-pane", "branches-pane", "pull-requests-pane"
]
ListTableId = Literal["sessions", "worktrees", "branches", "pull-requests"]


@dataclass(frozen=True, slots=True)
class PaneSpec:
    """Everything one list pane varies by, declared once.

    ``query_kind`` is the paged Query Source kind the pane lists, whose
    query its ``controls`` submit; a pane over the observation store has
    neither. ``controls`` composes the pane's filtering controls, one per
    screen, and ``controls_height`` is the height they take.
    ``visible_row_limit`` bounds records on a pane that must leave another
    surface flexible; ``None`` lets a pane seek enough viewport height for
    every record. ``related`` picks the relationship set that holds this
    pane's keys, and ``related_columns`` the columns that emphasise a related
    row; a pane without either takes no part in relationship emphasis.
    """

    pane_id: ListPaneId
    table_id: ListTableId
    label: str
    columns: tuple[ListColumn, ...]
    empty_message: str
    rows: PaneRowsSource
    table_type: type[FocusCursorTable[ListCell]] = FocusCursorTable
    query_kind: ResourceKind | None = None
    controls: Callable[[], ItemFilterBar] | None = None
    controls_height: int = 0
    visible_row_limit: int | None = None
    related: Callable[[RelatedRows], frozenset[str]] | None = None
    related_columns: frozenset[str] = frozenset()


def session_pane_rows(context: PaneContext) -> PaneRows:
    """List every active Agent Session, with the columns its result shows."""
    sessions = context.store.query_sessions()
    return PaneRows(
        build_list_rows(
            sessions.rows,
            partial(
                session_cells,
                dark=context.dark,
                now=context.now,
                target=shows_target(sessions),
            ),
            issue_id=lambda row: row.bound_issue_id,
        ),
        columns=session_columns(sessions),
        records=sessions.rows,
    )


def branch_pane_rows(context: PaneContext) -> PaneRows:
    """List every observed Branch, noting when the remotes were last fetched."""
    branches = context.store.query_branches()
    return PaneRows(
        build_list_rows(
            branches.rows, partial(branch_cells, dark=context.dark, now=context.now)
        ),
        note=branch_note(
            branches.summary.integration_refs, branches.summary.fetched_at, context.now
        ),
        records=branches.rows,
    )


def worktree_pane_rows(context: PaneContext) -> PaneRows:
    """List every observed Worktree in the Repository's topology order."""
    worktrees = context.store.query_worktrees()
    return PaneRows(
        build_list_rows(worktrees.rows, partial(worktree_cells, dark=context.dark)),
        records=worktrees.rows,
    )


def pull_request_pane_rows(context: PaneContext) -> PaneRows:
    """List the accepted Pull Request page with the Project's totals."""
    store = context.store
    page = store.pages.get("pull-requests")
    projects = store.projects()
    summary = totals_text(store.totals.get("pull-requests"))
    navigation = context.navigation["pull-requests"]
    # The controls count what the query matched, as the Issue filter bar
    # does, never the page's length; a page still to land says so.
    filter_count = page_text(navigation, context.now, detail="compact")
    if page is None or not projects:
        return PaneRows(
            (),
            title_summary=summary,
            empty_message="Loading page",
            filter_count=filter_count,
        )
    # The page is the source's answer, already filtered and ordered; the
    # rows join each Pull Request to the Project it was asked for.
    rows = build_list_rows(
        (
            PullRequestListRow(row_key("pull-request", pr.id), projects[0], pr)
            for pr in page.pull_requests
        ),
        lambda row: pull_request_cells(
            row.pull_request, dark=context.dark, now=context.now
        ),
    )
    return PaneRows(
        rows,
        title_summary=summary,
        note=page_text(navigation, context.now),
        empty_message="No matching Pull Requests"
        if page.status == "fresh"
        else "Pull Requests unavailable",
        filter_count=filter_count,
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
        count="Loading page",
    )


# The Dashboard panes in reading order, each declared once.
DASHBOARD_PANE_SPECS: tuple[PaneSpec, ...] = (
    PaneSpec(
        "sessions-pane",
        "sessions",
        SESSIONS_PANE_LABEL,
        SESSION_COLUMNS,
        "no active sessions",
        session_pane_rows,
        table_type=SessionTable,
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
)

# The dedicated peer's one content-capped list above its flexible Issue table.
QUERY_PANE_SPECS: tuple[PaneSpec, ...] = (
    PaneSpec(
        "pull-requests-pane",
        "pull-requests",
        PULL_REQUESTS_PANE_LABEL,
        PULL_REQUEST_COLUMNS,
        "pull requests unavailable",
        pull_request_pane_rows,
        query_kind="pull-requests",
        controls=pull_request_filter_bar,
        controls_height=ItemFilterBar.HEIGHT,
        visible_row_limit=8,
    ),
)

# The complete pane catalogue remains one source for the Legend.
LIST_PANE_SPECS: tuple[PaneSpec, ...] = (*DASHBOARD_PANE_SPECS, *QUERY_PANE_SPECS)
