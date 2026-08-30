from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from dashpot import hook


@pytest.mark.parametrize(
    ("entry_point", "label"),
    [(hook.main, "Codex"), (hook.claude_code_main, "Claude Code")],
)
def test_a_publish_failure_is_a_non_blocking_hook_exit(
    entry_point: Callable[[], int],
    label: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Exit code 2 would tell Claude Code to block the action and feed stderr
    # back to the model; a failed observation must never do that.
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))

    assert entry_point() == 1

    captured = capsys.readouterr()
    assert captured.err.startswith(f"dashpot {label} hook: ")
    assert captured.out == ""


def test_an_unsupported_event_is_a_non_blocking_hook_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = {"session_id": "s1", "hook_event_name": "Nope", "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 1
    assert "unsupported hook event" in capsys.readouterr().err
