from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashpot.integrate import (
    CODEX_HOOK_EVENTS,
    codex_integration_status,
    install_codex_integration,
    remove_codex_integration,
)


def codex_home(root: Path) -> Path:
    home = root / ".codex"
    home.mkdir(parents=True, exist_ok=True)
    return home


def publisher(root: Path) -> Path:
    command = root / "bin" / "dashpot-codex-hook"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


def read_hooks(home: Path) -> dict:
    return json.loads((home / "hooks.json").read_text())


def test_fresh_install_registers_every_lifecycle_event(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)

    messages = install_codex_integration(home, command_path=command)

    document = read_hooks(home)
    assert set(document["hooks"]) == set(CODEX_HOOK_EVENTS)
    for event in CODEX_HOOK_EVENTS:
        assert document["hooks"][event] == [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": str(command),
                        "timeout": 3,
                    }
                ]
            }
        ]
    assert any("installed" in message for message in messages)
    assert any(str(command) in message for message in messages)


def test_install_is_idempotent(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)
    install_codex_integration(home, command_path=command)
    before = (home / "hooks.json").read_text()

    messages = install_codex_integration(home, command_path=command)

    assert (home / "hooks.json").read_text() == before
    assert any("already installed" in message for message in messages)


def test_install_preserves_foreign_hooks_and_unknown_keys(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)
    theirs = {
        "type": "command",
        "command": "notify-send done",
        "timeout": 5,
    }
    (home / "hooks.json").write_text(
        json.dumps(
            {
                "description": "user config",
                "hooks": {
                    "Stop": [{"matcher": "shell", "hooks": [theirs]}],
                    "PreToolUse": [{"hooks": [theirs]}],
                },
            }
        )
    )

    install_codex_integration(home, command_path=command)

    document = read_hooks(home)
    assert document["description"] == "user config"
    assert document["hooks"]["Stop"][0] == {
        "matcher": "shell",
        "hooks": [theirs],
    }
    assert document["hooks"]["PreToolUse"] == [{"hooks": [theirs]}]
    assert len(document["hooks"]["Stop"]) == 2


def test_install_replaces_a_stale_publisher_path(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    stale = {
        "type": "command",
        "command": "/old/env/bin/dashpot-codex-hook",
        "timeout": 3,
    }
    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [stale]}]}})
    )
    command = publisher(tmp_path)

    install_codex_integration(home, command_path=command)

    stop_groups = read_hooks(home)["hooks"]["Stop"]
    assert len(stop_groups) == 1
    assert stop_groups[0]["hooks"][0]["command"] == str(command)


def test_install_requires_an_existing_codex_home(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no Codex configuration directory"):
        install_codex_integration(
            tmp_path / ".codex", command_path=publisher(tmp_path)
        )


def test_malformed_hooks_file_is_an_error_and_left_untouched(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    (home / "hooks.json").write_text("{not json")

    with pytest.raises(RuntimeError, match="fix or move the file"):
        install_codex_integration(home, command_path=publisher(tmp_path))

    assert (home / "hooks.json").read_text() == "{not json"


def test_config_toml_hooks_coexistence_is_noted(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    (home / "config.toml").write_text('[hooks]\nStop = "something"\n')

    messages = install_codex_integration(
        home, command_path=publisher(tmp_path)
    )

    assert any("config.toml also defines hooks" in message for message in messages)


def test_remove_strips_only_the_dashpot_hooks(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    theirs = {"type": "command", "command": "notify-send done"}
    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [theirs]}]}})
    )
    install_codex_integration(home, command_path=publisher(tmp_path))

    messages = remove_codex_integration(home)

    document = read_hooks(home)
    assert document == {"hooks": {"Stop": [{"hooks": [theirs]}]}}
    assert any("removed the Dashpot hooks" in message for message in messages)


def test_remove_deletes_a_file_that_only_held_dashpot_hooks(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_codex_integration(home, command_path=publisher(tmp_path))

    messages = remove_codex_integration(home)

    assert not (home / "hooks.json").exists()
    assert any("contained only the Dashpot hooks" in message for message in messages)


def test_remove_without_installation_is_a_calm_message(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    assert "not installed" in remove_codex_integration(home)[0]

    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": []}]}})
    )
    assert "no Dashpot hooks" in remove_codex_integration(home)[0]


def test_install_then_remove_round_trips_a_user_file(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    original = {
        "description": "user config",
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]},
    }
    (home / "hooks.json").write_text(json.dumps(original))

    install_codex_integration(home, command_path=publisher(tmp_path))
    remove_codex_integration(home)

    assert read_hooks(home) == original


def test_status_reports_installed_state_and_records(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)
    install_codex_integration(home, command_path=command)
    state = tmp_path / "state"
    state.mkdir()
    (state / "session.json").write_text("{}")

    messages = codex_integration_status(
        home, state_dir=state, current=tmp_path
    )

    joined = "\n".join(messages)
    assert f"installed in {home / 'hooks.json'}" in joined
    assert f"hook publisher: {command}" in joined
    assert f"session records outside configured Projects: 1 in {state}" in joined


def test_status_flags_missing_events_and_publisher(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    gone = tmp_path / "bin" / "dashpot-codex-hook"
    (home / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": str(gone),
                                    "timeout": 3,
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )

    messages = codex_integration_status(
        home, state_dir=tmp_path / "no-state", current=tmp_path
    )

    joined = "\n".join(messages)
    assert "missing hook events" in joined
    assert "SessionStart" in joined
    assert "hook publisher missing" in joined
    assert "session records outside configured Projects: none" in joined


def test_status_when_nothing_is_installed(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    messages = codex_integration_status(
        home, state_dir=tmp_path / "state", current=tmp_path
    )

    assert "not installed" in messages[0]

    messages = codex_integration_status(
        tmp_path / "absent", state_dir=tmp_path / "state", current=tmp_path
    )
    assert "configuration directory not found" in messages[0]


def test_status_reports_the_current_projects_session_store(
    tmp_path: Path,
) -> None:
    import subprocess

    home = codex_home(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".dashpot").mkdir()
    (repo / ".dashpot" / "config.json").write_text("{}")
    sessions = repo / ".dashpot" / "state" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "one.json").write_text("{}")

    messages = codex_integration_status(
        home, state_dir=tmp_path / "state", current=repo
    )

    joined = "\n".join(messages)
    assert f"session records for this Project: 1 in {sessions}" in joined
