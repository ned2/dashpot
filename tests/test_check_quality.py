from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

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
