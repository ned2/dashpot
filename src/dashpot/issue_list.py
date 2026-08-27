from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from .model import AgentRun, Issue, ProjectObservation, RunState, WorkspaceSnapshot


IssueState = Literal["open", "closed"]
RowKind = Literal["issue", "project", "agent-run"]


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    states: frozenset[IssueState] = frozenset({"open"})
    text: str = ""


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    kind: RowKind
    project: ProjectObservation
    issue: Issue | None = None
    run: AgentRun | None = None
    observed_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[RunState, ...] = ()
    empty_message: str | None = None


@dataclass(frozen=True, slots=True)
class IssueListResult:
    rows: tuple[IssueListRow, ...]
    matched_issue_count: int
    observed_issue_count: int


def query_issue_list(
    snapshot: WorkspaceSnapshot,
    query: IssueListQuery = IssueListQuery(),
) -> IssueListResult:
    """Query source-neutral Issue-list rows from complete observed state."""
    issue_id_counts = Counter(
        issue["id"]
        for project in snapshot.projects
        if project.snapshot
        for issue in project.snapshot.issues
    )
    runs = snapshot.agent_runs
    issue_runs = snapshot.issue_runs
    matched_runs = {
        run_id for run_ids in issue_runs.values() for run_id in run_ids
    }
    runs_by_id = {run.id: run for run in runs}
    rows: list[IssueListRow] = []
    observed_issue_count = 0
    matched_issue_count = 0
    for project in snapshot.projects:
        issues = project.snapshot.issues if project.snapshot else []
        observed_issue_count += len(issues)
        search = query.text.strip().casefold()
        visible_issues = [
            issue
            for issue in issues
            if issue["state"] in query.states
            and (not search or search in _searchable_issue_text(issue, project))
        ]
        project_has_unmatched_run = any(
            run.id not in matched_runs
            and run.observation_project_id == project.project_id
            for run in runs
        )
        if not visible_issues and not project_has_unmatched_run:
            empty_message = (
                "source unavailable"
                if project.status == "unavailable"
                else _empty_issue_message(query)
            )
            rows.append(
                IssueListRow(
                    row_key("project", project.project_id),
                    "project",
                    project,
                    empty_message=empty_message,
                )
            )
        for issue in visible_issues:
            matched_issue_count += 1
            key = (
                row_key("issue", issue["id"])
                if issue_id_counts[issue["id"]] == 1
                else row_key("issue", project.project_id, issue["id"])
            )
            bound_run_ids = issue_runs.get(issue["id"], [])
            observed_runs = tuple(
                runs_by_id[run_id]
                for run_id in bound_run_ids
                if run_id in runs_by_id
            )
            session_states: tuple[RunState, ...] = tuple(
                runs_by_id[run_id].state if run_id in runs_by_id else "unknown"
                for run_id in bound_run_ids
            )
            rows.append(
                IssueListRow(
                    key,
                    "issue",
                    project,
                    issue=issue,
                    observed_runs=observed_runs,
                    session_states=session_states,
                )
            )
    projects_by_id = {project.project_id: project for project in snapshot.projects}
    for run in runs:
        if run.id in matched_runs:
            continue
        project = projects_by_id.get(run.observation_project_id)
        if project is None:
            continue
        rows.append(
            IssueListRow(
                row_key("run", run.id),
                "agent-run",
                project,
                run=run,
            )
        )
    return IssueListResult(
        tuple(rows),
        matched_issue_count,
        observed_issue_count,
    )


def row_key(kind: str, *identities: str) -> str:
    """Encode opaque identities into an unambiguous row key."""
    return json.dumps([kind, *identities], ensure_ascii=False, separators=(",", ":"))


def _empty_issue_message(query: IssueListQuery) -> str:
    if query.text.strip():
        return "no Issues match the current filters"
    if query.states == frozenset({"open"}):
        return "no open Issues"
    if query.states == frozenset({"closed"}):
        return "no closed Issues"
    if query.states == frozenset({"open", "closed"}):
        return "no Issues"
    return "no Issues match the current filters"


def _searchable_issue_text(issue: Issue, project: ProjectObservation) -> str:
    values = [
        project.display_label,
        str(issue.get("title", "")),
        str(issue.get("reference", "")),
        str(issue.get("body", "")),
        *(str(label) for label in issue.get("labels", [])),
        *(str(assignee) for assignee in issue.get("assignees", [])),
    ]
    milestone = issue.get("milestone")
    if isinstance(milestone, dict):
        values.append(str(milestone.get("title", "")))
    return "\n".join(values).casefold()
