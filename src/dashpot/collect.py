from __future__ import annotations

import concurrent.futures
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from .agent_bindings import bind_issue_runs
from .agents import lock_holder_probe, observe_agent_runs
from .github_issues import GitHubIssuesSource
from .issue_sources import IssueSource, IssueSourceObservation, utc_now
from .local_markdown_issues import LocalMarkdownIssuesSource
from .model import (
    AgentRun,
    Branch,
    Diagnostic,
    IssueActivity,
    ObservationTarget,
    ObservationTargetInventory,
    ProjectObservation,
    ProjectSnapshot,
    ResolvedProject,
    SourceStatus,
    WorkspaceSnapshot,
)
from .observation_store import StoreChange, WorkspaceObservationStore
from .project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
)
from .repository import (
    BranchObservation,
    github_repo_from_remote,
    observe_branches,
    observe_observation_targets,
    worktree_root,
)

WorkspaceAgentObserver = Callable[
    [Mapping[str, Sequence[ObservationTarget]]],
    tuple[list[AgentRun], list[Diagnostic]],
]
ObservationTargetObserver = Callable[[Sequence[Path]], ObservationTargetInventory]
BranchObserver = Callable[[Sequence[Path]], BranchObservation]

ObservationKind = Literal["issues", "targets", "agent-runs", "workspace"]
WORKSPACE_SCOPE = "*"


@dataclass(frozen=True, slots=True)
class ObservationKey:
    """One independently scheduled observation: a kind for one Project."""

    kind: ObservationKind
    project_id: str = WORKSPACE_SCOPE

    @property
    def group(self) -> str:
        return f"{self.kind}:{self.project_id}"


AGENT_RUNS_KEY = ObservationKey("agent-runs")
WORKSPACE_KEY = ObservationKey("workspace")


@dataclass(frozen=True, slots=True)
class ObservationTicket:
    """A request for one observation; only the newest ticket per key is accepted."""

    key: ObservationKey
    generation: int


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    """What happened to a ticket after its observation ran.

    ``accepted`` is false when a newer ticket for the same key superseded it.
    An accepted observation is held by the scheduler until ``publish`` moves
    it into a store, so publishing can stay on the consumer's thread.
    """

    ticket: ObservationTicket
    accepted: bool


@runtime_checkable
class ObservationScheduler(Protocol):
    """Schedules keyed observations and publishes accepted ones into a store."""

    def keys(self, project_id: str | None = None) -> Sequence[ObservationKey]: ...

    def request(self, keys: Sequence[ObservationKey]) -> list[ObservationTicket]: ...

    def is_current(self, ticket: ObservationTicket) -> bool: ...

    def observe(self, ticket: ObservationTicket) -> ObservationOutcome: ...

    def publish(self, store: WorkspaceObservationStore) -> list[StoreChange]: ...

    def follow_ups(
        self, changes: Sequence[StoreChange]
    ) -> Sequence[ObservationKey]: ...


# What an observation seam may raise: adapter failures, and the strict
# frozen models rejecting a malformed observation — either becomes a
# Diagnostic rather than failing the whole refresh.
OBSERVATION_FAILURES = (OSError, RuntimeError, ValidationError)


class ProjectObserver(Protocol):
    """What the coordinator asks of a per-Project collector."""

    def observe_issues(self) -> IssueSourceObservation: ...

    def observe_targets(self) -> ObservationTargetInventory: ...


