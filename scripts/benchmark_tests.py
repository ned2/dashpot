"""Compare serial and parallel full-suite execution without changing test selection."""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from dashpot.models import ConfigModel


class BenchmarkRun(ConfigModel):
    """Record one full-suite execution."""

    workers: int
    repeat: int
    seconds: float
    returncode: int
    command: list[str]


class BenchmarkReport(ConfigModel):
    """Associate benchmark runs with their source and environment."""

    revision: str
    platform: str
    python: str
    cpu_count: int | None
    coverage: bool
    runs: list[BenchmarkRun]


def benchmark(output: Path, workers: list[int], repeats: int, coverage: bool) -> None:
    """Record repeated suite timings and reject changed test outcomes."""
    output.mkdir(parents=True, exist_ok=True)
    records: list[BenchmarkRun] = []
    baseline: list[tuple[str, str, str]] | None = None
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    # Interleave counts to reduce bias from machine load or cache warming.
    for repeat in range(repeats):
        for count in workers:
            directory = output / f"workers-{count}-repeat-{repeat + 1}"
            directory.mkdir(exist_ok=True)
            report = directory / "junit.xml"
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--durations=30",
                "-n",
                str(count),
                "--dist=load",
                "--max-worker-restart=0",
                f"--junitxml={report}",
            ]
            environment = dict(os.environ)
            if environment.get("PYTEST_ADDOPTS"):
                raise ValueError("Unset PYTEST_ADDOPTS for comparable full-suite runs")
            if coverage:
                command.extend(
                    [
                        "--cov",
                        "--cov-report=term-missing",
                        f"--cov-report=json:{directory / 'coverage.json'}",
                    ]
                )
                environment.update(
                    COVERAGE_FILE=str(directory / ".coverage"),
                    COVERAGE_DEBUG="sys,pid",
                    COVERAGE_DEBUG_FILE=str(directory / "coverage-debug.log"),
                )
            start = time.monotonic()
            with (directory / "pytest.log").open("w") as log:
                result = subprocess.run(
                    command, env=environment, stdout=log, stderr=subprocess.STDOUT
                )
            elapsed = time.monotonic() - start
            records.append(
                BenchmarkRun(
                    workers=count,
                    repeat=repeat + 1,
                    seconds=elapsed,
                    returncode=result.returncode,
                    command=command,
                )
            )
            metadata = BenchmarkReport(
                revision=revision,
                platform=platform.platform(),
                python=platform.python_version(),
                cpu_count=os.cpu_count(),
                coverage=coverage,
                runs=records,
            )
            (output / "results.json").write_text(
                metadata.model_dump_json(indent=2) + "\n"
            )
            print(
                f"workers={count} repeat={repeat + 1}: {elapsed:.2f}s exit={result.returncode}",
                flush=True,
            )
            if result.returncode:
                raise subprocess.CalledProcessError(result.returncode, command)
            cases = sorted(
                (
                    case.get("classname", ""),
                    case.get("name", ""),
                    "skipped" if case.find("skipped") is not None else "passed",
                )
                for case in ET.parse(report).iter("testcase")
            )
            if baseline is not None and cases != baseline:
                raise ValueError(
                    "Test identities or outcomes changed between benchmark runs"
                )
            baseline = cases
    for count in workers:
        times = [run.seconds for run in records if run.workers == count]
        print(f"workers={count}: median {statistics.median(times):.2f}s", flush=True)


def main() -> None:
    """Benchmark the current checkout using its installed development environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, nargs="+", default=[0, 2, 4])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1 or any(count < 0 for count in args.workers):
        parser.error("Repeats must be positive and worker counts nonnegative")
    benchmark(args.output.resolve(), args.workers, args.repeats, args.coverage)


if __name__ == "__main__":
    main()
