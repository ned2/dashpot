"""Run a committed trace's strict check and say whose change drifted each source.

A retained ``verify.mjs`` under ``--strict`` fails with a Node stack trace
when a source its trace hashed has changed since the run. This wrapper runs
it, catches that failure, and lists each drifted source as changed by the
PR's own diff or by ``main`` since the run's base, so the rule in AGENTS.md
can be applied: a source the PR changes must match the PR head, while drift
``main`` brought in is recorded in the PR rather than re-measured. The
retained verifiers stay as they are; editing one is itself a source change
under the source-hash rules. A verifier that takes no ``--strict`` runs
without it, and the wrapper's own comparison of the trace's hashes stands in
for the flag.

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
STACK_FRAME = re.compile(r"^\s+at ")

Origin = Literal["this PR", "main", "neither", "unknown", "missing"]
ORIGIN_LABELS: dict[Origin, str] = {
    "this PR": "changed by this PR",
    "main": "changed by main since the run's base",
    "neither": "changed by neither this PR nor main since the run's base",
    "unknown": "not changed by this PR; with no recorded base, main's part is unknown",
    "missing": "not found in the checkout",
}


@dataclass(frozen=True, slots=True)
class Hashed:
    """A source the trace hashed that the checkout no longer matches."""

    name: str
    # The repository paths the hashed name can mean: the one found, or every
    # candidate when none exists.
    paths: tuple[str, ...]
    found: bool


@dataclass(frozen=True, slots=True)
class Drift:
    """A hashed source whose current content differs from the run's."""

    name: str
    origin: Origin
    # False when the source is gone from the checkout: moved, removed, or
    # named relative to a directory this wrapper does not know.
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
            *("git", "-C", str(root), "diff", "--name-only", "--no-renames", "-z"),
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
    """The trace's environment record, which names the run's sources and hashes.

    It is usually the first record, but some runners write another first.
    """
    opener = gzip.open if trace.suffix == ".gz" else open
    with opener(trace, "rt", encoding="utf-8") as lines:
        for line in lines:
            record: object = json.loads(line)
            if isinstance(record, dict) and record.get("kind") == "environment":
                return {str(key): item for key, item in record.items()}
    raise ValueError(f"{trace} has no environment record")


