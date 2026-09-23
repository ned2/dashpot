"""The Sessions pane's rendered values: its columns, state Glyphs and cells.

Everything here turns a queried `SessionListRow` into what the pane shows;
the query itself lives in ``session_list``. Each column carries its own
Column Description, from which its header tooltip and Legend section are
built.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.text import Text

from ..core.ages import relative_age
from ..core.model import HARNESS_DISPLAY, AgentRun, SessionActivity
from ..observation.list_result import ListResult
from ..observation.session_list import (
    OUTSIDE_PROJECT_TEXT,
    SESSION_STATE_ORDER,
    UNBOUND_ISSUE_TEXT,
    SessionListRow,
    abbreviate_path,
    directory_within_target,
    shows_target,
)
from .glyphs import (
    ACTIVITY_COLUMN_GLYPH,
    ACTIVITY_LEGEND,
    ACTIVITY_WIDTH,
    SESSION_STATE_GLYPHS,
)
from .list_rows import (
    ListCell,
    ListColumn,
    truncate_end,
    truncate_start,
)

STATE_GLYPHS = SESSION_STATE_GLYPHS
LEGEND = tuple(STATE_GLYPHS[state] for state in SESSION_STATE_ORDER)
# Long values are clipped so a row stays scannable; the scan-level fact is
# the tail of a path and the head of a branch or title.
PATH_LIMIT = 28
BRANCH_LIMIT = 24
ISSUE_LIMIT = 36

# What each column shows, said once for the header tooltip and the Legend.
# The pane lists Agent Sessions, so its activity column is the session's own
# state, unlike the Worktrees and Branches columns that summarize the
# sessions located on a row and the Issues column that summarizes the Agent
# Runs bound to one.
STATE_DESCRIPTION = (
    "this Agent Session's own lifecycle state, observed at turn boundaries: "
    "running while a turn is in progress, waiting while idle between turns, "
    "unknown when no lifecycle hook has reported it or its liveness "
    "cannot be confirmed, and orphaned when its process is gone without a "
    "graceful end while its Agent Run is still held, which resuming a Claude "
    "Code session continues and work stop --session ends; the pane lists "
    "running sessions "
    "first, then waiting, then orphaned, then unknown, each by most recent "
    "activity"
)
HARNESS_DESCRIPTION = (
    "the harness whose conversation this Agent Session is: "
    f"{' or '.join(HARNESS_DISPLAY.values())}"
)
TARGET_DESCRIPTION = (
    "the Observation Target the session is located at, ~-abbreviated and "
    f"clipped from the left past {PATH_LIMIT} characters, or "
    f"{OUTSIDE_PROJECT_TEXT} when the observed Project owns no such Worktree; "
    "the column is dropped while every listed session shares one Target and "
    "none is outside the Project, and DIRECTORY then carries the whole path"
)
BRANCH_DESCRIPTION = (
    "the Branch checked out where the session is located, clipped past "
    f"{BRANCH_LIMIT} characters, or detached when no Branch is"
)
ISSUE_DESCRIPTION = (
    "the Issue the session's active Agent Run is bound to by the Work Store's "
    "accepted Issue Binding, with the number and title the Issue Source "
    "shows for it, or its reference or identity alone while the Issue Source "
    "has not shown that Issue; "
    f"{UNBOUND_ISSUE_TEXT} when the session has not opted in; clipped past "
    f"{ISSUE_LIMIT} characters. A Worktree or Branch named for an Issue is an "
    "Issue Hint, not a binding"
)
DIRECTORY_DESCRIPTION = (
    "the session's working directory relative to its Observation Target, or "
    "the whole ~-abbreviated path while TARGET is dropped or the directory "
    "lies outside the Target; - when the harness reported none; clipped from "
    f"the left past {PATH_LIMIT} characters"
)
ACTIVITY_DESCRIPTION = (
    "how long the session has been doing what it is doing, observed at turn "
    "boundaries rather than within a turn: running 14m is the current turn's "
    "duration so far, or running alone when the turn's start is unknown, "
    "idle 14m how long it has been quiet since its last observed event, and "
    "started 3d ago an Agent Run no hook has observed yet, dated from its "
    "Work Store start; last seen 2h ago when an Orphaned Agent Run's session "
    "was last observed, followed by host restarted when the host has booted "
    "since that session's process started; - when none of those is known"
)

SESSION_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn(
        "state",
        ACTIVITY_COLUMN_GLYPH.symbol,
        width=ACTIVITY_WIDTH,
        frozen=True,
        description=STATE_DESCRIPTION,
        glyphs=ACTIVITY_LEGEND,
    ),
    ListColumn("harness", "HARNESS", description=HARNESS_DESCRIPTION),
    ListColumn("target", "TARGET", description=TARGET_DESCRIPTION),
    ListColumn("branch", "BRANCH", description=BRANCH_DESCRIPTION),
    ListColumn("issue", "ISSUE", description=ISSUE_DESCRIPTION),
    ListColumn("directory", "DIRECTORY", description=DIRECTORY_DESCRIPTION),
    ListColumn("activity", "ACTIVITY", description=ACTIVITY_DESCRIPTION),
)


def session_columns(result: ListResult[SessionListRow, None]) -> tuple[ListColumn, ...]:
    """The pane's columns for this result, without the ones it cannot vary."""
    if shows_target(result):
        return SESSION_COLUMNS
    return tuple(column for column in SESSION_COLUMNS if column.key != "target")


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
        session_state_cell(session.activity, dark=dark),
        HARNESS_DISPLAY[session.harness],
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
    timestamp as an activity it never saw. An Orphaned Agent Run is not idle:
    nothing is running it, so the cell says when it was last seen.
    """
    if session.orphaned:
        seen = relative_age(session.last_activity_at, now)
        text = f"last seen {seen}" if seen else "ended unobserved"
        return f"{text}, host restarted" if session.host_restarted else text
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


def session_state_cell(state: SessionActivity, *, dark: bool) -> Text:
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
