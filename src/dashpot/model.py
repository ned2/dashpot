from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SourceStatus = Literal["fresh", "stale", "unavailable"]
BlockedState = bool | Literal["unknown"]
RunState = Literal["running", "waiting", "unknown"]


@dataclass(slots=True)
class Diagnostic:
    source: str
    severity: Literal["info", "warning", "error"]
    message: str


@dataclass(slots=True)
class Location:
    file: str | None = None
    line: int | None = None
    url: str | None = None


@dataclass(slots=True)
class WorkItem:
    key: str
    source: str
    title: str
    priority: str
    tags: list[str]
    declared_claimant: str | None
    declared_blocked: BlockedState
    location: Location | None
    observed_runs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskObservation:
    status: SourceStatus
    attempted_at: str
    last_good_at: str | None
    work_items: list[WorkItem]
    diagnostic: Diagnostic | None = None


@dataclass(slots=True)
class Worktree:
    path: str
    head: str
    branch: str | None


@dataclass(slots=True)
class Repository:
    root: str
    name: str
    branch: str | None
    head: str
    dirty: bool
    worktrees: list[Worktree]


@dataclass(slots=True)
class AgentRun:
    id: str
    harness: str
    process_or_session: str
    state: RunState
    repository_root: str | None
    worktree: str | None
    branch: str | None
    declared_work_key: str | None
    working_directory: str | None = None
    last_activity_at: str | None = None


@dataclass(slots=True)
class ProjectSnapshot:
    collected_at: str
    task_source_status: SourceStatus
    task_source_attempted_at: str
    task_source_last_good_at: str | None
    repository: Repository
    work_items: list[WorkItem]
    agent_runs: list[AgentRun]
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    name: str
    root: str


@dataclass(frozen=True, slots=True)
class ProjectTarget:
    workspace: str
    repository: str
    root: str


@dataclass(slots=True)
class ProjectObservation:
    workspace: str
    repository: str
    root: str
    status: SourceStatus
    elapsed_ms: int
    snapshot: ProjectSnapshot | None
    diagnostics: list[Diagnostic]


@dataclass(slots=True)
class WorkspaceSnapshot:
    collected_at: str
    elapsed_ms: int
    projects: list[ProjectObservation]


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            camel_case(key): to_jsonable(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def camel_case(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)
