"""Word the English a person reads, so every surface agrees on it."""

from __future__ import annotations


def counted(count: int, noun: str) -> str:
    """``1 commit`` or ``3 commits``: a count with its noun agreeing."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
