from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .issue_search import parse_issue_search
from .model import AgentRun, Issue, ProjectObservation, RunState, WorkspaceSnapshot

IssueState = Literal["open", "closed"]
RowKind = Literal["issue"]


class IssueSearchField(StrEnum):
    PROJECT = "project"
    NUMBER = "number"
    ASSIGNEES = "assignees"
    LABELS = "labels"
    AUTHOR = "author"
    MILESTONE = "milestone"
    TYPE = "type"
    TITLE = "title"

    def values(self, issue: Issue, project: ProjectObservation) -> tuple[str, ...]:
        if self is IssueSearchField.PROJECT:
            return (project.display_label,)
        if self is IssueSearchField.NUMBER:
            return (f"#{issue['number']}",)
        if self is IssueSearchField.ASSIGNEES:
            return tuple(str(value) for value in issue.get("assignees", []))
        if self is IssueSearchField.LABELS:
            return tuple(str(value) for value in issue.get("labels", []))
        if self is IssueSearchField.AUTHOR:
            return _optional_value(issue.get("author"))
        if self is IssueSearchField.MILESTONE:
            return _optional_value(issue.get("milestone"))
        if self is IssueSearchField.TYPE:
            return _optional_value(issue.get("issueType"))
        return (str(issue.get("title", "")),)


def _optional_value(value: object) -> tuple[str, ...]:
    return (str(value),) if value else ()


@dataclass(frozen=True, slots=True)
class IssueListQuery:
    states: frozenset[IssueState] = frozenset({"open"})
    text: str = ""
    search_fields: frozenset[IssueSearchField] = frozenset(IssueSearchField)


@dataclass(frozen=True, slots=True)
class IssueListRow:
    key: str
    kind: RowKind
    project: ProjectObservation
    issue: Issue | None = None
    observed_runs: tuple[AgentRun, ...] = ()
    project_runs: tuple[AgentRun, ...] = ()
    session_states: tuple[RunState, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueListResult:
    rows: tuple[IssueListRow, ...]
    matched_issue_count: int
    observed_issue_count: int
    revision: int = 0
    # Lifecycle split of every observed Issue, before any filter, so the
    # header can show both counts the way a tracker's feed does.
    open_issue_count: int = 0
    closed_issue_count: int = 0


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
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        projects[project.project_id] = project
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            key = (project.project_id, issue["id"])
            if key in issues:
                raise ValueError(
                    f"Duplicate Issue Identity {issue['id']} in {project.project_id}"
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
    issue_id_counts = Counter(issue_id for _project_id, issue_id in issues)
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
    open_issue_count = 0
    search_terms = tuple(
        term.casefold() for term in parse_issue_search(query.text).terms
    )
    for project in projects.values():
        project_issues = issues_by_project[project.project_id]
        observed_issue_count += len(project_issues)
        open_issue_count += sum(
            1 for issue in project_issues if issue["state"] == "open"
        )
        visible_issues = [
            issue
            for issue in project_issues
            if issue["state"] in query.states
            and _matches_search(issue, project, query.search_fields, search_terms)
        ]
        # Only Issues are rows, like an Issue tracker's feed: a Project with
        # nothing visible contributes no placeholder.
        for issue in visible_issues:
            matched_issue_count += 1
            key = (
                row_key("issue", issue["id"])
                if issue_id_counts[issue["id"]] == 1
                else row_key("issue", project.project_id, issue["id"])
            )
            bound_run_ids = issue_runs.get(issue["id"], [])
            observed_runs = tuple(
                agent_runs[run_id] for run_id in bound_run_ids if run_id in agent_runs
            )
            session_states: tuple[RunState, ...] = tuple(
                agent_runs[run_id].state if run_id in agent_runs else "unknown"
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
    # Agent Runs without an Issue Binding are not Work rows; they remain
    # visible through each Project's observed-run facts (project_runs).
    return IssueListResult(
        tuple(rows),
        matched_issue_count,
        observed_issue_count,
        revision,
        open_issue_count=open_issue_count,
        closed_issue_count=observed_issue_count - open_issue_count,
    )


ISSUE_STATE_CYCLE: tuple[frozenset[IssueState], ...] = (
    frozenset({"open"}),
    frozenset({"closed"}),
    frozenset({"open", "closed"}),
)


def next_issue_states(states: frozenset[IssueState]) -> frozenset[IssueState]:
    """Flip the lifecycle filter open -> closed -> all -> open."""
    if states in ISSUE_STATE_CYCLE:
        index = ISSUE_STATE_CYCLE.index(states)
        return ISSUE_STATE_CYCLE[(index + 1) % len(ISSUE_STATE_CYCLE)]
    return ISSUE_STATE_CYCLE[0]


def issue_count_text(result: IssueListResult, query: IssueListQuery) -> str:
    """Summarize the list like a tracker feed: ``3 of 12 open · 28 closed``.

    The active lifecycle scope comes first with its matched count when a
    search narrows it; the other lifecycle count follows so the split is
    always visible.
    """
    counts = {"open": result.open_issue_count, "closed": result.closed_issue_count}
    if query.states == frozenset({"open", "closed"}):
        scope = _scope_count(result.matched_issue_count, result.observed_issue_count)
        return f"{scope} Issues · {counts['open']} open, {counts['closed']} closed"
    if query.states == frozenset({"closed"}):
        active, other = "closed", "open"
    else:
        active, other = "open", "closed"
    scope = _scope_count(result.matched_issue_count, counts[active])
    return f"{scope} {active} · {counts[other]} {other}"


def _scope_count(matched: int, total: int) -> str:
    return str(total) if matched == total else f"{matched} of {total}"


def row_key(kind: str, *identities: str) -> str:
    """Encode opaque identities into an unambiguous row key."""
    return json.dumps([kind, *identities], ensure_ascii=False, separators=(",", ":"))


def empty_issue_message(query: IssueListQuery) -> str:
    """Explain an empty Issue list in terms of the active query."""
    if parse_issue_search(query.text).terms:
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
    values = [value for field in fields for value in field.values(issue, project)]
    return "\n".join(values).casefold()


def _matches_search(
    issue: Issue,
    project: ProjectObservation,
    fields: frozenset[IssueSearchField],
    terms: tuple[str, ...],
) -> bool:
    if not terms:
        return True
    searchable = _searchable_issue_text(issue, project, fields)
    return all(term in searchable for term in terms)
