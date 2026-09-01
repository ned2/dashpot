"""Read strings out of untrusted JSON records and hook inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def require_string(value: object, name: str) -> str:
    """Read a required hook input string, raising ``RuntimeError`` when it is not."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"hook input needs non-empty {name}")
    return value


def require_field(record: Mapping[str, Any], key: str) -> str:
    """Read a required record string field, raising ``ValueError`` when it is not."""
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"record needs non-empty {key}")
    return value


def optional_string(value: object) -> str | None:
    """Read a value as its string when it is a non-empty one, else ``None``."""
    return value if isinstance(value, str) and value else None
