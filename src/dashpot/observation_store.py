from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Literal, TypeVar

from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    _query_indexed_issue_list,
    row_key,
)
from .model import (
    AgentRun,
    Diagnostic,
    Issue,
    ObservationTarget,
    ProjectObservation,
    WorkspaceSnapshot,
)


ObservationKind = Literal["workspace", "projects", "agent-runs"]
Key = TypeVar("Key")
Value = TypeVar("Value")


@dataclass(frozen=True, slots=True)
class StoreChange:
    revision: int
    kinds: frozenset[ObservationKind]
    project_ids: frozenset[str] = frozenset()
    issue_keys: frozenset[tuple[str, str]] = frozenset()
    observation_target_keys: frozenset[tuple[str, str]] = frozenset()
    agent_run_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class IssueContext:
    project: ProjectObservation
    issue: Issue
    observed_runs: tuple[AgentRun, ...]


@dataclass(frozen=True, slots=True)
class ObservedDiagnostic:
    diagnostic: Diagnostic
    project_label: str | None = None


@dataclass(frozen=True, slots=True)
class _StoreState:
    revision: int
    collected_at: str
    elapsed_ms: int
    projects: dict[str, ProjectObservation]
    issues: dict[tuple[str, str], Issue]
    observation_targets: dict[tuple[str, str], ObservationTarget]
    agent_runs: dict[str, AgentRun]
    issue_runs: dict[str, list[str]]
    diagnostics: list[Diagnostic]


