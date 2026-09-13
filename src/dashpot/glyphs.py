"""The Glyph vocabulary: a rendered symbol is never separated from its meaning.

Each pane owns the Glyphs it renders and expresses them as `Glyph` values, so
a cell reads `glyph.symbol` and the Legend reads `glyph.meaning` from the
same constant. A Glyph therefore cannot be added without a meaning, and the
Legend cannot omit one that a pane renders.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model import RunState


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


ACTIVITY_COLUMN_GLYPH = Glyph("◈", "the agent activity column")
ACTIVITY_WIDTH = 1
SESSION_STATE_ORDER: dict[RunState, int] = {"running": 0, "waiting": 1, "unknown": 2}
SESSION_STATE_GLYPHS: dict[RunState, Glyph] = {
    "running": Glyph("●", "an Agent Session is running", ("#1a7f37", "#3fb950")),
    "waiting": Glyph("◐", "an Agent Session is waiting", ("#9a6700", "#d29922")),
    "unknown": Glyph(
        "○", "an Agent Session in an unknown state", ("#59636e", "#8b949e")
    ),
}
# The shared agent-activity column's Legend, ranked as its cells are.
ACTIVITY_LEGEND = (
    ACTIVITY_COLUMN_GLYPH,
    *(SESSION_STATE_GLYPHS[state] for state in SESSION_STATE_ORDER),
)
# Between a symbol and its meaning on a Legend or tooltip line.
MEANING_GUTTER = "  "


def align_symbols(glyphs: Sequence[Glyph]) -> list[tuple[str, str]]:
    """Pair each symbol, padded to the widest, with its meaning."""
    width = max((len(glyph.symbol) for glyph in glyphs), default=0)
    return [(glyph.symbol.ljust(width), glyph.meaning) for glyph in glyphs]
