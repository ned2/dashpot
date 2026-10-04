"""``dashpot integrate``: every bundled agent definition, installed, checked and removed.

OpenCode's integration manages one file per agent definition Dashpot
bundles, beside its plugin and skills, and only a file that carries that
agent's own marker (ADR 0093). Codex and Claude Code install none. A second
bundled agent is injected from a fixture file, so behaviour across several
agents is exercised while Dashpot ships one.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from dashpot.core.model import Harness
from dashpot.sessions.integrate import (
    BUNDLED_AGENTS,
    BUNDLED_AGENTS_ROOT,
    BUNDLED_SKILL_VERSION,
    ISSUE_WORK_SKILL,
    OPENCODE,
    OPENCODE_ACCEPTED_VERSION,
    WORKER_AGENT,
    BundledAgent,
    IntegrationError,
    agent_file,
    install_integration,
    integration,
    integration_status,
    remove_integration,
    skill_directory,
)

# The keys OpenCode 2.0.22 decodes as a native agent definition
# (packages/schema/src/config/agent.ts, plus ``variant``). Any other
# frontmatter key makes it decode the whole file as a v1 definition.
NATIVE_AGENT_KEYS = {
    "model",
    "variant",
    "request",
    "system",
    "description",
    "mode",
    "hidden",
    "color",
    "steps",
    "disabled",
    "permissions",
}


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every harness's user directories inside the test's own directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    return home


@pytest.fixture
def second(tmp_path: Path) -> BundledAgent:
    """A second bundled agent definition."""
    source = tmp_path / "bundled" / "fixture-second-agent.md"
    source.parent.mkdir(parents=True)
    agent = BundledAgent(
        name="fixture-second-agent", label="second agent", source=source
    )
    source.write_text(f"---\n{agent.marker}\ndescription: The second agent.\n---\n")
    return agent


def opencode_home() -> Path:
    """OpenCode's global configuration directory, created as its first run would."""
    OPENCODE.default_home.mkdir(parents=True, exist_ok=True)
    return OPENCODE.default_home


def publisher(tmp_path: Path, harness: Harness) -> Path:
    command = tmp_path / "bin" / integration(harness).command_name
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


def accepted() -> str:
    return f"opencode v{OPENCODE_ACCEPTED_VERSION}"


def install(
    tmp_path: Path, agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS
) -> list[str]:
    return install_integration(
        "opencode",
        opencode_home(),
        command_path=publisher(tmp_path, "opencode"),
        version_probe=accepted,
        agents=agents,
    )


def status(
    tmp_path: Path, agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS
) -> list[str]:
    return integration_status(
        "opencode",
        opencode_home(),
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ={},
        version_probe=accepted,
        agents=agents,
    )


def remove(agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS) -> list[str]:
    return remove_integration("opencode", opencode_home(), agents=agents)


def copy_of(agent: BundledAgent) -> Path:
    copy = agent_file(OPENCODE, opencode_home(), agent)
    assert copy is not None
    return copy