class WorkspaceObservationStore:
    """Own the latest accepted workspace observations and their read models."""

    def __init__(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        self._state = _StoreState(
            revision=0,
            collected_at="",
            elapsed_ms=0,
            projects={},
            issues={},
            observation_targets={},
            agent_runs={},
            issue_runs={},
            diagnostics=[],
        )
        if snapshot is not None:
            self.replace(snapshot)

    @property
    def revision(self) -> int:
        return self._state.revision

    @property
    def has_observations(self) -> bool:
        return self._state.revision > 0

    def replace(self, snapshot: WorkspaceSnapshot) -> StoreChange:
        """Atomically accept a complete collector checkpoint."""
        before = self._state
        incoming = deepcopy(snapshot)

        accepted_projects: list[ProjectObservation] = []
        retained_issue_ids: set[str] = set()
        for project in incoming.projects:
            accepted, retained = self._preserve_last_good(
                project, before.projects
            )
            accepted_projects.append(accepted)
            retained_issue_ids.update(retained)
        projects = _projects_by_id(accepted_projects)
        issues = _issues_by_project(projects)
        observation_targets = _targets_by_project(projects)
        agent_runs = _agent_runs_by_id(incoming.agent_runs)
        issue_runs = deepcopy(incoming.issue_runs)
        _restore_retained_issue_runs(
            issue_runs,
            agent_runs,
            issues,
            retained_issue_ids,
        )

        return self._commit(
            _StoreState(
                revision=before.revision,
                collected_at=incoming.collected_at,
                elapsed_ms=incoming.elapsed_ms,
                projects=projects,
                issues=issues,
                observation_targets=observation_targets,
                agent_runs=agent_runs,
                issue_runs=issue_runs,
                diagnostics=incoming.diagnostics,
            )
        )

    def replace_project(
        self,
        observation: ProjectObservation,
        *,
        collected_at: str | None = None,
        elapsed_ms: int | None = None,
    ) -> StoreChange:
        """Atomically replace one Project while retaining its last good data.

        ``collected_at``/``elapsed_ms`` optionally record the observation that
        produced this publish as the Workspace's latest collection metadata.
        """
        before = self._state
        accepted, _retained = self._preserve_last_good(
            deepcopy(observation), before.projects
        )
        projects = dict(before.projects)
        projects[accepted.project_id] = accepted
        issues = _issues_by_project(projects)
        observation_targets = _targets_by_project(projects)

        return self._commit(
            replace(
                before,
                projects=projects,
                issues=issues,
                observation_targets=observation_targets,
                **_metadata_updates(before, collected_at, elapsed_ms),
            )
        )

    def replace_agent_runs(
        self,
        agent_runs: Sequence[AgentRun],
        issue_runs: Mapping[str, Sequence[str]],
        diagnostics: Sequence[Diagnostic] | None = None,
        *,
        collected_at: str | None = None,
        elapsed_ms: int | None = None,
    ) -> StoreChange:
        """Atomically replace Agent Runs and their accepted Issue bindings.

        Workspace-level ``diagnostics`` (agent observation and binding) are
        replaced when given; ``None`` leaves the current ones in place.
        """
        before = self._state
        accepted_agent_runs = _agent_runs_by_id(deepcopy(agent_runs))
        accepted_issue_runs = {
            issue_id: list(run_ids) for issue_id, run_ids in issue_runs.items()
        }
        updates = _metadata_updates(before, collected_at, elapsed_ms)
        if diagnostics is not None:
            updates["diagnostics"] = deepcopy(list(diagnostics))

        return self._commit(
            replace(
                before,
                agent_runs=accepted_agent_runs,
                issue_runs=accepted_issue_runs,
                **updates,
            )
        )

    def query_issues(
        self, query: IssueListQuery = IssueListQuery()
    ) -> IssueListResult:
        state = self._state
        result = _query_indexed_issue_list(
            projects=state.projects,
            issues=state.issues,
            agent_runs=state.agent_runs,
            issue_runs=state.issue_runs,
            query=query,
            revision=state.revision,
        )
        return deepcopy(result)

    def project(self, project_id: str) -> ProjectObservation | None:
        project = self._state.projects.get(project_id)
        return deepcopy(project) if project is not None else None

    def issue(
        self,
        issue_id: str,
        *,
        project_id: str | None = None,
    ) -> IssueContext | None:
        state = self._state
        contexts = [
            context
            for context in _issue_contexts(state, issue_id)
            if project_id is None or context.project.project_id == project_id
        ]
        if len(contexts) != 1:
            return None
        return deepcopy(contexts[0])

    def detail_for(self, row: IssueListRow) -> IssueListRow | None:
        """Resolve a queried row's identity against the current state."""
        state = self._state
        context: IssueListRow | None
        if row.kind == "project":
            project = state.projects.get(row.project.project_id)
            context = (
                IssueListRow(
                    key=row.key,
                    kind=row.kind,
                    project=project,
                    project_runs=_project_runs(state, project.project_id),
                    empty_message=row.empty_message,
                )
                if project is not None
                else None
            )
        elif row.kind == "issue" and row.issue is not None:
            context = _issue_detail(state, row)
        elif row.kind == "agent-run" and row.run is not None:
            remains_unmatched = all(
                row.run.id not in run_ids
                for run_ids in state.issue_runs.values()
            )
            current_run = (
                state.agent_runs.get(row.run.id) if remains_unmatched else None
            )
            project = (
                state.projects.get(current_run.observation_project_id)
                if current_run is not None
                else None
            )
            context = (
                IssueListRow(
                    key=row.key,
                    kind=row.kind,
                    project=project,
                    run=current_run,
                    project_runs=_project_runs(state, project.project_id),
                    empty_message=row.empty_message,
                )
                if project is not None and current_run is not None
                else None
            )
        else:
            context = None
        return deepcopy(context)

    def diagnostics(self) -> tuple[ObservedDiagnostic, ...]:
        state = self._state
        entries = [
            ObservedDiagnostic(diagnostic)
            for diagnostic in state.diagnostics
        ]
        for project in state.projects.values():
            diagnostics = list(project.diagnostics)
            if project.snapshot is not None:
                diagnostics.extend(project.snapshot.diagnostics)
                for target in project.snapshot.observation_targets:
                    diagnostics.extend(target.diagnostics)
            entries.extend(
                ObservedDiagnostic(diagnostic, project.display_label)
                for diagnostic in diagnostics
            )
        return deepcopy(tuple(entries))

    def checkpoint(self) -> WorkspaceSnapshot:
        """Return a detached serializable view of the latest accepted state."""
        return _checkpoint(self._state)

    def _preserve_last_good(
        self,
        incoming: ProjectObservation,
        projects: Mapping[str, ProjectObservation],
    ) -> tuple[ProjectObservation, frozenset[str]]:
        previous = projects.get(incoming.project_id)
        if (
            previous is None
            or previous.repository_id != incoming.repository_id
            or previous.snapshot is None
        ):
            return incoming, frozenset()
        retained_issue_ids = frozenset(
            issue["id"] for issue in previous.snapshot.issues
        )
        if incoming.snapshot is None and incoming.status == "unavailable":
            return (
                replace(incoming, snapshot=deepcopy(previous.snapshot)),
                retained_issue_ids,
            )
        if (
            incoming.snapshot is not None
            and incoming.snapshot.issue_source_status == "unavailable"
            and previous.snapshot.issue_source_last_good_at is not None
        ):
            snapshot = replace(
                incoming.snapshot,
                issue_source_status="stale",
                issue_source_last_good_at=(
                    previous.snapshot.issue_source_last_good_at
                ),
                issues=deepcopy(previous.snapshot.issues),
            )
            return (
                replace(incoming, status="stale", snapshot=snapshot),
                retained_issue_ids,
            )
        return incoming, frozenset()

    def _commit(self, candidate: _StoreState) -> StoreChange:
        before = self._state
        after = replace(candidate, revision=before.revision + 1)
        change = _store_change(before, after)
        self._state = after
        return change


def _metadata_updates(
    before: _StoreState, collected_at: str | None, elapsed_ms: int | None
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if collected_at is not None:
        updates["collected_at"] = collected_at
    if elapsed_ms is not None:
        updates["elapsed_ms"] = elapsed_ms
    return updates


def _checkpoint(state: _StoreState) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        collected_at=state.collected_at,
        elapsed_ms=state.elapsed_ms,
        projects=deepcopy(list(state.projects.values())),
        agent_runs=deepcopy(list(state.agent_runs.values())),
        issue_runs=deepcopy(state.issue_runs),
        diagnostics=deepcopy(state.diagnostics),
    )


def _issue_detail(
    state: _StoreState, row: IssueListRow
) -> IssueListRow | None:
    issue_id = row.issue["id"]
    if row.key == row_key("issue", issue_id):
        matches = [
            (project_id, issue)
            for (project_id, indexed_issue_id), issue in state.issues.items()
            if indexed_issue_id == issue_id
        ]
        if len(matches) != 1:
            return None
        project_id, current_issue = matches[0]
    else:
        project_id = row.project.project_id
        current_issue = state.issues.get((project_id, issue_id))
        if current_issue is None:
            return None
    project = state.projects.get(project_id)
    if project is None:
        return None
    bound_run_ids = state.issue_runs.get(issue_id, [])
    observed_runs = tuple(
        state.agent_runs[run_id]
        for run_id in bound_run_ids
        if run_id in state.agent_runs
    )
    session_states = tuple(
        state.agent_runs[run_id].state
        if run_id in state.agent_runs
        else "unknown"
        for run_id in bound_run_ids
    )
    return IssueListRow(
        key=row.key,
        kind=row.kind,
        project=project,
        issue=current_issue,
        observed_runs=observed_runs,
        project_runs=_project_runs(state, project_id),
        session_states=session_states,
        empty_message=row.empty_message,
    )


def _project_runs(
    state: _StoreState, project_id: str
) -> tuple[AgentRun, ...]:
    return tuple(
        run
        for run in state.agent_runs.values()
        if run.observation_project_id == project_id
    )


def _issue_contexts(state: _StoreState, issue_id: str) -> list[IssueContext]:
    observed_runs = tuple(
        state.agent_runs[run_id]
        for run_id in state.issue_runs.get(issue_id, [])
        if run_id in state.agent_runs
    )
    return [
        IssueContext(state.projects[project_id], issue, observed_runs)
        for (project_id, indexed_issue_id), issue in state.issues.items()
        if indexed_issue_id == issue_id
    ]


def _store_change(before: _StoreState, after: _StoreState) -> StoreChange:
    project_ids = _changed_keys(before.projects, after.projects)
    issue_keys = _changed_keys(before.issues, after.issues)
    binding_issue_ids = _changed_keys(before.issue_runs, after.issue_runs)
    observation_target_keys = _changed_keys(
        before.observation_targets,
        after.observation_targets,
    )
    agent_run_ids = _changed_keys(before.agent_runs, after.agent_runs)
    binding_issue_ids.update(
        issue_id
        for bindings in (before.issue_runs, after.issue_runs)
        for issue_id, run_ids in bindings.items()
        if any(run_id in agent_run_ids for run_id in run_ids)
    )
    issue_keys.update(
        key for key in after.issues if key[1] in binding_issue_ids
    )
    kinds: set[ObservationKind] = set()
    if project_ids:
        kinds.add("projects")
    if agent_run_ids or before.issue_runs != after.issue_runs:
        kinds.add("agent-runs")
    if _workspace_metadata(before) != _workspace_metadata(after):
        kinds.add("workspace")
    return StoreChange(
        revision=after.revision,
        kinds=frozenset(kinds),
        project_ids=frozenset(project_ids),
        issue_keys=frozenset(issue_keys),
        observation_target_keys=frozenset(observation_target_keys),
        agent_run_ids=frozenset(agent_run_ids),
    )


def _workspace_metadata(
    state: _StoreState,
) -> tuple[str, int, list[Diagnostic]]:
    return state.collected_at, state.elapsed_ms, state.diagnostics


def _changed_keys(
    before: Mapping[Key, Value], after: Mapping[Key, Value]
) -> set[Key]:
    return {
        key
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key)
    }


