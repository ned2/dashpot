"""The Glyph vocabulary: a rendered symbol is never separated from its meaning.

Each pane owns the Glyphs it renders and expresses them as `Glyph` values, so
a cell reads `glyph.symbol` and the Legend reads `glyph.meaning` from the
same constant. A Glyph therefore cannot be added without a meaning, and the
Legend cannot omit one that a pane renders.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..core.model import RunState
from ..observation.session_list import SESSION_STATE_ORDER

# GitHub Primer foreground colours every pane's Glyphs share; each pair is
# (light theme, dark theme), and a Glyph never spells a colour of its own.
GOOD_COLORS = ("#1a7f37", "#3fb950")
ATTENTION_COLORS = ("#9a6700", "#d29922")
BAD_COLORS = ("#cf222e", "#f85149")
MUTED_COLORS = ("#59636e", "#8b949e")
DONE_COLORS = ("#8250df", "#ab7df8")
# Primer emphasis colours: the block behind an Issue's state, which its chip
# and the ISSUE pane border repeat so the border's meaning is discoverable.
OPEN_EMPHASIS_COLORS = ("#1f883d", "#238636")
DONE_EMPHASIS_COLORS = ("#8250df", "#8957e5")
NEUTRAL_EMPHASIS_COLORS = ("#59636e", "#656c76")


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
    """One Legend entry: a pane column's Glyphs, ranked, and its Column Description.

    A section that is not a column, such as a pane's key actions, names
    itself in ``column`` and carries no Glyphs.
    """

    pane: str
    column: str
    glyphs: tuple[Glyph, ...]
    note: str | None = None


ACTIVITY_COLUMN_GLYPH = Glyph("◈", "the agent activity column")
ACTIVITY_WIDTH = 1
SESSION_STATE_GLYPHS: dict[RunState, Glyph] = {
    "running": Glyph("●", "an Agent Session is running", GOOD_COLORS),
    "waiting": Glyph("◐", "an Agent Session is waiting", ATTENTION_COLORS),
    "unknown": Glyph("○", "an Agent Session in an unknown state", MUTED_COLORS),
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
