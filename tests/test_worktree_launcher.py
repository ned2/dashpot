from __future__ import annotations

import subprocess
import sys
from unittest.mock import Mock

import pytest

from dashpot.core.commands import CommandResult
from dashpot.project.settings import SettingsFile, load_settings
from dashpot.repository.worktree_launcher import (
    WorktreeLauncher,
    configure_worktree_launcher,
    run_launch_command,
)


@pytest.mark.parametrize(
    "command",
    [[], [""], ["  "], ["{path}"], ["run", "\0"], ["./run"], ["~/run"], "run", [3]],
)
def test_invalid_launcher_settings_name_the_field(tmp_path, command):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="worktree_open_command"):
        SettingsFile.model_validate({"worktree_open_command": command})


@pytest.mark.parametrize(
    "command",
    [
        ["launcher"],
        ["launcher", "{path}"],
        ["launcher", "", "{path}", "{path}", "--dir={path}"],
    ],
)
def test_custom_launcher_preserves_literal_arguments_and_cwd(tmp_path, command):
    path = tmp_path / "space 日本語 #{pane_id};"
    path.mkdir()
    runner = Mock(return_value=CommandResult([], 0, "", ""))
    launcher = WorktreeLauncher(
        tuple(command), "%5", True, tmp_path / "config.toml", 7, runner
    )
    launcher(path)
    runner.assert_called_once_with(
        [str(path) if a == "{path}" else a for a in command], path, 7
    )


def test_toml_launcher_is_loaded_without_losing_root_or_unknown_fields(tmp_path):
    settings_file = tmp_path / "config.toml"
    settings_file.write_text(
        "worktree_root = 'trees'\nworktree_open_command = [\n'launcher',\n'{path}',\n]\nfuture = true\n"
    )
    settings = load_settings(settings_file)
    assert settings.worktree_root == tmp_path / "trees"
    assert settings.worktree_open_command == ("launcher", "{path}")
    config = configure_worktree_launcher(
        path=settings_file, environment={"TMUX": "socket", "TMUX_PANE": "%8"}
    )
    assert config.opener is not None
    assert config.diagnostics[0].code == "settings-unknown-field"


@pytest.mark.parametrize(
    "text", ["invalid toml", "worktree_open_command = []", "worktree_root = 3"]
)
def test_settings_failures_disable_launching_without_fallback(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    config = configure_worktree_launcher(
        path=path, environment={"TMUX": "socket", "TMUX_PANE": "%8"}
    )
    assert config.opener is None
    assert config.diagnostics[0].severity == "error"
    assert str(path) in config.diagnostics[0].message


def test_tmux_uses_explicit_origin_and_literal_path(tmp_path):
    path = tmp_path / "#{pane_id} #(printf unsafe) #;,;"
    path.mkdir()
    runner = Mock(return_value=CommandResult([], 0, "", ""))
    WorktreeLauncher(None, "%8", True, tmp_path / "config.toml", 3, runner)(path)
    expected = str(path).replace("#", "##")[:-1] + r"\;"
    runner.assert_called_once_with(
        ["tmux", "split-window", "-v", "-t", "%8", "-c", expected], path, 3
    )


@pytest.mark.parametrize("pane", [None, "", "1", "%1;", "unrelated"])
def test_invalid_tmux_origin_never_launches(tmp_path, pane):
    runner = Mock()
    with pytest.raises(RuntimeError, match="originating tmux pane"):
        WorktreeLauncher(None, pane, True, tmp_path / "config.toml", runner=runner)(
            tmp_path
        )
    runner.assert_not_called()


def test_outside_tmux_guidance_names_setting_and_copy_action(tmp_path):
    runner = Mock()
    with pytest.raises(
        RuntimeError, match=r"worktree_open_command.*config.toml.*press y"
    ):
        WorktreeLauncher(None, None, False, tmp_path / "config.toml", runner=runner)(
            tmp_path
        )
    runner.assert_not_called()


def test_missing_directory_is_not_repaired(tmp_path):
    runner = Mock()
    path = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="directory is unavailable"):
        WorktreeLauncher(
            ("launcher",), None, False, tmp_path / "config.toml", runner=runner
        )(path)
    assert not path.exists()
    runner.assert_not_called()


def test_custom_failure_does_not_fall_back_to_tmux(tmp_path):
    runner = Mock(return_value=CommandResult([], 2, "", "failed\nrequest"))
    with pytest.raises(RuntimeError, match="launcher exited 2: failed request"):
        WorktreeLauncher(
            ("launcher",), "%8", True, tmp_path / "config.toml", runner=runner
        )(tmp_path)
    assert runner.call_count == 1


def test_launch_command_captures_success_and_missing_executable(tmp_path):
    result = run_launch_command(
        [sys.executable, "-c", 'print("requested")'], tmp_path, 2
    )
    assert result.returncode == 0 and result.stdout.strip() == "requested"
    with pytest.raises(RuntimeError, match="cannot launch"):
        run_launch_command([str(tmp_path / "absent")], tmp_path, 2)


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="isolated Linux subreaper owns the orphaned test child",
)
@pytest.mark.parametrize("redirect", [False, True])
def test_request_with_persistent_child_is_bounded_and_child_is_not_killed(
    tmp_path, redirect
):
    # A separate supervisor adopts the request's child, so the test reaps every
    # process without changing pytest's process-wide child handling.
    script = r"""
import ctypes, os, signal, subprocess, sys, time
from pathlib import Path
from dashpot.repository.worktree_launcher import run_launch_command
assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
root=Path(sys.argv[1]); redirect=sys.argv[2]=='True'
pidfile=root/'child.pid'
child="import time; time.sleep(30)"
request="import subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c',"+repr(child)+"],"+("stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL," if redirect else "")+"); Path("+repr(str(pidfile))+").write_text(str(p.pid))"
try:
    started=time.monotonic()
    try:
        result=run_launch_command([sys.executable,'-c',request], root, 0.5)
        assert redirect and result.returncode==0
    except RuntimeError as error:
        assert not redirect and 'timed out' in str(error), error
    assert time.monotonic()-started < 3
    pid=int(pidfile.read_text())
    os.kill(pid,0)
finally:
    if pidfile.exists():
        pid=int(pidfile.read_text())
        os.kill(pid,signal.SIGKILL)
        os.waitpid(pid,0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(redirect)],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr
