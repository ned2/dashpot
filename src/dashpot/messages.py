"""The messages the dashboard posts to itself: off-loop outcomes and a layout.

Each is a dataclass whose fields are its payload: Textual's ``Message``
initialises its own state (sender, time, propagation) in ``__post_init__``,
which the generated ``__init__`` calls, so no message hand-writes one.
They are neither frozen nor slotted, unlike the internal values, because
``Message`` mutates that state and keeps its own ``__slots__``; ``eq=False``
keeps a message's identity as its equality. Each off-loop outcome ends
with its value and then ``error``, one of them set, in that order, which
is what ``DashpotApp.run_off_loop`` builds it from.
"""

from __future__ import annotations

from dataclasses import dataclass

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
from .page_navigation import PageTicket


@dataclass(eq=False)
class QueryFinished(Message):
    """One keyed source query answered, or failed; a page carries its ticket."""

    key: str
    ticket: PageTicket | None
    value: object = None
    error: str | None = None


@dataclass(eq=False)
class ObservationFinished(Message):
    """One keyed observation ran; the outcome says whether it was accepted."""

    ticket: ObservationTicket
    trigger: str
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
