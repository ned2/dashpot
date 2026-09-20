"""The pane-height arithmetic, exercised without an App or a widget."""

from __future__ import annotations

from dashpot.ui.pane_layout import (
    EMPTY_PANE_HEIGHT,
    PANE_CHROME,
    content_height_wish,
    fit_panes,
    pane_wish,
)

VISIBLE_ROW_LIMIT = 8


def test_an_empty_pane_wishes_for_its_frame_and_message_line() -> None:
    assert pane_wish(0) == EMPTY_PANE_HEIGHT


def test_a_pane_with_records_wishes_for_chrome_records_and_a_scrollbar_row() -> None:
    assert pane_wish(1) == PANE_CHROME + 1 + 1
    assert pane_wish(12) == PANE_CHROME + 12 + 1


def test_a_bounded_pane_never_wishes_for_a_record_beyond_its_limit() -> None:
    assert (
        pane_wish(50, visible_row_limit=VISIBLE_ROW_LIMIT)
        == PANE_CHROME + VISIBLE_ROW_LIMIT
    )


def test_a_bounded_complete_inventory_reserves_a_scrollbar_line() -> None:
    assert (
        content_height_wish(VISIBLE_ROW_LIMIT, VISIBLE_ROW_LIMIT)
        == VISIBLE_ROW_LIMIT + 1
    )


def test_filter_controls_join_a_panes_wish_but_disappear_when_it_collapses() -> None:
    wishes = (pane_wish(0, controls_height=3), pane_wish(8))

    assert wishes[0] == EMPTY_PANE_HEIGHT + 3
    assert fit_panes(14, 6, wishes, controls_heights=(3, 0)) == (0, 1)


def test_empty_panes_keep_their_message_line_with_height_to_spare() -> None:
    wishes = (pane_wish(0), pane_wish(0), pane_wish(0))

    assert fit_panes(30, 6, wishes) == (1, 1, 1)


def test_zero_body_height_collapses_every_pane() -> None:
    wishes = (pane_wish(2), pane_wish(2), pane_wish(2))

    assert fit_panes(0, 6, wishes) == (0, 0, 0)


def test_a_full_pane_is_capped_with_its_scrollbar_spare_row() -> None:
    wishes = (
        pane_wish(1),
        pane_wish(50, visible_row_limit=VISIBLE_ROW_LIMIT),
        pane_wish(0),
    )

    assert fit_panes(32, 6, wishes) == (2, VISIBLE_ROW_LIMIT, 1)


def test_a_modest_wish_leaves_its_share_to_the_panes_that_want_more() -> None:
    # An even split of the 34 spare rows would starve the two full panes;
    # the empty pane's unused share flows to them instead.
    wishes = (pane_wish(0), pane_wish(50), pane_wish(50))

    assert fit_panes(40, 6, wishes) == (1, 11, 11)


def test_caps_follow_the_order_of_the_wishes_not_the_grant_order() -> None:
    # The smaller second pane is granted first, but its cap comes back in
    # the caller's pane order.
    wishes = (pane_wish(50), pane_wish(0))

    assert fit_panes(20, 6, wishes) == (10 - PANE_CHROME, 1)


def test_the_issue_table_minimum_squeezes_panes_to_bare_frames() -> None:
    wishes = (pane_wish(50), pane_wish(50), pane_wish(50))

    assert fit_panes(14, 6, wishes) == (0, 0, 0)


def test_equal_wishes_split_a_constrained_height_first_pane_last() -> None:
    # Ties are granted in pane order (stable sort), so the first pane takes
    # the floor share and the remainder accrues to the later grants.
    wishes = (pane_wish(50), pane_wish(50), pane_wish(50))

    assert fit_panes(32, 6, wishes) == (4, 5, 5)
