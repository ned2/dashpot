from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from dashpot import hook
from dashpot.hook_records import build_hook_record
from factories import git


def test_a_detached_head_still_records_the_repository_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(
        root,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "first",
    )
    git(root, "checkout", "-q", "--detach")
    event = {"session_id": "s1", "hook_event_name": "Stop", "cwd": str(root)}

    record = build_hook_record(event, environ={})

    # The root routes the record to the Project's own store; only the
    # branch name is genuinely unavailable.
    assert record["repositoryRoot"] == str(root.resolve())
    assert record["branch"] is None


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


def test_a_non_object_hook_input_is_a_non_blocking_hook_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('["not", "an", "object"]'))

    assert hook.main() == 1
    assert "hook input must be a JSON object" in capsys.readouterr().err


def test_a_published_event_is_a_clean_hook_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published: list[tuple[dict[str, object], str]] = []

    def publish(event: dict[str, object], harness: str = "codex") -> Path:
        published.append((event, harness))
        return tmp_path

    monkeypatch.setattr(hook, "publish_hook_event", publish)
    event = {"session_id": "s1", "hook_event_name": "Stop", "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 0

    assert published == [(event, "claude-code")]
    captured = capsys.readouterr()
    assert captured.err == ""
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
