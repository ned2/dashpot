"""An age is a tracker-feed phrase, and an unreadable timestamp has none."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dashpot.core.ages import relative_age

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-09-13T11:59:30Z", "just now"),
        ("2026-09-13T11:55:00Z", "5m ago"),
        ("2026-09-13T09:00:00Z", "3h ago"),
        ("2026-09-10T12:00:00Z", "3d ago"),
        ("2026-09-13T13:00:00Z", "just now"),
        # A naive timestamp is read as UTC rather than refused.
        ("2026-09-13T11:00:00", "1h ago"),
    ],
)
def test_relative_age_phrases_the_elapsed_time(timestamp: str, expected: str) -> None:
    assert relative_age(timestamp, NOW) == expected


@pytest.mark.parametrize("timestamp", [None, "", "yesterday"])
def test_relative_age_has_nothing_to_say_without_a_timestamp(
    timestamp: str | None,
) -> None:
    assert relative_age(timestamp, NOW) is None
