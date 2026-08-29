from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import get_args
from unittest import mock

import pytest
from rich.console import Console

from dashpot import cli
from dashpot.agents import ProcessIdentity
from dashpot.hook import publish_from_stream
from dashpot.integrate import INTEGRATIONS
from dashpot.model import (
    RepositoryAnchor,
    ResolvedProject,
    Workspace,
    WorkspaceSnapshot,
)
from dashpot.workspace import WorkspaceResolution


def write_config_marker(root: Path) -> None:
    (root / ".dashpot").mkdir(exist_ok=True)
    (root / ".dashpot" / "config.json").write_text("{}")


def project(root: Path) -> ResolvedProject:
    return ResolvedProject(
        "project:test",
        "Test Project",
        "repository:test",
        ("test",),
        (str(root),),
        str(root),
    )


def test_workspace_argument_accepts_named_and_bare_paths(tmp_path: Path) -> None:
    named = cli.parse_workspace_argument(f"portable={tmp_path}")
    bare = cli.parse_workspace_argument(str(tmp_path))

    assert named == Workspace("portable", (RepositoryAnchor(str(tmp_path)),))
    assert bare == Workspace(tmp_path.name, (RepositoryAnchor(str(tmp_path)),))


def test_workspace_argument_infers_name_from_resolved_dot_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    workspace = cli.parse_workspace_argument(".")

    assert workspace == Workspace(tmp_path.name, (RepositoryAnchor(str(tmp_path)),))


@pytest.mark.parametrize("value", ["", "=", "name="])
def test_workspace_argument_rejects_incomplete_values(value: str) -> None:
    with pytest.raises(ValueError, match="workspace must be"):
        cli.parse_workspace_argument(value)


def test_no_argument_cli_defaults_to_configured_current_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config_marker(tmp_path)
    monkeypatch.chdir(tmp_path)
    options = cli.ObservationOptions()

    resolution = WorkspaceResolution([project(tmp_path)], [])
    with (
        mock.patch.object(cli, "worktree_root", return_value=tmp_path),
        mock.patch.object(cli, "load_workspaces") as load_workspaces,
        mock.patch.object(
            cli, "resolve_workspace_projects", return_value=resolution
        ) as resolve,
    ):
        collector = cli.create_collector(options)

    load_workspaces.assert_not_called()
    resolve.assert_called_once_with(
        [Workspace(tmp_path.name, (RepositoryAnchor(str(tmp_path)),))],
        timeout=10.0,
    )
    assert collector.projects == [project(tmp_path)]


def test_no_argument_cli_anchors_ephemeral_workspace_at_git_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    nested = project_root / "src" / "package"
    nested.mkdir(parents=True)
    write_config_marker(project_root)
    monkeypatch.chdir(nested)
    options = cli.ObservationOptions()
    resolution = WorkspaceResolution([project(project_root)], [])

    with (
        mock.patch.object(cli, "worktree_root", return_value=project_root),
        mock.patch.object(
            cli, "resolve_workspace_projects", return_value=resolution
        ) as resolve,
    ):
        collector = cli.create_collector(options)

    resolve.assert_called_once_with(
        [
            Workspace(
                project_root.name,
                (RepositoryAnchor(str(project_root)),),
            )
        ],
        timeout=10.0,
    )
    assert collector.projects == [project(project_root)]


def test_explicit_config_takes_precedence_over_current_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config_marker(tmp_path)
    configured = tmp_path / "configured"
    configured.mkdir()
    write_config_marker(configured)
    config = tmp_path / "workspaces.json"
    monkeypatch.chdir(tmp_path)
    options = cli.ObservationOptions(config=config)

    with (
        mock.patch.object(
            cli,
            "load_workspaces",
            return_value=[
                Workspace("configured", (RepositoryAnchor(str(configured)),))
            ],
        ) as load_workspaces,
        mock.patch.object(
            cli,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(configured)], []),
        ),
    ):
        collector = cli.create_collector(options)

    load_workspaces.assert_called_once_with(config)
    assert collector.projects == [project(configured)]


def test_explicit_workspace_takes_precedence_over_config(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "explicit"
    workspace.mkdir()
    write_config_marker(workspace)
    options = cli.ObservationOptions(
        workspaces=(Workspace("explicit", (RepositoryAnchor(str(workspace)),)),),
        config=tmp_path / "unused.json",
    )

    with (
        mock.patch.object(cli, "load_workspaces") as load_workspaces,
        mock.patch.object(
            cli,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(workspace)], []),
        ),
    ):
        collector = cli.create_collector(options)

    load_workspaces.assert_not_called()
    assert collector.projects == [project(workspace)]


