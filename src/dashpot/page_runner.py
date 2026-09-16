"""Run the source queries behind the pages, totals and identities.

Each query key — a kind's page, a kind's totals, the identities — runs on
its own executor thread against its own Query Source, one query at a time:
a request for a key whose query is running waits its turn, and only the
latest such request runs when the key is free. The runner owns each paged
kind's navigation and publishes its accepted page to the store, so every
store write goes through a method that advances the store's revision.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, TypeVar

from .messages import (
    IdentitiesFinished,
    OffLoopHost,
    PageFinished,
    TotalsFinished,
)
from .paged_store import PagedObservationStore
from .queries.page_navigation import PageNavigation, PageTicket
from .queries.source_queries import QueryRequest, QuerySource, ResourceKind

if TYPE_CHECKING:
    from textual.message import Message

PAGED_KINDS: tuple[ResourceKind, ...] = ("issues", "pull-requests")


def totals_key(kind: ResourceKind) -> str:
    """Name the query key of a kind's Project Totals."""
    return f"totals:{kind}"


# The Query Sources the shipped app consults, one per concurrent consumer:
# each key runs on its own executor thread against its own source instance.
QUERY_SOURCE_KEYS: tuple[str, ...] = (
    *PAGED_KINDS,
    *(totals_key(kind) for kind in PAGED_KINDS),
    "identities",
)

T = TypeVar("T")


class PageRunner:
    """Run one source query per key at a time and keep each kind's navigation."""

    def __init__(
        self,
        sources: Mapping[str, QuerySource],
        store: PagedObservationStore,
        host: OffLoopHost,
    ) -> None:
        self.sources = dict(sources)
        self.store = store
        self.host = host
        self.navigation: dict[ResourceKind, PageNavigation] = {
            kind: PageNavigation(QueryRequest(kind=kind)) for kind in PAGED_KINDS
        }
        self.executor = ThreadPoolExecutor(
            max_workers=len(QUERY_SOURCE_KEYS), thread_name_prefix="dashpot-query"
        )
        self.busy: set[str] = set()
        # Only the latest request for a busy key is worth running once the
        # key is free; an earlier one would answer a superseded ticket.
        self.queued: dict[str, Callable[[], None]] = {}

    def shutdown(self) -> None:
        """Release the pool without waiting for queries still running."""
        self.executor.shutdown(wait=False, cancel_futures=True)

    def refresh(self, *, restart: bool) -> None:
        """Re-query every page and every total.

        A restart begins each navigation at page one; otherwise the displayed
        page is repeated unless its query is still running.
        """
        for kind in PAGED_KINDS:
            navigation = self.navigation[kind]
            if restart:
                self.request_page(kind, navigation.restart())
            elif kind not in self.busy:
                self.request_page(kind, navigation.refresh())
            if totals_key(kind) not in self.busy:
                self.request_totals(kind)

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

    def request_page(self, kind: ResourceKind, ticket: PageTicket) -> None:
        """Query the page a ticket names."""
        self._launch(
            kind,
            lambda: self.sources[kind].query_page(ticket.request),
            partial(PageFinished, kind, ticket),
        )

    def request_totals(self, kind: ResourceKind) -> None:
        """Query a kind's Project Totals."""
        key = totals_key(kind)
        self._launch(
            key, lambda: self.sources[key].totals(kind), partial(TotalsFinished, kind)
        )

    def request_identities(self, identities: tuple[str, ...]) -> None:
        """Resolve the named Issue Identities."""
        self._launch(
            "identities",
            lambda: self.sources["identities"].resolve_identities(identities),
            IdentitiesFinished,
        )

    def _launch(
        self,
        key: str,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
    ) -> None:
        """Run one query per key at a time; the latest request waits its turn."""
        if key in self.busy:
            self.queued[key] = partial(self._launch, key, operation, on_done)
            return
        self.busy.add(key)
        self.host.run_off_loop(
            f"query {key}", f"query:{key}", operation, on_done, executor=self.executor
        )

    def _release(self, key: str) -> None:
        """Free a key whose query answered, then run the request that waited."""
        self.busy.discard(key)
        queued = self.queued.pop(key, None)
        if queued is not None:
            queued()

    def finish_page(self, message: PageFinished) -> None:
        """Land a page on its navigation, which rejects a superseded ticket."""
        self.navigation[message.kind].accept(
            message.ticket, message.page, message.error
        )
        self._release(message.kind)

    def finish_totals(self, message: TotalsFinished) -> None:
        """Land a kind's totals in the store."""
        if message.totals is not None:
            self.store.accept_totals(message.totals)
        self._release(totals_key(message.kind))

    def finish_identities(self, message: IdentitiesFinished) -> None:
        """Land the resolved identities in the store."""
        if message.outcomes is not None:
            self.store.accept_identities(message.outcomes)
        self._release("identities")

    def publish(self) -> None:
        """Show each navigation's page in the store, in flight while its query runs."""
        for kind, navigation in self.navigation.items():
            self.store.accept_page(kind, navigation.shown, in_flight=kind in self.busy)
