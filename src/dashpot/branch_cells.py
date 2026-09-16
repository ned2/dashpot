"""The Branches pane's rendered values: its columns, Glyphs and cells.

Everything here turns a queried `BranchListRow` into what the pane shows;
the query itself lives in ``branch_list``. Each column carries its own
description and the Glyphs its cells render, which is what both a header
tooltip and the Legend's Branches sections are built from.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from rich.text import Text

from .ages import relative_age
from .branch_list import BranchListResult, BranchListRow, integration_summary
from .glyphs import (
    ACTIVITY_COLUMN_GLYPH,
    ACTIVITY_LEGEND,
    ACTIVITY_WIDTH,
    ATTENTION_COLORS,
    BAD_COLORS,
    Glyph,
)
from .list_rows import ListCell, ListColumn, ListRow, truncate_end
from .model import Branch, IntegrationState
from .worktree_cells import (
    activity_cell,
    activity_description,
    sessions_cell,
    sessions_description,
)

NAME_LIMIT = 48
# Presence and relation states are glyph-only so their columns stay narrow.
REF_PRESENT_GLYPH = Glyph("✓", "a Branch ref exists in this location")
IN_SYNC_GLYPH = Glyph("=", "in sync with upstream")
AHEAD_BEHIND_GLYPH = Glyph(
    "↑2 ↓1", "commits ahead of / behind upstream", ATTENTION_COLORS
)
NO_UPSTREAM_GLYPH = Glyph("∅", "no upstream is configured", ATTENTION_COLORS)
UPSTREAM_GONE_GLYPH = Glyph(
    "✗", "upstream gone: it was configured and no longer exists", BAD_COLORS
)
NO_LOCAL_REF_GLYPH = Glyph("-", "remote-only, so there is no local upstream")
# INTEGRATED summarizes every ref the row represents, so its Glyphs speak of
# all of them; the per-ref counts stay in the Cleanup preview.
INTEGRATED_GLYPH = Glyph(
    "⊆", "every ref's commits are reachable from the Integration Branch"
)
CONTENT_INTEGRATED_GLYPH = Glyph(
    "≡",
    "every ref has landed, at least one by content only (squash-merged): "
    "the Integration Branch holds its work, not its commits",
)
UNINTEGRATED_GLYPH = Glyph(
    "↑",
    "some ref has commits the Integration Branch neither reaches nor holds "
    "the content of; the Cleanup preview counts them per target",
    ATTENTION_COLORS,
)
NO_INTEGRATION_GLYPH = Glyph(
    "⊘",
    "no ref is known unintegrated, but a comparison is unavailable",
    BAD_COLORS,
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
INTEGRATION_GLYPHS: dict[IntegrationState, Glyph] = {
    "integrated": INTEGRATED_GLYPH,
    "content-integrated": CONTENT_INTEGRATED_GLYPH,
    "unintegrated": UNINTEGRATED_GLYPH,
    "unknown": NO_INTEGRATION_GLYPH,
}

# What each column shows, said once for the header tooltip and the Legend.
# A tooltip is a box beside the mouse, so each description is one dense
# sentence or two rather than a paragraph.
ACTIVITY_DESCRIPTION = activity_description("on this Branch")
SESSIONS_DESCRIPTION = sessions_description("on this Branch")
NAME_DESCRIPTION = (
    "the branch name; one row carries its local Branch and every same-name "
    f"Remote-Tracking Branch together, clipped past {NAME_LIMIT} characters"
)
LOCAL_DESCRIPTION = "whether a local Branch exists: a ref under refs/heads"
# The check is the Repository's copy, not the remote itself: a
# Remote-Tracking Branch can outlive the Branch at the remote until a fetch
# prunes it, so the description says what the check means and where its age is.
REMOTE_DESCRIPTION = (
    "whether a Remote-Tracking Branch exists as of the last fetch, which can "
    "outlive the Branch at the remote until pruned; the pane border carries "
    "the fetch age and f fetches and prunes, including inside either Cleanup "
    "dialog"
)
UPSTREAM_DESCRIPTION = (
    "how the local Branch relates to its configured upstream, which need not "
    "share its name; a remote-only row has none"
)
# INTEGRATED is the prerequisite for x, not its verdict: the row sums up
# every ref it represents, while the Cleanup preview judges each concrete
# target on its own, so the description keeps the two apart.
INTEGRATION_DESCRIPTION = (
    "whether every ref this row represents has landed on the Integration "
    "Branch: the local Branch and each same-name Remote-Tracking Branch as of "
    "the last fetch, not a differently named upstream. Known unintegrated "
    "work outranks missing evidence, which never reads as integrated. An "
    "integrated row is the prerequisite for the Cleanup x opens, not a "
    "verdict on its targets: the preview checks each target's own "
    "integration and commit count, blockers, selection, and confirmation"
)
COMMIT_DESCRIPTION = "the age of the newest commit across the row's refs"

BRANCH_COLUMNS: tuple[ListColumn, ...] = (
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
    ListColumn("name", "BRANCH", description=NAME_DESCRIPTION),
    ListColumn(
        "local",
        "LOCAL",
        justify="center",
        description=LOCAL_DESCRIPTION,
        glyphs=PRESENCE_LEGEND,
    ),
    ListColumn(
        "remote",
        "REMOTE",
        justify="center",
        description=REMOTE_DESCRIPTION,
        glyphs=PRESENCE_LEGEND,
    ),
    ListColumn(
        "upstream",
        "UPSTREAM",
        justify="center",
        description=UPSTREAM_DESCRIPTION,
        glyphs=UPSTREAM_LEGEND,
    ),
    ListColumn(
        "integrated",
        "INTEGRATED",
        justify="center",
        description=INTEGRATION_DESCRIPTION,
        glyphs=INTEGRATION_LEGEND,
    ),
    ListColumn("commit", "LAST COMMIT", description=COMMIT_DESCRIPTION),
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
        integration_cell(integration_summary(row), dark=dark),
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


def integration_cell(summary: IntegrationState, *, dark: bool) -> ListCell:
    """Report whether the Integration Branch holds every ref the row represents."""
    glyph = INTEGRATION_GLYPHS[summary]
    style = glyph.style(dark=dark)
    return Text(glyph.symbol, style=style) if style else glyph.symbol


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