def test_no_argument_cli_falls_back_to_standard_workspace_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured"
    configured.mkdir()
    write_config_marker(configured)
    config = tmp_path / "workspaces.json"
    monkeypatch.chdir(tmp_path)
    options = cli.ObservationOptions()

    with (
        mock.patch.object(cli, "default_workspace_config", return_value=config),
        mock.patch.object(
            cli,
            "load_workspaces",
            return_value=[
                Workspace("configured", (RepositoryAnchor(str(configured)),))
            ],
        ) as load_workspaces,
        mock.patch.object(
            cli,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(configured)], []),
        ),
    ):
        collector = cli.create_collector(options)

    load_workspaces.assert_called_once_with(config)
    assert collector.projects == [project(configured)]


def test_json_mode_prints_snapshot() -> None:
    collector = mock.Mock()
    collector.refresh.return_value = WorkspaceSnapshot("2026-08-25T01:00:00Z", 4, [])

    with (
        mock.patch.object(
            cli, "create_collector", return_value=collector
        ) as create_collector,
        mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
    ):
        result = cli.main(["--workspace", "/repo", "--json"])

    assert result == 0
    assert json.loads(stdout.getvalue())["elapsedMs"] == 4
    create_collector.assert_called_once_with(
        cli.ObservationOptions(
            workspaces=(Workspace("repo", (RepositoryAnchor("/repo"),)),)
        )
    )


def test_cli_reports_startup_error_without_traceback() -> None:
    with (
        mock.patch.object(
            cli, "create_collector", side_effect=RuntimeError("bad config")
        ),
        mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
    ):
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

    with (
        mock.patch("dashpot.agents.state_directory", return_value=tmp_path / "state"),
        mock.patch("dashpot.agents.nearest_harness_process", return_value=process),
    ):
        publish_from_stream(io.StringIO(json.dumps(event)))

    record = json.loads((tmp_path / "state" / "session-7.json").read_text())
    assert record["state"] == "running"
    assert record["sessionProcess"]["pid"] == 42


def test_unconfigured_repository_error_suggests_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    options = cli.ObservationOptions()
    missing = tmp_path / "nowhere" / "workspaces.json"

    with (
        mock.patch.object(cli, "worktree_root", return_value=tmp_path),
        mock.patch.object(cli, "default_workspace_config", return_value=missing),
        pytest.raises(RuntimeError, match="dashpot init"),
    ):
        cli.create_collector(options)


def test_init_command_prints_messages_and_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli, "initialize_project", return_value=["created config"]
    ) as init:
        code = cli.main(["init", "--markdown", "issues"])

    assert code == 0
    init.assert_called_once_with(
        Path.cwd().resolve(), markdown_path="issues", timeout=10.0
    )
    assert "created config" in capsys.readouterr().out


def test_init_command_reports_errors_like_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli,
        "initialize_project",
        side_effect=RuntimeError("already configured"),
    ):
        code = cli.main(["init"])

    assert code == 2
    assert "already configured" in capsys.readouterr().err


def test_work_start_dispatches_with_reference_and_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli, "start_issue_work", return_value=["started work on #7"]
    ) as start:
        code = cli.main(["work", "start", "#7"])

    assert code == 0
    start.assert_called_once_with(Path.cwd().resolve(), "#7", timeout=10.0)
    assert "started work on #7" in capsys.readouterr().out


def test_work_stop_and_show_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli, "stop_issue_work", return_value=["stopped work on #7"]
    ) as stop:
        assert cli.main(["work", "stop"]) == 0
    stop.assert_called_once_with(Path.cwd().resolve(), session_key=None)

    with mock.patch.object(
        cli, "stop_issue_work", return_value=["stopped orphaned work on #7"]
    ) as stop:
        assert cli.main(["work", "stop", "--session", "codex-42-abcd1234"]) == 0
    stop.assert_called_once_with(Path.cwd().resolve(), session_key="codex-42-abcd1234")

    with mock.patch.object(
        cli, "show_issue_work", return_value=["no active Issue work"]
    ) as show:
        assert cli.main(["work", "show"]) == 0
    show.assert_called_once_with(Path.cwd().resolve())

    output = capsys.readouterr().out
    assert "stopped work on #7" in output
    assert "no active Issue work" in output


