"""The messages the dashboard posts to itself: off-loop outcomes and a layout.

Each is a dataclass whose fields are its payload: Textual's ``Message``
initialises its own state (sender, time, propagation) in ``__post_init__``,
which the generated ``__init__`` calls, so no message hand-writes one.
They are neither frozen nor slotted, unlike the internal values, because
``Message`` mutates that state and keeps its own ``__slots__``; ``eq=False``
keeps a message's identity as its equality. Each off-loop outcome ends
with its value and then ``error``, one of them set, in that order, which
is what an ``OffLoopHost`` builds it from.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from textual.geometry import Size
from textual.message import Message

from .cleanup import (
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
)
from .collect import ObservationOutcome, ObservationTicket
from .fetch import FetchReport
from .queries.page_navigation import PageTicket
from .queries.source_queries import (
    ProjectTotals,
    QueryPage,
    ResolvedIssue,
    ResourceKind,
)

T = TypeVar("T")

# What asked for an observation: the first load, a person's key press, an
# automatic tick, or a Remote Fetch or Cleanup that changed the Repository.
ObservationTrigger = Literal["initial", "manual", "timer", "fetch", "cleanup"]


class OffLoopHost(Protocol):
    """What runs one operation off the event loop and posts its outcome.

    ``on_done`` makes the message from the value, or from the failure's
    text: the one error boundary for off-loop work, where a failure is a
    message and never an exit.
    """

    def run_off_loop(
        self,
        name: str,
        group: str,
        operation: Callable[[], T],
        on_done: Callable[[T | None, str | None], Message],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None: ...


@dataclass(eq=False)
class PageFinished(Message):
    """One Query Page was observed for its ticket, or the query failed."""

    kind: ResourceKind
    ticket: PageTicket
    page: QueryPage | None = None
    error: str | None = None


@dataclass(eq=False)
class TotalsFinished(Message):
    """One kind's Project Totals were observed, or the query failed."""

    kind: ResourceKind
    totals: ProjectTotals | None = None
    error: str | None = None


@dataclass(eq=False)
class IdentitiesFinished(Message):
    """The requested Issue Identities were resolved, or the query failed."""

    outcomes: tuple[ResolvedIssue, ...] | None = None
    error: str | None = None


@dataclass(eq=False)
class ObservationFinished(Message):
    """One keyed observation ran; the outcome says whether it was accepted."""

    ticket: ObservationTicket
    trigger: ObservationTrigger
    outcome: ObservationOutcome | None = None
    error: str | None = None


@dataclass(eq=False)
class CleanupInspected(Message):
    """One Cleanup's preview was taken off the event loop, or failed."""

    project_id: str
    request: CleanupRequest
    preview: CleanupPreview | None = None
    error: str | None = None


@dataclass(eq=False)
class CleanupFinished(Message):
    """One confirmed Cleanup was performed, or the adapter failed."""

    project_id: str
    confirmation: CleanupConfirmation
    report: CleanupReport | None = None
    error: str | None = None


@dataclass(eq=False)
class FetchFinished(Message):
    """One Project's explicit remote fetch ran; ``error`` is a fetcher failure."""

    project_id: str
    report: FetchReport | None = None
    error: str | None = None


@dataclass(eq=False)
class BodyResized(Message):
    """The dashboard body was laid out at a new size."""

    size: Size
