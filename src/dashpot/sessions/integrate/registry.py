"""What ``integrate`` installs: each harness's integration, and the skills and agents it bundles.

A harness's integration is reached through ``integration(harness)``; the
Harness Adapters in ``sessions.harnesses`` are a different registry, of how
each harness identifies an Agent Session.
"""

from __future__ import annotations

import os
import shutil
import sysconfig
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, override

from ...core.model import HARNESS_DISPLAY, Harness
from ..harnesses import HarnessError
from .writes import IntegrationError

# The Dashpot release the bundled skills and agents are written for, kept
# aligned with the package version (docs/releasing.md).
BUNDLED_SKILL_VERSION = "0.1.0"
BUNDLED_SKILLS_ROOT = Path(__file__).parents[2] / "skills"
BUNDLED_AGENTS_ROOT = Path(__file__).parents[2] / "agents"


@dataclass(frozen=True, slots=True)
class BundledSkill:
    """One agent skill Dashpot ships, which ``integrate`` installs for each harness.

    A copy is Dashpot's to manage only while its ``SKILL.md`` carries this
    skill's own marker: a directory of the same name without it is the
    user's, and is never overwritten or removed. Inside a managed copy, the
    files its manifest names are Dashpot's, and any other is the user's
    (ADR 0103).
    """

    name: str
    # What ``integrate``'s messages call the skill, such as "Issue work skill".
    label: str
    source: Path

    @property
    def marker(self) -> str:
        """The line that marks an installed copy as Dashpot's to manage."""
        return f"<!-- dashpot-managed-skill: {self.name} -->"

    @property
    def files(self) -> tuple[Path, ...]:
        """Every file the skill ships, relative to its directory."""
        return tuple(
            sorted(
                path.relative_to(self.source)
                for path in self.source.rglob("*")
                if path.is_file()
            )
        )


ISSUE_WORK_SKILL = BundledSkill(
    name="dashpot-issue-work",
    label="Issue work skill",
    source=BUNDLED_SKILLS_ROOT / "dashpot-issue-work",
)

# Every skill ``integrate`` installs, updates, checks and removes. Adding a
# skill is an entry here and its directory under ``skills/``.
BUNDLED_SKILLS: tuple[BundledSkill, ...] = (
    ISSUE_WORK_SKILL,
    BundledSkill(
        name="dashpot-execute-issues",
        label="Issue arc skill",
        source=BUNDLED_SKILLS_ROOT / "dashpot-execute-issues",
    ),
)


@dataclass(frozen=True, slots=True)
class BundledAgent:
    """One OpenCode agent definition Dashpot ships, which ``integrate`` installs.

    The definition is one Markdown file named for the agent. An installed
    file is Dashpot's to manage only while it carries this agent's own
    marker: a file of the same name without it is the user's, and is never
    overwritten or removed (ADR 0093).
    """

    name: str
    # What ``integrate``'s messages call the agent, such as "worker agent".
    label: str
    source: Path

    @property
    def marker(self) -> str:
        """The line that marks an installed copy as Dashpot's to manage.

        It is a YAML comment inside the frontmatter. OpenCode 2.0.22 reads a
        definition with any frontmatter key it does not know as a v1 one, and
        takes the body as the agent's system prompt, so neither can carry it.
        """
        return f"# dashpot-managed-agent: {self.name}"


# The agent a ``dashpot-execute-issues`` lead launches each worker as, which
# cannot move its lead's session (ADR 0093).
WORKER_AGENT = BundledAgent(
    name="dashpot-worker",
    label="worker agent",
    source=BUNDLED_AGENTS_ROOT / "dashpot-worker.md",
)

# Every agent definition ``integrate`` installs, updates, checks and removes
# for a harness that loads them: OpenCode alone.
BUNDLED_AGENTS: tuple[BundledAgent, ...] = (WORKER_AGENT,)

# How Dashpot's lifecycle hooks reach a harness: handlers it adds to the
# harness's own hooks file, or a managed plugin the harness loads in place
# of hook definitions, as OpenCode does (ADR 0079). Each names the hook
# installer that writes, removes and reports it.
HookInstallerKind = Literal["hooks file", "plugin"]


@dataclass(frozen=True, slots=True)
class HarnessIntegration:
    """One supported harness's opt-in lifecycle hook installation."""

    harness: Harness
    display: str
    home_name: str
    # The hooks file, or for a plugin installer the managed plugin's path,
    # inside the configuration directory.
    hooks_file: str
    command_name: str
    # Where the harness reads user-wide skills: inside its configuration
    # directory when ``skills_in_configuration``, else relative to the
    # user's home directory, as Codex reads the shared ``.agents``.
    skills_home: Path
    events: tuple[str, ...]
    checks_config_toml: bool
    # Events subscribed for one tool alone, as ``(event, matcher)``: the
    # publisher runs once per matching tool call rather than per event.
    matched_events: tuple[tuple[str, str], ...] = ()
    installer: HookInstallerKind = "hooks file"
    # Whether the configuration directory is under ``$XDG_CONFIG_HOME``
    # rather than the home directory, as OpenCode's is (ADR 0079).
    xdg_configuration: bool = False
    # Where, inside its configuration directory, the harness reads the agent
    # definitions Dashpot bundles; ``None`` for a harness that installs none.
    agents_home: Path | None = None
    # The environment variable naming the configuration directory itself,
    # which the harness reads in place of its default, such as Claude
    # Code's ``CLAUDE_CONFIG_DIR``.
    home_variable: str | None = None
    skills_in_configuration: bool = False

    @property
    def default_home(self) -> Path:
        """The configuration directory the harness reads in this environment."""
        return configuration_directory(self).path

    @property
    def default_skills_home(self) -> Path:
        """The directory the harness reads user-wide skills from in this environment."""
        if self.skills_in_configuration:
            return self.default_home / self.skills_home
        return Path.home() / self.skills_home

    @property
    def hook_labels(self) -> tuple[str, ...]:
        """Every subscription, matched ones spelled ``Event(matcher)``."""
        return (
            *self.events,
            *(hook_label(event, matcher) for event, matcher in self.matched_events),
        )


