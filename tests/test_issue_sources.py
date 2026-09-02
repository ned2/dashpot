from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from typing_extensions import override

from dashpot.issue_profile import conform_issue
from dashpot.issue_sources import (
    CollectedIssues,
    IssueHint,
    IssueSource,
    IssueSourceObservation,
    IssueSourceRefreshError,
    parse_issue_hint,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ISSUE = conform_issue(
    json.loads(
        (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
    )
)


def fixture_location() -> str:
    """The fixture Issue's Location as it should appear in a diagnostic."""
    location = FIXTURE_ISSUE.location
    assert location.kind == "github"
    return location.url


class FaultySource(IssueSource):
    """A source whose adapter raises something it did not foresee."""

    def __init__(self) -> None:
        super().__init__(clock=lambda: "2026-08-31T00:00:00Z")
        self.fault: Exception | None = None

    @property
    @override
    def name(self) -> str:
        return "faulty"

    @override
    def _collect(self) -> CollectedIssues:
        if self.fault is not None:
            raise self.fault
        return CollectedIssues((FIXTURE_ISSUE,))


class ScriptedSource(IssueSource):
    """A source that returns each scripted collection cycle in turn."""

    def __init__(self, cycles: list[CollectedIssues | Exception]) -> None:
        super().__init__(clock=lambda: "2026-08-31T00:00:00Z")
        self.cycles = cycles

    @property
    @override
    def name(self) -> str:
        return "scripted"

    @override
    def _collect(self) -> CollectedIssues:
        cycle = self.cycles.pop(0)
        if isinstance(cycle, Exception):
            raise cycle
        return cycle


def test_an_unforeseen_adapter_fault_is_a_failed_refresh_not_a_raise() -> None:
    source = FaultySource()
    assert source.refresh().status == "fresh"
    source.fault = KeyError("pageInfo")

    observation = source.refresh()

    # ADR 0002: a failed refresh yields a diagnostic and keeps the last good
    # collection; it never propagates into the observer.
    assert observation.status == "stale"
    assert observation.issues == (FIXTURE_ISSUE,)
    (diagnostic,) = observation.diagnostics
    assert diagnostic.code == "faulty-internal"
    assert diagnostic.severity == "warning"
    assert diagnostic.message == "KeyError: 'pageInfo'"


def test_a_fault_before_any_good_collection_is_unavailable() -> None:
    source = FaultySource()
    source.fault = OSError("cannot fork")

    observation = source.refresh()

    assert observation.status == "unavailable"
    assert observation.issues == ()
    assert observation.diagnostics[0].severity == "error"


def test_a_duplicate_issue_identity_is_refused_by_the_base_class() -> None:
    twin = FIXTURE_ISSUE.model_copy(update={"number": FIXTURE_ISSUE.number + 1})
    source = ScriptedSource([CollectedIssues((FIXTURE_ISSUE, twin))])

    observation = source.refresh()

    assert observation.status == "unavailable"
    assert observation.issues == ()
    (diagnostic,) = observation.diagnostics
    assert diagnostic.code == "scripted-duplicate-identity"
    assert FIXTURE_ISSUE.id in diagnostic.message
    assert fixture_location() in diagnostic.message


def test_a_duplicate_issue_number_is_refused_by_the_base_class() -> None:
    twin = FIXTURE_ISSUE.model_copy(update={"id": "I_kwDOUEerrs7L_other"})
    source = ScriptedSource([CollectedIssues((FIXTURE_ISSUE, twin))])

    observation = source.refresh()

    assert observation.status == "unavailable"
    assert observation.issues == ()
    (diagnostic,) = observation.diagnostics
    assert diagnostic.code == "scripted-duplicate-number"
    assert f"#{FIXTURE_ISSUE.number}" in diagnostic.message
    assert fixture_location() in diagnostic.message


def test_a_failed_cycle_never_leaks_its_palette_into_the_next_observation() -> None:
    good = CollectedIssues(
        issues=(FIXTURE_ISSUE,), label_colors={"enhancement": "a2eeef"}
    )
    # The failed cycle carries a different palette; because a cycle is one
    # value rather than three hook calls, none of it can survive the raise.
    source = ScriptedSource([good, RuntimeError("mid-cycle fault")])

    assert dict(source.refresh().label_colors) == {"enhancement": "a2eeef"}
    observation = source.refresh()

    assert observation.status == "stale"
    assert dict(observation.label_colors) == {"enhancement": "a2eeef"}
    assert dict(observation.issue_activity) == {}


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("35", IssueHint(raw="35", number=35, reference=None)),
        ("#35", IssueHint(raw="#35", number=35, reference=None)),
        (" 35 ", IssueHint(raw="35", number=35, reference=None)),
        (
            "worktree-protocol",
            IssueHint(
                raw="worktree-protocol", number=None, reference="worktree-protocol"
            ),
        ),
        (
            "ned2/dashpot#35",
            IssueHint(raw="ned2/dashpot#35", number=35, reference="ned2/dashpot#35"),
        ),
        (
            "https://github.com/ned2/dashpot/issues/35",
            IssueHint(
                raw="https://github.com/ned2/dashpot/issues/35",
                number=35,
                reference="ned2/dashpot#35",
            ),
        ),
        (
            "https://github.com/ned2/dashpot/issues/35/",
            IssueHint(
                raw="https://github.com/ned2/dashpot/issues/35/",
                number=35,
                reference="ned2/dashpot#35",
            ),
        ),
        (
            "https://github.com/ned2/dashpot/issues/35#issuecomment-1",
            IssueHint(
                raw="https://github.com/ned2/dashpot/issues/35#issuecomment-1",
                number=35,
                reference="ned2/dashpot#35",
            ),
        ),
        (
            "https://github.com/ned2/dashpot/issues/35?notification_referrer_id=x",
            IssueHint(
                raw="https://github.com/ned2/dashpot/issues/35?notification_referrer_id=x",
                number=35,
                reference="ned2/dashpot#35",
            ),
        ),
    ],
)
def test_parse_issue_hint_normalizes_numbers_references_and_urls(
    hint: str, expected: IssueHint
) -> None:
    assert parse_issue_hint(hint) == expected


