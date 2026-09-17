"""The Sessions pane read model: every active Agent Session, once.

An Agent Session is observed as one `AgentRun` record whether it came from a
hook record, a Work Store record, or both correlated by process; the
observer has already made that join, so each record here is one row. The
optional active Issue work is a relationship on the row (the Work Store is
the sole authority for it), never a second row.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.issue_profile import IssueProfile
from ..core.model import AgentRun, ProjectObservation, RunState
from .issue_list import row_key
from .list_result import ListResult

HARNESS_LABELS = {"codex": "Codex", "claude-code": "Claude Code"}
SESSION_STATE_ORDER: dict[RunState, int] = {"running": 0, "waiting": 1, "unknown": 2}
OUTSIDE_PROJECT_TEXT = "outside Project"
UNBOUND_ISSUE_TEXT = "no active Issue work"


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


def query_indexed_session_list(
    *,
    projects: Mapping[str, ProjectObservation],
    issues: Mapping[tuple[str, str], IssueProfile],
    agent_runs: Mapping[str, AgentRun],
    issue_runs: Mapping[str, Sequence[str]],
    revision: int,
) -> ListResult[SessionListRow, None]:
    # Accepted bindings win over the record's own hint so the pane agrees
    # with the Issue table about which Issue a session is working on.
    bound_issue_by_run = {
        run_id: issue_id
        for issue_id, run_ids in issue_runs.items()
        for run_id in run_ids
    }
    identities = Counter(
        (run.harness, run.session_id)
        for run in agent_runs.values()
        if run.session_id is not None
    )
    rows = []
    for run in agent_runs.values():
        project = projects.get(run.observation_project_id)
        issue_id = bound_issue_by_run.get(run.id, run.issue_id)
        issue = (
            issues.get((run.observation_project_id, issue_id))
            if issue_id is not None
            else None
        )
        # Agent Runs change on Issue work switches; the enclosing conversation
        # keeps its cursor. Conflicting records still need separately visible rows.
        key = (
            row_key("session", run.harness, run.session_id)
            if run.session_id is not None
            and identities[run.harness, run.session_id] == 1
            else row_key("session", run.id)
        )
        rows.append(SessionListRow(key, run, project, issue))
    rows.sort(key=_sort_key)
    return ListResult(rows=tuple(rows), summary=None, revision=revision)


def _sort_key(row: SessionListRow) -> tuple[int, int, str, str]:
    """State first, then the most recent activity, never a bare identity."""
    session = row.session
    activity = session.last_activity_at
    return (
        SESSION_STATE_ORDER[session.state],
        0 if activity else 1,
        _descending(activity or ""),
        session.id,
    )


def _descending(value: str) -> str:
    """Invert an ISO-8601 timestamp so an ascending sort lists newest first."""
    return "".join(chr(0x10FFFF - ord(character)) for character in value)


def shows_target(result: ListResult[SessionListRow, None]) -> bool:
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
