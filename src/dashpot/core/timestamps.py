"""Stamp and read the RFC 3339 UTC instants Dashpot records and observes.

Dashpot stores and compares instants in UTC, and shows them to a person on
the local clock (ADR 0098).
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> str:
    """Stamp an observation, at a fixed width so records order by text too."""
    return utc_stamp(datetime.now(UTC))


def utc_stamp(moment: datetime) -> str:
    """Stamp one instant in UTC, at the fixed width :func:`utc_now` uses."""
    return (
        moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def observed_instant(value: str | None) -> datetime:
    """Order observations by instant; a record may be older than the format.

    Unstamped and unparsable records sort before every stamped one rather
    than claiming a time Dashpot never observed.
    """
    moment = reported_instant(value) if value else None
    return datetime.min.replace(tzinfo=UTC) if moment is None else moment


def reported_instant(value: str) -> datetime | None:
    """Read an RFC 3339 instant, taking one with no offset as UTC; None when unreadable."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def local_clock_text(instant: datetime) -> str:
    """An instant on the local clock, to the second, as the dashboard shows it."""
    return f"{instant.astimezone():%H:%M:%S}"


def local_offset_text(instant: datetime) -> str:
    """An instant on the local clock, to the second, with the clock's UTC offset.

    For text that also reaches headless output, such as a ``--json``
    document's Diagnostics, where no dashboard says which clock it is read on.
    """
    return f"{instant.astimezone():%H:%M:%S %:z}"


def utc_timestamp(value: str) -> str:
    """Normalise an offset timestamp to UTC so timestamps sort as text."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
