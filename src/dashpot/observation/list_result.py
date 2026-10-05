"""Carry one list query's rows and summary together."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListResult[Row, Summary = None]:
    """Carry queried rows and their typed summary."""

    rows: tuple[Row, ...]
    summary: Summary

    @property
    def count(self) -> int:
        return len(self.rows)
