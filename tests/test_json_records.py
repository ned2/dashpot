from __future__ import annotations

import pytest

from dashpot.json_records import optional_string, require_field, require_string


def test_a_missing_hook_input_string_names_the_input() -> None:
    assert require_string("s1", "session_id") == "s1"

    with pytest.raises(RuntimeError, match="non-empty session_id"):
        require_string("", "session_id")


def test_a_missing_record_field_names_the_field() -> None:
    assert require_field({"cwd": "/repo"}, "cwd") == "/repo"

    with pytest.raises(ValueError, match="non-empty cwd"):
        require_field({"cwd": 3}, "cwd")


def test_an_optional_string_reads_only_non_empty_strings() -> None:
    assert optional_string("main") == "main"
    assert optional_string("") is None
    assert optional_string(3) is None
