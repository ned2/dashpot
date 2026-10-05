from __future__ import annotations

import io
import json
import runpy
import subprocess
from functools import partial
from pathlib import Path
from typing import Literal, get_args
from unittest import mock

import pytest
from rich.console import Console

from dashpot import cli, composition
from dashpot.cli import init as cli_init
from dashpot.cli import integrate as cli_integrate
from dashpot.cli import observe as cli_observe
from dashpot.cli import root as cli_root
from dashpot.cli import sources as cli_sources
from dashpot.cli import work as cli_work
from dashpot.cli import worktrees as cli_worktrees
from dashpot.core.command_outcomes import OutcomeNote
from dashpot.core.errors import DashpotError
from dashpot.core.event_log import EventLogDestination
from dashpot.core.git import GitError
from dashpot.core.issue_profile import IssueProfileError, conform_issue
from dashpot.core.model import WorkspaceSnapshot
from dashpot.core.working_directory import WorkingDirectoryError, current_directory
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.github.github import LatestRateLimit
from dashpot.hook import publish_from_stream
from dashpot.issues.issue_resolution import IssueResolutionError
from dashpot.issues.issue_sources import IssueSourceRefreshError
from dashpot.issues.local_markdown_issues import LocalMarkdownIssueError
from dashpot.project.init import InitError
from dashpot.project.project_config import ProjectConfigError
from dashpot.project.workspace import (
    RepositoryAnchor,
    ResolvedProject,
    Workspace,
    WorkspaceInventory,
    WorkspaceResolution,
)
from dashpot.queries.query_source import ProjectUnresolvedError, UnresolvedQuerySource
from dashpot.queries.source_queries import QUERY_SOURCE_KEYS, QueryRequest
from dashpot.repository.cleanup import (
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupError,
    CleanupPreview,
    CleanupReport,
    CleanupTarget,
    TargetResult,
    WorktreeCleanupRequest,
    inspect_cleanup,
    perform_cleanup,
    protection,
)
from dashpot.repository.worktrees.create import WorktreePlan
from dashpot.repository.worktrees.removability import (
    WorktreeRemovability,
    check_worktree,
)
from dashpot.sessions.hook_records import session_directory, state_directory
from dashpot.sessions.integrate import (
    INTEGRATIONS,
    CombinedStatus,
    HarnessOutcome,
    HarnessReport,
    IncompleteIntegrationError,
    IncompleteRemovalError,
    IntegrationError,
)
from dashpot.sessions.processes import AgentAncestry, ProcessIdentity
from dashpot.sessions.session_identity import IssueWorkError
from dashpot.ui import launch
from factories import git, init_repository, write_config_marker, write_project_config
from helpers import issue_payload, table_lookup
from test_cleanup import (
    CLAUDE,
    CLAUDE_CODE_STEPS,
    PARENT,
    SESSION,
    occupied_worktree,
    publish_subagent,
    sub_agent_worktrees,
)
from test_serialization import REMOVABILITY_KEYS


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
    named = cli_observe.parse_workspace_argument(f"portable={tmp_path}")
    bare = cli_observe.parse_workspace_argument(str(tmp_path))

    assert named == Workspace("portable", (RepositoryAnchor(str(tmp_path)),))
    assert bare == Workspace(tmp_path.name, (RepositoryAnchor(str(tmp_path)),))


def test_workspace_argument_infers_name_from_resolved_dot_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    workspace = cli_observe.parse_workspace_argument(".")

    assert workspace == Workspace(tmp_path.name, (RepositoryAnchor(str(tmp_path)),))


@pytest.mark.parametrize("value", ["", "=", "name=", "=/anchor", " =/anchor", "/"])
def test_workspace_argument_rejects_incomplete_values(value: str) -> None:
    with pytest.raises(ValueError, match="workspace must be"):
        cli_observe.parse_workspace_argument(value)


def test_no_argument_cli_defaults_to_configured_current_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config_marker(tmp_path)
    monkeypatch.chdir(tmp_path)
    options = composition.ObservationOptions()

    resolution = WorkspaceResolution([project(tmp_path)], [])
    with (
        mock.patch.object(composition, "worktree_root", return_value=tmp_path),
        mock.patch.object(composition, "load_workspaces") as load_workspaces,
        mock.patch.object(
            composition, "resolve_workspace_projects", return_value=resolution
        ) as resolve,
    ):
        collector = composition.create_collector(options)

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
    options = composition.ObservationOptions()
    resolution = WorkspaceResolution([project(project_root)], [])

    with (
        mock.patch.object(composition, "worktree_root", return_value=project_root),
        mock.patch.object(
            composition, "resolve_workspace_projects", return_value=resolution
        ) as resolve,
    ):
        collector = composition.create_collector(options)

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
    options = composition.ObservationOptions(config=config)

    with (
        mock.patch.object(
            composition,
            "load_workspaces",
            return_value=WorkspaceInventory(
                (Workspace("configured", (RepositoryAnchor(str(configured)),)),)
            ),
        ) as load_workspaces,
        mock.patch.object(
            composition,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(configured)], []),
        ),
    ):
        collector = composition.create_collector(options)

    load_workspaces.assert_called_once_with(config)
    assert collector.projects == [project(configured)]


def test_explicit_workspace_takes_precedence_over_config(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "explicit"
    workspace.mkdir()
    write_config_marker(workspace)
    options = composition.ObservationOptions(
        workspaces=(Workspace("explicit", (RepositoryAnchor(str(workspace)),)),),
        config=tmp_path / "unused.json",
    )

    with (
        mock.patch.object(composition, "load_workspaces") as load_workspaces,
        mock.patch.object(
            composition,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(workspace)], []),
        ),
    ):
        collector = composition.create_collector(options)

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
    options = composition.ObservationOptions()

    with (
        mock.patch.object(composition, "default_workspace_config", return_value=config),
        mock.patch.object(
            composition,
            "load_workspaces",
            return_value=WorkspaceInventory(
                (Workspace("configured", (RepositoryAnchor(str(configured)),)),)
            ),
        ) as load_workspaces,
        mock.patch.object(
            composition,
            "resolve_workspace_projects",
            return_value=WorkspaceResolution([project(configured)], []),
        ),
    ):
        collector = composition.create_collector(options)

    load_workspaces.assert_called_once_with(config)
    assert collector.projects == [project(configured)]


def test_json_mode_prints_snapshot() -> None:
    collector = mock.Mock()
    collector.refresh.return_value = WorkspaceSnapshot(
        collected_at="2026-08-25T01:00:00Z", elapsed_ms=4, projects=[]
    )

    with (
        mock.patch.object(
            cli_observe, "create_collector", return_value=collector
        ) as create_collector,
        mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
    ):
        result = cli.main(["--workspace", "/repo", "--json"])

    assert result == 0
    assert json.loads(stdout.getvalue())["elapsedMs"] == 4
    create_collector.assert_called_once_with(
        composition.ObservationOptions(
            workspaces=(Workspace("repo", (RepositoryAnchor("/repo"),)),)
        ),
        recurring=False,
    )


def source_of(kind: str) -> mock.Mock:
    """A stand-in Query Source reporting only which provider it asks."""
    return mock.Mock(context=mock.Mock(source=kind))


def test_tui_mode_constructs_a_recurring_collector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    collector = mock.Mock()
    sources = {key: mock.Mock() for key in QUERY_SOURCE_KEYS}

    with (
        mock.patch.object(
            cli_observe, "create_collector", return_value=collector
        ) as create_collector,
        mock.patch.object(
            cli_observe, "create_query_sources", return_value=sources
        ) as create_query_sources,
        mock.patch.object(launch, "DashpotApp") as app,
    ):
        result = cli.main(["--workspace", "/repo"])

    assert result == 0
    create_collector.assert_called_once_with(
        composition.ObservationOptions(
            workspaces=(Workspace("repo", (RepositoryAnchor("/repo"),)),)
        ),
        recurring=True,
    )
    ((given_collector, reading),) = [
        call.args for call in create_query_sources.call_args_list
    ]
    assert given_collector is collector
    assert app.call_args.args == (collector,)
    assert app.call_args.kwargs["sources"] is sources
    # Runtime Stats shows the very reading the Query Sources record into.
    assert app.call_args.kwargs["rate_limit"] is reading
    app.return_value.run.assert_called_once_with()


