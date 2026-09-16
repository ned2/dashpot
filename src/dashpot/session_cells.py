"""The Sessions pane's rendered values: its columns, state Glyphs and cells.

Everything here turns a queried `SessionListRow` into what the pane shows;
the query itself lives in ``session_list``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich.text import Text

from .core.ages import relative_age
from .core.model import AgentRun, RunState
from .glyphs import ACTIVITY_COLUMN_GLYPH, ACTIVITY_WIDTH, SESSION_STATE_GLYPHS
from .list_rows import (
    ListCell,
    ListColumn,
    ListRow,
    truncate_end,
    truncate_start,
)
from .session_list import (
    HARNESS_LABELS,
    OUTSIDE_PROJECT_TEXT,
    STATE_ORDER,
    UNBOUND_ISSUE_TEXT,
    SessionListResult,
    SessionListRow,
    abbreviate_path,
    directory_within_target,
    shows_target,
)

STATE_GLYPHS = SESSION_STATE_GLYPHS
LEGEND = tuple(STATE_GLYPHS[state] for state in STATE_ORDER)
# Long values are clipped so a row stays scannable; the scan-level fact is
# the tail of a path and the head of a branch or title.
PATH_LIMIT = 28
BRANCH_LIMIT = 24
ISSUE_LIMIT = 36

SESSION_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn(
        "state", ACTIVITY_COLUMN_GLYPH.symbol, width=ACTIVITY_WIDTH, frozen=True
    ),
    ListColumn("harness", "HARNESS"),
    ListColumn("target", "TARGET"),
    ListColumn("branch", "BRANCH"),
    ListColumn("issue", "ISSUE"),
    ListColumn("directory", "DIRECTORY"),
    ListColumn("activity", "ACTIVITY"),
)


def session_columns(result: SessionListResult) -> tuple[ListColumn, ...]:
    """The pane's columns for this result, without the ones it cannot vary."""
    if shows_target(result):
        return SESSION_COLUMNS
    return tuple(column for column in SESSION_COLUMNS if column.key != "target")


def build_session_rows(
    result: SessionListResult,
    *,
    dark: bool,
    now: datetime | None = None,
    home: Path | None = None,
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    current = now or datetime.now(UTC)
    target = shows_target(result)
    return tuple(
        ListRow(
            row.key,
            session_cells(row, dark=dark, now=current, home=home, target=target),
            issue_id=row.bound_issue_id,
        )
        for row in result.rows
    )


def session_cells(
    row: SessionListRow,
    *,
    dark: bool,
    now: datetime,
    home: Path | None = None,
    target: bool = True,
) -> tuple[ListCell, ...]:
    session = row.session
    return (
        session_state_cell(session.state, dark=dark),
        HARNESS_LABELS.get(session.harness, session.harness),
        *((session_target_cell(row, home=home),) if target else ()),
        truncate_end(session.branch or "detached", BRANCH_LIMIT),
        session_issue_cell(row),
        # Exactly one column names the Observation Target: with TARGET
        # dropped the directory has to locate itself in full.
        truncate_start(
            directory_within_target(
                session.working_directory, session.observation_target, home=home
            )
            if target
            else abbreviate_path(session.working_directory, home=home),
            PATH_LIMIT,
        ),
        activity_text(session, now),
    )


def activity_text(session: AgentRun, now: datetime) -> str:
    """How long the run has been doing what it is doing, and which that is.

    A running turn's age and an idle session's age are different facts that
    read alike as a bare age, so the cell says which one it is. A run nothing
    has observed reports when its work began rather than borrowing that
    timestamp as an activity it never saw.
    """
    if session.state == "running":
        elapsed = _elapsed(session.turn_started_at or session.last_activity_at, now)
        return f"running {elapsed}" if elapsed else "running"
    elapsed = _elapsed(session.last_activity_at, now)
    if elapsed:
        return f"idle {elapsed}"
    started = relative_age(session.started_at, now)
    return f"started {started}" if started else "-"


def _elapsed(timestamp: str | None, now: datetime) -> str | None:
    """An age as a duration: how long it has been, not when it was."""
    age = relative_age(timestamp, now)
    if age is None:
        return None
    return "<1m" if age == "just now" else age.removesuffix(" ago")


def session_target_cell(row: SessionListRow, *, home: Path | None = None) -> ListCell:
    """Where the session is, or an honest marker when that is not the Project."""
    if row.project is None:
        return Text(OUTSIDE_PROJECT_TEXT, style="dim italic")
    return truncate_start(
        abbreviate_path(row.session.observation_target, home=home), PATH_LIMIT
    )


def session_state_cell(state: RunState, *, dark: bool) -> Text:
    glyph = STATE_GLYPHS[state]
    return Text(glyph.symbol, style=glyph.style(dark=dark))


def session_issue_cell(row: SessionListRow) -> ListCell:
    """The bound Issue by number and title, or an intentional unbound value."""
    if row.issue is not None:
        return truncate_end(f"#{row.issue.number} {row.issue.title}", ISSUE_LIMIT)
    if row.bound_issue_id is not None:
        # Bound to an Issue this Project's source has not shown yet.
        return truncate_end(
            row.session.issue_reference_hint or row.bound_issue_id, ISSUE_LIMIT
        )
    return Text(UNBOUND_ISSUE_TEXT, style="dim italic")