def test_work_errors_are_reported_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli,
        "start_issue_work",
        side_effect=RuntimeError("no supported agent session"),
    ):
        code = cli.main(["work", "start", "#7"])

    assert code == 2
    assert "no supported agent session" in capsys.readouterr().err


def test_integrate_codex_dispatches_install_remove_and_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        cli, "install_integration", return_value=["installed hooks"]
    ) as install:
        assert cli.main(["integrate", "codex"]) == 0
    install.assert_called_once_with("codex")

    with mock.patch.object(
        cli, "remove_integration", return_value=["removed hooks"]
    ) as remove:
        assert cli.main(["integrate", "claude-code", "--remove"]) == 0
    remove.assert_called_once_with("claude-code")

    with mock.patch.object(
        cli, "integration_status", return_value=["installed in x"]
    ) as status:
        assert cli.main(["integrate", "claude-code", "--status"]) == 0
    status.assert_called_once_with("claude-code")

    output = capsys.readouterr().out
    assert "installed hooks" in output
    assert "removed hooks" in output
    assert "installed in x" in output


def test_integrate_errors_are_reported_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        cli,
        "install_integration",
        side_effect=RuntimeError("no Codex configuration directory"),
    ):
        code = cli.main(["integrate", "codex"])

    assert code == 2
    assert "no Codex configuration directory" in capsys.readouterr().err


def test_anchors_for_two_projects_are_refused_at_startup(tmp_path: Path) -> None:
    roots = []
    for name, project_id in (
        ("dashpot", "project:01947e42-3f67-7c38-a41c-218df18a169b"),
        ("other", "project:0195aaaa-1111-7c38-a41c-218df18a169b"),
    ):
        root = tmp_path / name
        (root / ".dashpot").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".dashpot" / "config.json").write_text(
            json.dumps(
                {
                    "projectId": project_id,
                    "displayLabel": name.title(),
                    "repositoryId": f"repository:{name}",
                    "issueSource": {"kind": "markdown", "path": "issues"},
                }
            )
        )
        roots.append(root)

    with (
        mock.patch.object(cli, "DashpotApp") as app,
        mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
    ):
        result = cli.main(
            ["--workspace", f"personal={roots[0]}", "--workspace", f"client={roots[1]}"]
        )

    assert result == 2
    message = stderr.getvalue()
    assert message.startswith("dashpot: Dashpot observes one Project per run")
    assert "2 Projects" in message
    assert str(roots[0].resolve()) in message
    assert str(roots[1].resolve()) in message
    app.assert_not_called()


def parse(argv: list[str]) -> dict[str, object]:
    _, bound, _ = cli.app.parse_args(argv, exit_on_error=False, print_error=False)
    bound.apply_defaults()
    return dict(bound.arguments)


def help_text(argv: list[str]) -> str:
    output = io.StringIO()
    console = Console(file=output, width=100, force_terminal=False, color_system=None)
    cli.app(argv, console=console, result_action="return_value")
    return output.getvalue()


def test_default_command_parses_every_observation_option(tmp_path: Path) -> None:
    bound = parse(
        [
            "--workspace",
            f"personal={tmp_path}",
            "--workspace",
            str(tmp_path / "clone"),
            "--config",
            "~/workspaces.json",
            "--timeout",
            "2.5",
            "--refresh-seconds",
            "0",
            "--state-dir",
            "/state",
            "--compact-json",
        ]
    )

    assert bound == {
        "workspace": [
            Workspace("personal", (RepositoryAnchor(str(tmp_path)),)),
            Workspace("clone", (RepositoryAnchor(str(tmp_path / "clone")),)),
        ],
        "config": Path("~/workspaces.json"),
        "timeout": 2.5,
        "refresh_seconds": 0.0,
        "state_dir": Path("/state"),
        "json_output": False,
        "compact_json": True,
    }


def test_default_command_defaults_match_observation_options() -> None:
    bound = parse([])

    assert bound["workspace"] is None
    assert bound["config"] is None
    assert bound["timeout"] == cli.ObservationOptions().timeout
    assert bound["refresh_seconds"] == cli.ObservationOptions().refresh_seconds
    assert bound["state_dir"] is None
    assert bound["json_output"] is False


