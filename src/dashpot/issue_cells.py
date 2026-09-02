"""The Issue table's rendered values: cell types, Glyphs and chip formatting.

Everything here turns an Issue Profile fact into what a cell shows — a
coloured state block, a label chip, a relative age — while retaining the
domain value the cell sorts by. The column catalogue and the view-state
machine that arrange these cells live in ``issue_table``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Self, TypeAlias, cast

from rich.text import Text

from .glyphs import Glyph
from .issue_profile import IssueProfile
from .model import IssueActivity, ProjectObservation, RunState

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

# What a column yields for ordering: something Python can compare, or nothing.
SortValue: TypeAlias = "SupportsRichComparison | None"

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
AGENT_STATE_COLUMN_GLYPH = Glyph("◈", "the Agent Run state column")
# The column summarizes Issue work without exposing the number of Agent
# Runs: the liveliest state wins, ranked by the order here.
AGENT_STATE_GLYPHS: dict[RunState, Glyph] = {
    "running": Glyph("▶", "an Agent Run on this Issue is running"),
    "waiting": Glyph("Ⅱ", "an Agent Run on this Issue is waiting"),
    "unknown": Glyph("?", "an Agent Run on this Issue is in an unknown state"),
}
SORT_GLYPHS: dict[bool | None, Glyph] = {
    None: Glyph("↕", "a sortable column"),
    False: Glyph("↑", "sorted ascending"),
    True: Glyph("↓", "sorted descending"),
}
LEGEND_ISSUE_STATE = (ISSUE_STATE_COLUMN_GLYPH, *ISSUE_STATE_GLYPHS.values())
LEGEND_AGENT_STATE = (AGENT_STATE_COLUMN_GLYPH, *AGENT_STATE_GLYPHS.values())
LEGEND_SORT = tuple(SORT_GLYPHS.values())


class IssueTableCell(str):
    """A rendered table value that retains its domain sort value."""

    sort_value: SortValue

    def __new__(cls, text: str, sort_value: SortValue) -> Self:
        cell = super().__new__(cls, text)
        cell.sort_value = sort_value
        return cell


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
    """A right-aligned Issue Number that retains its numeric sort value."""

    __slots__ = ("sort_value",)

    sort_value: SortValue

    def __init__(self, number: int) -> None:
        super().__init__(str(number), justify="right")
        self.sort_value = number


# Chip colour for labels whose tracker supplies no palette.
NEUTRAL_LABEL_COLOR = "6e7781"

# The compact P-level a recognized priority label stands for.
PriorityLevel = Literal["P0", "P1", "P2", "P3"]


class PriorityCell(Text):
    """An Issue's priority as a chip in the colour of the label that set it.

    An Issue without a recognized priority label renders empty and sorts
    after every priority: the table never invents a default.
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
    IssueTableCell | IssueStateCell | IssueNumberCell | LabelsCell | PriorityCell
)


def cell_sort_value(value: object) -> SortValue:
    """The domain value a rendered cell orders by; other values compare as-is."""
    if isinstance(
        value,
        (IssueTableCell, IssueStateCell, IssueNumberCell, LabelsCell, PriorityCell),
    ):
        return value.sort_value
    return cast("SortValue", value)


def cells_match(left: TableCell, right: TableCell) -> bool:
    if isinstance(left, LabelsCell) and isinstance(right, LabelsCell):
        return left.labels == right.labels and left == right
    if isinstance(left, PriorityCell) and isinstance(right, PriorityCell):
        return left.priority == right.priority and left == right
    if isinstance(left, IssueStateCell) and isinstance(right, IssueStateCell):
        return (
            left.state_kind == right.state_kind
            and left.style == right.style
            and left.sort_value == right.sort_value
        )
    if left != right:
        return False
    if isinstance(left, IssueTableCell) and isinstance(right, IssueTableCell):
        return left.sort_value == right.sort_value
    return type(left) is type(right)


def text_cell(value: str) -> IssueTableCell:
    return IssueTableCell(value, value.casefold())


def issue_activity(issue: IssueProfile, project: ProjectObservation) -> IssueActivity:
    if project.snapshot is None:
        return IssueActivity()
    return project.snapshot.issue_activity.get(issue.id, IssueActivity())


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


def relative_age(timestamp: str | None, now: datetime) -> str | None:
    """A tracker-feed style age such as ``just now``, ``5m ago`` or ``3d ago``."""
    if not timestamp:
        return None
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


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


def agent_state_cell(states: tuple[RunState, ...]) -> IssueTableCell:
    """Summarize Issue work without exposing the number of Agent Runs."""
    for index, (state, glyph) in enumerate(AGENT_STATE_GLYPHS.items()):
        if state in states:
            return IssueTableCell(glyph.symbol, len(AGENT_STATE_GLYPHS) - index)
    return IssueTableCell("", 0)


PRIORITY_BY_LABEL: dict[str, PriorityLevel] = {
    "priority/p0": "P0",
    "priority/p1": "P1",
    "priority/p2": "P2",
    "priority/p3": "P3",
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}


def is_priority_label(label: str) -> bool:
    return label.casefold() in PRIORITY_BY_LABEL


def issue_priority_label(issue: IssueProfile) -> str | None:
    """The recognized label that sets the Issue's priority: the most urgent one."""
    labels = [label for label in issue.labels if is_priority_label(label)]
    if not labels:
        return None
    return min(labels, key=lambda label: PRIORITY_BY_LABEL[label.casefold()])


def issue_priority(issue: IssueProfile) -> PriorityLevel | None:
    """The Issue's compact priority, or nothing when no label declares one."""
    label = issue_priority_label(issue)
    return None if label is None else PRIORITY_BY_LABEL[label.casefold()]
