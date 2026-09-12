from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashpot.settings import Settings, default_settings_path, load_settings


def test_absent_settings_are_the_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "config.toml") == Settings()


@pytest.mark.parametrize("text", ["", "# Preferences\n", "\n# Preferences\n\n"])
def test_empty_settings_select_defaults(tmp_path: Path, text: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text)
    assert load_settings(path) == Settings()


def test_worktree_root_is_read_and_relative_paths_anchor_at_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text("worktree_root = 'worktrees'\n")
    assert load_settings(path).worktree_root == tmp_path / "worktrees"

    path.write_text(f"worktree_root = {json.dumps(str(tmp_path / 'elsewhere'))}\n")
    assert load_settings(path).worktree_root == tmp_path / "elsewhere"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[]", "cannot read Dashpot settings"),
        ("worktree_root = ''", "worktree_root must be a non-empty string"),
        ("worktree_root = '  '", "worktree_root must be a non-empty string"),
        ("worktree_root = 3", "worktree_root must be a string"),
        ("worktree_root = true", "worktree_root must be a string"),
        ("worktree_root = 2026-09-12", "worktree_root must be a string"),
        ("worktree_root = []", "worktree_root must be a string"),
        ("[worktree_root]", "worktree_root must be a string"),
        ("worktree_root = null", "cannot read Dashpot settings"),
        ("worktree_root = 'a'\nworktree_root = 'b'", "cannot read Dashpot settings"),
        ('{"worktreeRoot": "worktrees"}', "cannot read Dashpot settings"),
    ],
)
def test_malformed_settings_are_refused(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(RuntimeError, match=message) as error:
        load_settings(path)
    assert str(path) in str(error.value)


@pytest.mark.parametrize("content", [b"worktree_root = '\xff'", None])
def test_unreadable_settings_report_the_source(
    tmp_path: Path, content: bytes | None
) -> None:
    path = tmp_path / "config.toml"
    if content is None:
        path.mkdir()
    else:
        path.write_bytes(content)
    with pytest.raises(RuntimeError, match="cannot read Dashpot settings") as error:
        load_settings(path)
    assert str(path) in str(error.value)


def test_unknown_fields_and_old_aliases_warn_without_overriding_known_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text("worktreeRoot = 'old'\nbogus = 1\nworktree_root = 'worktrees'\n")
    settings = load_settings(path)
    assert settings.worktree_root == tmp_path / "worktrees"
    (diagnostic,) = settings.diagnostics
    assert diagnostic.code == "settings-unknown-field"
    assert diagnostic.severity == "warning"
    assert diagnostic.source == f"settings:{path}"
    assert "bogus" in diagnostic.message and "worktreeRoot" in diagnostic.message

    path.write_text("worktreeRoot = 'old'\n")
    assert load_settings(path).worktree_root is None
    assert load_settings(path).diagnostics


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("worktree_root = '  worktrees '", "worktrees"),
        ("worktree_root = '日本語 worktrees'", "日本語 worktrees"),
        ('worktree_root = "a \\"quoted\\" path"', 'a "quoted" path'),
        ("worktree_root = 'null'", "null"),
        ("worktree_root = '$DASHPOT_ROOT'", "$DASHPOT_ROOT"),
        (r"worktree_root = 'literal\path'", r"literal\path"),
        (r'worktree_root = "escaped\\path"', r"escaped\path"),
    ],
)
def test_settings_strings_keep_path_semantics(
    tmp_path: Path, text: str, value: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    assert load_settings(path).worktree_root == tmp_path / value


def test_home_expansion_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("worktree_root = '~/worktrees'\n")
    assert load_settings(path).worktree_root == Path.home() / "worktrees"


@pytest.mark.parametrize("legacy", ['{"worktreeRoot": "old"}', "malformed JSON"])
@pytest.mark.parametrize("current", [None, "", "# Defaults", "worktree_root = 'new'"])
def test_default_loading_ignores_legacy_files_and_never_changes_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: str, current: str | None
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    directory = tmp_path / "dashpot"
    directory.mkdir()
    (directory / "settings.json").write_text(legacy)
    if current is not None:
        (directory / "config.toml").write_text(current)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    settings = load_settings()
    assert settings.worktree_root == (
        directory / "new" if current == "worktree_root = 'new'" else None
    )
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_explicit_path_is_toml_regardless_of_filename(tmp_path: Path) -> None:
    path = tmp_path / "custom.json"
    path.write_text("worktree_root = 'custom'\n")
    (tmp_path / "config.toml").write_text("worktree_root = 'sibling'\n")
    assert load_settings(path).worktree_root == tmp_path / "custom"
    assert load_settings(tmp_path / "absent") == Settings()


def test_default_settings_path_follows_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_settings_path() == tmp_path / "dashpot" / "config.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert default_settings_path() == Path.home() / ".config/dashpot/config.toml"
