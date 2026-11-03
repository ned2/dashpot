"""Run a committed trace's strict check and say whose change drifted each source.

A retained ``verify.mjs`` under ``--strict`` fails with a Node stack trace
when a source its trace hashed has changed since the run. This wrapper runs
it, catches that failure, and lists each drifted source as changed by the
PR's own diff or by ``main`` since the run's base, so the rule in AGENTS.md
can be applied: a source the PR changes must match the PR head, while drift
``main`` brought in is recorded in the PR rather than re-measured. The
retained verifiers stay as they are; editing one is itself a source change
under the source-hash rules. It serves a verifier that takes ``--strict``:
one that takes no such flag fails on the flag itself.

    uv run python scripts/trace_drift.py <verify.mjs> <trace> [verifier argument ...]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

DIGEST = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
# The line Node prints for an uncaught error, between its source excerpt and
# its stack: `AssertionError [ERR_ASSERTION]: <message>`.
UNCAUGHT = re.compile(r"^(?:\w*Error)(?: \[[A-Z_]+\])?: (.+)$")

Origin = Literal["this PR", "main", "neither"]
ORIGIN_LABELS: dict[Origin, str] = {
    "this PR": "changed by this PR",
    "main": "changed by main since the run's base",
    "neither": "changed by neither this PR nor main since the run's base",
}


@dataclass(frozen=True, slots=True)
class Drift:
    """A hashed source whose current content differs from the run's."""

    name: str
    origin: Origin | None
    # False when no candidate path exists in the checkout: the source moved,
    # was removed, or the trace names it relative to a directory this
    # wrapper does not know.
    found: bool


@dataclass(frozen=True, slots=True)
class RunBase:
    """The commit a trace's run is taken to start from, and where it came from."""

    commit: str
    recorded: bool


def git(root: Path, *arguments: str) -> str:
    """Read one Git fact from the checkout."""
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True
    ).strip()


def changed_names(root: Path, *arguments: str) -> set[str]:
    """The paths a ``git diff`` names, both sides of every rename included."""
    output = subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            *arguments,
        ]
    )
    return {os.fsdecode(name) for name in output.split(b"\0") if name}


def resolves(root: Path, revision: str) -> bool:
    """Whether a revision names a commit this checkout has."""
    return (
        subprocess.run(
            [
                *("git", "-C", str(root), "rev-parse", "--verify", "--quiet"),
                # Without the peel a full hash verifies whether or not Git has it.
                f"{revision}^{{commit}}",
            ],
            capture_output=True,
        ).returncode
        == 0
    )


def environment_record(trace: Path) -> dict[str, object]:
    """The trace's first record, which names the run's sources and their hashes."""
    opener = gzip.open if trace.suffix == ".gz" else open
    with opener(trace, "rt", encoding="utf-8") as lines:
        record: object = json.loads(lines.readline())
    if not isinstance(record, dict):
        raise ValueError(f"{trace} does not open with a JSON object")
    return {str(key): item for key, item in record.items()}


