"""Each Dashpot process opens its Event Log where, and at the level, it belongs."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from cyclopts import CycloptsError

from dashpot import cli, event_logs, hook
from dashpot.core import state_paths
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    EventLog,
    EventLogDestination,
    unrecorded_event_log,
    working_directory,
)
from dashpot.core.project_state import STATE_GITIGNORE
from dashpot.event_logs import (
    LEVEL_VARIABLE,
    event_level,
    open_event_log,
    process_identity,
    route_event_log,
)
from dashpot.github.github import GitHubRequestError
from dashpot.sessions.hook_publish import HookPublication
from factories import init_repository, write_project_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def written(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_bytes().splitlines()
    ]


# The fields every event carries in its envelope, whatever its body.
ENVELOPE = {
    "schema",
    "time",
    "dashpot.level",
    "service.instance.id",
    "dashpot.process.kind",
    "dashpot.agent_session.harness",
    "dashpot.agent_session.id",
    "dashpot.project.id",
    "dashpot.worktree.path",
    "dashpot.issue.id",
}


def body_of(event: dict[str, Any]) -> dict[str, Any]:
    """The fields of one written event that are its body, not its envelope."""
    return {key: value for key, value in event.items() if key not in ENVELOPE}


def settings(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


# --- Levels -----------------------------------------------------------------


def test_the_environment_decides_the_level_before_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = settings(tmp_path, "event_level = 'full'\n")

    monkeypatch.setenv(LEVEL_VARIABLE, " Off ")
    assert event_level(path) == "off"
    monkeypatch.setenv(LEVEL_VARIABLE, "verbose")
    assert event_level(path) == "full"
    monkeypatch.delenv(LEVEL_VARIABLE)
    assert event_level(path) == "full"
    assert event_level(tmp_path / "missing.toml") == "standard"


@pytest.mark.parametrize(
    "text",
    ["event_level = 'loud'\n", "not = [toml\n", "refresh_seconds = -1\n"],
    ids=["unknown-level", "malformed", "other-setting-invalid"],
)
def test_a_settings_file_that_fails_to_load_leaves_the_default_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.delenv(LEVEL_VARIABLE)

    assert event_level(settings(tmp_path, text)) == "standard"


# --- Routing ----------------------------------------------------------------


def test_a_process_in_a_configured_checkout_writes_to_its_state(
    tmp_path: Path,
) -> None:
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)
    (checkout / "src" / "deep").mkdir(parents=True)

    assert route_event_log(checkout / "src" / "deep") == EventLogDestination(
        checkout / ".dashpot" / "state" / "events", checkout=checkout
    )


def test_a_linked_worktree_is_its_own_checkout(tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: /somewhere/else\n")
    write_project_config(linked)

    assert route_event_log(linked) == EventLogDestination(
        linked / ".dashpot" / "state" / "events", checkout=linked
    )


@pytest.mark.parametrize("configured", [False, True])
def test_anything_else_writes_to_the_machine_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repository = init_repository(tmp_path / "repository")
    if configured:
        # A configuration above the checkout is not the checkout's.
        write_project_config(tmp_path)

    fallback = EventLogDestination(tmp_path / "state" / "dashpot" / "events")
    assert route_event_log(repository) == fallback
    assert route_event_log(None) == fallback
    assert route_event_log(tmp_path / "gone") == fallback


def test_a_process_identity_keeps_only_what_fits_its_field(tmp_path: Path) -> None:
    identity = process_identity(
        "hook:codex:Stop",
        worktree=Path("relative/path"),
        harness="codex",
        session_id="not a session id\nwith a newline",
    )

    assert (identity.kind, identity.harness) == ("hook:codex:Stop", "codex")
    assert identity.worktree is None
    assert identity.session_id is None
    assert len(identity.run_id) == 32
    assert process_identity("dashboard").run_id != identity.run_id


def test_a_log_opened_in_a_checkout_names_its_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)

    log = open_event_log("command:work-show", working_directory=checkout)
    log.start()
    log.close()

    events = checkout / ".dashpot" / "state"
    assert (events / ".gitignore").read_text() == STATE_GITIGNORE
    (start,) = written(events / "events")
    assert start["dashpot.worktree.path"] == str(checkout)
    assert start["process.working_directory"] == str(checkout)
    assert "dashpot.source.dirty" not in start


# --- The command line -------------------------------------------------------


@pytest.mark.parametrize(
    ("tokens", "kind", "subcommand"),
    [
        ([], DASHBOARD_KIND, None),
        (["--workspace", "/repo"], DASHBOARD_KIND, None),
        (["--json"], "command:observe", "observe"),
        (["--compact-json", "--workspace", "/repo"], "command:observe", "observe"),
        (["--help"], "command:help", "help"),
        (["--version"], "command:help", "help"),
        (["work", "show"], "command:work-show", "work show"),
        (["work", "start", "#7", "--timeout", "3"], "command:work-start", "work start"),
        (["worktree", "check", "--help"], "command:worktree-check", "worktree check"),
        (["no-such-command"], "command:observe", "observe"),
        (["--workspace"], "command:observe", "observe"),
    ],
)
def test_a_command_line_runs_as_its_process_kind(
    tokens: list[str], kind: str, subcommand: str | None
) -> None:
    assert cli.process_kind(tokens) == (kind, subcommand)


def test_a_command_records_its_start_and_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli, "show_issue_work", return_value=["no active Issue work"]
    ):
        assert cli.main(["work", "show"], event_log=EventLogDestination(tmp_path)) == 0
    assert cli.main(["work", "nope"], event_log=EventLogDestination(tmp_path)) == 2

    events = written(tmp_path)
    assert [
        (event["event.name"], event["dashpot.process.kind"]) for event in events
    ] == [
        ("process.start", "command:work-show"),
        ("process.end", "command:work-show"),
        ("process.start", "command:work"),
        ("process.end", "command:work"),
    ]
    assert events[0]["dashpot.subcommand"] == "work show"
    assert [event.get("process.exit.code") for event in events[1::2]] == [0, 2]
    assert events[0]["service.instance.id"] != events[2]["service.instance.id"]


def test_a_command_that_crashes_leaves_no_process_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    with (
        mock.patch.object(cli, "show_issue_work", side_effect=AssertionError),
        pytest.raises(AssertionError),
    ):
        cli.main(["work", "show"], event_log=EventLogDestination(tmp_path))

    assert [event["event.name"] for event in written(tmp_path)] == ["process.start"]
    assert cli._EVENT_LOG.get() is None


def test_an_interrupted_command_ends_with_its_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    with (
        mock.patch.object(cli, "show_issue_work", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit),
    ):
        cli.main(["work", "show"], event_log=EventLogDestination(tmp_path))

    assert [event.get("process.exit.code") for event in written(tmp_path)] == [
        None,
        130,
    ]


@pytest.mark.parametrize(("code", "status"), [(None, 0), (3, 3), ("a message", 1)])
def test_an_exit_status_follows_python(code: object, status: int) -> None:
    assert cli.exit_status(SystemExit(code)) == status


def test_the_dashboard_is_handed_the_command_lines_event_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    handed: list[EventLog | None] = []

    def app(*args: object, event_log: EventLog | None, **kwargs: object) -> mock.Mock:
        handed.append(event_log)
        return mock.Mock()

    with (
        mock.patch.object(cli, "create_collector"),
        mock.patch.object(cli, "create_query_sources", return_value={}),
        mock.patch.object(cli, "DashpotApp", side_effect=app),
    ):
        assert (
            cli.main(["--workspace", "/repo"], event_log=EventLogDestination(tmp_path))
            == 0
        )

    (log,) = handed
    assert log is not None and log.identity.kind == DASHBOARD_KIND
    assert log.path is not None and log.path.name.startswith(
        f"dashboard-{log.identity.run_id}-"
    )
    assert [event["event.name"] for event in written(tmp_path)] == [
        "process.start",
        "process.end",
    ]
    assert cli._EVENT_LOG.get() is None


# --- Hooks ------------------------------------------------------------------


def test_a_hook_records_its_harness_event_and_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)
    monkeypatch.setattr(
        hook,
        "publish_hook_event",
        lambda event, harness: HookPublication(tmp_path, state="waiting"),
    )
    event = {"session_id": "s-1", "hook_event_name": "Stop", "cwd": str(checkout)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 0

    start, outcome, end = written(checkout / ".dashpot" / "state" / "events")
    assert start["dashpot.process.kind"] == "hook:claude-code:Stop"
    assert start["dashpot.agent_session.harness"] == "claude-code"
    assert start["dashpot.agent_session.id"] == "s-1"
    assert start["process.working_directory"] == str(checkout)
    assert body_of(outcome) == {
        "event.name": "hook.outcome",
        "dashpot.hook.event": "Stop",
        "dashpot.outcome.result": "succeeded",
        "dashpot.agent_session.state": "waiting",
        "dashpot.work_store.change": "unchanged",
    }
    assert outcome["dashpot.agent_session.id"] == "s-1"
    assert end["process.exit.code"] == 0


def test_a_hook_that_changed_an_agent_run_names_its_issue_from_then_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.setattr(
        hook,
        "publish_hook_event",
        lambda event, harness: HookPublication(
            tmp_path, state="ended", work="ended", issue_id="I_314"
        ),
    )
    event = {"session_id": "s-1", "hook_event_name": "SessionEnd"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.main(event_log=EventLogDestination(tmp_path / "events")) == 0

    start, outcome, end = written(tmp_path / "events")
    assert "dashpot.issue.id" not in start
    assert outcome["dashpot.work_store.change"] == "ended"
    assert outcome["dashpot.agent_session.state"] == "ended"
    assert outcome["dashpot.issue.id"] == end["dashpot.issue.id"] == "I_314"


@pytest.mark.parametrize(
    "stdin",
    ["not json", json.dumps(["an", "array"]), json.dumps({"hook_event_name": "a b"})],
)
def test_a_hook_that_fails_records_its_exit_and_still_reports_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stdin: str,
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))

    assert hook.main(event_log=EventLogDestination(tmp_path)) == 1

    reported = capsys.readouterr().err
    assert reported.startswith("dashpot Codex hook: ")
    start, outcome, end = written(tmp_path)
    assert start["dashpot.process.kind"] == "hook:codex"
    assert set(body_of(outcome)) == {
        "event.name",
        "dashpot.outcome.result",
        "error.type",
    }
    assert outcome["dashpot.outcome.result"] == "failed"
    assert outcome["error.type"] in {"JSONDecodeError", "HookRecordError"}
    # The line the harness read is never what the Event Log keeps.
    message = reported.removeprefix("dashpot Codex hook: ").strip()
    assert message not in "".join(path.read_text() for path in tmp_path.glob("*.jsonl"))
    assert end["process.exit.code"] == 1


def test_a_hook_whose_publish_fails_records_the_error_class_never_its_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    def refuse(event: object, harness: str) -> HookPublication:
        raise PermissionError(13, "Permission denied", "/secret/place")

    monkeypatch.setattr(hook, "publish_hook_event", refuse)
    event = {"session_id": "s-1", "hook_event_name": "PostToolUse"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.main(event_log=EventLogDestination(tmp_path)) == 1

    _, outcome, _ = written(tmp_path)
    assert body_of(outcome) == {
        "event.name": "hook.outcome",
        "dashpot.hook.event": "PostToolUse",
        "dashpot.outcome.result": "failed",
        "error.type": "EACCES",
    }
    text = "".join(path.read_text() for path in tmp_path.glob("*.jsonl"))
    assert "/secret/place" not in text
    assert "Permission denied" not in text


def test_a_hook_error_that_carries_a_code_is_recorded_by_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    def fail(event: object, harness: str) -> HookPublication:
        raise GitHubRequestError("github-timeout", "gh timed out for someone")

    monkeypatch.setattr(hook, "publish_hook_event", fail)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s"})))

    assert hook.main(event_log=EventLogDestination(tmp_path)) == 1

    _, outcome, _ = written(tmp_path)
    assert outcome["error.type"] == "github-timeout"
    assert "someone" not in "".join(p.read_text() for p in tmp_path.glob("*.jsonl"))


def test_a_hook_whose_event_log_cannot_be_written_says_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(
        hook, "publish_hook_event", lambda event, harness: HookPublication(tmp_path)
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s"})))

    assert hook.main(event_log=EventLogDestination(blocker / "events")) == 0

    assert capsys.readouterr() == ("", "")


# --- Isolation --------------------------------------------------------------


def test_the_suite_records_no_runtime_event_outside_its_own_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The autouse fixture keeps every process quiet, subprocesses included."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    before = sorted((REPOSITORY_ROOT / ".dashpot" / "state" / "events").glob("*"))

    cli.main(["work", "nope"])
    open_event_log(DASHBOARD_KIND, working_directory=REPOSITORY_ROOT).start()
    subprocess.run(
        [sys.executable, "-m", "dashpot.cli", "--version"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )

    assert sorted((REPOSITORY_ROOT / ".dashpot" / "state" / "events").glob("*")) == (
        before
    )
    assert not (tmp_path / "state").exists()
    assert event_logs.event_level() == "off"


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("darwin", Path("Library") / "Application Support" / "dashpot"),
        ("linux", Path(".local") / "state" / "dashpot"),
    ],
)
def test_the_machine_local_state_follows_the_platform_without_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, expected: Path
) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(state_paths.sys, "platform", platform)

    assert state_paths.machine_state_directory() == tmp_path / expected
    assert route_event_log(None) == EventLogDestination(tmp_path / expected / "events")


def test_a_working_directory_that_is_gone_has_no_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(Path, "cwd", mock.Mock(side_effect=FileNotFoundError))
    monkeypatch.setattr(
        event_logs, "configured_checkout", mock.Mock(side_effect=PermissionError)
    )

    assert working_directory() is None
    assert route_event_log(tmp_path) == EventLogDestination(
        tmp_path / "state" / "dashpot" / "events"
    )
    assert unrecorded_event_log()._facts_source().working_directory is None


def test_a_command_line_that_cannot_be_parsed_opens_no_dashboard() -> None:
    # Cyclopts parses leniently today; a stricter release must still leave
    # the usage error to dispatch rather than fail before it.
    with mock.patch.object(
        type(cli.app), "parse_commands", side_effect=CycloptsError(msg="bad")
    ):
        assert cli.process_kind([]) == ("command:observe", "observe")


def test_with_no_home_directory_a_hook_records_nowhere_and_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(LEVEL_VARIABLE)
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setattr(Path, "home", mock.Mock(side_effect=RuntimeError("no home")))
    monkeypatch.setattr(
        hook, "publish_hook_event", lambda event, harness: HookPublication(tmp_path)
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(tmp_path)})))

    assert event_level() == "standard"
    assert route_event_log(tmp_path) is None
    assert hook.main() == 0
    assert capsys.readouterr() == ("", "")


def test_a_symlinked_working_directory_routes_to_the_checkout_git_reports(
    tmp_path: Path,
) -> None:
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)
    link = tmp_path / "link"
    link.symlink_to(checkout)

    assert route_event_log(link) == EventLogDestination(
        checkout / ".dashpot" / "state" / "events", checkout=checkout
    )
