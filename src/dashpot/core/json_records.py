"""Read strings out of untrusted hook inputs and records."""

from __future__ import annotations

from .errors import DashpotError
from .model import Harness, is_harness


class HookRecordError(DashpotError):
    """A hook input or persisted hook record that cannot be read as one."""


def require_string(value: object, name: str) -> str:
    """Read a required hook input string, refusing an absent or empty one."""
    if not isinstance(value, str) or not value:
        raise HookRecordError(f"hook input needs non-empty {name}")
    return value


def optional_string(value: object) -> str | None:
    """Read a value as its string when it is a non-empty one, else ``None``."""
    return value if isinstance(value, str) and value else None


def require_harness(value: object, name: str = "harness") -> Harness:
    """Read a required hook input harness name, refusing an unsupported one."""
    text = require_string(value, name)
    if not is_harness(text):
        raise HookRecordError(f"unsupported {name}: {text!r}")
    return text
