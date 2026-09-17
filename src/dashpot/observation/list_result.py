"""Carry one list query's rows, revision, and summary together."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListResult[Row, Summary]:
    """Carry queried rows, their revision, and their typed summary."""

    rows: tuple[Row, ...]
    summary: Summary
    revision: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)
