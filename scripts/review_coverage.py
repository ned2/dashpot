"""Collect and verify local coverage evidence for a fixed review base."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from dashpot.models import ConfigModel

REPORT_DIRECTORY = ".review-coverage"


class Evidence(ConfigModel):
    """Associate a successful coverage run with its source and environment."""

    schema_version: Literal[1] = 1
    base_commit: str
    head_commit: str
    source_digest: str
    coverage_digest: str
    python: str
    platform: str
    coverage_version: str
    command: list[str]
    completed_at: str


def git(root: Path, *arguments: str) -> str:
    """Read Git facts from the selected checkout."""
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True
    ).strip()


def source_digest(root: Path) -> str:
    """Fingerprint tracked and non-ignored new files independently of staging."""
    names = subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ]
    )
    entries: list[tuple[str, str, str]] = []
    for raw_name in sorted(set(names.split(b"\0")) - {b""}):
        name = os.fsdecode(raw_name)
        path = root / name
        if path.is_symlink():
            data, mode = os.fsencode(os.readlink(path)), "symlink"
        elif path.is_file():
            data = path.read_bytes()
            mode = "executable" if path.stat().st_mode & 0o111 else "file"
        elif not path.exists():
            continue
        else:
            raise ValueError(f"Cannot fingerprint source entry: {name}")
        entries.append((name, mode, hashlib.sha256(data).hexdigest()))
    return hashlib.sha256(json.dumps(entries, ensure_ascii=True).encode()).hexdigest()


def report_digest(root: Path) -> str:
    """Identify the exact coverage report supplied to review."""
    return hashlib.sha256(
        (root / REPORT_DIRECTORY / "coverage.json").read_bytes()
    ).hexdigest()


def collect(root: Path, base: str) -> Evidence:
    """Run the full suite once and publish evidence only for unchanged sources."""
    directory = root / REPORT_DIRECTORY
    directory.mkdir(exist_ok=True)
    manifest = directory / "evidence.json"
    manifest.unlink(missing_ok=True)
    report = directory / "coverage.json"
    report.unlink(missing_ok=True)
    if os.environ.get("PYTEST_ADDOPTS"):
        raise ValueError("Unset PYTEST_ADDOPTS so coverage verifies the full suite")
    base_commit = git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    before = source_digest(root)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov",
        "--cov-report=term-missing",
        f"--cov-report=json:{REPORT_DIRECTORY}/coverage.json",
    ]
    environment = {**os.environ, "COVERAGE_FILE": str(directory / ".coverage")}
    subprocess.run(command, cwd=root, env=environment, check=True)
    if source_digest(root) != before:
        raise ValueError("Source files changed during coverage; run it again")
    evidence = Evidence(
        base_commit=base_commit,
        head_commit=git(root, "rev-parse", "HEAD"),
        source_digest=before,
        coverage_digest=report_digest(root),
        python=platform.python_version(),
        platform=platform.platform(),
        coverage_version=version("coverage"),
        command=command,
        completed_at=datetime.now(UTC).isoformat(),
    )
    manifest.write_text(evidence.model_dump_json(indent=2) + "\n")
    return evidence


def verify(root: Path, base: str) -> Evidence:
    """Reject missing, replaced, or stale coverage evidence before review or push."""
    evidence = Evidence.model_validate_json(
        (root / REPORT_DIRECTORY / "evidence.json").read_text()
    )
    if evidence.base_commit != git(root, "rev-parse", "--verify", f"{base}^{{commit}}"):
        raise ValueError("Review base changed; collect coverage for the intended base")
    if evidence.source_digest != source_digest(root):
        raise ValueError("Source files changed since coverage; run it again")
    if evidence.coverage_digest != report_digest(root):
        raise ValueError("Coverage report changed since collection; run it again")
    return evidence


def main() -> int:
    """Collect coverage or verify its association with the current checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", required=True, help="fixed commit or ref used for review"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify existing evidence without running tests",
    )
    arguments = parser.parse_args()
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
        evidence = (
            verify(root, arguments.base)
            if arguments.check
            else collect(root, arguments.base)
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Coverage evidence failed: {error}", file=sys.stderr)
        return 1
    print(f"Coverage evidence: {REPORT_DIRECTORY}/evidence.json")
    print(
        f"Review base: {evidence.base_commit}; source SHA-256: {evidence.source_digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
