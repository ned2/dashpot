from __future__ import annotations

import pytest

from dashpot.core.json_records import (
    HookRecordError,
    optional_string,
    require_harness,
    require_string,
)


def test_a_missing_hook_input_string_names_the_input() -> None:
    assert require_string("s1", "session_id") == "s1"

    with pytest.raises(HookRecordError, match="non-empty session_id"):
        require_string("", "session_id")


def test_an_optional_string_reads_only_non_empty_strings() -> None:
    assert optional_string("main") == "main"
    assert optional_string("") is None
    assert optional_string(3) is None


def test_a_hook_input_harness_must_be_a_supported_one() -> None:
    assert require_harness("claude-code") == "claude-code"

    with pytest.raises(HookRecordError, match="unsupported harness: 'cursor'"):
        require_harness("cursor")
    with pytest.raises(HookRecordError, match="non-empty harness"):
        require_harness(None)
