from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .issue_profile import IssueProfileError, conform_issue_v1
from .issue_sources import Clock, IssueSource, IssueSourceRefreshError


LOCAL_MARKDOWN_SCHEMA_VERSION = 1
_LOCAL_METADATA_KEYS = {
    "schemaVersion",
    "id",
    "reference",
    "state",
    "stateReason",
    "labels",
    "assignees",
    "author",
    "relationships",
    "issueType",
    "milestone",
    "createdAt",
    "updatedAt",
    "closedAt",
}


class LocalMarkdownIssueError(ValueError):
    """A Local Issue document cannot produce a complete Issue profile."""

    def __init__(self, message: str, *, code: str = "markdown-malformed") -> None:
        super().__init__(message)
        self.code = code


class LocalMarkdownIssuesV1Source(IssueSource):
    """Collect Issue profile v1 snapshots from local Markdown documents."""

    def __init__(
        self,
        root: Path,
        *,
        issues_path: Path,
        project_id: str,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.root = root
        self.issues_path = issues_path
        self.project_id = project_id

    @property
    def name(self) -> str:
        return "local-markdown-issues-v1"

    def _collect(self) -> list[dict[str, Any]]:
        try:
            root = self.root.resolve()
            path = (root / self.issues_path).resolve()
            if not path.is_relative_to(root):
                raise IssueSourceRefreshError(
                    "markdown-path",
                    "Configured Local Issue path must stay inside the Repository Anchor",
                )
            if not path.exists():
                raise IssueSourceRefreshError(
                    "markdown-not-found",
                    f"Configured Local Issue path does not exist: {self.issues_path}",
                )
            paths = sorted(path.rglob("*.md")) if path.is_dir() else [path]
            issues: list[dict[str, Any]] = []
            seen_issue_ids: set[str] = set()
            for issue_path in paths:
                if not issue_path.resolve().is_relative_to(root):
                    raise IssueSourceRefreshError(
                        "markdown-path",
                        "Local Issue files must stay inside the Repository Anchor",
                    )
                relative_path = issue_path.relative_to(root).as_posix()
                try:
                    issue = parse_local_markdown_issue_v1(
                        issue_path.read_text(encoding="utf-8"),
                        project_id=self.project_id,
                        path=relative_path,
                    )
                except LocalMarkdownIssueError as exc:
                    raise LocalMarkdownIssueError(
                        f"{relative_path}: {exc}", code=exc.code
                    ) from exc
                issue_id = issue["id"]
                if issue_id in seen_issue_ids:
                    raise IssueSourceRefreshError(
                        "markdown-duplicate-identity",
                        f"Local Markdown contains duplicate Issue identity {issue_id}",
                    )
                seen_issue_ids.add(issue_id)
                issues.append(issue)
        except LocalMarkdownIssueError as exc:
            raise IssueSourceRefreshError(exc.code, str(exc)) from exc
        except PermissionError as exc:
            raise IssueSourceRefreshError("markdown-permission", str(exc)) from exc
        except UnicodeError as exc:
            raise IssueSourceRefreshError("markdown-malformed", str(exc)) from exc
        except FileNotFoundError as exc:
            raise IssueSourceRefreshError("markdown-not-found", str(exc)) from exc
        except OSError as exc:
            raise IssueSourceRefreshError("markdown-io", str(exc)) from exc
        return issues


def parse_local_markdown_issue_v1(
    text: str, *, project_id: str, path: str
) -> dict[str, Any]:
    """Parse one version 1 Local Issue Markdown document."""

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise LocalMarkdownIssueError("Local Issue must start with JSON front matter")
    try:
        front_matter_end = lines.index("---", 1)
    except ValueError as exc:
        raise LocalMarkdownIssueError("Local Issue front matter is not closed") from exc
    try:
        metadata = json.loads(
            "\n".join(lines[1:front_matter_end]),
            object_pairs_hook=_json_object_without_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise LocalMarkdownIssueError(
            f"Local Issue front matter is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(metadata, dict):
        raise LocalMarkdownIssueError("Local Issue front matter must be an object")
    metadata = dict(metadata)
    if "schemaVersion" not in metadata:
        raise LocalMarkdownIssueError("Local Issue is missing schemaVersion")
    schema_version = metadata["schemaVersion"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != LOCAL_MARKDOWN_SCHEMA_VERSION
    ):
        raise LocalMarkdownIssueError(
            "schemaVersion must be 1", code="markdown-unsupported-version"
        )
    missing = sorted(_LOCAL_METADATA_KEYS - set(metadata))
    unexpected = sorted(set(metadata) - _LOCAL_METADATA_KEYS)
    if missing:
        raise LocalMarkdownIssueError(
            f"Local Issue metadata is missing fields: {', '.join(missing)}",
            code="markdown-profile",
        )
    if unexpected:
        raise LocalMarkdownIssueError(
            f"Local Issue metadata has unexpected fields: {', '.join(unexpected)}",
            code="markdown-profile",
        )
    metadata.pop("schemaVersion")

    title_line = front_matter_end + 1
    while title_line < len(lines) and not lines[title_line]:
        title_line += 1
    if title_line == len(lines) or not lines[title_line].startswith("# "):
        raise LocalMarkdownIssueError(
            "Local Issue front matter must be followed by a level-one title"
        )
    title = lines[title_line][2:]
    body_lines = lines[title_line + 1 :]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]

    profile = {
        "profileVersion": 1,
        "projectId": project_id,
        "title": title,
        "body": "\n".join(body_lines),
        **metadata,
        "origin": {
            "kind": "markdown",
            "schemaVersion": schema_version,
        },
        "location": {
            "kind": "markdown",
            "path": path,
            "line": title_line + 1,
        },
    }
    try:
        return conform_issue_v1(profile)
    except IssueProfileError as exc:
        raise LocalMarkdownIssueError(
            f"Local Issue does not conform to profile v1: {exc}",
            code="markdown-profile",
        ) from exc


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LocalMarkdownIssueError(f"duplicate metadata key: {key}")
        value[key] = item
    return value
