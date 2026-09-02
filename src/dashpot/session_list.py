"""The Sessions pane read model: every active Agent Session, once.

An Agent Session is observed as one `AgentRun` record whether it came from a
hook record, a Work Store record, or both correlated by process; the
observer has already made that join, so each record here is one row. The
optional active Issue work is a relationship on the row (the Work Store is
the sole authority for it), never a second row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rich.text import Text

from .glyphs import Glyph
from .issue_cells import relative_age
from .issue_list import row_key
from .issue_profile import IssueProfile
from .list_pane import ListCell, ListColumn, ListRow, truncate_end, truncate_start
from .model import AgentRun, ProjectObservation, RunState, WorkspaceSnapshot

HARNESS_LABELS = {"codex": "Codex", "claude-code": "Claude Code"}
STATE_ORDER: dict[RunState, int] = {"running": 0, "waiting": 1, "unknown": 2}
# GitHub Primer emphasis colours: running is success, waiting is attention,
# unknown is muted; each pair is (light theme, dark theme). The fill of the
# circle is the liveliness, which is why the family reads as one.
STATE_GLYPHS: dict[RunState, Glyph] = {
    "running": Glyph("●", "an Agent Session is running", ("#1a7f37", "#3fb950")),
    "waiting": Glyph("◐", "an Agent Session is waiting", ("#9a6700", "#d29922")),
    "unknown": Glyph(
        "○", "an Agent Session in an unknown state", ("#59636e", "#8b949e")
    ),
}
LEGEND = tuple(STATE_GLYPHS[state] for state in STATE_ORDER)
OUTSIDE_PROJECT_TEXT = "outside Project"
UNBOUND_ISSUE_TEXT = "no active Issue work"
# Long values are clipped so a row stays scannable; the scan-level fact is
# the tail of a path and the head of a branch or title.
PATH_LIMIT = 28
BRANCH_LIMIT = 24
ISSUE_LIMIT = 36

SESSION_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("state", "STATE"),
    ListColumn("harness", "HARNESS"),
    ListColumn("target", "TARGET"),
    ListColumn("branch", "BRANCH"),
    ListColumn("issue", "ISSUE"),
    ListColumn("directory", "DIRECTORY"),
    ListColumn("activity", "ACTIVITY"),
)


@dataclass(frozen=True, slots=True)
class SessionListRow:
    """One active Agent Session with its Project and any bound Issue joined."""

    key: str
    session: AgentRun
    project: ProjectObservation | None
    issue: IssueProfile | None = None

    @property
    def bound_issue_id(self) -> str | None:
        if self.issue is not None:
            return self.issue.id
        return self.session.issue_id


@dataclass(frozen=True, slots=True)
class SessionListResult:
    rows: tuple[SessionListRow, ...]
    revision: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)


def query_session_list(
    snapshot: WorkspaceSnapshot, *, revision: int = 0
) -> SessionListResult:
    """Query the Sessions pane rows from complete observed state."""
    projects: dict[str, ProjectObservation] = {}
    issues: dict[tuple[str, str], IssueProfile] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            issues[project.project_id, issue.id] = issue
    agent_runs: dict[str, AgentRun] = {}
    for run in snapshot.agent_runs:
        if run.id in agent_runs:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        agent_runs[run.id] = run
    return _query_indexed_session_list(
        projects=projects,
        issues=issues,
        agent_runs=agent_runs,
        issue_runs=snapshot.issue_runs,
        revision=revision,
    )


def _query_indexed_session_list(
    *,
    projects: Mapping[str, ProjectObservation],
    issues: Mapping[tuple[str, str], IssueProfile],
    agent_runs: Mapping[str, AgentRun],
    issue_runs: Mapping[str, Sequence[str]],
    revision: int,
) -> SessionListResult:
    # Accepted bindings win over the record's own hint so the pane agrees
    # with the Issue table about which Issue a session is working on.
    bound_issue_by_run = {
        run_id: issue_id
        for issue_id, run_ids in issue_runs.items()
        for run_id in run_ids
    }
    rows = []
    for run in agent_runs.values():
        project = projects.get(run.observation_project_id)
        issue_id = bound_issue_by_run.get(run.id, run.issue_id)
        issue = (
            issues.get((run.observation_project_id, issue_id))
            if issue_id is not None
            else None
        )
        rows.append(SessionListRow(row_key("session", run.id), run, project, issue))
    rows.sort(key=_sort_key)
    return SessionListResult(tuple(rows), revision)


def _sort_key(row: SessionListRow) -> tuple[int, int, str, str]:
    """State first, then the most recent activity, never a bare identity."""
    session = row.session
    activity = session.last_activity_at
    return (
        STATE_ORDER[session.state],
        0 if activity else 1,
        _descending(activity or ""),
        session.id,
    )


def _descending(value: str) -> str:
    """Invert an ISO-8601 timestamp so an ascending sort lists newest first."""
    return "".join(chr(0x10FFFF - ord(character)) for character in value)


def shows_target(result: SessionListResult) -> bool:
    """Whether TARGET tells the rows apart, or repeats one checkout on each.

    A Project is usually one Worktree, and then the column is the same path
    on every row; it earns its width once the sessions are spread across
    linked Worktrees or independent clones, or once one of them is outside
    the Project, which is a fact and not a path.
    """
    if not result.rows:
        return True
    if any(row.project is None for row in result.rows):
        return True
    return len({row.session.observation_target for row in result.rows}) > 1


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
    return Text(f"{glyph.symbol} {state}", style=glyph.style(dark=dark))


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


def directory_within_target(
    directory: str | None, target: str | None, *, home: Path | None = None
) -> str:
    """A working directory relative to its Observation Target, or in full."""
    if not directory:
        return "-"
    if target:
        try:
            relative = Path(directory).relative_to(target)
        except ValueError:
            pass
        else:
            return str(relative)
    return abbreviate_path(directory, home=home)


def abbreviate_path(path: str | None, *, home: Path | None = None) -> str:
    """Shorten a path under the home directory to its ``~`` form."""
    if not path:
        return "-"
    root = home if home is not None else Path.home()
    try:
        relative = Path(path).relative_to(root)
    except ValueError:
        return path
    return f"~/{relative}" if str(relative) != "." else "~"