@pytest.mark.parametrize(
    ("argv", "local", "github"),
    [
        ([], 5.0, 90.0),
        (["--refresh-seconds", "20", "--github-refresh-seconds", "0"], 20.0, 0.0),
    ],
)
def test_tui_mode_paces_each_refresh_from_its_flag_or_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: list[str],
    local: float,
    github: float,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "dashpot").mkdir()
    (tmp_path / "dashpot" / "config.toml").write_text(
        "refresh_seconds = 5\ngithub_refresh_seconds = 90\n"
    )
    sources = {key: source_of("github") for key in QUERY_SOURCE_KEYS}

    with (
        mock.patch.object(cli_observe, "create_collector") as create_collector,
        mock.patch.object(cli_observe, "create_query_sources", return_value=sources),
        mock.patch.object(launch, "DashpotApp") as app,
    ):
        assert cli.main(["--workspace", "/repo", *argv]) == 0

    assert create_collector.call_args.args[0].refresh_seconds == local
    assert app.call_args.kwargs["refresh_seconds"] == local
    assert app.call_args.kwargs["query_refresh_seconds"] == github


@pytest.mark.parametrize(
    ("argv", "idle"), [([], 600.0), (["--unattended-seconds", "0"], 0.0)]
)
def test_tui_mode_watches_attendance_from_its_flag_or_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: list[str],
    idle: float,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    (tmp_path / "dashpot").mkdir()
    (tmp_path / "dashpot" / "config.toml").write_text("unattended_seconds = 600\n")
    sources = {key: source_of("github") for key in QUERY_SOURCE_KEYS}

    with (
        mock.patch.object(cli_observe, "create_collector"),
        mock.patch.object(cli_observe, "create_query_sources", return_value=sources),
        mock.patch.object(launch, "DashpotApp") as app,
    ):
        assert cli.main(["--workspace", "/repo", *argv]) == 0

    attendance = app.call_args.kwargs["attendance"]
    assert attendance.idle_seconds == idle
    # Inside tmux, a detached session also shows nobody attending.
    assert attendance.probe is not None


def test_tui_mode_without_tmux_watches_only_idleness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TMUX", raising=False)
    sources = {key: source_of("github") for key in QUERY_SOURCE_KEYS}

    with (
        mock.patch.object(cli_observe, "create_collector"),
        mock.patch.object(cli_observe, "create_query_sources", return_value=sources),
        mock.patch.object(launch, "DashpotApp") as app,
    ):
        assert cli.main(["--workspace", "/repo"]) == 0

    attendance = app.call_args.kwargs["attendance"]
    assert attendance.idle_seconds == composition.DEFAULT_UNATTENDED_SECONDS
    assert attendance.probe is None


def test_tui_mode_without_a_github_query_source_never_pauses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A local Query Source spends nothing while nobody attends.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    sources = {key: source_of("local-markdown") for key in QUERY_SOURCE_KEYS}

    with (
        mock.patch.object(cli_observe, "create_collector"),
        mock.patch.object(cli_observe, "create_query_sources", return_value=sources),
        mock.patch.object(launch, "DashpotApp") as app,
    ):
        assert cli.main(["--workspace", "/repo"]) == 0

    assert app.call_args.kwargs["attendance"] is None


def test_refresh_periods_default_without_a_flag_or_setting(tmp_path: Path) -> None:
    assert composition.refresh_periods(
        settings_path=tmp_path / "config.toml"
    ) == composition.RefreshPeriods(local=15.0, github=60.0, unattended=7200.0)


def test_unreadable_settings_leave_the_default_refresh_periods(tmp_path: Path) -> None:
    # The dashboard still opens; its launcher configuration reports the file.
    path = tmp_path / "config.toml"
    path.write_text("refresh_seconds = -1\ngithub_refresh_seconds = 5\n")

    assert composition.refresh_periods(
        settings_path=path
    ) == composition.RefreshPeriods(local=15.0, github=60.0, unattended=7200.0)
    assert composition.refresh_periods(
        3, settings_path=path
    ) == composition.RefreshPeriods(local=3, github=60.0)
    assert composition.refresh_periods(
        unattended_seconds=0, settings_path=path
    ) == composition.RefreshPeriods(unattended=0)


