"""The Issue table's rendered values: cell types, Glyphs and chip formatting.

Everything here turns an Issue Profile fact into what a cell shows — a
coloured state block, a label chip, a date. A plain text value is a ``str``;
a Rich cell carries its style, and where the text alone would not say what
it shows — an Issue state block, a priority chip, label chips — the typed fact
beside it. Nothing here orders rows: the source orders every Query Page.
The column catalogue and the view state that arrange these cells live in
``issue_table``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from rich.text import Text

from ..core.issue_profile import IssueProfile
from ..core.model import IssueActivity, ProjectObservation, SessionActivity
from ..issues.ordering import (
    PRIORITY_BY_LABEL,
    PriorityLevel,
    is_priority_label,
    issue_priority_label,
)
from .glyphs import (
    ACTIVITY_COLUMN_GLYPH,
    DONE_EMPHASIS_COLORS,
    NEUTRAL_EMPHASIS_COLORS,
    OPEN_EMPHASIS_COLORS,
    SESSION_STATE_GLYPHS,
    Glyph,
)

IssueStateKind = Literal[
    "open",
    "completed",
    "not-planned",
    "duplicate",
]

GITHUB_ISSUE_STATE_COLORS: dict[IssueStateKind, tuple[str, str]] = {
    "open": OPEN_EMPHASIS_COLORS,
    "completed": DONE_EMPHASIS_COLORS,
    "not-planned": NEUTRAL_EMPHASIS_COLORS,
    "duplicate": NEUTRAL_EMPHASIS_COLORS,
}
# One block per Issue state; the states differ only by colour, so the Legend
# shows every one of them.
ISSUE_STATE_GLYPHS: dict[IssueStateKind, Glyph] = {
    kind: Glyph("■", f"Issue {kind.replace('-', ' ')}", colors)
    for kind, colors in GITHUB_ISSUE_STATE_COLORS.items()
}
ISSUE_STATE_COLUMN_GLYPH = Glyph("◉", "the Issue state column")
AGENT_STATE_COLUMN_GLYPH = ACTIVITY_COLUMN_GLYPH
AGENT_STATE_GLYPHS = SESSION_STATE_GLYPHS
SORT_GLYPHS: dict[bool | None, Glyph] = {
    None: Glyph("↕", "a sortable column"),
    False: Glyph("↑", "sorted ascending"),
    True: Glyph("↓", "sorted descending"),
}
LEGEND_ISSUE_STATE = (ISSUE_STATE_COLUMN_GLYPH, *ISSUE_STATE_GLYPHS.values())
LEGEND_AGENT_STATE = (AGENT_STATE_COLUMN_GLYPH, *AGENT_STATE_GLYPHS.values())
LEGEND_SORT = tuple(SORT_GLYPHS.values())


class AgentStateCell(Text):
    """The aggregate Agent Run state as its shared Glyph."""

    __slots__ = ()

    def __init__(self, state: SessionActivity | None, *, dark: bool) -> None:
        glyph = AGENT_STATE_GLYPHS[state] if state is not None else None
        super().__init__(
            glyph.symbol if glyph is not None else "",
            style=glyph.style(dark=dark) if glyph is not None else "",
        )


class IssueStateCell(Text):
    """A semantic Issue-state value rendered as a colored block."""

    __slots__ = ("state_kind",)

    def __init__(self, state_kind: IssueStateKind, *, dark: bool) -> None:
        glyph = ISSUE_STATE_GLYPHS[state_kind]
        super().__init__(glyph.symbol, style=glyph.style(dark=dark))
        self.state_kind = state_kind


class IssueNumberCell(Text):
    """A right-aligned Issue Number."""

    __slots__ = ()

    def __init__(self, number: int) -> None:
        super().__init__(str(number), justify="right")


# Chip colour for labels whose tracker supplies no palette.
NEUTRAL_LABEL_COLOR = "6e7781"


class PriorityCell(Text):
    """An Issue's priority as a chip in the colour of the label that set it.

    An Issue without a recognized priority label renders empty and carries
    no priority: the table never invents a default.
    """

    __slots__ = ("priority",)

    def __init__(
        self,
        priority: PriorityLevel | None,
        label: str | None,
        colors: Mapping[str, str],
    ) -> None:
        super().__init__(no_wrap=True)
        self.priority = priority
        if priority is not None and label is not None:
            append_chip(self, priority, colors.get(label, NEUTRAL_LABEL_COLOR))


class LabelsCell(Text):
    """Issue labels rendered as coloured chips, like a tracker's feed."""

    __slots__ = ("labels",)

    def __init__(
        self,
        labels: tuple[str, ...],
        colors: Mapping[str, str],
    ) -> None:
        super().__init__(no_wrap=True)
        self.labels = labels
        append_label_chips(self, labels, colors)


