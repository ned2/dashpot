"""Keep benchmark comparisons complete and failures visible."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import benchmark_tests

sys.path.pop(0)


def fake_suite(monkeypatch, *, fail=False, change=False):
    commands = []
    original_run = subprocess.run
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    original = subprocess.check_output

    def revision(command, *args, **kwargs):
        if command == ["git", "rev-parse", "HEAD"]:
            return "revision\n"
        return original(command, *args, **kwargs)

    monkeypatch.setattr(benchmark_tests.subprocess, "check_output", revision)

    def run(command, **kwargs):
        if command[1:3] != ["-m", "pytest"]:
            return original_run(command, **kwargs)
        commands.append((command, kwargs["env"]))
        report = Path(
            next(
                arg.removeprefix("--junitxml=")
                for arg in command
                if arg.startswith("--junitxml=")
            )
        )
        name = "different" if change and len(commands) > 1 else "test_example"
        report.write_text(
            f'<testsuites><testsuite><testcase classname="tests.example" name="{name}"/></testsuite></testsuites>'
        )
        return subprocess.CompletedProcess(command, 1 if fail else 0)

    monkeypatch.setattr(benchmark_tests.subprocess, "run", run)
    return commands


def test_benchmark_records_interleaved_full_suite_commands_and_coverage(
    tmp_path, monkeypatch
):
    commands = fake_suite(monkeypatch)
    benchmark_tests.benchmark(tmp_path, [0, 2], 2, True)
    result = json.loads((tmp_path / "results.json").read_text())
    assert [run["workers"] for run in result["runs"]] == [0, 2, 0, 2]
    assert [run["repeat"] for run in result["runs"]] == [1, 1, 2, 2]
    assert result["revision"] == "revision"
    assert result["coverage"] is True
    for command, env in commands:
        assert "--cov" in command
        assert "--max-worker-restart=0" in command
        assert str(tmp_path) in env["COVERAGE_FILE"]
        assert env["COVERAGE_DEBUG"] == "sys,pid"
    assert len({env["COVERAGE_FILE"] for _, env in commands}) == 4


def test_platform_detection_can_use_a_subprocess(tmp_path, monkeypatch):
    commands = fake_suite(monkeypatch)
    monkeypatch.setattr(
        benchmark_tests.platform,
        "platform",
        lambda: subprocess.check_output(
            [sys.executable, "-c", "print('detected platform')"], text=True
        ).strip(),
    )
    benchmark_tests.benchmark(tmp_path, [0], 1, False)
    assert len(commands) == 1
    assert (
        json.loads((tmp_path / "results.json").read_text())["platform"]
        == "detected platform"
    )


def test_benchmark_failure_keeps_evidence_and_does_not_retry(tmp_path, monkeypatch):
    commands = fake_suite(monkeypatch, fail=True)
    with pytest.raises(subprocess.CalledProcessError):
        benchmark_tests.benchmark(tmp_path, [0, 2], 3, False)
    assert len(commands) == 1
    assert (
        json.loads((tmp_path / "results.json").read_text())["runs"][0]["returncode"]
        == 1
    )


def test_different_test_selection_cannot_claim_a_speedup(tmp_path, monkeypatch):
    fake_suite(monkeypatch, change=True)
    with pytest.raises(ValueError, match="identities or outcomes"):
        benchmark_tests.benchmark(tmp_path, [0, 2], 1, False)


def test_pytest_environment_cannot_filter_benchmarks(tmp_path, monkeypatch):
    commands = fake_suite(monkeypatch)
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k fast")
    with pytest.raises(ValueError, match="Unset PYTEST_ADDOPTS"):
        benchmark_tests.benchmark(tmp_path, [0], 1, False)
    assert not commands