def test_default_find_matches_misses_and_refuses_ambiguity() -> None:
    twin = FIXTURE_ISSUE.model_copy(
        update={"id": "I_twin", "number": FIXTURE_ISSUE.number + 1}
    )
    source = ScriptedSource([CollectedIssues((FIXTURE_ISSUE, twin))] * 3)

    assert source.find(parse_issue_hint(str(FIXTURE_ISSUE.number))) == FIXTURE_ISSUE
    assert source.find(parse_issue_hint("999")) is None
    # Both Issues share one Reference; only the complete collection can see it.
    with pytest.raises(IssueSourceRefreshError, match="is ambiguous") as caught:
        source.find(parse_issue_hint(FIXTURE_ISSUE.reference))
    assert caught.value.code == "scripted-ambiguous-hint"


def test_default_find_raises_the_diagnosis_when_the_source_cannot_answer() -> None:
    source = ScriptedSource([IssueSourceRefreshError("scripted-down", "no answer")])

    with pytest.raises(IssueSourceRefreshError, match="unavailable") as caught:
        source.find(parse_issue_hint("9"))

    assert caught.value.code == "scripted-down"


def test_concurrent_refreshes_do_not_cross_contaminate() -> None:
    first = CollectedIssues(issues=(FIXTURE_ISSUE,), label_colors={"one": "111111"})
    second = CollectedIssues(issues=(), label_colors={"two": "222222"})
    source = ScriptedSource([first, second])
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    observations: list[IssueSourceObservation] = []

    def refresh() -> None:
        barrier.wait(timeout=2)
        observation = source.refresh()
        with lock:
            observations.append(observation)

    threads = [threading.Thread(target=refresh) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    # Each observation pairs its own cycle's issues with its own palette: the
    # observation is built from the cycle's CollectedIssues, not an instance
    # stash. (The _last_good retention fields stay unlocked; the coordinator
    # serializes refreshes per key in production.)
    issues_by_palette = {
        "".join(observation.label_colors): observation.issues
        for observation in observations
    }
    assert issues_by_palette == {"one": (FIXTURE_ISSUE,), "two": ()}