def test_the_unattended_period_comes_from_its_flag_then_its_setting(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text("unattended_seconds = 600\n")

    assert composition.refresh_periods(
        settings_path=path
    ) == composition.RefreshPeriods(unattended=600)
    assert composition.refresh_periods(
        unattended_seconds=30, settings_path=path
    ) == composition.RefreshPeriods(unattended=30)


def test_only_a_github_query_source_takes_the_github_period() -> None:
    periods = composition.RefreshPeriods(local=15.0, github=60.0)

    assert periods.query_seconds({"issues": source_of("github")}) == periods.github
    assert (
        periods.query_seconds({"issues": source_of("local-markdown")}) == periods.local
    )


def test_query_sources_are_configured_per_key_at_the_first_project_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[tuple[Path, float]] = []
    readings: list[LatestRateLimit | None] = []

    def configured(
        root: Path, *, timeout: float, latest_rate_limit: LatestRateLimit | None
    ) -> object:
        built.append((root, timeout))
        readings.append(latest_rate_limit)
        return object()

    monkeypatch.setattr(composition, "configured_query_source", configured)
    project = ResolvedProject(
        "project:example",
        "Example",
        "repository:example",
        ("test",),
        ("/clone-one", "/clone-two"),
        "/clone-one",
    )
    collector = mock.Mock(projects=[project], timeout=7.5)

    sources = composition.create_query_sources(collector)

    # One source per dashboard query, each its own instance, so concurrent
    # queries never share a source's caches across executor threads.
    assert tuple(sources) == QUERY_SOURCE_KEYS
    assert len({id(source) for source in sources.values()}) == len(sources)
    assert built == [(Path("/clone-one"), 7.5)] * len(QUERY_SOURCE_KEYS)
    # They share one rate limit reading, so the dashboard reports the most
    # recent one GitHub gave any of them.
    assert readings[0] is not None
    assert all(reading is readings[0] for reading in readings)

    # A reading given is the one they share, so the dashboard can show it.
    shared = LatestRateLimit()
    readings.clear()
    composition.create_query_sources(collector, shared)
    assert readings == [shared] * len(QUERY_SOURCE_KEYS)


def test_with_no_project_resolved_no_query_reads_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Started inside another configured Project, a dashboard whose one anchor
    # fails to resolve must neither query that Project nor refuse over a
    # configuration the working directory's subdirectory does not hold.
    configured = init_repository(tmp_path / "configured")
    write_project_config(configured)
    nested = configured / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    missing = tmp_path / "missing"
    collector = composition.create_collector(
        composition.ObservationOptions(
            workspaces=(Workspace("gone", (RepositoryAnchor(str(missing)),)),)
        ),
        recurring=False,
    )
    assert collector.projects == []

    sources = composition.create_query_sources(collector)

    assert tuple(sources) == QUERY_SOURCE_KEYS
    assert all(isinstance(each, UnresolvedQuerySource) for each in sources.values())
    assert not composition.reads_github(sources)
    for source in sources.values():
        assert source.context is None
        assert source.source_diagnostics() == ()
        assert not source.supports_sort(QueryRequest(kind="issues"), "number")
        assert source.resolve_identities(()) == ()
        with pytest.raises(ProjectUnresolvedError, match="no Project resolved"):
            source.query_page(QueryRequest(kind="issues"))
        with pytest.raises(ProjectUnresolvedError):
            source.resolve_identities(("issue:1",))
        with pytest.raises(ProjectUnresolvedError):
            source.enumerate_source("issues")


def test_a_dashboard_with_no_project_resolved_opens_with_its_anchor_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = init_repository(tmp_path / "configured")
    write_project_config(configured)
    (configured / "src").mkdir()
    monkeypatch.chdir(configured / "src")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    with mock.patch.object(launch, "DashpotApp") as app:
        app.return_value.return_code = None
        assert cli.main(["--workspace", str(tmp_path / "missing")]) == 0

    collector = app.call_args.args[0]
    assert collector.projects == []
    assert [diagnostic.code for diagnostic in collector.diagnostics]
    sources = app.call_args.kwargs["sources"]
    assert all(isinstance(each, UnresolvedQuerySource) for each in sources.values())


def test_compact_json_mode_has_no_recurring_polling_schedule() -> None:
    collector = mock.Mock()
    collector.refresh.return_value = WorkspaceSnapshot(
        collected_at="2026-08-25T01:00:00Z", elapsed_ms=4, projects=[]
    )

    with (
        mock.patch.object(
            cli_observe, "create_collector", return_value=collector
        ) as create_collector,
        mock.patch("sys.stdout", new_callable=io.StringIO),
    ):
        result = cli.main(["--workspace", "/repo", "--compact-json"])

    assert result == 0
    create_collector.assert_called_once_with(
        composition.ObservationOptions(
            workspaces=(Workspace("repo", (RepositoryAnchor("/repo"),)),)
        ),
        recurring=False,
    )


def test_cli_reports_startup_error_without_traceback() -> None:
    with (
        mock.patch.object(
            cli_observe,
            "create_collector",
            side_effect=ProjectConfigError("bad config"),
        ),
        mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
    ):
        result = cli.main([])

    assert result == 2
    assert stderr.getvalue() == "dashpot: bad config\n"


@pytest.mark.parametrize(
    ("argv", "seam", "error"),
    [
        (
            ["--json"],
            "dashpot.cli.observe.create_collector",
            ProjectConfigError("bad config"),
        ),
        (
            ["--json"],
            "dashpot.cli.observe.create_collector",
            DashpotError("stated refusal"),
        ),
        (
            ["--json"],
            "dashpot.cli.observe.create_collector",
            GitError(("rev-parse", "--show-toplevel"), Path("/r"), detail="no git"),
        ),
        (
            ["issue", "show", "9"],
            "dashpot.cli.sources.show_issue",
            IssueProfileError("Issue 9 incomplete"),
        ),
        (
            ["issue", "show", "9"],
            "dashpot.cli.sources.show_issue",
            IssueSourceRefreshError("github-profile", "malformed Issue node"),
        ),
        (
            ["issue", "show", "9"],
            "dashpot.cli.sources.show_issue",
            LocalMarkdownIssueError("malformed Local Issue document"),
        ),
        (
            ["issue", "show", "9"],
            "dashpot.cli.sources.show_issue",
            IssueSourceRefreshError("gh-failed", "gh exited 1"),
        ),
        (
            ["work", "start", "9"],
            "dashpot.cli.work.start_issue_work",
            DashpotError("no supported agent session encloses this command"),
        ),
        (
            ["worktree", "check", "/nowhere"],
            "dashpot.cli.worktrees.check_worktree",
            CleanupError("/nowhere is not a Worktree"),
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

    with mock.patch(seam, side_effect=error):
        assert cli.main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"dashpot: {error}\n"


GONE = (
    "dashpot: the working directory no longer exists; change to a directory "
    "that does and run the command again\n"
)


def remove_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave this process in a directory that has been removed, as a shell can be."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--workspace", "relative"],
        ["init"],
        ["work", "start", "1"],
        ["work", "relocate", "elsewhere"],
        ["work", "stop"],
        ["work", "forget-subagents", "session"],
        ["work", "assign", "1", "--worker", "agent", "--worktree", "elsewhere"],
        ["work", "unassign", "agent"],
        ["work", "show"],
        ["events"],
        ["events", "remove", "--before", "2026-09-01"],
        ["issue", "show", "1"],
        ["issue", "list"],
        ["pr", "list"],
        ["worktree", "create", "1"],
        ["worktree", "check"],
        ["worktree", "remove", "elsewhere"],
        ["branch", "delete", "feature", "--local"],
        ["integrate", "claude-code", "--status"],
        ["integrate", "codex", "opencode", "--status"],
    ],
)
def test_a_command_run_in_a_removed_directory_refuses_on_one_line(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    remove_working_directory(tmp_path, monkeypatch)

    assert cli.main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == GONE


def test_an_absolute_workspace_needs_no_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remove_working_directory(tmp_path, monkeypatch)

    assert cli_observe.parse_workspace_argument(str(tmp_path)) == Workspace(
        tmp_path.name, (RepositoryAnchor(str(tmp_path)),)
    )
    with pytest.raises(WorkingDirectoryError):
        cli_observe.parse_workspace_argument("relative")


def test_an_unreadable_working_directory_is_refused_with_its_reason() -> None:
    with (
        mock.patch.object(Path, "cwd", side_effect=PermissionError("denied")),
        pytest.raises(WorkingDirectoryError, match="cannot read the working directory"),
    ):
        current_directory()


def test_a_refusal_without_text_is_named_by_its_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_sources, "show_issue", side_effect=IssueResolutionError()
    ):
        assert cli.main(["issue", "show", "1"]) == 2

    assert capsys.readouterr().err == "dashpot: IssueResolutionError\n"


def test_an_unreadable_configuration_never_hides_what_a_command_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The command's outcome names its Project from the configuration once it
    # is done; one that does not decode names none rather than failing it.
    checkout = init_repository(tmp_path / "checkout")
    (checkout / ".dashpot").mkdir()
    (checkout / ".dashpot" / "config.json").write_bytes(b'{"projectId": "caf\xe9"}')
    monkeypatch.chdir(checkout)
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    events = tmp_path / "events"

    assert (
        cli.main(
            ["events", "remove", "--before", "2020-01-01"],
            event_log=EventLogDestination(events),
        )
        == 0
    )

    (outcome,) = [
        record
        for path in events.glob("*.jsonl")
        for line in path.read_text().splitlines()
        if (record := json.loads(line))["event.name"] == "command.outcome"
    ]
    assert outcome["dashpot.outcome.result"] == "succeeded"
    assert "dashpot.project.id" not in outcome


def test_hook_stream_publishes_atomic_session_record(tmp_path: Path) -> None:
    event = {
        "session_id": "session-7",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
    }
    process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    with (
        mock.patch(
            "dashpot.sessions.hook_publish.state_directory",
            return_value=tmp_path / "state",
        ),
        mock.patch(
            "dashpot.sessions.hook_publish.observe_agent_ancestry",
            return_value=AgentAncestry(("codex", process)),
        ),
    ):
        publish_from_stream(io.StringIO(json.dumps(event)))

    record = json.loads((tmp_path / "state" / "session-7.json").read_text())
    # A session's start begins no turn (ADR 0106).
    assert record["state"] == "waiting"
    assert record["sessionProcess"]["pid"] == 42


def test_a_programmer_fault_is_not_stated_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only DashpotError is the contract: a bare RuntimeError is a bug, so it
    # escapes ``main`` with its traceback instead of one ``dashpot:`` line.
    monkeypatch.chdir(tmp_path)

    with (
        mock.patch.object(
            cli_observe, "create_collector", side_effect=RuntimeError("closed union")
        ),
        pytest.raises(RuntimeError, match="closed union"),
    ):
        cli.main(["--json"])


def test_not_a_repository_is_read_from_git_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Composition treats only Git's refusal as "not inside a repository"; a
    # runtime fault while asking is not silently read as that answer.
    monkeypatch.chdir(tmp_path)
    options = composition.ObservationOptions()

    with (
        mock.patch.object(
            composition, "worktree_root", side_effect=RuntimeError("symlink loop")
        ),
        pytest.raises(RuntimeError, match="symlink loop"),
    ):
        composition.create_collector(options)
    with (
        mock.patch.object(
            protection, "worktree_root", side_effect=RuntimeError("symlink loop")
        ),
        pytest.raises(RuntimeError, match="symlink loop"),
    ):
        composition.cleanup_protection()


def test_unconfigured_repository_error_suggests_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    options = composition.ObservationOptions()
    missing = tmp_path / "nowhere" / "workspaces.json"

    with (
        mock.patch.object(composition, "worktree_root", return_value=tmp_path),
        mock.patch.object(
            composition, "default_workspace_config", return_value=missing
        ),
        pytest.raises(ProjectConfigError, match="dashpot init"),
    ):
        composition.create_collector(options)


def test_init_command_prints_messages_and_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_init, "initialize_project", return_value=["created config"]
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
        cli_init,
        "initialize_project",
        side_effect=InitError("already configured"),
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
        cli_work, "start_issue_work", return_value=["started work on #7"]
    ) as start:
        code = cli.main(["work", "start", "#7"])

    assert code == 0
    start.assert_called_once_with(
        Path.cwd().resolve(), "#7", timeout=10.0, outcome=mock.ANY
    )
    assert "started work on #7" in capsys.readouterr().out


