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
from .page_navigation import PageNavigation, PageTicket
from .paged_store import PagedObservationStore
from .source_queries import QueryRequest, QuerySource, ResourceKind

if TYPE_CHECKING:
    from textual.message import Message

# The Query Sources the shipped app consults, one per concurrent consumer:
# each key runs on its own executor thread against its own source instance.
QUERY_SOURCE_KEYS: tuple[str, ...] = (
    "issues",
    "pull-requests",
    "totals:issues",
    "totals:pull-requests",
    "identities",
)
PAGED_KINDS: tuple[ResourceKind, ...] = ("issues", "pull-requests")

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
        # The latest request for each busy key, launched once the key is free.
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
            if f"totals:{kind}" not in self.busy:
                self.request_totals(kind)

    def submit(self, kind: ResourceKind, **updates: str) -> None:
        """Submit a new query context and invalidate prior navigation history."""
        navigation = self.navigation[kind]
        self.request_page(
            kind, navigation.restart(navigation.request.model_copy(update=updates))
        )

    def request_page(self, kind: ResourceKind, ticket: PageTicket) -> None:
        """Query the page a ticket names and publish the navigation's state."""
        self.launch(
            kind,
            lambda: self.sources[kind].query_page(ticket.request),
            partial(PageFinished, kind, ticket),
        )
        self.publish()

    def request_totals(self, kind: ResourceKind) -> None:
        """Query a kind's Project Totals."""
        key = f"totals:{kind}"
        self.launch(
            key, lambda: self.sources[key].totals(kind), partial(TotalsFinished, kind)
        )

    def request_identities(self, identities: tuple[str, ...]) -> None:
        """Resolve the named Issue Identities."""
        self.launch(
            "identities",
            lambda: self.sources["identities"].resolve_identities(identities),
            IdentitiesFinished,
        )

    def launch(
        self,
        key: str,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
    ) -> None:
        """Run one query per key at a time; the latest request waits its turn."""
        if key in self.busy:
            self.queued[key] = partial(self.launch, key, operation, on_done)
            return
        self.busy.add(key)
        self.host.run_off_loop(
            f"query {key}", f"query:{key}", operation, on_done, executor=self.executor
        )

    def finish(self, key: str) -> None:
        """Free a key whose query answered, then run the request that waited."""
        self.busy.discard(key)
        queued = self.queued.pop(key, None)
        if queued is not None:
            queued()

    def accept_page(self, message: PageFinished) -> None:
        """Land a page on its navigation, which rejects a superseded ticket."""
        self.navigation[message.kind].accept(
            message.ticket, message.page, message.error
        )
        self.finish(message.kind)

    def accept_totals(self, message: TotalsFinished) -> None:
        """Land a kind's totals in the store."""
        if message.totals is not None:
            self.store.accept_totals(message.totals)
        self.finish(f"totals:{message.kind}")

    def accept_identities(self, message: IdentitiesFinished) -> None:
        """Land the resolved identities in the store."""
        if message.outcomes is not None:
            self.store.accept_identities(message.outcomes)
        self.finish("identities")

    def publish(self) -> None:
        """Show each navigation's page in the store."""
        for kind, navigation in self.navigation.items():
            self.store.accept_page(kind, navigation.page)
