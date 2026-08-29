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

from .issue_list import row_key
from .issue_table import relative_age
from .list_pane import ListCell, ListColumn, ListRow, truncate_end, truncate_start
from .model import AgentRun, Issue, ProjectObservation, RunState, WorkspaceSnapshot

HARNESS_LABELS = {"codex": "Codex", "claude-code": "Claude Code"}
STATE_ORDER: dict[RunState, int] = {"running": 0, "waiting": 1, "unknown": 2}
# GitHub Primer emphasis colours: running is success, waiting is attention,
# unknown is muted; each pair is (light theme, dark theme).
STATE_STYLES: dict[RunState, tuple[str, str, str]] = {
    "running": ("●", "#1a7f37", "#3fb950"),
    "waiting": ("◐", "#9a6700", "#d29922"),
    "unknown": ("○", "#59636e", "#8b949e"),
}
UNBOUND_ISSUE_TEXT = "no active Issue work"
# Long values are clipped so a row stays scannable; the scan-level fact is
# the tail of a path and the head of a branch or title.
PATH_LIMIT = 28
BRANCH_LIMIT = 24
ISSUE_LIMIT = 36

SESSION_COLUMNS: tuple[ListColumn, ...] = (
    ListColumn("state", "STATE"),
    ListColumn("harness", "HARNESS"),
    ListColumn("project", "PROJECT"),
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
    issue: Issue | None = None

    @property
    def bound_issue_id(self) -> str | None:
        if self.issue is not None:
            return str(self.issue["id"])
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
    issues: dict[tuple[str, str], Issue] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            issues[project.project_id, issue["id"]] = issue
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
    issues: Mapping[tuple[str, str], Issue],
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


def build_session_rows(
    result: SessionListResult,
    *,
    dark: bool,
    now: datetime | None = None,
    home: Path | None = None,
) -> tuple[ListRow, ...]:
    """Render the query result as pane rows carrying every scan-level fact."""
    current = now or datetime.now(UTC)
    return tuple(
        ListRow(
            row.key,
            session_cells(row, dark=dark, now=current, home=home),
            project_id=row.session.observation_project_id,
            issue_id=row.bound_issue_id,
        )
        for row in result.rows
    )


def session_cells(
    row: SessionListRow, *, dark: bool, now: datetime, home: Path | None = None
) -> tuple[ListCell, ...]:
    session = row.session
    return (
        session_state_cell(session.state, dark=dark),
        HARNESS_LABELS.get(session.harness, session.harness),
        row.project.display_label
        if row.project is not None
        else session.observation_project_id,
        truncate_start(
            abbreviate_path(session.observation_target, home=home), PATH_LIMIT
        ),
        truncate_end(session.branch or "detached", BRANCH_LIMIT),
        session_issue_cell(row),
        truncate_start(
            directory_within_target(
                session.working_directory, session.observation_target, home=home
            ),
            PATH_LIMIT,
        ),
        relative_age(session.last_activity_at, now) or "-",
    )


def session_state_cell(state: RunState, *, dark: bool) -> Text:
    glyph, light_color, dark_color = STATE_STYLES[state]
    return Text(f"{glyph} {state}", style=dark_color if dark else light_color)


def session_issue_cell(row: SessionListRow) -> ListCell:
    """The bound Issue by number and title, or an intentional unbound value."""
    if row.issue is not None:
        return truncate_end(f"#{row.issue['number']} {row.issue['title']}", ISSUE_LIMIT)
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
