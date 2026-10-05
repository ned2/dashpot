"""Install, update, remove and report each harness's managed copy of a bundled agent.

A copy is one Markdown file that carries the agent's marker (ADR 0093).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from ...core.model import Harness
from ...core.record_store import replace_atomically
from .registry import BUNDLED_SKILL_VERSION, BundledAgent, HarnessIntegration
from .writes import IntegrationError, PendingWrite, Planned

# What an agent's destination holds, judged by its marker.
AgentState = Literal["vacant", "managed", "unmanaged", "not a file"]


def agent_file(
    spec: HarnessIntegration, home: Path, agent: BundledAgent
) -> Path | None:
    """Locate this harness's user-wide copy of one bundled agent, if it installs agents."""
    if spec.agents_home is None:
        return None
    return home / spec.agents_home / f"{agent.name}.md"


def agent_copies(
    spec: HarnessIntegration, home: Path, agents: tuple[BundledAgent, ...]
) -> list[tuple[BundledAgent, Path]]:
    """Each bundled agent, paired with where this harness keeps its copy, if anywhere."""
    return [
        (agent, target)
        for agent in agents
        if (target := agent_file(spec, home, agent)) is not None
    ]


def _agent_state(agent: BundledAgent, destination: Path) -> AgentState:
    """What holds a bundled agent's destination.

    Nothing at the path leaves it vacant; anything else that is not a
    file, a link that leads nowhere included, is not one. Raises
    ``OSError`` when the file cannot be read, and ``ValueError`` when it is
    not text.
    """
    if not os.path.lexists(destination):
        return "vacant"
    if not destination.is_file():
        return "not a file"
    text = destination.read_text(encoding="utf-8")
    return "managed" if agent.marker in text else "unmanaged"


def is_managed_agent(agent: BundledAgent, destination: Path) -> bool:
    """Whether an agent file is readable and carries this agent's marker."""
    try:
        return _agent_state(agent, destination) == "managed"
    except (OSError, ValueError):
        return False


def _is_current_agent(agent: BundledAgent, destination: Path) -> bool:
    """Whether an agent file is the one this Dashpot ships, unchanged."""
    return destination.is_file() and (
        destination.read_bytes() == agent.source.read_bytes()
    )


def agent_has_update(agent: BundledAgent, destination: Path) -> bool:
    """Whether refreshing would write an agent: one behind, or one this release adds.

    A file Dashpot does not manage, or cannot read to tell, does not count,
    since refreshing refuses it.
    """
    try:
        state = _agent_state(agent, destination)
    except (OSError, ValueError):
        return False
    return state in ("vacant", "managed") and not _is_current_agent(agent, destination)


def agent_refusal(agent: BundledAgent, destination: Path) -> str | None:
    """Why an agent's destination holds what Dashpot does not manage; ``None`` when free.

    An absent agent file is free to install into; anything else at its path
    must be a file carrying that agent's own marker.
    """
    refused = f"cannot install the Dashpot {agent.label} at {destination}: "
    try:
        state = _agent_state(agent, destination)
    except (OSError, ValueError):
        state = "unmanaged"
    if state == "not a file":
        return f"{refused}the path is not a file; move it and retry"
    if state == "unmanaged":
        return (
            f"{refused}an existing agent is not managed by Dashpot; move it and retry"
        )
    return None


def plan_agent(agent: BundledAgent, destination: Path) -> Planned:
    """The pending write of the shipped agent definition, unless it is current."""
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

    return PendingWrite(
        subject=f"the Dashpot {agent.label} at {destination}",
        directories=(destination.parent,),
        perform=write,
    )


def remove_agent(agent: BundledAgent, destination: Path) -> str:
    """Remove a managed agent file, leaving any file that is not Dashpot's.

    Raises ``IntegrationError`` when the managed file cannot be unlinked.
    """
    try:
        state = _agent_state(agent, destination)
    except (OSError, ValueError) as exc:
        return f"could not inspect Dashpot {agent.label} at {destination}: {exc}"
    if state == "vacant":
        return f"Dashpot {agent.label} is not installed: no {destination}"
    if state != "managed":
        return f"left unmanaged {agent.label} unchanged at {destination}"
    try:
        destination.unlink()
    except OSError as exc:
        raise IntegrationError(
            f"could not remove Dashpot {agent.label} from {destination}: {exc}"
        ) from exc
    return f"removed the Dashpot {agent.label} from {destination}"


def agent_status(agent: BundledAgent, destination: Path, *, harness: Harness) -> str:
    """Report whether an agent file is installed, current, or not Dashpot's."""
    try:
        state = _agent_state(agent, destination)
    except (OSError, ValueError) as exc:
        return f"{agent.label} unreadable at {destination}: {exc}"
    if state == "vacant":
        return f"{agent.label} not installed: no {destination}"
    if state != "managed":
        return f"{agent.label} conflict at {destination}: not managed by Dashpot"
    if not _is_current_agent(agent, destination):
        return (
            f"{agent.label} update available at {destination}; run "
            f"'dashpot integrate {harness}' to repair"
        )
    return (
        f"{agent.label} installed in {destination} for Dashpot {BUNDLED_SKILL_VERSION}"
    )