@dataclass(frozen=True, slots=True)
class ConfigurationDirectory:
    """Where a harness reads its user-wide configuration, and what chose it."""

    path: Path
    # The harness's own variable that named the directory, such as
    # ``CODEX_HOME``; ``None`` when the harness's default is in use.
    variable: str | None = None

    @override
    def __str__(self) -> str:
        if self.variable is None:
            return str(self.path)
        return f"{self.path} (from {self.variable})"


def configuration_directory(
    spec: HarnessIntegration, environ: Mapping[str, str] | None = None
) -> ConfigurationDirectory:
    """Resolve a harness's configuration directory as the harness itself does.

    Claude Code reads ``$CLAUDE_CONFIG_DIR`` and Codex ``$CODEX_HOME`` in
    place of their directories in the home directory, and OpenCode its
    directory under ``$XDG_CONFIG_HOME``; a variable set but empty is read
    as unset (ADR 0130).
    """
    environment = os.environ if environ is None else environ
    if spec.home_variable is not None:
        configured = environment.get(spec.home_variable)
        if configured:
            return ConfigurationDirectory(Path(configured), spec.home_variable)
    if spec.xdg_configuration:
        configured = environment.get("XDG_CONFIG_HOME")
        base = Path(configured) if configured else Path.home() / ".config"
        return ConfigurationDirectory(base / spec.home_name)
    return ConfigurationDirectory(Path.home() / spec.home_name)


def configuration_in_use(
    spec: HarnessIntegration, home: Path | None
) -> ConfigurationDirectory:
    """The configuration directory a command works in: the one named, else the harness's."""
    return (
        configuration_directory(spec) if home is None else ConfigurationDirectory(home)
    )


def hook_label(event: str, matcher: str | None) -> str:
    return f"{event}({matcher})" if matcher else event


_CODEX = HarnessIntegration(
    harness="codex",
    display=HARNESS_DISPLAY["codex"],
    home_name=".codex",
    hooks_file="hooks.json",
    command_name="dashpot-codex-hook",
    # Codex reads user skills from the shared ``~/.agents``, wherever
    # ``CODEX_HOME`` puts its own directory.
    skills_home=Path(".agents/skills"),
    # A delegated thread's boundaries keep its parent's live set, as Claude
    # Code's do, so a Codex sub-agent blocks Cleanup too (ADR 0066, ADR 0067).
    events=(
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "Interrupt",
        "SubagentStart",
        "SubagentStop",
        "SessionEnd",
    ),
    checks_config_toml=True,
    home_variable="CODEX_HOME",
)

_CLAUDE_CODE = HarnessIntegration(
    harness="claude-code",
    display=HARNESS_DISPLAY["claude-code"],
    home_name=".claude",
    hooks_file="settings.json",
    command_name="dashpot-claude-code-hook",
    skills_home=Path("skills"),
    # A sub-agent's boundaries keep the session running while it works after
    # the main turn has stopped (ADR 0016).
    events=(
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "SubagentStart",
        "SubagentStop",
        "SessionEnd",
    ),
    checks_config_toml=False,
    # ``EnterWorktree`` moves a running session to another Worktree, and
    # ``ExitWorktree`` moves it back, without firing any lifecycle event, so
    # each completion is observed on its own: one invocation per relocation,
    # not per tool call (ADR 0009).
    matched_events=(
        ("PostToolUse", "EnterWorktree"),
        ("PostToolUse", "ExitWorktree"),
    ),
    home_variable="CLAUDE_CONFIG_DIR",
    skills_in_configuration=True,
)

# OpenCode loads every ``plugins/*.js`` in its global configuration directory,
# so its integration is one managed plugin, which runs the publisher as a
# bounded helper; its events are the plugin's to choose (ADR 0079).
_OPENCODE = HarnessIntegration(
    harness="opencode",
    display=HARNESS_DISPLAY["opencode"],
    home_name="opencode",
    hooks_file="plugins/dashpot.js",
    command_name="dashpot-opencode-hook",
    skills_home=Path("skills"),
    events=(),
    checks_config_toml=False,
    installer="plugin",
    xdg_configuration=True,
    agents_home=Path("agent"),
    skills_in_configuration=True,
)

INTEGRATIONS: dict[Harness, HarnessIntegration] = {
    spec.harness: spec for spec in (_CODEX, _CLAUDE_CODE, _OPENCODE)
}

HOOK_COMMAND_NAMES = frozenset(spec.command_name for spec in INTEGRATIONS.values())


def integration(harness: Harness) -> HarnessIntegration:
    """The integration of a supported harness."""
    spec = INTEGRATIONS.get(harness)
    if spec is None:
        raise HarnessError(f"unsupported harness: {harness}")
    return spec


def resolve_hook_command(spec: HarnessIntegration) -> Path:
    """Locate this environment's installed hook publisher."""
    scripts = Path(sysconfig.get_path("scripts")) / spec.command_name
    if scripts.is_file():
        return scripts
    found = shutil.which(spec.command_name)
    if found:
        return Path(found)
    raise IntegrationError(
        f"cannot locate the {spec.command_name} publisher installed with "
        "Dashpot; reinstall Dashpot and retry"
    )
