from __future__ import annotations

from dashpot.spread_table import proportional_shares, spread_widths


def test_shares_follow_the_weights_and_sum_exactly() -> None:
    assert proportional_shares(10, [1, 1, 3, 5]) == [1, 1, 3, 5]
    assert proportional_shares(5, [2, 2, 2]) == [2, 2, 1]
    assert proportional_shares(7, [0, 0, 0]) == [3, 2, 2]
    assert proportional_shares(0, [3, 4]) == [0, 0]
    assert proportional_shares(9, []) == []
    # A zero weight beside real ones takes nothing.
    assert proportional_shares(10, [0, 1, 4]) == [0, 2, 8]


def test_widths_keep_the_content_and_spread_only_the_surplus() -> None:
    # 40 cells, three columns of 1, 5 and 14 with padding 2 each: 26 used.
    assert spread_widths(40, [1, 5, 14], [1, 5, 14], padding=2) == [2, 8, 24]
    # An icon column with weight 0 keeps its width; the rest share the 14.
    assert spread_widths(40, [1, 5, 14], [0, 5, 14], padding=2) == [1, 9, 24]
    # Content that does not fit is left to the table to scroll.
    assert spread_widths(20, [1, 5, 14], [1, 5, 14], padding=2) == [None] * 3
    assert spread_widths(26, [1, 5, 14], [1, 5, 14], padding=2) == [None] * 3
