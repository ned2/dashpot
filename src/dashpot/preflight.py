"""Verify an operator-written Codex Arc profile through bounded sandbox probes."""

from __future__ import annotations

import os
import platform
import re
import sys
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import (
    ConfigDict,
    StrictBool,
    ValidationError,
    computed_field,
    model_validator,
)

from .core.commands import CommandError, CommandRunner, run_command
from .core.git import Git
from .core.model import ObservationModel
from .core.pydantic import LaxSequence, PublishedModel
from .core.worktree_paths import main_worktree, worktree_root
from .project.settings import Settings, load_settings
from .repository.worktrees.create import resolve_worktree_root

QUALIFIED_VERSION = "0.166.0"
_DEFAULT_RUNNER: CommandRunner = partial(run_command, non_interactive=True)
LIMITS = (
    "Worktree Root uses the invoking Dashpot's settings and environment; keep them consistent with the intended Lead.",
    "Predicts a fresh launch with this profile, not a resumed thread's saved permissions, "
    "a managed daemon's environment, or a Worker's environment. Run the checks inside the session too.",
    "Filesystem probes create no files. Codex may refresh its helper binaries under $CODEX_HOME/tmp/arg0-linux/. "
    "Operator-configured transport/authentication tools may execute configuration commands and update their own state within the profile's grants.",
    "Git remote and gh authentication checks do not establish push, Issue/PR write, or merge permission.",
)