def test_work_relocate_dispatches_with_the_target_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "linked"

    with mock.patch.object(
        cli_work, "relocate_issue_work", return_value=["prepared relocation"]
    ) as relocate:
        code = cli.main(["work", "relocate", str(target)])

    assert code == 0
    relocate.assert_called_once_with(
        Path.cwd().resolve(), target.resolve(), outcome=mock.ANY
    )
    assert "prepared relocation" in capsys.readouterr().out


def test_work_forget_subagents_dispatches_with_the_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_work, "forget_session_subagents", return_value=["forgot 1 sub-agent"]
    ) as forget:
        assert cli.main(["work", "forget-subagents", "0199-lead"]) == 0
        assert (
            cli.main(
                ["work", "forget-subagents", "0199-lead", "--harness", "claude-code"]
            )
            == 0
        )

    assert forget.call_args_list == [
        mock.call(Path.cwd().resolve(), "0199-lead", harness=None, outcome=mock.ANY),
        mock.call(
            Path.cwd().resolve(), "0199-lead", harness="claude-code", outcome=mock.ANY
        ),
    ]
    assert "forgot 1 sub-agent" in capsys.readouterr().out


def test_work_forget_subagents_fails_when_a_record_changed_meanwhile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    def changed(*_args: object, outcome: OutcomeNote, **_kwargs: object) -> list[str]:
        outcome.incomplete = True
        return ["the record changed while it was read"]

    with mock.patch.object(cli_work, "forget_session_subagents", side_effect=changed):
        assert cli.main(["work", "forget-subagents", "0199-lead"]) == 2

    assert "changed while it was read" in capsys.readouterr().out


def test_work_assign_and_unassign_dispatch_with_the_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_work, "assign_worker", return_value=["assigned Worker agent-1 to #7"]
    ) as assign:
        assert (
            cli.main(
                ["work", "assign", "#7", "--worker", "agent-1", "--worktree", "../w7"]
            )
            == 0
        )
    assign.assert_called_once_with(
        Path.cwd().resolve(),
        "#7",
        "agent-1",
        Path("../w7"),
        timeout=10.0,
        outcome=mock.ANY,
    )
    assert "assigned Worker agent-1 to #7" in capsys.readouterr().out

    with mock.patch.object(
        cli_work, "unassign_worker", return_value=["unassigned Worker agent-1 from #7"]
    ) as unassign:
        assert cli.main(["work", "unassign", "agent-1"]) == 0
    unassign.assert_called_once_with(Path.cwd().resolve(), "agent-1", outcome=mock.ANY)
    assert "unassigned Worker agent-1 from #7" in capsys.readouterr().out


def test_work_assign_refusal_is_reported_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_work,
        "assign_worker",
        side_effect=IssueWorkError("lists no Sub-agent agent-1 as working"),
    ):
        code = cli.main(
            ["work", "assign", "#7", "--worker", "agent-1", "--worktree", "."]
        )

    assert code == 2
    assert "lists no Sub-agent agent-1 as working" in capsys.readouterr().err


def test_work_stop_and_show_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_work, "stop_issue_work", return_value=["stopped work on #7"]
    ) as stop:
        assert cli.main(["work", "stop"]) == 0
    stop.assert_called_once_with(
        Path.cwd().resolve(), session_key=None, outcome=mock.ANY
    )

    with mock.patch.object(
        cli_work, "stop_issue_work", return_value=["stopped orphaned work on #7"]
    ) as stop:
        assert cli.main(["work", "stop", "--session", "codex-42-abcd1234"]) == 0
    stop.assert_called_once_with(
        Path.cwd().resolve(), session_key="codex-42-abcd1234", outcome=mock.ANY
    )

    with (
        mock.patch.object(
            cli_work, "show_issue_work", return_value=["no active Issue work"]
        ) as show,
        mock.patch.object(
            cli_work,
            "show_session_events",
            return_value=["recent events of codex pid 42:", "  an event"],
        ) as recent,
    ):
        assert cli.main(["work", "show"]) == 0
    show.assert_called_once_with(Path.cwd().resolve())
    recent.assert_called_once_with(Path.cwd().resolve())

    output = capsys.readouterr().out
    assert "stopped work on #7" in output
    assert "no active Issue work\nrecent events of codex pid 42:\n  an event" in output


def test_work_errors_are_reported_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_work,
        "start_issue_work",
        side_effect=IssueWorkError("no supported agent session"),
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

    with mock.patch.object(cli_sources, "show_issue", return_value=issue) as show:
        assert cli.main(["issue", "show", "35"]) == 0
    show.assert_called_once_with(Path.cwd().resolve(), "35", timeout=10.0)
    lines = capsys.readouterr().out
    assert "ned2/dashpot#35: Worktree protocol" in lines
    assert "location: https://github.com/ned2/dashpot/issues/35" in lines

    with mock.patch.object(cli_sources, "show_issue", return_value=issue):
        assert cli.main(["issue", "show", "#35", "--json", "--timeout", "2"]) == 0
    # The wire payload pins the JSON contract independently of the model's
    # own dump: camelCase keys and explicit nulls, exactly as the fixture.
    assert json.loads(capsys.readouterr().out) == payload

    with mock.patch.object(
        cli_sources,
        "show_issue",
        side_effect=IssueResolutionError("did not match an Issue"),
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
    main_worktree="/w/dashpot",
    dry_run=False,
    created=True,
)


def test_worktree_create_dispatches_every_option_and_prints_the_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(
        cli_worktrees, "create_issue_worktree", return_value=PLAN
    ) as create:
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
    assert (
        "worktree root: /w/dashpot.worktrees "
        "(from default-sibling, beside the main working tree /w/dashpot)"
    ) in out


