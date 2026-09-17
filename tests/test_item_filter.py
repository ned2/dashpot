"""The lifecycle vocabulary the item-list filters and the source queries share."""

from __future__ import annotations

import pytest

from dashpot.ui.item_filter import LIFECYCLE_STATUSES, lifecycle_states, lifecycle_value


@pytest.mark.parametrize(
    ("states", "value"),
    [
        (frozenset({"open"}), "open"),
        (frozenset({"closed"}), "closed"),
        (frozenset({"open", "closed"}), "all"),
    ],
)
def test_lifecycle_value_and_states_round_trip(
    states: frozenset[str], value: str
) -> None:
    assert lifecycle_value(states) == value
    assert lifecycle_states(value) == states


def test_every_offered_status_selects_states_and_nothing_else_does() -> None:
    assert [value for _label, value in LIFECYCLE_STATUSES] == ["open", "closed", "all"]
    assert all(lifecycle_states(value) for _label, value in LIFECYCLE_STATUSES)
    assert lifecycle_states("draft") is None
    assert lifecycle_states(None) is None
