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
        ('{"bogus": 1}', "unexpected fields: bogus"),
        ('{"worktreeRoot": ""}', "non-empty string"),
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


def test_default_settings_path_follows_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert default_settings_path() == tmp_path / "dashpot" / "settings.json"
