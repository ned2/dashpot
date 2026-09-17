"""Keep source query failures and bounded last-good observations behind one seam."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path

from ..core.model import Diagnostic
from ..observation_errors import QUERY_OBSERVATION_FAILURES
from ..timestamps import utc_now
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
    decode_continuation,
    verify_continuation,
)


class CachedQuerySource(ABC):
    result_limit: int | None = None

    def __init__(
        self, context: SourceContext, *, clock: Callable[[], str] = utc_now
    ) -> None:
        self.context = context
        self.clock = clock
        self._pages: OrderedDict[tuple[str, str | None], QueryPage] = OrderedDict()
        self._totals: dict[ResourceKind, ProjectTotals] = {}
        self._identities: OrderedDict[str, ResolvedIssue] = OrderedDict()

    def query_page(self, request: QueryRequest) -> QueryPage:
        """Accept one complete page or retain only its verified last-good request."""
        token = decode_continuation(request.cursor) if request.cursor else None
        attempted = self.clock()
        key: tuple[str, str | None] | None = None
        context: SourceContext | None = None
        try:
            context = self.observe_context()
            verify_continuation(token, context, request)
            key = (context_fingerprint(context, request), request.cursor)
            page = self.fetch_page(context, request, token, attempted)
        except InvalidContinuation:
            raise
        except QUERY_OBSERVATION_FAILURES as exc:
            previous = self._pages.get(key) if key else None
            diagnostic = self.diagnostic(exc)
            if previous is not None:
                return previous.model_copy(
                    update={
                        "status": "stale",
                        "attempted_at": attempted,
                        "diagnostics": (diagnostic,),
                    }
                )
            return QueryPage(
                context=context or self.context,
                request=request,
                effective_ordering=request.ordering,
                status="unavailable",
                attempted_at=attempted,
                last_good_at=None,
                diagnostics=(diagnostic,),
                returned_count=0,
                matched_count=None,
                next_cursor=None,
                continuation="unavailable",
                result_limit=self.result_limit,
            )
        self._pages[key] = page
        self._pages.move_to_end(key)
        while len(self._pages) > 16:
            self._pages.popitem(last=False)
        return page

    def totals(self, kind: ResourceKind) -> ProjectTotals:
        """Observe Project-wide counts independently of all query requests."""
        attempted = self.clock()
        context: SourceContext | None = None
        try:
            context = self.observe_context()
            opened, closed = self.fetch_totals(kind)
            result = ProjectTotals(
                context=context,
                kind=kind,
                open_count=opened,
                closed_count=closed,
                status="fresh",
                attempted_at=attempted,
                last_good_at=attempted,
            )
        except QUERY_OBSERVATION_FAILURES as exc:
            previous = self._totals.get(kind)
            diagnostic = self.diagnostic(exc)
            if previous and previous.context == context:
                return previous.model_copy(
                    update={
                        "status": "stale",
                        "attempted_at": attempted,
                        "diagnostics": (diagnostic,),
                    }
                )
            return ProjectTotals(
                context=self.context,
                kind=kind,
                open_count=None,
                closed_count=None,
                status="unavailable",
                attempted_at=attempted,
                last_good_at=None,
                diagnostics=(diagnostic,),
            )
        self._totals[kind] = result
        return result

    def resolve_identities(
        self, identities: Sequence[str]
    ) -> tuple[ResolvedIssue, ...]:
        """Deduplicate requested identities and preserve attributable sibling outcomes."""
        requested = tuple(dict.fromkeys(identities))
        if not requested:
            return ()
        attempted = self.clock()
        context: SourceContext | None = None
        try:
            context = self.observe_context()
            results = self.fetch_identities(context, requested, attempted)
        except QUERY_OBSERVATION_FAILURES as exc:
            results = tuple(
                ResolvedIssue(
                    context=self.context,
                    issue_id=identity,
                    outcome="unavailable",
                    status="unavailable",
                    attempted_at=attempted,
                    last_good_at=None,
                    diagnostics=(self.diagnostic(exc),),
                )
                for identity in requested
            )
        retained: list[ResolvedIssue] = []
        for result in results:
            previous = self._identities.get(result.issue_id)
            if (
                result.status == "unavailable"
                and previous
                and previous.context == context
            ):
                result = previous.model_copy(
                    update={
                        "status": "stale",
                        "outcome": "unavailable",
                        "attempted_at": attempted,
                        "diagnostics": result.diagnostics,
                    }
                )
            if result.status == "fresh":
                self._identities[result.issue_id] = result
                self._identities.move_to_end(result.issue_id)
            retained.append(result)
        while len(self._identities) > 256:
            self._identities.popitem(last=False)
        return tuple(retained)

    def diagnostic(self, exc: Exception) -> Diagnostic:
        """Report an adapter failure without manufacturing empty success."""
        return Diagnostic(
            source=self.context.source,
            severity="warning",
            code=getattr(exc, "code", "source-query-unavailable"),
            message=str(exc),
        )

    @property
    @abstractmethod
    def search_prompt(self) -> str: ...

    @abstractmethod
    def supports_sort(self, request: QueryRequest, column: str) -> bool: ...

    @abstractmethod
    def observe_context(self) -> SourceContext: ...

    @abstractmethod
    def fetch_page(
        self,
        context: SourceContext,
        request: QueryRequest,
        token: Continuation | None,
        attempted: str,
    ) -> QueryPage: ...

    @abstractmethod
    def fetch_totals(self, kind: ResourceKind) -> tuple[int, int]: ...

    @abstractmethod
    def fetch_identities(
        self, context: SourceContext, identities: Sequence[str], attempted: str
    ) -> tuple[ResolvedIssue, ...]: ...

    @abstractmethod
    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration: ...


def configured_query_source(root: Path, *, timeout: float = 10) -> CachedQuerySource:
    """Build the configured source for both dashboard and CLI query consumers."""
    from ..project.project_config import (
        GitHubIssueSourceConfig,
        load_project_config,
    )
    from .github_queries import GitHubQuerySource
    from .markdown_queries import MarkdownQuerySource

    config = load_project_config(root)
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        return GitHubQuerySource(root, config, timeout=timeout)
    return MarkdownQuerySource(root, config)
