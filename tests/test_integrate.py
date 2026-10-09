from __future__ import annotations

import dataclasses
import json
import os
import shlex
import shutil
import stat
import subprocess
import sysconfig
from collections.abc import Callable, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import pytest

from dashpot.core.model import Harness
from dashpot.repository.cleanup import DESPITE_SUBAGENTS_FLAG
from dashpot.repository.cleanup.obstacles import session_exit
from dashpot.sessions.harnesses import OPENCODE_ACCEPTED_VERSION, HarnessError
from dashpot.sessions.hook_records import HookRecord, HookRecordStore
from dashpot.sessions.integrate import (
    BUNDLED_SKILL_VERSION,
    BUNDLED_SKILLS,
    ISSUE_WORK_SKILL,
    BundledSkill,
    CombinedStatus,
    ConfigurationDirectory,
    HarnessOutcome,
    HarnessReport,
    IncompleteRemovalError,
    IntegrationEnvironment,
    IntegrationError,
    configuration_directory,
    install_integration,
    install_integrations,
    integration,
    integration_presence,
    integration_status,
    integration_totals,
    integrations_status,
    refresh_integrations,
    refuse_integrate_arguments,
    remove_integration,
    resolve_hook_command,
    skill_directory,
)
from factories import (
    CODEX,
    git,
    hook_record_document,
    init_repository,
    write_config_marker,
)
from helpers import absent, present, table_lookup, unobservable


