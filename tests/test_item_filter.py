"""The lifecycle vocabulary the item-list filters and the source queries share."""

from __future__ import annotations

import pytest

from dashpot.ui.item_filter import (
    ISSUE_LIFECYCLE_STATUSES,
    LIFECYCLE_STATUSES,
    issue_lifecycle,
    lifecycle_states,
    lifecycle_value,
    next_status,
)


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


def test_issues_add_ready_to_the_lifecycle_they_offer() -> None:
    assert [value for _label, value in ISSUE_LIFECYCLE_STATUSES] == [
        "open",
        "ready",
        "closed",
        "all",
    ]
    assert all(
        issue_lifecycle(value) == value for _label, value in ISSUE_LIFECYCLE_STATUSES
    )
    assert issue_lifecycle("draft") is None
    assert issue_lifecycle(None) is None
    # Ready is an Issue lifecycle only.
    assert lifecycle_states("ready") is None


def test_next_status_walks_the_offered_choices_and_wraps() -> None:
    walked = ["open"]
    for _ in ISSUE_LIFECYCLE_STATUSES:
        walked.append(next_status(ISSUE_LIFECYCLE_STATUSES, walked[-1]))
    assert walked == ["open", "ready", "closed", "all", "open"]
    assert next_status(LIFECYCLE_STATUSES, "closed") == "all"
    assert next_status(LIFECYCLE_STATUSES, "draft") == "open"
