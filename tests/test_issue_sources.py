from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typing_extensions import override

from dashpot.issue_sources import IssueSource

ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


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
    def _collect(self) -> list[dict[str, Any]]:
        if self.fault is not None:
            raise self.fault
        return [dict(ISSUE_FIXTURE)]


def test_an_unforeseen_adapter_fault_is_a_failed_refresh_not_a_raise() -> None:
    source = FaultySource()
    assert source.refresh().status == "fresh"
    source.fault = KeyError("pageInfo")

    observation = source.refresh()

    # ADR 0002: a failed refresh yields a diagnostic and keeps the last good
    # collection; it never propagates into the observer.
    assert observation.status == "stale"
    assert observation.issues == [ISSUE_FIXTURE]
    (diagnostic,) = observation.diagnostics
    assert diagnostic.code == "faulty-internal"
    assert diagnostic.severity == "warning"
    assert diagnostic.message == "KeyError: 'pageInfo'"


def test_a_fault_before_any_good_collection_is_unavailable() -> None:
    source = FaultySource()
    source.fault = OSError("cannot fork")

    observation = source.refresh()

    assert observation.status == "unavailable"
    assert observation.issues == []
    assert observation.diagnostics[0].severity == "error"