def test_timeout_is_accepted_after_the_subcommand_it_applies_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(cli, "initialize_project", return_value=[]) as init:
        assert cli.main(["init", "--timeout", "5"]) == 0
    init.assert_called_once_with(Path.cwd().resolve(), markdown_path=None, timeout=5.0)

    with mock.patch.object(cli, "start_issue_work", return_value=[]) as start:
        assert cli.main(["work", "start", "12", "--timeout", "0.5"]) == 0
    start.assert_called_once_with(Path.cwd().resolve(), "12", timeout=0.5)


@pytest.mark.parametrize(
    ("argv", "diagnostic"),
    [
        (["--workspace", "name="], "workspace must be PATH or NAME=PATH"),
        (["--workspace", "="], "workspace must be PATH or NAME=PATH"),
        (["--timeout", "0"], 'Invalid value "0.0" for --timeout. Must be > 0.'),
        (["--timeout", "-1"], "Must be > 0."),
        (["--timeout", "soon"], 'unable to convert "soon" into float'),
        (["--refresh-seconds", "-1"], "Must be >= 0."),
        (["--no-json"], "Unknown option: --no-json"),
        (["--empty-workspace"], "Unknown option: --empty-workspace"),
        (["--timeout", "5", "init"], "Unused Tokens: ['init']"),
        (["--bogus"], "Unknown option: --bogus"),
        (["work", "start"], "REFERENCE requires an argument"),
        (["work", "bogus"], 'Unknown command "bogus"'),
        (["init", "--timeout", "0"], "Must be > 0."),
        (["integrate"], "HARNESS requires an argument"),
        (["integrate", "emacs"], 'Choose from: "codex", "claude-code"'),
        (
            ["integrate", "codex", "--status", "--remove"],
            "Mutually exclusive arguments: {--status, --remove}",
        ),
    ],
)
def test_invalid_input_fails_with_a_diagnostic_and_no_traceback(
    argv: list[str], diagnostic: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with mock.patch.object(cli, "create_collector") as create_collector:
        code = cli.main(argv)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("dashpot: ")
    # Rich wraps long diagnostics at the terminal width; compare the words.
    assert diagnostic in " ".join(captured.err.split())
    assert "Traceback" not in captured.err
    create_collector.assert_not_called()


def test_root_help_describes_the_command_hierarchy_and_options() -> None:
    text = help_text(["--help"])

    assert "Usage: dashpot COMMAND [OPTIONS]" in text
    assert "Passively observe Issues, repositories, and agent runs." in text
    for command in ("init", "integrate", "work"):
        assert f" {command} " in text
    for option in (
        "--workspace",
        "--config",
        "--timeout",
        "--refresh-seconds",
        "--state-dir",
        "--json",
        "--compact-json",
        "--version",
    ):
        assert option in text
    assert "[NAME=]PATH" in text
    assert "--no-json" not in text
    assert "--empty-workspace" not in text
    assert "[default: False]" not in text


def test_subcommand_help_pages_describe_their_arguments() -> None:
    work = help_text(["work", "--help"])
    assert "Usage: dashpot work COMMAND" in work
    for command in ("start", "stop", "show"):
        assert f" {command} " in work

    start = help_text(["work", "start", "--help"])
    assert "Usage: dashpot work start [OPTIONS] REFERENCE" in start
    assert "Issue Reference" in start
    assert "--timeout" in start

    stop = help_text(["work", "stop", "--help"])
    assert "--session" in stop
    assert "orphaned Agent Run" in stop

    init = help_text(["init", "--help"])
    assert "--markdown" in init
    assert "--timeout" in init

    integrate = help_text(["integrate", "--help"])
    assert "Usage: dashpot integrate [OPTIONS] HARNESS" in integrate
    assert "[choices: codex, claude-code]" in integrate
    assert "--status" in integrate
    assert "--remove" in integrate


def test_help_and_version_print_to_stdout_and_exit_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--help"]) == 0
    assert cli.main(["-h"]) == 0
    assert cli.main(["--version"]) == 0
    assert cli.main(["work"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("Usage: dashpot COMMAND [OPTIONS]") == 2
    assert "Usage: dashpot work COMMAND" in captured.out
    assert "0.1.0" in captured.out


def test_harness_choices_track_the_supported_integrations() -> None:
    assert set(get_args(cli.Harness)) == set(INTEGRATIONS)


def test_cli_module_no_longer_uses_argparse() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")

    assert "argparse" not in source
