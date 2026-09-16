"""Read strings out of untrusted hook inputs and records."""

from __future__ import annotations


def require_string(value: object, name: str) -> str:
    """Read a required hook input string, raising ``RuntimeError`` when it is not."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"hook input needs non-empty {name}")
    return value


def optional_string(value: object) -> str | None:
    """Read a value as its string when it is a non-empty one, else ``None``."""
    return value if isinstance(value, str) and value else None
