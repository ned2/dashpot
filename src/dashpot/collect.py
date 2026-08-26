from __future__ import annotations

import concurrent.futures
import threading
import time
from pathlib import Path
from typing import Callable, Sequence

from .agents import observe_hook_runs
from .correlation import correlate_issues
from .github_issues import GitHubIssuesSource
from .issue_sources import IssueSource, utc_now
from .local_markdown_issues import LocalMarkdownIssuesSource
from .model import (
    AgentRun,
    Diagnostic,
    ProjectObservation,
    ProjectSnapshot,
    Repository,
    ResolvedProject,
    WorkspaceSnapshot,
)
from .project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
)
from .repository import github_repo_from_remote, observe_repository


AgentObserver = Callable[[Repository], tuple[list[AgentRun], list[Diagnostic]]]
RepositoryObserver = Callable[[Path], Repository]


class ProjectCollector:
    def __init__(
        self,
        project: ResolvedProject,
        source: IssueSource,
        repository_observer: RepositoryObserver = observe_repository,
        agent_observer: AgentObserver = observe_hook_runs,
    ) -> None:
        self.project = project
        self.root = Path(project.primary_anchor)
        self.source = source
        self.repository_observer = repository_observer
        self.agent_observer = agent_observer

    def refresh(self) -> ProjectSnapshot:
        repository = self.repository_observer(self.root)
        issue_observation = self.source.refresh()
        agent_runs, agent_diagnostics = self.agent_observer(repository)
        issue_runs = correlate_issues(issue_observation.issues, agent_runs)
        diagnostics = list(agent_diagnostics)
        diagnostics[0:0] = [
            Diagnostic(
                diagnostic.source,
                diagnostic.severity,
                diagnostic.message,
                diagnostic.code,
            )
            for diagnostic in issue_observation.diagnostics
        ]
        return ProjectSnapshot(
            project_id=self.project.project_id,
            display_label=self.project.display_label,
            repository_id=self.project.repository_id,
            collected_at=utc_now(),
            issue_source_status=issue_observation.status,
            issue_source_attempted_at=issue_observation.attempted_at,
            issue_source_last_good_at=issue_observation.last_good_at,
            repository=repository,
            issues=issue_observation.issues,
            issue_runs=issue_runs,
            agent_runs=agent_runs,
            diagnostics=diagnostics,
        )


def create_project_collector(
    project: ResolvedProject,
    timeout: float = 10,
    state_dir: Path | None = None,
) -> ProjectCollector:
    requested_root = Path(project.primary_anchor)
    repository = observe_repository(requested_root)
    root = Path(repository.root)
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
            repository_reference=repository_reference,
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
        agent_observer=lambda current: observe_hook_runs(current, state_dir),
    )


class WorkspaceCollector:
    """Refresh independent project collectors concurrently with failure isolation."""

    def __init__(
        self,
        projects: Sequence[ResolvedProject],
        timeout: float = 10,
        state_dir: Path | None = None,
        factory: Callable[..., ProjectCollector] = create_project_collector,
        diagnostics: Sequence[Diagnostic] = (),
    ) -> None:
        self.projects = list(projects)
        self.timeout = timeout
        self.state_dir = state_dir
        self.factory = factory
        self.diagnostics = list(diagnostics)
        self.collectors: dict[str, ProjectCollector] = {}
        self.refresh_lock = threading.Lock()

    def refresh(self) -> WorkspaceSnapshot:
        # Textual can cancel the refresh coroutine but cannot stop its executor call.
        # Serialize generations so stateful last-good source caches are never
        # refreshed concurrently by a superseding UI request.
        with self.refresh_lock:
            return self._refresh()

    def _refresh(self) -> WorkspaceSnapshot:
        started = time.monotonic()
        worker_count = max(1, min(8, len(self.projects)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [
                pool.submit(self.refresh_one, project) for project in self.projects
            ]
            projects = [future.result() for future in futures]
        return WorkspaceSnapshot(
            collected_at=utc_now(),
            elapsed_ms=round((time.monotonic() - started) * 1000),
            projects=projects,
            diagnostics=list(self.diagnostics),
        )

    def refresh_one(self, project: ResolvedProject) -> ProjectObservation:
        started = time.monotonic()
        root = Path(project.primary_anchor)
        try:
            if not root.is_dir():
                raise RuntimeError(
                    "repository root does not exist or is not a directory: "
                    f"{root}"
                )
            collector = self.collectors.get(project.project_id)
            if collector is None:
                collector = self.factory(
                    project,
                    timeout=self.timeout,
                    state_dir=self.state_dir,
                )
                self.collectors[project.project_id] = collector
            snapshot = collector.refresh()
            return ProjectObservation(
                project.project_id,
                project.display_label,
                project.repository_id,
                list(project.workspaces),
                list(project.anchors),
                project.primary_anchor,
                snapshot.issue_source_status,
                round((time.monotonic() - started) * 1000),
                snapshot,
                [],
            )
        except (OSError, RuntimeError) as exc:
            return ProjectObservation(
                project.project_id,
                project.display_label,
                project.repository_id,
                list(project.workspaces),
                list(project.anchors),
                project.primary_anchor,
                "unavailable",
                round((time.monotonic() - started) * 1000),
                None,
                [
                    Diagnostic(
                        f"project:{project.project_id}",
                        "error",
                        str(exc),
                        "project-collection",
                    )
                ],
            )
