"""Describe how long ago an observed timestamp was, as a tracker feed would."""

from __future__ import annotations

from datetime import UTC, datetime


def relative_age(timestamp: str | None, now: datetime) -> str | None:
    """A tracker-feed style age such as ``just now``, ``5m ago`` or ``3d ago``."""
    if not timestamp:
        return None
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
