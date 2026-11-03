"""``dashpot preflight codex``: verify an operator-written Arc launch profile."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ..core.working_directory import current_directory
from ..preflight import check_codex_profile, describe_preflight
from ..serialization import codex_preflight_document, render_json
from .shared import USAGE_EXIT_CODE, JsonOutput, Timeout, print_lines

preflight = App(
    name="preflight",
    help="Verify an operator-written launch profile; configured tools may update state.",
)


@preflight.command(name="codex")
def codex_preflight(
    *,
    profile: Annotated[
        str, Parameter(help="NAME: an operator-written Codex profile to verify")
    ],
    remote: Annotated[
        str, Parameter(help="NAME: the push remote to check inside the profile")
    ] = "origin",
    worktree_root: Annotated[
        Path | None,
        Parameter(help="DIR: override the existing Worktree Root resolution"),
    ] = None,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Check directory grants, cache variables, Git transport and gh authentication.

    Filesystem probes create no files. Codex may refresh helper binaries,
    and operator-configured transport/authentication tools may update state.
    This predicts a fresh launch, not a resumed thread or a Worker's shell.
    """
    report = check_codex_profile(
        current_directory(),
        profile,
        remote=remote,
        worktree_root_option=worktree_root,
        timeout=timeout,
    )
    if json_output:
        print(render_json(codex_preflight_document(report)))
    else:
        print_lines(describe_preflight(report))
    return 0 if report.passed else USAGE_EXIT_CODE
