"""Run the keyed observations behind the dashboard, one per key at a time.

The runner is the dashboard's scheduling rule of ADR 0020: a key is
observed at most once at a time, a request for a key in flight coalesces
onto it, and every trigger but a timer tick queues one rerun for when the
running observation lands. It drives the app through the narrow
``ObservationHost`` — start off-loop work, start a timer, redraw the alert —
so the coalescing runs, and is tested, without a running app.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from ..observation.collect import ObservationScheduler
from ..observation.keys import ObservationKey, ObservationTicket
from ..observation.observation_store import StoreChange, WorkspaceObservationStore
from .messages import ObservationFinished, ObservationTrigger, OffLoopHost

# Observation triggers a person asked for, whose outcome earns a toast.
MANUAL_TRIGGERS: frozenset[ObservationTrigger] = frozenset({"manual", "fetch"})
# Triggers that coalesce onto an observation already in flight without
# queueing a rerun: the next tick is the rerun. Every other trigger (a key
# press, a Remote Fetch or Cleanup that changed the Repository, a follow-up
# of a publish) still observes once more after the running one lands.
COALESCED_TRIGGERS: frozenset[ObservationTrigger] = frozenset({"timer"})


def refresh_pool_size(key_count: int) -> int:
    """Size the refresh pool to the keys, between two and eight threads."""
    return max(2, min(8, key_count))


class TimerHandle(Protocol):
    """A started timer the runner can stop before it fires."""

    def stop(self) -> None: ...


class ObservationHost(OffLoopHost, Protocol):
    """What the runner asks of the app beyond running work off the loop."""

    def set_timer(
        self, delay: float, callback: Callable[[], None], *, name: str | None = None
    ) -> TimerHandle: ...

    def update_alert(self) -> None: ...


@dataclass(frozen=True, slots=True)
class DroppedObservation:
    """A superseded failure or a superseded result, which changes nothing."""

    trigger: ObservationTrigger


@dataclass(frozen=True, slots=True)
class FailedObservation:
    """A failure recorded for its key; ``changed`` says it is new or different."""

    trigger: ObservationTrigger
    error: str
    changed: bool

    @property
    def announced(self) -> bool:
        """Whether the failure earns a toast: a person asked, and it is news."""
        return self.trigger in MANUAL_TRIGGERS and self.changed


@dataclass(frozen=True, slots=True)
class PublishedObservation:
    """An accepted observation moved into the store, and what that altered."""

    trigger: ObservationTrigger
    recovered: bool
    changes: tuple[StoreChange, ...]

    @property
    def announced(self) -> bool:
        """Whether the recovery earns a toast: a person asked, and the key had failed."""
        return self.trigger in MANUAL_TRIGGERS and self.recovered


# What landing one observation changed, for the dashboard to show.
Acceptance = DroppedObservation | FailedObservation | PublishedObservation


class ObservationRunner:
    """Coordinate the observations in flight, their reruns, and their indicator."""

    def __init__(
        self,
        scheduler: ObservationScheduler,
        store: WorkspaceObservationStore,
        host: ObservationHost,
        *,
        indicator_seconds: float = 0.75,
    ) -> None:
        self.scheduler = scheduler
        self.store = store
        self.host = host
        self.in_flight: dict[ObservationKey, int] = {}
        # A key requested while its observation is in flight is observed once
        # more when that observation lands, under the latest trigger.
        self.pending_rerun: dict[ObservationKey, ObservationTrigger] = {}
        # The last failure per key, until an observation of it is accepted.
        self.errors: dict[ObservationKey, str] = {}
        # Told of every landed observation once it is presented, so a flow
        # waiting on a Project's Git keys hears them land without the app
        # relaying each one.
        self.landings: list[Callable[[ObservationFinished], None]] = []
        # Quick background observations should not flicker an indicator; the
        # refreshing alert appears only once work has been in flight this long.
        self.indicator_seconds = indicator_seconds
        self.indicator_timer: TimerHandle | None = None
        self.refreshing_visible = False
        # A key is observed at most once at a time, so a pool sized to the
        # keys lets every key run concurrently and a slow Issue Source never
        # holds a thread the Git or Agent Run observation needs.
        self.executor = ThreadPoolExecutor(
            max_workers=refresh_pool_size(len(scheduler.keys())),
            thread_name_prefix="dashpot-refresh",
        )

    @property
    def refreshing(self) -> tuple[ObservationKey, ...]:
        """Name the keys in flight once they have been for long enough to show."""
        return tuple(self.in_flight) if self.refreshing_visible else ()

    def git_keys(self, project_id: str) -> list[ObservationKey]:
        """Name the keys that observe a Project's Git state, which a mutation changes."""
        return [
            key
            for key in self.scheduler.keys(project_id)
            if key.kind in ("targets", "workspace")
        ]

    def shutdown(self) -> None:
        """Release the pool without waiting for observations still running."""
        self.executor.shutdown(wait=False, cancel_futures=True)

    def refresh(self, trigger: ObservationTrigger) -> None:
        """Observe every key in the Workspace."""
        self.schedule(self.scheduler.keys(), trigger)

    def schedule(
        self,
        keys: Sequence[ObservationKey],
        trigger: ObservationTrigger,
        *,
        rerun_in_flight: bool | None = None,
    ) -> None:
        """Observe ``keys``, coalescing onto any observation already in flight.

        Observations of one key are serialised by the scheduler, so a second
        ticket could never land sooner than the running one; requesting it
        would only discard the running work when it lands. A key in flight
        is therefore left to finish and, unless the trigger coalesces
        (``rerun_in_flight`` decides; by default only a timer tick does), is
        observed once more afterwards under the latest trigger.
        """
        if rerun_in_flight is None:
            rerun_in_flight = trigger not in COALESCED_TRIGGERS
        wanted: list[ObservationKey] = []
        coalesced = False
        for key in keys:
            if key not in self.in_flight:
                wanted.append(key)
            elif rerun_in_flight:
                self.pending_rerun[key] = trigger
                coalesced = True
        tickets = self.scheduler.request(wanted) if wanted else ()
        for ticket in tickets:
            self.in_flight[ticket.key] = ticket.generation
            # Not exclusive: a worker is never cancelled by a later request,
            # so every started observation ends by posting its outcome and
            # the in-flight gate always reopens.
            self.host.run_off_loop(
                f"observe {ticket.key.group}",
                ticket.key.group,
                partial(self.scheduler.observe, ticket),
                partial(ObservationFinished, ticket, trigger),
                executor=self.executor,
            )
        if coalesced and not self.refreshing_visible:
            # The press did something; say so at once rather than after the
            # indicator threshold, which the running observation may have
            # already passed.
            self.refreshing_visible = True
            self.host.update_alert()
        if self.indicator_timer is None and self.in_flight:
            self.indicator_timer = self.host.set_timer(
                self.indicator_seconds, self.show_refreshing, name="refresh indicator"
            )

    def show_refreshing(self) -> None:
        """Show the keys still in flight once the indicator delay has passed."""
        self.indicator_timer = None
        if self.in_flight:
            self.refreshing_visible = True
            self.host.update_alert()

    def finish(
        self, message: ObservationFinished, present: Callable[[Acceptance], None]
    ) -> None:
        """Land one observation: reopen its key, accept it, then run its rerun.

        ``present`` shows the acceptance while the finished ticket is still
        the current generation of its key, and the landings hear of it
        next; whatever they do, the queued rerun is scheduled and the alert
        redrawn afterwards.
        """
        self._release(message.ticket)
        try:
            present(self.accept(message))
            for landing in self.landings:
                landing(message)
        finally:
            self._rerun(message.ticket.key)
            self.host.update_alert()

    def _release(self, ticket: ObservationTicket) -> None:
        if self.in_flight.get(ticket.key) == ticket.generation:
            del self.in_flight[ticket.key]
        # A queued rerun keeps the key refreshing; the indicator stays put
        # until it is scheduled rather than blinking off in between.
        if not self.in_flight and not self.pending_rerun:
            if self.indicator_timer is not None:
                self.indicator_timer.stop()
                self.indicator_timer = None
            self.refreshing_visible = False

    def _rerun(self, key: ObservationKey) -> None:
        # The host lands nothing once it is shutting down, so a rerun never
        # starts on a closed app.
        trigger = self.pending_rerun.pop(key, None)
        if trigger is not None:
            self.schedule([key], trigger)

    def accept(self, message: ObservationFinished) -> Acceptance:
        """Record a failure, or publish an accepted observation and its follow-ups."""
        key = message.ticket.key
        trigger = message.trigger
        if message.error is not None:
            if not self.scheduler.is_current(message.ticket):
                return DroppedObservation(trigger)
            error = f"Refresh failed: {message.error}"
            # The persistent alert already carries a repeated failure; only a
            # new or changed failure earns a toast.
            changed = self.errors.get(key) != error
            self.errors[key] = error
            return FailedObservation(trigger, error, changed)
        outcome = message.outcome
        if outcome is None or not outcome.accepted:
            return DroppedObservation(trigger)
        recovered = self.errors.pop(key, None) is not None
        # Publishing happens here, on the UI thread, so the store is never
        # mutated while a read model is being rendered from it.
        changes = tuple(self.scheduler.publish(self.store))
        # Follow-ups are derived from what was published, not from this
        # ticket's key: another key's handler may already have published
        # this one's pending composition.
        follow_ups = self.scheduler.follow_ups(changes) if changes else ()
        if follow_ups:
            # A follow-up already in flight started before this publish, so
            # it is observed again whatever the trigger.
            self.schedule(follow_ups, trigger, rerun_in_flight=True)
        return PublishedObservation(trigger, recovered, changes)
