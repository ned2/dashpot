from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dashpot.agents import ProcessIdentity, write_hook_record
from dashpot.integrate import (
    CLAUDE_CODE_HOOK_EVENTS,
    CODEX_HOOK_EVENTS,
    codex_integration_status,
    install_codex_integration,
    install_integration,
    integration_status,
    remove_codex_integration,
    remove_integration,
)
from helpers import absent, present, unobservable

CODEX = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")


def session_record(session_id: str, state: str = "waiting") -> dict[str, Any]:
    return {
        "version": 2,
        "sessionId": session_id,
        "harness": "codex",
        "state": state,
        "cwd": "/repo",
        "repositoryRoot": "/repo",
        "branch": "main",
        "event": "Stop",
        "lastActivityAt": "2026-08-24T15:00:00Z",
        "sessionProcess": CODEX.as_record(),
    }


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


def read_hooks(home: Path) -> dict[str, Any]:
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


def test_a_publisher_path_containing_spaces_is_recognised(tmp_path: Path) -> None:
    # Ordinary on macOS: the publisher lives under a home directory with a
    # space, and the installer writes that path unquoted.
    home = codex_home(tmp_path)
    command = publisher(tmp_path / "My User")
    assert " " in str(command)
    install_codex_integration(home, command_path=command)
    before = (home / "hooks.json").read_text()

    messages = install_codex_integration(home, command_path=command)

    assert (home / "hooks.json").read_text() == before
    assert any("already installed" in message for message in messages)
    stop_groups = read_hooks(home)["hooks"]["Stop"]
    assert [
        handler["command"] for group in stop_groups for handler in group["hooks"]
    ] == [str(command)]
    status = "\n".join(codex_integration_status(home, current=tmp_path))
    assert f"installed in {home / 'hooks.json'}" in status
    remove_codex_integration(home)
    assert not (home / "hooks.json").exists()


def test_a_command_line_with_arguments_is_recognised_by_its_executable(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    handler = {
        "type": "command",
        "command": "/old/env/bin/dashpot-codex-hook --verbose",
        "timeout": 3,
    }
    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [handler]}]}})
    )

    install_codex_integration(home, command_path=publisher(tmp_path))

    stop_groups = read_hooks(home)["hooks"]["Stop"]
    assert len(stop_groups) == 1
    assert len(stop_groups[0]["hooks"]) == 1


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
        install_codex_integration(tmp_path / ".codex", command_path=publisher(tmp_path))


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

    messages = install_codex_integration(home, command_path=publisher(tmp_path))

    assert any("config.toml also defines hooks" in message for message in messages)


