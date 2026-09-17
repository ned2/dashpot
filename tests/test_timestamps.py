from __future__ import annotations

import re
from datetime import UTC, datetime

from dashpot.core.timestamps import observed_instant, utc_now, utc_timestamp


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
