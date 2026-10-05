"""Check that the suite's own Git configuration is the only one a test's Git reads."""

from __future__ import annotations

import os
from pathlib import Path

from factories import git, init_repository


def test_git_reads_only_the_suite_configuration(git_repository: Path) -> None:
    origins = {
        line.split("\t", 1)[0]
        for line in git(git_repository, "config", "--list", "--show-origin").split("\n")
    }

    assert origins == {
        f"file:{os.environ['GIT_CONFIG_GLOBAL']}",
        "file:.git/config",
    }


def test_a_test_commit_is_unsigned_by_the_suite_identity_on_main(
    tmp_path: Path,
) -> None:
    root = init_repository(tmp_path / "repo")
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {tmp_path / 'hook-ran'}\nexit 1\n")
    hook.chmod(0o755)

    git(root, "commit", "-q", "--allow-empty", "-m", "first")

    assert git(root, "log", "-1", "--format=%an <%ae> %G?") == (
        "Dashpot Tests <tests@example.invalid> N"
    )
    assert git(root, "branch", "--show-current") == "main"
    assert not (tmp_path / "hook-ran").exists()
