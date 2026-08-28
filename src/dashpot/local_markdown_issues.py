from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typing_extensions import override

from .issue_profile import IssueProfileError, conform_issue
from .issue_sources import Clock, IssueSource, IssueSourceRefreshError

_LOCAL_METADATA_KEYS = {
    "id",
    "number",
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


class LocalMarkdownIssuesSource(IssueSource):
    """Collect complete Issue snapshots from local Markdown documents."""

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
    @override
    def name(self) -> str:
        return "local-markdown-issues"

    @override
    def _collect(self) -> list[dict[str, Any]]:
        try:
            root = self.root.resolve()
            path = (root / self.issues_path).resolve()
            if not path.is_relative_to(root):
                raise IssueSourceRefreshError(
                    "markdown-path",
                    "Configured Local Issue path must stay inside the "
                    "Repository Anchor",
                )
            if not path.exists():
                raise IssueSourceRefreshError(
                    "markdown-not-found",
                    f"Configured Local Issue path does not exist: {self.issues_path}",
                )
            paths = sorted(path.rglob("*.md")) if path.is_dir() else [path]
            issues: list[dict[str, Any]] = []
            seen_issue_ids: set[str] = set()
            issue_paths_by_number: dict[int, str] = {}
            for issue_path in paths:
                if not issue_path.resolve().is_relative_to(root):
                    raise IssueSourceRefreshError(
                        "markdown-path",
                        "Local Issue files must stay inside the Repository Anchor",
                    )
                relative_path = issue_path.relative_to(root).as_posix()
                try:
                    issue = parse_local_markdown_issue(
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
                issue_number = issue["number"]
                previous_path = issue_paths_by_number.get(issue_number)
                if previous_path is not None:
                    raise IssueSourceRefreshError(
                        "markdown-duplicate-number",
                        f"Local Markdown Issue Number #{issue_number} appears in "
                        f"both {previous_path} and {relative_path}",
                    )
                seen_issue_ids.add(issue_id)
                issue_paths_by_number[issue_number] = relative_path
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


def parse_local_markdown_issue(
    text: str, *, project_id: str, path: str
) -> dict[str, Any]:
    """Parse one Local Issue Markdown document."""

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
        "projectId": project_id,
        "title": title,
        "body": "\n".join(body_lines),
        **metadata,
        "origin": {"kind": "markdown"},
        "location": {
            "kind": "markdown",
            "path": path,
            "line": title_line + 1,
        },
    }
    try:
        return conform_issue(profile)
    except IssueProfileError as exc:
        raise LocalMarkdownIssueError(
            f"Local Issue does not conform to the Issue profile: {exc}",
            code="markdown-profile",
        ) from exc


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LocalMarkdownIssueError(f"duplicate metadata key: {key}")
        value[key] = item
    return value
