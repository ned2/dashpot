"""The Issue table's rendered values: cell types, Glyphs and chip formatting.

Everything here turns an Issue Profile fact into what a cell shows — a
coloured state block, a label chip, a date — while retaining the domain
value behind the text, which ``issue_list`` derives the same way when it
orders a Query Page. The column catalogue and the view state that arrange
these cells live in ``issue_table``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal, Self

from rich.text import Text

from .glyphs import ACTIVITY_COLUMN_GLYPH, SESSION_STATE_GLYPHS, Glyph
from .issue_list import (
    PRIORITY_BY_LABEL,
    PriorityLevel,
    SortValue,
    is_priority_label,
    issue_priority_label,
)
from .issue_profile import IssueProfile
from .model import IssueActivity, ProjectObservation, RunState

IssueStateKind = Literal[
    "open",
    "completed",
    "not-planned",
    "duplicate",
]

GITHUB_ISSUE_STATE_COLORS: dict[IssueStateKind, tuple[str, str]] = {
    "open": ("#1f883d", "#238636"),
    "completed": ("#8250df", "#8957e5"),
    "not-planned": ("#59636e", "#656c76"),
    "duplicate": ("#59636e", "#656c76"),
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


class IssueTableCell(str):
    """A rendered table value that retains the domain value behind its text."""

    sort_value: SortValue

    def __new__(cls, text: str, sort_value: SortValue) -> Self:
        cell = super().__new__(cls, text)
        cell.sort_value = sort_value
        return cell


class AgentStateCell(Text):
    """Retain the aggregate Agent Run state alongside its shared Glyph."""

    __slots__ = ("sort_value",)
    sort_value: SortValue

    def __init__(self, state: RunState | None, *, dark: bool) -> None:
        glyph = AGENT_STATE_GLYPHS[state] if state is not None else None
        super().__init__(
            glyph.symbol if glyph is not None else "",
            style=glyph.style(dark=dark) if glyph is not None else "",
        )
        self.sort_value = (
            ("unknown", "waiting", "running").index(state) + 1 if state else 0
        )


class IssueStateCell(Text):
    """A semantic Issue-state value rendered as a colored block."""

    __slots__ = ("sort_value", "state_kind")

    sort_value: SortValue

    def __init__(self, state_kind: IssueStateKind, *, dark: bool) -> None:
        glyph = ISSUE_STATE_GLYPHS[state_kind]
        super().__init__(glyph.symbol, style=glyph.style(dark=dark))
        self.state_kind = state_kind
        self.sort_value = (
            "open",
            "completed",
            "not-planned",
            "duplicate",
        ).index(state_kind)


class IssueNumberCell(Text):
    """A right-aligned Issue Number that retains the number itself."""

    __slots__ = ("sort_value",)

    sort_value: SortValue

    def __init__(self, number: int) -> None:
        super().__init__(str(number), justify="right")
        self.sort_value = number


# Chip colour for labels whose tracker supplies no palette.
NEUTRAL_LABEL_COLOR = "6e7781"


class PriorityCell(Text):
    """An Issue's priority as a chip in the colour of the label that set it.

    An Issue without a recognized priority label renders empty and carries
    no priority: the table never invents a default.
    """

    __slots__ = ("priority", "sort_value")

    sort_value: SortValue

    def __init__(
        self,
        priority: PriorityLevel | None,
        label: str | None,
        colors: Mapping[str, str],
    ) -> None:
        super().__init__(no_wrap=True)
        self.priority = priority
        self.sort_value = None if priority is None else int(priority[1:])
        if priority is not None and label is not None:
            append_chip(self, priority, colors.get(label, NEUTRAL_LABEL_COLOR))


class LabelsCell(Text):
    """Issue labels rendered as coloured chips, like a tracker's feed."""

    __slots__ = ("labels", "sort_value")

    sort_value: SortValue

    def __init__(
        self,
        labels: tuple[str, ...],
        colors: Mapping[str, str],
    ) -> None:
        super().__init__(no_wrap=True)
        self.labels = labels
        self.sort_value = (
            tuple(label.casefold() for label in labels) if labels else None
        )
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
    IssueTableCell
    | AgentStateCell
    | IssueStateCell
    | IssueNumberCell
    | LabelsCell
    | PriorityCell
)


def text_cell(value: str) -> IssueTableCell:
    return IssueTableCell(value, value.casefold())


def comments_cell(activity: IssueActivity) -> IssueTableCell:
    count = activity.comment_count
    return IssueTableCell(str(count) if count else "-", count)


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


def optional_text_cell(value: str | None) -> IssueTableCell:
    if value is None:
        return IssueTableCell("-", None)
    return text_cell(value)


def date_cell(timestamp: str | None) -> IssueTableCell:
    if timestamp is None:
        return IssueTableCell("-", None)
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return IssueTableCell(instant.date().isoformat(), instant.timestamp())


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
    states: tuple[RunState, ...], *, dark: bool = True
) -> AgentStateCell:
    """Summarize bound Agent Runs with the shared Agent Session state Glyphs."""
    state = next((state for state in AGENT_STATE_GLYPHS if state in states), None)
    return AgentStateCell(state, dark=dark)
