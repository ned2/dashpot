"""Query a deterministic revision of configured Local Issue documents."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import override

from ..core.issue_profile import IssueProfile
from ..core.model import Diagnostic, ProjectObservation
from ..issues.local_markdown_issues import (
    LocalMarkdownIssuesSource,
    parse_local_markdown_issue,
)
from ..issues.ordering import is_issue_sort_column, sort_issues
from ..issues.search import IssueSearchField, matches_issue_search, parse_search
from ..project.project_config import (
    LocalMarkdownIssueSourceConfig,
    ProjectConfig,
    load_project_config,
)
from .query_source import CachedQuerySource
from .source_queries import (
    Continuation,
    InvalidContinuation,
    ProjectTotals,
    QueryPage,
    QueryRequest,
    ResolvedIssue,
    ResourceKind,
    SourceContext,
    SourceEnumeration,
    context_fingerprint,
    encode_continuation,
)


class MarkdownQuerySource(CachedQuerySource):
    def __init__(self, root: Path, config: ProjectConfig) -> None:
        assert isinstance(config.issue_source, LocalMarkdownIssueSourceConfig)
        self.root = root.resolve()
        self.config = config
        self.path = (self.root / config.issue_source.path).resolve()
        self.records: tuple[IssueProfile, ...] = ()
        self.export_source = LocalMarkdownIssuesSource(
            self.root,
            project_id=config.project_id,
            issues_path=Path(config.issue_source.path),
        )
        super().__init__(
            SourceContext(
                project_id=config.project_id,
                repository_id=config.repository_id,
                source="local-markdown",
                location=str(self.path),
            )
        )

    @property
    @override
    def search_prompt(self) -> str:
        return "Local text search (Enter)"

    @override
    def supports_sort(self, request: QueryRequest, column: str) -> bool:
        return is_issue_sort_column(column) and parse_search(request.query).sort is None

    @override
    def observe_context(self) -> SourceContext:
        """Read paths and contents once for both revision and complete Profiles."""
        if not self.path.is_relative_to(self.root) or not self.path.exists():
            raise ValueError(
                "Configured Local Issue path is unavailable or outside the Repository Anchor"
            )
        paths = (
            sorted(self.path.rglob("*.md"), key=lambda path: path.as_posix())
            if self.path.is_dir()
            else [self.path]
        )
        digest = hashlib.sha256()
        records: list[IssueProfile] = []
        for path in paths:
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("Local Issue path is outside the Repository Anchor")
            relative = path.relative_to(self.root).as_posix()
            content = path.read_bytes()
            for part in (relative.encode(), content):
                digest.update(len(part).to_bytes(8, "big"))
                digest.update(part)
            records.append(
                parse_local_markdown_issue(
                    content.decode("utf-8"),
                    project_id=self.config.project_id,
                    path=relative,
                )
            )
        if len({issue.id for issue in records}) != len(records) or len(
            {issue.number for issue in records}
        ) != len(records):
            raise ValueError("Local Issue collection repeats an identity or number")
        self.records = tuple(records)
        return self.context.model_copy(
            update={
                "revision": digest.hexdigest(),
                "configuration": load_project_config(self.root).model_dump_json(),
            }
        )

    @override
    def fetch_page(
        self,
        context: SourceContext,
        request: QueryRequest,
        token: Continuation | None,
        attempted: str,
    ) -> QueryPage:
        """Filter and order the local collection before selecting a page."""
        if context.configuration != self.config.model_dump_json():
            raise ValueError(
                "Project source configuration changed; reopen the dashboard"
            )
        if request.kind != "issues":
            raise ValueError("Pull Requests are not configured for a Markdown Project")
        project = ProjectObservation(
            project_id=context.project_id,
            repository_id=context.repository_id,
            display_label=self.config.display_label,
            workspaces=(),
            anchors=(str(self.root),),
            primary_anchor=str(self.root),
            status="fresh",
            elapsed_ms=0,
            snapshot=None,
            diagnostics=(),
        )
        parsed = parse_search(request.query)
        if parsed.diagnostics:
            raise ValueError("; ".join(parsed.diagnostics))
        terms = tuple(term.casefold() for term in parsed.terms)
        records = [
            issue
            for issue in self.records
            if (request.state == "all" or issue.state == request.state)
            and matches_issue_search(issue, project, frozenset(IssueSearchField), terms)
        ]
        ordering = (
            "last_action:desc"
            if request.ordering == "provider-default"
            else request.ordering
        )
        if parsed.sort:
            column = "created" if parsed.sort.field == "created" else "last_action"
            ordering = column + (":desc" if parsed.sort.descending else ":asc")
        if ordering != "provider-default":
            column, _, direction = ordering.rpartition(":")
            if not is_issue_sort_column(column) or direction not in {"asc", "desc"}:
                raise ValueError("Unsupported local column ordering")
            records = sort_issues(
                records, project, column, descending=direction == "desc"
            )
        offset = token.offset if token else 0
        if token and offset >= len(records):
            raise InvalidContinuation(
                "Local continuation is outside the query result; restart from page one"
            )
        page = records[offset : offset + request.page_size]
        end = offset + len(page)
        next_cursor = (
            encode_continuation(
                Continuation(
                    fingerprint=context_fingerprint(context, request), offset=end
                )
            )
            if end < len(records)
            else None
        )
        return QueryPage(
            context=context,
            request=request,
            effective_ordering="path-asc"
            if ordering == "provider-default"
            else ordering,
            status="fresh",
            attempted_at=attempted,
            last_good_at=attempted,
            issues=page,
            returned_count=len(page),
            matched_count=len(records),
            next_cursor=next_cursor,
            continuation="more" if next_cursor else "end",
            result_limit=None,
        )

    @override
    def fetch_totals(
        self, context: SourceContext, kind: ResourceKind, attempted: str
    ) -> ProjectTotals:
        """Count the complete local collection without query constraints."""
        if kind != "issues":
            raise ValueError("Pull Requests are not configured for a Markdown Project")
        opened = sum(issue.state == "open" for issue in self.records)
        return ProjectTotals(
            context=context,
            kind=kind,
            open_count=opened,
            closed_count=len(self.records) - opened,
            status="fresh",
            attempted_at=attempted,
            last_good_at=attempted,
        )

    @override
    def fetch_identities(
        self, context: SourceContext, identities: Sequence[str], attempted: str
    ) -> tuple[ResolvedIssue, ...]:
        """Resolve opaque identities independently of local page membership."""
        records = {issue.id: issue for issue in self.records}
        return tuple(
            ResolvedIssue(
                context=context,
                issue_id=identity,
                issue=records.get(identity),
                outcome="resolved" if identity in records else "not-resolved",
                status="fresh",
                attempted_at=attempted,
                last_good_at=attempted,
            )
            for identity in identities
        )

    @override
    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration:
        """Publish complete local exports with their existing last-good semantics."""
        if kind != "issues":
            return SourceEnumeration(
                context=self.context,
                kind=kind,
                status="unavailable",
                attempted_at=self.clock(),
                last_good_at=None,
                diagnostics=(
                    Diagnostic(
                        source="pull-requests",
                        severity="info",
                        code="pull-requests-not-configured",
                        message="Pull Requests are not configured for a Markdown Project",
                    ),
                ),
            )
        observation = self.export_source.refresh()
        return SourceEnumeration(
            context=self.context,
            kind=kind,
            issues=observation.issues,
            status=observation.status,
            attempted_at=observation.attempted_at,
            last_good_at=observation.last_good_at,
            diagnostics=tuple(
                Diagnostic(
                    source=d.source, severity=d.severity, code=d.code, message=d.message
                )
                for d in observation.diagnostics
            ),
        )
