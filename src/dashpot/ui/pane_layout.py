"""Pure height arithmetic for fitting list panes within a Peer Screen.

The owning Peer Screen gathers the widget facts — the body's height, any
flexible table's stylesheet minimum, each pane's record count — and this module
decides how many records each pane may show. Nothing here touches a widget,
so the arithmetic is unit-testable without an App.
"""

from __future__ import annotations

from collections.abc import Sequence

# A list pane's top gutter, its frame and its header all come out of the height
# that pane's records get. The first gutter separates the Peer Status Bar;
# every later pane's gutter separates it from its predecessor. An empty pane is
# its gutter, frame and one message line.
PANE_MARGIN = 1
PANE_FRAME = 2
COLLAPSED_PANE_HEIGHT = PANE_MARGIN + PANE_FRAME
PANE_HEADER = 1
PANE_CHROME = PANE_MARGIN + PANE_FRAME + PANE_HEADER
EMPTY_PANE_HEIGHT = PANE_MARGIN + PANE_FRAME + 1


def content_height_wish(record_count: int, visible_row_limit: int | None = None) -> int:
    """The content lines a pane can use for its records or empty message.

    A non-empty pane reserves one line for a possible horizontal scrollbar
    when doing so cannot expose a record beyond its declared limit. The
    allowance lets every eligible record remain visible at narrow widths
    without measuring reactive scrollbar state in the height allocator.
    """
    if not record_count:
        return 1
    visible_records = (
        record_count
        if visible_row_limit is None
        else min(record_count, visible_row_limit)
    )
    scrollbar_allowance = int(
        visible_row_limit is None or record_count <= visible_row_limit
    )
    return visible_records + scrollbar_allowance


def pane_wish(
    record_count: int,
    *,
    controls_height: int = 0,
    visible_row_limit: int | None = None,
) -> int:
    """The height a pane would take unconstrained: frame, header and records.

    A pane with records may ask for one spare horizontal-scrollbar row when
    ``content_height_wish`` can grant it without breaking a record limit.
    """
    if not record_count:
        return EMPTY_PANE_HEIGHT + controls_height
    return (
        PANE_CHROME
        + controls_height
        + content_height_wish(record_count, visible_row_limit)
    )


def fit_panes(
    body_height: int,
    minimum: int,
    wishes: Sequence[int],
    *,
    controls_heights: Sequence[int] | None = None,
) -> tuple[int, ...]:
    """Cap each pane's records to the height left after the fixed minimums.

    ``minimum`` is the height a flexible table keeps; whatever remains is
    shared between the panes, and a pane that wishes for less than its share
    (an empty one, or one with few records) leaves the rest to the panes
    that wish for more. The returned content-height caps follow the order of
    ``wishes``; a cap of zero collapses a pane to a frame with a count. A cap
    counts a horizontal scrollbar when the table needs one, so it is not
    necessarily the number of visible records.
    """
    heights = controls_heights or (0,) * len(wishes)
    if len(heights) != len(wishes):
        raise ValueError("Pane controls heights must match the pane wishes")
    # Every pane keeps its frame and top gutter even when no content fits. Share
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
            content_height_cap = granted - PANE_HEADER - controls_height
            caps[index] = content_height_cap if content_height_cap >= 1 else 0
    return tuple(caps)
