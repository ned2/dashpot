from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pytest

from factories import git

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The maintenance script is intentionally not part of the installed package.
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import check_quality  # ruff: ignore[module-import-not-at-top-of-file]

sys.path.pop(0)


@dataclass(frozen=True, slots=True)
class Gate:
    """One gate the quality script ran, with the directory and environment it got."""

    name: str
    command: list[str]
    cwd: Path
    env: Mapping[str, str] | None


def record_gates(
    monkeypatch: pytest.MonkeyPatch, *, failing: str | None = None
) -> list[Gate]:
    """Replace every gate with a recorder, raising for the gate named ``failing``."""
    calls: list[Gate] = []

    def run_gate(
        name: str,
        command: list[str],
        *,
        cwd: Path = check_quality.PROJECT_ROOT,
        env: Mapping[str, str] | None = None,
    ) -> None:
        calls.append(Gate(name, command, cwd, env))
        if name == failing:
            raise subprocess.CalledProcessError(1, command)
        if name == "Build distributions":
            distributions = Path(command[-1])
            distributions.mkdir()
            (distributions / "dashpot.whl").touch()
            (distributions / "dashpot.tar.gz").touch()

    monkeypatch.setattr(check_quality, "run_gate", run_gate)
    return calls


def test_direct_quality_gate_includes_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_gates(monkeypatch)

    check_quality.run_quality_gates()

    assert "Tests" in [gate.name for gate in calls]


def test_pre_push_quality_gate_skips_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_gates(monkeypatch)

    check_quality.run_quality_gates(include_tests=False)

    assert "Tests" not in [gate.name for gate in calls]


def test_skip_tests_option_configures_quality_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_selections: list[bool] = []
    monkeypatch.delenv(check_quality.PRE_COMMIT_TO_REF, raising=False)
    monkeypatch.setattr(
        check_quality,
        "run_quality_gates",
        lambda *, include_tests=True: test_selections.append(include_tests),
    )

    assert check_quality.main(["--skip-tests"]) == 0
    assert test_selections == [False]


def test_pre_push_forwards_test_skip_to_pushed_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = record_gates(monkeypatch)

    check_quality.run_pushed_revision("abc123", include_tests=False)

    pushed_gate = next(
        gate for gate in calls if gate.name == "Quality gates for pushed revision"
    )
    assert pushed_gate.command[-1] == "--skip-tests"


def test_pushed_revision_gate_runs_in_its_checkout_without_the_hook_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Git exports these to a pre-push hook run from a linked Worktree.
    monkeypatch.setenv("GIT_DIR", "/hook/worktree/.git")
    monkeypatch.setenv("GIT_INDEX_FILE", "/hook/worktree/.git/index")
    monkeypatch.setenv(check_quality.PRE_COMMIT_TO_REF, "abc123")
    monkeypatch.setenv("DASHPOT_QUALITY_KEPT", "kept")
    calls = record_gates(monkeypatch)

    check_quality.run_pushed_revision("abc123")

    checkout, pushed, removal = calls
    assert checkout.name == "Checkout pushed revision"
    assert checkout.command[-1] == "abc123"
    assert pushed.name == "Quality gates for pushed revision"
    assert pushed.cwd == Path(checkout.command[-2])
    assert pushed.env is not None
    assert pushed.env["DASHPOT_QUALITY_KEPT"] == "kept"
    assert not [
        name
        for name in pushed.env
        if name.startswith("GIT_") or name == check_quality.PRE_COMMIT_TO_REF
    ]
    assert removal.name == "Remove pushed revision worktree"
    assert removal.command[-1] == checkout.command[-2]


def test_a_failed_pushed_revision_gate_still_removes_its_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = record_gates(monkeypatch, failing="Quality gates for pushed revision")

    with pytest.raises(subprocess.CalledProcessError):
        check_quality.run_pushed_revision("abc123")

    checkout, _pushed, removal = calls
    assert removal.name == "Remove pushed revision worktree"
    assert removal.command == [
        "git",
        "worktree",
        "remove",
        "--force",
        checkout.command[-2],
    ]


def test_a_failed_checkout_removes_no_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = record_gates(monkeypatch, failing="Checkout pushed revision")

    with pytest.raises(subprocess.CalledProcessError):
        check_quality.run_pushed_revision("abc123")

    assert [gate.name for gate in calls] == ["Checkout pushed revision"]


def test_only_the_tracked_hooks_directory_is_a_configured_hooks_path() -> None:
    for spelling in (".githooks", ".githooks/", "./.githooks"):
        assert check_quality.hooks_path_warning(spelling) is None

    unset = check_quality.hooks_path_warning(None)
    elsewhere = check_quality.hooks_path_warning("/elsewhere/hooks")

    assert unset is not None
    assert "core.hooksPath is unset" in unset
    assert "git config core.hooksPath .githooks" in unset
    assert elsewhere is not None
    assert "core.hooksPath is '/elsewhere/hooks'" in elsewhere
    assert "git config core.hooksPath .githooks" in elsewhere


def test_the_hooks_path_is_read_from_the_checkouts_git_configuration(
    git_repository: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty_global = tmp_path / "empty-gitconfig"
    empty_global.touch()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_global))

    assert check_quality.configured_hooks_path(git_repository) is None

    git(git_repository, "config", "core.hooksPath", ".githooks")

    assert check_quality.configured_hooks_path(git_repository) == ".githooks"


def test_a_misconfigured_hooks_path_warns_without_failing_the_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv(check_quality.PRE_COMMIT_TO_REF, raising=False)
    monkeypatch.setattr(check_quality, "configured_hooks_path", lambda _checkout: None)
    calls = record_gates(monkeypatch)

    assert check_quality.main(["--skip-tests"]) == 0

    assert "core.hooksPath is unset" in capsys.readouterr().err
    assert "Lockfile" in [gate.name for gate in calls]


