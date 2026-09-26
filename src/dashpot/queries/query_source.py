"""Keep source query failures and bounded last-good observations behind one seam."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path

from ..core.model import Diagnostic
from ..core.observation_errors import QUERY_OBSERVATION_FAILURES
from ..core.timestamps import utc_now
from .source_queries import (
    Continuation,
    InvalidContinuation,
    PageObservation,
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

    def query_page(self, request: QueryRequest) -> PageObservation:
        """Accept one complete page or retain only its verified last-good request.

        The same request counts the kind's Project Totals, which land even
        when the page itself fails after the source counted them.
        """
        token = decode_continuation(request.cursor) if request.cursor else None
        attempted = self.clock()
        key: tuple[str, str | None] | None = None
        sent: SourceContext | None = None
        context: SourceContext | None = None
        counted: list[ProjectTotals] = []
        try:
            sent = self.request_context()
            # Only a continuation must know its context before it is sent;
            # every other request is verified in the response it gets back.
            context = self.observe_continuation(sent) if token else sent
            verify_continuation(token, context, request)
            page = self.fetch_page(context, request, token, attempted, counted.append)
        except InvalidContinuation:
            raise
        except QUERY_OBSERVATION_FAILURES as exc:
            known = self._failed_context(context or sent)
            if known is not None:
                key = (context_fingerprint(known, request), request.cursor)
            previous = self._pages.get(key) if key else None
            diagnostic = self.diagnostic(exc)
            totals = (
                self._accept_totals(counted[-1])
                if counted
                else self._failed_totals(request.kind, known, attempted, diagnostic)
            )
            if previous is not None:
                return PageObservation(
                    previous.model_copy(
                        update={
                            "status": "stale",
                            "attempted_at": attempted,
                            "diagnostics": (diagnostic,),
                        }
                    ),
                    totals,
                )
            return PageObservation(
                QueryPage(
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
                ),
                totals,
            )
        if not counted:
            raise AssertionError("A source must count Project Totals with its page")
        key = (context_fingerprint(page.context, request), request.cursor)
        self._pages[key] = page
        self._pages.move_to_end(key)
        while len(self._pages) > 16:
            self._pages.popitem(last=False)
        return PageObservation(page, self._accept_totals(counted[-1]))

    def _accept_totals(self, totals: ProjectTotals) -> ProjectTotals:
        """Retain counted Project Totals as their kind's last good observation."""
        self._totals[totals.kind] = totals
        return totals

    def _failed_totals(
        self,
        kind: ResourceKind,
        known: SourceContext | None,
        attempted: str,
        diagnostic: Diagnostic,
    ) -> ProjectTotals:
        """The Project Totals of a request that failed before counting them.

        ``known`` is the context the failure finds last good observations
        under; totals counted under another are never shown as stale.
        """
        previous = self._totals.get(kind)
        if previous and previous.context == known:
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
            context = self.request_context()
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
        known = self._failed_context(context)
        retained: list[ResolvedIssue] = []
        for result in results:
            previous = self._identities.get(result.issue_id)
            if (
                result.status == "unavailable"
                and previous
                and previous.context == known
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

    def _failed_context(self, context: SourceContext | None) -> SourceContext | None:
        """The context a failed request finds its last good observation under.

        A response can report a new principal before a later part of the same
        request fails, so the context a response last reported wins over the
        one the request was sent under; the request's configuration still
        applies. Another principal's observation is then never shown as stale.
        """
        known = self.last_known_context()
        if known is None or context is None:
            return known or context
        return known.model_copy(update={"configuration": context.configuration})

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
    def request_context(self) -> SourceContext:
        """Begin one request, returning the context it is sent under.

        A source whose responses carry their own context starts from what it
        last observed and verifies each response; a local source observes it.
        """

    def observe_continuation(self, context: SourceContext) -> SourceContext:
        """Observe the context a continuation is bound to before it is sent.

        The default is ``context`` itself, for a source whose request context
        is already an observation.
        """
        return context

    def last_known_context(self) -> SourceContext | None:
        """The context a response most recently answered for, when one has.

        A failure proves nothing about the context (ADR 0033), so a failed
        request finds its last good observation under this context.
        """
        return None

    @abstractmethod
    def fetch_page(
        self,
        context: SourceContext,
        request: QueryRequest,
        token: Continuation | None,
        attempted: str,
        count_totals: Callable[[ProjectTotals], None],
    ) -> QueryPage:
        """Complete one page, reporting the kind's Project Totals to ``count_totals``.

        The totals are reported as soon as they are counted, before any later
        part of the page can fail, and always before a page is returned.
        """

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