class PreflightCheck(ObservationModel):
    """One provisioning capability and the remedy for its failure."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    detail: str
    remedy: str | None = None


class CodexPreflight(ObservationModel):
    """The bounded capabilities observed under one operator-written launch profile."""

    profile: str
    version: str | None
    worktree_root: str
    git_directory: str
    remote: str
    checks: LaxSequence[PreflightCheck]
    limits: LaxSequence[str] = LIMITS

    @computed_field
    @property
    def passed(self) -> bool:
        """Whether every applicable check passed."""
        return bool(self.checks) and all(
            check.status != "failed" for check in self.checks
        )


class _ProbeObservation(PublishedModel):
    """The closed boolean-only response from the isolated probe."""

    model_config = ConfigDict(extra="forbid")
    worktree_root: StrictBool
    git_directory: StrictBool
    uv_cache: StrictBool
    pre_commit_cache: StrictBool
    remote: StrictBool
    ssh: StrictBool | None
    git_remote: StrictBool | None
    authentication: StrictBool

    @model_validator(mode="after")
    def consistent_remote_checks(self) -> _ProbeObservation:
        """Require a remote probe for a resolved remote and none without one."""
        if self.remote != (self.git_remote is not None):
            raise ValueError("inconsistent remote probe")
        if not self.remote and self.ssh is not None:
            raise ValueError("SSH probe without a remote")
        return self


_REMEDIES = {
    "worktree-root": "Grant the resolved Worktree Root in the operator-written profile, and create the directory if absent.",
    "git-directory": "Add an explicit write rule for the shared Git directory in the profile; this includes hooks and Git configuration.",
    "uv-cache": "Set UV_CACHE_DIR in the profile to an existing absolute directory covered by its write grants.",
    "pre-commit-cache": "Set PRE_COMMIT_HOME in the profile to an existing absolute directory covered by its write grants.",
    "remote": "Select an existing push remote with --remote; inspect its configuration outside the checker.",
    "ssh": "Select an operator-approved, qualified Git transport remedy for this profile and recheck its SSH configuration.",
    "git-remote": "Check the selected remote's reachability, profile network policy and transport credentials outside the checker.",
    "authentication": "Provide gh authentication through the documented external mechanism; keep credential values out of launch flags and reports.",
}


def _check(name: str, passed: bool | None, detail: str) -> PreflightCheck:
    """Translate one observation into a result and an actionable remedy."""
    status = "skipped" if passed is None else "passed" if passed else "failed"
    return PreflightCheck(
        name=name,
        status=status,
        detail=detail,
        remedy=_REMEDIES[name] if passed is False else None,
    )


def check_codex_profile(
    current: Path,
    profile: str,
    *,
    remote: str = "origin",
    worktree_root_option: Path | None = None,
    timeout: float = 10,
    runner: CommandRunner = _DEFAULT_RUNNER,
    git: Git | None = None,
    settings: Settings | None = None,
    environ: Mapping[str, str] | None = None,
) -> CodexPreflight:
    """Check one profile without loading its contents or changing its permissions."""
    adapter = git if git is not None else Git(current, timeout)
    checkout = worktree_root(current, adapter)
    records = adapter.worktree_records()
    root, _source = resolve_worktree_root(
        main_worktree(records),
        worktree_root_option,
        os.environ if environ is None else environ,
        load_settings() if settings is None else settings,
    )
    common = adapter.text("rev-parse", "--path-format=absolute", "--git-common-dir")
    version = None
    checks: list[PreflightCheck] = []
    try:
        result = runner(["codex", "--version"], checkout, timeout)
        match = (
            re.fullmatch(r"codex-cli (\d+\.\d+\.\d+)", result.stdout.strip())
            if result.returncode == 0
            else None
        )
        version = match[1] if match else None
    except (OSError, CommandError):
        pass
    qualified = version == QUALIFIED_VERSION and platform.system() == "Linux"
    checks.append(
        PreflightCheck(
            name="qualification",
            status="passed" if qualified else "failed",
            detail="Qualified for Codex 0.166.0 on Linux."
            if qualified
            else "The installed Codex release/platform could not be qualified; no sandbox probes ran.",
            remedy=None
            if qualified
            else "Use the retained qualified Codex 0.166.0 on Linux, or qualify the selected release/platform first.",
        )
    )
    if qualified:
        args = [
            "codex",
            "sandbox",
            "--profile",
            profile,
            "--",
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).with_name("preflight_probe.py")),
            str(root),
            common,
            remote,
            str(timeout),
        ]
        try:
            result = runner(args, checkout, timeout * 12 + 5)
            if result.returncode != 0:
                raise ValueError("probe failed")
            observed = _ProbeObservation.model_validate_json(result.stdout)
        except (OSError, CommandError, ValueError, ValidationError):
            checks.append(
                PreflightCheck(
                    name="sandbox-probes",
                    status="failed",
                    detail="The profile's sandbox probe failed, timed out, or returned an invalid result. Its raw output is withheld.",
                    remedy="Inspect the named profile and Codex sandbox diagnostics outside the checker; no grant or credential conclusion was made.",
                )
            )
        else:
            checks.extend(
                (
                    _check(
                        "worktree-root",
                        observed.worktree_root,
                        "Write-free directory grant check.",
                    ),
                    _check(
                        "git-directory",
                        observed.git_directory,
                        "Write-free shared Git-directory grant check.",
                    ),
                    _check(
                        "uv-cache",
                        observed.uv_cache,
                        "UV_CACHE_DIR must select an absolute writable directory.",
                    ),
                    _check(
                        "pre-commit-cache",
                        observed.pre_commit_cache,
                        "PRE_COMMIT_HOME must select an absolute writable directory.",
                    ),
                    _check(
                        "remote",
                        observed.remote,
                        "The selected push remote must resolve inside the profile.",
                    ),
                    _check(
                        "ssh",
                        observed.ssh,
                        "SSH configuration parsing, or not applicable to this remote.",
                    ),
                    _check(
                        "git-remote",
                        observed.git_remote,
                        "ls-remote against the push destination; not run if the remote did not resolve.",
                    ),
                    _check(
                        "authentication",
                        observed.authentication,
                        "gh auth status exit status only; output discarded.",
                    ),
                )
            )
    return CodexPreflight(
        profile=profile,
        version=version,
        worktree_root=str(root),
        git_directory=common,
        remote=remote,
        checks=checks,
    )


def describe_preflight(report: CodexPreflight) -> list[str]:
    """Render the capability results, remedies and qualification limits."""
    lines = [
        f"Codex profile {report.profile}: {'passed' if report.passed else 'failed'}",
        f"Worktree Root: {report.worktree_root}",
        f"Git directory: {report.git_directory}",
    ]
    for check in report.checks:
        lines.append(f"{check.status}: {check.name}: {check.detail}")
        if check.remedy:
            lines.append(f"  Remedy: {check.remedy}")
    return [*lines, *report.limits]