def session_record(session_id: str, state: str = "waiting") -> dict[str, Any]:
    return hook_record_document(
        "/repo",
        session_id,
        "codex",
        CODEX,
        state=state,
        at="2026-08-24T15:00:00Z",
        event="Stop",
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


def read_hooks(home: Path) -> dict[str, Any]:
    return json.loads((home / "hooks.json").read_text())


def installed_skill(home: Path, harness: Harness = "codex") -> Path:
    return skill_directory(integration(harness), home, ISSUE_WORK_SKILL, os.environ)


def test_fresh_install_registers_every_lifecycle_event(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)

    messages = install_integration("codex", home, command_path=command)

    document = read_hooks(home)
    assert set(document["hooks"]) == set(integration("codex").events)
    for event in integration("codex").events:
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
    install_integration("codex", home, command_path=command)
    before = (home / "hooks.json").read_text()

    messages = install_integration("codex", home, command_path=command)

    assert (home / "hooks.json").read_text() == before
    assert any("already installed" in message for message in messages)


def test_install_distributes_the_versioned_issue_work_skill(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    messages = install_integration("codex", home, command_path=publisher(tmp_path))

    skill = installed_skill(home)
    text = (skill / "SKILL.md").read_text()
    assert skill == tmp_path / ".agents" / "skills" / "dashpot-issue-work"
    assert ISSUE_WORK_SKILL.marker in text
    assert f"written for Dashpot {BUNDLED_SKILL_VERSION}" in text
    dispatch = (skill / "references" / "dispatch.md").read_text()
    assert "codex resume <session-id> -C <worktree-path>" in dispatch
    assert "work relocate <worktree-path>" in dispatch
    assert "/cd <worktree-path>" in dispatch
    assert "cannot complete a Relocation Intent" in dispatch
    assert "the model cannot invoke it" in dispatch
    assert (skill / "references" / "recovery.md").is_file()
    assert version("dashpot") == BUNDLED_SKILL_VERSION
    assert any(f"installed Dashpot Issue work skill in {skill}" in m for m in messages)


def test_install_repairs_a_managed_issue_work_skill(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    skill = installed_skill(home)
    dispatch = skill / "references" / "dispatch.md"
    dispatch.write_text("stale\n")

    status = integration_status(
        "codex", home, state_dir=tmp_path / "state", current=tmp_path
    )
    messages = install_integration("codex", home, command_path=publisher(tmp_path))

    assert any("skill update available" in message for message in status)
    assert dispatch.read_text() != "stale\n"
    assert any("updated Dashpot Issue work skill" in message for message in messages)


def test_install_refuses_to_overwrite_an_unmanaged_skill(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    skill = installed_skill(home)
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: dashpot-issue-work\n---\nMine.\n")

    with pytest.raises(IntegrationError, match="not managed by Dashpot"):
        install_integration("codex", home, command_path=publisher(tmp_path))

    assert not (home / "hooks.json").exists()
    assert (skill / "SKILL.md").read_text().endswith("Mine.\n")


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_a_publisher_path_containing_spaces_is_executable(
    tmp_path: Path, harness: Harness
) -> None:
    home = codex_home(tmp_path)
    spec = integration(harness)
    command = publisher(tmp_path / "My User's tools $(false)").with_name(
        spec.command_name
    )
    command.write_text("#!/bin/sh\nprintf 'publisher executed'\n")
    command.chmod(0o755)
    assert " " in str(command)
    install_integration(harness, home, command_path=command)
    settings = home / spec.hooks_file
    before = settings.read_text()

    messages = install_integration(harness, home, command_path=command)

    assert settings.read_text() == before
    assert any("already installed" in message for message in messages)
    stop_groups = json.loads(settings.read_text())["hooks"]["Stop"]
    assert [
        handler["command"] for group in stop_groups for handler in group["hooks"]
    ] == [shlex.quote(str(command))]
    result = subprocess.run(
        ["/bin/sh", "-c", stop_groups[0]["hooks"][0]["command"]],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "publisher executed"
    status = "\n".join(integration_status(harness, home, current=tmp_path))
    assert "publisher missing" not in status
    assert "not executable" not in status
    remove_integration(harness, home)
    assert not settings.exists()


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

    install_integration("codex", home, command_path=publisher(tmp_path))

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

    install_integration("codex", home, command_path=command)

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

    install_integration("codex", home, command_path=command)

    stop_groups = read_hooks(home)["hooks"]["Stop"]
    assert len(stop_groups) == 1
    assert stop_groups[0]["hooks"][0]["command"] == str(command)


def test_install_requires_an_existing_codex_home(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="no Codex configuration directory"):
        install_integration(
            "codex", tmp_path / ".codex", command_path=publisher(tmp_path)
        )


def test_malformed_hooks_file_is_an_error_and_left_untouched(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    (home / "hooks.json").write_text("{not json")

    with pytest.raises(IntegrationError, match="fix or move the file"):
        install_integration("codex", home, command_path=publisher(tmp_path))

    assert (home / "hooks.json").read_text() == "{not json"


def test_config_toml_hooks_coexistence_is_noted(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    (home / "config.toml").write_text('[hooks]\nStop = "something"\n')

    messages = install_integration("codex", home, command_path=publisher(tmp_path))

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

    messages = install_integration("codex", home, command_path=publisher(tmp_path))

    assert not any("also defines hooks" in message for message in messages)

    (home / "config.toml").write_text('[[hooks.Stop]]\ncommand = "x"\n')
    messages = integration_status(
        "codex", home, state_dir=tmp_path / "state", current=tmp_path
    )
    assert any("also defines hooks" in message for message in messages)


def test_remove_strips_only_the_dashpot_hooks(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    theirs = {"type": "command", "command": "notify-send done"}
    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [theirs]}]}})
    )
    install_integration("codex", home, command_path=publisher(tmp_path))

    messages = remove_integration("codex", home)

    document = read_hooks(home)
    assert document == {"hooks": {"Stop": [{"hooks": [theirs]}]}}
    assert any("removed the Dashpot hooks" in message for message in messages)


def test_remove_deletes_a_file_that_only_held_dashpot_hooks(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))

    messages = remove_integration("codex", home)

    assert not (home / "hooks.json").exists()
    assert not installed_skill(home).exists()
    assert any("contained only the Dashpot hooks" in message for message in messages)


def test_remove_preserves_foreign_files_in_the_managed_skill_directory(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    skill = installed_skill(home)
    foreign = skill / "notes.txt"
    foreign.write_text("keep me\n")

    messages = remove_integration("codex", home)

    assert foreign.read_text() == "keep me\n"
    assert not (skill / "SKILL.md").exists()
    assert any("removed the Dashpot Issue work skill" in m for m in messages)


def test_remove_without_installation_is_a_calm_message(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    assert "not installed" in remove_integration("codex", home)[0]

    (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": []}]}}))
    assert "no Dashpot hooks" in remove_integration("codex", home)[0]


@pytest.mark.parametrize(
    ("document", "said"),
    [
        ({"hooks": []}, "no hooks in"),
        ({"hooks": {"Stop": "not a list"}}, "no Dashpot hooks in"),
    ],
)
def test_remove_leaves_a_hooks_file_without_dashpot_hooks_unchanged(
    tmp_path: Path, document: dict[str, Any], said: str
) -> None:
    home = codex_home(tmp_path)
    (home / "hooks.json").write_text(json.dumps(document))

    messages = remove_integration("codex", home)

    assert messages[0] == (
        f"Codex integration is not installed: {said} {home / 'hooks.json'}"
    )
    assert read_hooks(home) == document


def test_remove_cleans_the_managed_skill_when_hooks_are_already_absent(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    (home / "hooks.json").unlink()

    messages = remove_integration("codex", home)

    assert not installed_skill(home).exists()
    assert "integration is not installed" in messages[0]
    assert "removed the Dashpot Issue work skill" in messages[1]


def test_install_then_remove_round_trips_a_user_file(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    original = {
        "description": "user config",
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]},
    }
    (home / "hooks.json").write_text(json.dumps(original))

    install_integration("codex", home, command_path=publisher(tmp_path))
    remove_integration("codex", home)

    assert read_hooks(home) == original


def test_status_reports_installed_state_and_records(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    command = publisher(tmp_path)
    install_integration("codex", home, command_path=command)
    state = tmp_path / "state"
    state.mkdir()
    (state / "session.json").write_text("{}")

    messages = integration_status("codex", home, state_dir=state, current=tmp_path)

    joined = "\n".join(messages)
    assert f"installed in {home / 'hooks.json'}" in joined
    assert f"hook publisher: {command}" in joined
    assert "Issue work skill installed" in joined
    assert (
        f"session records outside configured Projects: 1 in {state} "
        "(0 live, 0 unknown, 0 stale, 1 unreadable)"
    ) in joined


def test_status_lists_stale_session_records_without_pruning(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    HookRecordStore(state).write(
        HookRecord.model_validate(session_record("0199-stale"))
    )
    HookRecordStore(state).write(HookRecord.model_validate(session_record("0199-live")))

    messages = integration_status(
        "codex",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(lookup=absent()),
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

    messages = integration_status(
        "codex",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(lookup=present(CODEX)),
    )
    assert "(2 live, 0 unknown, 0 stale, 0 unreadable)" in "\n".join(messages)


def test_status_names_the_sub_agents_that_keep_an_ended_record(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    state.mkdir()
    HookRecordStore(state).replace(
        "0199-ended",
        {
            **session_record("0199-ended", state="ended"),
            "event": "SessionEnd",
            "liveSubagents": ["0199-worker"],
        },
    )

    messages = integration_status(
        "codex",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(lookup=present(CODEX)),
    )

    assert (
        "  stale: Codex session 0199-ended last event SessionEnd at "
        "2026-08-24T15:00:00Z, ended by SessionEnd, kept for its 1 sub-agent "
        "listed as working (0199-worker on pid 4242) until each stops or its Host Process exits"
    ) in "\n".join(messages)


@pytest.mark.parametrize("ended", [False, True])
@pytest.mark.parametrize("unknown_host", [False, True])
def test_status_names_the_other_host_that_keeps_a_stale_records_subagent(
    tmp_path: Path, ended: bool, unknown_host: bool
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    other = dataclasses.replace(CODEX, pid=4243, started_at="Tue Aug 25 03:00:00 2026")
    another = dataclasses.replace(other, pid=4244)
    state.mkdir()
    HookRecordStore(state).replace(
        "0199-stale",
        {
            **session_record("0199-stale", state="ended" if ended else "waiting"),
            "event": "SessionEnd" if ended else "Stop",
            "liveSubagents": ["0199-another-worker", "0199-dead-worker", "0199-worker"],
            "subagentProcesses": {
                "0199-worker": {"pid": 0} if unknown_host else other.as_record(),
                "0199-another-worker": another.as_record(),
            },
        },
    )

    messages = integration_status(
        "codex",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(
            lookup=table_lookup({other.pid: other, another.pid: another})
        ),
    )

    description = next(line for line in messages if line.startswith("  stale:"))
    assert ("ended by SessionEnd" if ended else "pid 4242 gone") in description
    assert (
        "0199-worker on an unknown Host Process"
        if unknown_host
        else "0199-worker on pid 4243"
    ) in description
    assert "0199-another-worker on pid 4244" in description
    assert "0199-dead-worker" not in description
    assert "until each stops or its Host Process exits" in description
    assert (state / "0199-stale.json").exists()


def test_status_shows_unknown_liveness_reasons(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    state = tmp_path / "state"
    HookRecordStore(state).write(HookRecord.model_validate(session_record("sandboxed")))

    messages = integration_status(
        "codex",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(lookup=unobservable("isolated-namespace")),
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

    messages = integration_status(
        "codex", home, state_dir=tmp_path / "no-state", current=tmp_path
    )

    joined = "\n".join(messages)
    assert "missing hook events" in joined
    assert "SessionStart" in joined
    assert "hook publisher missing" in joined
    assert "session records outside configured Projects: none" in joined


def test_an_install_without_sub_agent_events_is_reported_and_upgraded(
    tmp_path: Path,
) -> None:
    # An install written before Codex sub-agents held their parent running
    # lacks the boundaries (ADR 0067); status names them and a rerun adds them.
    home = codex_home(tmp_path)
    command = publisher(tmp_path)
    install_integration("codex", home, command_path=command)
    document = read_hooks(home)
    for event in ("SubagentStart", "SubagentStop"):
        del document["hooks"][event]
    (home / "hooks.json").write_text(json.dumps(document))

    missing = [
        message
        for message in integration_status(
            "codex", home, state_dir=tmp_path / "no-state", current=tmp_path
        )
        if "missing hook events" in message
    ]
    assert missing and "SubagentStart" in missing[0] and "SubagentStop" in missing[0]

    install_integration("codex", home, command_path=command)

    assert {"SubagentStart", "SubagentStop"} <= set(read_hooks(home)["hooks"])


def test_the_codex_example_subscribes_every_lifecycle_event() -> None:
    example = Path(__file__).parents[1] / "examples" / "codex-hooks.json"

    assert set(json.loads(example.read_text())["hooks"]) == set(
        integration("codex").events
    )


def test_status_when_nothing_is_installed(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    messages = integration_status(
        "codex", home, state_dir=tmp_path / "state", current=tmp_path
    )

    assert "not installed" in messages[0]

    messages = integration_status(
        "codex", tmp_path / "absent", state_dir=tmp_path / "state", current=tmp_path
    )
    assert "configuration directory not found" in messages[0]


def test_status_reports_the_current_projects_session_store(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_config_marker(repo)
    sessions = repo / ".dashpot" / "state" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "one.json").write_text("{}")

    messages = integration_status(
        "codex", home, state_dir=tmp_path / "state", current=repo
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
    assert set(document["hooks"]) >= set(integration("claude-code").events)
    assert "Interrupt" not in document["hooks"]
    assert document["hooks"]["Stop"][0]["hooks"][0]["command"] == "notify-send x"
    assert document["hooks"]["Stop"][1]["hooks"][0]["command"] == str(command)
    assert any("Claude Code lifecycle hooks" in message for message in messages)
    skill = installed_skill(home, "claude-code")
    assert skill == home / "skills" / "dashpot-issue-work"
    assert (skill / "SKILL.md").is_file()


def skill_section(document: Path, heading: str) -> str:
    """The body of one ``## `` section of an installed skill document."""
    return document.read_text().split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def flowed(text: str) -> str:
    """``text`` with its line wrapping collapsed to single spaces."""
    return " ".join(text.split())


def test_claude_code_skill_returns_before_entering_and_hands_off_a_refusal(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    install_integration("claude-code", home, command_path=claude_publisher(tmp_path))

    skill = installed_skill(home, "claude-code")
    dispatch = skill / "references" / "dispatch.md"
    move = skill_section(dispatch, "Move a Claude Code session")
    assert "limits that switch to its own `.claude/worktrees/`" in flowed(move)
    assert move.index('`ExitWorktree` with `action: "keep"`') < move.index(
        "2. Call `EnterWorktree` with the exact path"
    )
    assert "never `remove`" in move
    handoff = skill_section(dispatch, "Hand off when `EnterWorktree` is refused")
    command = next(
        line for line in handoff.splitlines() if line.startswith("cd <worktree-path>")
    )
    assert shlex.split(command) == [
        "cd",
        "<worktree-path>",
        "&&",
        "claude",
        "Continue Issue <reference>. First run <dashpot> work start <reference> "
        "and verify it with <dashpot> work show, then follow the repository "
        "workflow through green CI.",
    ]
    handoff_text = flowed(handoff)
    assert "or when the user declines the move" in handoff_text
    assert "on the same Issue, run `<dashpot> work stop`" in handoff_text
    assert "do not promise that `gh` works" in handoff_text
    assert "https://github.com/ned2/dashpot/issues/274" in handoff
    refusal = skill_section(
        skill / "references" / "recovery.md", "Claude Code refuses `EnterWorktree`"
    )
    assert "is not under <repository>/.claude/worktrees" in refusal
    assert "Hand the work to a fresh session" in flowed(refusal)


def test_issue_work_skill_leaves_the_worktree_once_its_run_has_stopped(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    install_integration("claude-code", home, command_path=claude_publisher(tmp_path))

    skill = installed_skill(home, "claude-code")
    text = flowed(skill_section(skill / "SKILL.md", "Finish the engagement"))
    entered = text.index("**Claude Code, entered with `EnterWorktree`.**")
    started = text.index("**Claude Code, started in the Worktree.**")
    by_cd = text.index("**Claude Code, reached by a shell `cd`.**")
    codex = text.index("**Codex.**")
    opencode = text.index("**OpenCode.**")
    follow_up = text.index("If the user asks for follow-up changes")
    assert (
        text.index("work stop")
        < entered
        < started
        < by_cd
        < codex
        < opencode
        < follow_up
    )
    assert "do not wait for the user to ask" in text[:entered]
    entered_case = text[entered:started]
    assert 'Call `ExitWorktree` with `action: "keep"`' in entered_case
    assert "only after `show` reports no active Issue work" in entered_case
    assert "Never use `remove`" in entered_case
    started_case = text[started:by_cd]
    assert "There is nothing to exit" in started_case
    assert "reports that no worktree session is active" in started_case
    assert "not a refusal to recover from or a reason to hand off" in started_case
    assert "keeps the Worktree from Cleanup until it ends" in started_case
    assert (
        "Change the shell back to the directory the session started in"
        in (text[by_cd:codex])
    )
    # Each way out the skill names is the one the Cleanup blocker names.
    codex_case = text[codex:opencode]
    assert "until its client exits" in codex_case
    assert "`codex resume <session-id> -C <directory>`" in codex_case
    assert "60 s after its last client leaves" in codex_case
    assert "60 s after its last client leaves" in session_exit("codex").end
    opencode_case = text[opencode:follow_up]
    assert "Move the session to the Repository's main Worktree" in opencode_case
    assert "with steps 2 and 3 of the [OpenCode move]" in opencode_case
    assert "only after `show` reports no active Issue work" in opencode_case
    assert "Run no `work start` there" in opencode_case
    assert "If the move fails" in opencode_case
    assert "moved to another location in OpenCode" in opencode_case
    assert "move that session to another location in OpenCode" in flowed(
        session_exit("opencode").move
    )
    assert "`opencode session delete <session-id>`" in opencode_case
    assert "opencode session delete {session_id}" in session_exit("opencode").end
    flowed_opencode = flowed(opencode_case)
    assert (
        "quitting a client of the shared service leaves it running, and quitting "
        "a `--standalone` client stops its server" in flowed_opencode
    )
    # A session off the shared service makes no move back (ADR 0108).
    assert "Move only when its Host Process mode is `shared-service`" in flowed_opencode
    assert "or the mode rules it out, tell the user" in flowed_opencode
    follow_up_text = text[follow_up:]
    assert "enters it again with `EnterWorktree`" in follow_up_text
    assert "OpenCode moves there with every step of the [OpenCode move]" in (
        follow_up_text
    )
    assert "checks `<dashpot> work show` before any `work start`" in follow_up_text
    assert "continues from step 5" in follow_up_text
    assert (
        "Keep the Issue Worktree and its Branch in place unless the user "
        "explicitly requests Cleanup." in follow_up_text
    )
    move = skill_section(
        skill / "references" / "dispatch.md", "Move a Claude Code session"
    )
    assert "requires, which already returns the session" in flowed(move)


def test_issue_work_skill_leaves_the_sub_agent_override_to_the_user(
    tmp_path: Path,
) -> None:
    # The override is the person's assertion about where sub-agents work,
    # so an agent shows the preview rather than passing it (ADR 0112).
    home = claude_home(tmp_path)
    install_integration("claude-code", home, command_path=claude_publisher(tmp_path))

    skill = installed_skill(home, "claude-code")
    text = flowed(skill_section(skill / "SKILL.md", "Finish the engagement"))
    assert f"including the `{DESPITE_SUBAGENTS_FLAG}` value it offers" in text
    assert "leave that flag and the Cleanup dialog's matching toggle to the user" in (
        text
    )
    assert "never pass the flag or tick the toggle yourself" in text


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
    HookRecordStore(state).write(HookRecord.model_validate(stale))
    messages = integration_status(
        "claude-code",
        home,
        state_dir=state,
        current=tmp_path,
        environment=IntegrationEnvironment(lookup=absent()),
    )
    joined = "\n".join(messages)
    assert "(0 live, 0 unknown, 1 stale, 0 unreadable)" in joined
    assert "stale: Claude Code session claude-stale" in joined
    assert "no SessionEnd delivered" in joined

    with pytest.raises(IntegrationError, match="no Claude Code configuration"):
        install_integration("claude-code", tmp_path / "absent", command_path=command)


def test_each_harness_removal_only_touches_its_own_file(tmp_path: Path) -> None:
    codex = codex_home(tmp_path)
    claude = claude_home(tmp_path)
    install_integration("codex", codex, command_path=publisher(tmp_path))
    install_integration("claude-code", claude, command_path=claude_publisher(tmp_path))

    remove_integration("codex", codex)

    assert not (codex / "hooks.json").exists()
    document = json.loads((claude / "settings.json").read_text())
    assert set(document["hooks"]) == {*integration("claude-code").events, "PostToolUse"}


def test_unsupported_harness_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match="unsupported harness"):
        install_integration(cast("Harness", "cursor"), tmp_path)


def test_status_reports_the_identity_a_sandboxed_command_would_claim(
    tmp_path: Path,
) -> None:
    from dashpot.sessions.harnesses import SESSION_OVERRIDE_VARIABLE
    from dashpot.sessions.hook_records import project_session_store

    home = codex_home(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    write_config_marker(root)
    state = tmp_path / "state"

    none = integration_status(
        "codex",
        home,
        state_dir=state,
        current=root,
        environment=IntegrationEnvironment(lookup=present(CODEX), environ={}),
    )
    assert any(
        "Agent Session identity claimed here: none for Codex" in message
        and SESSION_OVERRIDE_VARIABLE in message
        for message in none
    )

    claimed = {"CODEX_THREAD_ID": "thread-9"}
    missing = integration_status(
        "codex",
        home,
        state_dir=state,
        current=root,
        environment=IntegrationEnvironment(lookup=present(CODEX), environ=claimed),
    )
    assert any(
        "Codex session thread-9 (from Codex environment), rejected: no "
        "lifecycle hook record" in message
        for message in missing
    )

    project_session_store(root).write(
        HookRecord.model_validate(
            {**session_record("thread-9", "running"), "repositoryRoot": str(root)}
        )
    )
    confirmed = integration_status(
        "codex",
        home,
        state_dir=state,
        current=root,
        environment=IntegrationEnvironment(lookup=present(CODEX), environ=claimed),
    )
    assert any(
        "Codex session thread-9 (from Codex environment), confirmed by its "
        "live hook record" in message
        for message in confirmed
    )

    explicit = integration_status(
        "codex",
        home,
        state_dir=state,
        current=root,
        environment=IntegrationEnvironment(
            lookup=present(CODEX), environ={SESSION_OVERRIDE_VARIABLE: "codex:thread-9"}
        ),
    )
    assert any(
        f"thread-9 (from {SESSION_OVERRIDE_VARIABLE}), confirmed" in message
        for message in explicit
    )


def test_status_confirms_an_identity_only_where_its_freshest_record_places_it(
    tmp_path: Path,
) -> None:
    # A move whose record at the destination could not be written leaves the
    # freshest record behind, so a command at the destination is elsewhere.
    from dashpot.sessions.hook_records import project_session_store

    home = codex_home(tmp_path)
    main, linked = linked_worktree(tmp_path)
    write_config_marker(main)
    write_config_marker(linked)
    project_session_store(main).write(
        HookRecord.model_validate(
            {**session_record("thread-9", "running"), "repositoryRoot": str(main)}
        )
    )

    def status(current: Path) -> list[str]:
        return integration_status(
            "codex",
            home,
            state_dir=tmp_path / "state",
            current=current,
            environment=IntegrationEnvironment(
                lookup=present(CODEX), environ={"CODEX_THREAD_ID": "thread-9"}
            ),
        )

    at_destination = [m for m in status(linked) if "identity claimed here" in m]
    assert at_destination == [
        "Agent Session identity claimed here: Codex session thread-9 (from Codex "
        f"environment), elsewhere: its freshest hook record, live, places it at "
        f"{main}, not here"
    ]
    assert any(
        "thread-9 (from Codex environment), confirmed by its live hook record" in m
        for m in status(main)
    )


def test_status_of_the_other_harness_does_not_borrow_a_claim(tmp_path: Path) -> None:
    from dashpot.sessions.harnesses import SESSION_OVERRIDE_VARIABLE

    home = tmp_path / ".claude"
    home.mkdir()

    messages = integration_status(
        "claude-code",
        home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environment=IntegrationEnvironment(
            environ={
                SESSION_OVERRIDE_VARIABLE: "codex:thread-9",
                "CODEX_THREAD_ID": "x",
            }
        ),
    )

    assert any("none for Claude Code" in message for message in messages)


# --- Claude Code: PostToolUse matched to the relocation tools alone (ADR 0009)


def test_claude_code_subscribes_post_tool_use_to_the_relocation_tools_alone(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)

    install_integration("claude-code", home, command_path=command)

    document = json.loads((home / "settings.json").read_text())
    handler = {"type": "command", "command": str(command), "timeout": 3}
    assert document["hooks"]["PostToolUse"] == [
        {"matcher": "EnterWorktree", "hooks": [handler]},
        {"matcher": "ExitWorktree", "hooks": [handler]},
    ]
    before = (home / "settings.json").read_text()
    messages = install_integration("claude-code", home, command_path=command)
    assert (home / "settings.json").read_text() == before
    assert any("already installed" in message for message in messages)
    status = integration_status(
        "claude-code", home, state_dir=tmp_path / "no-state", current=tmp_path
    )
    assert any(
        "PostToolUse(EnterWorktree), PostToolUse(ExitWorktree)" in message
        for message in status
    )
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
    assert "PostToolUse(ExitWorktree)" in missing[0]


def test_an_install_that_predates_exit_worktree_is_flagged_and_upgraded(
    tmp_path: Path,
) -> None:
    """A user-wide install from before the return trip was observed."""
    home = claude_home(tmp_path)
    command = claude_publisher(tmp_path)
    install_integration("claude-code", home, command_path=command)
    document = json.loads((home / "settings.json").read_text())
    document["hooks"]["PostToolUse"] = [
        group
        for group in document["hooks"]["PostToolUse"]
        if group["matcher"] == "EnterWorktree"
    ]
    (home / "settings.json").write_text(json.dumps(document))

    messages = integration_status(
        "claude-code", home, state_dir=tmp_path / "no-state", current=tmp_path
    )
    missing = [message for message in messages if "missing hook events" in message]
    assert missing and "PostToolUse(ExitWorktree)" in missing[0]
    assert "PostToolUse(EnterWorktree)" not in missing[0]

    install_integration("claude-code", home, command_path=command)

    document = json.loads((home / "settings.json").read_text())
    assert [group["matcher"] for group in document["hooks"]["PostToolUse"]] == [
        "EnterWorktree",
        "ExitWorktree",
    ]


def test_codex_subscribes_no_matched_events(tmp_path: Path) -> None:
    home = codex_home(tmp_path)

    install_integration("codex", home, command_path=publisher(tmp_path))

    assert "PostToolUse" not in read_hooks(home)


def test_resolve_hook_command_prefers_the_environment_scripts_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = integration("codex")
    installed = tmp_path / spec.command_name
    installed.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(tmp_path))

    assert resolve_hook_command(spec) == installed


def test_resolve_hook_command_falls_back_to_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = integration("claude-code")
    on_path = tmp_path / "bin" / spec.command_name
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(tmp_path / "absent"))
    monkeypatch.setattr(shutil, "which", lambda name: str(on_path))

    assert resolve_hook_command(spec) == on_path


def test_resolve_hook_command_reports_a_missing_publisher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = integration("codex")
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(tmp_path / "absent"))
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(IntegrationError, match="reinstall Dashpot"):
        resolve_hook_command(spec)


# --- Bindings a linked Worktree's lifetime would break ------------------------


HARNESS_HOMES = [
    pytest.param("codex", codex_home, "hooks.json", id="codex"),
    pytest.param("claude-code", claude_home, "settings.json", id="claude-code"),
]


def linked_worktree(root: Path) -> tuple[Path, Path]:
    """A committed Repository at ``root/repo`` and one linked Worktree beside it."""
    main = init_repository(root / "repo")
    (main / "README.md").write_text("Sim\n")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "first")
    linked = root / "repo.worktrees" / "157-issue"
    git(main, "worktree", "add", "-q", "-b", "157-issue", str(linked))
    return main.resolve(), linked.resolve()


def environment_publisher(tree: Path, harness: Harness) -> Path:
    """The publisher a ``.venv`` inside ``tree`` would install."""
    command = tree / ".venv" / "bin" / integration(harness).command_name
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


@pytest.mark.parametrize(("harness", "make_home", "hooks_file"), HARNESS_HOMES)
def test_install_refuses_a_publisher_inside_a_linked_worktree(
    tmp_path: Path,
    harness: Harness,
    make_home: Callable[[Path], Path],
    hooks_file: str,
) -> None:
    home = make_home(tmp_path)
    before = json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "notify"}]}]}})
    (home / hooks_file).write_text(before)
    main, linked = linked_worktree(tmp_path)
    command = environment_publisher(linked, harness)

    with pytest.raises(IntegrationError) as refusal:
        install_integration(harness, home, command_path=command)

    message = str(refusal.value)
    assert message.startswith(
        f"cannot bind the {integration(harness).display} hooks to {command}: "
    )
    assert f"lives in the linked Worktree {linked}" in message
    assert (
        f"run 'dashpot integrate {harness}' from the main working tree {main}"
        in message
    )
    assert (home / hooks_file).read_text() == before
    assert not installed_skill(home, harness).exists()


@pytest.mark.parametrize(("harness", "make_home", "hooks_file"), HARNESS_HOMES)
def test_install_binds_a_publisher_in_the_main_working_tree(
    tmp_path: Path,
    harness: Harness,
    make_home: Callable[[Path], Path],
    hooks_file: str,
) -> None:
    home = make_home(tmp_path)
    main, _linked = linked_worktree(tmp_path)
    command = environment_publisher(main, harness)

    messages = install_integration(harness, home, command_path=command)

    assert f"hook publisher: {command}" in messages
    assert (home / hooks_file).is_file()
    status = integration_status(
        harness, home, state_dir=tmp_path / "state", current=tmp_path
    )
    joined = "\n".join(status)
    assert f"hook publisher: {command}" in joined
    assert "linked Worktree" not in joined


@pytest.mark.parametrize(("harness", "make_home", "hooks_file"), HARNESS_HOMES)
def test_install_binds_a_publisher_outside_any_git_working_tree(
    tmp_path: Path,
    harness: Harness,
    make_home: Callable[[Path], Path],
    hooks_file: str,
) -> None:
    home = make_home(tmp_path)
    # A tool installation: an environment no Repository contains.
    command = environment_publisher(tmp_path / "tools" / "dashpot", harness)
    outside = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=tmp_path, capture_output=True
    )
    assert outside.returncode != 0

    messages = install_integration(harness, home, command_path=command)

    assert f"hook publisher: {command}" in messages
    assert (home / hooks_file).is_file()
    status = integration_status(
        harness, home, state_dir=tmp_path / "state", current=tmp_path
    )
    assert "linked Worktree" not in "\n".join(status)


def test_a_bare_repository_names_no_main_working_tree_to_run_from(
    tmp_path: Path,
) -> None:
    main, _linked = linked_worktree(tmp_path)
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(main), str(bare))
    checkout = tmp_path / "bare.worktrees" / "157-issue"
    git(bare, "worktree", "add", "-q", str(checkout), "157-issue")
    home = codex_home(tmp_path)
    command = environment_publisher(checkout.resolve(), "codex")

    with pytest.raises(IntegrationError) as refusal:
        install_integration("codex", home, command_path=command)

    message = str(refusal.value)
    assert f"lives in the linked Worktree {checkout.resolve()}" in message
    assert message.endswith(
        "run 'dashpot integrate codex' from an installed tool environment"
    )
    assert "main working tree" not in message
    assert not (home / "hooks.json").exists()


@pytest.mark.parametrize(("harness", "make_home", "hooks_file"), HARNESS_HOMES)
def test_status_warns_about_a_linked_worktree_binding_until_its_file_is_gone(
    tmp_path: Path,
    harness: Harness,
    make_home: Callable[[Path], Path],
    hooks_file: str,
) -> None:
    home = make_home(tmp_path)
    main, linked = linked_worktree(tmp_path)
    command = environment_publisher(linked, harness)
    handler = {"type": "command", "command": shlex.quote(str(command)), "timeout": 3}
    (home / hooks_file).write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [handler]}]}})
    )

    messages = integration_status(
        harness, home, state_dir=tmp_path / "state", current=tmp_path
    )

    publisher_line = messages.index(f"hook publisher: {handler['command']}")
    warning = messages[publisher_line + 1]
    assert warning.startswith(
        f"warning: that publisher lives in the linked Worktree {linked}, which is "
        "removed when its Issue is finished, and every hook event would fail"
    )
    assert f"from the main working tree {main}" in warning

    git(main, "worktree", "remove", "--force", str(linked))
    messages = integration_status(
        harness, home, state_dir=tmp_path / "state", current=tmp_path
    )

    joined = "\n".join(messages)
    assert f"hook publisher missing at {handler['command']}" in joined
    assert "linked Worktree" not in joined