def label_chips(labels: Sequence[str], colors: Mapping[str, str]) -> Text:
    """Labels as coloured chips that may wrap, for the Issue view."""
    return append_label_chips(Text(), tuple(labels), colors)


def append_label_chips(
    text: Text, labels: tuple[str, ...], colors: Mapping[str, str]
) -> Text:
    for index, label in enumerate(labels):
        if index:
            text.append(" ")
        append_chip(text, label, colors.get(label, NEUTRAL_LABEL_COLOR))
    if not labels:
        text.append("-")
    return text


def append_chip(text: Text, label: str, background: str) -> Text:
    """``label`` as a chip on ``background``, in the text that reads best on it."""
    return text.append(
        f" {label} ",
        style=f"{chip_foreground(background)} on #{background}",
    )


def issue_state_colors(*, dark: bool) -> dict[str, str]:
    """The Issue state colours as CSS variables (``$issue-open`` and so on)."""
    return {
        f"issue-{kind}": colors[1] if dark else colors[0]
        for kind, colors in GITHUB_ISSUE_STATE_COLORS.items()
    }


def issue_state_chip(issue: IssueProfile, label: str, *, dark: bool) -> Text:
    """``label`` as a chip whose background is the Issue's state colour.

    The colour is the same one the ISSUE pane border and the state column
    use, so the chip makes the border's meaning discoverable.
    """
    light_color, dark_color = GITHUB_ISSUE_STATE_COLORS[issue_state_kind(issue)]
    background = (dark_color if dark else light_color).lstrip("#")
    return Text(
        f" {label} ",
        style=f"{chip_foreground(background)} on #{background}",
        no_wrap=True,
    )


def chip_foreground(background: str) -> str:
    """Black or white text, whichever reads better on the chip colour."""
    red, green, blue = (
        int(background[index : index + 2], 16) / 255 for index in (0, 2, 4)
    )
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#000000" if luminance > 0.55 else "#ffffff"


TableCell = (
    str | AgentStateCell | IssueStateCell | IssueNumberCell | LabelsCell | PriorityCell
)


def comments_cell(activity: IssueActivity) -> str:
    count = activity.comment_count
    return str(count) if count else "-"


_NO_LABEL_COLORS: Mapping[str, str] = dict[str, str]()


def label_colors(project: ProjectObservation) -> Mapping[str, str]:
    if project.snapshot is None:
        return _NO_LABEL_COLORS
    return project.snapshot.label_colors


def labels_cell(issue: IssueProfile, project: ProjectObservation) -> LabelsCell:
    """The Issue's ordinary labels; a recognized priority label is the PRIORITY cell."""
    labels = tuple(label for label in issue.labels if not is_priority_label(label))
    return LabelsCell(labels, label_colors(project))


def priority_cell(issue: IssueProfile, project: ProjectObservation) -> PriorityCell:
    label = issue_priority_label(issue)
    priority = None if label is None else PRIORITY_BY_LABEL[label.casefold()]
    return PriorityCell(priority, label, label_colors(project))


def optional_text_cell(value: str | None) -> str:
    return "-" if value is None else value


def date_cell(timestamp: str | None) -> str:
    if timestamp is None:
        return "-"
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()


_CLOSED_STATE_KINDS: dict[str, IssueStateKind] = {
    "not-planned": "not-planned",
    "duplicate": "duplicate",
}


def issue_state_kind(issue: IssueProfile) -> IssueStateKind:
    if issue.state == "open":
        return "open"
    if issue.state_reason is None:
        return "completed"
    return _CLOSED_STATE_KINDS.get(issue.state_reason, "completed")


def issue_state_cell(issue: IssueProfile, *, dark: bool) -> IssueStateCell:
    return IssueStateCell(issue_state_kind(issue), dark=dark)


def agent_state_cell(
    states: tuple[SessionActivity, ...], *, dark: bool = True
) -> AgentStateCell:
    """Summarize bound Agent Runs with the shared Agent Session state Glyphs."""
    state = next((state for state in AGENT_STATE_GLYPHS if state in states), None)
    return AgentStateCell(state, dark=dark)
