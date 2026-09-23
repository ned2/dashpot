from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from dashpot import hook
from dashpot.sessions.hook_publish import HookPublication
from dashpot.sessions.hook_records import HookRecordStore, build_hook_record
from dashpot.sessions.processes import AgentAncestry
from dashpot.sessions.session_matching import SessionEvidence
from dashpot.sessions.work_store import ActiveWork, SessionProcess
from factories import git, hook_record_document


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

    record = build_hook_record(event)

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

    def publish(event: dict[str, object], harness: str = "codex") -> HookPublication:
        published.append((event, harness))
        return HookPublication(tmp_path)

    monkeypatch.setattr(hook, "publish_hook_event", publish)
    event = {"session_id": "s1", "hook_event_name": "Stop", "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 0

    assert published == [(event, "claude-code")]
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


CONTINUED = ActiveWork(
    session_key="claude-code-session-abc",
    harness="claude-code",
    session_label="claude-code pid 8888",
    session_process=SessionProcess(pid=8888, started_at="Wed Aug 26 09:00:00 2026"),
    issue_id="I_observer",
    issue_reference="owner/repo#7",
    binding_provenance="explicit-reference",
    started_at="2026-08-25T02:00:00Z",
    working_directory="/work/repo",
    branch="7-observer",
    session_id="s1",
)


@pytest.mark.parametrize(
    ("event_name", "tells_the_agent"),
    [("SessionStart", True), ("PostToolUse", True), ("Stop", False)],
)
def test_a_continued_run_is_announced_to_the_resumed_agent(
    event_name: str,
    tells_the_agent: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def publish(event: dict[str, object], harness: str = "codex") -> HookPublication:
        return HookPublication(tmp_path, CONTINUED)

    monkeypatch.setattr(hook, "publish_hook_event", publish)
    event = {"session_id": "s1", "hook_event_name": event_name, "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 0

    out = capsys.readouterr().out
    if not tells_the_agent:
        # Claude Code reads no context from this event's output.
        assert out == ""
        return
    output = json.loads(out)["hookSpecificOutput"]
    assert output["hookEventName"] == event_name
    context = output["additionalContext"]
    assert "owner/repo#7" in context
    assert "/work/repo" in context
    assert "dashpot work stop" in context


def test_an_unsupported_event_is_a_non_blocking_hook_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = {"session_id": "s1", "hook_event_name": "Nope", "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 1
    assert "unsupported hook event" in capsys.readouterr().err


def test_an_occupied_destination_is_a_non_blocking_hook_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The store refuses to overwrite another Agent Session Identity's record
    # with a ``ValueError``; the harness must still see the one-line report.
    state_dir = tmp_path / "state"
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(state_dir))
    monkeypatch.setattr(
        "dashpot.sessions.hook_publish.observe_agent_ancestry",
        lambda harness: AgentAncestry(None, "isolated-namespace"),
    )
    state_dir.mkdir()
    # Only a record already sitting at this identity's own storage key can
    # occupy it, which no ``write`` produces, so the store seeds it directly.
    key = SessionEvidence("claude-code", "s1").storage_key()
    HookRecordStore(state_dir).replace(
        key, hook_record_document(tmp_path, "other", state="waiting")
    )
    event = {"session_id": "s1", "hook_event_name": "Stop", "cwd": str(tmp_path)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 1

    captured = capsys.readouterr()
    assert captured.err == (
        "dashpot Claude Code hook: hook destination is occupied by another "
        "Agent Session Identity\n"
    )
    assert captured.out == ""
