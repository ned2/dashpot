"""The Legend: every Glyph the main screen renders, explained where it is seen.

The Legend is generated from the Glyph values the panes render with, so it is
never a second list to keep in step. Its sections follow the main screen top
to bottom and name the column a Glyph appears in, because the reader's
question is always about the cell in front of them. The Branches sections
are the pane's own column definitions, whose descriptions and Glyphs the
header tooltips read too.
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

from . import alerts, issue_cells, pull_request_cells
from .branch_cells import BRANCH_COLUMNS
from .glyphs import (
    ACTIVITY_COLUMN_GLYPH,
    ACTIVITY_LEGEND,
    MEANING_GUTTER,
    Glyph,
    LegendSection,
    align_symbols,
)
from .list_pane import (
    BRANCHES_PANE_LABEL,
    ISSUE_PANE_LABEL,
    PULL_REQUESTS_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
)
from .worktree_cells import activity_description, sessions_description

DIAGNOSTICS_LABEL = "ALERT · DIAGNOSTICS"
KEYS_LABEL = "KEYS"
SESSIONS_COUNT_NOTE = (
    f"the activity Glyph shows {activity_description('here')}; the next "
    f"SESSIONS column shows {sessions_description('here')}"
)
AGENT_STATE_NOTE = "the liveliest explicitly bound Agent Run; blank when none"
RELATED_ROWS_NOTE = (
    "Sessions, Worktrees, Branches, and Issues emphasize direct relationships "
    "from the focused cursor with a background and bold identifying cells "
    "(HARNESS and TARGET for Sessions). Sessions links its location and bound "
    "Issue; Worktrees and Branches link checked-out topology, directly located "
    "Sessions, and their bound Issues; Issues links bound Sessions and their "
    "locations. No recursive expansion: Project-scoped locations and accepted "
    "Agent Run memberships establish links, never Issue Hints or shared backend "
    "processes. Pane entry selects the first row; refresh preserves surviving "
    "cursor keys. Controls and modals clear emphasis; Pull Requests are excluded. "
    "Other cursors, filters, scroll positions, activity Glyphs, and counts stay "
    "unchanged; selection performs no observation or mutation"
)
WORKTREE_SESSIONS_NOTE = (
    f"{SESSIONS_COUNT_NOTE}; x removes a linked Worktree only when it is clean, "
    "unlocked, and no Agent Session or Agent Run is here, and retains its Branch "
    "unless that is selected too; the primary Worktree needs no checkbox, and f "
    "fetches and rebuilds the preview before confirmation; Enter opens the selected Worktree in tmux or a "
    "custom launcher, and y sends its full path to the terminal clipboard"
)

LEGEND: tuple[LegendSection, ...] = (
    LegendSection(
        SESSIONS_PANE_LABEL,
        ACTIVITY_COLUMN_GLYPH.symbol,
        ACTIVITY_LEGEND,
        RELATED_ROWS_NOTE,
    ),
    LegendSection(
        WORKTREES_PANE_LABEL,
        ACTIVITY_COLUMN_GLYPH.symbol,
        ACTIVITY_LEGEND,
        WORKTREE_SESSIONS_NOTE,
    ),
    # Every Branches column, Glyphs or not, in the order the pane shows them:
    # the section is the column's own definition, as its header tooltip is.
    *(
        LegendSection(
            BRANCHES_PANE_LABEL, column.label, column.glyphs, column.description
        )
        for column in BRANCH_COLUMNS
    ),
    LegendSection(PULL_REQUESTS_PANE_LABEL, "STATE", pull_request_cells.STATE_LEGEND),
    LegendSection(PULL_REQUESTS_PANE_LABEL, "REVIEW", pull_request_cells.REVIEW_LEGEND),
    LegendSection(PULL_REQUESTS_PANE_LABEL, "CHECKS", pull_request_cells.CHECKS_LEGEND),
    LegendSection(PULL_REQUESTS_PANE_LABEL, "MERGE", pull_request_cells.MERGE_LEGEND),
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
    """One line per Glyph, the symbol in the colour the cell shows it in.

    A column that renders no Glyph, such as BRANCH, is its note alone.
    """
    text = Text()
    for index, (glyph, (symbol, meaning)) in enumerate(
        zip(section.glyphs, align_symbols(section.glyphs), strict=True)
    ):
        if index:
            text.append("\n")
        text.append(symbol, style=glyph.style(dark=dark, theme=theme))
        text.append(f"{MEANING_GUTTER}{meaning}")
    if section.note:
        if section.glyphs:
            text.append("\n")
        text.append(section.note, style="dim italic")
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
