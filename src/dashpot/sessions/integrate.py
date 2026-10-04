"""Install, check, and describe one harness's lifecycle hook integration."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sysconfig
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from ..core.errors import DashpotError
from ..core.git import GitError
from ..core.model import HARNESS_DISPLAY, Harness
from ..core.pydantic import (
    PersistedRecord,
    PublishedModel,
    RepositoryRelativePath,
    describe_validation_error,
)
from ..core.record_store import replace_atomically
from ..core.state_paths import is_configured_checkout
from ..core.worktree_paths import (
    main_worktree,
    same_path,
    worktree_records,
    worktree_root,
)
from .harnesses import (
    OPENCODE_ACCEPTED_VERSION,
    SESSION_OVERRIDE_VARIABLE,
    HarnessError,
    OpenCodeHostMode,
    adapter,
    is_opencode_host_process,
    opencode_host_mode,
    opencode_shell_refusal,
    override_claim,
)
from .hook_claims import SessionClaimError, validate_session_claim
from .hook_records import session_directory, state_directory
from .hook_scan import (
    SessionRecordSummary,
    StaleSessionRecord,
    summarize_session_records,
)
from .processes import (
    ProcessAbsent,
    ProcessLookup,
    ProcessPresent,
    ProcessUnobservable,
    host_process_lookup,
)
from .session_exits import named_subagents

HOOK_TIMEOUT = 3
# Inline hook definitions live under ``[hooks]`` or ``[[hooks.<Event>]]``.
# Codex also keeps its hook trust ledger under ``[hooks.state...]``, which is
# not a definition and must not trigger the coexistence note.
CONFIG_HOOKS_TABLE = re.compile(r"^\s*\[+\s*hooks\s*(?:\]|\.(?!state\b))", re.MULTILINE)
# The Dashpot release the bundled skills and agents are written for, kept
# aligned with the package version (docs/releasing.md).
BUNDLED_SKILL_VERSION = "0.1.0"
BUNDLED_SKILLS_ROOT = Path(__file__).parents[1] / "skills"
BUNDLED_AGENTS_ROOT = Path(__file__).parents[1] / "agents"
# Written beside the marker in every managed skill copy, it names each file
# Dashpot wrote there, so a later Dashpot can tell a file an earlier one
# shipped from one the user added (ADR 0103).
SKILL_MANIFEST = Path(".dashpot-manifest.json")
# The file that carries a skill, and in a managed copy its marker.
SKILL_FILE = Path("SKILL.md")


class IntegrationError(DashpotError):
    """A hook or skill installation refused with the file left as it was."""


class IncompleteIntegrationError(IntegrationError):
    """An installation that wrote every destination it could, past those it could not.

    Its message names each destination that failed; ``messages`` reports
    what the installation did, as a complete one's return value would
    (ADR 0110).
    """

    def __init__(
        self, harness: Harness, failures: Sequence[str], messages: Sequence[str]
    ) -> None:
        super().__init__(
            f"{'; '.join(failures)}; the rest of the integration is written, and "
            f"rerunning 'dashpot integrate {harness}' finishes it"
        )
        self.messages = tuple(messages)


@dataclass(frozen=True, slots=True)
class _PendingWrite:
    """One destination ``integrate`` changes, checked before any is written."""

    # What a refusal names, such as "the Dashpot Issue work skill at <path>".
    subject: str
    # Every directory the write creates, replaces or removes a file in.
    directories: tuple[Path, ...]
    # Write the destination and report it; raises ``IntegrationError``.
    perform: Callable[[], str]

    def refusal(self) -> str | None:
        """Why this write cannot be made; ``None`` when every directory allows it."""
        for directory in self.directories:
            reason = _unwritable(directory)
            if reason is not None:
                return f"cannot install {self.subject}: {reason}"
        return None


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


class SkillManifest(PersistedRecord):
    """The files Dashpot wrote into one managed skill copy, relative to it."""

    # A copy's files obey the Repository-relative rule: a POSIX path that
    # stays inside the directory it is relative to, here the copy itself.
    files: tuple[RepositoryRelativePath, ...]


# What a skill's destination holds, judged by its marker before any listing.
CopyState = Literal["vacant", "managed", "unmanaged", "not a directory"]


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


@dataclass(frozen=True, slots=True)
class HarnessIntegration:
    """One supported harness's opt-in lifecycle hook installation."""

    harness: Harness
    display: str
    home_name: str
    hooks_file: str
    command_name: str
    skills_home: Path
    events: tuple[str, ...]
    checks_config_toml: bool
    # Events subscribed for one tool alone, as ``(event, matcher)``: the
    # publisher runs once per matching tool call rather than per event.
    matched_events: tuple[tuple[str, str], ...] = ()
    # A harness configured under ``$XDG_CONFIG_HOME`` rather than the home
    # directory, whose skills live inside its configuration directory, and
    # which loads a managed plugin at ``hooks_file`` instead of reading hook
    # definitions from it: OpenCode (ADR 0079).
    plugin: bool = False
    # Where, inside its configuration directory, the harness reads the agent
    # definitions Dashpot bundles; ``None`` for a harness that installs none.
    agents_home: Path | None = None

    @property
    def default_home(self) -> Path:
        if self.plugin:
            configured = os.environ.get("XDG_CONFIG_HOME")
            base = Path(configured) if configured else Path.home() / ".config"
            return base / self.home_name
        return Path.home() / self.home_name

    @property
    def default_skills_home(self) -> Path:
        if self.plugin:
            return self.default_home / self.skills_home
        return Path.home() / self.skills_home

    @property
    def hook_labels(self) -> tuple[str, ...]:
        """Every subscription, matched ones spelled ``Event(matcher)``."""
        return (
            *self.events,
            *(hook_label(event, matcher) for event, matcher in self.matched_events),
        )


def hook_label(event: str, matcher: str | None) -> str:
    return f"{event}({matcher})" if matcher else event


CODEX = HarnessIntegration(
    harness="codex",
    display=HARNESS_DISPLAY["codex"],
    home_name=".codex",
    hooks_file="hooks.json",
    command_name="dashpot-codex-hook",
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
)

CLAUDE_CODE = HarnessIntegration(
    harness="claude-code",
    display=HARNESS_DISPLAY["claude-code"],
    home_name=".claude",
    hooks_file="settings.json",
    command_name="dashpot-claude-code-hook",
    skills_home=Path(".claude/skills"),
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
)

# OpenCode loads every ``plugins/*.js`` in its global configuration directory,
# so its integration is one managed plugin, which runs the publisher as a
# bounded helper; its events are the plugin's to choose (ADR 0079).
OPENCODE = HarnessIntegration(
    harness="opencode",
    display=HARNESS_DISPLAY["opencode"],
    home_name="opencode",
    hooks_file="plugins/dashpot.js",
    command_name="dashpot-opencode-hook",
    skills_home=Path("skills"),
    events=(),
    checks_config_toml=False,
    plugin=True,
    agents_home=Path("agent"),
)

INTEGRATIONS: dict[Harness, HarnessIntegration] = {
    spec.harness: spec for spec in (CODEX, CLAUDE_CODE, OPENCODE)
}