# --- Several harnesses in one command (ADR 0111) ---------------------------


@pytest.fixture
def user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every harness's default user directories inside the test's own."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    return home


def default_home(harness: Harness) -> Path:
    """A harness's default configuration directory, as its first run leaves it."""
    home = configuration_directory(integration(harness), os.environ).path
    home.mkdir(parents=True, exist_ok=True)
    return home


def publishers(directory: Path) -> dict[Harness, Path]:
    """One installed publisher per harness, outside every Git working tree."""
    commands: dict[Harness, Path] = {}
    for harness in ("claude-code", "codex", "opencode"):
        command = directory / "bin" / integration(harness).command_name
        command.parent.mkdir(parents=True, exist_ok=True)
        command.write_text("#!/bin/sh\n")
        command.chmod(0o755)
        commands[harness] = command
    return commands


def opencode_accepted() -> str:
    return f"opencode v{OPENCODE_ACCEPTED_VERSION}"


def accepting(**seams: Any) -> IntegrationEnvironment:
    """This process's environment with ``seams`` in place, OpenCode's release accepted."""
    return dataclasses.replace(
        IntegrationEnvironment(version_probe=opencode_accepted), **seams
    )


def integrate_one(harness: Harness, tmp_path: Path, **seams: Any) -> list[str]:
    return install_integration(
        harness,
        default_home(harness),
        command_path=publishers(tmp_path)[harness],
        environment=accepting(**seams),
    )


