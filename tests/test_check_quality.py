from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The maintenance script is intentionally not part of the installed package.
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import check_quality  # ruff: ignore[module-import-not-at-top-of-file]

sys.path.pop(0)


def record_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, list[str]]]:
    calls: list[tuple[str, list[str]]] = []

    def run_gate(
        name: str,
        command: list[str],
        *,
        cwd: Path = check_quality.PROJECT_ROOT,
        env: object = None,
    ) -> None:
        del cwd, env
        calls.append((name, command))
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

    assert "Tests" in [name for name, _command in calls]


def test_pre_push_quality_gate_skips_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_gates(monkeypatch)

    check_quality.run_quality_gates(include_tests=False)

    assert "Tests" not in [name for name, _command in calls]


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
        command
        for name, command in calls
        if name == "Quality gates for pushed revision"
    )
    assert pushed_gate[-1] == "--skip-tests"