HOOK_COMMAND_NAMES = frozenset(spec.command_name for spec in INTEGRATIONS.values())

CODEX_HOOK_EVENTS = CODEX.events
CLAUDE_CODE_HOOK_EVENTS = CLAUDE_CODE.events


def integration(harness: Harness) -> HarnessIntegration:
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


@dataclass(frozen=True, slots=True)
class LinkedWorktreeBinding:
    """A hook publisher that a linked Worktree's lifetime would take away."""

    worktree: Path
    # None when the Repository is bare: every checkout is then a linked
    # Worktree and there is no main working tree to run the command from.
    main_worktree: Path | None


def linked_worktree_binding(command: Path) -> LinkedWorktreeBinding | None:
    """Name the linked Worktree holding a hook publisher, if one does.

    A publisher inside a linked Worktree — its ``.venv`` — is removed with
    that Worktree when its Issue is finished, and every hook event fails
    from then on. One in the main working tree, or outside any Git working
    tree such as a tool installation, has no such lifetime.
    """
    # When Git cannot answer — no Repository holds the publisher, or Git
    # itself is unavailable — the binding is not refused: the refusal names
    # the one lifetime it can see, and ordinary installation does not wait
    # on Git to prove a negative.
    try:
        root = worktree_root(command.parent)
        records = worktree_records(root)
    except GitError:
        return None
    main = main_worktree(records)
    if root == main:
        return None
    return LinkedWorktreeBinding(
        worktree=root, main_worktree=None if "bare" in records[0] else main
    )


def _linked_worktree_consequence(
    spec: HarnessIntegration, binding: LinkedWorktreeBinding
) -> str:
    rerun = f"run 'dashpot integrate {spec.harness}' from "
    if binding.main_worktree is not None:
        rerun += f"the main working tree {binding.main_worktree} or from "
    return (
        f"that publisher lives in the linked Worktree {binding.worktree}, which "
        "is removed when its Issue is finished, and every hook event would fail "
        f"from then on; {rerun}an installed tool environment"
    )


def install_integration(
    harness: Harness,
    home: Path | None = None,
    *,
    command_path: Path | None = None,
    version_probe: Callable[[], str | None] | None = None,
    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS,
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS,
) -> list[str]:
    """Idempotently register one harness's lifecycle hooks, bundled skills and agents.

    OpenCode's plugin is refused while the ``opencode`` on PATH, which
    ``version_probe`` asks by default, is a v1 release (ADR 0090). OpenCode
    also gets the bundled agent definitions (ADR 0093). Every destination is
    checked before anything is written: a directory of a bundled skill's
    name, or a file of a bundled agent's, that Dashpot does not manage, and
    a destination that needs writing where Dashpot cannot write, refuse the
    whole installation. A write that fails once the checks have passed does
    not stop the others, and raises ``IncompleteIntegrationError`` naming
    every failure once they are done (ADR 0110).
    """
    spec = integration(harness)
    home = home or spec.default_home
    if not home.is_dir():
        raise IntegrationError(
            f"no {spec.display} configuration directory at {home}; install "
            f"and run {spec.display} once before integrating"
        )
    destinations = _skill_copies(spec, home, skills)
    agent_destinations = _agent_copies(spec, home, agents)
    _validate_destinations(destinations, agent_destinations)
    command = command_path or resolve_hook_command(spec)
    # Refuse before anything is loaded or written: the binding would outlive
    # the environment it names, so the file is left exactly as it was.
    binding = linked_worktree_binding(command)
    if binding is not None:
        raise IntegrationError(
            f"cannot bind the {spec.display} hooks to {command}: "
            f"{_linked_worktree_consequence(spec, binding)}"
        )
    planned: list[str | _PendingWrite]
    if spec.plugin:
        reported = (version_probe or _opencode_version)()
        release = None if reported is None else opencode_release(reported)
        if release is not None and _major(release) == 1:
            raise IntegrationError(
                f"the opencode on PATH is OpenCode {release}, and Dashpot observes "
                f"OpenCode v2 only; install OpenCode {OPENCODE_ACCEPTED_VERSION} "
                "and retry"
            )
        planned = [
            *_opencode_release_status("OpenCode release on PATH", reported),
            _plan_plugin(spec, home, command),
            f"hook publisher: {command}",
            *(_plan_skill(skill, target) for skill, target in destinations),
            *(_plan_agent(agent, target) for agent, target in agent_destinations),
            *_opencode_skill_copies(destinations),
        ]
    else:
        planned = [
            _plan_hooks(spec, home, command),
            f"hook publisher: {command}",
            *(_plan_skill(skill, target) for skill, target in destinations),
            *_config_toml_coexistence_warning(spec, home),
        ]
    return _write_planned(harness, planned)


def _plan_hooks(
    spec: HarnessIntegration, home: Path, command: Path
) -> str | _PendingWrite:
    """The hooks file with Dashpot's handlers bound to ``command``, unless it already is."""
    path = home / spec.hooks_file
    document = _load_hooks_document(spec, path)
    original = json.dumps(document, sort_keys=True)
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise IntegrationError(
            f'{path} has a non-object top-level "hooks" value; fix the file and retry'
        )
    handler = {
        "type": "command",
        "command": shlex.quote(str(command)),
        "timeout": HOOK_TIMEOUT,
    }
    # One event may carry several subscriptions (a matcher per relocation
    # tool), so its existing Dashpot handlers are cleared once and every
    # group re-added, rather than each subscription clearing the last.
    matchers_by_event: dict[str, list[str | None]] = {}
    for event in spec.events:
        matchers_by_event.setdefault(event, []).append(None)
    for event, matcher in spec.matched_events:
        matchers_by_event.setdefault(event, []).append(matcher)
    for event, matchers in matchers_by_event.items():
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
        kept, _ours = _split_dashpot_handlers(groups)
        for matcher in matchers:
            group: dict[str, Any] = {"hooks": [dict(handler)]}
            if matcher is not None:
                group = {"matcher": matcher, **group}
            kept.append(group)
        hooks[event] = kept
    if json.dumps(document, sort_keys=True) == original:
        return f"{spec.display} lifecycle hooks already installed in {path}"

    def write() -> str:
        try:
            _write_json(path, document)
        except OSError as exc:
            raise IntegrationError(
                f"could not install the {spec.display} lifecycle hooks in {path}: {exc}"
            ) from exc
        return f"installed {spec.display} lifecycle hooks in {path}"

    return _PendingWrite(
        subject=f"the {spec.display} lifecycle hooks in {path}",
        directories=(path.parent,),
        perform=write,
    )


def _write_planned(
    harness: Harness, planned: Sequence[str | _PendingWrite]
) -> list[str]:
    """Check every pending write, then make each, carrying on past one that fails.

    Nothing is written while any destination is refused, so a destination
    Dashpot cannot write leaves the installation as it was. A check can pass
    and its write still fail, as when the destination changes in between or
    a filesystem refuses only the write; the others are written regardless,
    and every failure is named together once they are (ADR 0110).
    """
    refusals = [
        refusal
        for item in planned
        if isinstance(item, _PendingWrite) and (refusal := item.refusal()) is not None
    ]
    if refusals:
        raise IntegrationError("; ".join(refusals))
    messages: list[str] = []
    failures: list[str] = []
    for item in planned:
        if isinstance(item, str):
            messages.append(item)
            continue
        try:
            messages.append(item.perform())
        except IntegrationError as exc:
            failures.append(str(exc))
    if failures:
        raise IncompleteIntegrationError(harness, failures, messages)
    return messages


