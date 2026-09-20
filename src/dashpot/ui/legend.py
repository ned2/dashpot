"""The Legend: every column and Glyph the Peer Screens render, explained.

The Legend is generated from the same column definitions the panes build
their tables from and the same Glyph values their cells render with, so it
is never a second list to keep in step. Its sections follow the Peer Screens
in reading order, one per column of each pane whether or not the column
renders a Glyph, because the reader's question is always about the cell in
front of them; each section is the column's Column Description, which its
header tooltip reads too. The Issue table's optional columns are listed
whether or not they are shown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, override

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.color import Color
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from . import alerts, issue_cells
from .branch_cells import BRANCH_COLUMNS
from .glyphs import MEANING_GUTTER, Glyph, LegendSection, align_symbols
from .issue_table import COLUMN_SPECS, DEFAULT_COLUMNS
from .list_pane import (
    BRANCHES_PANE_LABEL,
    ISSUE_PANE_LABEL,
    PULL_REQUESTS_PANE_LABEL,
    SESSIONS_PANE_LABEL,
    WORKTREES_PANE_LABEL,
)
from .list_rows import DescribedColumn
from .pull_request_cells import PULL_REQUEST_COLUMNS
from .session_cells import SESSION_COLUMNS
from .status_bar import TOTALS_FRESHNESS_LEGEND
from .worktree_cells import WORKTREE_COLUMNS

DIAGNOSTICS_LABEL = "ALERT · DIAGNOSTICS"
KEYS_LABEL = "KEYS"
RELATED_ROWS_LABEL = "RELATED ROWS"
STATUS_BAR_LABEL = "STATUS BAR"
# The sections that are not one column: a pane's keys, the Issue table's
# choice of columns, and the emphasis the panes share.
WORKTREE_ACTIONS_SECTION = "x · Enter · y"
ISSUE_COLUMNS_SECTION = "column headers"
RELATED_ROWS_SECTION = "emphasis"
RELATED_ROWS_NOTE = (
    "Sessions, Worktrees, and Branches emphasize direct relationships within "
    "the Dashboard peer "
    "from the focused cursor with a background and bold identifying cells "
    "(HARNESS and TARGET for Sessions). Sessions links its location and Branch; "
    "Worktrees and Branches link checked-out topology and directly located "
    "Sessions. No recursive expansion: Project-scoped "
    "locations and accepted "
    "Agent Run memberships establish links, never Issue Hints or shared backend "
    "processes. Each pane keeps its cursor across focus changes; refresh "
    "preserves surviving cursor keys. Controls and modals clear emphasis; Issues "
    "and Pull Requests are excluded. "
    "Other cursors, filters, scroll positions, activity Glyphs, and counts stay "
    "unchanged; selection performs no observation or mutation"
)
WORKTREE_ACTIONS_NOTE = (
    "x removes a linked Worktree only when it is clean, unlocked, and no Agent "
    "Session or Agent Run is here, and retains its Branch unless that is "
    "selected too; the primary Worktree needs no checkbox, and f fetches and "
    "rebuilds the preview before confirmation; Enter opens the selected "
    "Worktree in tmux or a custom launcher, and y sends its full path to the "
    "terminal clipboard"
)


def _issue_columns_note() -> str:
    """What the Issue headers and c offer, listing the columns by default and on request."""
    default = [
        spec.label
        for spec in COLUMN_SPECS
        if spec.key in DEFAULT_COLUMNS and spec.key != "agent_state"
    ]
    optional = [spec.label for spec in COLUMN_SPECS if spec.key not in DEFAULT_COLUMNS]
    return (
        "a marked header orders the page by its column when selected, and again "
        "reverses it, where the Issue Source can order by that column; c chooses "
        f"and orders the columns after {issue_cells.AGENT_STATE_COLUMN_GLYPH.symbol}, "
        f"which are {', '.join(default)} until chosen otherwise and "
        f"{', '.join(optional)} on request"
    )


ISSUE_COLUMNS_NOTE = _issue_columns_note()


def column_sections(
    pane: str, columns: Iterable[DescribedColumn]
) -> tuple[LegendSection, ...]:
    """One Legend section per column, from the column's own definition.

    The section's Glyph lines and note are the column's Column Description,
    which is also what its header tooltip reads, so neither can drift.
    """
    return tuple(
        LegendSection(pane, column.label, column.glyphs, column.description)
        for column in columns
    )


LEGEND: tuple[LegendSection, ...] = (
    LegendSection(
        STATUS_BAR_LABEL,
        "freshness",
        TOTALS_FRESHNESS_LEGEND,
        "one aggregate mark covers both exact open totals; - means a total is "
        "not available",
    ),
    *column_sections(SESSIONS_PANE_LABEL, SESSION_COLUMNS),
    *column_sections(WORKTREES_PANE_LABEL, WORKTREE_COLUMNS),
    LegendSection(
        WORKTREES_PANE_LABEL, WORKTREE_ACTIONS_SECTION, (), WORKTREE_ACTIONS_NOTE
    ),
    *column_sections(BRANCHES_PANE_LABEL, BRANCH_COLUMNS),
    *column_sections(PULL_REQUESTS_PANE_LABEL, PULL_REQUEST_COLUMNS),
    # Every Issue table column, chosen or not: the Legend is where a person
    # learns what a column they have not shown would tell them.
    *column_sections(ISSUE_PANE_LABEL, COLUMN_SPECS),
    LegendSection(
        ISSUE_PANE_LABEL,
        ISSUE_COLUMNS_SECTION,
        issue_cells.LEGEND_SORT,
        ISSUE_COLUMNS_NOTE,
    ),
    LegendSection(RELATED_ROWS_LABEL, RELATED_ROWS_SECTION, (), RELATED_ROWS_NOTE),
    LegendSection(DIAGNOSTICS_LABEL, "severity", alerts.LEGEND),
)


@dataclass(frozen=True, slots=True)
class KeyGroup:
    """The keys one screen or widget binds, named for where they are pressed."""

    label: str
    bindings: tuple[BindingType, ...]
    include_hidden: bool = False


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
    """Explain every column, Glyph and key binding without leaving the keyboard."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
    ]

    def __init__(self, keys: Sequence[KeyGroup]) -> None:
        # The caller supplies the keys to list: the dashboard's live on the
        # DashboardScreen, which this module must not import.
        super().__init__()
        self.legend_keys = tuple(keys)

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
            for index, group in enumerate(self.legend_keys):
                yield Static(
                    f"{KEYS_LABEL} · {group.label}",
                    classes="legend-heading",
                    id=f"legend-keys-heading-{index}",
                )
                yield Static(
                    self.keys_text(group),
                    classes="legend-section legend-keys",
                    id=f"legend-keys-{index}",
                )

    def keys_text(self, group: KeyGroup) -> Text:
        """The group's documented bindings, including hidden keys when requested."""
        bindings = list(Binding.make_bindings(group.bindings))
        if not group.include_hidden:
            bindings = [binding for binding in bindings if binding.show]
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
