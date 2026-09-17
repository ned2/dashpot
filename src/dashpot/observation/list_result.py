from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

Row = TypeVar("Row")
Summary = TypeVar("Summary")


@dataclass(frozen=True, slots=True)
class ListResult(Generic[Row, Summary]):
    """Carry queried rows, their revision, and their typed summary."""

    rows: tuple[Row, ...]
    summary: Summary
    revision: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)
