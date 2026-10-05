"""Run the local quality gates.

Direct runs check the current working tree. Under the pre-push hook, the
`PRE_COMMIT_TO_REF` environment variable names the exact revision being pushed,
and that revision is checked in a temporary detached worktree instead. The
pre-push hook skips tests because CI runs them across the supported matrix.

Each run also warns, without failing, when Git does not run this Repository's
tracked hooks from `.githooks`; `--hooks-path-only` gives that warning alone,
for the commit hook that reaches a checkout whose hooks were never set up.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT_TO_REF = "PRE_COMMIT_TO_REF"
HOOKS_PATH = ".githooks"


def hooks_path_warning(configured: str | None) -> str | None:
    """The warning for a ``core.hooksPath`` other than the tracked hooks, if any."""
    if configured == HOOKS_PATH:
        return None
    found = "is unset" if configured is None else f"is {configured!r}"
    return (
        f"warning: core.hooksPath {found}, so Git does not run the tracked hooks "
        f"in {HOOKS_PATH}/. Run `git config core.hooksPath {HOOKS_PATH}` once "
        "from any checkout (README.md#development-setup)."
    )


def configured_hooks_path(checkout: Path = PROJECT_ROOT) -> str | None:
    """The ``core.hooksPath`` Git applies in this checkout, or None when unset."""
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def warn_about_hooks_path(checkout: Path = PROJECT_ROOT) -> None:
    """Print the hooks-path warning; CI commits nothing, so it never gets one."""
    if os.environ.get("CI"):
        return
    try:
        configured = configured_hooks_path(checkout)
    except OSError:
        # Without Git there are no hooks to run; the warning never fails a gate.
        return
    warning = hooks_path_warning(configured)
    if warning is not None:
        print(warning, file=sys.stderr, flush=True)


def run_gate(
    name: str,
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
) -> None:
    """Run one gate and stop immediately if it fails."""
    print(f"\n==> {name}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def uv_run(*arguments: str) -> list[str]:
    """Build a locked command in the project environment."""
    return ["uv", "run", "--locked", *arguments]


def is_null_ref(revision: str) -> bool:
    """Return whether Git represents this ref as a deletion."""
    return bool(revision) and set(revision) == {"0"}


def run_pushed_revision(revision: str, *, include_tests: bool = True) -> None:
    """Run the pushed revision's own quality gate in a detached worktree."""
    if is_null_ref(revision):
        print("Skipping quality gates for a deleted ref.")
        return

    with TemporaryDirectory(prefix="dashpot-pushed-ref-") as temporary_directory:
        checkout = Path(temporary_directory) / "checkout"
        worktree_added = False
        try:
            run_gate(
                "Checkout pushed revision",
                ["git", "worktree", "add", "--detach", str(checkout), revision],
            )
            worktree_added = True
            # Git exports GIT_DIR and friends to a hook run from a linked
            # worktree; inherited, they would point every git command in the
            # pushed-revision checkout (and the tests' own temporary
            # repositories) back at this worktree.
            child_environment = {
                name: value
                for name, value in os.environ.items()
                if name != PRE_COMMIT_TO_REF and not name.startswith("GIT_")
            }
            quality_command = uv_run("python", "scripts/check_quality.py")
            if not include_tests:
                quality_command.append("--skip-tests")
            run_gate(
                "Quality gates for pushed revision",
                quality_command,
                cwd=checkout,
                env=child_environment,
            )
        finally:
            if worktree_added:
                run_gate(
                    "Remove pushed revision worktree",
                    ["git", "worktree", "remove", "--force", str(checkout)],
                )


def run_quality_gates(*, include_tests: bool = True) -> None:
    """Run selected local gates with locked dependencies and temporary artifacts."""
    run_gate("Lockfile", ["uv", "lock", "--check"])
    run_gate("Ruff lint", uv_run("ruff", "check", "."))
    run_gate("Ruff format", uv_run("ruff", "format", "--check", "."))
    run_gate("Type checking", uv_run("ty", "check"))
    run_gate("Documents", uv_run("python", "scripts/maintain_docs.py"))
    if include_tests:
        run_gate("Tests", uv_run("pytest", "-q"))

    with TemporaryDirectory(prefix="dashpot-quality-") as temporary_directory:
        distributions = Path(temporary_directory) / "dist"
        run_gate(
            "Build distributions",
            ["uv", "build", "--no-sources", "--out-dir", str(distributions)],
        )
        archives = sorted(distributions.iterdir())
        wheels = [archive for archive in archives if archive.suffix == ".whl"]
        source_distributions = [
            archive for archive in archives if archive.name.endswith(".tar.gz")
        ]
        if len(wheels) != 1 or len(source_distributions) != 1:
            raise RuntimeError("Expected exactly one wheel and one source distribution")
        run_gate(
            "Inspect distributions",
            uv_run("python", "scripts/check_distributions.py", str(distributions)),
        )


def parse_options(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the quality gate's options."""
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip pytest because CI runs the supported test matrix",
    )
    selection.add_argument(
        "--hooks-path-only",
        action="store_true",
        help="only warn when Git does not run the tracked hooks; never fails",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the current tree directly, or the exact revision from pre-push."""
    options = parse_options(arguments)
    if options.hooks_path_only:
        warn_about_hooks_path()
        return 0
    include_tests = not bool(options.skip_tests)
    pushed_revision = os.environ.get(PRE_COMMIT_TO_REF)
    try:
        if pushed_revision:
            # The pushed revision's own gate is a direct run, which warns.
            run_pushed_revision(pushed_revision, include_tests=include_tests)
        else:
            warn_about_hooks_path()
            run_quality_gates(include_tests=include_tests)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nQuality gate failed: {error}", file=sys.stderr)
        return 1

    print("\nAll local quality gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
