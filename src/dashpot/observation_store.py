from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Literal, TypeVar

from .issue_list import IssueListQuery, IssueListResult, query_issue_list
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


class WorkspaceObservationStore:
    """Own the latest accepted workspace observations and their read models."""

    def __init__(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        self._revision = 0
        self._collected_at = ""
        self._elapsed_ms = 0
        self._projects: dict[str, ProjectObservation] = {}
        self._issues: dict[tuple[str, str], Issue] = {}
        self._observation_targets: dict[tuple[str, str], ObservationTarget] = {}
        self._agent_runs: dict[str, AgentRun] = {}
        self._issue_runs: dict[str, list[str]] = {}
        self._diagnostics: list[Diagnostic] = []
        if snapshot is not None:
            self.replace(snapshot)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def has_observations(self) -> bool:
        return self._revision > 0

    def replace(self, snapshot: WorkspaceSnapshot) -> StoreChange:
        """Atomically accept a complete collector checkpoint."""
        incoming = deepcopy(snapshot)
        before_projects = deepcopy(self._projects)
        before_agent_runs = deepcopy(self._agent_runs)
        before_issue_runs = deepcopy(self._issue_runs)
        before_workspace = self._workspace_metadata()

        accepted_projects: list[ProjectObservation] = []
        retained_issue_ids: set[str] = set()
        for project in incoming.projects:
            accepted, retained = self._preserve_last_good(project)
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

        self._projects = projects
        self._issues = issues
        self._observation_targets = observation_targets
        self._agent_runs = agent_runs
        self._issue_runs = issue_runs
        self._collected_at = incoming.collected_at
        self._elapsed_ms = incoming.elapsed_ms
        self._diagnostics = incoming.diagnostics
        self._revision += 1

        return self._change(
            before_projects,
            before_agent_runs,
            before_issue_runs,
            before_workspace,
        )

    def replace_project(self, observation: ProjectObservation) -> StoreChange:
        """Atomically replace one Project while retaining its last good data."""
        before_projects = deepcopy(self._projects)
        accepted, _retained = self._preserve_last_good(deepcopy(observation))
        projects = deepcopy(self._projects)
        projects[accepted.project_id] = accepted
        issues = _issues_by_project(projects)
        observation_targets = _targets_by_project(projects)

        self._projects = projects
        self._issues = issues
        self._observation_targets = observation_targets
        self._revision += 1
        return self._change(
            before_projects,
            deepcopy(self._agent_runs),
            deepcopy(self._issue_runs),
            self._workspace_metadata(),
        )

    def replace_agent_runs(
        self,
        agent_runs: Sequence[AgentRun],
        issue_runs: Mapping[str, Sequence[str]],
    ) -> StoreChange:
        """Atomically replace Agent Runs and their accepted Issue bindings."""
        before_agent_runs = deepcopy(self._agent_runs)
        before_issue_runs = deepcopy(self._issue_runs)
        accepted_agent_runs = _agent_runs_by_id(deepcopy(agent_runs))
        accepted_issue_runs = {
            issue_id: list(run_ids) for issue_id, run_ids in issue_runs.items()
        }

        self._agent_runs = accepted_agent_runs
        self._issue_runs = accepted_issue_runs
        self._revision += 1
        return self._change(
            deepcopy(self._projects),
            before_agent_runs,
            before_issue_runs,
            self._workspace_metadata(),
        )

    def query_issues(
        self, query: IssueListQuery = IssueListQuery()
    ) -> IssueListResult:
        return query_issue_list(
            self.checkpoint(), query, revision=self._revision
        )

    def project(self, project_id: str) -> ProjectObservation | None:
        project = self._projects.get(project_id)
        return deepcopy(project) if project is not None else None

    def issue(
        self,
        issue_id: str,
        *,
        project_id: str | None = None,
    ) -> IssueContext | None:
        contexts = [
            context
            for context in self._issue_contexts(issue_id)
            if project_id is None or context.project.project_id == project_id
        ]
        if len(contexts) != 1:
            return None
        return deepcopy(contexts[0])

    def diagnostics(self) -> tuple[ObservedDiagnostic, ...]:
        entries = [
            ObservedDiagnostic(diagnostic)
            for diagnostic in self._diagnostics
        ]
        for project in self._projects.values():
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
        return WorkspaceSnapshot(
            collected_at=self._collected_at,
            elapsed_ms=self._elapsed_ms,
            projects=deepcopy(list(self._projects.values())),
            agent_runs=deepcopy(list(self._agent_runs.values())),
            issue_runs=deepcopy(self._issue_runs),
            diagnostics=deepcopy(self._diagnostics),
        )

    def _preserve_last_good(
        self, incoming: ProjectObservation
    ) -> tuple[ProjectObservation, frozenset[str]]:
        previous = self._projects.get(incoming.project_id)
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

    def _issue_contexts(self, issue_id: str) -> list[IssueContext]:
        runs_by_id = self._agent_runs
        observed_runs = tuple(
            runs_by_id[run_id]
            for run_id in self._issue_runs.get(issue_id, [])
            if run_id in runs_by_id
        )
        return [
            IssueContext(self._projects[project_id], issue, observed_runs)
            for (project_id, indexed_issue_id), issue in self._issues.items()
            if indexed_issue_id == issue_id
        ]

    def _workspace_metadata(self) -> tuple[str, int, list[Diagnostic]]:
        return (
            self._collected_at,
            self._elapsed_ms,
            deepcopy(self._diagnostics),
        )

    def _change(
        self,
        before_projects: dict[str, ProjectObservation],
        before_agent_runs: dict[str, AgentRun],
        before_issue_runs: dict[str, list[str]],
        before_workspace: tuple[str, int, list[Diagnostic]],
    ) -> StoreChange:
        project_ids = _changed_keys(before_projects, self._projects)
        issue_keys = _changed_keys(
            _issues_by_project(before_projects),
            self._issues,
        )
        binding_issue_ids = _changed_keys(before_issue_runs, self._issue_runs)
        observation_target_keys = _changed_keys(
            _targets_by_project(before_projects),
            self._observation_targets,
        )
        agent_run_ids = _changed_keys(before_agent_runs, self._agent_runs)
        binding_issue_ids.update(
            issue_id
            for bindings in (before_issue_runs, self._issue_runs)
            for issue_id, run_ids in bindings.items()
            if any(run_id in agent_run_ids for run_id in run_ids)
        )
        issue_keys.update(
            key for key in self._issues if key[1] in binding_issue_ids
        )
        kinds: set[ObservationKind] = set()
        if project_ids:
            kinds.add("projects")
        if agent_run_ids or before_issue_runs != self._issue_runs:
            kinds.add("agent-runs")
        if before_workspace != self._workspace_metadata():
            kinds.add("workspace")
        return StoreChange(
            revision=self._revision,
            kinds=frozenset(kinds),
            project_ids=frozenset(project_ids),
            issue_keys=frozenset(issue_keys),
            observation_target_keys=frozenset(observation_target_keys),
            agent_run_ids=frozenset(agent_run_ids),
        )


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
