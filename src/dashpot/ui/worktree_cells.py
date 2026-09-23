"""The Worktrees pane's rendered values: its columns, colours and cells.

Everything here turns a queried `WorktreeListRow` into what the pane shows;
the query itself lives in ``worktree_list``. The Branches pane shares the
activity and session-count cells and their descriptions, so they are
defined here once. Each column carries its own Column Description, from
which its header tooltip and Legend section are built.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.text import Text

from ..core.model import ObservationTarget, SessionActivity
from ..observation.session_list import SESSION_STATE_ORDER, abbreviate_path
from ..observation.worktree_list import WorktreeListRow
from .glyphs import (
    ACTIVITY_COLUMN_GLYPH,
    ACTIVITY_LEGEND,
    ACTIVITY_WIDTH,
    ATTENTION_COLORS,
    BAD_COLORS,
)
from .list_rows import ListCell, ListColumn, truncate_end
from .session_cells import STATE_GLYPHS

BRANCH_LIMIT = 24
SHORT_HEAD = 7


def activity_description(where: str) -> str:
    """Describe the activity column for the rows located ``where``.

    A located session is one whose Observation Target is the row, whatever
    Issue it works on; the Issues table's column of the same Glyph summarizes
    bound Agent Runs instead.
    """
    return (
        f"the liveliest Agent Session located {where}, running before waiting "
        "before orphaned before unknown, or blank when none is; a session "
        "counts by where its harness runs, not by any Issue it is bound to"
    )


def sessions_description(where: str) -> str:
    """Describe the SESSIONS count column for the rows located ``where``."""
    return (
        f"how many active Agent Sessions are located {where}, whatever their "
        "state, or - when none is"
    )


# What each column shows, said once for the header tooltip and the Legend.
ACTIVITY_DESCRIPTION = activity_description("at this Worktree")
SESSIONS_DESCRIPTION = sessions_description("at this Worktree")
PATH_DESCRIPTION = (
    "the Worktree's path, ~-abbreviated and never clipped, so the pane "
    "scrolls sideways for a long one; followed by stale while the topology "
    "is retained from an earlier observation, or unavailable when observing "
    "the Worktree failed, either detailed in Diagnostics"
)
KIND_DESCRIPTION = (
    "the Worktree's place in Git's topology: main is the Repository's main "
    "working tree, and linked a working tree added beside it; the pane lists "
    "main first, then linked by path"
)
BRANCH_DESCRIPTION = (
    "the Branch checked out at the Worktree, clipped past "
    f"{BRANCH_LIMIT} characters, or detached @ with the {SHORT_HEAD}-character "
    "HEAD of a detached checkout, detached alone when that HEAD is unknown"
)
TREE_DESCRIPTION = (
    "whether the working tree carries uncommitted changes: clean, dirty, or "
    "unknown when Git could not answer; a Cleanup removes only a clean linked "
    "Worktree"
)

WORKTREE_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn(
        "activity",
        ACTIVITY_COLUMN_GLYPH.symbol,
        width=ACTIVITY_WIDTH,
        frozen=True,
        description=ACTIVITY_DESCRIPTION,
        glyphs=ACTIVITY_LEGEND,
    ),
    ListColumn(
        "sessions", "SESSIONS", justify="center", description=SESSIONS_DESCRIPTION
    ),
    ListColumn("path", "PATH", description=PATH_DESCRIPTION),
    ListColumn("kind", "KIND", description=KIND_DESCRIPTION),
    ListColumn("branch", "BRANCH", description=BRANCH_DESCRIPTION),
    ListColumn("tree", "TREE", description=TREE_DESCRIPTION),
)


def worktree_cells(
    row: WorktreeListRow, *, dark: bool, home: Path | None = None
) -> tuple[ListCell, ...]:
    target = row.target
    return (
        activity_cell(tuple(session.activity for session in row.sessions), dark=dark),
        sessions_cell(tuple(session.activity for session in row.sessions), dark=dark),
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
        return Text("dirty", style=ATTENTION_COLORS[dark])
    return "clean"


def freshness_color(freshness: str, *, dark: bool) -> str:
    """Choose emphasis for freshness that points at the target's Diagnostics."""
    if freshness == "unavailable":
        return BAD_COLORS[dark]
    return ATTENTION_COLORS[dark]


def sessions_cell(states: Sequence[SessionActivity], *, dark: bool) -> ListCell:
    """Report the total number of located Agent Sessions."""
    return str(len(states)) if states else "-"


def activity_cell(states: Sequence[SessionActivity], *, dark: bool) -> Text:
    """Render the liveliest Agent Session state, or blank when absent."""
    if not states:
        return Text("")
    glyph = STATE_GLYPHS[min(states, key=lambda item: SESSION_STATE_ORDER[item])]
    return Text(glyph.symbol, style=glyph.style(dark=dark))
