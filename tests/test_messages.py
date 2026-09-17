"""The dashboard's off-loop messages are dataclasses Textual can dispatch."""

from __future__ import annotations

from dashpot.ui.messages import FetchFinished, TotalsFinished


def test_messages_carry_their_payload_and_textual_message_state() -> None:
    failed = FetchFinished("project:alpha", error="no remote")
    assert (failed.project_id, failed.report, failed.error) == (
        "project:alpha",
        None,
        "no remote",
    )
    # Textual dispatches by the handler name it derives from the class.
    assert FetchFinished.handler_name == "on_fetch_finished"
    assert failed.bubble
    # Message state is initialised, so the message can be posted and stopped.
    assert failed.time > 0
    assert failed.stop() is failed


def test_messages_are_compared_by_identity_not_payload() -> None:
    first = TotalsFinished("issues")
    second = TotalsFinished("issues")
    assert first != second
    assert first == first