def test_config_toml_hook_trust_ledger_is_not_a_hook_definition(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    (home / "config.toml").write_text(
        "[hooks.state]\n\n"
        '[hooks.state."/x/.codex/hooks.json:post_tool_use:0:0"]\n'
        'trusted_hash = "sha256:abc"\nenabled = true\n'
    )

    messages = install_codex_integration(home, command_path=publisher(tmp_path))

    assert not any("also defines hooks" in message for message in messages)

    (home / "config.toml").write_text('[[hooks.Stop]]\ncommand = "x"\n')
    messages = codex_integration_status(
        home, state_dir=tmp_path / "state", current=tmp_path
    )
    assert any("also defines hooks" in message for message in messages)


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

    (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": []}]}}))
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

    messages = codex_integration_status(home, state_dir=state, current=tmp_path)

    joined = "\n".join(messages)
    assert f"installed in {home / 'hooks.json'}" in joined
    assert f"hook publisher: {command}" in joined
    assert (
        f"session records outside configured Projects: 1 in {state} "
        "(0 live, 0 unknown, 0 stale, 1 unreadable)"
    ) in joined


def test_status_lists_stale_session_records_without_pruning(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    install_codex_integration(home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    write_hook_record(session_record("0199-stale"), state)
    write_hook_record(session_record("0199-live"), state)

    messages = codex_integration_status(
        home, state_dir=state, current=tmp_path, lookup=absent()
    )

    joined = "\n".join(messages)
    assert (
        f"session records outside configured Projects: 2 in {state} "
        "(0 live, 0 unknown, 2 stale, 0 unreadable)"
    ) in joined
    assert (
        "  stale: Codex session 0199-stale last event Stop at "
        "2026-08-24T15:00:00Z, pid 4242 gone (no SessionEnd delivered)"
    ) in joined
    assert (state / "0199-stale.json").exists()

    messages = codex_integration_status(
        home, state_dir=state, current=tmp_path, lookup=present(CODEX)
    )
    assert "(2 live, 0 unknown, 0 stale, 0 unreadable)" in "\n".join(messages)


def test_status_shows_unknown_liveness_reasons(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    install_codex_integration(home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    write_hook_record(session_record("sandboxed"), state)

    messages = codex_integration_status(
        home,
        state_dir=state,
        current=tmp_path,
        lookup=unobservable("isolated-namespace"),
    )

    assert "(0 live, 1 unknown [isolated-namespace], 0 stale, 0 unreadable)" in (
        "\n".join(messages)
    )


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
    assert (
        f"session records for this Project: 1 in {sessions} "
        "(0 live, 0 unknown, 0 stale, 1 unreadable)"
    ) in joined


def claude_home(root: Path) -> Path:
    home = root / ".claude"
    home.mkdir(parents=True, exist_ok=True)
    return home


def claude_publisher(root: Path) -> Path:
    command = root / "bin" / "dashpot-claude-code-hook"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


def test_claude_code_install_merges_into_settings(tmp_path: Path) -> None:
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)
    (home / "settings.json").write_text(
        json.dumps(
            {
                "model": "opus",
                "permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "notify-send x"}]}
                    ]
                },
            }
        )
    )

    messages = install_integration("claude-code", home, command_path=command)

    document = json.loads((home / "settings.json").read_text())
    assert document["model"] == "opus"
    assert document["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert set(document["hooks"]) >= set(CLAUDE_CODE_HOOK_EVENTS)
    assert "Interrupt" not in document["hooks"]
    assert document["hooks"]["Stop"][0]["hooks"][0]["command"] == "notify-send x"
    assert document["hooks"]["Stop"][1]["hooks"][0]["command"] == str(command)
    assert any("Claude Code lifecycle hooks" in message for message in messages)


def test_claude_code_remove_keeps_unrelated_settings(tmp_path: Path) -> None:
    home = claude_home(tmp_path)
    (home / "settings.json").write_text(json.dumps({"model": "opus"}))
    install_integration("claude-code", home, command_path=claude_publisher(tmp_path))

    messages = remove_integration("claude-code", home)

    document = json.loads((home / "settings.json").read_text())
    assert document == {"model": "opus"}
    assert any("removed the Dashpot hooks" in message for message in messages)


def test_claude_code_status_and_missing_home(tmp_path: Path) -> None:
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)
    install_integration("claude-code", home, command_path=command)

    messages = integration_status(
        "claude-code", home, state_dir=tmp_path / "state", current=tmp_path
    )
    joined = "\n".join(messages)
    assert f"installed in {home / 'settings.json'}" in joined
    assert f"hook publisher: {command}" in joined

    state = tmp_path / "state"
    stale = {**session_record("claude-stale"), "harness": "claude-code"}
    write_hook_record(stale, state)
    messages = integration_status(
        "claude-code", home, state_dir=state, current=tmp_path, lookup=absent()
    )
    joined = "\n".join(messages)
    assert "(0 live, 0 unknown, 1 stale, 0 unreadable)" in joined
    assert "stale: Claude Code session claude-stale" in joined
    assert "no SessionEnd delivered" in joined

    with pytest.raises(RuntimeError, match="no Claude Code configuration"):
        install_integration("claude-code", tmp_path / "absent", command_path=command)


def test_each_harness_removal_only_touches_its_own_file(tmp_path: Path) -> None:
    codex = codex_home(tmp_path)
    claude = claude_home(tmp_path)
    install_integration("codex", codex, command_path=publisher(tmp_path))
    install_integration("claude-code", claude, command_path=claude_publisher(tmp_path))

    remove_integration("codex", codex)

    assert not (codex / "hooks.json").exists()
    document = json.loads((claude / "settings.json").read_text())
    assert set(document["hooks"]) == {*CLAUDE_CODE_HOOK_EVENTS, "PostToolUse"}


def test_unsupported_harness_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsupported harness"):
        install_integration("cursor", tmp_path)


def test_status_reports_the_identity_a_sandboxed_command_would_claim(
    tmp_path: Path,
) -> None:
    import subprocess

    from dashpot.agents import session_directory
    from dashpot.harnesses import SESSION_OVERRIDE_VARIABLE

    home = codex_home(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".dashpot").mkdir()
    (root / ".dashpot" / "config.json").write_text("{}")
    state = tmp_path / "state"

    none = codex_integration_status(
        home, state_dir=state, current=root, lookup=present(CODEX), environ={}
    )
    assert any(
        "Agent Session identity claimed here: none for Codex" in message
        and SESSION_OVERRIDE_VARIABLE in message
        for message in none
    )

    claimed = {"CODEX_THREAD_ID": "thread-9"}
    missing = codex_integration_status(
        home, state_dir=state, current=root, lookup=present(CODEX), environ=claimed
    )
    assert any(
        "Codex session thread-9 (from Codex environment), rejected: no "
        "lifecycle hook record" in message
        for message in missing
    )

    write_hook_record(
        {**session_record("thread-9", "running"), "repositoryRoot": str(root)},
        session_directory(root),
    )
    confirmed = codex_integration_status(
        home, state_dir=state, current=root, lookup=present(CODEX), environ=claimed
    )
    assert any(
        "Codex session thread-9 (from Codex environment), confirmed by its "
        "live hook record" in message
        for message in confirmed
    )

    explicit = codex_integration_status(
        home,
        state_dir=state,
        current=root,
        lookup=present(CODEX),
        environ={SESSION_OVERRIDE_VARIABLE: "codex:thread-9"},
    )
    assert any(
        f"thread-9 (from {SESSION_OVERRIDE_VARIABLE}), confirmed" in message
        for message in explicit
    )


def test_status_of_the_other_harness_does_not_borrow_a_claim(tmp_path: Path) -> None:
    from dashpot.harnesses import SESSION_OVERRIDE_VARIABLE

    home = tmp_path / ".claude"
    home.mkdir()

    messages = integration_status(
        "claude-code",
        home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ={SESSION_OVERRIDE_VARIABLE: "codex:thread-9", "CODEX_THREAD_ID": "x"},
    )

    assert any("none for Claude Code" in message for message in messages)


# --- Claude Code: PostToolUse matched to EnterWorktree alone (ADR 0009) ------


def test_claude_code_subscribes_post_tool_use_to_enter_worktree_alone(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)

    install_integration("claude-code", home, command_path=command)

    document = json.loads((home / "settings.json").read_text())
    assert document["hooks"]["PostToolUse"] == [
        {
            "matcher": "EnterWorktree",
            "hooks": [{"type": "command", "command": str(command), "timeout": 3}],
        }
    ]
    before = (home / "settings.json").read_text()
    messages = install_integration("claude-code", home, command_path=command)
    assert (home / "settings.json").read_text() == before
    assert any("already installed" in message for message in messages)
    status = integration_status(
        "claude-code", home, state_dir=tmp_path / "no-state", current=tmp_path
    )
    assert any("PostToolUse(EnterWorktree)" in message for message in status)
    assert not any("missing hook events" in message for message in status)

    remove_integration("claude-code", home)

    assert not (home / "settings.json").exists()


def test_claude_code_status_flags_a_missing_matched_hook(tmp_path: Path) -> None:
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)
    install_integration("claude-code", home, command_path=command)
    document = json.loads((home / "settings.json").read_text())
    del document["hooks"]["PostToolUse"]
    (home / "settings.json").write_text(json.dumps(document))

    messages = integration_status(
        "claude-code", home, state_dir=tmp_path / "no-state", current=tmp_path
    )

    missing = [message for message in messages if "missing hook events" in message]
    assert missing and "PostToolUse(EnterWorktree)" in missing[0]


def test_codex_subscribes_no_matched_events(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    install_codex_integration(home, command_path=publisher(tmp_path))

    assert "PostToolUse" not in read_hooks(home)