def recorded_head(environment: dict[str, object]) -> str | None:
    """The Dashpot commit the run recorded, under whichever key its runner used."""
    dashpot = environment.get("dashpot")
    candidates = [
        dashpot.get("head") if isinstance(dashpot, dict) else None,
        environment.get("dashpotHead"),
        environment.get("head"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and COMMIT.fullmatch(candidate):
            return candidate
    return None


def hashed_sources(value: object) -> Iterator[tuple[str, str]]:
    """Every ``(name, SHA-256)`` the run recorded of a working-tree source.

    Runners name their hash maps differently (``sourceSHA256``,
    ``experimentSHA256``, ``worktreeSourceSHA256`` …), so every map whose key
    ends ``SHA256`` and whose values are digests counts. A ``head…`` map
    records the committed copy beside the working tree's, and an object
    naming a ``revision`` read its sources from Git rather than the working
    tree, so neither is compared with the checkout.
    """
    if isinstance(value, list):
        for item in value:
            yield from hashed_sources(item)
    if not isinstance(value, dict) or "revision" in value:
        return
    for key, item in value.items():
        pairs = (
            [(name, digest) for name, digest in item.items()]
            if isinstance(item, dict)
            else []
        )
        digests = [
            (name, digest)
            for name, digest in pairs
            if isinstance(name, str)
            and isinstance(digest, str)
            and DIGEST.fullmatch(digest)
        ]
        if (
            isinstance(key, str)
            and key.endswith("SHA256")
            and not key.startswith("head")
            and digests
            and len(digests) == len(pairs)
        ):
            yield from digests
        else:
            yield from hashed_sources(item)


def candidates(root: Path, verifier: Path, name: str) -> list[str]:
    """The repository paths a hashed name can mean, most specific first.

    Runners name Dashpot's sources from the checkout root, their own helpers
    from the experiment's directory, a sibling experiment's helpers from
    ``scripts/experiments``, and a publisher's sources from the package.
    """
    experiment = verifier.resolve().parent.relative_to(root.resolve())
    bases = [
        PurePosixPath(),
        PurePosixPath(experiment.as_posix()),
        PurePosixPath("scripts", "experiments"),
        PurePosixPath("src", "dashpot"),
    ]
    return list(dict.fromkeys((base / name).as_posix() for base in bases))


def digest(path: Path) -> str:
    """The SHA-256 of a file's bytes, as the runners record it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drifted(
    root: Path, verifier: Path, environment: dict[str, object]
) -> list[tuple[str, list[str], bool]]:
    """Each hashed source that differs from the run, with the paths it can mean."""
    found: dict[str, tuple[str, list[str], bool]] = {}
    for name, recorded in hashed_sources(environment):
        paths = candidates(root, verifier, name)
        existing = next((path for path in paths if (root / path).is_file()), None)
        if existing is None:
            found.setdefault(name, (name, paths, False))
        elif digest(root / existing) != recorded:
            found.setdefault(existing, (existing, [existing], True))
    return sorted(found.values())


def classify(
    root: Path,
    verifier: Path,
    environment: dict[str, object],
    main: str,
) -> tuple[RunBase, list[Drift]]:
    """Attribute each drifted source to this PR's diff or to ``main`` since the run."""
    pr_base = git(root, "merge-base", main, "HEAD")
    head = recorded_head(environment)
    if head is not None and resolves(root, head):
        base = RunBase(head, recorded=True)
    else:
        base = RunBase(pr_base, recorded=False)
    # The PR's own diff: committed, staged, unstaged, and new untracked files.
    own = changed_names(root, pr_base) | {
        os.fsdecode(name)
        for name in subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"]
        ).split(b"\0")
        if name
    }
    from_main = changed_names(root, git(root, "merge-base", base.commit, main), pr_base)
    drift: list[Drift] = []
    for name, paths, found in drifted(root, verifier, environment):
        origin: Origin = (
            "this PR"
            if own.intersection(paths)
            else "main"
            if from_main.intersection(paths)
            else "neither"
        )
        if not found and origin == "neither":
            drift.append(Drift(name, None, found=False))
            continue
        shown = next((path for path in paths if path in own | from_main), name)
        drift.append(Drift(shown, origin, found=found))
    return base, drift


def failure(result: subprocess.CompletedProcess[str]) -> str:
    """The message of the error a verifier died of, without its stack."""
    for line in result.stderr.splitlines():
        if match := UNCAUGHT.match(line):
            return str(match[1])
    return f"it exited with status {result.returncode}"


def run_verifier(
    verifier: Path, trace: Path, arguments: Sequence[str], *, strict: bool
) -> subprocess.CompletedProcess[str]:
    """Run a retained verifier against its trace."""
    command = ["node", str(verifier), str(trace), *arguments]
    if strict:
        command.append("--strict")
    return subprocess.run(command, capture_output=True, text=True)


def report(
    root: Path,
    verifier: Path,
    trace: Path,
    arguments: Sequence[str],
    main: str,
) -> int:
    """Check one trace strictly; on failure, print its drift by origin."""
    strict = run_verifier(verifier, trace, arguments, strict=True)
    if strict.returncode == 0:
        sys.stdout.write(strict.stdout)
        return 0
    print(f"{trace}: {verifier} --strict failed: {failure(strict)}")
    lenient = run_verifier(verifier, trace, arguments, strict=False)
    if lenient.returncode == 0:
        print("Without --strict it passes, so the failure is source drift alone.")
    else:
        print(f"Without --strict it fails too: {failure(lenient)}")
    base, drift = classify(root, verifier, environment_record(trace), main)
    if base.recorded:
        print(f"The run's base: {base.commit}, as the trace records it.")
    else:
        print(
            "The trace records no run base this checkout has, so the run's base "
            f"is taken as the merge-base of HEAD and {main}: {base.commit}."
        )
    if not drift:
        print("No hashed source differs from the run's, so the failure is not drift.")
        return 1
    print("Drifted sources:")
    for origin, label in ORIGIN_LABELS.items():
        for item in drift:
            if item.origin == origin:
                note = "" if item.found else " (no longer in the checkout)"
                print(f"  {label}: {item.name}{note}")
    for item in drift:
        if item.origin is None:
            print(f"  not found in the checkout: {item.name}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Check a committed trace strictly and report its drift without a stack trace."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    parser.add_argument(
        "--main",
        default="origin/main",
        help="the integration branch the PR targets (default: origin/main)",
    )
    parser.add_argument("verifier", type=Path, help="the experiment's verify.mjs")
    parser.add_argument("trace", type=Path, help="the committed trace it checks")
    parser.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="further verifier arguments, passed before --strict",
    )
    options = parser.parse_args(argv)
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
        if not resolves(root, options.main):
            raise ValueError(f"{options.main} names no commit in this checkout")
        return report(
            root,
            options.verifier,
            options.trace,
            options.arguments,
            options.main,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Trace check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
