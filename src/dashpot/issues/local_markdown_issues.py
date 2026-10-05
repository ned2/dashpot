"""Observe a local Markdown Issue Source and conform its Issues to the Issue Profile."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

from ..core.errors import DashpotError
from ..core.issue_profile import IssueProfile, IssueProfileError, conform_issue
from .issue_sources import (
    CollectedIssues,
    IssueHint,
    IssueSource,
    IssueSourceRefreshError,
)
from .retaining_source import Clock

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


class LocalMarkdownIssueError(DashpotError, ValueError):
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

    @property
    @override
    def code_prefix(self) -> str:
        return "markdown"

    @override
    def find(self, hint: IssueHint) -> IssueProfile | None:
        """Resolve a slug hint by reading its one conventional document.

        Documents are named by slug, so only a Reference hint has a
        conventional path — a Number hint still scans the whole collection,
        an asymmetry a numbered file convention would remove. A document
        found elsewhere than its conventional path falls back to the scan;
        when two documents share one slug, the conventional path wins here
        where only the full scan can see the ambiguity and refuse it.
        """
        if hint.reference is None:
            return super().find(hint)
        root = self.root.resolve()
        directory = (root / self.issues_path).resolve()
        if not directory.is_dir() or not directory.is_relative_to(root):
            return super().find(hint)
        candidate = directory / f"{hint.reference}.md"
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(directory) or not candidate.is_file():
                return super().find(hint)
            relative_path = resolved.relative_to(root).as_posix()
            text = candidate.read_bytes().decode("utf-8")
        except (OSError, ValueError):
            return super().find(hint)
        try:
            issue = parse_local_markdown_issue(
                text, project_id=self.project_id, path=relative_path
            )
        except LocalMarkdownIssueError as exc:
            raise IssueSourceRefreshError(exc.code, f"{relative_path}: {exc}") from exc
        if issue.reference != hint.reference:
            return super().find(hint)
        return issue

    def read_documents(self) -> tuple[LocalIssueDocument, ...]:
        """Read the complete collection's documents, refusing what a refresh refuses.

        A consumer that needs the documents themselves, such as a revision
        digest over their bytes, reads them here, under the same rules and
        Diagnostic codes as ``refresh``.
        """
        documents = read_local_issue_documents(
            self.root, self.issues_path, project_id=self.project_id
        )
        self._check_collection_invariants(_collected(documents))
        return documents

    @override
    def _collect(self) -> CollectedIssues:
        return _collected(
            read_local_issue_documents(
                self.root, self.issues_path, project_id=self.project_id
            )
        )


@dataclass(frozen=True, slots=True)
class LocalIssueDocument:
    """One Local Issue document as read: its path, its bytes, and its Issue.

    ``path`` is repository-relative POSIX text, and ``content`` is exactly
    the bytes the Issue was parsed from.
    """

    path: str
    content: bytes
    issue: IssueProfile


def read_local_issue_documents(
    root: Path, issues_path: Path, *, project_id: str
) -> tuple[LocalIssueDocument, ...]:
    """Read and parse every Local Issue document a configured path names.

    The configured path and every discovered document must resolve inside
    the Repository Anchor ``root``; a directory's ``*.md`` documents are read
    in repository-relative POSIX path order. Every failure is an
    ``IssueSourceRefreshError`` with its ``markdown-*`` code. The collection
    invariants are the caller's: ``LocalMarkdownIssuesSource`` checks them.
    """
    try:
        anchor = root.resolve()
        path = (anchor / issues_path).resolve()
        if not path.is_relative_to(anchor):
            raise IssueSourceRefreshError(
                "markdown-path",
                "Configured Local Issue path must stay inside the Repository Anchor",
            )
        if not path.exists():
            raise IssueSourceRefreshError(
                "markdown-not-found",
                f"Configured Local Issue path does not exist: {issues_path}",
            )
        # The contract orders documents by repository-relative POSIX path;
        # sorting Paths compares their parts, which puts "a/b.md" before
        # "a-b.md" though "/" sorts after "-" as text.
        paths = (
            sorted(path.rglob("*.md"), key=lambda found: found.as_posix())
            if path.is_dir()
            else [path]
        )
        documents: list[LocalIssueDocument] = []
        for document_path in paths:
            if not document_path.resolve().is_relative_to(anchor):
                raise IssueSourceRefreshError(
                    "markdown-path",
                    "Local Issue files must stay inside the Repository Anchor",
                )
            relative_path = document_path.relative_to(anchor).as_posix()
            content = document_path.read_bytes()
            try:
                issue = parse_local_markdown_issue(
                    content.decode("utf-8"),
                    project_id=project_id,
                    path=relative_path,
                )
            except LocalMarkdownIssueError as exc:
                raise LocalMarkdownIssueError(
                    f"{relative_path}: {exc}", code=exc.code
                ) from exc
            documents.append(LocalIssueDocument(relative_path, content, issue))
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
    return tuple(documents)


def _collected(documents: tuple[LocalIssueDocument, ...]) -> CollectedIssues:
    return CollectedIssues(tuple(document.issue for document in documents))


def parse_local_markdown_issue(
    text: str, *, project_id: str, path: str
) -> IssueProfile:
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
