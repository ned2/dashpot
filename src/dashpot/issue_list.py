from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .model import AgentRun, Issue, ProjectObservation, RunState, WorkspaceSnapshot


IssueState = Literal["open", "closed"]
RowKind = Literal["issue", "project", "agent-run"]


class IssueSearchField(StrEnum):
    PROJECT = "project"
    ASSIGNEES = "assignees"
    TITLE = "title"

    def values(
        self, issue: Issue, project: ProjectObservation
    ) -> tuple[str, ...]:
        if self is IssueSearchField.PROJECT:
            return (project.display_label,)
        if self is IssueSearchField.ASSIGNEES:
            return tuple(str(value) for value in issue.get("assignees", []))
        return (str(issue.get("title", "")),)


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    states: frozenset[IssueState] = frozenset({"open"})
    text: str = ""
    search_fields: frozenset[IssueSearchField] = frozenset(
        IssueSearchField
    )


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    kind: RowKind
    project: ProjectObservation
    issue: Issue | None = None
    run: AgentRun | None = None
    observed_runs: tuple[AgentRun, ...] = ()
    project_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[RunState, ...] = ()
    empty_message: str | None = None


@dataclass(frozen=True, slots=True)
class IssueListResult:
    rows: tuple[IssueListRow, ...]
    matched_issue_count: int
    observed_issue_count: int
    revision: int = 0


def query_issue_list(
    snapshot: WorkspaceSnapshot,
    query: IssueListQuery = IssueListQuery(),
    *,
    revision: int = 0,
) -> IssueListResult:
    """Query source-neutral Issue-list rows from complete observed state."""
    projects: dict[str, ProjectObservation] = {}
    issues: dict[tuple[str, str], Issue] = {}
    for project in snapshot.projects:
        if project.project_id in projects:
            raise ValueError(
                f"Duplicate Project Identity {project.project_id}"
            )
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            key = (project.project_id, issue["id"])
            if key in issues:
                raise ValueError(
                    f"Duplicate Issue Identity {issue['id']} in "
                    f"{project.project_id}"
                )
            issues[key] = issue
    agent_runs: dict[str, AgentRun] = {}
    for run in snapshot.agent_runs:
        if run.id in agent_runs:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        agent_runs[run.id] = run
    return _query_indexed_issue_list(
        projects=projects,
        issues=issues,
        agent_runs=agent_runs,
        issue_runs=snapshot.issue_runs,
        query=query,
        revision=revision,
    )


def _query_indexed_issue_list(
    *,
    projects: Mapping[str, ProjectObservation],
    issues: Mapping[tuple[str, str], Issue],
    agent_runs: Mapping[str, AgentRun],
    issue_runs: Mapping[str, Sequence[str]],
    query: IssueListQuery,
    revision: int,
) -> IssueListResult:
    issue_id_counts = Counter(
        issue_id for _project_id, issue_id in issues
    )
    matched_runs = {
        run_id for run_ids in issue_runs.values() for run_id in run_ids
    }
    issues_by_project: dict[str, list[Issue]] = {
        project_id: [] for project_id in projects
    }
    for (project_id, _issue_id), issue in issues.items():
        if project_id in issues_by_project:
            issues_by_project[project_id].append(issue)
    runs_by_project = {
        project.project_id: tuple(
            run
            for run in agent_runs.values()
            if run.observation_project_id == project.project_id
        )
        for project in projects.values()
    }
    rows: list[IssueListRow] = []
    observed_issue_count = 0
    matched_issue_count = 0
    for project in projects.values():
        project_issues = issues_by_project[project.project_id]
        observed_issue_count += len(project_issues)
        search = query.text.strip().casefold()
        visible_issues = [
            issue
            for issue in project_issues
            if issue["state"] in query.states
            and (
                not search
                or search
                in _searchable_issue_text(issue, project, query.search_fields)
            )
        ]
        project_has_unmatched_run = any(
            run.id not in matched_runs
            for run in runs_by_project[project.project_id]
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
                    project_runs=runs_by_project[project.project_id],
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
                agent_runs[run_id]
                for run_id in bound_run_ids
                if run_id in agent_runs
            )
            session_states: tuple[RunState, ...] = tuple(
                agent_runs[run_id].state
                if run_id in agent_runs
                else "unknown"
                for run_id in bound_run_ids
            )
            rows.append(
                IssueListRow(
                    key,
                    "issue",
                    project,
                    issue=issue,
                    observed_runs=observed_runs,
                    project_runs=runs_by_project[project.project_id],
                    session_states=session_states,
                )
            )
    for run in agent_runs.values():
        if run.id in matched_runs:
            continue
        project = projects.get(run.observation_project_id)
        if project is None:
            continue
        rows.append(
            IssueListRow(
                row_key("run", run.id),
                "agent-run",
                project,
                run=run,
                project_runs=runs_by_project[project.project_id],
            )
        )
    return IssueListResult(
        tuple(rows),
        matched_issue_count,
        observed_issue_count,
        revision,
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


def _searchable_issue_text(
    issue: Issue,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
) -> str:
    values = [
        value
        for field in fields
        for value in field.values(issue, project)
    ]
    return "\n".join(values).casefold()
