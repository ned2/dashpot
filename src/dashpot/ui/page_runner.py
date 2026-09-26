"""Run the source queries behind the pages and identities.

Each query key — a kind's page, which counts its Project Totals too, and the
identities — runs on its own executor thread against its own Query Source,
one query at a time: a request for a key whose query is running waits its
turn, and only the latest such request runs when the key is free. The runner owns each paged
kind's navigation and publishes its accepted page to the store, so every
store write goes through a method that advances the store's revision.

Each query is timed as a key span, under the refresh that asked for it or,
for a page a person moved to and the Issues a selection resolves, as a root.
A queued request keeps its own span while it waits: replaced by a newer one,
it is dropped, and a tick that finds its key busy is skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING

from ..core.commands import RunningCommands, start_pool
from ..core.event_log import EventLog, unrecorded_event_log
from ..core.runtime_events import KeyOutcome, QueryAttributes
from ..observation.paged_store import PagedObservationStore
from ..queries.page_navigation import PageNavigation, PageQueryState, PageTicket
from ..queries.source_queries import (
    PAGED_KINDS,
    QUERY_SOURCE_KEYS,
    QueryRequest,
    QuerySource,
    ResourceKind,
)
from .messages import (
    IdentitiesFinished,
    OffLoopHost,
    PageFinished,
)
from .refresh_spans import KeySpan, Refresh

if TYPE_CHECKING:
    from textual.message import Message


class PageRunner:
    """Run one source query per key at a time and keep each kind's navigation."""

    def __init__(
        self,
        sources: Mapping[str, QuerySource],
        store: PagedObservationStore,
        host: OffLoopHost,
        *,
        running: RunningCommands | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        self.sources = dict(sources)
        self.store = store
        self.host = host
        # Where the queries are timed.
        self.event_log = event_log or unrecorded_event_log()
        self.navigation: dict[ResourceKind, PageNavigation] = {
            kind: PageNavigation(QueryRequest(kind=kind)) for kind in PAGED_KINDS
        }
        self.executor = start_pool(
            running,
            max_workers=len(QUERY_SOURCE_KEYS),
            thread_name_prefix="dashpot-query",
        )
        self.busy: set[str] = set()
        self._page_failures: set[ResourceKind] = set()
        # Only the latest request for a busy key is worth running once the
        # key is free; an earlier one would answer a superseded ticket.
        self.queued: dict[str, Callable[[], None]] = {}
        # The span of each key's running query, and of its queued request.
        self._running_spans: dict[str, KeySpan] = {}
        self._queued_spans: dict[str, KeySpan] = {}

    def shutdown(self) -> None:
        """Release the pool without waiting for queries still running."""
        self.executor.shutdown(wait=False, cancel_futures=True)

    @property
    def page_states(self) -> dict[ResourceKind, PageQueryState]:
        """The accepted and transient state of every Query Page kind."""
        return {
            kind: PageQueryState(
                self.navigation[kind].shown,
                in_flight=kind in self.busy,
                failed_without_page=kind in self._page_failures,
            )
            for kind in PAGED_KINDS
        }

    def refresh(self, *, restart: bool, refresh: Refresh | None = None) -> None:
        """Re-query every page, and with it every kind's Project Totals.

        A restart begins each navigation at page one; otherwise the displayed
        page is repeated unless its query is still running, and that query
        brings the totals.
        """
        for kind in PAGED_KINDS:
            navigation = self.navigation[kind]
            if restart:
                self.request_page(kind, navigation.restart(), refresh=refresh)
            elif kind not in self.busy:
                self.request_page(kind, navigation.refresh(), refresh=refresh)
            else:
                self._key_span(kind, refresh).end("skipped")

    def submit(self, kind: ResourceKind, **updates: str) -> None:
        """Submit a new query context and invalidate prior navigation history."""
        navigation = self.navigation[kind]
        self.request_page(
            kind, navigation.restart(navigation.request.model_copy(update=updates))
        )

    def next_page(self, kind: ResourceKind) -> None:
        """Move a kind's navigation on, querying the page when none is retained."""
        ticket = self.navigation[kind].next()
        if ticket:
            self.request_page(kind, ticket)

    def previous_page(self, kind: ResourceKind) -> None:
        """Move a kind's navigation back to the page it retained."""
        self.navigation[kind].previous()

    def restart_page(self, kind: ResourceKind) -> None:
        """Begin a kind's navigation again at page one."""
        self.request_page(kind, self.navigation[kind].restart())

    def supports_sort(self, kind: ResourceKind, column: str) -> bool:
        """Report whether a kind's source can order its submitted request by a column."""
        return self.sources[kind].supports_sort(self.navigation[kind].request, column)

    def request_page(
        self,
        kind: ResourceKind,
        ticket: PageTicket,
        *,
        refresh: Refresh | None = None,
    ) -> None:
        """Query the page a ticket names, counting the kind's Project Totals."""
        self._launch(
            kind,
            lambda: self.sources[kind].query_page(ticket.request),
            partial(PageFinished, kind, ticket),
            self._key_span(kind, refresh),
        )

    def request_identities(
        self, identities: tuple[str, ...], *, refresh: Refresh | None = None
    ) -> None:
        """Resolve the named Issue Identities."""
        self._launch(
            "identities",
            lambda: self.sources["identities"].resolve_identities(identities),
            IdentitiesFinished,
            self._key_span("identities", refresh),
        )

    def _key_span(self, key: str, refresh: Refresh | None) -> KeySpan:
        """Start one query's span, under ``refresh`` or as a root without one."""
        attributes = QueryAttributes(key=key)
        if refresh is None:
            return KeySpan(self.event_log, "query", attributes)
        return refresh.key("query", attributes)

    def _launch[T](
        self,
        key: str,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
        span: KeySpan,
    ) -> None:
        """Run one query per key at a time; the latest request waits its turn."""
        if key in self.busy:
            replaced = self._queued_spans.pop(key, None)
            self._queued_spans[key] = span
            self.queued[key] = partial(self._launch, key, operation, on_done, span)
            if replaced is not None:
                replaced.end("dropped")
            return
        self.busy.add(key)
        self._running_spans[key] = span
        self.host.run_off_loop(
            f"query {key}",
            f"query:{key}",
            span.carrying(operation),
            on_done,
            executor=self.executor,
        )

    def _release(self, key: str, outcome: KeyOutcome = "landed") -> None:
        """Free a key whose query answered, then run the request that waited."""
        self.busy.discard(key)
        running = self._running_spans.pop(key, None)
        queued = self.queued.pop(key, None)
        self._queued_spans.pop(key, None)
        if queued is not None:
            queued()
        if running is not None:
            running.end(outcome)

    def finish_page(self, message: PageFinished) -> None:
        """Land a page on its navigation, and its Project Totals in the store.

        The navigation rejects a superseded ticket's page, but not its totals:
        they count the whole Project whatever the page asked, and a kind's
        queries answer in the order they were sent.
        """
        observation = message.observation
        page = observation.page if observation is not None else None
        accepted = self.navigation[message.kind].accept(
            message.ticket, page, message.error
        )
        if accepted:
            if page is None:
                self._page_failures.add(message.kind)
            else:
                self._page_failures.discard(message.kind)
        if observation is not None:
            self.store.accept_totals(observation.totals)
        self._accept_source_diagnostics()
        self._release(message.kind, "landed" if accepted else "superseded")

    def finish_identities(self, message: IdentitiesFinished) -> None:
        """Land the resolved identities in the store."""
        if message.outcomes is not None:
            self.store.accept_identities(message.outcomes)
        self._accept_source_diagnostics()
        self._release("identities")

    def _accept_source_diagnostics(self) -> None:
        """Land what the sources now report about themselves, each line once.

        Sources that share one rate limit reading report the same warning,
        which is one line however many of them report it. A query that failed
        may still have read one, so every answer lands them.
        """
        self.store.accept_source_diagnostics(
            tuple(
                dict.fromkeys(
                    diagnostic
                    for source in self.sources.values()
                    for diagnostic in source.source_diagnostics()
                )
            )
        )

    def publish(self) -> None:
        """Show each navigation's page in the store, in flight while its query runs."""
        for kind, navigation in self.navigation.items():
            self.store.accept_page(kind, navigation.shown, in_flight=kind in self.busy)