def test_worktree_create_refusal_exits_2_in_both_output_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    refused = PLAN.model_copy(
        update={
            "created": False,
            "refusals": ("Branch 35-worktree-protocol already exists",),
        }
    )

    with mock.patch.object(
        cli_worktrees, "create_issue_worktree", return_value=refused
    ):
        assert cli.main(["worktree", "create", "35"]) == 2
    captured = capsys.readouterr()
    assert (
        captured.err == "dashpot: refused: Branch 35-worktree-protocol already exists\n"
    )
    assert captured.out.startswith("refused Worktree ")

    with mock.patch.object(
        cli_worktrees, "create_issue_worktree", return_value=refused
    ):
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
            CleanupBlocker(
                kind="dirty",
                detail="1 changed path",
                command="git -C /w/x status",
            ),
        ),
        remove_commands=("git worktree remove /w/x",),
    )

    protected = [Path("/w/anchor")]
    with (
        mock.patch.object(cli_worktrees, "cleanup_protection", return_value=protected),
        mock.patch.object(
            cli_worktrees, "check_worktree", return_value=report
        ) as check,
    ):
        assert cli.main(["worktree", "check", "/w/x"]) == 0
    # The check protects what a Cleanup protects, by the same rule.
    check.assert_called_once_with(
        Path.cwd().resolve(), Path("/w/x"), protected=protected, timeout=10.0
    )
    out = capsys.readouterr().out
    assert "Removable  no" in out
    assert "  - dirty: 1 changed path\n      run: git -C /w/x status" in out

    with mock.patch.object(cli_worktrees, "check_worktree", return_value=report):
        assert cli.main(["worktree", "check", "/w/x", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["removable"] is False
    assert payload["obstacles"][0]["kind"] == "dirty"


def test_worktree_check_without_a_path_reports_every_linked_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    def report(path: str, removable: bool) -> WorktreeRemovability:
        return WorktreeRemovability(
            path=path,
            branch="b",
            head="e319d3c",
            role="linked",
            removable=removable,
            obstacles=()
            if removable
            else (CleanupBlocker(kind="dirty", detail="1 changed path"),),
            remove_commands=(f"git worktree remove {path}",),
        )

    reports = {Path("/w/a"): report("/w/a", True), Path("/w/b"): report("/w/b", False)}
    with (
        mock.patch.object(
            cli_worktrees, "linked_worktrees", return_value=list(reports)
        ) as listed,
        mock.patch.object(
            cli_worktrees,
            "check_worktree",
            side_effect=lambda _c, p, protected, timeout: reports[p],
        ),
    ):
        assert cli.main(["worktree", "check"]) == 0
    listed.assert_called_once_with(Path.cwd().resolve(), timeout=10.0)
    out = capsys.readouterr().out
    assert (
        "Worktree   /w/a\nBranch     b\nRemovable  yes\n"
        "           Sub-agents of Agent Sessions outside this Repository are not "
        "checked.\nRemove with\n" in out
    )
    assert "\n\nWorktree   /w/b\nBranch     b\nRemovable  no\nObstacles\n" in out
    assert out.count("Sub-agents") == 1

    with (
        mock.patch.object(
            cli_worktrees, "linked_worktrees", return_value=list(reports)
        ),
        mock.patch.object(
            cli_worktrees,
            "check_worktree",
            side_effect=lambda _c, p, protected, timeout: reports[p],
        ),
    ):
        assert cli.main(["worktree", "check", "--json"]) == 0
    listed_json = capsys.readouterr().out
    payload = json.loads(listed_json)
    assert [item["removable"] for item in payload] == [True, False]
    assert "Sub-agents" not in listed_json

    with mock.patch.object(cli_worktrees, "linked_worktrees", return_value=[]):
        assert cli.main(["worktree", "check"]) == 0
    assert capsys.readouterr().out.strip() == "no linked Worktrees in this Repository"


def cleanup_target(
    kind: Literal["local-branch", "remote-branch", "worktree"],
    *,
    requires: str | None = None,
) -> CleanupTarget:
    identity = {
        "local-branch": "local:refs/heads/feat",
        "remote-branch": "remote:origin:refs/heads/feat",
        "worktree": "worktree:/w/x",
    }[kind]
    return CleanupTarget(
        identity=identity,
        kind=kind,
        label={
            "local-branch": "Local Branch",
            "remote-branch": "Branch at origin",
            "worktree": "Worktree",
        }[kind],
        expected="e319d3c0000000000000000000000000000000ab",
        ref="refs/remotes/origin/feat"
        if kind == "remote-branch"
        else "refs/heads/feat",
        remote="origin" if kind == "remote-branch" else None,
        path="/w/x" if kind == "worktree" else None,
        integration=None,
        observed_at=None,
        requires=requires,
        blockers=(),
        consequences=(),
    )


def cleanup_preview(
    kind: Literal["branch", "worktree"], *targets: CleanupTarget
) -> CleanupPreview:
    return CleanupPreview(
        kind=kind,
        subject="feat" if kind == "branch" else "/w/x",
        anchor="/w/repo",
        targets=targets,
        ignored=(),
        refusals=(),
        fingerprint="0123456789abcdef",
    )


def cleanup_report(
    preview: CleanupPreview,
    *,
    dry_run: bool = False,
    performed: bool = True,
    refusals: tuple[str, ...] = (),
    planned: tuple[str, ...] = (),
    results: tuple[TargetResult, ...] = (),
) -> CleanupReport:
    return CleanupReport(
        kind=preview.kind,
        subject=preview.subject,
        anchor=preview.anchor,
        dry_run=dry_run,
        performed=performed,
        preview=preview,
        refusals=refusals,
        planned=planned,
        results=results,
    )


def test_branch_delete_previews_confirms_and_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    local = cleanup_target("local-branch")
    preview = cleanup_preview("branch", local)
    report = cleanup_report(
        preview,
        results=(
            TargetResult(
                identity=local.identity,
                kind="local-branch",
                label="Local Branch",
                expected=local.expected,
                outcome="deleted",
                detail="deleted refs/heads/feat at e319d3c",
                recovery=f"git branch feat {local.expected}",
            ),
        ),
    )
    adapter = object()

    with (
        mock.patch.object(composition, "cleanup_git", return_value=adapter),
        mock.patch.object(
            composition, "inspect_cleanup", return_value=preview
        ) as inspect,
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert cli.main(["branch", "delete", "feat", "--local"]) == 0
    request = BranchCleanupRequest(tmp_path.resolve(), "feat")
    protected = [tmp_path.resolve()]
    inspect.assert_called_once_with(
        request, protected=protected, timeout=10.0, git=adapter
    )
    perform.assert_called_once_with(
        CleanupConfirmation(request, "0123456789abcdef", (local.identity,)),
        protected=protected,
        timeout=10.0,
        git=adapter,
        dry_run=False,
    )
    out = capsys.readouterr().out
    assert "Delete Branch   feat" in out
    assert "  deleted        Local Branch refs/heads/feat @ e319d3c" in out
    assert f"      recover: git branch feat {local.expected}" in out

    with (
        mock.patch.object(composition, "cleanup_git", return_value=adapter),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(composition, "perform_cleanup", return_value=report),
    ):
        assert cli.main(["branch", "delete", "feat", "--local", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["succeeded"] is True
    assert payload["results"][0]["outcome"] == "deleted"


def test_branch_delete_names_each_remote_it_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    preview = cleanup_preview("branch", cleanup_target("local-branch"))
    report = cleanup_report(preview, performed=False, refusals=("nothing",))

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert (
            cli.main(
                [
                    "branch",
                    "delete",
                    "feat",
                    "--remote",
                    "origin",
                    "--remote",
                    "upstream",
                    "--local",
                ]
            )
            == 2
        )
    assert perform.call_args.args[0].selected == (
        "local:refs/heads/feat",
        "remote:origin:refs/heads/feat",
        "remote:upstream:refs/heads/feat",
    )


def test_branch_delete_without_a_target_flag_is_a_usage_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(composition, "inspect_cleanup") as inspect:
        assert cli.main(["branch", "delete", "feat"]) == 2
    inspect.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "dashpot: name at least one target to delete: --local, --remote REMOTE\n"
    )


def test_branch_delete_refusal_exits_2_and_names_each_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    preview = cleanup_preview("branch")
    report = cleanup_report(
        preview, performed=False, refusals=("no Branch named feat",)
    )

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert cli.main(["branch", "delete", "feat", "--local"]) == 2
    # With no local target to select, the command still names the one it
    # meant so the refusal is about that ref.
    assert perform.call_args.args[0].selected == ("local:refs/heads/feat",)
    captured = capsys.readouterr()
    assert "Refused         no Branch named feat" in captured.out
    assert captured.err == "dashpot: refused: no Branch named feat\n"


def test_worktree_remove_selects_its_targets_from_the_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    tree = cleanup_target("worktree")
    local = cleanup_target("local-branch", requires=tree.identity)
    preview = cleanup_preview("worktree", tree, local)
    report = cleanup_report(
        preview,
        dry_run=True,
        performed=False,
        planned=(tree.identity, local.identity),
    )
    adapter = object()

    with (
        mock.patch.object(composition, "cleanup_git", return_value=adapter),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert (
            cli.main(
                [
                    "worktree",
                    "remove",
                    "/w/x",
                    "--delete-branch",
                    "--delete-ignored",
                    "--dry-run",
                    "--timeout",
                    "3",
                ]
            )
            == 0
        )
    perform.assert_called_once_with(
        CleanupConfirmation(
            WorktreeCleanupRequest(tmp_path.resolve(), Path("/w/x")),
            "0123456789abcdef",
            (tree.identity, local.identity),
            delete_ignored=True,
        ),
        protected=[tmp_path.resolve()],
        timeout=3.0,
        git=adapter,
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert "Dry run         would attempt, in order" in out
    assert "  1. Worktree /w/x" in out
    assert "  2. Local Branch refs/heads/feat" in out

    with (
        mock.patch.object(composition, "cleanup_git", return_value=adapter),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert cli.main(["worktree", "remove", "/w/x", "--json"]) == 0
    assert perform.call_args.args[0].selected == (tree.identity,)
    assert perform.call_args.args[0].delete_ignored is False
    assert json.loads(capsys.readouterr().out)["planned"] == [
        tree.identity,
        local.identity,
    ]


def test_worktree_remove_with_delete_branch_needs_a_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    preview = cleanup_preview("worktree", cleanup_target("worktree"))

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(composition, "perform_cleanup") as perform,
    ):
        assert cli.main(["worktree", "remove", "/w/x", "--delete-branch"]) == 2
    perform.assert_not_called()
    assert capsys.readouterr().err == (
        "dashpot: /w/x has no Branch checked out to delete\n"
    )


@pytest.mark.parametrize(
    ("flags", "selected"),
    [
        ((), ("worktree:/w/x",)),
        (
            ("--delete-remote-branch",),
            ("worktree:/w/x", "remote:origin:refs/heads/feat"),
        ),
        (
            ("--delete-branch", "--delete-remote-branch"),
            (
                "worktree:/w/x",
                "local:refs/heads/feat",
                "remote:origin:refs/heads/feat",
            ),
        ),
    ],
)
def test_worktree_remove_deletes_at_the_push_remote_only_with_its_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: tuple[str, ...],
    selected: tuple[str, ...],
) -> None:
    """No default applies to the CLI: its flags are its disclosure."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    tree = cleanup_target("worktree")
    local = cleanup_target("local-branch", requires=tree.identity)
    pushed = cleanup_target("remote-branch", requires=tree.identity)
    preview = cleanup_preview("worktree", tree, local, pushed)
    report = cleanup_report(preview, dry_run=True, performed=False, planned=selected)

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert (
            cli.main(
                ["worktree", "remove", "/w/x", *flags, "--delete-ignored", "--dry-run"]
            )
            == 0
        )
    assert perform.call_args.args[0].selected == selected


@pytest.mark.parametrize(
    ("targets", "reason"),
    [
        (("worktree",), "/w/x has no Branch checked out to delete"),
        (
            ("worktree", "local-branch"),
            "/w/x's Branch has no Remote-Tracking Branch for it at the remote a plain "
            "git push reaches; fetch, or delete it with dashpot branch delete "
            "--remote",
        ),
    ],
)
def test_worktree_remove_with_delete_remote_branch_needs_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    targets: tuple[Literal["local-branch", "worktree"], ...],
    reason: str,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    preview = cleanup_preview("worktree", *map(cleanup_target, targets))

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(composition, "inspect_cleanup", return_value=preview),
        mock.patch.object(composition, "perform_cleanup") as perform,
    ):
        assert cli.main(["worktree", "remove", "/w/x", "--delete-remote-branch"]) == 2
    perform.assert_not_called()
    assert capsys.readouterr().err == f"dashpot: {reason}\n"


def test_worktree_remove_refusal_says_how_to_free_it_of_a_live_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree, (root, _worktree) = occupied_worktree(
        tmp_path, "claude-code", SESSION, CLAUDE
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(root)
    lookup = table_lookup({CLAUDE.pid: CLAUDE})

    with (
        mock.patch.object(
            composition, "inspect_cleanup", partial(inspect_cleanup, lookup=lookup)
        ),
        mock.patch.object(
            composition, "perform_cleanup", partial(perform_cleanup, lookup=lookup)
        ),
    ):
        assert cli.main(["worktree", "remove", str(worktree)]) == 2

    refusal = (
        f"Worktree is unavailable: Claude Code session {SESSION} is live here "
        f"(last activity 2026-09-30T03:40:00.000000Z). To free this Worktree, "
        f"{CLAUDE_CODE_STEPS}."
    )
    captured = capsys.readouterr()
    assert f"Refused         {refusal}" in captured.out.splitlines()
    assert captured.err == f"dashpot: refused: {refusal}\n"
    assert worktree.exists()


@pytest.mark.parametrize("parent_in_repository", [False, True])
def test_worktree_remove_dry_run_says_which_sub_agents_go_unchecked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    parent_in_repository: bool,
) -> None:
    """The gap #357 accepted is stated where the preview would remove the Worktree.

    A sub-agent of a session placed outside the Repository is not counted, so
    the Worktree is removable and the dry run says what went unchecked; one
    placed in the Repository blocks, and the refusal needs no such line.
    """
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    if parent_in_repository:
        publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")
    else:
        publish_subagent(state_directory(), elsewhere, "SubagentStart", "a686b12")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(root)
    lookup = table_lookup({PARENT.pid: PARENT})

    with (
        mock.patch.object(
            composition, "inspect_cleanup", partial(inspect_cleanup, lookup=lookup)
        ),
        mock.patch.object(
            composition, "perform_cleanup", partial(perform_cleanup, lookup=lookup)
        ),
    ):
        code = cli.main(
            ["worktree", "remove", str(target), "--delete-ignored", "--dry-run"]
        )

    lines = capsys.readouterr().out.splitlines()
    scope = "     Sub-agents of Agent Sessions outside this Repository are not checked."
    if parent_in_repository:
        assert code == 2
        assert any(line.startswith("Refused ") for line in lines)
        assert scope not in lines
    else:
        assert code == 0
        assert lines[2:] == [
            "Dry run         would attempt, in order",
            f"  1. Worktree {target.resolve()}",
            scope,
        ]
    assert target.exists()


@pytest.mark.parametrize("parent_in_repository", [False, True])
def test_worktree_check_says_which_sub_agents_go_unchecked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    parent_in_repository: bool,
) -> None:
    """``worktree check`` states the gap #357 accepted where it says ``yes``.

    The line the Cleanup preview gives a Worktree it would remove qualifies a
    removable verdict here too. A blocked verdict claims no absence of
    occupants, and the JSON document carries no prose for a person.
    """
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    if parent_in_repository:
        publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")
    else:
        publish_subagent(state_directory(), elsewhere, "SubagentStart", "a686b12")
    monkeypatch.chdir(root)
    lookup = table_lookup({PARENT.pid: PARENT})
    check = partial(check_worktree, lookup=lookup)

    with mock.patch.object(cli_worktrees, "check_worktree", check):
        assert cli.main(["worktree", "check", str(target)]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert cli.main(["worktree", "check", str(target), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)

    scope = "           Sub-agents of Agent Sessions outside this Repository are not checked."
    if parent_in_repository:
        assert lines[2:4] == ["Removable  no", "Obstacles"]
        assert scope not in lines
    else:
        assert lines[2:5] == ["Removable  yes", scope, "Remove with"]
    assert payload["removable"] is not parent_in_repository
    assert set(payload) == REMOVABILITY_KEYS
    assert "Sub-agents" not in json.dumps(payload)


def test_cleanup_protects_this_checkout_and_every_configured_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI protects what a dashboard run from here would observe."""
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    write_config_marker(repository)
    inside = repository / "src"
    inside.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    other_inside = other / "pkg"
    other_inside.mkdir()
    plain = tmp_path / "plain"
    plain.mkdir()
    xdg = tmp_path / "xdg"
    (xdg / "dashpot").mkdir(parents=True)
    (xdg / "dashpot" / "workspaces.json").write_text(
        json.dumps(
            {
                "workspaces": [
                    {"name": "all", "anchors": [str(other_inside), str(plain)]}
                ]
            }
        )
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.chdir(inside)
    preview = cleanup_preview("worktree", cleanup_target("worktree"))
    report = cleanup_report(preview, dry_run=True, performed=False)

    with (
        mock.patch.object(composition, "cleanup_git", return_value=object()),
        mock.patch.object(
            composition, "inspect_cleanup", return_value=preview
        ) as inspect,
        mock.patch.object(
            composition, "perform_cleanup", return_value=report
        ) as perform,
    ):
        assert cli.main(["worktree", "remove", "/w/x", "--dry-run"]) == 0

    expected = [
        inside.resolve(),
        repository.resolve(),
        other.resolve(),
        plain.resolve(),
    ]
    assert inspect.call_args.kwargs["protected"] == expected
    assert perform.call_args.kwargs["protected"] == expected


@pytest.mark.parametrize(
    "content",
    [b"not json", b'{"workspaces": [{"name": "caf\xe9", "anchors": ["/a"]}]}'],
    ids=["malformed", "not-utf-8"],
)
def test_cleanup_refuses_when_the_workspace_inventory_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: bytes,
) -> None:
    xdg = tmp_path / "xdg"
    (xdg / "dashpot").mkdir(parents=True)
    (xdg / "dashpot" / "workspaces.json").write_bytes(content)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(composition, "inspect_cleanup") as inspect:
        assert cli.main(["branch", "delete", "feat", "--local"]) == 2

    inspect.assert_not_called()
    err = capsys.readouterr().err
    assert "cannot tell which Repository Anchors to protect" in err
    assert "workspaces.json" in err


def test_integrate_codex_dispatches_install_remove_and_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        cli_integrate, "install_integration", return_value=["installed hooks"]
    ) as install:
        assert cli.main(["integrate", "codex"]) == 0
    install.assert_called_once_with("codex")

    with mock.patch.object(
        cli_integrate, "remove_integration", return_value=["removed hooks"]
    ) as remove:
        assert cli.main(["integrate", "claude-code", "--remove"]) == 0
    remove.assert_called_once_with("claude-code")

    with mock.patch.object(
        cli_integrate, "integration_status", return_value=["installed in x"]
    ) as status:
        assert cli.main(["integrate", "claude-code", "--status"]) == 0
    status.assert_called_once_with("claude-code", current=current_directory())

    output = capsys.readouterr().out
    assert "installed hooks" in output
    assert "removed hooks" in output
    assert "installed in x" in output


def test_integrate_errors_are_reported_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        cli_integrate,
        "install_integration",
        side_effect=IntegrationError("no Codex configuration directory"),
    ):
        code = cli.main(["integrate", "codex"])

    assert code == 2
    assert "no Codex configuration directory" in capsys.readouterr().err


def test_an_incomplete_integrate_reports_what_it_wrote_then_what_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    incomplete = IncompleteIntegrationError(
        "codex",
        ["could not install the Dashpot Second skill in /x: disk full"],
        ["installed Codex lifecycle hooks in /h", "installed Dashpot First skill"],
    )
    with mock.patch.object(
        cli_integrate, "install_integration", side_effect=incomplete
    ):
        code = cli.main(["integrate", "codex"])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out.splitlines() == [
        "installed Codex lifecycle hooks in /h",
        "installed Dashpot First skill",
    ]
    assert captured.err == (
        "dashpot: could not install the Dashpot Second skill in /x: disk full; "
        "the rest of the integration is written, and rerunning 'dashpot "
        "integrate codex' once that is fixed finishes it\n"
    )


def test_an_incomplete_removal_reports_what_it_removed_then_what_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    incomplete = IncompleteRemovalError(
        "opencode",
        ["could not remove Dashpot worker agent from /a: denied"],
        ["removed the OpenCode plugin /p", "removed the Dashpot First skill from /s"],
    )
    with mock.patch.object(cli_integrate, "remove_integration", side_effect=incomplete):
        code = cli.main(["integrate", "opencode", "--remove"])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out.splitlines() == [
        "removed the OpenCode plugin /p",
        "removed the Dashpot First skill from /s",
    ]
    assert captured.err == (
        "dashpot: could not remove Dashpot worker agent from /a: denied; the "
        "rest of the integration is removed, and rerunning 'dashpot integrate "
        "opencode --remove' once that is fixed finishes it\n"
    )


def test_integrate_runs_several_harnesses_together_and_groups_their_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reports = [
        HarnessReport("claude-code", "installed", ("installed hooks in /c",)),
        HarnessReport("codex", "not integrated", note="not integrated (no /x)"),
        HarnessReport(
            "opencode", "refused", note="refused", error="the opencode on PATH is 1.x"
        ),
    ]
    with mock.patch.object(
        cli_integrate, "install_integrations", return_value=reports
    ) as run:
        code = cli.main(["integrate", "opencode", "claude-code", "codex", "opencode"])

    run.assert_called_once_with(("claude-code", "codex", "opencode"))
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out.splitlines() == [
        "Claude Code:",
        "  installed hooks in /c",
        "Codex: not integrated (no /x)",
        "OpenCode: refused",
    ]
    assert captured.err == "dashpot: OpenCode: the opencode on PATH is 1.x\n"


@pytest.mark.parametrize(
    ("outcome", "code"),
    [("installed", 0), ("partial", 0), ("not integrated", 0), ("incomplete", 2)],
)
def test_installed_fails_only_for_a_harness_refused_or_left_incomplete(
    capsys: pytest.CaptureFixture[str], outcome: HarnessOutcome, code: int
) -> None:
    error = "disk full" if outcome == "incomplete" else None
    report = HarnessReport("codex", outcome, ("a line",), error=error)
    with mock.patch.object(
        cli_integrate, "refresh_integrations", return_value=[report]
    ) as run:
        assert cli.main(["integrate", "--installed"]) == code

    run.assert_called_once_with()
    assert capsys.readouterr().out.splitlines() == ["Codex:", "  a line"]


@pytest.mark.parametrize(
    "argv",
    [["integrate", "--status"], ["integrate", "--installed", "--status"]],
)
def test_integrate_status_without_a_harness_reports_every_harness(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    combined = CombinedStatus(
        (
            HarnessReport("claude-code", "reported", ("installed in /c",)),
            HarnessReport("codex", "not integrated", note="not integrated (no /x)"),
        ),
        ("session records outside configured Projects: none",),
    )
    with mock.patch.object(
        cli_integrate, "integrations_status", return_value=combined
    ) as run:
        assert cli.main(argv) == 0

    run.assert_called_once_with((), current=current_directory())
    assert capsys.readouterr().out.splitlines() == [
        "Claude Code:",
        "  installed in /c",
        "Codex: not integrated (no /x)",
        "session records outside configured Projects: none",
    ]


def test_one_harness_named_twice_is_integrated_as_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        cli_integrate, "install_integration", return_value=["done"]
    ) as run:
        assert cli.main(["integrate", "codex", "codex"]) == 0

    run.assert_called_once_with("codex")
    assert capsys.readouterr().out == "done\n"


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
        mock.patch.object(launch, "DashpotApp") as app,
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
    _, bound, _ = cli_root.app.parse_args(argv, exit_on_error=False, print_error=False)
    bound.apply_defaults()
    return dict(bound.arguments)


def help_text(argv: list[str]) -> str:
    output = io.StringIO()
    console = Console(file=output, width=100, force_terminal=False, color_system=None)
    cli_root.app(argv, console=console, result_action="return_value")
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
            "--github-refresh-seconds",
            "120",
            "--unattended-seconds",
            "600",
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
        "github_refresh_seconds": 120.0,
        "unattended_seconds": 600.0,
        "state_dir": Path("/state"),
        "json_output": False,
        "compact_json": True,
    }


def test_default_command_defaults_match_observation_options() -> None:
    bound = parse([])

    assert bound["workspace"] is None
    assert bound["config"] is None
    assert bound["timeout"] == composition.ObservationOptions().timeout
    # An absent period flag defers to the settings file, then the default.
    assert bound["refresh_seconds"] is None
    assert bound["github_refresh_seconds"] is None
    assert bound["unattended_seconds"] is None
    assert bound["state_dir"] is None
    assert bound["json_output"] is False


def test_timeout_is_accepted_after_the_subcommand_it_applies_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(cli_init, "initialize_project", return_value=[]) as init:
        assert cli.main(["init", "--timeout", "5"]) == 0
    init.assert_called_once_with(Path.cwd().resolve(), markdown_path=None, timeout=5.0)

    with mock.patch.object(cli_work, "start_issue_work", return_value=[]) as start:
        assert cli.main(["work", "start", "12", "--timeout", "0.5"]) == 0
    start.assert_called_once_with(
        Path.cwd().resolve(), "12", timeout=0.5, outcome=mock.ANY
    )


@pytest.mark.parametrize(
    ("argv", "diagnostic"),
    [
        (["--workspace", "name="], "workspace must be PATH or NAME=PATH"),
        (["--workspace", "="], "workspace must be PATH or NAME=PATH"),
        (["--timeout", "0"], 'Invalid value "0.0" for --timeout. Must be > 0.'),
        (["--timeout", "-1"], "Must be > 0."),
        (["--timeout", "soon"], 'unable to convert "soon" into float'),
        (["--refresh-seconds", "-1"], "Must be >= 0."),
        (["--github-refresh-seconds", "-1"], "Must be >= 0."),
        (["--refresh-seconds", "inf"], "Must be a finite number of seconds."),
        (["--github-refresh-seconds", "inf"], "Must be a finite number of seconds."),
        (["--no-json"], "Unknown option: --no-json"),
        (["--empty-workspace"], "Unknown option: --empty-workspace"),
        (["--timeout", "5", "init"], "Unused Tokens: ['init']"),
        (["--bogus"], "Unknown option: --bogus"),
        (["work", "start"], "REFERENCE requires an argument"),
        (["work", "bogus"], 'Unknown command "bogus"'),
        (["issue", "show"], "REFERENCE requires an argument"),
        (["worktree", "create"], "REFERENCE requires an argument"),
        (["worktree", "create", "35", "--no-dry-run"], "Unknown option: --no-dry-run"),
        (["init", "--timeout", "0"], "Must be > 0."),
        (
            ["integrate"],
            "name a harness to integrate, or pass --installed to refresh every "
            "integrated harness",
        ),
        (["integrate", "emacs"], 'Choose from: "codex", "claude-code"'),
        (
            ["integrate", "codex", "--installed"],
            "name the harnesses to integrate or pass --installed, not both",
        ),
        (["integrate", "--remove"], "--remove takes exactly one named harness"),
        (
            ["integrate", "codex", "opencode", "--remove"],
            "--remove takes exactly one named harness",
        ),
        (
            ["integrate", "--installed", "--remove"],
            "--remove takes exactly one named harness",
        ),
        (
            ["integrate", "codex", "--status", "--remove"],
            "Mutually exclusive arguments: {--status, --remove}",
        ),
    ],
)
def test_invalid_input_fails_with_a_diagnostic_and_no_traceback(
    argv: list[str], diagnostic: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with mock.patch.object(cli_observe, "create_collector") as create_collector:
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
    for command in (
        "branch",
        "events",
        "init",
        "integrate",
        "issue",
        "work",
        "worktree",
    ):
        assert f" {command} " in text
    for option in (
        "--workspace",
        "--config",
        "--timeout",
        "--refresh-seconds",
        "--github-refresh-seconds",
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
    for command in ("relocate", "start", "stop", "show"):
        assert f" {command} " in work

    start = help_text(["work", "start", "--help"])
    assert "Usage: dashpot work start [OPTIONS] REFERENCE" in start

    relocate = help_text(["work", "relocate", "--help"])
    assert "Usage: dashpot work relocate PATH" in relocate

    create = help_text(["worktree", "create", "--help"])
    assert "Usage: dashpot worktree create [OPTIONS] REFERENCE" in create
    for option in ("--base", "--branch", "--worktree-root", "--dry-run", "--json"):
        assert option in create
    # The help is Markdown, which would take a bare placeholder for a tag.
    flat_create = " ".join(create.replace("│", " ").split())
    assert "defaults to <number>-<title-slug> (a Local Issue's slug)" in flat_create
    assert "the main working tree's sibling <main>.worktrees/" in flat_create
    for listing in (["issue", "list", "--help"], ["pr", "list", "--help"]):
        text = " ".join(help_text(listing).replace("│", " ").split())
        # These commands print JSON only, and say so.
        assert "instead of lines" not in text
        assert "as JSON" in text
        assert "accepted and ignored: the page is always printed as JSON" in text
        assert "[default: False]" not in text
        for option in ("--query", "--page-size", "--cursor", "--compact-json"):
            described = text.split(option, 1)[1].split(" --", 1)[0].strip()
            assert described and not described.startswith("["), option
            assert "[default:" not in described, option
    remove = help_text(["worktree", "remove", "--help"])
    assert "Usage: dashpot worktree remove [OPTIONS] PATH" in remove
    for option in ("--delete-branch", "--delete-ignored", "--dry-run", "--json"):
        assert option in remove
    delete = help_text(["branch", "delete", "--help"])
    assert "Usage: dashpot branch delete [OPTIONS] NAME" in delete
    for option in ("--local", "--remote", "--dry-run", "--json"):
        assert option in delete
    assert "Usage: dashpot issue show [OPTIONS] REFERENCE" in help_text(
        ["issue", "show", "--help"]
    )
    assert "Issue Reference" in start
    assert "--timeout" in start

    events = help_text(["events", "--help"])
    assert "Usage: dashpot events COMMAND [OPTIONS]" in events
    for option in ("--session", "--issue", "--project", "--since", "--level", "--json"):
        assert option in events
    assert " remove " in events
    # Where a dashboard's events about another Project are kept.
    assert "the checkout it was started in" in " ".join(events.split())
    events_remove = help_text(["events", "remove", "--help"])
    assert "Usage: dashpot events remove --before DATE [OPTIONS]" in events_remove
    for option in ("--dry-run", "--json"):
        assert option in events_remove

    stop = help_text(["work", "stop", "--help"])
    assert "--session" in stop
    assert "orphaned Agent Run" in stop

    init = help_text(["init", "--help"])
    assert "--markdown" in init
    assert "--timeout" in init

    integrate = help_text(["integrate", "--help"])
    assert "Usage: dashpot integrate [OPTIONS] [HARNESS...]" in integrate
    assert "--installed" in integrate
    assert "[choices: codex, claude-code, opencode]" in integrate
    assert "--status" in integrate
    assert "--remove" in integrate
    assert "integration and bundled skills" in integrate


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
    assert set(get_args(cli_integrate.Harness)) == set(INTEGRATIONS)


def test_python_dash_m_dashpot_exits_with_the_cli_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dashpot.cli.main", lambda: 3)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("dashpot", run_name="__main__")

    assert excinfo.value.code == 3