class ProjectCollector:
    """Observe one Project's Issue Source and worktree topology independently."""

    def __init__(
        self,
        project: ResolvedProject,
        source: IssueSource,
        target_observer: ObservationTargetObserver = observe_observation_targets,
        branch_observer: BranchObserver = observe_branches,
    ) -> None:
        self.project = project
        self.root = Path(project.primary_anchor)
        self.source = source
        self.target_observer = target_observer
        self.branch_observer = branch_observer

    def observe_issues(self) -> IssueSourceObservation:
        return self.source.refresh()

    def observe_targets(self) -> ObservationTargetInventory:
        """Observe the worktree topology and the Branches as one repository state."""
        anchors = [Path(anchor) for anchor in self.project.anchors]
        inventory = self.target_observer(anchors)
        branches = self.branch_observer(anchors)
        return ObservationTargetInventory(
            targets=inventory.targets,
            diagnostics=[*inventory.diagnostics, *branches.diagnostics],
            branches=branches.branches,
            fetched_at=branches.fetched_at,
            integration_ref=branches.integration_ref,
        )

    def refresh(self) -> ProjectSnapshot:
        """Observe both halves in one call (single-shot convenience)."""
        issue_observation = self.observe_issues()
        attempted_at = utc_now()
        try:
            target_inventory = self.observe_targets()
            target_status: SourceStatus = "fresh"
        except OBSERVATION_FAILURES as exc:
            target_status = "unavailable"
            target_inventory = ObservationTargetInventory(
                targets=[],
                diagnostics=[
                    _target_discovery_diagnostic(self.project.project_id, exc)
                ],
            )
        diagnostics = list(target_inventory.diagnostics)
        diagnostics[0:0] = _issue_diagnostics(issue_observation)
        return ProjectSnapshot(
            project_id=self.project.project_id,
            display_label=self.project.display_label,
            repository_id=self.project.repository_id,
            collected_at=utc_now(),
            issue_source_status=issue_observation.status,
            issue_source_attempted_at=issue_observation.attempted_at,
            issue_source_last_good_at=issue_observation.last_good_at,
            observation_targets=target_inventory.targets,
            issues=issue_observation.issues,
            diagnostics=diagnostics,
            label_colors=issue_observation.label_colors,
            issue_activity=issue_observation.issue_activity,
            target_status=target_status,
            target_attempted_at=attempted_at,
            target_last_good_at=(attempted_at if target_status == "fresh" else None),
            branches=target_inventory.branches,
            fetched_at=target_inventory.fetched_at,
            integration_ref=target_inventory.integration_ref,
        )


def create_project_collector(
    project: ResolvedProject,
    timeout: float = 10,
    state_dir: Path | None = None,
) -> ProjectCollector:
    requested_root = Path(project.primary_anchor)
    root = worktree_root(requested_root)
    config = load_project_config(root)
    if (
        config.project_id != project.project_id
        or config.display_label != project.display_label
        or config.repository_id != project.repository_id
    ):
        raise RuntimeError(
            f"Project configuration changed after resolving Repository Anchor {root}"
        )
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        repository_reference = github_repo_from_remote(root)
        if not repository_reference:
            raise RuntimeError(
                "A GitHub Issue Source requires the Repository Anchor to have "
                "a GitHub origin remote"
            )
        source: IssueSource = GitHubIssuesSource(
            root,
            project_id=config.project_id,
            repository_id=config.repository_id,
            timeout=timeout,
        )
    elif isinstance(config.issue_source, LocalMarkdownIssueSourceConfig):
        source = LocalMarkdownIssuesSource(
            root,
            project_id=config.project_id,
            issues_path=Path(config.issue_source.path),
        )
    else:  # pragma: no cover - exhaustive guard for future source kinds.
        raise RuntimeError("unsupported configured Issue Source")
    return ProjectCollector(
        project,
        source,
        target_observer=lambda anchors: observe_observation_targets(
            anchors, timeout=timeout, process_lookup=lock_holder_probe
        ),
        branch_observer=lambda anchors: observe_branches(anchors, timeout=timeout),
    )


@dataclass(frozen=True, slots=True)
class _SourceObservation:
    """The latest accepted result for one Project half (Issues or targets)."""

    status: SourceStatus
    attempted_at: str
    last_good_at: str | None
    data: tuple[Any, ...]
    diagnostics: tuple[Diagnostic, ...]
    project_diagnostics: tuple[Diagnostic, ...]
    elapsed_ms: int
    label_colors: Mapping[str, str] = field(default_factory=dict)
    issue_activity: Mapping[str, IssueActivity] = field(default_factory=dict)
    branches: tuple[Branch, ...] = ()
    fetched_at: str | None = None
    integration_ref: str | None = None

    def retained_after_failure(
        self,
        attempted_at: str,
        diagnostic: Diagnostic,
        *,
        project_failure: bool,
    ) -> _SourceObservation:
        """Keep the last good data, mark it stale, and attach the new failure."""
        return replace(
            self,
            status="stale",
            attempted_at=attempted_at,
            diagnostics=() if project_failure else (diagnostic,),
            project_diagnostics=(diagnostic,) if project_failure else (),
            elapsed_ms=0,
        )


