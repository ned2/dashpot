from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from dashpot.core.timestamps import (
    local_clock_text,
    local_clock_with_offset_text,
    observed_instant,
    reported_instant,
    utc_now,
    utc_timestamp,
)


def test_the_clock_stamps_a_fixed_width_utc_instant() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", utc_now())


def test_observations_order_by_instant_with_unstamped_records_first() -> None:
    earliest = datetime.min.replace(tzinfo=UTC)

    assert observed_instant("2026-08-28T01:00:00Z") == datetime(
        2026, 8, 28, 1, tzinfo=UTC
    )
    # A record older than the format may carry a naive instant; it is read as UTC.
    assert observed_instant("2026-08-28T01:00:00") == datetime(
        2026, 8, 28, 1, tzinfo=UTC
    )
    assert observed_instant(None) == earliest
    assert observed_instant("") == earliest
    assert observed_instant("not an instant") == earliest


def test_offset_timestamps_normalise_to_utc_and_others_pass_through() -> None:
    assert utc_timestamp("2026-08-28T11:00:00+10:00") == "2026-08-28T01:00:00Z"
    assert utc_timestamp("2026-08-28T01:00:00") == "2026-08-28T01:00:00Z"
    assert utc_timestamp("yesterday") == "yesterday"


def test_a_reported_instant_without_an_offset_is_read_as_utc() -> None:
    assert reported_instant("2026-08-28T11:00:00+10:00") == datetime(
        2026, 8, 28, 1, tzinfo=UTC
    )
    assert reported_instant("2026-08-28T01:00:00Z") == datetime(
        2026, 8, 28, 1, tzinfo=UTC
    )
    assert reported_instant("2026-08-28T01:00:00") == datetime(
        2026, 8, 28, 1, tzinfo=UTC
    )
    assert reported_instant("not an instant") is None


@pytest.mark.usefixtures("local_clock_ten_hours_ahead")
def test_an_instant_is_shown_on_the_local_clock() -> None:
    instant = datetime(2026, 9, 27, 13, 0, 5, 250_000, tzinfo=UTC)

    assert local_clock_text(instant) == "23:00:05"
    # Text read away from the dashboard names the clock by its offset.
    assert local_clock_with_offset_text(instant) == "23:00:05 +10:00"
