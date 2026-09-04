from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, TypeVar

from .branch_list import BranchListResult, _query_indexed_branch_list
from .issue_list import (
    IssueListQuery,
    IssueListResult,
    IssueListRow,
    _query_indexed_issue_list,
    row_key,
)
from .issue_profile import IssueProfile
from .model import (
    AgentRun,
    Branch,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    PullRequest,
    WorkspaceSnapshot,
)
from .pull_request_list import (
    PullRequestListResult,
    _query_indexed_pull_request_list,
)
from .session_list import SessionListResult, _query_indexed_session_list
from .worktree_list import WorktreeListResult, _query_indexed_worktree_list

StoreChangeKind = Literal["workspace", "projects", "agent-runs"]
Key = TypeVar("Key")
Value = TypeVar("Value")


@dataclass(frozen=True, slots=True)
class StoreChange:
    revision: int
    kinds: frozenset[StoreChangeKind]
    project_ids: frozenset[str] = frozenset()
    issue_keys: frozenset[tuple[str, str]] = frozenset()
    observation_target_keys: frozenset[tuple[str, str]] = frozenset()
    branch_keys: frozenset[tuple[str, str]] = frozenset()
    agent_run_ids: frozenset[str] = frozenset()
    pull_request_keys: frozenset[tuple[str, str]] = frozenset()
    agent_dependency_project_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class IssueContext:
    project: ProjectObservation
    issue: IssueProfile
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
        self._state = _StoreState(
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
        return self._state.revision

    @property
    def has_observations(self) -> bool:
        return self._state.revision > 0

    def replace(self, snapshot: WorkspaceSnapshot) -> StoreChange:
        """Atomically accept a complete collector checkpoint."""
        before = self._state

        accepted_projects: list[ProjectObservation] = []
        retained_issue_ids: set[str] = set()
        for project in snapshot.projects:
            accepted, retained = self._preserve_last_good(project, before.projects)
            accepted_projects.append(accepted)
            retained_issue_ids.update(retained)
        projects = _projects_by_id(accepted_projects)
        issues = _issues_by_project(projects)
        pull_requests = _pull_requests_by_project(projects)
        observation_targets = _targets_by_project(projects)
        branches = _branches_by_project(projects)
        agent_runs = _agent_runs_by_id(snapshot.agent_runs)
        # The store owns its binding index and restore writes into it, so the
        # frozen snapshot mapping is expanded into fresh mutable containers.
        issue_runs = {
            issue_id: list(run_ids) for issue_id, run_ids in snapshot.issue_runs.items()
        }
        _restore_retained_issue_runs(
            issue_runs,
            agent_runs,
            issues,
            retained_issue_ids,
        )

        return self._commit(
            _StoreState(
                revision=before.revision,
                collected_at=snapshot.collected_at,
                elapsed_ms=snapshot.elapsed_ms,
                projects=projects,
                issues=issues,
                pull_requests=pull_requests,
                observation_targets=observation_targets,
                branches=branches,
                agent_runs=agent_runs,
                issue_runs=issue_runs,
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
        """Atomically replace one Project while retaining its last good data.

        ``collected_at``/``elapsed_ms`` optionally record the observation that
        produced this publish as the Workspace's latest collection metadata.
        """
        before = self._state
        accepted, _retained = self._preserve_last_good(observation, before.projects)
        projects = dict(before.projects)
        projects[accepted.project_id] = accepted
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

    def query_issues(self, query: IssueListQuery = IssueListQuery()) -> IssueListResult:
        state = self._state
        result = _query_indexed_issue_list(
            projects=state.projects,
            issues=state.issues,
            agent_runs=state.agent_runs,
            issue_runs=state.issue_runs,
            query=query,
            revision=state.revision,
        )
        return result

    def query_sessions(self) -> SessionListResult:
        """Query every active Agent Session, with its Project and Issue joined."""
        state = self._state
        result = _query_indexed_session_list(
            projects=state.projects,
            issues=state.issues,
            agent_runs=state.agent_runs,
            issue_runs=state.issue_runs,
            revision=state.revision,
        )
        return result

    def query_worktrees(self) -> WorktreeListResult:
        """Query every observed Observation Target with its located sessions."""
        state = self._state
        result = _query_indexed_worktree_list(
            projects=state.projects,
            observation_targets=state.observation_targets,
            agent_runs=state.agent_runs,
            revision=state.revision,
        )
        return result

    def query_branches(self) -> BranchListResult:
        """Query every observed Branch by name, with its refs and locations joined."""
        state = self._state
        result = _query_indexed_branch_list(
            projects=state.projects,
            branches=state.branches,
            observation_targets=state.observation_targets,
            agent_runs=state.agent_runs,
            revision=state.revision,
        )
        return result

    def query_pull_requests(self) -> PullRequestListResult:
        """Query every active Pull Request with its independent freshness."""
        state = self._state
        return _query_indexed_pull_request_list(
            projects=state.projects,
            pull_requests=state.pull_requests,
            revision=state.revision,
        )

    def projects(self) -> tuple[ProjectObservation, ...]:
        """Every observed Project, in acceptance order."""
        return tuple(self._state.projects.values())

    def project(self, project_id: str) -> ProjectObservation | None:
        return self._state.projects.get(project_id)

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
        return contexts[0]

    def detail_for(self, row: IssueListRow) -> IssueListRow | None:
        """Resolve a queried row's identity against the current state."""
        state = self._state
        return _issue_detail(state, row, row.issue) if row.kind == "issue" else None

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
                ObservedDiagnostic(diagnostic, project.display_label)
                for diagnostic in diagnostics
            )
        return tuple(entries)

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
            return incoming, frozenset[str]()
        retained_issue_ids = frozenset(issue.id for issue in previous.snapshot.issues)
        if incoming.snapshot is None and incoming.status == "unavailable":
            return (
                incoming.model_copy(update={"snapshot": previous.snapshot}),
                retained_issue_ids,
            )
        if incoming.snapshot is None:
            return incoming, frozenset[str]()
        snapshot = incoming.snapshot
        snapshot_updates: dict[str, Any] = {}
        accepted_status = incoming.status
        if (
            snapshot.issue_source_status == "unavailable"
            and previous.snapshot.issue_source_last_good_at is not None
        ):
            snapshot_updates.update(
                issue_source_status="stale",
                issue_source_last_good_at=previous.snapshot.issue_source_last_good_at,
                issues=previous.snapshot.issues,
            )
            accepted_status = "stale"
        else:
            retained_issue_ids = frozenset[str]()
        if (
            snapshot.pull_request_status == "unavailable"
            and previous.snapshot.pull_request_last_good_at is not None
        ):
            snapshot_updates.update(
                pull_request_status="stale",
                pull_request_last_good_at=(previous.snapshot.pull_request_last_good_at),
                pull_requests=previous.snapshot.pull_requests,
            )
        if not snapshot_updates:
            return incoming, retained_issue_ids
        accepted_snapshot = snapshot.model_copy(update=snapshot_updates)
        return (
            incoming.model_copy(
                update={"status": accepted_status, "snapshot": accepted_snapshot}
            ),
            retained_issue_ids,
        )

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
    # Every value is frozen, so a checkpoint is detached by construction.
    return WorkspaceSnapshot(
        collected_at=state.collected_at,
        elapsed_ms=state.elapsed_ms,
        projects=tuple(state.projects.values()),
        agent_runs=tuple(state.agent_runs.values()),
        issue_runs=state.issue_runs,
        diagnostics=state.diagnostics,
    )


def _issue_detail(
    state: _StoreState, row: IssueListRow, issue: IssueProfile
) -> IssueListRow | None:
    issue_id = issue.id
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
        state.agent_runs[run_id].state if run_id in state.agent_runs else "unknown"
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
    )


def _project_runs(state: _StoreState, project_id: str) -> tuple[AgentRun, ...]:
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
    agent_dependency_project_ids = {
        project_id
        for project_id in before.projects.keys() | after.projects.keys()
        if _agent_project_projection(before.projects.get(project_id))
        != _agent_project_projection(after.projects.get(project_id))
    }
    issue_keys = _changed_keys(before.issues, after.issues)
    pull_request_keys = _changed_keys(before.pull_requests, after.pull_requests)
    binding_issue_ids = _changed_keys(before.issue_runs, after.issue_runs)
    observation_target_keys = _changed_keys(
        before.observation_targets,
        after.observation_targets,
    )
    branch_keys = _changed_keys(before.branches, after.branches)
    agent_run_ids = _changed_keys(before.agent_runs, after.agent_runs)
    binding_issue_ids.update(
        issue_id
        for bindings in (before.issue_runs, after.issue_runs)
        for issue_id, run_ids in bindings.items()
        if any(run_id in agent_run_ids for run_id in run_ids)
    )
    issue_keys.update(key for key in after.issues if key[1] in binding_issue_ids)
    kinds: set[StoreChangeKind] = set()
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
        branch_keys=frozenset(branch_keys),
        agent_run_ids=frozenset(agent_run_ids),
        pull_request_keys=frozenset(pull_request_keys),
        agent_dependency_project_ids=frozenset(agent_dependency_project_ids),
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


def _workspace_metadata(
    state: _StoreState,
) -> tuple[str, int, tuple[Diagnostic, ...]]:
    return state.collected_at, state.elapsed_ms, state.diagnostics


def _changed_keys(before: Mapping[Key, Value], after: Mapping[Key, Value]) -> set[Key]:
    return {
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    }


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


def _restore_retained_issue_runs(
    issue_runs: dict[str, list[str]],
    agent_runs: Mapping[str, AgentRun],
    issues: Mapping[tuple[str, str], IssueProfile],
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
