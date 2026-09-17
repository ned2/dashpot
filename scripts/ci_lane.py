"""Select CI verification from the complete PR or candidate diff and enforce its results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import PurePosixPath


def documentation_path(name: str) -> bool:
    """Recognize documentation without skipping executable or configuration files."""
    path = PurePosixPath(name)
    return path.suffix == ".md" and (
        len(path.parts) == 1 or path.parts[0] in {"docs", "conformance"}
    )


# A pull request run classifies the branch diff; a merge queue run classifies
# the candidate the queue built on main. Every other invocation runs full.
DIFF_CLASSIFIED_EVENTS = frozenset({"pull_request", "merge_group"})


def classify(event: str, base: str, head: str, *, force_full: bool = False) -> str:
    """Require full verification unless a complete documentation diff is available."""
    if force_full or event not in DIFF_CLASSIFIED_EVENTS or not base or not head:
        return "full"
    try:
        # Disabling rename detection includes both paths of cross-boundary moves.
        changed = subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                f"{base}...{head}",
                "--",
            ]
        )
        names = [os.fsdecode(name) for name in changed.split(b"\0") if name]
    except (OSError, subprocess.CalledProcessError):
        return "full"
    return "docs" if names and all(map(documentation_path, names)) else "full"


def require_success(results: dict[str, object]) -> None:
    """Reject failures and every skip not authorized by a successful classification."""
    expensive = {"test", "build", "install", "minimum-git"}
    if set(results) != expensive | {"changes", "quality"}:
        raise ValueError("Unexpected CI jobs")
    # This bootstrap gate runs before dependencies are installed; use stdlib validation.
    changes = results["changes"]
    if not isinstance(changes, dict) or changes.get("result") != "success":
        raise ValueError("CI classification did not succeed")
    outputs = changes.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("lane") not in {"docs", "full"}:
        raise ValueError("Missing or invalid CI lane")
    lane = outputs["lane"]
    for name, job in results.items():
        expected = "skipped" if lane == "docs" and name in expensive else "success"
        if not isinstance(job, dict) or job.get("result") != expected:
            raise ValueError(f"{name} must report {expected}")


def main() -> None:
    """Publish the selected lane or validate the aggregate gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["classify", "require"])
    args = parser.parse_args()
    if args.action == "classify":
        lane = classify(
            os.environ.get("GITHUB_EVENT_NAME", ""),
            os.environ.get("PR_BASE_SHA", ""),
            os.environ.get("PR_HEAD_SHA", ""),
            force_full=os.environ.get("FORCE_FULL", "false") != "false",
        )
        print(f"lane={lane}")
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"lane={lane}\n")
    else:
        require_success(json.loads(os.environ["RESULTS"]))


if __name__ == "__main__":
    main()