def frontmatter(text: str) -> tuple[list[str], str]:
    """The frontmatter's lines and the body after it."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    return str(match.group(1)).splitlines(), text[match.end() :]


def test_the_worker_agent_is_installed_in_opencodes_agent_directory(
    home: Path, tmp_path: Path
) -> None:
    copy = home / ".config" / "opencode" / "agent" / "dashpot-worker.md"
    assert copy_of(WORKER_AGENT) == copy

    messages = install(tmp_path)

    assert f"installed Dashpot worker agent in {copy}" in messages
    assert copy.read_bytes() == WORKER_AGENT.source.read_bytes()
    assert (
        f"worker agent installed in {copy} for Dashpot {BUNDLED_SKILL_VERSION}"
        in status(tmp_path)
    )

    again = install(tmp_path)

    assert f"Dashpot worker agent already installed in {copy}" in again
    assert copy.read_bytes() == WORKER_AGENT.source.read_bytes()


def test_the_worker_agent_denies_the_session_move_and_nothing_else() -> None:
    # The skill launches every OpenCode worker by this name.
    assert WORKER_AGENT.name == "dashpot-worker"
    lines, body = frontmatter(WORKER_AGENT.source.read_text(encoding="utf-8"))

    # The marker is a YAML comment inside the frontmatter, which OpenCode's
    # parser skips: neither a key it does not know nor a line in the body,
    # which would become the agent's system prompt.
    assert lines[0] == WORKER_AGENT.marker
    assert all(line.startswith("#") for line in lines if "dashpot-managed" in line)
    keys = {
        line.split(":", 1)[0]
        for line in lines
        if line and not line.startswith(("#", " "))
    }
    assert keys == {"description", "mode", "permissions"}
    assert keys <= NATIVE_AGENT_KEYS
    assert "mode: subagent" in lines
    rules = [line.strip() for line in lines if line.startswith(" ")]
    assert rules == [
        '- action: "*session_move"',
        'resource: "*"',
        "effect: deny",
    ]
    # No body, so OpenCode's default system prompt applies; no model is set,
    # so the user's own does.
    assert body == ""
    description = next(line for line in lines if line.startswith("description:"))
    assert "dashpot-execute-issues" in description
    assert "cannot move any session" in description
    # A colon-free description stays a plain YAML scalar.
    assert ":" not in description.removeprefix("description:")


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_codex_and_claude_code_install_no_agent(
    harness: Harness, home: Path, tmp_path: Path
) -> None:
    spec = integration(harness)
    spec.default_home.mkdir(parents=True)
    assert agent_file(spec, spec.default_home, WORKER_AGENT) is None

    installed = install_integration(
        harness, spec.default_home, command_path=publisher(tmp_path, harness)
    )
    reported = integration_status(
        harness,
        spec.default_home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ={},
    )
    removed = remove_integration(harness, spec.default_home)

    assert not any(
        "worker agent" in message for message in installed + reported + removed
    )
    assert not list(home.rglob("dashpot-worker.md"))


def test_status_reports_a_missing_agent_and_install_writes_it(
    tmp_path: Path, second: BundledAgent
) -> None:
    install(tmp_path)
    agents = (WORKER_AGENT, second)

    assert f"second agent not installed: no {copy_of(second)}" in status(
        tmp_path, agents
    )

    messages = install(tmp_path, agents)

    assert f"Dashpot worker agent already installed in {copy_of(WORKER_AGENT)}" in (
        messages
    )
    assert f"installed Dashpot second agent in {copy_of(second)}" in messages
    assert copy_of(second).read_bytes() == second.source.read_bytes()


def test_an_edited_managed_agent_is_reported_and_updated(tmp_path: Path) -> None:
    install(tmp_path)
    copy = copy_of(WORKER_AGENT)
    copy.write_text(copy.read_text().replace("mode: subagent", "mode: all"))

    assert (
        f"worker agent update available at {copy}; run 'dashpot integrate "
        "opencode' to repair"
    ) in status(tmp_path)

    messages = install(tmp_path)

    assert f"updated Dashpot worker agent in {copy}" in messages
    assert copy.read_bytes() == WORKER_AGENT.source.read_bytes()
    # No temporary is left where OpenCode would read it as a definition.
    assert sorted(path.name for path in copy.parent.iterdir()) == [copy.name]


def test_an_unmanaged_agent_of_a_bundled_name_is_never_touched(
    tmp_path: Path, second: BundledAgent
) -> None:
    copy = copy_of(WORKER_AGENT)
    copy.parent.mkdir(parents=True)
    # Another bundled agent's marker does not make a file this agent's.
    mine = f"---\n{second.marker}\ndescription: Mine.\n---\n\nMy own worker.\n"
    copy.write_text(mine)
    plugin = opencode_home() / OPENCODE.hooks_file

    with pytest.raises(IntegrationError) as refused:
        install(tmp_path)

    assert str(refused.value) == (
        f"cannot install the Dashpot worker agent at {copy}: an existing agent "
        "is not managed by Dashpot; move it and retry"
    )
    # Refused before anything was written.
    assert not plugin.exists()
    assert not skill_directory(OPENCODE, opencode_home(), ISSUE_WORK_SKILL).exists()
    assert copy.read_text() == mine
    assert f"worker agent conflict at {copy}: not managed by Dashpot" in status(
        tmp_path
    )

    messages = remove()

    assert f"left unmanaged worker agent unchanged at {copy}" in messages
    assert copy.read_text() == mine


@pytest.mark.parametrize("shape", ["directory", "dangling link"])
def test_a_path_that_is_no_agent_file_is_a_conflict_left_in_place(
    tmp_path: Path, shape: str
) -> None:
    copy = copy_of(WORKER_AGENT)
    copy.parent.mkdir(parents=True)
    if shape == "directory":
        copy.mkdir()
    else:
        copy.symlink_to(tmp_path / "nowhere.md")

    with pytest.raises(IntegrationError) as refused:
        install(tmp_path)

    assert str(refused.value) == (
        f"cannot install the Dashpot worker agent at {copy}: the path is not a "
        "file; move it and retry"
    )
    assert f"worker agent conflict at {copy}: not managed by Dashpot" in status(
        tmp_path
    )
    assert f"left unmanaged worker agent unchanged at {copy}" in remove()
    assert os.path.lexists(copy)
    assert copy.is_dir() == (shape == "directory")


def test_an_install_refusal_names_every_skill_and_agent_it_cannot_manage(
    tmp_path: Path,
) -> None:
    skill = skill_directory(OPENCODE, opencode_home(), ISSUE_WORK_SKILL)
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Mine.\n")
    copy = copy_of(WORKER_AGENT)
    copy.parent.mkdir(parents=True)
    copy.write_text("Mine.\n")

    with pytest.raises(IntegrationError) as refused:
        install(tmp_path)

    assert str(refused.value) == (
        f"cannot install the Dashpot Issue work skill at {skill}: an existing "
        "skill is not managed by Dashpot; move it and retry; "
        f"cannot install the Dashpot worker agent at {copy}: an existing agent "
        "is not managed by Dashpot; move it and retry"
    )


def test_an_unreadable_agent_is_refused_reported_and_left_alone(
    tmp_path: Path,
) -> None:
    copy = copy_of(WORKER_AGENT)
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b"\xff not an agent Dashpot wrote\n")

    with pytest.raises(IntegrationError, match="not managed by Dashpot"):
        install(tmp_path)

    assert any(
        message.startswith(f"worker agent unreadable at {copy}: ")
        for message in status(tmp_path)
    )
    assert any(
        message.startswith(f"could not inspect Dashpot worker agent at {copy}: ")
        for message in remove()
    )
    assert copy.read_bytes() == b"\xff not an agent Dashpot wrote\n"


def test_remove_takes_every_managed_agent_and_keeps_the_users_own(
    tmp_path: Path, second: BundledAgent
) -> None:
    agents = (WORKER_AGENT, second)
    install(tmp_path, agents)
    directory = copy_of(WORKER_AGENT).parent
    theirs = directory / "reviewer.md"
    theirs.write_text("---\ndescription: The user's own agent.\n---\n")

    messages = remove(agents)

    assert f"removed the Dashpot worker agent from {copy_of(WORKER_AGENT)}" in (
        messages
    )
    assert f"removed the Dashpot second agent from {copy_of(second)}" in messages
    assert sorted(path.name for path in directory.iterdir()) == ["reviewer.md"]

    again = remove(agents)

    assert f"Dashpot worker agent is not installed: no {copy_of(WORKER_AGENT)}" in again
    assert f"worker agent not installed: no {copy_of(WORKER_AGENT)}" in status(tmp_path)


def test_every_bundled_agent_file_is_registered_and_marked() -> None:
    names = [agent.name for agent in BUNDLED_AGENTS]
    assert len(set(names)) == len(names)
    assert sorted(f"{name}.md" for name in names) == sorted(
        path.name for path in BUNDLED_AGENTS_ROOT.iterdir()
    )
    for agent in BUNDLED_AGENTS:
        assert agent.source == BUNDLED_AGENTS_ROOT / f"{agent.name}.md"
        lines, _body = frontmatter(agent.source.read_text(encoding="utf-8"))
        assert agent.marker in lines
