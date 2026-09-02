"""The Legend: every Glyph the main screen renders, explained where it is seen.

The Legend is generated from the Glyph values the panes render with, so it is
never a second list to keep in step. Its sections follow the main screen top
to bottom and name the column a Glyph appears in, because the reader's
question is always about the cell in front of them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.color import Color
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static
from typing_extensions import override

from . import alerts, branch_list, issue_cells, session_list
from .glyphs import Glyph, LegendSection
from .list_pane import (
    BRANCHES_PANE_LABEL,
    ISSUE_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
)

DIAGNOSTICS_LABEL = "ALERT · DIAGNOSTICS"
KEYS_LABEL = "KEYS"
SESSIONS_COUNT_NOTE = (
    "followed by how many Agent Sessions are located here, led by the liveliest state"
)
AGENT_STATE_NOTE = "blank when no Agent Run is on the Issue"

LEGEND: tuple[LegendSection, ...] = (
    LegendSection(SESSIONS_PANE_LABEL, "STATE", session_list.LEGEND),
    LegendSection(BRANCHES_PANE_LABEL, "LOCAL", branch_list.PRESENCE_LEGEND),
    LegendSection(BRANCHES_PANE_LABEL, "REMOTE", branch_list.PRESENCE_LEGEND),
    LegendSection(BRANCHES_PANE_LABEL, "UPSTREAM", branch_list.UPSTREAM_LEGEND),
    LegendSection(BRANCHES_PANE_LABEL, "INTEGRATED", branch_list.INTEGRATION_LEGEND),
    LegendSection(
        BRANCHES_PANE_LABEL, "SESSIONS", session_list.LEGEND, SESSIONS_COUNT_NOTE
    ),
    LegendSection(
        WORKTREES_PANE_LABEL, "SESSIONS", session_list.LEGEND, SESSIONS_COUNT_NOTE
    ),
    LegendSection(
        ISSUE_PANE_LABEL,
        issue_cells.ISSUE_STATE_COLUMN_GLYPH.symbol,
        issue_cells.LEGEND_ISSUE_STATE,
    ),
    LegendSection(
        ISSUE_PANE_LABEL,
        issue_cells.AGENT_STATE_COLUMN_GLYPH.symbol,
        issue_cells.LEGEND_AGENT_STATE,
        AGENT_STATE_NOTE,
    ),
    LegendSection(ISSUE_PANE_LABEL, "column headers", issue_cells.LEGEND_SORT),
    LegendSection(DIAGNOSTICS_LABEL, "severity", alerts.LEGEND),
)


def legend_glyphs() -> tuple[Glyph, ...]:
    """Every Glyph the Legend explains, once each, in Legend order."""
    seen: list[Glyph] = []
    for section in LEGEND:
        seen.extend(glyph for glyph in section.glyphs if glyph not in seen)
    return tuple(seen)


def section_heading(section: LegendSection) -> str:
    return f"{section.pane} · {section.column}"


def theme_colors(variables: Mapping[str, str]) -> dict[str, str]:
    """Resolve each theme variable a Glyph names to its colour on ``$surface``.

    The stylesheet resolves ``auto 60%`` and alpha colours against the box
    behind them; the Legend's rows sit on the same surface as Diagnostics.
    """
    surface = Color.parse(variables["surface"])
    resolved: dict[str, str] = {}
    for glyph in legend_glyphs():
        name = glyph.theme_color
        if name is None or name in resolved:
            continue
        value = variables[name]
        if value.startswith("auto"):
            percent = value.removeprefix("auto").strip().rstrip("%")
            color = surface.get_contrast_text(float(percent) / 100 if percent else 1)
        else:
            color = Color.parse(value)
        resolved[name] = (surface + color).hex6
    return resolved


def section_text(
    section: LegendSection, *, dark: bool, theme: Mapping[str, str] | None = None
) -> Text:
    """One line per Glyph, the symbol in the colour the cell shows it in."""
    width = max(len(glyph.symbol) for glyph in section.glyphs)
    text = Text()
    for index, glyph in enumerate(section.glyphs):
        if index:
            text.append("\n")
        text.append(
            glyph.symbol.ljust(width), style=glyph.style(dark=dark, theme=theme)
        )
        text.append(f"  {glyph.meaning}")
    if section.note:
        text.append(f"\n{section.note}", style="dim italic")
    return text


class LegendScreen(ModalScreen[None]):
    """Explain every Glyph and key binding without leaving the keyboard."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
    ]

    def __init__(self, bindings: Sequence[BindingType]) -> None:
        # The caller supplies the bindings to list: the dashboard's keys live
        # on the DashboardScreen, which this module must not import.
        super().__init__()
        self.legend_bindings = tuple(bindings)

    @override
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="legend-dialog"):
            yield Static("LEGEND", id="legend-title")
            for index, section in enumerate(LEGEND):
                yield Static(
                    section_heading(section),
                    classes="legend-heading",
                    id=f"legend-heading-{index}",
                )
                yield Static(
                    section_text(
                        section,
                        dark=self.app.current_theme.dark,
                        theme=theme_colors(self.app.get_css_variables()),
                    ),
                    classes="legend-section",
                    id=f"legend-section-{index}",
                )
            yield Static(KEYS_LABEL, classes="legend-heading", id="legend-keys-heading")
            yield Static(self.keys_text(), classes="legend-section", id="legend-keys")

    def keys_text(self) -> Text:
        """The supplied bindings as the Footer would show them, one per line."""
        bindings = list(Binding.make_bindings(self.legend_bindings))
        width = max(len(self.app.get_key_display(binding)) for binding in bindings)
        text = Text()
        for index, binding in enumerate(bindings):
            if index:
                text.append("\n")
            text.append(self.app.get_key_display(binding).ljust(width), style="bold")
            text.append(f"  {binding.description}")
        return text

    def action_close(self) -> None:
        self.dismiss(None)
