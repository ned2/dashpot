"""Pure height arithmetic for sharing the dashboard body between list panes.

The dashboard gathers the widget facts — the body's height, the Issue
table's stylesheet minimum, each pane's record count — and this module
decides how many records each pane may show. Nothing here touches a widget,
so the arithmetic is unit-testable without an App.
"""

from __future__ import annotations

from collections.abc import Sequence

# A list pane's blank line below it, its frame and its header, all of which
# come out of the height that pane's records get. The last pane's margin is
# the gap before the Issue table. An empty pane is its frame and one message
# line.
PANE_MARGIN = 1
PANE_FRAME = 2
COLLAPSED_PANE_HEIGHT = PANE_MARGIN + PANE_FRAME
PANE_HEADER = 1
PANE_CHROME = PANE_MARGIN + PANE_FRAME + PANE_HEADER
EMPTY_PANE_HEIGHT = PANE_MARGIN + PANE_FRAME + 1
# Header plus eight records; a longer list scrolls inside the pane.
DEFAULT_ROW_CAP = 8


def pane_wish(record_count: int, *, controls_height: int = 0) -> int:
    """The height a pane would take unconstrained: frame, header and records.

    A pane with records is granted one spare row for a horizontal scrollbar:
    its table is content-sized under the cap, so the row is only ever taken
    when wide records need it.
    """
    if not record_count:
        return EMPTY_PANE_HEIGHT + controls_height
    return PANE_CHROME + controls_height + min(record_count, DEFAULT_ROW_CAP) + 1


def fit_panes(
    body_height: int,
    minimum: int,
    wishes: Sequence[int],
    *,
    controls_heights: Sequence[int] | None = None,
) -> tuple[int, ...]:
    """Cap each pane's records to the height left after the fixed minimums.

    ``minimum`` is the height the Issue table keeps; whatever remains is
    shared between the panes, and a pane that wishes for less than its share
    (an empty one, or one with few records) leaves the rest to the panes
    that wish for more. The returned caps follow the order of ``wishes``; a
    cap of zero collapses a pane to a frame with a count.
    """
    heights = controls_heights or (0,) * len(wishes)
    if len(heights) != len(wishes):
        raise ValueError("Pane controls heights must match the pane wishes")
    # Every pane keeps its frame and margin even when no content fits. Share
    # what remains above those collapsed shapes; an atomic controls-and-row
    # minimum is either granted in full or left for another pane.
    remaining = max(
        0,
        body_height - minimum - COLLAPSED_PANE_HEIGHT * len(wishes),
    )
    desired = tuple(max(0, wish - COLLAPSED_PANE_HEIGHT) for wish in wishes)
    # A filtered empty pane's controls remain available when they fit, but
    # they yield to panes that have records when height is scarce.
    order = sorted(
        range(len(wishes)),
        key=lambda index: (
            heights[index] > 0 and wishes[index] == EMPTY_PANE_HEIGHT + heights[index],
            desired[index],
        ),
    )
    caps = [0] * len(wishes)
    for position, index in enumerate(order):
        controls_height = heights[index]
        empty = wishes[index] == EMPTY_PANE_HEIGHT + controls_height
        minimum_extra = controls_height + (1 if empty else PANE_HEADER + 1)
        if remaining < minimum_extra:
            continue
        share = remaining // (len(wishes) - position)
        granted = min(desired[index], max(minimum_extra, share))
        remaining -= granted
        if empty:
            caps[index] = 1
        else:
            row_cap = granted - PANE_HEADER - controls_height
            caps[index] = row_cap if row_cap >= 1 else 0
    return tuple(caps)
