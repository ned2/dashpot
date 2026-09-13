"""The Branches pane's rendered values: its columns, Glyphs and cells.

Everything here turns a queried `BranchListRow` into what the pane shows;
the query itself lives in ``branch_list``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from rich.text import Text

from .ages import relative_age
from .branch_list import BranchListResult, BranchListRow, integration_subject
from .glyphs import ACTIVITY_COLUMN_GLYPH, ACTIVITY_WIDTH, Glyph
from .list_rows import ListCell, ListColumn, ListRow, truncate_end
from .model import Branch
from .worktree_cells import (
    DIRTY_COLORS,
    UNAVAILABLE_COLORS,
    activity_cell,
    sessions_cell,
)

NAME_LIMIT = 48
# Presence and relation states are glyph-only so their columns stay narrow.
REF_PRESENT_GLYPH = Glyph("✓", "a Branch ref exists in this location")
IN_SYNC_GLYPH = Glyph("=", "in sync with upstream")
AHEAD_BEHIND_GLYPH = Glyph("↑2 ↓1", "commits ahead of / behind upstream", DIRTY_COLORS)
NO_UPSTREAM_GLYPH = Glyph("∅", "no upstream is configured", DIRTY_COLORS)
UPSTREAM_GONE_GLYPH = Glyph(
    "✗", "upstream gone: it was configured and no longer exists", UNAVAILABLE_COLORS
)
NO_LOCAL_REF_GLYPH = Glyph("-", "remote-only, so there is no local upstream")
INTEGRATED_GLYPH = Glyph(
    "⊆", "all Branch commits are reachable from the Integration Branch"
)
UNINTEGRATED_GLYPH = Glyph(
    "↑2",
    "commits not reachable from the Integration Branch",
    DIRTY_COLORS,
)
CONTENT_INTEGRATED_GLYPH = Glyph(
    "≡",
    "the Integration Branch holds the Branch's content, though its commits "
    "are not reachable (squash-merged)",
)
NO_INTEGRATION_GLYPH = Glyph(
    "⊘", "no Integration Branch comparison is available", UNAVAILABLE_COLORS
)
PRESENCE_LEGEND = (REF_PRESENT_GLYPH,)
UPSTREAM_LEGEND = (
    IN_SYNC_GLYPH,
    AHEAD_BEHIND_GLYPH,
    NO_UPSTREAM_GLYPH,
    UPSTREAM_GONE_GLYPH,
    NO_LOCAL_REF_GLYPH,
)
INTEGRATION_LEGEND = (
    INTEGRATED_GLYPH,
    CONTENT_INTEGRATED_GLYPH,
    UNINTEGRATED_GLYPH,
    NO_INTEGRATION_GLYPH,
)
LEGEND = PRESENCE_LEGEND + UPSTREAM_LEGEND + INTEGRATION_LEGEND

BRANCH_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn(
        "activity", ACTIVITY_COLUMN_GLYPH.symbol, width=ACTIVITY_WIDTH, frozen=True
    ),
    ListColumn("sessions", "SESSIONS", justify="center"),
    ListColumn("name", "BRANCH"),
    ListColumn("local", "LOCAL", justify="center"),
    ListColumn("remote", "REMOTE", justify="center"),
    ListColumn("upstream", "UPSTREAM", justify="center"),
    ListColumn("integrated", "INTEGRATED", justify="center"),
    ListColumn("commit", "LAST COMMIT"),
)


def build_branch_rows(
    result: BranchListResult,
    *,
    dark: bool,
    now: datetime | None = None,
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    current = now or datetime.now(UTC)
    return tuple(
        ListRow(row.key, branch_cells(row, dark=dark, now=current))
        for row in result.rows
    )


def branch_cells(
    row: BranchListRow,
    *,
    dark: bool,
    now: datetime,
) -> tuple[ListCell, ...]:
    return (
        activity_cell(tuple(session.state for session in row.sessions), dark=dark),
        sessions_cell(tuple(session.state for session in row.sessions), dark=dark),
        truncate_end(row.name, NAME_LIMIT),
        REF_PRESENT_GLYPH.symbol if row.local is not None else "",
        REF_PRESENT_GLYPH.symbol if row.remotes else "",
        sync_cell(row.local, dark=dark),
        integration_cell(integration_subject(row), dark=dark),
        relative_age(row.committed_at, now) or "-",
    )


def sync_cell(local: Branch | None, *, dark: bool) -> ListCell:
    """How the local branch relates to its upstream; remote-only rows have none."""
    if local is None:
        return NO_LOCAL_REF_GLYPH.symbol
    if local.upstream_gone:
        return Text(
            UPSTREAM_GONE_GLYPH.symbol, style=UPSTREAM_GONE_GLYPH.style(dark=dark)
        )
    if local.upstream is None:
        return Text(
            NO_UPSTREAM_GLYPH.symbol,
            style=NO_UPSTREAM_GLYPH.style(dark=dark),
        )
    parts: list[str] = []
    if local.ahead:
        parts.append(f"↑{local.ahead}")
    if local.behind:
        parts.append(f"↓{local.behind}")
    if not parts:
        return IN_SYNC_GLYPH.symbol
    return Text(" ".join(parts), style=AHEAD_BEHIND_GLYPH.style(dark=dark))


def integration_cell(branch: Branch | None, *, dark: bool) -> ListCell:
    """Report whether the Integration Branch holds the Branch's commits or content."""
    if branch is None:
        return Text(
            NO_INTEGRATION_GLYPH.symbol,
            style=NO_INTEGRATION_GLYPH.style(dark=dark),
        )
    count = branch.unintegrated_commits
    if count is None:
        return Text(
            NO_INTEGRATION_GLYPH.symbol,
            style=NO_INTEGRATION_GLYPH.style(dark=dark),
        )
    if count == 0:
        return INTEGRATED_GLYPH.symbol
    if branch.content_integrated:
        return CONTENT_INTEGRATED_GLYPH.symbol
    return Text(f"↑{count}", style=UNINTEGRATED_GLYPH.style(dark=dark))


def fetch_age_text(fetched_at: str | None, now: datetime) -> str:
    """``remote last fetched 3h ago``, or that it was never fetched."""
    age = relative_age(fetched_at, now)
    return f"remote last fetched {age}" if age else "remote never fetched"


def branch_note(
    integration_refs: Sequence[str], fetched_at: str | None, now: datetime
) -> str:
    """Name the Integration Branch and the freshness of remote facts."""
    if not integration_refs:
        integration = "integration unavailable"
    elif len(integration_refs) > 1:
        integration = "integration varies"
    else:
        ref = integration_refs[0]
        short = ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")
        integration = f"integration {short}"
    return f"{integration} · {fetch_age_text(fetched_at, now)}"
