"""The widget-free shape of a pane row: its columns, cells and clipping.

A read model's query half never renders, and its cells half renders without
a widget; both describe rows with the values here so neither imports Textual.
``list_pane`` builds its tables from the same values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.text import Text

from .glyphs import MEANING_GUTTER, Glyph, align_symbols

ListCell = str | Text

ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class ListColumn:
    """One pane column: its identity, heading, layout, and what it means.

    ``description`` says what the column shows, and ``glyphs`` are the
    Glyphs its cells render, in Legend order. The header tooltip and the
    Legend's section for the column are both built from these two fields,
    so neither can drift from the other.
    """

    key: str
    label: str
    width: int | None = None
    frozen: bool = False
    justify: Literal["left", "center", "right", "full"] | None = None
    description: str | None = None
    glyphs: tuple[Glyph, ...] = ()


def column_help(column: ListColumn) -> str | None:
    """The column's description with its Glyph meanings, for a header tooltip.

    Nothing when the column carries no description: a Glyph alone is
    explained by the Legend, not by a tooltip that repeats it without
    saying what the column is.
    """
    if column.description is None:
        return None
    lines = [column.description]
    lines.extend(
        f"{symbol}{MEANING_GUTTER}{meaning}"
        for symbol, meaning in align_symbols(column.glyphs)
    )
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ListRow:
    """One record in a list pane, keyed by the stable identity it survives by.

    ``issue_id`` is the Issue the row navigates to, when it has one.
    """

    key: str
    cells: tuple[ListCell, ...]
    issue_id: str | None = None


def truncate_end(value: str, limit: int) -> str:
    """Keep the start of an overlong value and say so with an ellipsis."""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + ELLIPSIS


def truncate_start(value: str, limit: int) -> str:
    """Keep the end of an overlong value, which is where a path is specific."""
    if len(value) <= limit:
        return value
    return ELLIPSIS + value[len(value) - max(0, limit - 1) :]
