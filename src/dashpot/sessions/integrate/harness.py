"""Install, remove, check and describe one harness's integration.

Each step is its hook installer's, the hooks file or OpenCode's plugin,
followed by each bundled skill's copy and agent's copy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

from ...core.model import Harness
from ..processes import ProcessLookup, host_process_lookup
from .agent_copies import (
    agent_copies,
    agent_has_update,
    agent_refusal,
    agent_status,
    is_managed_agent,
    plan_agent,
    remove_agent,
)
from .diagnostics import claimed_identity_status, record_store_status
from .hooks_file import HOOKS_FILE
from .installer import HookInstaller, StatusProbe
from .opencode_plugin import OPENCODE_PLUGIN
from .publisher import linked_worktree_binding, linked_worktree_consequence
from .registry import (
    BUNDLED_AGENTS,
    BUNDLED_SKILLS,
    BundledAgent,
    BundledSkill,
    HarnessIntegration,
    HookInstallerKind,
    configuration_in_use,
    integration,
    resolve_hook_command,
)
from .skill_copies import (
    is_managed,
    plan_skill,
    remove_skill,
    skill_copies,
    skill_has_update,
    skill_refusal,
    skill_status,
)
from .writes import IncompleteRemovalError, IntegrationError, Planned, write_planned

INSTALLERS: dict[HookInstallerKind, HookInstaller] = {
    "hooks file": HOOKS_FILE,
    "plugin": OPENCODE_PLUGIN,
}


def hook_installer(spec: HarnessIntegration) -> HookInstaller:
    """The hook installer of a harness's integration."""
    return INSTALLERS[spec.installer]


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
    configuration = configuration_in_use(spec, home)
    home = configuration.path
    if not home.is_dir():
        raise IntegrationError(
            f"no {spec.display} configuration directory at {configuration}; "
            f"install and run {spec.display} once before integrating"
        )
    destinations = skill_copies(spec, home, skills)
    agent_destinations = agent_copies(spec, home, agents)
    _validate_destinations(destinations, agent_destinations)
    command = command_path or resolve_hook_command(spec)
    # Refuse before anything is loaded or written: the binding would outlive
    # the environment it names, so the file is left exactly as it was.
    binding = linked_worktree_binding(command)
    if binding is not None:
        raise IntegrationError(
            f"cannot bind the {spec.display} hooks to {command}: "
            f"{linked_worktree_consequence(spec.harness, binding)}"
        )
    hooks = hook_installer(spec)
    planned: list[Planned] = [
        *hooks.plan(spec, home, command, version_probe=version_probe),
        f"hook publisher: {command}",
        *(plan_skill(skill, target) for skill, target in destinations),
        *(plan_agent(agent, target) for agent, target in agent_destinations),
        *hooks.notes(spec, home, destinations, None),
    ]
    return write_planned(harness, planned)


def _validate_destinations(
    destinations: list[tuple[BundledSkill, Path]],
    agent_destinations: list[tuple[BundledAgent, Path]],
) -> None:
    """Refuse when any skill or agent destination holds what Dashpot does not manage."""
    refusals = [
        *(skill_refusal(skill, target) for skill, target in destinations),
        *(agent_refusal(agent, target) for agent, target in agent_destinations),
    ]
    named = [refusal for refusal in refusals if refusal is not None]
    if named:
        raise IntegrationError("; ".join(named))