@dataclass(frozen=True, slots=True)
class _AgentObservation:
    agent_runs: tuple[AgentRun, ...]
    issue_runs: Mapping[str, tuple[str, ...]]
    diagnostics: tuple[Diagnostic, ...]
    elapsed_ms: int = 0


class ObservationCoordinator:
    """Schedule independent Project observations and publish them as they land.

    Every ``(kind, project_id)`` key carries its own generation, lock, and last
    accepted result. A ticket whose generation is no longer current is skipped
    before it starts or discarded after it finishes, so a late result can never
    overwrite a newer one. Issues and worktree targets are observed separately;
    a Project is composed from its latest accepted halves and becomes
    publishable only once both have been observed at least once, so a store
    never shows a Project as "observed absent" before its first complete
    observation. ``publish`` moves every pending composition into a store in
    accept order, which keeps the store single-threaded for its consumer.
    """

    def __init__(
        self,
        projects: Sequence[ResolvedProject],
        timeout: float = 10,
        state_dir: Path | None = None,
        factory: Callable[..., ProjectObserver] = create_project_collector,
        diagnostics: Sequence[Diagnostic] = (),
        agent_observer: WorkspaceAgentObserver | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.projects = list(projects)
        self.projects_by_id = {project.project_id: project for project in self.projects}
        self.timeout = timeout
        self.state_dir = state_dir
        self.factory = factory
        self.diagnostics = list(diagnostics)
        self.agent_observer = agent_observer or (
            lambda targets: observe_agent_runs(targets, self.state_dir)
        )
        self.clock = clock
        self.collectors: dict[str, ProjectObserver] = {}
        self.refresh_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._key_locks: dict[ObservationKey, threading.Lock] = {}
        self._generations: dict[ObservationKey, int] = {}
        self._accepted: dict[ObservationKey, int] = {}
        self._observations: dict[ObservationKey, _SourceObservation] = {}
        self._composed: dict[str, ProjectObservation] = {}
        self._pending_projects: dict[str, None] = {}
        self._agent: _AgentObservation | None = None
        self._agent_pending = False

    # -- scheduling -------------------------------------------------------

    def keys(self, project_id: str | None = None) -> list[ObservationKey]:
        """Keys for one Project (plus Agent Runs), or every key when unknown."""
        if project_id is not None and project_id in self.projects_by_id:
            selected = [project_id]
        else:
            selected = [project.project_id for project in self.projects]
        keys = [
            ObservationKey(kind, current)
            for current in selected
            for kind in ("issues", "targets")
        ]
        keys.append(AGENT_RUNS_KEY)
        return keys

    def follow_ups(self, changes: Sequence[StoreChange]) -> list[ObservationKey]:
        """Agent Runs depend on published Projects: re-observe after any."""
        if any("projects" in change.kinds for change in changes):
            return [AGENT_RUNS_KEY]
        return []

    def request(self, keys: Sequence[ObservationKey]) -> list[ObservationTicket]:
        tickets: list[ObservationTicket] = []
        with self._state_lock:
            for key in keys:
                generation = self._generations.get(key, 0) + 1
                self._generations[key] = generation
                self._key_locks.setdefault(key, threading.Lock())
                tickets.append(ObservationTicket(key, generation))
        return tickets

    def is_current(self, ticket: ObservationTicket) -> bool:
        with self._state_lock:
            return self._generations.get(ticket.key) == ticket.generation

    def observe(self, ticket: ObservationTicket) -> ObservationOutcome:
        """Run one ticket's observation and accept it if still current."""
        key = ticket.key
        with self._state_lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
        # Serialize per key so stateful last-good source caches are never
        # refreshed concurrently by a superseding request for the same key.
        with lock:
            if not self.is_current(ticket):
                return ObservationOutcome(ticket, accepted=False)
            started = time.monotonic()
            if key.kind == "agent-runs":
                agent = self._observe_agent_runs()
                # Timing belongs to this seam, so it is stamped by rebuilding
                # the frozen value rather than assigning into it.
                agent = replace(
                    agent, elapsed_ms=round((time.monotonic() - started) * 1000)
                )
                with self._state_lock:
                    if self._generations.get(key) != ticket.generation:
                        return ObservationOutcome(ticket, accepted=False)
                    self._accepted[key] = ticket.generation
                    self._agent = agent
                    self._agent_pending = True
                return ObservationOutcome(ticket, accepted=True)
            if key.kind not in ("issues", "targets"):
                raise RuntimeError(f"unsupported observation kind: {key.kind}")
            with self._state_lock:
                previous = self._observations.get(key)
            observation = self._observe_project_half(key, previous)
            observation = replace(
                observation, elapsed_ms=round((time.monotonic() - started) * 1000)
            )
            with self._state_lock:
                if self._generations.get(key) != ticket.generation:
                    return ObservationOutcome(ticket, accepted=False)
                self._accepted[key] = ticket.generation
                self._observations[key] = observation
                composed = self._compose(key.project_id)
                if composed is not None:
                    self._composed[key.project_id] = composed
                    self._pending_projects[key.project_id] = None
            return ObservationOutcome(ticket, accepted=True)

    def publish(
        self,
        store: WorkspaceObservationStore,
        *,
        elapsed_ms: int | None = None,
    ) -> list[StoreChange]:
        """Move every accepted-but-unpublished observation into the store.

        Projects are published before Agent Runs so bindings never reference
        Issues the store has not seen. Returns one change per publish.
        """
        changes: list[StoreChange] = []
        with self._state_lock:
            # Configured order keeps a fresh store's checkpoint deterministic
            # however the observations happened to complete.
            pending = [
                project.project_id
                for project in self.projects
                if project.project_id in self._pending_projects
            ]
            for project_id in pending:
                composed = self._composed[project_id]
                changes.append(
                    store.replace_project(
                        composed,
                        collected_at=self.clock(),
                        elapsed_ms=(
                            composed.elapsed_ms if elapsed_ms is None else elapsed_ms
                        ),
                    )
                )
            self._pending_projects.clear()
            if self._agent_pending and self._agent is not None:
                changes.append(
                    store.replace_agent_runs(
                        self._agent.agent_runs,
                        self._agent.issue_runs,
                        self._agent.diagnostics,
                        collected_at=self.clock(),
                        elapsed_ms=(
                            self._agent.elapsed_ms if elapsed_ms is None else elapsed_ms
                        ),
                    )
                )
                self._agent_pending = False
        return changes

    def refresh(
        self, store: WorkspaceObservationStore | None = None
    ) -> WorkspaceSnapshot:
        """Coordinated barrier: observe every key, publish, then checkpoint."""
        # Barriers are serialized so their generations never interleave; a
        # superseded barrier would otherwise return an incomplete checkpoint.
        with self.refresh_lock:
            store = store or WorkspaceObservationStore()
            started = time.monotonic()
            tickets = self.request(self.keys())
            project_tickets = [
                ticket for ticket in tickets if ticket.key.kind != "agent-runs"
            ]
            worker_count = max(1, min(8, len(project_tickets)))
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=worker_count
            ) as pool:
                futures = [
                    pool.submit(self.observe, ticket) for ticket in project_tickets
                ]
                for future in futures:
                    future.result()
            self.observe(
                next(ticket for ticket in tickets if ticket.key.kind == "agent-runs")
            )
            self.publish(store, elapsed_ms=round((time.monotonic() - started) * 1000))
            return store.checkpoint()

    # -- observation ------------------------------------------------------

    def _collector(self, project: ResolvedProject) -> ProjectObserver:
        root = Path(project.primary_anchor)
        if not root.is_dir():
            raise RuntimeError(
                f"repository root does not exist or is not a directory: {root}"
            )
        with self._state_lock:
            collector = self.collectors.get(project.project_id)
        if collector is None:
            collector = self.factory(
                project, timeout=self.timeout, state_dir=self.state_dir
            )
            with self._state_lock:
                collector = self.collectors.setdefault(project.project_id, collector)
        return collector

    def _observe_project_half(
        self, key: ObservationKey, previous: _SourceObservation | None
    ) -> _SourceObservation:
        project = self.projects_by_id[key.project_id]
        attempted_at = self.clock()
        try:
            collector = self._collector(project)
        except OBSERVATION_FAILURES as exc:
            return self._failed(
                previous,
                attempted_at,
                Diagnostic(
                    source=f"project:{project.project_id}",
                    severity="error",
                    message=str(exc),
                    code="project-collection",
                ),
                project_failure=True,
            )
        if key.kind == "issues":
            try:
                issue_observation = collector.observe_issues()
            except OBSERVATION_FAILURES as exc:
                return self._failed(
                    previous,
                    attempted_at,
                    Diagnostic(
                        source=f"project:{project.project_id}",
                        severity="error",
                        message=f"Cannot collect Issues: {exc}",
                        code="issue-collection",
                    ),
                    project_failure=False,
                )
            return _SourceObservation(
                status=issue_observation.status,
                attempted_at=issue_observation.attempted_at,
                last_good_at=issue_observation.last_good_at,
                data=issue_observation.issues,
                diagnostics=tuple(_issue_diagnostics(issue_observation)),
                project_diagnostics=(),
                elapsed_ms=0,
                label_colors=issue_observation.label_colors,
                issue_activity=issue_observation.issue_activity,
            )
        try:
            inventory = collector.observe_targets()
        except OBSERVATION_FAILURES as exc:
            return self._failed(
                previous,
                attempted_at,
                _target_discovery_diagnostic(project.project_id, exc),
                project_failure=False,
            )
        return _SourceObservation(
            status="fresh",
            attempted_at=attempted_at,
            last_good_at=attempted_at,
            data=tuple(inventory.targets),
            diagnostics=tuple(inventory.diagnostics),
            project_diagnostics=(),
            elapsed_ms=0,
            branches=tuple(inventory.branches),
            fetched_at=inventory.fetched_at,
            integration_ref=inventory.integration_ref,
        )

    def _failed(
        self,
        previous: _SourceObservation | None,
        attempted_at: str,
        diagnostic: Diagnostic,
        *,
        project_failure: bool,
    ) -> _SourceObservation:
        if previous is not None and previous.last_good_at is not None:
            return previous.retained_after_failure(
                attempted_at, diagnostic, project_failure=project_failure
            )
        return _SourceObservation(
            status="unavailable",
            attempted_at=attempted_at,
            last_good_at=None,
            data=(),
            diagnostics=() if project_failure else (diagnostic,),
            project_diagnostics=(diagnostic,) if project_failure else (),
            elapsed_ms=0,
        )

    def _compose(self, project_id: str) -> ProjectObservation | None:
        """Compose a Project from its latest accepted halves, or None if pending."""
        issues = self._observations.get(ObservationKey("issues", project_id))
        targets = self._observations.get(ObservationKey("targets", project_id))
        if issues is None or targets is None:
            return None
        project = self.projects_by_id[project_id]
        project_diagnostics = _unique_diagnostics(
            [*issues.project_diagnostics, *targets.project_diagnostics]
        )
        elapsed_ms = issues.elapsed_ms + targets.elapsed_ms
        never_observed = issues.last_good_at is None and targets.last_good_at is None
        if project_diagnostics and never_observed:
            snapshot = None
        else:
            snapshot = ProjectSnapshot(
                project_id=project.project_id,
                display_label=project.display_label,
                repository_id=project.repository_id,
                collected_at=self.clock(),
                issue_source_status=issues.status,
                issue_source_attempted_at=issues.attempted_at,
                issue_source_last_good_at=issues.last_good_at,
                observation_targets=targets.data,
                issues=issues.data,
                diagnostics=[*issues.diagnostics, *targets.diagnostics],
                label_colors=issues.label_colors,
                issue_activity=issues.issue_activity,
                target_status=targets.status,
                target_attempted_at=targets.attempted_at,
                target_last_good_at=targets.last_good_at,
                branches=targets.branches,
                fetched_at=targets.fetched_at,
                integration_ref=targets.integration_ref,
            )
        return ProjectObservation(
            project_id=project.project_id,
            display_label=project.display_label,
            repository_id=project.repository_id,
            workspaces=project.workspaces,
            anchors=project.anchors,
            primary_anchor=project.primary_anchor,
            status=issues.status,
            elapsed_ms=elapsed_ms,
            snapshot=snapshot,
            diagnostics=project_diagnostics,
        )

    def _observe_agent_runs(self) -> _AgentObservation:
        # Project Observations are frozen, so sharing them outside the lock
        # only needs a snapshot of the mapping itself.
        with self._state_lock:
            published = dict(self._composed)
        targets_by_project = {
            project_id: observation.snapshot.observation_targets
            for project_id, observation in published.items()
            if observation.snapshot is not None
        }
        try:
            agent_runs, agent_diagnostics = self.agent_observer(targets_by_project)
        except OBSERVATION_FAILURES as exc:
            agent_runs = []
            agent_diagnostics = [
                Diagnostic(
                    source="workspace",
                    severity="warning",
                    message=f"Cannot observe Agent Runs: {exc}",
                    code="agent-observation",
                )
            ]
        # Projects not yet composed take part in binding as unobserved so a
        # bound Issue they own is deferred rather than reported as missing.
        binding_projects = [
            published.get(project.project_id) or _pending_project(project)
            for project in self.projects
        ]
        binding = bind_issue_runs(binding_projects, agent_runs)
        return _AgentObservation(
            tuple(agent_runs),
            binding.issue_runs,
            (*self.diagnostics, *agent_diagnostics, *binding.diagnostics),
        )


