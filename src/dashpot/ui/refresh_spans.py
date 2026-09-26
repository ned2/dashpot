"""Time each dashboard refresh, and every key it asks for, as spans.

A refresh starts when the first load, ``r``, a Refresh Period's timer, or a
Remote Fetch or Cleanup fires it, and ends when the last key it asked for
has landed. The work is asynchronous: a runner schedules a key now and lands
it from a later message, and a key that is busy waits, or is skipped. So a
key's span is started when its refresh asks for it and travels with the
work — the ticket in flight, the queued request, the pending rerun — naming
that refresh as its parent whichever message releases it. The commands and
GitHub requests the key runs nest under its span on the executor thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from ..core.event_log import EventLog, Span, use_span
from ..core.runtime_events import (
    KeyOutcome,
    ObservationAttributes,
    QueryAttributes,
    RefreshAttributes,
    RefreshTrigger,
)
from .messages import ObservationTrigger

KeySpanName = Literal["observation", "query"]


def refresh_trigger(trigger: ObservationTrigger) -> RefreshTrigger:
    """Name what fired a refresh: an observation's ``timer`` is the local period's."""
    return "local" if trigger == "timer" else trigger


class Refresh:
    """One refresh's span, held open until the last key it asked for ends.

    Its owner asks for keys through it and then seals it; a key asked for
    later — a rerun, or a follow-up of a key that landed — keeps it open
    too, since it is asked for before the key that caused it ends.
    """

    def __init__(self, log: EventLog, trigger: RefreshTrigger) -> None:
        self.log = log
        self.span = log.start_span(
            "refresh", attributes=RefreshAttributes(trigger=trigger), parent=None
        )
        self._open = 0
        self._sealed = False

    @property
    def ended(self) -> bool:
        """Whether every key the refresh asked for has ended, and so has it."""
        return self._sealed and self._open == 0

    def key(
        self, name: KeySpanName, attributes: ObservationAttributes | QueryAttributes
    ) -> KeySpan:
        """Start the span of one key this refresh asks for."""
        self._open += 1
        return KeySpan(self.log, name, attributes, refresh=self)

    def seal(self) -> None:
        """Say the owner has asked for every key; the refresh ends once they have."""
        self._sealed = True
        self._settle()

    def key_ended(self) -> None:
        """Count one of the refresh's keys as ended."""
        self._open -= 1
        self._settle()

    def _settle(self) -> None:
        if self.ended:
            self.span.end()


class KeySpan:
    """One key's span: started when asked for, ended with what became of it.

    ``refresh`` is ``None`` for a key no refresh asked for — a page a person
    moved to, the Issues a selection resolves — whose span is a root.
    """

    def __init__(
        self,
        log: EventLog,
        name: KeySpanName,
        attributes: ObservationAttributes | QueryAttributes,
        *,
        refresh: Refresh | None = None,
    ) -> None:
        self.refresh = refresh
        self.attributes = attributes
        self.span: Span = log.start_span(
            name,
            attributes=attributes,
            parent=None if refresh is None else refresh.span,
        )

    def carrying[T](self, operation: Callable[[], T]) -> Callable[[], T]:
        """Run ``operation`` inside this key's span, failing it if the work raises."""
        span = self.span

        def run() -> T:
            with use_span(span):
                try:
                    return operation()
                except Exception as exc:
                    span.fail(exc)
                    raise

        return run

    def end(self, outcome: KeyOutcome) -> None:
        """Record what became of the key, and count it ended for its refresh."""
        if self.span.ended:
            return
        self.span.set_attributes(
            self.attributes.model_copy(update={"outcome": outcome})
        )
        self.span.end()
        if self.refresh is not None:
            self.refresh.key_ended()