def _unwritable(directory: Path) -> str | None:
    """Why a file cannot be written in ``directory``, or ``None`` when it can be.

    A directory not there yet is created inside its nearest existing
    ancestor, so that ancestor is the one checked. The check reads
    permissions alone: a write it passes may still fail.
    """
    for candidate in (directory, *directory.parents):
        try:
            mode = _file_mode(candidate)
        except OSError as exc:
            return f"could not inspect {candidate}: {exc}; fix it and retry"
        if mode is None:
            continue
        if not stat.S_ISDIR(mode):
            return f"{candidate} is not a directory; move it and retry"
        if not os.access(candidate, os.W_OK | os.X_OK):
            return f"{candidate} is not writable; make it writable and retry"
        return None
    return None  # pragma: no cover - the filesystem root always exists.


def remove_integration(
    harness: Harness,
    home: Path | None = None,
    *,
    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS,
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS,
) -> list[str]:
    """Remove exactly Dashpot's hooks, managed skills and agents for one harness."""
    spec = integration(harness)
    home = home or spec.default_home
    path = home / spec.hooks_file
    messages: list[str] = []
    if spec.plugin:
        messages.append(remove_plugin(spec, home))
    elif not path.is_file():
        messages.append(f"{spec.display} integration is not installed: no {path}")
    else:
        document = _load_hooks_document(spec, path)
        hooks = document.get("hooks")
        if not isinstance(hooks, dict):
            messages.append(
                f"{spec.display} integration is not installed: no hooks in {path}"
            )
        else:
            removed = False
            for event in list(hooks):
                groups = hooks[event]
                if not isinstance(groups, list):
                    continue
                kept, ours = _split_dashpot_handlers(groups)
                if ours:
                    removed = True
                if kept:
                    hooks[event] = kept
                else:
                    del hooks[event]
            if not removed:
                messages.append(
                    f"{spec.display} integration is not installed: no Dashpot "
                    f"hooks in {path}"
                )
            elif hooks or set(document) - {"description", "hooks"}:
                if not hooks:
                    del document["hooks"]
                _write_json(path, document)
                messages.append(f"removed the Dashpot hooks from {path}")
            else:
                path.unlink()
                messages.append(f"removed {path}; it contained only the Dashpot hooks")
    messages.extend(
        _remove_skill(skill, target)
        for skill, target in _skill_copies(spec, home, skills)
    )
    messages.extend(
        _remove_agent(agent, target)
        for agent, target in _agent_copies(spec, home, agents)
    )
    return messages


def integration_status(
    harness: Harness,
    home: Path | None = None,
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
    version_probe: Callable[[], str | None] | None = None,
    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS,
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS,
) -> list[str]:
    """Report the observable state of one harness's integration."""
    spec = integration(harness)
    home = home or spec.default_home
    path = home / spec.hooks_file
    messages: list[str] = []
    if not home.is_dir():
        messages.append(f"{spec.display} configuration directory not found: {home}")
    elif spec.plugin:
        messages.extend(plugin_status(spec, home))
    elif not path.is_file():
        messages.append(f"not installed: no {path}")
    else:
        try:
            document = _load_hooks_document(spec, path)
        except IntegrationError as exc:
            return [str(exc)]
        commands = _installed_commands(document)
        if not commands:
            messages.append(f"not installed: no Dashpot hooks in {path}")
        else:
            events = sorted(commands)
            missing = [label for label in spec.hook_labels if label not in commands]
            messages.append(f"installed in {path} for: {', '.join(events)}")
            if missing:
                messages.append(
                    f"missing hook events (run 'dashpot integrate "
                    f"{spec.harness}' to repair): {', '.join(missing)}"
                )
            for command in sorted({c for cs in commands.values() for c in cs}):
                executable = _hook_executable(command)
                if not executable.is_file():
                    messages.append(
                        f"hook publisher missing at {command}; run "
                        f"'dashpot integrate {spec.harness}' to repair"
                    )
                elif not os.access(executable, os.X_OK):
                    messages.append(f"hook publisher at {command} is not executable")
                else:
                    messages.append(f"hook publisher: {command}")
                    # While the file still exists the binding only looks
                    # healthy; say now what removing its Worktree will do.
                    binding = linked_worktree_binding(executable)
                    if binding is not None:
                        messages.append(
                            f"warning: {_linked_worktree_consequence(spec, binding)}"
                        )
    destinations = _skill_copies(spec, home, skills)
    messages.extend(
        _skill_status(skill, target, harness=spec.harness)
        for skill, target in destinations
    )
    messages.extend(
        _agent_status(agent, target, harness=spec.harness)
        for agent, target in _agent_copies(spec, home, agents)
    )
    messages.extend(_config_toml_coexistence_warning(spec, home))
    if spec.plugin:
        messages.extend(_opencode_skill_copies(destinations))
        messages.extend(_opencode_plugin_copies(path, current, environ))
        messages.extend(_opencode_runtime_status(version_probe, environ, lookup))
    messages.extend(_record_store_status(state_dir, current, lookup))
    messages.extend(_claimed_identity_status(spec, current, lookup, environ))
    return messages


def install_codex_integration(
    codex_home: Path | None = None,
    *,
    command_path: Path | None = None,
) -> list[str]:
    return install_integration("codex", codex_home, command_path=command_path)


def remove_codex_integration(codex_home: Path | None = None) -> list[str]:
    return remove_integration("codex", codex_home)