class SnapshotCollector(Protocol):
    def refresh(self) -> WorkspaceSnapshot: ...


class SnapshotScheduler:
    """Schedule a single-shot ``refresh()`` collector as one Workspace key.

    The whole checkpoint is published atomically; only ticket generations are
    tracked so a superseded refresh cannot overwrite a newer one.
    """

    def __init__(self, collector: SnapshotCollector) -> None:
        self.collector = collector
        self._lock = threading.Lock()
        self._generation = 0
        self._pending: WorkspaceSnapshot | None = None

    def keys(self, project_id: str | None = None) -> list[ObservationKey]:
        return [WORKSPACE_KEY]

    def follow_ups(self, changes: Sequence[StoreChange]) -> list[ObservationKey]:
        return []

    def request(self, keys: Sequence[ObservationKey]) -> list[ObservationTicket]:
        with self._lock:
            self._generation += 1
            return [ObservationTicket(WORKSPACE_KEY, self._generation)]

    def is_current(self, ticket: ObservationTicket) -> bool:
        with self._lock:
            return ticket.generation == self._generation

    def observe(self, ticket: ObservationTicket) -> ObservationOutcome:
        if not self.is_current(ticket):
            return ObservationOutcome(ticket, accepted=False)
        snapshot = self.collector.refresh()
        with self._lock:
            if ticket.generation != self._generation:
                return ObservationOutcome(ticket, accepted=False)
            self._pending = snapshot
        return ObservationOutcome(ticket, accepted=True)

    def publish(self, store: WorkspaceObservationStore) -> list[StoreChange]:
        with self._lock:
            snapshot, self._pending = self._pending, None
        if snapshot is None:
            return []
        return [store.replace(snapshot)]


def _pending_project(project: ResolvedProject) -> ProjectObservation:
    return ProjectObservation(
        project_id=project.project_id,
        display_label=project.display_label,
        repository_id=project.repository_id,
        workspaces=project.workspaces,
        anchors=project.anchors,
        primary_anchor=project.primary_anchor,
        status="unavailable",
        elapsed_ms=0,
        snapshot=None,
        diagnostics=[],
    )


def _issue_diagnostics(
    observation: IssueSourceObservation,
) -> list[Diagnostic]:
    return [
        Diagnostic(
            source=diagnostic.source,
            severity=diagnostic.severity,
            message=diagnostic.message,
            code=diagnostic.code,
        )
        for diagnostic in observation.diagnostics
    ]


def _target_discovery_diagnostic(project_id: str, exc: BaseException) -> Diagnostic:
    return Diagnostic(
        source=f"project:{project_id}",
        severity="warning",
        message=f"Cannot discover Observation Targets: {exc}",
        code="target-discovery",
    )


def _unique_diagnostics(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
    unique: list[Diagnostic] = []
    for diagnostic in diagnostics:
        if diagnostic not in unique:
            unique.append(diagnostic)
    return unique
