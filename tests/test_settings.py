from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashpot.settings import Settings, default_settings_path, load_settings


def test_absent_settings_are_the_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "settings.json") == Settings()


def test_worktree_root_is_read_and_relative_paths_anchor_at_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"worktreeRoot": "worktrees"}))

    assert load_settings(path).worktree_root == tmp_path / "worktrees"

    path.write_text(json.dumps({"worktreeRoot": str(tmp_path / "elsewhere")}))
    assert load_settings(path).worktree_root == tmp_path / "elsewhere"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[]", "must contain a JSON object"),
        ('{"worktreeRoot": ""}', "worktreeRoot must be a non-empty string"),
        ('{"worktreeRoot": 3}', "worktreeRoot must be a string"),
        ('{"worktreeRoot": true}', "worktreeRoot must be a string"),
        ("{", "cannot read Dashpot settings"),
    ],
)
def test_malformed_settings_are_refused(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(text)

    with pytest.raises(RuntimeError, match=message):
        load_settings(path)


def test_unknown_fields_are_ignored_with_a_diagnostic(tmp_path: Path) -> None:
    # A field written by a newer Dashpot must not stop this one starting.
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"bogus": 1, "worktreeRoot": "worktrees"}))

    settings = load_settings(path)

    assert settings.worktree_root == tmp_path / "worktrees"
    (diagnostic,) = settings.diagnostics
    assert diagnostic.code == "settings-unknown-field"
    assert diagnostic.severity == "warning"
    assert "bogus" in diagnostic.message


def test_the_worktree_root_setting_is_stripped_before_resolution(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"worktreeRoot": "  worktrees "}))

    assert load_settings(path).worktree_root == tmp_path / "worktrees"


def test_default_settings_path_follows_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert default_settings_path() == tmp_path / "dashpot" / "settings.json"
