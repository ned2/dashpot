"""The Worktrees pane's rendered values: its columns, colours and cells.

Everything here turns a queried `WorktreeListRow` into what the pane shows;
the query itself lives in ``worktree_list``. The Branches pane shares the
activity and session-count cells, so they are defined here once.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.text import Text

from .glyphs import ACTIVITY_COLUMN_GLYPH, ACTIVITY_WIDTH
from .list_rows import ListCell, ListColumn, ListRow, truncate_end
from .model import ObservationTarget, RunState
from .session_cells import STATE_GLYPHS
from .session_list import STATE_ORDER, abbreviate_path
from .worktree_list import WorktreeListResult, WorktreeListRow

BRANCH_LIMIT = 24
SHORT_HEAD = 7
# GitHub Primer emphasis colours for the working-tree and availability
# states; each pair is (light theme, dark theme).
DIRTY_COLORS = ("#9a6700", "#d29922")
UNAVAILABLE_COLORS = ("#cf222e", "#f85149")
STALE_COLORS = ("#9a6700", "#d29922")

WORKTREE_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn(
        "activity", ACTIVITY_COLUMN_GLYPH.symbol, width=ACTIVITY_WIDTH, frozen=True
    ),
    ListColumn("sessions", "SESSIONS", justify="center"),
    ListColumn("path", "PATH"),
    ListColumn("kind", "KIND"),
    ListColumn("branch", "BRANCH"),
    ListColumn("tree", "TREE"),
)


def build_worktree_rows(
    result: WorktreeListResult, *, dark: bool, home: Path | None = None
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    return tuple(
        ListRow(
            row.key,
            worktree_cells(row, dark=dark, home=home),
        )
        for row in result.rows
    )


def worktree_cells(
    row: WorktreeListRow, *, dark: bool, home: Path | None = None
) -> tuple[ListCell, ...]:
    target = row.target
    return (
        activity_cell(tuple(session.state for session in row.sessions), dark=dark),
        sessions_cell(tuple(session.state for session in row.sessions), dark=dark),
        path_cell(row, dark=dark, home=home),
        target.role,
        branch_cell(target),
        tree_cell(target.dirty, dark=dark),
    )


def path_cell(
    row: WorktreeListRow, *, dark: bool, home: Path | None = None
) -> ListCell:
    """Show the path with exceptional freshness when observation failed."""
    path = abbreviate_path(row.target.path, home=home)
    freshness = row.freshness
    if freshness == "available":
        return path
    cell = Text(f"{path} · ")
    cell.append(freshness, style=freshness_color(freshness, dark=dark))
    return cell


def branch_cell(target: ObservationTarget) -> str:
    """Show a Branch name, or the useful short HEAD for a detached checkout."""
    if target.branch is not None:
        return truncate_end(target.branch, BRANCH_LIMIT)
    head = target.head[:SHORT_HEAD]
    return f"detached @ {head}" if head else "detached"


def tree_cell(dirty: bool | None, *, dark: bool) -> ListCell:
    if dirty is None:
        return Text("unknown", style="dim")
    if dirty:
        return Text("dirty", style=DIRTY_COLORS[dark])
    return "clean"


def freshness_color(freshness: str, *, dark: bool) -> str:
    """Choose emphasis for freshness that points at the target's Diagnostics."""
    if freshness == "unavailable":
        return UNAVAILABLE_COLORS[dark]
    return STALE_COLORS[dark]


def sessions_cell(states: Sequence[RunState], *, dark: bool) -> ListCell:
    """Report the total number of located Agent Sessions."""
    return str(len(states)) if states else "-"


def activity_cell(states: Sequence[RunState], *, dark: bool) -> Text:
    """Render the liveliest Agent Session state, or blank when absent."""
    if not states:
        return Text("")
    glyph = STATE_GLYPHS[min(states, key=lambda item: STATE_ORDER[item])]
    return Text(glyph.symbol, style=glyph.style(dark=dark))
