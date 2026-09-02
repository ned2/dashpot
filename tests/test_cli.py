from __future__ import annotations

import io
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import get_args
from unittest import mock

import pytest
from rich.console import Console

from dashpot import cli
from dashpot.errors import DashpotError
from dashpot.git import GitError
from dashpot.hook import publish_from_stream
from dashpot.integrate import INTEGRATIONS
from dashpot.issue_profile import IssueProfileError, conform_issue
from dashpot.issue_sources import IssueSourceRefreshError
from dashpot.local_markdown_issues import LocalMarkdownIssueError
from dashpot.model import (
    RepositoryAnchor,
    ResolvedProject,
    Workspace,
    WorkspaceSnapshot,
)
from dashpot.processes import AgentAncestry, ProcessIdentity
from dashpot.workspace import WorkspaceResolution
from dashpot.worktrees import RemovalObstacle, WorktreePlan, WorktreeRemovability
from factories import write_config_marker
from helpers import issue_payload


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
    collector.refresh.return_value = WorkspaceSnapshot(
        collected_at="2026-08-25T01:00:00Z", elapsed_ms=4, projects=[]
    )

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


@pytest.mark.parametrize(
    ("argv", "seam", "error"),
    [
        (["--json"], "create_collector", RuntimeError("bad config")),
        (["--json"], "create_collector", DashpotError("stated refusal")),
        (
            ["--json"],
            "create_collector",
            GitError(("rev-parse", "--show-toplevel"), Path("/r"), detail="no git"),
        ),
        (["issue", "show", "9"], "show_issue", IssueProfileError("Issue 9 incomplete")),
        (
            ["issue", "show", "9"],
            "show_issue",
            IssueSourceRefreshError("github-profile", "malformed Issue node"),
        ),
        (
            ["issue", "show", "9"],
            "show_issue",
            LocalMarkdownIssueError("malformed Local Issue document"),
        ),
        (
            ["issue", "show", "9"],
            "show_issue",
            IssueSourceRefreshError("gh-failed", "gh exited 1"),
        ),
        (
            ["work", "start", "9"],
            "start_issue_work",
            DashpotError("no supported agent session encloses this command"),
        ),
        (
            ["worktree", "check", "/nowhere"],
            "check_worktree",
            RuntimeError("/nowhere is not a Worktree"),
        ),
    ],
)
def test_every_error_family_is_one_line_and_exits_two(
    argv: list[str],
    seam: str,
    error: Exception,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The contract stated by DashpotError and README: one ``dashpot:`` line
    # on stderr, nothing on stdout, exit 2, no traceback — per error family.
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(cli, seam, side_effect=error):
        assert cli.main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"dashpot: {error}\n"


def test_hook_stream_publishes_atomic_session_record(tmp_path: Path) -> None:
    event = {
        "session_id": "session-7",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
    }
    process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    with (
        mock.patch(
            "dashpot.hook_records.state_directory", return_value=tmp_path / "state"
        ),
        mock.patch(
            "dashpot.hook_records.observe_agent_ancestry",
            return_value=AgentAncestry(("codex", process)),
        ),
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


def test_issue_show_prints_lines_or_the_issue_profile_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = issue_payload(
        id="I_35",
        number=35,
        reference="ned2/dashpot#35",
        title="Worktree protocol",
        state="open",
        stateReason=None,
        location={
            "kind": "github",
            "url": "https://github.com/ned2/dashpot/issues/35",
        },
    )
    issue = conform_issue(payload)

    with mock.patch.object(cli, "show_issue", return_value=issue) as show:
        assert cli.main(["issue", "show", "35"]) == 0
    show.assert_called_once_with(Path.cwd().resolve(), "35", timeout=10.0)
    lines = capsys.readouterr().out
    assert "ned2/dashpot#35: Worktree protocol" in lines
    assert "location: https://github.com/ned2/dashpot/issues/35" in lines

    with mock.patch.object(cli, "show_issue", return_value=issue):
        assert cli.main(["issue", "show", "#35", "--json", "--timeout", "2"]) == 0
    # The wire payload pins the JSON contract independently of the model's
    # own dump: camelCase keys and explicit nulls, exactly as the fixture.
    assert json.loads(capsys.readouterr().out) == payload

    with mock.patch.object(
        cli, "show_issue", side_effect=RuntimeError("did not match an Issue")
    ):
        assert cli.main(["issue", "show", "99"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "dashpot: did not match an Issue\n"


PLAN = WorktreePlan(
    issue_id="I_35",
    issue_reference="ned2/dashpot#35",
    path="/w/dashpot.worktrees/35-worktree-protocol",
    branch="35-worktree-protocol",
    base_ref="refs/remotes/origin/main",
    base_source="origin/HEAD",
    base_commit="e319d3c",
    worktree_root="/w/dashpot.worktrees",
    worktree_root_source="default-sibling",
    dry_run=False,
    created=True,
)


def test_worktree_create_dispatches_every_option_and_prints_the_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(cli, "create_issue_worktree", return_value=PLAN) as create:
        assert (
            cli.main(
                [
                    "worktree",
                    "create",
                    "35",
                    "--base",
                    "main",
                    "--branch",
                    "35-alt",
                    "--worktree-root",
                    "/w",
                    "--dry-run",
                    "--timeout",
                    "3",
                ]
            )
            == 0
        )
    create.assert_called_once_with(
        Path.cwd().resolve(),
        "35",
        base="main",
        branch="35-alt",
        worktree_root_option=Path("/w"),
        dry_run=True,
        timeout=3.0,
    )
    out = capsys.readouterr().out
    assert out.startswith("created Worktree /w/dashpot.worktrees/35-worktree-protocol")
    assert "base: refs/remotes/origin/main at e319d3c (from origin/HEAD)" in out
    assert "worktree root: /w/dashpot.worktrees (from default-sibling)" in out


def test_worktree_create_refusal_exits_2_in_both_output_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    refused = replace(
        PLAN, created=False, refusals=("Branch 35-worktree-protocol already exists",)
    )

    with mock.patch.object(cli, "create_issue_worktree", return_value=refused):
        assert cli.main(["worktree", "create", "35"]) == 2
    captured = capsys.readouterr()
    assert (
        captured.err == "dashpot: refused: Branch 35-worktree-protocol already exists\n"
    )
    assert captured.out.startswith("refused Worktree ")

    with mock.patch.object(cli, "create_issue_worktree", return_value=refused):
        assert cli.main(["worktree", "create", "35", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["created"] is False
    assert payload["refusals"] == ["Branch 35-worktree-protocol already exists"]
    assert payload["baseCommit"] == "e319d3c"


def test_worktree_check_dispatches_and_prints_the_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    report = WorktreeRemovability(
        path="/w/dashpot.worktrees/35-worktree-protocol",
        branch="35-worktree-protocol",
        head="e319d3c",
        role="linked",
        removable=False,
        obstacles=(
            RemovalObstacle(
                "dirty", "1 changed path", "git worktree remove --force /w/x"
            ),
        ),
        remove_commands=("git worktree remove /w/x",),
    )

    with mock.patch.object(cli, "check_worktree", return_value=report) as check:
        assert cli.main(["worktree", "check", "/w/x"]) == 0
    check.assert_called_once_with(Path.cwd().resolve(), Path("/w/x"), timeout=10.0)
    out = capsys.readouterr().out
    assert "is not removable:" in out
    assert "- dirty: 1 changed path -> git worktree remove --force /w/x" in out

    with mock.patch.object(cli, "check_worktree", return_value=report):
        assert cli.main(["worktree", "check", "/w/x", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["removable"] is False
    assert payload["obstacles"][0]["kind"] == "dirty"


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
        (["issue", "show"], "REFERENCE requires an argument"),
        (["worktree", "create"], "REFERENCE requires an argument"),
        (["worktree", "check"], "PATH requires an argument"),
        (["worktree", "create", "35", "--no-dry-run"], "Unknown option: --no-dry-run"),
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
    for command in ("init", "integrate", "issue", "work", "worktree"):
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

    create = help_text(["worktree", "create", "--help"])
    assert "Usage: dashpot worktree create [OPTIONS] REFERENCE" in create
    for option in ("--base", "--branch", "--worktree-root", "--dry-run", "--json"):
        assert option in create
    assert "Usage: dashpot issue show [OPTIONS] REFERENCE" in help_text(
        ["issue", "show", "--help"]
    )
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
