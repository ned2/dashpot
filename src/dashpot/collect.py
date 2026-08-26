from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

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
    ProjectTarget,
    Repository,
    WorkspaceEntry,
    WorkspaceSnapshot,
)
from .project_config import (
    PROJECT_CONFIG_NAME,
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
        root: Path,
        source: IssueSource,
        repository_observer: RepositoryObserver = observe_repository,
        agent_observer: AgentObserver = observe_hook_runs,
    ) -> None:
        self.root = root
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
    repository_path: str | Path = ".",
    timeout: float = 10,
    state_dir: Path | None = None,
) -> ProjectCollector:
    requested_root = Path(repository_path).resolve()
    repository = observe_repository(requested_root)
    root = Path(repository.root)
    config = load_project_config(root)
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
            repository_id=config.issue_source.repository_id,
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
        root,
        source,
        agent_observer=lambda current: observe_hook_runs(current, state_dir),
    )


class WorkspaceCollector:
    """Refresh independent project collectors concurrently with failure isolation."""

    def __init__(
        self,
        targets: Sequence[ProjectTarget],
        timeout: float = 10,
        state_dir: Path | None = None,
        factory: Callable[..., ProjectCollector] = create_project_collector,
    ) -> None:
        self.targets = list(targets)
        self.timeout = timeout
        self.state_dir = state_dir
        self.factory = factory
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
        worker_count = max(1, min(8, len(self.targets)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(self.refresh_one, target) for target in self.targets]
            projects = [future.result() for future in futures]
        return WorkspaceSnapshot(
            collected_at=utc_now(),
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
                    timeout=self.timeout,
                    state_dir=self.state_dir,
                )
                self.collectors[target.root] = collector
            snapshot = collector.refresh()
            return ProjectObservation(
                target.workspace,
                target.repository,
                target.root,
                snapshot.issue_source_status,
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
                [
                    Diagnostic(
                        f"workspace:{target.workspace}/{target.repository}",
                        "error",
                        str(exc),
                    )
                ],
            )


def default_workspace_config() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "dashpot" / "workspaces.json"


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
        roots = discover_repository_roots(entry_root)
        for root in roots:
            canonical = root.resolve()
            if canonical in seen:
                continue
            seen.add(canonical)
            repository = "." if canonical == entry_root else canonical.name
            targets.append(ProjectTarget(entry.name, repository, str(canonical)))
    return targets


def discover_repository_roots(workspace_root: Path) -> list[Path]:
    def has_project_config(path: Path) -> bool:
        return (path / PROJECT_CONFIG_NAME).is_file()

    roots: list[Path] = []
    if has_project_config(workspace_root):
        roots.append(workspace_root)
    try:
        children = sorted(workspace_root.iterdir(), key=lambda child: child.name)
    except OSError:
        return roots
    for child in children:
        if child.name.startswith(".") or child.name == "node_modules":
            continue
        if child.is_dir() and has_project_config(child):
            roots.append(child)
    return roots
