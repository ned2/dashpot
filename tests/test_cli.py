from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock

import pytest

from dashpot import cli
from dashpot.agents import ProcessIdentity
from dashpot.hook import publish_from_stream
from dashpot.model import WorkspaceEntry, WorkspaceSnapshot


def test_workspace_argument_accepts_named_and_bare_paths(tmp_path: Path) -> None:
    named = cli.parse_workspace_argument(f"portable={tmp_path}")
    bare = cli.parse_workspace_argument(str(tmp_path))

    assert named == WorkspaceEntry("portable", str(tmp_path))
    assert bare == WorkspaceEntry(tmp_path.name, str(tmp_path))


@pytest.mark.parametrize("value", ["", "=", "name="])
def test_workspace_argument_rejects_incomplete_values(value: str) -> None:
    with pytest.raises(Exception, match="workspace must be"):
        cli.parse_workspace_argument(value)


def test_json_mode_prints_snapshot() -> None:
    collector = mock.Mock()
    collector.refresh.return_value = WorkspaceSnapshot("2026-08-25T01:00:00Z", 4, [])

    with mock.patch.object(cli, "create_collector", return_value=collector):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            result = cli.main(["--workspace", "/repo", "--json"])

    assert result == 0
    assert json.loads(stdout.getvalue())["elapsedMs"] == 4


def test_cli_reports_startup_error_without_traceback() -> None:
    with mock.patch.object(cli, "create_collector", side_effect=RuntimeError("bad config")):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = cli.main([])

    assert result == 2
    assert stderr.getvalue() == "dashpot: bad config\n"


def test_hook_stream_publishes_atomic_session_record(tmp_path: Path) -> None:
    event = {
        "session_id": "session-7",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
    }
    process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    with mock.patch(
        "dashpot.agents.state_directory", return_value=tmp_path / "state"
    ):
        with mock.patch(
            "dashpot.agents.nearest_codex_process", return_value=process
        ):
            publish_from_stream(io.StringIO(json.dumps(event)))

    record = json.loads((tmp_path / "state" / "session-7.json").read_text())
    assert record["state"] == "running"
    assert record["sessionProcess"]["pid"] == 42
