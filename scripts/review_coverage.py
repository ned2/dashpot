"""Collect and verify local coverage evidence for a fixed review base."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from ci_lane import documentation_path

from dashpot.core.pydantic import ConfigModel

REPORT_DIRECTORY = ".review-coverage"


class Evidence(ConfigModel):
    """Associate a successful coverage run with its source and environment."""

    schema_version: Literal[2] = 2
    base_commit: str
    head_commit: str
    source_digest: str
    # Each fingerprinted path's mode and content hash, so a later check can
    # name the paths that changed rather than only detect that some did.
    sources: dict[str, str]
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


@dataclass(frozen=True, slots=True)
class Verified:
    """Evidence that still stands, with the documentation it was accepted across."""

    evidence: Evidence
    # Documentation paths changed since the coverage run, which leave its
    # evidence standing; empty when the sources are exactly the run's.
    documentation_delta: tuple[str, ...]


def source_entries(root: Path) -> dict[str, str]:
    """Each tracked and non-ignored new file's mode and content hash, by path."""
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
    entries: dict[str, str] = {}
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
        entries[name] = f"{mode} {hashlib.sha256(data).hexdigest()}"
    return entries


def digest_of(entries: Mapping[str, str]) -> str:
    """Fingerprint source entries independently of staging."""
    # Names sort by their bytes, so the digest stays the one this gate has
    # always computed.
    ordered = sorted(entries, key=os.fsencode)
    listed = [[name, *entries[name].split(" ")] for name in ordered]
    return hashlib.sha256(json.dumps(listed, ensure_ascii=True).encode()).hexdigest()


def source_digest(root: Path) -> str:
    """Fingerprint tracked and non-ignored new files independently of staging."""
    return digest_of(source_entries(root))


def report_digest(root: Path) -> str:
    """Identify the exact coverage report supplied to review."""
    return hashlib.sha256(
        (root / REPORT_DIRECTORY / "coverage.json").read_bytes()
    ).hexdigest()


def collect(root: Path, base: str, workers: int | None = None) -> Evidence:
    """Run the full suite once and publish evidence only for unchanged sources."""
    directory = root / REPORT_DIRECTORY
    directory.mkdir(exist_ok=True)
    manifest = directory / "evidence.json"
    manifest.unlink(missing_ok=True)
    report = directory / "coverage.json"
    report.unlink(missing_ok=True)
    if workers is not None and workers < 0:
        raise ValueError("Workers must be zero (serial) or a positive count")
    if os.environ.get("PYTEST_ADDOPTS"):
        raise ValueError("Unset PYTEST_ADDOPTS so coverage verifies the full suite")
    base_commit = git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    before = source_entries(root)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--durations=0",
        "--cov",
        "--cov-report=term-missing",
        f"--cov-report=json:{REPORT_DIRECTORY}/coverage.json",
    ]
    if workers is not None:
        command.extend(["-n", str(workers), "--dist=load", "--max-worker-restart=0"])
    environment = {**os.environ, "COVERAGE_FILE": str(directory / ".coverage")}
    subprocess.run(command, cwd=root, env=environment, check=True)
    if source_entries(root) != before:
        raise ValueError("Source files changed during coverage; run it again")
    evidence = Evidence(
        base_commit=base_commit,
        head_commit=git(root, "rev-parse", "HEAD"),
        source_digest=digest_of(before),
        sources=before,
        coverage_digest=report_digest(root),
        python=platform.python_version(),
        platform=platform.platform(),
        coverage_version=version("coverage"),
        command=command,
        completed_at=datetime.now(UTC).isoformat(),
    )
    manifest.write_text(evidence.model_dump_json(indent=2) + "\n")
    return evidence


def verify(root: Path, base: str) -> Verified:
    """Reject missing, replaced, or stale coverage evidence before review or push.

    Evidence still stands when every path changed since the run is
    documentation as CI's lane classifier defines it; those paths are
    returned so the caller can report them.
    """
    evidence = Evidence.model_validate_json(
        (root / REPORT_DIRECTORY / "evidence.json").read_text()
    )
    if evidence.base_commit != git(root, "rev-parse", "--verify", f"{base}^{{commit}}"):
        raise ValueError("Review base changed; collect coverage for the intended base")
    if digest_of(evidence.sources) != evidence.source_digest:
        raise ValueError("Evidence sources do not match its digest; run it again")
    if evidence.coverage_digest != report_digest(root):
        raise ValueError("Coverage report changed since collection; run it again")
    current = source_entries(root)
    changed = sorted(
        name
        for name in evidence.sources.keys() | current.keys()
        if evidence.sources.get(name) != current.get(name)
    )
    rerun = [name for name in changed if not documentation_path(name)]
    if rerun:
        raise ValueError(
            f"Source files changed since coverage; run it again: {', '.join(rerun)}"
        )
    return Verified(evidence, tuple(changed))


def main() -> int:
    """Collect coverage or verify its association with the current checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", required=True, help="fixed commit or ref used for review"
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="override the repository's automatic worker count; 0 runs serially",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify existing evidence without running tests",
    )
    arguments = parser.parse_args()
    accepted: tuple[str, ...] = ()
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
        if arguments.check:
            verified = verify(root, arguments.base)
            evidence, accepted = verified.evidence, verified.documentation_delta
        else:
            evidence = collect(root, arguments.base, arguments.workers)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Coverage evidence failed: {error}", file=sys.stderr)
        return 1
    print(f"Coverage evidence: {REPORT_DIRECTORY}/evidence.json")
    print(
        f"Review base: {evidence.base_commit}; source SHA-256: {evidence.source_digest}"
    )
    if accepted:
        print("Accepted documentation changed since coverage:")
        print("\n".join(f"  {name}" for name in accepted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