def remove_integration(
    harness: Harness,
    home: Path | None = None,
    *,
    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS,
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS,
) -> list[str]:
    """Remove exactly Dashpot's hooks, managed skills and agents for one harness.

    A step that fails, such as a hooks file that cannot be read or a file
    that cannot be unlinked, does not stop the others: every other step
    runs, and ``IncompleteRemovalError`` names each failure once they are
    done (ADR 0130).
    """
    spec = integration(harness)
    home = configuration_in_use(spec, home).path
    steps: list[Callable[[], str]] = [
        partial(hook_installer(spec).remove, spec, home),
        *(partial(remove_skill, *copy) for copy in skill_copies(spec, home, skills)),
        *(partial(remove_agent, *copy) for copy in agent_copies(spec, home, agents)),
    ]
    messages: list[str] = []
    failures: list[str] = []
    for step in steps:
        try:
            messages.append(step())
        except IntegrationError as exc:
            failures.append(str(exc))
    if failures:
        raise IncompleteRemovalError(harness, failures, messages)
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
    records: bool = True,
) -> list[str]:
    """Report the observable state of one harness's integration.

    ``records`` adds the session record stores, which every harness shares,
    so a report across harnesses states them once rather than per harness.
    """
    spec = integration(harness)
    hooks = hook_installer(spec)
    configuration = configuration_in_use(spec, home)
    home = configuration.path
    messages: list[str] = []
    if configuration.variable is not None:
        messages.append(f"{spec.display} configuration directory: {configuration}")
    if not home.is_dir():
        messages.append(
            f"{spec.display} configuration directory not found: {configuration}"
        )
    else:
        try:
            messages.extend(hooks.status_lines(spec, home))
        except IntegrationError as exc:
            return [*messages, str(exc)]
    destinations = skill_copies(spec, home, skills)
    messages.extend(
        skill_status(skill, target, harness=spec.harness)
        for skill, target in destinations
    )
    messages.extend(
        agent_status(agent, target, harness=spec.harness)
        for agent, target in agent_copies(spec, home, agents)
    )
    probe = StatusProbe(
        current=current, lookup=lookup, environ=environ, version_probe=version_probe
    )
    messages.extend(hooks.notes(spec, home, destinations, probe))
    if records:
        messages.extend(record_store_status(state_dir, current, lookup))
    messages.extend(claimed_identity_status(spec, current, lookup, environ))
    return messages


# How far one harness's integration is installed. Integrated means every
# lifecycle hook is registered, however stale its skills or agents; partial
# means some of Dashpot's integration is there without every hook.
IntegrationState = Literal["integrated", "partial", "not integrated"]


@dataclass(frozen=True, slots=True)
class IntegrationPresence:
    """How far one harness's integration is installed, and what shows it."""

    state: IntegrationState
    # What was found, such as "missing hook events: Stop".
    detail: str


def integration_presence(
    harness: Harness,
    home: Path | None = None,
    *,
    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS,
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS,
) -> IntegrationPresence:
    """Tell whether one harness is integrated: every lifecycle hook registered.

    A stale integration, every hook registered but a skill or agent behind
    or missing, is integrated, and refreshing it is what ``--installed``
    does. Some hooks without the others, or a managed skill or agent left
    with no hook, is partial: the person's opt-in incomplete or half
    removed. Raises ``IntegrationError`` when the hooks file or plugin
    cannot be read to tell.
    """
    spec = integration(harness)
    hooks = hook_installer(spec)
    configuration = configuration_in_use(spec, home)
    home = configuration.path
    if not home.is_dir():
        return IntegrationPresence(
            "not integrated",
            f"no {spec.display} configuration directory at {configuration}",
        )
    path = home / spec.hooks_file
    missing = hooks.missing(spec, home)
    if missing is not None and not missing:
        return IntegrationPresence(
            "integrated", f"every lifecycle hook registered in {path}"
        )
    if missing is not None:
        return IntegrationPresence(
            "partial", f"missing hook events in {path}: {', '.join(missing)}"
        )
    left = [
        *(
            f"the Dashpot {skill.label} at {target}"
            for skill, target in skill_copies(spec, home, skills)
            if is_managed(skill, target)
        ),
        *(
            f"the Dashpot {agent.label} at {target}"
            for agent, target in agent_copies(spec, home, agents)
            if is_managed_agent(agent, target)
        ),
    ]
    # The variable that moved the directory is named, as ``--status`` names
    # it, so a shell without it is seen looking in the default directory.
    where = (
        f" ({configuration.variable} names {home})" if configuration.variable else ""
    )
    if left:
        return IntegrationPresence(
            "partial",
            f"no Dashpot {hooks.noun} at {path}{where}, but {', '.join(left)}",
        )
    return IntegrationPresence(
        "not integrated", f"no Dashpot {hooks.noun} at {path}{where}"
    )


def has_update(
    spec: HarnessIntegration,
    home: Path,
    skills: tuple[BundledSkill, ...],
    agents: tuple[BundledAgent, ...],
) -> bool:
    """Whether refreshing an integrated harness would update its skills, agents or hooks.

    A skill or agent this release adds counts, as one behind does; one held
    by what Dashpot does not manage does not, since refreshing refuses it.
    """
    return (
        any(
            skill_has_update(skill, target)
            for skill, target in skill_copies(spec, home, skills)
        )
        or any(
            agent_has_update(agent, target)
            for agent, target in agent_copies(spec, home, agents)
        )
        or hook_installer(spec).has_update(spec, home)
    )