def recorded_head(environment: dict[str, object]) -> str | None:
    """The Dashpot commit the run recorded, under whichever key its runner used."""
    nested = [environment.get(key) for key in ("dashpot", "checkout")]
    candidates = [
        *(item.get("head") for item in nested if isinstance(item, dict)),
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
    ends ``SHA256`` and whose values are digests counts; a ``null`` among them
    marks a source the runner could not hash. A ``head…`` map
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
        pairs = [
            (name, recorded)
            for name, recorded in (item.items() if isinstance(item, dict) else [])
            if recorded is not None
        ]
        digests = [
            (name, recorded)
            for name, recorded in pairs
            if isinstance(name, str)
            and isinstance(recorded, str)
            and DIGEST.fullmatch(recorded)
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


def candidates(root: Path, verifier: Path, name: str) -> tuple[str, ...]:
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
    return tuple(dict.fromkeys((base / name).as_posix() for base in bases))


def digest(path: Path) -> str:
    """The SHA-256 of a file's bytes, or of a directory's tree, as runners record it.

    A directory, named with a trailing slash, hashes each file's relative
    name, a NUL and its bytes, in name order.
    """
    if not path.is_dir():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    tree = hashlib.sha256()
    for name in sorted(item.relative_to(path).as_posix() for item in path.rglob("*")):
        if (path / name).is_file():
            tree.update(name.encode() + b"\0" + (path / name).read_bytes())
    return tree.hexdigest()


def drifted(root: Path, verifier: Path, environment: dict[str, object]) -> list[Hashed]:
    """Each hashed source that differs from the run, with the paths it can mean."""
    by_name: dict[str, Hashed] = {}
    for name, recorded in hashed_sources(environment):
        paths = candidates(root, verifier, name)
        existing = next((path for path in paths if (root / path).exists()), None)
        if existing is None:
            by_name.setdefault(name, Hashed(name, paths, found=False))
        elif digest(root / existing) != recorded:
            by_name.setdefault(existing, Hashed(existing, (existing,), found=True))
    return sorted(by_name.values(), key=lambda item: item.name)


def run_base(root: Path, environment: dict[str, object], pr_base: str) -> RunBase:
    """The run's recorded commit when this checkout has it, else the PR's base."""
    head = recorded_head(environment)
    if head is not None and resolves(root, head):
        return RunBase(head, recorded=True)
    return RunBase(pr_base, recorded=False)


def existed(root: Path, commit: str, paths: tuple[str, ...]) -> bool:
    """Whether any of the paths was ever in the history that leads to a commit."""
    return bool(git(root, "rev-list", "-1", commit, "--", *paths))


def touches(names: set[str], paths: tuple[str, ...]) -> bool:
    """Whether a diff names any of the paths, or a file inside one that is a tree."""
    return any(
        name == path or name.startswith(f"{path}/") for name in names for path in paths
    )


def classify(
    root: Path, verifier: Path, environment: dict[str, object], main: str
) -> tuple[RunBase, str, list[Drift]]:
    """Attribute each drifted source to this PR's diff or to ``main`` since the run.

    Also returns the commit ``main``'s changes are counted from: the run's
    base where it is on ``main``, else where the run's branch left ``main``.
    """
    pr_base = git(root, "merge-base", main, "HEAD")
    base = run_base(root, environment, pr_base)
    # The PR's own diff: committed, staged, unstaged, and new untracked files.
    untracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"]
    )
    own = changed_names(root, pr_base) | {
        os.fsdecode(name) for name in untracked.split(b"\0") if name
    }
    since = git(root, "merge-base", base.commit, main)
    from_main = changed_names(root, since, pr_base)
    drift: list[Drift] = []
    for item in drifted(root, verifier, environment):
        origin: Origin = (
            "this PR"
            if touches(own, item.paths)
            else "main"
            if touches(from_main, item.paths)
            else "neither"
            if base.recorded
            else "unknown"
        )
        # Gone without a known cause: with a recorded base nothing since it
        # removed the source, so its name is relative to a directory this
        # wrapper does not know. Without one, a source the PR's base once had
        # was removed at an unknown point and still counts.
        if not item.found and (
            origin == "neither"
            or (origin == "unknown" and not existed(root, pr_base, item.paths))
        ):
            origin = "missing"
        shown = next(
            (path for path in item.paths if touches(own | from_main, (path,))),
            item.name,
        )
        drift.append(Drift(shown, origin, found=item.found))
    return base, since, drift


def failure(result: subprocess.CompletedProcess[str]) -> str:
    """The message of the error a verifier died of, without its stack."""
    lines = result.stderr.splitlines()
    for index, line in enumerate(lines):
        if match := UNCAUGHT.match(line):
            message = [str(match[1])]
            for following in lines[index + 1 :]:
                if STACK_FRAME.match(following):
                    break
                message.append(following)
            return "\n".join(message).rstrip()
    return f"it exited with status {result.returncode}"


def takes_strict(verifier: Path) -> bool:
    """Whether a retained verifier reads a ``--strict`` flag at all."""
    return '"--strict"' in verifier.read_text(encoding="utf-8")


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
    strict = takes_strict(verifier)
    result = run_verifier(verifier, trace, arguments, strict=strict)
    if strict and result.returncode == 0:
        sys.stdout.write(result.stdout)
        return 0
    base, since, drift = classify(root, verifier, environment_record(trace), main)
    # A name found nowhere was hashed relative to a directory this wrapper
    # cannot know, such as another experiment's runner: it is listed, but it
    # does not decide the verdict.
    checked = [item for item in drift if item.origin != "missing"]
    if not strict and result.returncode == 0 and not checked:
        sys.stdout.write(result.stdout)
        print("The verifier takes no --strict; every source found matches the run's.")
        print_drift(drift, "Hashed names not found in the checkout, so not checked:")
        return 0
    # Whether the failure is a verifier failure rather than a strict-only one.
    failed_plainly = not strict
    if strict:
        print(f"{trace}: {verifier} --strict failed: {failure(result)}")
        lenient = run_verifier(verifier, trace, arguments, strict=False)
        failed_plainly = lenient.returncode != 0
        if failed_plainly:
            print(f"Without --strict it fails too: {failure(lenient)}")
        elif checked:
            print("Without --strict it passes, so the failure is source drift alone.")
        else:
            print(
                "Without --strict it passes, yet no source this wrapper can find "
                "differs from the run's: read the verifier's message."
            )
    elif result.returncode != 0:
        print(f"{trace}: {verifier} failed: {failure(result)}")
    else:
        print(f"{trace}: {verifier} passes, but takes no --strict; its hashes drift.")
    if base.recorded:
        print(f"The run's base: {base.commit}, as the trace records it.")
        if since != base.commit:
            print(f"main's changes are counted from where the run left it: {since}.")
    else:
        print(
            "The trace records no run base this checkout has, so the run's base "
            f"is taken as the merge-base of HEAD and {main}: {base.commit}."
        )
    if failed_plainly and not checked:
        print("No hashed source differs from the run's, so the failure is not drift.")
    print_drift(drift, "Drifted sources:")
    return 1


def print_drift(drift: Sequence[Drift], heading: str) -> None:
    """List drifted sources under a heading, grouped by origin, if there are any."""
    if not drift:
        return
    print(heading)
    for origin, label in ORIGIN_LABELS.items():
        for item in drift:
            if item.origin == origin:
                note = "" if item.found or origin == "missing" else " (now removed)"
                print(f"  {label}: {item.name}{note}")


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
