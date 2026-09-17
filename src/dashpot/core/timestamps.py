"""Stamp and read the RFC 3339 UTC instants Dashpot records and observes."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> str:
    """Stamp an observation, at a fixed width so records order by text too."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def observed_instant(value: str | None) -> datetime:
    """Order observations by instant; a record may be older than the format.

    Unstamped and unparsable records sort before every stamped one rather
    than claiming a time Dashpot never observed.
    """
    if value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def utc_timestamp(value: str) -> str:
    """Normalise an offset timestamp to UTC so timestamps sort as text."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