def codex_integration_status(
    codex_home: Path | None = None,
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    return integration_status(
        "codex",
        codex_home,
        state_dir=state_dir,
        current=current,
        lookup=lookup,
        environ=environ,
    )


def skill_directory(spec: HarnessIntegration, home: Path, skill: BundledSkill) -> Path:
    """Locate this harness's user-wide copy of one bundled skill."""
    if spec.plugin:
        return home / spec.skills_home / skill.name
    if home == spec.default_home:
        return spec.default_skills_home / skill.name
    return home.parent / spec.skills_home / skill.name


def _skill_copies(
    spec: HarnessIntegration, home: Path, skills: tuple[BundledSkill, ...]
) -> list[tuple[BundledSkill, Path]]:
    """Each bundled skill, paired with where this harness keeps its copy."""
    return [(skill, skill_directory(spec, home, skill)) for skill in skills]


def _skill_text(destination: Path) -> str:
    """An installed copy's ``SKILL.md``; raises ``OSError`` or ``ValueError``."""
    return (destination / SKILL_FILE).read_text(encoding="utf-8")


def _is_managed(skill: BundledSkill, destination: Path) -> bool:
    """Whether a copy's ``SKILL.md`` is readable and carries this skill's marker."""
    try:
        return _copy_state(skill, destination) == "managed"
    except (OSError, ValueError):
        return False


def _file_mode(path: Path) -> int | None:
    """A path's mode, or ``None`` when nothing is there; raises any other ``OSError``.

    Only absence is absence: ``Path.exists`` reads a path it may not search
    as absent on some Python releases, which would report a copy it cannot
    inspect as missing.
    """
    try:
        return path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None


def _copy_state(skill: BundledSkill, destination: Path) -> CopyState:
    """What holds a bundled skill's destination.

    ``SKILL.md`` is read before the directory is listed, so a copy that can
    be entered but not listed is still recognised by its marker; only a
    directory without one is listed, to tell an empty directory from
    someone else's. Raises ``OSError`` when the destination cannot be
    inspected, and ``ValueError`` when its ``SKILL.md`` is not text.
    """
    mode = _file_mode(destination)
    if mode is None:
        return "vacant"
    if not stat.S_ISDIR(mode):
        return "not a directory"
    skill_mode = _file_mode(destination / SKILL_FILE)
    if skill_mode is not None and stat.S_ISREG(skill_mode):
        return "managed" if skill.marker in _skill_text(destination) else "unmanaged"
    return "unmanaged" if any(destination.iterdir()) else "vacant"


def _recorded_files(destination: Path) -> frozenset[Path] | None:
    """The files a copy's manifest names, or ``None`` when it has no valid one."""
    try:
        manifest = SkillManifest.model_validate_json(
            (destination / SKILL_MANIFEST).read_bytes()
        )
    except (OSError, ValidationError):
        return None
    return frozenset(Path(relative) for relative in manifest.files)


def _written_files(skill: BundledSkill, destination: Path) -> frozenset[Path]:
    """Every file Dashpot wrote into a managed copy.

    A copy without a valid manifest was written by a revision from before
    Dashpot kept one, and every file those revisions shipped is still
    shipped, so the files this Dashpot ships stand in for its list
    (ADR 0103).
    """
    recorded = _recorded_files(destination)
    return frozenset(skill.files) if recorded is None else recorded


def _is_current(skill: BundledSkill, destination: Path) -> bool:
    """Whether a copy holds every file this Dashpot ships, unchanged, and no other of Dashpot's.

    Its manifest must name exactly the shipped files: a file it names beyond
    them is one an earlier Dashpot shipped and an update removes. Files the
    user added are not Dashpot's, and leave the copy current.
    """
    try:
        return _recorded_files(destination) == frozenset(skill.files) and all(
            (destination / relative).is_file()
            and (destination / relative).read_bytes()
            == (skill.source / relative).read_bytes()
            for relative in skill.files
        )
    except OSError:
        return False


def _validate_destinations(
    destinations: list[tuple[BundledSkill, Path]],
    agent_destinations: list[tuple[BundledAgent, Path]],
) -> None:
    """Refuse when any skill or agent destination holds what Dashpot does not manage.

    An empty or absent skill directory is free to install into; any other
    directory must already carry that skill's own marker, and one that
    cannot be inspected is refused. An absent agent file is free to install
    into; anything else at its path must be a file carrying that agent's
    own marker.
    """
    refusals: list[str] = []
    for skill, destination in destinations:
        refused = f"cannot install the Dashpot {skill.label} at {destination}: "
        try:
            state = _copy_state(skill, destination)
        except OSError as exc:
            refusals.append(f"{refused}could not inspect it: {exc}; move it and retry")
            continue
        except ValueError:
            state = "unmanaged"
        if state == "not a directory":
            refusals.append(f"{refused}the path is not a directory; move it and retry")
        elif state == "unmanaged":
            refusals.append(
                f"{refused}an existing skill is not managed by Dashpot; "
                "move it and retry"
            )
    for agent, destination in agent_destinations:
        if not os.path.lexists(destination):
            continue
        if not destination.is_file():
            refusals.append(
                f"cannot install the Dashpot {agent.label} at {destination}: "
                "the path is not a file; move it and retry"
            )
        elif not _is_managed_agent(agent, destination):
            refusals.append(
                f"cannot install the Dashpot {agent.label} at {destination}: "
                "an existing agent is not managed by Dashpot; move it and retry"
            )
    if refusals:
        raise IntegrationError("; ".join(refusals))


def _write_manifest(destination: Path, files: frozenset[Path]) -> None:
    """Record which files Dashpot wrote into a managed copy.

    The manifest is rewritten whole: anything a newer Dashpot recorded in it
    described the copy this one has just rewritten.
    """
    manifest = SkillManifest(files=tuple(path.as_posix() for path in sorted(files)))
    replace_atomically(
        destination / SKILL_MANIFEST,
        manifest.model_dump_json(by_alias=True, indent=2) + "\n",
        temporary_prefix=f".{SKILL_MANIFEST.name}.",
    )


def _remove_files(destination: Path, files: Sequence[Path]) -> None:
    """Unlink each named file of a copy, in order, then the directories they emptied.

    Only the directories holding a named file are pruned, deepest first, and
    only once empty: anything else in them is the user's. A name whose
    directory resolves outside the copy, through a symbolic link the user
    put there, is never followed.
    """
    root = destination.resolve()
    for relative in files:
        path = destination / relative
        if _resolves_inside(path, root) and path.is_file():
            path.unlink()
    nested = {
        ancestor
        for relative in files
        for ancestor in relative.parents
        if ancestor != Path(".")
    }
    for relative in sorted(nested, key=lambda path: len(path.parts), reverse=True):
        # Removing rather than listing first keeps a directory that cannot be
        # listed prunable; one still holding the user's files refuses.
        directory = destination / relative
        if _resolves_inside(directory, root):
            with contextlib.suppress(OSError):
                directory.rmdir()


def _plan_skill(skill: BundledSkill, destination: Path) -> str | _PendingWrite:
    """The shipped files of one skill, written into its copy unless it is current."""
    if _is_current(skill, destination):
        return f"Dashpot {skill.label} already installed in {destination}"
    # An empty directory, as a first installation cut short leaves, is
    # installed into, not updated.
    existed = _is_managed(skill, destination)

    def write() -> str:
        try:
            _write_skill(skill, destination, managed=existed)
        except OSError as exc:
            action = "update" if existed else "install"
            raise IntegrationError(
                f"could not {action} the Dashpot {skill.label} in {destination}: {exc}"
            ) from exc
        verb = "updated" if existed else "installed"
        return f"{verb} Dashpot {skill.label} in {destination}"

    return _PendingWrite(
        subject=f"the Dashpot {skill.label} at {destination}",
        directories=_skill_write_directories(skill, destination, managed=existed),
        perform=write,
    )


def _skill_write_directories(
    skill: BundledSkill, destination: Path, *, managed: bool
) -> tuple[Path, ...]:
    """Every directory an update of a copy writes a file in or removes one from.

    The copy itself holds its manifest. A file an earlier Dashpot wrote that
    this one no longer ships is removed only where its directory resolves
    inside the copy, so only there is its directory checked.
    """
    shipped = frozenset(skill.files)
    directories = {destination, *((destination / path).parent for path in shipped)}
    if managed:
        root = destination.resolve()
        for relative in _written_files(skill, destination) - shipped:
            if _resolves_inside(destination / relative, root):
                directories.add((destination / relative).parent)
    return tuple(sorted(directories))


def _resolves_inside(path: Path, root: Path) -> bool:
    """Whether the directory holding ``path`` resolves inside the resolved ``root``."""
    # A link loop is never followed: Python 3.12 raises ``RuntimeError``
    # for one where later releases leave the path unresolved.
    try:
        return path.parent.resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _write_skill(skill: BundledSkill, destination: Path, *, managed: bool) -> None:
    """Leave a managed copy holding exactly the shipped files, beside the user's own.

    ``SKILL.md`` is written first, so a first installation cut short before
    it leaves a directory free to install into again. An update cut short
    leaves every file Dashpot wrote named by the manifest, for the next
    update or ``--remove`` to finish.
    """
    shipped = frozenset(skill.files)
    recorded = _recorded_files(destination) if managed else None
    earlier = frozenset[Path]()
    if managed:
        earlier = shipped if recorded is None else recorded
    destination.mkdir(parents=True, exist_ok=True)
    # Without a manifest the shipped files already stand in for one, so only
    # a manifest that names fewer files than will be written is widened first.
    if recorded is not None and recorded != earlier | shipped:
        _write_manifest(destination, earlier | shipped)
    for relative in sorted(skill.files, key=lambda path: path != SKILL_FILE):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(
            target,
            (skill.source / relative).read_text(encoding="utf-8"),
            temporary_prefix=f".{target.name}.",
        )
    _remove_files(destination, sorted(earlier - shipped))
    _write_manifest(destination, shipped)


def _remove_skill(skill: BundledSkill, destination: Path) -> str:
    try:
        state = _copy_state(skill, destination)
    except (OSError, ValueError) as exc:
        return f"could not inspect Dashpot {skill.label} at {destination}: {exc}"
    if state == "vacant":
        return f"Dashpot {skill.label} is not installed: no {destination / SKILL_FILE}"
    if state != "managed":
        return f"left unmanaged {skill.label} unchanged at {destination}"
    # SKILL.md, which carries the marker, goes last, after the manifest, so
    # a removal cut short leaves a copy the next ``--remove`` still
    # recognises and finishes.
    written = sorted(_written_files(skill, destination) - {SKILL_FILE, SKILL_MANIFEST})
    try:
        _remove_files(destination, [*written, SKILL_MANIFEST, SKILL_FILE])
    except OSError as exc:
        return f"could not remove Dashpot {skill.label} from {destination}: {exc}"
    # The copy stays while it still holds the user's files.
    with contextlib.suppress(OSError):
        destination.rmdir()
    return f"removed the Dashpot {skill.label} from {destination}"


def _skill_status(skill: BundledSkill, destination: Path, *, harness: Harness) -> str:
    try:
        state = _copy_state(skill, destination)
    except (OSError, ValueError) as exc:
        return f"{skill.label} unreadable at {destination}: {exc}"
    if state == "vacant":
        return f"{skill.label} not installed: no {destination / SKILL_FILE}"
    if state != "managed":
        return f"{skill.label} conflict at {destination}: not managed by Dashpot"
    if not _is_current(skill, destination):
        return (
            f"{skill.label} update available at {destination}; run "
            f"'dashpot integrate {harness}' to repair"
        )
    return (
        f"{skill.label} installed in {destination} for Dashpot {BUNDLED_SKILL_VERSION}"
    )


def agent_file(
    spec: HarnessIntegration, home: Path, agent: BundledAgent
) -> Path | None:
    """Locate this harness's user-wide copy of one bundled agent, if it installs agents."""
    if spec.agents_home is None:
        return None
    return home / spec.agents_home / f"{agent.name}.md"


def _agent_copies(
    spec: HarnessIntegration, home: Path, agents: tuple[BundledAgent, ...]
) -> list[tuple[BundledAgent, Path]]:
    """Each bundled agent, paired with where this harness keeps its copy, if anywhere."""
    return [
        (agent, target)
        for agent in agents
        if (target := agent_file(spec, home, agent)) is not None
    ]


def _agent_text(destination: Path) -> str:
    """An installed agent file's text; raises ``OSError`` or ``ValueError``."""
    return destination.read_text(encoding="utf-8")


def _is_managed_agent(agent: BundledAgent, destination: Path) -> bool:
    """Whether an agent file is readable and carries this agent's marker."""
    try:
        return agent.marker in _agent_text(destination)
    except (OSError, ValueError):
        return False


def _is_current_agent(agent: BundledAgent, destination: Path) -> bool:
    """Whether an agent file is the one this Dashpot ships, unchanged."""
    return destination.is_file() and (
        destination.read_bytes() == agent.source.read_bytes()
    )


def _plan_agent(agent: BundledAgent, destination: Path) -> str | _PendingWrite:
    """The shipped agent definition, written to its file unless it is current."""
    if _is_current_agent(agent, destination):
        return f"Dashpot {agent.label} already installed in {destination}"
    existed = os.path.lexists(destination)

    def write() -> str:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # The temporary's name ends in random characters, not ``.md``,
            # so OpenCode never reads it as a definition while it is written.
            replace_atomically(
                destination,
                agent.source.read_text(encoding="utf-8"),
                temporary_prefix=f".{destination.name}.",
            )
        except OSError as exc:
            action = "update" if existed else "install"
            raise IntegrationError(
                f"could not {action} the Dashpot {agent.label} in {destination}: {exc}"
            ) from exc
        verb = "updated" if existed else "installed"
        return f"{verb} Dashpot {agent.label} in {destination}"

    return _PendingWrite(
        subject=f"the Dashpot {agent.label} at {destination}",
        directories=(destination.parent,),
        perform=write,
    )


def _remove_agent(agent: BundledAgent, destination: Path) -> str:
    if not os.path.lexists(destination):
        return f"Dashpot {agent.label} is not installed: no {destination}"
    unmanaged = f"left unmanaged {agent.label} unchanged at {destination}"
    if not destination.is_file():
        return unmanaged
    try:
        text = _agent_text(destination)
    except (OSError, ValueError) as exc:
        return f"could not inspect Dashpot {agent.label} at {destination}: {exc}"
    if agent.marker not in text:
        return unmanaged
    destination.unlink()
    return f"removed the Dashpot {agent.label} from {destination}"


def _agent_status(agent: BundledAgent, destination: Path, *, harness: Harness) -> str:
    if not os.path.lexists(destination):
        return f"{agent.label} not installed: no {destination}"
    conflict = f"{agent.label} conflict at {destination}: not managed by Dashpot"
    if not destination.is_file():
        return conflict
    try:
        text = _agent_text(destination)
    except (OSError, ValueError) as exc:
        return f"{agent.label} unreadable at {destination}: {exc}"
    if agent.marker not in text:
        return conflict
    if not _is_current_agent(agent, destination):
        return (
            f"{agent.label} update available at {destination}; run "
            f"'dashpot integrate {harness}' to repair"
        )
    return (
        f"{agent.label} installed in {destination} for Dashpot {BUNDLED_SKILL_VERSION}"
    )


def _record_store_status(
    state_dir: Path | None, current: Path | None, lookup: ProcessLookup
) -> list[str]:
    """Report the session stores visible from here: Project-local and global.

    Each store's records are classified at this moment without being pruned;
    stale records name the session so undelivered SessionEnd hooks can be
    diagnosed here rather than on the workspace Diagnostics surface.
    """
    messages: list[str] = []
    try:
        root = worktree_root(current or Path.cwd())
    except GitError:
        root = None
    if root is not None and is_configured_checkout(root):
        local = session_directory(root)
        messages.extend(
            _describe_records(
                "for this Project", summarize_session_records(local, lookup)
            )
        )
    directory = state_dir or state_directory()
    if directory.is_dir():
        messages.extend(
            _describe_records(
                "outside configured Projects",
                summarize_session_records(directory, lookup),
            )
        )
    else:
        messages.append(
            f"session records outside configured Projects: none ({directory} "
            "does not exist yet)"
        )
    return messages


def _claimed_identity_status(
    spec: HarnessIntegration,
    current: Path | None,
    lookup: ProcessLookup,
    environ: Mapping[str, str] | None,
) -> list[str]:
    """Report the Agent Session Identity this command's environment claims.

    This is the identity a sandboxed ``dashpot work start`` would use, so
    whether it names a live hook record here is what to check when opt-in
    from a sandbox is refused.
    """
    environment = environ if environ is not None else os.environ
    try:
        claim = override_claim(environment)
    except HarnessError as exc:
        return [f"Agent Session identity claimed here: {exc}"]
    if claim is None or claim.harness != spec.harness:
        claim = adapter(spec.harness).claim_session_identity(environment)
    if claim is None and spec.plugin:
        refusal = opencode_shell_refusal(environment, in_opencode=False) or (
            "only a shell OpenCode ran for its agent, prepared by the plugin, "
            "carries one"
        )
        return [
            f"Agent Session identity claimed here: none for {spec.display} ({refusal})"
        ]
    if claim is None:
        return [
            f"Agent Session identity claimed here: none for {spec.display} "
            f"(Issue opt-in from a sandbox needs one; {SESSION_OVERRIDE_VARIABLE}"
            f"={spec.harness}:<session id> states it explicitly)"
        ]
    prefix = (
        f"Agent Session identity claimed here: {spec.display} session "
        f"{claim.session_id} (from {claim.source})"
    )
    try:
        root = worktree_root(current or Path.cwd())
    except GitError:
        return [f"{prefix}, not validated: not inside a Git worktree"]
    try:
        validated = validate_session_claim(claim, root, lookup)
    except SessionClaimError as exc:
        return [f"{prefix}, rejected: {exc}"]
    # The freshest record may sit in another Worktree of the Repository, as
    # after a move whose record at the destination could not be written, and
    # then the session is not here, whatever directory this command runs in.
    location = validated.location
    if location is not None and not same_path(location.worktree, root):
        return [
            f"{prefix}, elsewhere: its freshest hook record, "
            f"{validated.record.outcome}, places it at {location.worktree}, "
            f"not here"
        ]
    confirmed = f"{prefix}, confirmed by its {validated.record.outcome} hook record"
    # Validation refuses an OpenCode claim without the plugin's pid, so every
    # confirmed OpenCode claim names its server.
    if claim.harness != "opencode" or claim.pid is None:
        return [confirmed]
    return [confirmed, _opencode_host_mode_status(claim.pid, lookup)]


def _opencode_host_mode_status(pid: int, lookup: ProcessLookup) -> str:
    """Report how the OpenCode server a confirmed session's claim names serves it.

    The server is the process ``DASHPOT_OPENCODE_PID`` names. A session moves
    itself, and leads Workers, only when this reads ``shared-service``: both
    are measured on the shared service alone (ADR 0108).
    """
    observed = lookup(pid)
    mode: OpenCodeHostMode
    if isinstance(observed, ProcessUnobservable):
        mode, detail = "unknown", f"pid {pid} could not be observed ({observed.reason})"
    elif isinstance(observed, ProcessAbsent):
        mode, detail = "unknown", f"pid {pid} has exited"
    else:
        mode = opencode_host_mode(observed.identity)
        detail = {
            "shared-service": f"pid {pid}, the shared 'opencode serve --service'",
            "standalone": (
                f"pid {pid}, a --standalone client's private 'opencode serve --stdio'"
            ),
            "unknown": (
                f"pid {pid} is neither 'opencode serve --service' nor "
                "'opencode serve --stdio'"
            ),
        }[mode]
    line = f"OpenCode Host Process mode: {mode} ({detail})"
    if mode == "shared-service":
        return line
    return (
        f"{line}; this session moves itself and leads Workers only on the "
        "shared service"
    )


def _describe_records(scope: str, summary: SessionRecordSummary) -> list[str]:
    unknown = f"{summary.unknown} unknown"
    if summary.unknown_reasons:
        reasons = ", ".join(reason for reason, _count in summary.unknown_reasons)
        unknown += f" [{reasons}]"
    messages = [
        f"session records {scope}: {summary.total} in {summary.directory} "
        f"({summary.live} live, {unknown}, {len(summary.stale)} stale, "
        f"{summary.unreadable} unreadable)"
    ]
    messages.extend(f"  stale: {_describe_stale(record)}" for record in summary.stale)
    return messages


def _describe_stale(record: StaleSessionRecord) -> str:
    display = HARNESS_DISPLAY.get(record.harness, record.harness)
    text = (
        f"{display} session {record.session_id} last event "
        f"{record.event or 'unknown'} at {record.last_activity_at or 'unknown time'}, "
    )
    if record.retained_subagents:
        return text + (
            f"ended by SessionEnd, kept for its "
            f"{named_subagents(record.retained_subagents)} until they stop or "
            f"pid {record.pid} exits"
        )
    if record.outcome == "ended":
        return text + "ended by SessionEnd (legacy record; pruned on next observation)"
    process = f"pid {record.pid}" if record.pid is not None else "process"
    return text + f"{process} gone (no SessionEnd delivered)"


def _load_hooks_document(spec: HarnessIntegration, path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hooks": {}}
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrationError(
            f"cannot read {spec.display} hooks at {path}: {exc}; fix or "
            "move the file and retry"
        ) from exc
    if not isinstance(document, dict):
        raise IntegrationError(
            f"{path} must contain a JSON object; fix or move the file and retry"
        )
    return document


def _split_dashpot_handlers(
    groups: list[Any],
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Split one event's matcher groups from the Dashpot handlers inside them."""
    kept: list[Any] = []
    ours: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            kept.append(group)
            continue
        remaining = []
        for handler in group["hooks"]:
            if _is_dashpot_handler(handler):
                ours.append(handler)
            else:
                remaining.append(handler)
        # A group that held only Dashpot handlers matches nothing once they
        # are gone; its matcher is part of the subscription, not user state.
        if remaining or set(group) - {"hooks", "matcher"}:
            preserved = dict(group)
            preserved["hooks"] = remaining
            kept.append(preserved)
    return kept, ours


def _is_dashpot_handler(handler: object) -> bool:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    command = handler.get("command")
    if isinstance(command, list) and command:
        command = command[0]
    if not isinstance(command, str):
        return False
    # Older installers wrote paths without shell quoting; recognise those
    # whole so rerunning integration can repair their command lines.
    candidates = [command]
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    if words:
        candidates.append(words[0])
    return any(Path(candidate).name in HOOK_COMMAND_NAMES for candidate in candidates)


def _hook_executable(command: str) -> Path:
    """Locate the executable in a current or older installed hook command."""
    raw = Path(command)
    if raw.is_file():
        return raw
    try:
        words = shlex.split(command)
    except ValueError:
        return raw
    return Path(words[0]) if words else raw


def _installed_commands(document: dict[str, Any]) -> dict[str, list[str]]:
    """Map each subscription label to the Dashpot commands registered for it."""
    commands: dict[str, list[str]] = {}
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            _, ours = _split_dashpot_handlers([group])
            if not ours:
                continue
            matcher = group.get("matcher") if isinstance(group, dict) else None
            label = hook_label(event, matcher if isinstance(matcher, str) else None)
            commands.setdefault(label, []).extend(
                handler["command"]
                if isinstance(handler.get("command"), str)
                else handler["command"][0]
                for handler in ours
            )
    return commands


def _config_toml_coexistence_warning(spec: HarnessIntegration, home: Path) -> list[str]:
    if not spec.checks_config_toml:
        return []
    config = home / "config.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return []
    if CONFIG_HOOKS_TABLE.search(text):
        return [
            f"note: {config} also defines hooks; {spec.display} merges both "
            "layers and warns at startup"
        ]
    return []


def _write_json(path: Path, document: dict[str, Any]) -> None:
    replace_atomically(
        path, json.dumps(document, indent=2) + "\n", temporary_prefix=f".{path.name}."
    )


# ``opencode --version`` prints ``opencode v2.0.22`` from v2 and a bare
# ``1.18.30`` from v1; the service's registration names a bare release.
OPENCODE_RELEASE = re.compile(
    r"(?:opencode )?v?(?P<release>\d+\.\d+\.\d+\S*)", re.IGNORECASE
)
PLUGIN_MARKER = "// dashpot-managed-plugin: opencode"
PLUGIN_HELPER_PLACEHOLDER = '"__DASHPOT_OPENCODE_HELPER__"'
PLUGIN_HELPER = re.compile(r'^const HELPER = (".*");$', re.MULTILINE)
VERSION_TIMEOUT_SECONDS = 5


def _bundled_plugin() -> Path:
    return Path(__file__).parents[1] / "plugins" / "opencode.js"


def render_plugin(command: Path) -> str:
    """The managed plugin, bound to the helper at ``command``."""
    source = _bundled_plugin().read_text(encoding="utf-8")
    return source.replace(PLUGIN_HELPER_PLACEHOLDER, json.dumps(str(command)), 1)


def _managed_plugin(path: Path) -> str | None:
    """The managed plugin's text at ``path``; ``None`` when there is no file.

    A file that is not Dashpot's is refused rather than overwritten or
    removed: it is the user's plugin of the same name.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IntegrationError(
            f"cannot read the plugin at {path}: {exc}; move it and retry"
        ) from exc
    if not text.startswith(PLUGIN_MARKER):
        raise IntegrationError(
            f"{path} is not a plugin Dashpot manages; move it and retry"
        )
    return text


def _plan_plugin(
    spec: HarnessIntegration, home: Path, command: Path
) -> str | _PendingWrite:
    """The managed plugin bound to ``command``, written unless it already is."""
    path = home / spec.hooks_file
    current = _managed_plugin(path)
    rendered = render_plugin(command)
    if current == rendered:
        return f"{spec.display} plugin already installed in {path}"
    action = "install" if current is None else "update"

    def write() -> str:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            replace_atomically(path, rendered, temporary_prefix=f".{path.name}.")
        except OSError as exc:
            raise IntegrationError(
                f"could not {action} the {spec.display} plugin in {path}: {exc}"
            ) from exc
        verb = "installed" if current is None else "updated"
        return f"{verb} the {spec.display} plugin in {path}"

    return _PendingWrite(
        subject=f"the {spec.display} plugin at {path}",
        directories=(path.parent,),
        perform=write,
    )


def remove_plugin(spec: HarnessIntegration, home: Path) -> str:
    """Remove the managed plugin, leaving any other file at its path alone."""
    path = home / spec.hooks_file
    try:
        current = _managed_plugin(path)
    except IntegrationError as exc:
        return f"left {path} unchanged: {exc}"
    if current is None:
        return f"{spec.display} integration is not installed: no {path}"
    path.unlink()
    return f"removed the {spec.display} plugin {path}"


def plugin_status(spec: HarnessIntegration, home: Path) -> list[str]:
    """Report whether the managed plugin is installed, current, and bound to a helper."""
    path = home / spec.hooks_file
    try:
        current = _managed_plugin(path)
    except IntegrationError as exc:
        return [f"plugin conflict: {exc}"]
    if current is None:
        return [f"not installed: no {path}"]
    bound = PLUGIN_HELPER.search(current)
    try:
        helper = Path(json.loads(bound.group(1))) if bound else None
    except ValueError:
        helper = None
    if helper is None:
        return [
            f"plugin at {path} names no hook publisher; run 'dashpot integrate "
            f"{spec.harness}' to repair"
        ]
    messages = [f"plugin installed in {path}"]
    if current != render_plugin(helper):
        messages.append(
            f"plugin update available at {path}; run 'dashpot integrate "
            f"{spec.harness}' to repair"
        )
    if not helper.is_file():
        messages.append(
            f"hook publisher missing at {helper}; run 'dashpot integrate "
            f"{spec.harness}' to repair"
        )
    elif not os.access(helper, os.X_OK):
        messages.append(f"hook publisher at {helper} is not executable")
    else:
        messages.append(f"hook publisher: {helper}")
        binding = linked_worktree_binding(helper)
        if binding is not None:
            messages.append(f"warning: {_linked_worktree_consequence(spec, binding)}")
    return messages


def _opencode_skill_copies(destinations: list[tuple[BundledSkill, Path]]) -> list[str]:
    """Report the other copies of each bundled skill OpenCode also discovers.

    OpenCode reads skills from Claude Code's and the shared ``.agents``
    directories too, and when two share a name it uses either. Each harness's
    integration owns only its own copy, so a copy that differs from the one
    this Dashpot ships is reported for its own harness to repair.
    """
    messages: list[str] = []
    for skill, own in destinations:
        for owner, directory in (
            ("claude-code", CLAUDE_CODE.default_skills_home / skill.name),
            ("codex", CODEX.default_skills_home / skill.name),
        ):
            if same_path(directory, own) or not _may_hold_a_skill(directory):
                continue
            if not (_is_managed(skill, directory) and _is_current(skill, directory)):
                messages.append(
                    f"warning: OpenCode also discovers the {skill.label} at "
                    f"{directory}, which differs from this Dashpot's, and may use "
                    f"either; run 'dashpot integrate {owner}' or move it"
                )
    return messages


def _may_hold_a_skill(directory: Path) -> bool:
    """Whether a directory has a ``SKILL.md``, or cannot be inspected to say."""
    try:
        mode = _file_mode(directory / SKILL_FILE)
    except OSError:
        return True
    return mode is not None and stat.S_ISREG(mode)


def _opencode_plugin_copies(
    own: Path, current: Path | None, environ: Mapping[str, str] | None
) -> list[str]:
    """Report other copies of the managed plugin that OpenCode would also load.

    OpenCode loads every ``{plugin,plugins}/*.{js,ts}`` of each configuration
    directory it reads: the global one, every project ``.opencode`` from the
    working directory up to its Worktree, ``~/.opencode``, and
    ``$OPENCODE_CONFIG_DIR``. A second copy, under any name, is another
    plugin in the same server: it shares the first's registry, but may be
    bound to another helper, which then writes whichever events its instances
    admit first (ADR 0090).
    """
    environment = environ if environ is not None else os.environ
    directories = [own.parent.parent]
    if not _enabled(environment.get("OPENCODE_DISABLE_PROJECT_CONFIG")):
        start = (current or Path.cwd()).resolve()
        for directory in (start, *start.parents):
            directories.append(directory / ".opencode")
            if (directory / ".git").exists():
                break
    directories.append(Path.home() / ".opencode")
    configured = environment.get("OPENCODE_CONFIG_DIR")
    if configured:
        directories.append(Path(configured))
    seen: set[Path] = set()
    messages: list[str] = []
    for directory in directories:
        if directory.resolve() in seen:
            continue
        seen.add(directory.resolve())
        for candidate in sorted(
            path
            for folder in ("plugin", "plugins")
            for pattern in ("*.js", "*.ts")
            for path in (directory / folder).glob(pattern)
        ):
            try:
                managed = candidate.read_text(encoding="utf-8").startswith(
                    PLUGIN_MARKER
                )
            except (OSError, UnicodeDecodeError):
                managed = False
            if managed and not same_path(candidate, own):
                messages.append(
                    f"warning: OpenCode also loads a copy of the Dashpot plugin "
                    f"at {candidate}; each copy may publish through its own "
                    f"helper, so remove it"
                )
    return messages


def _enabled(value: str | None) -> bool:
    """Whether an OpenCode flag variable is set to true."""
    return (value or "").lower() in {"1", "true"}


def _opencode_version() -> str | None:
    """The version the ``opencode`` on PATH reports, or ``None`` when it cannot say."""
    found = shutil.which("opencode")
    if found is None:
        return None
    try:
        completed = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    version = completed.stdout.strip()
    return version if completed.returncode == 0 and version else None


def opencode_release(reported: str) -> str | None:
    """The OpenCode release that ``reported`` names; ``None`` when it names none."""
    match = OPENCODE_RELEASE.fullmatch(reported.strip())
    return None if match is None else str(match.group("release"))


def _major(release: str) -> int:
    return int(release.split(".", 1)[0])


def _opencode_release_status(label: str, reported: str | None) -> list[str]:
    """Report one OpenCode release: accepted, another v2, refused v1, or unknown."""
    if reported is None:
        return [f"{label}: none found"]
    release = opencode_release(reported)
    if release is None:
        return [
            f"{label}: unreadable",
            f"warning: Dashpot cannot read an OpenCode release in {reported!r}, "
            "so cannot tell whether the plugin observes it",
        ]
    if release == OPENCODE_ACCEPTED_VERSION:
        return [f"{label}: {release}, the accepted release"]
    if _major(release) == 1:
        return [
            f"{label}: {release}, refused",
            f"warning: Dashpot observes OpenCode v2 only: under {release} the "
            "plugin publishes nothing and no command can opt in; install "
            f"OpenCode {OPENCODE_ACCEPTED_VERSION} and run 'dashpot integrate opencode'",
        ]
    if _major(release) == 2:
        return [
            f"{label}: {release}",
            f"warning: OpenCode {release} is not the accepted release "
            f"{OPENCODE_ACCEPTED_VERSION}; the plugin observes it, but another "
            "release may change what it observes",
        ]
    return [
        f"{label}: {release}",
        f"warning: OpenCode {release} is not v2, so the plugin observes nothing "
        f"under it; install OpenCode {OPENCODE_ACCEPTED_VERSION}",
    ]


class OpenCodeServiceRegistration(PublishedModel):
    """The shared OpenCode service's registration, as far as Dashpot reads it."""

    version: str
    pid: int = Field(gt=0)


def _opencode_service_file(environ: Mapping[str, str]) -> Path | None:
    """Where OpenCode registers its service; ``None`` when that cannot be known.

    OpenCode takes ``XDG_STATE_HOME`` as it finds it, so a relative value
    names a directory relative to whichever process wrote the registration.
    """
    configured = environ.get("XDG_STATE_HOME")
    if not configured:
        return Path.home() / ".local" / "state" / "opencode" / "service.json"
    if not Path(configured).is_absolute():
        return None
    return Path(configured) / "opencode" / "service.json"


def _opencode_service_status(
    environ: Mapping[str, str], lookup: ProcessLookup
) -> list[str]:
    """Report the running shared service's release, which a client may replace.

    A client of another release replaces the service when it connects, so
    the service can run another release than the one on PATH (ADR 0090). A
    killed service leaves its registration behind, so its pid must still
    be an OpenCode server's.
    """
    path = _opencode_service_file(environ)
    if path is None:
        return [
            "OpenCode service: unknown; XDG_STATE_HOME is relative, so where "
            "OpenCode registers its service depends on the process that wrote it"
        ]
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"OpenCode service: none registered in {path}"]
    except (OSError, UnicodeDecodeError) as exc:
        return [f"OpenCode service: cannot read {path}: {exc}"]
    try:
        registration = OpenCodeServiceRegistration.model_validate_json(raw)
    except ValidationError as exc:
        return [
            f"OpenCode service: cannot read {path}: {describe_validation_error(exc)}"
        ]
    observed = lookup(registration.pid)
    if isinstance(observed, ProcessAbsent):
        return [
            f"OpenCode service: none running; {path} names pid "
            f"{registration.pid}, which has exited"
        ]
    if isinstance(observed, ProcessPresent) and not is_opencode_host_process(
        observed.identity
    ):
        return [
            f"OpenCode service: none running; {path} names pid "
            f"{registration.pid}, which is now another process"
        ]
    if isinstance(observed, ProcessUnobservable):
        running = (
            f"OpenCode service: pid {registration.pid}, registered in {path}, "
            f"could not be observed ({observed.reason})"
        )
    else:
        running = f"OpenCode service: pid {registration.pid}, registered in {path}"
    return [
        running,
        *_opencode_release_status("OpenCode service release", registration.version),
    ]


def _opencode_runtime_status(
    version_probe: Callable[[], str | None] | None,
    environ: Mapping[str, str] | None,
    lookup: ProcessLookup,
) -> list[str]:
    """Report the OpenCode releases and the settings that keep the plugin out."""
    environment = environ if environ is not None else os.environ
    messages = [
        *_opencode_release_status(
            "OpenCode release on PATH", (version_probe or _opencode_version)()
        ),
        *_opencode_service_status(environment, lookup),
    ]
    if _enabled(environment.get("OPENCODE_PURE")):
        messages.append(
            "warning: OPENCODE_PURE is set here; OpenCode started with it, or "
            "with --pure, loads no plugin and publishes nothing"
        )
    return messages