def refresh(tmp_path: Path, *harnesses: Harness, **seams: Any) -> list[HarnessReport]:
    """Integrate the named harnesses, or refresh every integrated one when none is."""
    command_paths = publishers(tmp_path)
    if harnesses:
        return install_integrations(
            harnesses, command_paths=command_paths, environment=accepting(**seams)
        )
    return refresh_integrations(
        command_paths=command_paths, environment=accepting(**seams)
    )


def combined_status(
    tmp_path: Path, *harnesses: Harness, **seams: Any
) -> CombinedStatus:
    return integrations_status(
        harnesses,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environment=accepting(**{"environ": {}} | seams),
    )


def outcomes(reports: Sequence[HarnessReport]) -> list[tuple[Harness, str]]:
    return [(report.harness, report.outcome) for report in reports]


def every_file(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_installed_installs_nothing_when_no_harness_is_integrated(
    tmp_path: Path, user_home: Path
) -> None:
    for harness in ("claude-code", "codex", "opencode"):
        default_home(harness)

    reports = refresh(tmp_path)

    assert outcomes(reports) == [
        ("claude-code", "not integrated"),
        ("codex", "not integrated"),
        ("opencode", "not integrated"),
    ]
    assert reports[1].note == (
        f"not integrated (no Dashpot hooks at {user_home / '.codex' / 'hooks.json'})"
    )
    assert every_file(user_home) == {}


def test_installed_refreshes_only_the_integrated_harnesses(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path)
    codex = default_home("codex")
    (codex / "hooks.json").write_text('{"hooks": {}}\n')

    reports = refresh(tmp_path)

    assert outcomes(reports) == [
        ("claude-code", "installed"),
        ("codex", "not integrated"),
        ("opencode", "not integrated"),
    ]
    assert (
        reports[0]
        .messages[0]
        .startswith("Claude Code lifecycle hooks already installed in ")
    )
    assert reports[2].note == (
        "not integrated (no OpenCode configuration directory at "
        f"{user_home / '.config' / 'opencode'})"
    )
    assert (codex / "hooks.json").read_text() == '{"hooks": {}}\n'
    assert not (user_home / ".agents").exists()


def test_installed_refreshes_a_stale_integration_with_a_skill_this_release_adds(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path, skills=(ISSUE_WORK_SKILL,))
    added = added_skill(tmp_path)

    reports = refresh(tmp_path, skills=(ISSUE_WORK_SKILL, added))

    assert outcomes(reports)[0] == ("claude-code", "installed")
    copy = user_home / ".claude" / "skills" / added.name
    assert f"installed Dashpot Added skill in {copy}" in reports[0].messages
    assert (copy / "SKILL.md").read_text() == (added.source / "SKILL.md").read_text()


def added_skill(tmp_path: Path) -> BundledSkill:
    """A bundled skill a later release adds beside the Issue work skill."""
    source = tmp_path / "bundled" / "fixture-added-skill"
    source.mkdir(parents=True)
    skill = BundledSkill(name="fixture-added-skill", label="Added skill", source=source)
    (source / "SKILL.md").write_text(
        f"---\nname: {skill.name}\n---\n\n{skill.marker}\n"
    )
    return skill


def test_installed_leaves_a_harness_missing_some_hooks_unchanged(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path)
    settings = user_home / ".claude" / "settings.json"
    document = json.loads(settings.read_text())
    del document["hooks"]["Stop"]
    settings.write_text(json.dumps(document))
    before = every_file(user_home)

    reports = refresh(tmp_path)

    assert outcomes(reports)[0] == ("claude-code", "partial")
    assert reports[0].note == "partial"
    assert reports[0].error is None
    assert reports[0].messages == (
        f"left unchanged: missing hook events in {settings}: Stop; run 'dashpot "
        "integrate claude-code' to complete it, or 'dashpot integrate "
        "claude-code --remove' to clear it",
    )
    assert every_file(user_home) == before


def test_installed_leaves_a_managed_skill_without_hooks_unchanged(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("codex", tmp_path)
    hooks = user_home / ".codex" / "hooks.json"
    hooks.unlink()
    before = every_file(user_home)

    reports = refresh(tmp_path)

    copy = user_home / ".agents" / "skills" / ISSUE_WORK_SKILL.name
    assert outcomes(reports)[1] == ("codex", "partial")
    assert (
        reports[1]
        .messages[0]
        .startswith(
            f"left unchanged: no Dashpot hooks at {hooks}, but the Dashpot Issue "
            f"work skill at {copy}"
        )
    )
    assert every_file(user_home) == before


@pytest.mark.parametrize("unreadable", [b"{not json", b"\xff{}"])
def test_installed_refuses_a_harness_whose_hooks_cannot_be_read(
    tmp_path: Path, user_home: Path, unreadable: bytes
) -> None:
    integrate_one("claude-code", tmp_path)
    hooks = default_home("codex") / "hooks.json"
    hooks.write_bytes(unreadable)

    reports = refresh(tmp_path)
    status = combined_status(tmp_path)

    assert outcomes(reports)[:2] == [("claude-code", "installed"), ("codex", "refused")]
    assert reports[1].error is not None
    assert reports[1].error.startswith(f"cannot read Codex hooks at {hooks}: ")
    assert (
        status.harnesses[1]
        .messages[0]
        .startswith(f"cannot read Codex hooks at {hooks}: ")
    )
    assert hooks.read_bytes() == unreadable


def test_one_refused_harness_does_not_stop_the_others(
    tmp_path: Path, user_home: Path
) -> None:
    for harness in ("claude-code", "codex", "opencode"):
        default_home(harness)

    reports = refresh(
        tmp_path, "opencode", "codex", "claude-code", version_probe=lambda: "1.18.30"
    )

    assert outcomes(reports) == [
        ("claude-code", "installed"),
        ("codex", "installed"),
        ("opencode", "refused"),
    ]
    assert reports[2].note == "refused"
    assert reports[2].error is not None
    assert reports[2].error.startswith("the opencode on PATH is OpenCode 1.18.30")
    assert (user_home / ".claude" / "settings.json").is_file()
    assert (user_home / ".codex" / "hooks.json").is_file()
    assert not (user_home / ".config" / "opencode" / "plugins").exists()


def test_a_harness_left_incomplete_does_not_stop_the_others(
    tmp_path: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for harness in ("claude-code", "codex"):
        default_home(harness)
    rename = os.replace

    def full_disk(source: str | os.PathLike[str], destination: Path) -> None:
        if destination.name == "settings.json":
            raise OSError(28, "No space left on device")
        rename(source, destination)

    monkeypatch.setattr(os, "replace", full_disk)

    reports = refresh(tmp_path, "codex", "claude-code")

    assert outcomes(reports) == [("claude-code", "incomplete"), ("codex", "installed")]
    claude = reports[0]
    assert claude.note == "incomplete"
    assert claude.error is not None
    assert "No space left on device" in claude.error
    copy = user_home / ".claude" / "skills" / ISSUE_WORK_SKILL.name
    assert f"installed Dashpot Issue work skill in {copy}" in claude.messages
    assert (user_home / ".codex" / "hooks.json").is_file()


def test_a_combined_refresh_leaves_no_opencode_warning_about_copies_it_refreshed(
    tmp_path: Path, user_home: Path
) -> None:
    for harness in ("opencode", "codex", "claude-code"):
        integrate_one(harness, tmp_path)
    for directory in (".claude/skills", ".agents/skills"):
        skill = user_home / directory / ISSUE_WORK_SKILL.name / "SKILL.md"
        skill.write_text(skill.read_text() + "\nAn earlier release's text.\n")

    reports = refresh(tmp_path)

    assert outcomes(reports) == [
        ("claude-code", "installed"),
        ("codex", "installed"),
        ("opencode", "installed"),
    ]
    assert not any("also discovers" in message for message in reports[2].messages)


def test_a_combined_refresh_still_warns_about_a_foreign_copy(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("opencode", tmp_path)
    integrate_one("claude-code", tmp_path)
    foreign = user_home / ".agents" / "skills" / ISSUE_WORK_SKILL.name
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("---\nname: dashpot-issue-work\n---\nMine.\n")

    reports = refresh(tmp_path)

    assert outcomes(reports) == [
        ("claude-code", "installed"),
        ("codex", "not integrated"),
        ("opencode", "installed"),
    ]
    assert [m for m in reports[2].messages if "also discovers" in m] == [
        f"warning: OpenCode also discovers the Issue work skill at {foreign}, "
        "which differs from this Dashpot's, and may use either; run 'dashpot "
        "integrate codex' or move it"
    ]


@pytest.mark.parametrize(
    ("named", "arguments"),
    [((), "--installed"), (("codex", "claude-code"), "claude-code codex")],
)
def test_a_linked_worktree_publisher_refuses_every_harness_before_any_changes(
    tmp_path: Path,
    user_home: Path,
    named: tuple[Harness, ...],
    arguments: str,
) -> None:
    integrate_one("claude-code", tmp_path)
    integrate_one("codex", tmp_path)
    for directory in (".claude/skills", ".agents/skills"):
        skill = user_home / directory / ISSUE_WORK_SKILL.name / "SKILL.md"
        skill.write_text(skill.read_text() + "\nAn earlier release's text.\n")
    before = every_file(user_home)
    main, linked = linked_worktree(tmp_path / "repos")
    harnesses: tuple[Harness, ...] = ("claude-code", "codex")
    commands: dict[Harness, Path] = {
        harness: environment_publisher(linked, harness) for harness in harnesses
    }

    with pytest.raises(IntegrationError) as refusal:
        if named:
            install_integrations(named, command_paths=commands)
        else:
            refresh_integrations(command_paths=commands)

    assert str(refusal.value).startswith(
        "cannot bind the Claude Code and Codex hooks to their publishers in "
        f"{linked / '.venv' / 'bin'}: those publishers live in the linked "
        f"Worktree {linked}, which is removed"
    )
    assert (
        f"run 'dashpot integrate {arguments}' from the main working tree {main}"
        in str(refusal.value)
    )
    assert every_file(user_home) == before


def test_one_linked_worktree_publisher_is_named_as_one_harness_names_it(
    tmp_path: Path, user_home: Path
) -> None:
    default_home("codex")
    _main, linked = linked_worktree(tmp_path / "repos")
    command = environment_publisher(linked, "codex")

    with pytest.raises(IntegrationError) as refusal:
        install_integrations(("codex",), command_paths={"codex": command})

    assert str(refusal.value).startswith(
        f"cannot bind the Codex hooks to {command}: that publisher lives in the "
        f"linked Worktree {linked}"
    )
    assert not (user_home / ".codex" / "hooks.json").exists()


def test_a_missing_publisher_refuses_its_harness_alone(
    tmp_path: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    integrate_one("claude-code", tmp_path)
    monkeypatch.setattr(sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    monkeypatch.setenv("PATH", str(tmp_path / "none"))

    reports = refresh_integrations(
        command_paths={"codex": publishers(tmp_path)["codex"]}
    )

    assert outcomes(reports)[0] == ("claude-code", "refused")
    assert reports[0].error == (
        "cannot locate the dashpot-claude-code-hook publisher installed with "
        "Dashpot; reinstall Dashpot and retry"
    )


def test_combined_status_reports_each_harness_and_the_records_once(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path)
    integrate_one("codex", tmp_path)
    (user_home / ".codex" / "hooks.json").unlink()

    status = combined_status(tmp_path)

    claude, codex, opencode = status.harnesses
    assert (claude.outcome, claude.note) == ("reported", None)
    assert claude.messages[0].startswith(
        f"installed in {user_home / '.claude' / 'settings.json'} for: "
    )
    assert (codex.outcome, codex.note) == ("partial", "partial")
    assert codex.messages[0].startswith(
        f"no Dashpot hooks at {user_home / '.codex' / 'hooks.json'}, but the "
        "Dashpot Issue work skill at "
    )
    assert codex.messages[0].endswith(
        "; run 'dashpot integrate codex' to complete it, or 'dashpot integrate "
        "codex --remove' to clear it"
    )
    assert f"not installed: no {user_home / '.codex' / 'hooks.json'}" in codex.messages
    assert (opencode.outcome, opencode.messages) == ("not integrated", ())
    assert opencode.note is not None
    assert opencode.note.startswith("not integrated (no OpenCode configuration")
    for report in status.harnesses:
        assert not any(m.startswith("session records") for m in report.messages)
    assert [m for m in status.messages if m.startswith("session records")] == [
        "session records outside configured Projects: none "
        f"({tmp_path / 'state'} does not exist yet)"
    ]


def test_combined_status_reports_a_named_harness_even_when_not_integrated(
    tmp_path: Path, user_home: Path
) -> None:
    status = combined_status(tmp_path, "opencode", "codex")

    assert outcomes(status.harnesses) == [
        ("codex", "reported"),
        ("opencode", "reported"),
    ]
    assert status.harnesses[0].messages[0] == (
        f"Codex configuration directory not found: {user_home / '.codex'}"
    )


@pytest.mark.parametrize(
    ("named", "rerun"),
    [
        ((), "--installed"),
        (("opencode", "codex", "claude-code"), "claude-code codex opencode"),
    ],
)
def test_combined_status_names_one_command_for_several_harnesses_behind(
    tmp_path: Path, user_home: Path, named: tuple[Harness, ...], rerun: str
) -> None:
    for harness in ("claude-code", "codex", "opencode"):
        integrate_one(harness, tmp_path)
    added = added_skill(tmp_path)

    status = combined_status(tmp_path, *named, skills=(ISSUE_WORK_SKILL, added))

    assert status.messages[-1] == (
        "updates available for Claude Code, Codex, and OpenCode; run 'dashpot "
        f"integrate {rerun}' to update them together"
    )


def test_combined_status_counts_a_changed_plugin_or_a_missing_agent_as_behind(
    tmp_path: Path, user_home: Path
) -> None:
    for harness in ("claude-code", "codex", "opencode"):
        integrate_one(harness, tmp_path)
    skill = user_home / ".claude" / "skills" / ISSUE_WORK_SKILL.name / "SKILL.md"
    skill.write_text(skill.read_text() + "\nAn earlier release's text.\n")
    together = (
        "updates available for Claude Code and OpenCode; run 'dashpot integrate "
        "--installed' to update them together"
    )

    def summary(*named: Harness) -> list[str]:
        messages = combined_status(tmp_path, *named).messages
        return [message for message in messages if message.startswith("updates")]

    assert summary() == []

    plugin = user_home / ".config" / "opencode" / "plugins" / "dashpot.js"
    plugin.write_text(plugin.read_text() + "// an earlier release\n")
    assert summary() == [together]

    integrate_one("opencode", tmp_path)
    assert summary() == []
    (user_home / ".config" / "opencode" / "agent" / "dashpot-worker.md").unlink()
    assert summary() == [together]
    assert summary("codex", "opencode") == []


def test_an_unreadable_plugin_refuses_opencode_alone_and_is_reported_in_full(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path)
    plugin = default_home("opencode") / "plugins" / "dashpot.js"
    plugin.parent.mkdir()
    plugin.write_bytes(b"\xff not a plugin\n")

    reports = refresh(tmp_path)
    status = combined_status(tmp_path)

    assert outcomes(reports) == [
        ("claude-code", "installed"),
        ("codex", "not integrated"),
        ("opencode", "refused"),
    ]
    assert reports[2].error is not None
    assert reports[2].error.startswith(
        f"cannot tell whether OpenCode is integrated: cannot read {plugin}: "
    )
    assert plugin.read_bytes() == b"\xff not a plugin\n"
    opencode = status.harnesses[2]
    assert opencode.outcome == "reported"
    assert opencode.messages[0].startswith(
        f"plugin conflict: cannot read the plugin at {plugin}: "
    )


def test_a_skill_copy_that_is_not_text_is_no_update(
    tmp_path: Path, user_home: Path
) -> None:
    integrate_one("claude-code", tmp_path)
    integrate_one("codex", tmp_path)
    for directory in (".claude/skills", ".agents/skills"):
        skill = user_home / directory / ISSUE_WORK_SKILL.name / "SKILL.md"
        skill.write_bytes(b"\xff not a skill Dashpot wrote\n")

    messages = combined_status(tmp_path).messages

    assert not any(message.startswith("updates available") for message in messages)


# --- The user's configuration, where each harness reads it (ADR 0130) ------


def removed_skills(home: Path) -> tuple[str, ...]:
    """What removing every bundled skill's Codex copy reports."""
    spec = integration("codex")
    return tuple(
        f"removed the Dashpot {skill.label} from "
        f"{skill_directory(spec, home, skill, os.environ)}"
        for skill in BUNDLED_SKILLS
    )


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_install_and_remove_write_through_a_linked_hooks_file(
    tmp_path: Path, harness: Harness
) -> None:
    spec = integration(harness)
    home = tmp_path / spec.home_name
    home.mkdir()
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    managed = dotfiles / spec.hooks_file
    managed.write_text('{\n  "statusLine": "café → ✓"\n}\n', encoding="utf-8")
    managed.chmod(0o644)
    link = home / spec.hooks_file
    link.symlink_to(managed)

    installed = install_integration(
        harness, home, command_path=publishers(tmp_path)[harness]
    )

    assert f"installed {spec.display} lifecycle hooks in {link}" in installed
    assert link.is_symlink()
    assert link.readlink() == managed
    text = managed.read_text(encoding="utf-8")
    assert '"statusLine": "café → ✓"' in text
    assert set(json.loads(text)["hooks"]) == {
        *spec.events,
        *(event for event, _matcher in spec.matched_events),
    }
    assert stat.S_IMODE(managed.stat().st_mode) == 0o644
    assert list(dotfiles.iterdir()) == [managed]

    removed = remove_integration(harness, home)

    assert f"removed the Dashpot hooks from {link}" in removed
    assert link.is_symlink()
    assert managed.read_text(encoding="utf-8") == '{\n  "statusLine": "café → ✓"\n}\n'
    assert stat.S_IMODE(managed.stat().st_mode) == 0o644


def test_remove_keeps_a_linked_hooks_file_that_held_only_dashpot_hooks(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    managed = tmp_path / "dotfiles" / "hooks.json"
    managed.parent.mkdir()
    managed.write_text("{}\n")
    (home / "hooks.json").symlink_to(managed)
    install_integration("codex", home, command_path=publisher(tmp_path))

    messages = remove_integration("codex", home)

    assert f"removed the Dashpot hooks from {home / 'hooks.json'}" in messages
    assert (home / "hooks.json").is_symlink()
    assert managed.read_text() == "{}\n"


def test_a_replaced_hooks_file_keeps_its_mode(tmp_path: Path) -> None:
    home = codex_home(tmp_path)
    hooks = home / "hooks.json"
    hooks.write_text("{}\n")
    hooks.chmod(0o640)

    install_integration("codex", home, command_path=publisher(tmp_path))

    assert stat.S_IMODE(hooks.stat().st_mode) == 0o640
    assert not hooks.is_symlink()
    assert [path.name for path in home.iterdir()] == ["hooks.json"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes any directory")
def test_a_hooks_file_linked_into_a_read_only_directory_refuses_the_install(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    managed = store / "settings.json"
    managed.write_text("{}\n")
    link = home / "settings.json"
    link.symlink_to(managed)
    store.chmod(0o555)
    try:
        with pytest.raises(IntegrationError) as refused:
            install_integration(
                "claude-code", home, command_path=claude_publisher(tmp_path)
            )
    finally:
        store.chmod(0o755)

    assert str(refused.value) == (
        f"cannot install the Claude Code lifecycle hooks in {link}, a link to "
        f"{managed}: {store} is not writable; make it writable and retry"
    )
    assert link.is_symlink()
    assert managed.read_text() == "{}\n"
    assert not (home / "skills").exists()


def test_a_dangling_hooks_link_is_refused_naming_what_it_names(
    tmp_path: Path,
) -> None:
    home = claude_home(tmp_path)
    gone = tmp_path / "dotfiles" / "settings.json"
    hop = tmp_path / "hop.json"
    hop.symlink_to(gone)
    link = home / "settings.json"
    link.symlink_to(hop)

    with pytest.raises(IntegrationError) as refused:
        install_integration(
            "claude-code", home, command_path=claude_publisher(tmp_path)
        )

    assert str(refused.value) == (
        f"cannot install the Claude Code lifecycle hooks in {link}: the link leads "
        f"to nothing at {gone.resolve()}; restore what it names or move it, and retry"
    )
    assert link.is_symlink()
    assert not gone.exists()
    assert not (home / "skills").exists()


def test_a_hooks_file_that_is_not_utf8_is_refused_by_install_status_and_remove(
    tmp_path: Path,
) -> None:
    home = codex_home(tmp_path)
    install_integration("codex", home, command_path=publisher(tmp_path))
    hooks = home / "hooks.json"
    hooks.write_bytes(b"\xff{}")

    with pytest.raises(IntegrationError) as install_refused:
        install_integration("codex", home, command_path=publisher(tmp_path))
    report = integration_status(
        "codex", home, state_dir=tmp_path / "state", current=tmp_path
    )
    with pytest.raises(IncompleteRemovalError) as remove_incomplete:
        remove_integration("codex", home)

    refusal = f"cannot read Codex hooks at {hooks}: "
    assert str(install_refused.value).startswith(refusal)
    assert str(install_refused.value).endswith("; fix or move the file and retry")
    assert report[0].startswith(refusal)
    assert str(remove_incomplete.value).startswith(refusal)
    # Each skill copy, a step of its own, is removed regardless.
    assert remove_incomplete.value.messages == removed_skills(home)
    assert hooks.read_bytes() == b"\xff{}"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes any directory")
@pytest.mark.parametrize("foreign", [False, True])
def test_remove_carries_on_past_a_hooks_file_it_cannot_change(
    tmp_path: Path, foreign: bool
) -> None:
    home = codex_home(tmp_path)
    if foreign:
        theirs = {"type": "command", "command": "notify-send done"}
        (home / "hooks.json").write_text(
            json.dumps({"hooks": {"Stop": [{"hooks": [theirs]}]}})
        )
    install_integration("codex", home, command_path=publisher(tmp_path))
    hooks = (home / "hooks.json").read_bytes()
    home.chmod(0o555)
    try:
        with pytest.raises(IncompleteRemovalError) as incomplete:
            remove_integration("codex", home)
    finally:
        home.chmod(0o755)

    path = home / "hooks.json"
    assert str(incomplete.value).startswith(
        f"could not remove the Dashpot hooks from {path}: [Errno 13] "
    )
    assert str(incomplete.value).endswith(
        "; the rest of the integration is removed, and rerunning 'dashpot "
        "integrate codex --remove' once that is fixed finishes it"
    )
    assert incomplete.value.messages == removed_skills(home)
    assert not installed_skill(home).exists()
    assert path.read_bytes() == hooks
    assert [entry.name for entry in home.iterdir()] == ["hooks.json"]


def test_each_harness_reads_its_own_configuration_variable() -> None:
    claude = integration("claude-code")
    codex = integration("codex")
    opencode = integration("opencode")

    assert configuration_directory(
        claude, {"CLAUDE_CONFIG_DIR": "/work/claude", "CODEX_HOME": "/work/codex"}
    ) == ConfigurationDirectory(Path("/work/claude"), "CLAUDE_CONFIG_DIR")
    assert configuration_directory(
        codex, {"CODEX_HOME": "/work/codex"}
    ) == ConfigurationDirectory(Path("/work/codex"), "CODEX_HOME")
    assert configuration_directory(codex, {"CODEX_HOME": ""}) == (
        ConfigurationDirectory(Path.home() / ".codex")
    )
    assert configuration_directory(claude, {}) == (
        ConfigurationDirectory(Path.home() / ".claude")
    )
    assert configuration_directory(
        opencode, {"XDG_CONFIG_HOME": "/xdg", "CLAUDE_CONFIG_DIR": "/work/claude"}
    ) == ConfigurationDirectory(Path("/xdg/opencode"))
    assert str(ConfigurationDirectory(Path("/w"), "CODEX_HOME")) == (
        "/w (from CODEX_HOME)"
    )


def test_claude_code_is_integrated_where_claude_config_dir_names(
    tmp_path: Path, user_home: Path
) -> None:
    configured = tmp_path / "work-claude"
    configured.mkdir()
    (user_home / ".claude").mkdir()
    # The variable reaches integrate through its environment value alone, not
    # through this process's environment.
    environment = IntegrationEnvironment(environ={"CLAUDE_CONFIG_DIR": str(configured)})
    settings = configured / "settings.json"

    installed = install_integration(
        "claude-code",
        command_path=publishers(tmp_path)["claude-code"],
        environment=environment,
    )
    report = integration_status(
        "claude-code",
        state_dir=tmp_path / "state",
        current=tmp_path,
        environment=environment,
    )

    assert f"installed Claude Code lifecycle hooks in {settings}" in installed
    copy = configured / "skills" / ISSUE_WORK_SKILL.name
    assert f"installed Dashpot Issue work skill in {copy}" in installed
    assert list((user_home / ".claude").iterdir()) == []
    assert report[0] == (
        f"Claude Code configuration directory: {configured} (from CLAUDE_CONFIG_DIR)"
    )
    assert report[1].startswith(f"installed in {settings} for: ")
    assert integration_presence("claude-code", environment=environment).state == (
        "integrated"
    )
    hooks = settings.read_text()
    settings.unlink()
    partial = integration_presence("claude-code", environment=environment)
    assert partial.state == "partial"
    assert partial.detail.startswith(
        f"no Dashpot hooks at {settings} (CLAUDE_CONFIG_DIR names {configured}), "
        "but the Dashpot "
    )
    settings.write_text(hooks)

    removed = remove_integration("claude-code", environment=environment)

    assert f"removed {settings}; it contained only the Dashpot hooks" in removed
    assert not copy.exists()
    assert integration_presence("claude-code", environment=environment).detail == (
        f"no Dashpot hooks at {settings} (CLAUDE_CONFIG_DIR names {configured})"
    )
    # This process's own environment names no such directory.
    assert integration_presence("claude-code").detail == (
        f"no Dashpot hooks at {user_home / '.claude' / 'settings.json'}"
    )


def test_codex_is_integrated_where_codex_home_names_with_its_skills_in_agents(
    tmp_path: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "codex-home"
    configured.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(configured))

    installed = install_integration("codex", command_path=publishers(tmp_path)["codex"])

    hooks = configured / "hooks.json"
    assert f"installed Codex lifecycle hooks in {hooks}" in installed
    copy = user_home / ".agents" / "skills" / ISSUE_WORK_SKILL.name
    assert f"installed Dashpot Issue work skill in {copy}" in installed
    assert not (user_home / ".codex").exists()
    assert [report.outcome for report in refresh(tmp_path, "codex")] == ["installed"]


def test_a_configuration_variable_naming_no_directory_is_named_in_the_refusal(
    tmp_path: Path, user_home: Path
) -> None:
    default_home("codex")
    missing = tmp_path / "missing"
    environment = IntegrationEnvironment(environ={"CODEX_HOME": str(missing)})

    with pytest.raises(IntegrationError) as refused:
        install_integration(
            "codex",
            command_path=publishers(tmp_path)["codex"],
            environment=environment,
        )
    report = integration_status(
        "codex",
        state_dir=tmp_path / "state",
        current=tmp_path,
        environment=environment,
    )

    assert str(refused.value) == (
        f"no Codex configuration directory at {missing} (from CODEX_HOME); "
        "install and run Codex once before integrating"
    )
    assert report[:2] == [
        f"Codex configuration directory: {missing} (from CODEX_HOME)",
        f"Codex configuration directory not found: {missing} (from CODEX_HOME)",
    ]
    assert integration_presence("codex", environment=environment).detail == (
        f"no Codex configuration directory at {missing} (from CODEX_HOME)"
    )
    assert list((user_home / ".codex").iterdir()) == []


@pytest.mark.parametrize(
    ("named", "installed", "status", "remove", "refusal"),
    [
        (("codex",), True, False, False, "not both"),
        ((), False, False, True, "--remove takes exactly one named harness"),
        (
            ("claude-code", "codex"),
            False,
            False,
            True,
            "--remove takes exactly one named harness",
        ),
        ((), True, False, True, "--remove takes exactly one named harness"),
        ((), False, False, False, "name a harness to integrate"),
    ],
)
def test_integrate_arguments_that_name_no_one_action_are_refused(
    named: tuple[Harness, ...],
    installed: bool,
    status: bool,
    remove: bool,
    refusal: str,
) -> None:
    with pytest.raises(IntegrationError, match=refusal):
        refuse_integrate_arguments(
            named, installed=installed, status=status, remove=remove
        )


@pytest.mark.parametrize(
    ("named", "installed", "status", "remove"),
    [
        (("codex",), False, False, False),
        (("codex",), False, False, True),
        (("codex",), False, True, False),
        (("claude-code", "codex"), False, False, False),
        (("claude-code", "codex"), False, True, False),
        ((), True, False, False),
        ((), True, True, False),
        ((), False, True, False),
    ],
)
def test_integrate_arguments_that_name_one_action_pass(
    named: tuple[Harness, ...], installed: bool, status: bool, remove: bool
) -> None:
    refuse_integrate_arguments(named, installed=installed, status=status, remove=remove)


@pytest.mark.parametrize(
    ("outcomes", "refusals", "incomplete", "installed", "failed"),
    [
        ((), 0, False, False, False),
        (("installed", "partial", "not integrated"), 0, False, True, False),
        (("partial", "not integrated"), 0, False, False, False),
        (("installed", "incomplete"), 0, True, True, True),
        (("refused", "refused", "installed"), 2, False, True, True),
        (("refused", "not integrated"), 1, False, False, True),
    ],
)
def test_harness_reports_total_to_the_commands_outcome(
    outcomes: tuple[HarnessOutcome, ...],
    refusals: int,
    incomplete: bool,
    installed: bool,
    failed: bool,
) -> None:
    harnesses: tuple[Harness, ...] = ("claude-code", "codex", "opencode")
    reports = [
        HarnessReport(harness, outcome)
        for harness, outcome in zip(harnesses, outcomes, strict=False)
    ]

    totals = integration_totals(reports)

    assert (totals.refusals, totals.incomplete, totals.installed, totals.failed) == (
        refusals,
        incomplete,
        installed,
        failed,
    )
