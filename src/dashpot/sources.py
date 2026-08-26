from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .commands import CommandRunner, run_command
from .model import BlockedState, Diagnostic, Location, Task, TaskObservation


PRIORITY_FROM_LABEL = {
    "priority/p0": "P0",
    "priority/p1": "P1",
    "priority/p2": "P2",
    "priority/p3": "P3",
    "critical": "P0",
    "p0": "P0",
    "high": "P1",
    "p1": "P1",
    "medium": "P2",
    "p2": "P2",
    "low": "P3",
    "p3": "P3",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskSource:
    """Backend adapter which preserves the last good value across refresh failures."""

    def __init__(self) -> None:
        self._last_good: list[Task] | None = None
        self._last_good_at: str | None = None

    @property
    def name(self) -> str:
        raise NotImplementedError

    def collect(self) -> list[Task]:
        raise NotImplementedError

    def refresh(self) -> TaskObservation:
        attempted_at = now_iso()
        try:
            tasks = self.collect()
        except RuntimeError as exc:
            severity = "warning" if self._last_good is not None else "error"
            return TaskObservation(
                status="stale" if self._last_good is not None else "unavailable",
                attempted_at=attempted_at,
                last_good_at=self._last_good_at,
                tasks=copy.deepcopy(self._last_good or []),
                diagnostic=Diagnostic(self.name, severity, str(exc)),
            )
        self._last_good = copy.deepcopy(tasks)
        self._last_good_at = attempted_at
        return TaskObservation("fresh", attempted_at, attempted_at, tasks)


class LocalTasksSource(TaskSource):
    def __init__(
        self,
        root: Path,
        command: str = "tasks",
        timeout: float = 5,
        runner: CommandRunner = run_command,
    ) -> None:
        super().__init__()
        self.root = root
        self.command = command
        self.timeout = timeout
        self.runner = runner

    @property
    def name(self) -> str:
        return "tasks-md"

    def collect(self) -> list[Task]:
        result = self.runner([self.command, "list", "--json"], self.root, self.timeout)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            raise RuntimeError(f"tasks list failed: {detail}")
        tasks: list[Task] = []
        for record in parse_json_array(result.stdout, "tasks list"):
            item_id = optional_string(record.get("id"))
            file = optional_string(record.get("file"))
            line = record.get("line") if isinstance(record.get("line"), int) else None
            identity_file = file
            if file:
                try:
                    identity_file = str(Path(file).relative_to(self.root))
                except ValueError:
                    pass
            identity = item_id or f"{identity_file or '<unknown>'}:{line or '?'}"
            blocked: BlockedState = (
                record["blocked"] if isinstance(record.get("blocked"), bool) else "unknown"
            )
            tasks.append(
                Task(
                    key=f"tasks-md:{self.root}:{identity}",
                    source="tasks-md",
                    title=require_string(record, "summary", "tasks list"),
                    priority=optional_string(record.get("priority")) or "P2",
                    tags=string_list(record.get("tags")),
                    declared_claimant=optional_string(record.get("claimed")),
                    declared_blocked=blocked,
                    location=Location(file=file, line=line) if file or line else None,
                )
            )
        return tasks


class GitHubIssuesSource(TaskSource):
    def __init__(
        self,
        root: Path,
        repo: str,
        label: str = "tasks.md",
        timeout: float = 10,
        runner: CommandRunner = run_command,
    ) -> None:
        super().__init__()
        self.root = root
        self.repo = repo
        self.label = label
        self.timeout = timeout
        self.runner = runner

    @property
    def name(self) -> str:
        return "github-issues"

    def collect(self) -> list[Task]:
        args = [
            "gh",
            "issue",
            "list",
            "--repo",
            self.repo,
            "--label",
            self.label,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,labels,assignees,url",
        ]
        result = self.runner(args, self.root, self.timeout)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            raise RuntimeError(f"gh issue list failed: {detail}")
        tasks = [self.normalize(record) for record in parse_json_array(result.stdout, "gh issue list")]
        tasks.sort(key=lambda task: priority_rank(task.priority))
        return tasks

    def normalize(self, record: dict[str, Any]) -> Task:
        number = record.get("number")
        if not isinstance(number, int):
            raise RuntimeError("gh issue list item has no numeric issue number")
        labels = object_string_list(record.get("labels"), "name")
        priority = min(
            (
                PRIORITY_FROM_LABEL[label.lower()]
                for label in labels
                if label.lower() in PRIORITY_FROM_LABEL
            ),
            key=priority_rank,
            default="P2",
        )
        assignees = object_string_list(record.get("assignees"), "login")
        tags = [
            label
            for label in labels
            if label.lower() != self.label.lower()
            and label.lower() not in PRIORITY_FROM_LABEL
        ]
        return Task(
            key=f"github:{self.repo}#{number}",
            source="github-issues",
            title=require_string(record, "title", "gh issue list"),
            priority=priority,
            tags=tags,
            declared_claimant=assignees[0] if assignees else None,
            declared_blocked="unknown",
            location=Location(url=optional_string(record.get("url"))),
        )


def priority_rank(value: str) -> int:
    return int(value[1]) if re.fullmatch(r"P[0-3]", value) else 2


def parse_json_array(raw: str, source: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{source} returned malformed JSON: {exc.msg}") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"{source} returned JSON that is not an array of objects")
    return value


def require_string(record: dict[str, Any], key: str, source: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{source} item has no string {key}")
    return value


def optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def object_string_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item[key]
        for item in value
        if isinstance(item, dict) and isinstance(item.get(key), str)
    ]