def test_hooks_path_only_warns_and_runs_no_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(check_quality.PRE_COMMIT_TO_REF, "abc123")
    monkeypatch.setattr(
        check_quality, "configured_hooks_path", lambda _checkout: "/elsewhere"
    )
    calls = record_gates(monkeypatch)

    assert check_quality.main(["--hooks-path-only"]) == 0

    assert "core.hooksPath is '/elsewhere'" in capsys.readouterr().err
    assert calls == []


def test_the_tracked_hooks_path_gives_no_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(
        check_quality, "configured_hooks_path", lambda _checkout: ".githooks"
    )

    assert check_quality.main(["--hooks-path-only"]) == 0

    assert capsys.readouterr().err == ""


def test_ci_gets_no_hooks_path_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(check_quality, "configured_hooks_path", lambda _checkout: None)

    assert check_quality.main(["--hooks-path-only"]) == 0

    assert capsys.readouterr().err == ""


def test_a_missing_git_gives_no_hooks_path_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert check_quality.main(["--hooks-path-only"]) == 0

    assert capsys.readouterr().err == ""


def test_the_pushed_revision_leaves_the_warning_to_its_own_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(check_quality.PRE_COMMIT_TO_REF, "abc123")
    monkeypatch.setattr(check_quality, "configured_hooks_path", lambda _checkout: None)
    record_gates(monkeypatch)

    assert check_quality.main(["--skip-tests"]) == 0

    assert "core.hooksPath" not in capsys.readouterr().err


# --- The tracked hook scripts ------------------------------------------------

FAKE_UV = """#!/bin/sh
record="$DASHPOT_FAKE_UV_RECORD"
printf 'cwd=%s\\n' "$(pwd -P)" >> "$record"
for argument in "$@"; do printf 'arg=%s\\n' "$argument" >> "$record"; done
printf 'stdin=%s\\n' "$(cat)" >> "$record"
printf 'end\\n' >> "$record"
"""


@dataclass(frozen=True, slots=True)
class HookCall:
    """One run of ``uv`` a tracked hook script made."""

    cwd: Path
    arguments: list[str]
    stdin: str


def recorded_hook_calls(record: Path) -> list[HookCall]:
    """Every ``uv`` run the fake recorded, oldest first."""
    calls: list[HookCall] = []
    cwd, arguments, stdin = Path(), [], ""
    for line in record.read_text().splitlines():
        key, _, value = line.partition("=")
        if key == "cwd":
            cwd, arguments, stdin = Path(value), [], ""
        elif key == "arg":
            arguments.append(value)
        elif key == "stdin":
            stdin = value
        elif line == "end":
            calls.append(HookCall(cwd, arguments, stdin))
        else:
            stdin += "\n" + line
    return calls


def hook_call(hook_type: str, *remaining: str) -> list[str]:
    """The ``uv`` arguments a tracked hook script passes, in any checkout."""
    return [
        "run",
        "--locked",
        "pre-commit",
        "hook-impl",
        "--config=.pre-commit-config.yaml",
        f"--hook-type={hook_type}",
        "--",
        *remaining,
    ]


class HookedRepository(NamedTuple):
    """A repository running the tracked hooks, and where the fake ``uv`` records."""

    checkout: Path
    record: Path


@pytest.fixture
def hooked_repository(
    git_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> HookedRepository:
    """A repository running the tracked hooks, and the fake ``uv``'s record."""
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    fake_uv = bin_directory / "uv"
    fake_uv.write_text(FAKE_UV)
    fake_uv.chmod(0o755)
    record = tmp_path / "uv-record"
    record.touch()
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("DASHPOT_FAKE_UV_RECORD", str(record))

    shutil.copytree(PROJECT_ROOT / ".githooks", git_repository / ".githooks")
    git(git_repository, "config", "core.hooksPath", ".githooks")
    git(git_repository, "add", ".githooks")
    git(git_repository, "commit", "-q", "-m", "Track the hooks")
    return HookedRepository(git_repository, record)


def test_each_checkout_runs_pre_commit_from_its_own_root(
    hooked_repository: HookedRepository, tmp_path: Path
) -> None:
    main_checkout, record = hooked_repository
    linked = tmp_path / "linked"
    git(main_checkout, "worktree", "add", "-q", "-b", "feature", str(linked))

    git(linked, "commit", "-q", "--allow-empty", "-m", "From the linked Worktree")
    git(main_checkout, "worktree", "remove", str(linked))
    git(main_checkout, "commit", "-q", "--allow-empty", "-m", "After its removal")

    first, from_linked, after_removal = recorded_hook_calls(record)
    for call, checkout in (
        (first, main_checkout),
        (from_linked, linked),
        (after_removal, main_checkout),
    ):
        assert call.cwd == checkout.resolve()
        assert call.arguments == hook_call("pre-commit")


def test_pre_push_passes_the_pushed_refs_on(
    hooked_repository: HookedRepository, tmp_path: Path
) -> None:
    checkout, record = hooked_repository
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(checkout, "remote", "add", "origin", str(remote))
    head = git(checkout, "rev-parse", "HEAD")

    git(checkout, "push", "-q", "origin", "main")

    push = recorded_hook_calls(record)[-1]
    assert push.cwd == checkout.resolve()
    assert push.arguments == hook_call("pre-push", "origin", str(remote))
    assert push.stdin == f"refs/heads/main {head} refs/heads/main {'0' * 40}"
