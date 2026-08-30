"""The Glyph vocabulary: a rendered symbol is never separated from its meaning.

Each pane owns the Glyphs it renders and expresses them as `Glyph` values, so
a cell reads `glyph.symbol` and the Legend reads `glyph.meaning` from the
same constant. A Glyph therefore cannot be added without a meaning, and the
Legend cannot omit one that a pane renders.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Glyph:
    """One rendered symbol and the fact it stands for."""

    symbol: str
    meaning: str
    # (light theme, dark theme) when the symbol carries a semantic colour of
    # its own; ``theme_color`` names a Textual theme variable when the colour
    # comes from the enclosing widget's stylesheet instead.
    colors: tuple[str, str] | None = None
    theme_color: str | None = None

    def style(self, *, dark: bool, theme: Mapping[str, str] | None = None) -> str:
        """The colour for the current theme, or no style."""
        if self.colors is not None:
            return self.colors[dark]
        if self.theme_color is not None and theme is not None:
            return theme.get(self.theme_color, "")
        return ""


@dataclass(frozen=True, slots=True)
class LegendSection:
    """The Glyphs one column of one pane renders, in the order they are ranked."""

    pane: str
    column: str
    glyphs: tuple[Glyph, ...]
    # What the column shows around the Glyph, when the symbol is not the
    # whole cell.
    note: str | None = None
