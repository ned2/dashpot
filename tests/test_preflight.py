import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

from dashpot import cli, preflight
from dashpot.cli import preflight as cli_preflight
from dashpot.core.commands import CommandError, CommandResult
from dashpot.preflight_probe import probe
from dashpot.project.settings import Settings


def repository(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def observed(**changes):
    return {
        "worktreeRoot": True,
        "gitDirectory": True,
        "uvCache": True,
        "preCommitCache": True,
        "remote": True,
        "ssh": None,
        "gitRemote": True,
        "authentication": True,
        **changes,
    }


def runner_for(document, calls, *, version="0.166.0", returncode=0):
    def run(args, cwd, timeout):
        calls.append((list(args), cwd, timeout))
        if args == ["codex", "--version"]:
            return CommandResult(list(args), 0, f"codex-cli {version}\n", "")
        return CommandResult(
            list(args), returncode, json.dumps(document), "SECRET-STDERR"
        )

    return run


def test_profile_is_checked_inside_the_sandbox_with_the_resolved_repository_paths(
    tmp_path, monkeypatch
):
    root = repository(tmp_path)
    calls = []
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    pool = tmp_path / "configured-pool"
    report = preflight.check_codex_profile(
        root,
        "operator-arc",
        runner=runner_for(observed(), calls),
        settings=Settings(worktree_root=pool),
        environ={},
    )
    assert report.passed
    assert report.worktree_root == str(pool)
    assert report.git_directory == str(root / ".git")
    args, cwd, timeout = calls[1]
    assert args[:5] == ["codex", "sandbox", "--profile", "operator-arc", "--"]
    assert args[5:8] == [sys.executable, "-I", "-S"]
    assert args[-4:] == [str(pool), str(root / ".git"), "origin", "10"]
    assert cwd == root and timeout > 10
    assert next(c.status for c in report.checks if c.name == "ssh") == "skipped"
    assert any("resumed thread" in limit for limit in report.limits)
    assert any("helper binaries" in limit for limit in report.limits)


def test_all_capability_failures_have_remedies_and_no_credential_output(
    tmp_path, monkeypatch
):
    root = repository(tmp_path)
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    response = observed(
        worktreeRoot=False,
        gitDirectory=False,
        uvCache=False,
        preCommitCache=False,
        ssh=False,
        gitRemote=False,
        authentication=False,
    )
    report = preflight.check_codex_profile(
        root, "arc", runner=runner_for(response, []), settings=Settings(), environ={}
    )
    assert not report.passed
    failed = [c for c in report.checks if c.status == "failed"]
    assert {c.name for c in failed} == {
        "worktree-root",
        "git-directory",
        "uv-cache",
        "pre-commit-cache",
        "ssh",
        "git-remote",
        "authentication",
    }
    assert all(c.remedy for c in failed)
    assert "SECRET" not in json.dumps(report.model_dump())
    assert "SECRET" not in "\n".join(preflight.describe_preflight(report))


@pytest.mark.parametrize(
    "response",
    [
        observed(extra="SECRET"),
        observed(uvCache="true"),
        observed(gitRemote=None),
        observed(remote=False, gitRemote=None, ssh=True),
        {},
        None,
    ],
)
def test_malformed_probe_output_never_looks_like_a_passing_preflight(
    tmp_path, monkeypatch, response
):
    root = repository(tmp_path)
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    report = preflight.check_codex_profile(
        root, "arc", runner=runner_for(response, []), settings=Settings(), environ={}
    )
    assert not report.passed
    assert report.checks[-1].name == "sandbox-probes"
    assert "SECRET" not in report.model_dump_json()


@pytest.mark.parametrize(
    "version,system",
    [("0.162.0", "Linux"), ("0.166.1", "Linux"), ("0.166.0", "Darwin")],
)
def test_unqualified_releases_and_platforms_never_run_the_sandbox(
    tmp_path, monkeypatch, version, system
):
    root = repository(tmp_path)
    calls = []
    monkeypatch.setattr(preflight.platform, "system", lambda: system)
    report = preflight.check_codex_profile(
        root,
        "arc",
        runner=runner_for(observed(), calls, version=version),
        settings=Settings(),
        environ={},
    )
    assert not report.passed
    assert len(calls) == 1
    assert report.checks[0].name == "qualification"


@pytest.mark.parametrize(
    "failure",
    [
        CommandError("SECRET timeout", code="command-timed-out"),
        FileNotFoundError("SECRET"),
    ],
)
def test_a_failed_sandbox_launch_is_reported_without_its_raw_error(
    tmp_path, monkeypatch, failure
):
    root = repository(tmp_path)
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")

    def run(args, cwd, timeout):
        if args == ["codex", "--version"]:
            return CommandResult(list(args), 0, "codex-cli 0.166.0", "")
        raise failure

    report = preflight.check_codex_profile(
        root, "arc", runner=run, settings=Settings(), environ={}
    )
    assert not report.passed
    assert report.checks[-1].name == "sandbox-probes"
    assert "SECRET" not in report.model_dump_json()


def test_root_precedence_matches_worktree_creation(tmp_path, monkeypatch):
    root = repository(tmp_path)
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    configured, environment, explicit = (
        tmp_path / p for p in ("setting", "environment", "explicit")
    )
    for option, env, expected in [
        (None, {}, configured),
        (None, {"DASHPOT_WORKTREE_ROOT": str(environment)}, environment),
        (explicit, {"DASHPOT_WORKTREE_ROOT": str(environment)}, explicit),
    ]:
        report = preflight.check_codex_profile(
            root,
            "arc",
            worktree_root_option=option,
            settings=Settings(worktree_root=configured),
            environ=env,
            runner=runner_for(observed(), []),
        )
        assert report.worktree_root == str(expected)


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("passed", [False, True])
def test_cli_reports_all_checks_and_uses_nonzero_status_on_failure(
    tmp_path, monkeypatch, capsys, json_output, passed
):
    report = preflight.CodexPreflight(
        profile="arc",
        version="0.166.0",
        worktree_root=str(tmp_path),
        git_directory=str(tmp_path / ".git"),
        remote="origin",
        checks=[
            preflight.PreflightCheck(
                name="authentication",
                status="passed" if passed else "failed",
                detail="Credential status only.",
                remedy=None if passed else "Provide approved authentication.",
            )
        ],
    )

    def check(current, profile, **kwargs):
        assert profile == "arc"
        return report

    monkeypatch.setattr(cli_preflight, "check_codex_profile", check)
    args = ["preflight", "codex", "--profile", "arc"] + (
        ["--json"] if json_output else []
    )
    assert cli.main(args) == (0 if passed else 2)
    output = capsys.readouterr()
    assert output.err == ""
    if json_output:
        document = json.loads(output.out)
        assert document["passed"] is passed
        assert document["checks"][0]["status"] == ("passed" if passed else "failed")
    else:
        assert "authentication" in output.out
        if not passed:
            assert "Provide approved authentication" in output.out


def executable(path, code):
    path.write_text(f"#!{sys.executable}\n{code}\n")
    path.chmod(0o755)


def test_probe_script_discards_authentication_output_with_stateless_tools(
    tmp_path,
):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    executable(
        binaries / "git",
        'import sys\nif sys.argv[1] == "remote": print("https://example.invalid/repository")\nsys.exit(0)',
    )
    executable(
        binaries / "gh",
        'import sys\nprint("SECRET-CREDENTIAL")\nprint("SECRET-CREDENTIAL", file=sys.stderr)\nsys.exit(1)',
    )
    environment = {
        "PATH": str(binaries) + os.pathsep + os.defpath,
        "UV_CACHE_DIR": str(cache),
        "PRE_COMMIT_HOME": str(cache),
    }
    before = set(tmp_path.rglob("*"))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(preflight.__file__).with_name("preflight_probe.py")),
            str(tmp_path),
            str(tmp_path),
            "origin",
            "2",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert "SECRET" not in result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document["ssh"] is None
    assert document["gitRemote"] is True
    assert document["authentication"] is False
    assert document["uvCache"] is True
    assert set(tmp_path.rglob("*")) == before


