"""``dashpot integrate opencode``: the managed plugin, its skill, and its status (ADR 0079)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from dashpot.sessions.integrate import (
    ISSUE_WORK_SKILL_MARKER,
    ISSUE_WORK_SKILL_VERSION,
    OPENCODE,
    OPENCODE_UNSUPPORTED,
    IntegrationError,
    install_integration,
    integration_status,
    issue_work_skill_directory,
    remove_integration,
    render_plugin,
)
from test_integrate import environment_publisher, linked_worktree


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every harness's user directories inside the test's own directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


def opencode_home(root: Path) -> Path:
    home = root / "config" / "opencode"
    home.mkdir(parents=True, exist_ok=True)
    return home


def helper(root: Path) -> Path:
    command = root / "bin" / "dashpot-opencode-hook"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


def plugin_file(home: Path) -> Path:
    return home / "plugins" / "dashpot.js"


def status(
    home: Path,
    tmp_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    version_probe: Callable[[], str | None] = lambda: "1.18.30",
) -> list[str]:
    return integration_status(
        "opencode",
        home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ=environ or {},
        version_probe=version_probe,
    )


def test_the_default_home_is_opencodes_global_configuration_directory(
    _home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert OPENCODE.default_home == _home / ".config" / "opencode"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert OPENCODE.default_home == tmp_path / "xdg" / "opencode"
    assert OPENCODE.default_skills_home == tmp_path / "xdg" / "opencode" / "skills"
    assert issue_work_skill_directory(OPENCODE, OPENCODE.default_home) == (
        tmp_path / "xdg" / "opencode" / "skills" / "dashpot-issue-work"
    )


def test_install_writes_the_plugin_bound_to_the_helper_and_the_skill(
    tmp_path: Path,
) -> None:
    home = opencode_home(tmp_path)
    command = helper(tmp_path)

    messages = install_integration("opencode", home, command_path=command)

    installed = plugin_file(home).read_text()
    assert installed == render_plugin(command)
    assert installed.startswith("// dashpot-managed-plugin: opencode\n")
    assert f"const HELPER = {json.dumps(str(command))};" in installed
    assert "__DASHPOT_OPENCODE_HELPER__" not in installed
    skill = home / "skills" / "dashpot-issue-work"
    assert ISSUE_WORK_SKILL_MARKER in (skill / "SKILL.md").read_text()
    assert messages == [
        f"installed the OpenCode plugin in {plugin_file(home)}",
        f"hook publisher: {command}",
        f"installed Dashpot Issue work skill in {skill}",
        OPENCODE_UNSUPPORTED,
    ]

    again = install_integration("opencode", home, command_path=command)

    assert again[0] == f"OpenCode plugin already installed in {plugin_file(home)}"
    assert plugin_file(home).read_text() == installed


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_the_rendered_plugin_is_a_module_node_can_parse(tmp_path: Path) -> None:
    module = tmp_path / "dashpot.mjs"
    module.write_text(
        render_plugin(tmp_path / 'it\'s "here"' / "dashpot-opencode-hook")
    )

    checked = subprocess.run(
        ["node", "--check", str(module)], capture_output=True, text=True, check=False
    )

    assert checked.returncode == 0, checked.stderr


def test_install_rebinds_a_plugin_to_a_moved_helper(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    install_integration("opencode", home, command_path=helper(tmp_path / "old"))
    moved = helper(tmp_path / "new")

    messages = install_integration("opencode", home, command_path=moved)

    assert messages[0] == f"updated the OpenCode plugin in {plugin_file(home)}"
    assert plugin_file(home).read_text() == render_plugin(moved)


def test_install_refuses_a_plugin_dashpot_does_not_manage(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    plugin_file(home).parent.mkdir()
    plugin_file(home).write_text("export const Mine = async () => ({})\n")

    with pytest.raises(IntegrationError, match="is not a plugin Dashpot manages"):
        install_integration("opencode", home, command_path=helper(tmp_path))

    assert plugin_file(home).read_text() == "export const Mine = async () => ({})\n"
    assert not (home / "skills").exists()


def test_install_needs_opencodes_configuration_directory(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="no OpenCode configuration directory"):
        install_integration(
            "opencode", tmp_path / "missing", command_path=helper(tmp_path)
        )


def test_install_refuses_a_helper_inside_a_linked_worktree(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    _main, linked = linked_worktree(tmp_path)

    with pytest.raises(IntegrationError, match=f"linked Worktree {linked}"):
        install_integration(
            "opencode",
            home,
            command_path=environment_publisher(linked, "opencode"),
        )

    assert not plugin_file(home).exists()


def test_remove_takes_only_what_opencodes_integration_owns(
    tmp_path: Path, _home: Path
) -> None:
    home = opencode_home(tmp_path)
    install_integration("opencode", home, command_path=helper(tmp_path))
    claude_skill = _home / ".claude" / "skills" / "dashpot-issue-work"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text(f"{ISSUE_WORK_SKILL_MARKER}\n")

    messages = remove_integration("opencode", home)

    skill = home / "skills" / "dashpot-issue-work"
    assert messages == [
        f"removed the OpenCode plugin {plugin_file(home)}",
        f"removed the Dashpot Issue work skill from {skill}",
    ]
    assert not plugin_file(home).exists()
    assert not skill.exists()
    assert (claude_skill / "SKILL.md").is_file()
    assert remove_integration("opencode", home)[0] == (
        f"OpenCode integration is not installed: no {plugin_file(home)}"
    )


def test_remove_leaves_a_plugin_dashpot_does_not_manage(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    plugin_file(home).parent.mkdir()
    plugin_file(home).write_text("export const Mine = async () => ({})\n")

    messages = remove_integration("opencode", home)

    assert messages[0].startswith(f"left {plugin_file(home)} unchanged: ")
    assert plugin_file(home).is_file()


def test_status_of_a_current_installation(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    command = helper(tmp_path)
    install_integration("opencode", home, command_path=command)

    messages = status(home, tmp_path)

    assert messages[:3] == [
        f"plugin installed in {plugin_file(home)}",
        f"hook publisher: {command}",
        f"Issue work skill installed in {home / 'skills' / 'dashpot-issue-work'} "
        f"for Dashpot {ISSUE_WORK_SKILL_VERSION}",
    ]
    assert "OpenCode release: 1.18.30, the measured release" in messages
    assert OPENCODE_UNSUPPORTED in messages
    assert messages[-1] == (
        "Agent Session identity claimed here: none for OpenCode (only a command "
        "its plugin corroborated carries one)"
    )


def test_status_reports_what_needs_repair(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    assert f"not installed: no {plugin_file(home)}" in status(home, tmp_path)
    command = helper(tmp_path)
    install_integration("opencode", home, command_path=command)
    stale = plugin_file(home).read_text().replace("QUEUE_LIMIT = 16", "QUEUE_LIMIT = 4")
    plugin_file(home).write_text(stale)
    command.chmod(0o644)

    messages = status(home, tmp_path)

    assert f"plugin update available at {plugin_file(home)}; run 'dashpot " in (
        "\n".join(messages)
    )
    assert f"hook publisher at {command} is not executable" in messages

    command.unlink()
    assert any(
        message.startswith(f"hook publisher missing at {command}")
        for message in status(home, tmp_path)
    )

    for unbound in ("", 'const HELPER = "\\q";\n'):
        plugin_file(home).write_text(f"// dashpot-managed-plugin: opencode\n{unbound}")
        assert status(home, tmp_path)[0].startswith(
            f"plugin at {plugin_file(home)} names no hook publisher"
        )


def test_status_names_a_conflicting_plugin(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    plugin_file(home).mkdir(parents=True)

    messages = status(home, tmp_path)

    assert messages[0].startswith(
        f"plugin conflict: cannot read the plugin at {plugin_file(home)}"
    )


def test_status_warns_about_a_linked_worktree_helper(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)
    main, linked = linked_worktree(tmp_path)
    install_integration(
        "opencode", home, command_path=environment_publisher(main, "opencode")
    )
    linked_helper = environment_publisher(linked, "opencode")
    plugin_file(home).write_text(render_plugin(linked_helper))

    messages = status(home, tmp_path)

    assert any(
        message.startswith(
            f"warning: that publisher lives in the linked Worktree {linked}"
        )
        for message in messages
    )


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (None, "OpenCode release: not found on PATH"),
        (
            "1.19.0",
            "OpenCode release: 1.19.0; the plugin was measured against 1.18.30",
        ),
    ],
)
def test_status_names_an_unmeasured_release(
    tmp_path: Path, version: str | None, expected: str
) -> None:
    home = opencode_home(tmp_path)

    assert expected in status(home, tmp_path, version_probe=lambda: version)


def test_status_asks_the_opencode_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = opencode_home(tmp_path)
    binary = tmp_path / "path" / "opencode"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\necho 1.18.30\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary.parent))

    messages = integration_status(
        "opencode", home, state_dir=tmp_path / "state", current=tmp_path, environ={}
    )

    assert "OpenCode release: 1.18.30, the measured release" in messages
    for broken in ("#!/bin/sh\nexit 3\n", "#!/nonexistent/interpreter\n"):
        binary.write_text(broken)
        messages = integration_status(
            "opencode", home, state_dir=tmp_path / "state", current=tmp_path, environ={}
        )
        assert "OpenCode release: not found on PATH" in messages
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    messages = integration_status(
        "opencode", home, state_dir=tmp_path / "state", current=tmp_path, environ={}
    )
    assert "OpenCode release: not found on PATH" in messages


def test_status_warns_when_opencode_runs_without_plugins(tmp_path: Path) -> None:
    home = opencode_home(tmp_path)

    messages = status(home, tmp_path, environ={"OPENCODE_PURE": "1"})

    assert any(
        message.startswith("warning: OPENCODE_PURE is set") for message in messages
    )


def test_status_warns_about_another_harness_copy_opencode_also_discovers(
    tmp_path: Path, _home: Path
) -> None:
    home = opencode_home(tmp_path)
    install_integration("opencode", home, command_path=helper(tmp_path))
    (_home / ".codex").mkdir()
    install_integration(
        "codex", _home / ".codex", command_path=helper(tmp_path / "codex")
    )
    agents_skill = _home / ".agents" / "skills" / "dashpot-issue-work"
    claude_skill = _home / ".claude" / "skills" / "dashpot-issue-work"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_bytes(b"\xff not a skill Dashpot wrote\n")

    messages = status(home, tmp_path)

    warnings = [message for message in messages if "also discovers" in message]
    assert warnings == [
        f"warning: OpenCode also discovers the Issue work skill at {claude_skill}, "
        "which differs from this Dashpot's, and may use either; run 'dashpot "
        "integrate claude-code' or move it"
    ]
    assert (agents_skill / "SKILL.md").is_file()


def test_status_warns_about_another_copy_of_the_plugin_opencode_also_loads(
    tmp_path: Path, _home: Path
) -> None:
    home = opencode_home(tmp_path)
    install_integration("opencode", home, command_path=helper(tmp_path))
    worktree = tmp_path / "project"
    (worktree / ".git").mkdir(parents=True)
    current = worktree / "src"
    configured = tmp_path / "custom"
    # OpenCode loads every plugin file of each directory, whatever its name.
    copies = [
        home / "plugin" / "dashpot-old.ts",
        worktree / ".opencode" / "plugins" / "dashpot.js",
        _home / ".opencode" / "plugins" / "other.js",
        configured / "plugin" / "dashpot.js",
    ]
    # A user's own plugin of the same name, and a copy above the Worktree,
    # are not copies OpenCode loads for this Worktree.
    above = tmp_path / ".opencode" / "plugins" / "dashpot.js"
    for copy in (*copies, above):
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(plugin_file(home), copy)
    plugin_file(current / ".opencode").parent.mkdir(parents=True)
    plugin_file(current / ".opencode").write_text("export default {}\n")

    def warned(environ: Mapping[str, str]) -> list[str]:
        messages = integration_status(
            "opencode",
            home,
            state_dir=tmp_path / "state",
            current=current,
            environ=environ,
            version_probe=lambda: "1.18.30",
        )
        prefix = "warning: OpenCode also loads a copy of the Dashpot plugin at "
        return [
            message.removeprefix(prefix).split(";")[0]
            for message in messages
            if message.startswith(prefix)
        ]

    assert warned({"OPENCODE_CONFIG_DIR": str(configured)}) == [
        str(copy) for copy in copies
    ]
    # Without project configuration, and with the configured directory one
    # OpenCode reads anyway, each copy is reported once at most.
    assert warned(
        {
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_CONFIG_DIR": str(home),
        }
    ) == [str(copies[0]), str(copies[2])]
    assert warned({"OPENCODE_CONFIG_DIR": str(worktree / ".opencode")}) == [
        str(copy) for copy in copies[:3]
    ]
