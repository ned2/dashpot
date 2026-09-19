"""The observation runner coalesces requests onto the key in flight, without an app."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pytest
from textual.message import Message

from app_harness import issue, workspace_snapshot
from dashpot.observation.keys import (
    ObservationKey,
    ObservationOutcome,
    ObservationTicket,
)
from dashpot.observation.observation_store import StoreChange, WorkspaceObservationStore
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.ui.messages import ObservationFinished, ObservationTrigger
from dashpot.ui.observation_runner import (
    COALESCED_TRIGGERS,
    Acceptance,
    DroppedObservation,
    FailedObservation,
    ObservationRunner,
    PublishedObservation,
    refresh_pool_size,
)

ALPHA = ObservationKey("issues", "alpha")
BETA = ObservationKey("issues", "beta")
TARGETS = ObservationKey("targets", "alpha")


@dataclass
class OffLoopCall:
    """One operation the runner asked the host to run, held until landed."""

    name: str
    group: str
    operation: Callable[[], ObservationOutcome]
    on_done: Callable[[ObservationOutcome | None, str | None], Message]

    def land(self, *, error: str | None = None) -> ObservationFinished:
        """Run the operation, or fail it, and build the message it would post."""
        message = (
            self.on_done(None, error)
            if error is not None
            else self.on_done(self.operation(), None)
        )
        assert isinstance(message, ObservationFinished)
        return message


class FakeTimer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeHost:
    """Record what the runner asks for; nothing runs until a test lands it."""

    def __init__(self) -> None:
        self.calls: list[OffLoopCall] = []
        self.timers: list[tuple[float, Callable[[], None], FakeTimer]] = []
        self.alerts = 0

    def run_off_loop(
        self,
        name: str,
        group: str,
        operation: Callable[[], ObservationOutcome],
        on_done: Callable[[ObservationOutcome | None, str | None], Message],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        assert executor is not None
        self.calls.append(OffLoopCall(name, group, operation, on_done))

    def set_timer(
        self, delay: float, callback: Callable[[], None], *, name: str | None = None
    ) -> FakeTimer:
        timer = FakeTimer()
        self.timers.append((delay, callback, timer))
        return timer

    def update_alert(self) -> None:
        self.alerts += 1

    def pop_call(self, key: ObservationKey) -> OffLoopCall:
        """Take the one started observation of ``key``."""
        matching = [call for call in self.calls if call.group == key.group]
        assert len(matching) == 1, [call.group for call in self.calls]
        self.calls.remove(matching[0])
        return matching[0]

    def fire_timer(self) -> None:
        _delay, callback, _timer = self.timers.pop(0)
        callback()


@dataclass
class FakeScheduler:
    """Mint one generation per key and script what a publish changes."""

    all_keys: tuple[ObservationKey, ...] = (ALPHA, BETA)
    follow_up_keys: tuple[ObservationKey, ...] = ()
    changes_per_publish: list[StoreChange] = field(default_factory=list)
    generations: dict[ObservationKey, int] = field(default_factory=dict)
    observed: list[ObservationTicket] = field(default_factory=list)
    published: int = 0

    def keys(self, project_id: str | None = None) -> Sequence[ObservationKey]:
        return self.all_keys

    def request(self, keys: Sequence[ObservationKey]) -> list[ObservationTicket]:
        tickets = []
        for key in keys:
            self.generations[key] = self.generations.get(key, 0) + 1
            tickets.append(ObservationTicket(key, self.generations[key]))
        return tickets

    def is_current(self, ticket: ObservationTicket) -> bool:
        return self.generations.get(ticket.key) == ticket.generation

    def observe(self, ticket: ObservationTicket) -> ObservationOutcome:
        self.observed.append(ticket)
        return ObservationOutcome(ticket, accepted=self.is_current(ticket))

    def publish(self, store: WorkspaceObservationStore) -> list[StoreChange]:
        self.published += 1
        return list(self.changes_per_publish)

    def follow_ups(self, changes: Sequence[StoreChange]) -> Sequence[ObservationKey]:
        return self.follow_up_keys if changes else ()


def runner(
    scheduler: FakeScheduler | None = None, host: FakeHost | None = None
) -> tuple[ObservationRunner, FakeScheduler, FakeHost]:
    scheduler = scheduler or FakeScheduler()
    host = host or FakeHost()
    return (
        ObservationRunner(
            scheduler, PagedObservationStore(), host, indicator_seconds=0.5
        ),
        scheduler,
        host,
    )


def landed(observations: ObservationRunner, message: ObservationFinished) -> Acceptance:
    """Finish ``message`` and return what the runner presented for it."""
    presented: list[Acceptance] = []
    observations.finish(message, presented.append)
    assert len(presented) == 1
    return presented[0]


def test_a_request_during_an_observation_in_flight_reruns_once() -> None:
    observations, scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    running = host.pop_call(ALPHA)
    assert observations.in_flight == {ALPHA: 1}

    # Two presses while the observation runs: neither mints a new ticket,
    # and together they queue exactly one rerun under the latest trigger.
    observations.schedule([ALPHA], "cleanup")
    observations.schedule([ALPHA], "manual")
    assert host.calls == []
    assert scheduler.generations == {ALPHA: 1}
    assert observations.pending_rerun == {ALPHA: "manual"}

    assert isinstance(landed(observations, running.land()), PublishedObservation)
    rerun = host.pop_call(ALPHA)
    assert observations.pending_rerun == {}
    assert observations.in_flight == {ALPHA: 2}
    assert rerun.land().trigger == "manual"


def test_distinct_keys_run_independently() -> None:
    observations, scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    alpha = host.pop_call(ALPHA)

    # A request for another key runs at once; only Alpha is held.
    observations.schedule([ALPHA, BETA], "manual")
    beta = host.pop_call(BETA)
    assert observations.in_flight == {ALPHA: 1, BETA: 1}
    assert observations.pending_rerun == {ALPHA: "manual"}

    landed(observations, beta.land())
    assert observations.in_flight == {ALPHA: 1}
    assert host.calls == []
    landed(observations, alpha.land())
    assert scheduler.generations == {ALPHA: 2, BETA: 1}


def test_only_the_first_observation_of_a_key_is_pending() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([TARGETS], "initial")
    first = host.pop_call(TARGETS)
    assert observations.first_observations_in_flight == (TARGETS,)

    landed(observations, first.land())
    observations.schedule([TARGETS], "timer")
    host.pop_call(TARGETS)

    assert observations.first_observations_in_flight == ()


@pytest.mark.parametrize("trigger", sorted(COALESCED_TRIGGERS))
def test_a_coalesced_trigger_queues_no_rerun(trigger: ObservationTrigger) -> None:
    observations, scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    running = host.pop_call(ALPHA)

    observations.schedule([ALPHA], trigger)
    assert observations.pending_rerun == {}
    assert not observations.refreshing_visible

    landed(observations, running.land())
    assert host.calls == []
    assert scheduler.generations == {ALPHA: 1}


@pytest.mark.parametrize(
    "trigger",
    [
        t
        for t in ("initial", "manual", "fetch", "cleanup")
        if t not in COALESCED_TRIGGERS
    ],
)
def test_every_other_trigger_reruns_after_the_running_observation(
    trigger: ObservationTrigger,
) -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "timer")
    running = host.pop_call(ALPHA)

    observations.schedule([ALPHA], trigger)
    assert observations.pending_rerun == {ALPHA: trigger}
    landed(observations, running.land())
    assert host.pop_call(ALPHA).land().trigger == trigger


def test_rerun_in_flight_overrides_the_trigger_rule() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    host.pop_call(ALPHA)

    observations.schedule([ALPHA], "timer", rerun_in_flight=True)
    assert observations.pending_rerun == {ALPHA: "timer"}
    observations.schedule([BETA], "manual", rerun_in_flight=False)
    host.pop_call(BETA)
    observations.schedule([BETA], "manual", rerun_in_flight=False)
    assert observations.pending_rerun == {ALPHA: "timer"}


def test_a_coalesced_press_shows_refreshing_at_once() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    host.pop_call(ALPHA)
    # The indicator waits for its delay; nothing has been shown yet.
    assert len(host.timers) == 1
    assert host.timers[0][0] == pytest.approx(0.5)
    assert observations.refreshing == ()
    assert host.alerts == 0

    observations.schedule([ALPHA], "manual")
    assert observations.refreshing == (ALPHA,)
    assert host.alerts == 1
    # A second coalesced press changes nothing already shown.
    observations.schedule([ALPHA], "manual")
    assert host.alerts == 1


def test_the_indicator_shows_the_keys_still_in_flight_after_its_delay() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA, BETA], "initial")
    alpha = host.pop_call(ALPHA)
    host.pop_call(BETA)

    landed(observations, alpha.land())
    assert observations.indicator_timer is not None
    host.fire_timer()
    assert observations.indicator_timer is None
    assert observations.refreshing == (BETA,)


def test_a_quick_observation_stops_the_indicator_before_it_fires() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    running = host.pop_call(ALPHA)
    _delay, _callback, timer = host.timers[0]

    landed(observations, running.land())
    assert timer.stopped
    assert observations.indicator_timer is None
    assert not observations.refreshing_visible
    # A timer that had already queued its callback shows nothing.
    observations.show_refreshing()
    assert observations.refreshing == ()


def test_a_queued_rerun_keeps_the_indicator_up_between_observations() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    running = host.pop_call(ALPHA)
    observations.schedule([ALPHA], "manual")
    assert observations.refreshing_visible

    landed(observations, running.land())
    # The rerun is in flight now, and the indicator never blinked off.
    assert observations.refreshing == (ALPHA,)
    assert observations.indicator_timer is not None


def test_a_failure_is_recorded_once_and_a_recovery_is_reported() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "manual")
    failed = landed(observations, host.pop_call(ALPHA).land(error="boom"))
    assert isinstance(failed, FailedObservation)
    assert failed == FailedObservation("manual", "Refresh failed: boom", True)
    assert failed.announced
    assert observations.errors == {ALPHA: "Refresh failed: boom"}

    observations.schedule([ALPHA], "timer")
    repeated = landed(observations, host.pop_call(ALPHA).land(error="boom"))
    assert isinstance(repeated, FailedObservation)
    assert repeated == FailedObservation("timer", "Refresh failed: boom", False)
    assert not repeated.announced

    observations.schedule([ALPHA], "manual")
    recovered = landed(observations, host.pop_call(ALPHA).land())
    assert isinstance(recovered, PublishedObservation)
    assert recovered == PublishedObservation("manual", True, ())
    assert recovered.announced
    assert observations.errors == {}


def test_a_superseded_outcome_is_dropped() -> None:
    observations, scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    stale = host.pop_call(ALPHA)
    # The scheduler moved on; the old ticket's failure and result are stale.
    scheduler.request([ALPHA])
    assert landed(observations, stale.land(error="late")) == DroppedObservation(
        "initial"
    )
    assert observations.errors == {}
    assert landed(observations, stale.land()) == DroppedObservation("initial")
    assert scheduler.published == 0


def test_a_publish_with_changes_schedules_its_follow_ups_whatever_the_trigger() -> None:
    change = StoreChange(1, frozenset({"projects"}))
    scheduler = FakeScheduler(
        all_keys=(ALPHA, TARGETS),
        follow_up_keys=(TARGETS,),
        changes_per_publish=[change],
    )
    observations, _scheduler, host = runner(scheduler)
    observations.schedule([ALPHA, TARGETS], "timer")
    alpha = host.pop_call(ALPHA)
    targets = host.pop_call(TARGETS)

    published = landed(observations, alpha.land())
    assert published == PublishedObservation("timer", False, (change,))
    # The follow-up was already in flight, so a tick still reruns it.
    assert observations.pending_rerun == {TARGETS: "timer"}
    landed(observations, targets.land())
    assert host.pop_call(TARGETS).land().trigger == "timer"


def test_the_rerun_is_scheduled_even_when_presenting_fails() -> None:
    observations, _scheduler, host = runner()
    observations.schedule([ALPHA], "initial")
    running = host.pop_call(ALPHA)
    observations.schedule([ALPHA], "manual")

    def explode(_landed: Acceptance) -> None:
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        observations.finish(running.land(), explode)
    assert observations.pending_rerun == {}
    assert host.pop_call(ALPHA).land().trigger == "manual"


@pytest.mark.parametrize(
    ("key_count", "threads"), [(0, 2), (1, 2), (5, 5), (8, 8), (12, 8)]
)
def test_the_pool_is_sized_to_the_keys(key_count: int, threads: int) -> None:
    assert refresh_pool_size(key_count) == threads


def test_refresh_observes_every_key() -> None:
    observations, _scheduler, host = runner()
    observations.refresh("manual")
    assert sorted(call.group for call in host.calls) == [ALPHA.group, BETA.group]


def test_a_real_observation_is_published_into_the_store() -> None:
    # The runner publishes through the scheduler it is given; the harness
    # scheduler moves a whole checkpoint into the store on acceptance.
    from app_harness import SequenceCollector, SnapshotScheduler

    snapshot = workspace_snapshot(issue("test/repo#1", "First"))
    scheduler = SnapshotScheduler(SequenceCollector(snapshot))
    store = PagedObservationStore()
    host = FakeHost()
    observations = ObservationRunner(scheduler, store, host)
    observations.refresh("initial")
    published = landed(observations, host.calls.pop().land())
    assert isinstance(published, PublishedObservation)
    assert store.has_observations
    assert store.checkpoint() == snapshot
    assert published.changes[0].revision == 1
    observations.shutdown()
