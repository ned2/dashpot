"""Hold the accepted observations per Project and derive the Workspace Snapshot.

The store holds what was published last, and nothing older: a Project
replaced with a failed half shows that failure, since every source that
retains a last good observation does so before it publishes (ADR 0137).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..core.issue_profile import IssueProfile
from ..core.model import (
    AgentRun,
    Branch,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    PullRequest,
    WorkspaceSnapshot,
)
from .branch_list import (
    BranchListRow,
    BranchListSummary,
    query_indexed_branch_list,
)
from .list_result import ListResult
from .session_list import SessionListRow, query_indexed_session_list
from .worktree_list import (
    WorktreeListRow,
    query_indexed_worktree_list,
)


@dataclass(frozen=True, slots=True)
class StoreChange:
    """What one publish changed that another observation depends on.

    Agent Run binding reads Project facts, so a change to them asks for the
    Agent Runs to be observed again.
    """

    agent_dependency_project_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ObservedDiagnostic:
    """One Diagnostic as shown, with the Project it was observed for, if any."""

    diagnostic: Diagnostic
    project_label: str | None = None
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoreState:
    """Hold the indexed observations one commit accepted, replaced whole on the next."""

    revision: int
    collected_at: str
    elapsed_ms: int
    projects: dict[str, ProjectObservation]
    issues: dict[tuple[str, str], IssueProfile]
    pull_requests: dict[tuple[str, str], PullRequest]
    observation_targets: dict[tuple[str, str], ObservationTarget]
    branches: dict[tuple[str, str], Branch]
    agent_runs: dict[str, AgentRun]
    issue_runs: dict[str, list[str]]
    diagnostics: tuple[Diagnostic, ...]


class WorkspaceObservationStore:
    """Own the latest accepted workspace observations and their read models."""

    def __init__(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        self._state = StoreState(
            revision=0,
            collected_at="",
            elapsed_ms=0,
            projects={},
            issues={},
            pull_requests={},
            observation_targets={},
            branches={},
            agent_runs={},
            issue_runs={},
            diagnostics=(),
        )
        if snapshot is not None:
            self.replace(snapshot)

    @property
    def revision(self) -> int:
        """Count the commits accepted so far, each publish one."""
        return self._state.revision

    @property
    def has_observations(self) -> bool:
        return self._state.revision > 0

    def replace(self, snapshot: WorkspaceSnapshot) -> StoreChange:
        """Accept a complete Workspace Snapshot in one commit.

        The test suite seeds a store this way; the coordinator publishes one
        Project and the Agent Runs at a time instead (ADR 0137).
        """
        projects = _projects_by_id(snapshot.projects)
        return self._commit(
            StoreState(
                revision=self._state.revision,
                collected_at=snapshot.collected_at,
                elapsed_ms=snapshot.elapsed_ms,
                projects=projects,
                issues=_issues_by_project(projects),
                pull_requests=_pull_requests_by_project(projects),
                observation_targets=_targets_by_project(projects),
                branches=_branches_by_project(projects),
                agent_runs=_agent_runs_by_id(snapshot.agent_runs),
                issue_runs={
                    issue_id: list(run_ids)
                    for issue_id, run_ids in snapshot.issue_runs.items()
                },
                diagnostics=tuple(snapshot.diagnostics),
            )
        )

    def replace_project(
        self,
        observation: ProjectObservation,
        *,
        collected_at: str | None = None,
        elapsed_ms: int | None = None,
    ) -> StoreChange:
        """Atomically replace one Project with its latest composition.

        ``collected_at``/``elapsed_ms`` optionally record the observation that
        produced this publish as the Workspace's latest collection metadata.
        """
        before = self._state
        projects = dict(before.projects)
        projects[observation.project_id] = observation
        issues = _issues_by_project(projects)
        pull_requests = _pull_requests_by_project(projects)
        observation_targets = _targets_by_project(projects)
        branches = _branches_by_project(projects)

        return self._commit(
            replace(
                before,
                projects=projects,
                issues=issues,
                pull_requests=pull_requests,
                observation_targets=observation_targets,
                branches=branches,
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
        accepted_agent_runs = _agent_runs_by_id(agent_runs)
        accepted_issue_runs = {
            issue_id: list(run_ids) for issue_id, run_ids in issue_runs.items()
        }
        updates = _metadata_updates(before, collected_at, elapsed_ms)
        if diagnostics is not None:
            updates["diagnostics"] = tuple(diagnostics)

        return self._commit(
            replace(
                before,
                agent_runs=accepted_agent_runs,
                issue_runs=accepted_issue_runs,
                **updates,
            )
        )

    def query_sessions(self) -> ListResult[SessionListRow]:
        """Query every active Agent Session, with its Project and Issue joined."""
        state = self._state
        result = query_indexed_session_list(
            projects=state.projects,
            issues=state.issues,
            agent_runs=state.agent_runs,
            issue_runs=state.issue_runs,
        )
        return result

    def query_worktrees(self) -> ListResult[WorktreeListRow]:
        """Query every observed Observation Target with its located sessions."""
        state = self._state
        result = query_indexed_worktree_list(
            projects=state.projects,
            observation_targets=state.observation_targets,
            agent_runs=state.agent_runs,
        )
        return result

    def query_branches(self) -> ListResult[BranchListRow, BranchListSummary]:
        """Query every observed Branch by name, with its refs and locations joined."""
        state = self._state
        result = query_indexed_branch_list(
            projects=state.projects,
            branches=state.branches,
            observation_targets=state.observation_targets,
            agent_runs=state.agent_runs,
        )
        return result

    def projects(self) -> tuple[ProjectObservation, ...]:
        """Every observed Project, in acceptance order."""
        return tuple(self._state.projects.values())

    def project(self, project_id: str) -> ProjectObservation | None:
        return self._state.projects.get(project_id)

    def agent_runs(self) -> tuple[AgentRun, ...]:
        """Every observed Agent Session row, bound to an Issue or not."""
        return tuple(self._state.agent_runs.values())

    def diagnostics(self) -> tuple[ObservedDiagnostic, ...]:
        state = self._state
        entries = [ObservedDiagnostic(diagnostic) for diagnostic in state.diagnostics]
        for project in state.projects.values():
            diagnostics = list(project.diagnostics)
            if project.snapshot is not None:
                diagnostics.extend(project.snapshot.diagnostics)
                for target in project.snapshot.observation_targets:
                    diagnostics.extend(target.diagnostics)
            entries.extend(
                ObservedDiagnostic(
                    diagnostic, project.display_label, project.project_id
                )
                for diagnostic in diagnostics
            )
        return tuple(entries)

    def checkpoint(self) -> WorkspaceSnapshot:
        """Return a detached serializable view of the latest accepted state."""
        return _checkpoint(self._state)

    def _commit(self, candidate: StoreState) -> StoreChange:
        before = self._state
        after = replace(candidate, revision=before.revision + 1)
        change = _store_change(before, after)
        self._state = after
        return change


def _metadata_updates(
    before: StoreState, collected_at: str | None, elapsed_ms: int | None
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if collected_at is not None:
        updates["collected_at"] = collected_at
    if elapsed_ms is not None:
        updates["elapsed_ms"] = elapsed_ms
    return updates


def _checkpoint(state: StoreState) -> WorkspaceSnapshot:
    # Every value is frozen, so a checkpoint is detached by construction.
    return WorkspaceSnapshot(
        collected_at=state.collected_at,
        elapsed_ms=state.elapsed_ms,
        projects=tuple(state.projects.values()),
        agent_runs=tuple(state.agent_runs.values()),
        issue_runs=state.issue_runs,
        diagnostics=state.diagnostics,
    )


def _store_change(before: StoreState, after: StoreState) -> StoreChange:
    return StoreChange(
        agent_dependency_project_ids=frozenset(
            project_id
            for project_id in before.projects.keys() | after.projects.keys()
            if _agent_project_projection(before.projects.get(project_id))
            != _agent_project_projection(after.projects.get(project_id))
        )
    )


def _agent_project_projection(
    project: ProjectObservation | None,
) -> object:
    """Keep only Project facts the Agent Run observation and binding consume."""
    if project is None or project.snapshot is None:
        return project
    return (
        project.project_id,
        project.repository_id,
        project.workspaces,
        project.anchors,
        project.primary_anchor,
        project.status,
        project.snapshot.issue_source_status,
        project.snapshot.issues,
        project.snapshot.observation_targets,
    )


def _issues_by_project(
    projects: Mapping[str, ProjectObservation],
) -> dict[tuple[str, str], IssueProfile]:
    indexed: dict[tuple[str, str], IssueProfile] = {}
    for project in projects.values():
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            key = (project.project_id, issue.id)
            if key in indexed:
                raise ValueError(
                    f"Duplicate Issue Identity {issue.id} in {project.project_id}"
                )
            indexed[key] = issue
    return indexed


def _pull_requests_by_project(
    projects: Mapping[str, ProjectObservation],
) -> dict[tuple[str, str], PullRequest]:
    indexed: dict[tuple[str, str], PullRequest] = {}
    for project in projects.values():
        if project.snapshot is None:
            continue
        for pull_request in project.snapshot.pull_requests:
            key = (project.project_id, pull_request.id)
            if key in indexed:
                raise ValueError(
                    f"Duplicate Pull Request identity {pull_request.id} in "
                    f"{project.project_id}"
                )
            indexed[key] = pull_request
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


def _branches_by_project(
    projects: Mapping[str, ProjectObservation],
) -> dict[tuple[str, str], Branch]:
    indexed: dict[tuple[str, str], Branch] = {}
    for project in projects.values():
        if project.snapshot is None:
            continue
        for branch in project.snapshot.branches:
            key = (project.project_id, branch.refname)
            if key in indexed:
                raise ValueError(
                    f"Duplicate Branch {branch.refname} in {project.project_id}"
                )
            indexed[key] = branch
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
