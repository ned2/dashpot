"""Exercise the release guard before any publishing job can run."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from factories import git

SCRIPT = Path(__file__).parents[1] / "scripts/check_release.py"
SPEC = importlib.util.spec_from_file_location("check_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_release_notes_select_only_the_matching_version():
    changelog = "# Changelog\n\n## 0.2.0\n\nNewer.\n\n## 0.1.0 — First release\n\nInitial.\n\n## 0.0.1\n\nOlder.\n"
    assert release.release_notes("v0.1.0", "0.1.0", changelog) == "Initial.\n"


@pytest.mark.parametrize("tag", ["main", "v0.1.0rc1", "v0.1.1", "v00.1.0", "v0.1.0\n"])
def test_invalid_or_mismatched_tag_is_refused(tag):
    with pytest.raises(ValueError):
        release.release_notes(tag, "0.1.0", "## 0.1.0\n\nInitial.\n")


@pytest.mark.parametrize("changelog", ["", "## 0.1.0\n\n", "## 0.1.1\n\nNewer.\n"])
def test_missing_or_empty_release_notes_are_refused(changelog):
    with pytest.raises(ValueError, match="Missing changelog"):
        release.release_notes("v0.1.0", "0.1.0", changelog)


@pytest.mark.parametrize("on_main", [True, False])
def test_release_guard_requires_the_commit_to_belong_to_main(
    tmp_path, monkeypatch, on_main
):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    git(
        tmp_path,
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--allow-empty",
        "-m",
        "Main",
    )
    if not on_main:
        git(tmp_path, "checkout", "-b", "candidate")
        git(
            tmp_path,
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--allow-empty",
            "-m",
            "Candidate",
        )
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "CHANGELOG.md").write_text("## 0.1.0\n\nInitial.\n")
    notes = tmp_path / "notes.md"
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "v0.1.0", "--main-ref", "main", "--notes", str(notes)],
    )
    if on_main:
        release.main()
        assert notes.read_text() == "Initial.\n"
    else:
        with pytest.raises(subprocess.CalledProcessError):
            release.main()
        assert not notes.exists()