def test_probe_honors_the_operator_ssh_command_and_collects_other_failures(
    tmp_path, monkeypatch
):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(
        binaries / "git",
        'import sys\nif sys.argv[1] == "remote": print("ssh://git@example.invalid:2222/repository")\nsys.exit(0 if sys.argv[1] == "remote" else 1)',
    )
    executable(binaries / "gh", "import sys; sys.exit(1)")
    executable(
        binaries / "ssh",
        'import sys\nassert sys.argv[1:3] == ["-F", "operator-config"]\nassert sys.argv[-3:] == ["-p", "2222", "git@example.invalid"]\nsys.exit(0)',
    )
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.defpath)
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -F operator-config")
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setenv("PRE_COMMIT_HOME", "relative/cache")
    result = probe(str(tmp_path), str(tmp_path / "missing"), "origin", 2)
    assert result["ssh"] is True
    assert result["gitDirectory"] is False
    assert result["gitRemote"] is False
    assert result["authentication"] is False
    assert result["uvCache"] is False
    assert result["preCommitCache"] is False


def test_ssh_command_uses_the_same_shell_expansion_as_git(tmp_path, monkeypatch):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(
        binaries / "git",
        'import sys\nif sys.argv[1] == "remote": print("git@example.invalid:repository")\nsys.exit(0)',
    )
    executable(binaries / "gh", "import sys; sys.exit(0)")
    executable(
        binaries / "ssh",
        'import os,sys\nassert sys.argv[1:3] == ["-F", os.path.join(os.environ["HOME"],"approved config")]\nsys.exit(0)',
    )
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.defpath)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_SSH_COMMAND", 'ssh -F "$HOME/approved config"')
    assert probe(str(tmp_path), str(tmp_path), "origin", 2)["ssh"] is True


