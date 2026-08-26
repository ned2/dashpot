from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from .agents import observe_hook_runs
from .correlation import correlate
from .model import (
    AgentRun,
    Diagnostic,
    ProjectObservation,
    ProjectSnapshot,
    ProjectTarget,
    Repository,
    WorkspaceEntry,
    WorkspaceSnapshot,
)
from .repository import github_repo_from_remote, load_config, observe_repository
from .sources import GitHubIssuesSource, LocalTasksSource, TaskSource, now_iso, optional_string


AgentObserver = Callable[[Repository], tuple[list[AgentRun], list[Diagnostic]]]
RepositoryObserver = Callable[[Path], Repository]


class ProjectCollector:
    def __init__(
        self,
        root: Path,
        source: TaskSource,
        repository_observer: RepositoryObserver = observe_repository,
        agent_observer: AgentObserver = observe_hook_runs,
    ) -> None:
        self.root = root
        self.source = source
        self.repository_observer = repository_observer
        self.agent_observer = agent_observer

    def refresh(self) -> ProjectSnapshot:
        repository = self.repository_observer(self.root)
        task_observation = self.source.refresh()
        agent_runs, agent_diagnostics = self.agent_observer(repository)
        correlate(task_observation.tasks, agent_runs)
        diagnostics = list(agent_diagnostics)
        if task_observation.diagnostic:
            diagnostics.insert(0, task_observation.diagnostic)
        return ProjectSnapshot(
            collected_at=now_iso(),
            task_source_status=task_observation.status,
            task_source_attempted_at=task_observation.attempted_at,
            task_source_last_good_at=task_observation.last_good_at,
            repository=repository,
            tasks=task_observation.tasks,
            agent_runs=agent_runs,
            diagnostics=diagnostics,
        )


def create_project_collector(
    repository_path: str | Path = ".",
    backend_override: str | None = None,
    github_repo: str | None = None,
    github_label: str | None = None,
    tasks_command: str = "tasks",
    timeout: float = 10,
    state_dir: Path | None = None,
) -> ProjectCollector:
    requested_root = Path(repository_path).resolve()
    repository = observe_repository(requested_root)
    root = Path(repository.root)
    config = load_config(root)
    backend = backend_override or optional_string(config.get("backend")) or "tasks-md"
    if backend not in {"tasks-md", "github-issues"}:
        raise RuntimeError(f"unsupported configured backend: {backend!r}")
    if backend == "github-issues":
        repo = github_repo or optional_string(config.get("repo")) or github_repo_from_remote(root)
        if not repo:
            raise RuntimeError("GitHub backend needs config repo or a GitHub origin remote")
        label = github_label or optional_string(config.get("label")) or "tasks.md"
        source: TaskSource = GitHubIssuesSource(root, repo, label, timeout)
    else:
        source = LocalTasksSource(root, tasks_command, timeout)
    return ProjectCollector(
        root,
        source,
        agent_observer=lambda current: observe_hook_runs(current, state_dir),
    )


class WorkspaceCollector:
    """Refresh independent project collectors concurrently with failure isolation."""

    def __init__(
        self,
        targets: Sequence[ProjectTarget],
        tasks_command: str = "tasks",
        timeout: float = 10,
        state_dir: Path | None = None,
        factory: Callable[..., ProjectCollector] = create_project_collector,
    ) -> None:
        self.targets = list(targets)
        self.tasks_command = tasks_command
        self.timeout = timeout
        self.state_dir = state_dir
        self.factory = factory
        self.collectors: dict[str, ProjectCollector] = {}
        self.refresh_lock = threading.Lock()

    def refresh(self) -> WorkspaceSnapshot:
        # Textual can cancel a thread worker but cannot stop its Python thread.
        # Serialize generations so stateful last-good source caches are never
        # refreshed concurrently by a superseding UI request.
        with self.refresh_lock:
            return self._refresh()

    def _refresh(self) -> WorkspaceSnapshot:
        started = time.monotonic()
        worker_count = max(1, min(8, len(self.targets)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(self.refresh_one, target) for target in self.targets]
            projects = [future.result() for future in futures]
        return WorkspaceSnapshot(
            collected_at=now_iso(),
            elapsed_ms=round((time.monotonic() - started) * 1000),
            projects=projects,
        )

    def refresh_one(self, target: ProjectTarget) -> ProjectObservation:
        started = time.monotonic()
        root = Path(target.root)
        try:
            if not root.is_dir():
                raise RuntimeError(f"repository root does not exist or is not a directory: {root}")
            collector = self.collectors.get(target.root)
            if collector is None:
                collector = self.factory(
                    root,
                    tasks_command=self.tasks_command,
                    timeout=self.timeout,
                    state_dir=self.state_dir,
                )
                self.collectors[target.root] = collector
            snapshot = collector.refresh()
            return ProjectObservation(
                target.workspace,
                target.repository,
                target.root,
                snapshot.task_source_status,
                round((time.monotonic() - started) * 1000),
                snapshot,
                [],
            )
        except (OSError, RuntimeError) as exc:
            return ProjectObservation(
                target.workspace,
                target.repository,
                target.root,
                "unavailable",
                round((time.monotonic() - started) * 1000),
                None,
                [Diagnostic(f"workspace:{target.workspace}/{target.repository}", "error", str(exc))],
            )


def default_workspace_config() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "tasks-md" / "workspaces.json"


def load_workspace_entries(path: Path) -> list[WorkspaceEntry]:
    try:
        raw: Any = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"workspace config not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read workspace config {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("workspaces"), list):
        raise RuntimeError(f"workspace config {path} must contain a workspaces array")
    entries: list[WorkspaceEntry] = []
    for index, item in enumerate(raw["workspaces"]):
        if not isinstance(item, dict):
            raise RuntimeError(f"workspace entry {index} must be an object")
        name = item.get("name")
        root = item.get("root")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"workspace entry {index} needs a non-empty name")
        if not isinstance(root, str) or not root.strip():
            raise RuntimeError(f"workspace entry {index} needs a non-empty root")
        entries.append(WorkspaceEntry(name.strip(), str(Path(root).expanduser().resolve())))
    return entries


def discover_project_targets(entries: Sequence[WorkspaceEntry]) -> list[ProjectTarget]:
    targets: list[ProjectTarget] = []
    seen: set[Path] = set()
    for entry in entries:
        entry_root = Path(entry.root)
        roots = discover_repository_roots(entry_root) or [entry_root]
        for root in roots:
            canonical = root.resolve()
            if canonical in seen:
                continue
            seen.add(canonical)
            repository = "." if canonical == entry_root else canonical.name
            targets.append(ProjectTarget(entry.name, repository, str(canonical)))
    return targets


def discover_repository_roots(workspace_root: Path) -> list[Path]:
    def has_task_source(path: Path) -> bool:
        return (path / "TASKS.md").is_file() or (path / ".tasksmd.json").is_file()

    roots: list[Path] = []
    if has_task_source(workspace_root):
        roots.append(workspace_root)
    try:
        children = sorted(workspace_root.iterdir(), key=lambda child: child.name)
    except OSError:
        return roots
    for child in children:
        if child.name.startswith(".") or child.name == "node_modules":
            continue
        if child.is_dir() and has_task_source(child):
            roots.append(child)
    return roots