def _issues_by_project(
    projects: Mapping[str, ProjectObservation],
) -> dict[tuple[str, str], Issue]:
    indexed: dict[tuple[str, str], Issue] = {}
    for project in projects.values():
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            key = (project.project_id, issue["id"])
            if key in indexed:
                raise ValueError(
                    f"Duplicate Issue Identity {issue['id']} in {project.project_id}"
                )
            indexed[key] = issue
    return indexed


def _targets_by_project(
    projects: Mapping[str, ProjectObservation],
) -> dict[tuple[str, str], ObservationTarget]:
    indexed: dict[tuple[str, str], ObservationTarget] = {}
    for project in projects.values():
        if project.snapshot is None:
            continue
        for target in project.snapshot.observation_targets:
            key = (project.project_id, target.path)
            if key in indexed:
                raise ValueError(
                    f"Duplicate Observation Target {target.path} in "
                    f"{project.project_id}"
                )
            indexed[key] = target
    return indexed


def _projects_by_id(
    projects: Sequence[ProjectObservation],
) -> dict[str, ProjectObservation]:
    indexed: dict[str, ProjectObservation] = {}
    for project in projects:
        if project.project_id in indexed:
            raise ValueError(f"Duplicate Project Identity {project.project_id}")
        indexed[project.project_id] = project
    return indexed


def _agent_runs_by_id(agent_runs: Sequence[AgentRun]) -> dict[str, AgentRun]:
    indexed: dict[str, AgentRun] = {}
    for run in agent_runs:
        if run.id in indexed:
            raise ValueError(f"Duplicate Agent Run Identity {run.id}")
        indexed[run.id] = run
    return indexed


def _restore_retained_issue_runs(
    issue_runs: dict[str, list[str]],
    agent_runs: Mapping[str, AgentRun],
    issues: Mapping[tuple[str, str], Issue],
    retained_issue_ids: set[str],
) -> None:
    project_counts: dict[str, int] = {}
    for _project_id, issue_id in issues:
        project_counts[issue_id] = project_counts.get(issue_id, 0) + 1
    for issue_id in retained_issue_ids:
        if project_counts.get(issue_id) != 1:
            continue
        issue_runs[issue_id] = [
            run.id for run in agent_runs.values() if run.issue_id == issue_id
        ]