@pytest.mark.skipif(
    shutil.which("ssh") is None, reason="requires OpenSSH configuration parsing"
)
def test_operator_ssh_configuration_can_have_disclosed_side_effects(
    tmp_path, monkeypatch
):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(
        binaries / "git",
        'import sys\nif sys.argv[1] == "remote": print("git@example.invalid:repository")\nsys.exit(0)',
    )
    executable(binaries / "gh", "import sys; sys.exit(0)")
    marker = tmp_path / "operator-side-effect"
    config = tmp_path / "ssh-config"
    config.write_text(
        f'Host *\n HostName example.invalid\nMatch exec "touch {marker}"\n BatchMode yes\n'
    )
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -F " + shlex.quote(str(config)))
    assert probe(str(tmp_path), str(tmp_path), "origin", 2)["ssh"] is True
    assert marker.exists()
    assert any("update their own state" in limit for limit in preflight.LIMITS)


@pytest.mark.skipif(
    sys.platform != "linux", reason="qualified Linux process-group cleanup and /proc"
)
@pytest.mark.parametrize("interrupt", [False, True])
def test_timeout_and_outer_interruption_stop_the_active_command_and_its_helper(
    tmp_path, interrupt
):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    marker = tmp_path / "helper-pids.json"
    helper = (
        "import json,os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f'Path({str(marker.with_suffix(".tmp"))!r}).write_text(json.dumps({{"child":os.getpid(),"leader":os.getppid()}})); '
        f"Path({str(marker.with_suffix('.tmp'))!r}).replace({str(marker)!r}); "
        "time.sleep(60)"
    )
    executable(
        binaries / "git",
        'import sys\nif sys.argv[1] == "remote": print("https://example.invalid/repository")\nsys.exit(0)',
    )
    executable(
        binaries / "gh",
        f'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",{helper!r}])\ntime.sleep(60)',
    )
    environment = {"PATH": str(binaries) + os.pathsep + os.defpath}
    args = [
        sys.executable,
        "-I",
        "-S",
        str(Path(preflight.__file__).with_name("preflight_probe.py")),
        str(tmp_path),
        str(tmp_path),
        "origin",
        "10" if interrupt else "1",
    ]
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment
    )
    pids = {}
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        pids = json.loads(marker.read_text())
        if interrupt:
            process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        assert stderr == ""
        if interrupt:
            assert process.returncode == 128 + signal.SIGTERM
        else:
            assert process.returncode == 0
            assert json.loads(stdout)["authentication"] is False
        for pid in pids.values():
            stat = Path(f"/proc/{pid}/stat")
            assert not stat.exists() or stat.read_text().split(") ", 1)[1].startswith(
                "Z "
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for pid in pids.values():
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
