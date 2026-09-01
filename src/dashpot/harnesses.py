"""Harness Adapters: how each supported harness identifies an Agent Session.

An adapter answers two questions about its harness without Dashpot knowing
the harness's internals: which host process is the harness itself (never a
sandbox helper), and what Agent Session Identity the harness lets a command
running inside the session see. Neither harness documents its identity
variables as stable, so an adapter's claim is never trusted on its own: Issue
opt-in validates every claim against the lifecycle hook record the harness
published for the same Worktree, and a claim that names no such record
cannot create an Issue Binding.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .processes import ProcessIdentity

SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
# Dashpot's own, documented way for a session to state its identity when the
# harness cannot be walked to and its native claim is absent or ambiguous:
# ``<harness>:<Agent Session Identity>``, validated like every other claim.
SESSION_OVERRIDE_VARIABLE = "DASHPOT_AGENT_SESSION"


@dataclass(frozen=True, slots=True)
class SessionIdentityClaim:
    """An Agent Session Identity a command's environment claims to run under.

    A claim is evidence to validate against the harness's hook record, never
    identity in itself. ``pid`` is the host PID the environment attributes to
    the harness, when it names one, and must agree with the record.
    """

    harness: str
    session_id: str
    source: str
    pid: int | None = None


@dataclass(frozen=True, slots=True)
class HarnessAdapter:
    """One supported harness's process and session identity contract."""

    harness: str
    display: str
    is_host_process: Callable[[ProcessIdentity], bool]
    claim_session_identity: Callable[[Mapping[str, str]], SessionIdentityClaim | None]


def is_codex_host_process(process: ProcessIdentity) -> bool:
    """Whether a process is the Codex harness itself, never its sandbox helper."""
    name = Path(process.command).name.lower()
    arguments = (process.arguments or "").lower()
    if "codex-linux-sandbox" in arguments or "sandbox" in name:
        return False
    return name == "codex" or name.startswith("codex-")


def is_claude_code_host_process(process: ProcessIdentity) -> bool:
    """Whether a process is the Claude Code harness itself."""
    return Path(process.command).name.lower() == "claude"


def _codex_claim(environ: Mapping[str, str]) -> SessionIdentityClaim | None:
    # Codex's shell tool exports its thread identifier, which is the
    # ``session_id`` its hooks publish. The variable is undocumented, so the
    # claim is only ever accepted when a Codex hook record confirms it.
    session_id = _identity(environ.get("CODEX_THREAD_ID"))
    if session_id is None:
        return None
    return SessionIdentityClaim("codex", session_id, "Codex environment")


def _claude_code_claim(environ: Mapping[str, str]) -> SessionIdentityClaim | None:
    # Claude Code's Bash tool exports its session identifier, which is the
    # ``session_id`` its hooks publish, beside the harness's own host PID.
    # Both are undocumented; the PID must agree with the hook record, and the
    # claim is only ever accepted when a Claude Code hook record confirms it.
    session_id = _identity(environ.get("CLAUDE_CODE_SESSION_ID"))
    if session_id is None:
        return None
    pid: int | None = None
    raw_pid = environ.get("CLAUDE_PID", "")
    if raw_pid.isdigit():
        pid = int(raw_pid)
    return SessionIdentityClaim(
        "claude-code", session_id, "Claude Code environment", pid
    )


CODEX = HarnessAdapter(
    harness="codex",
    display="Codex",
    is_host_process=is_codex_host_process,
    claim_session_identity=_codex_claim,
)

CLAUDE_CODE = HarnessAdapter(
    harness="claude-code",
    display="Claude Code",
    is_host_process=is_claude_code_host_process,
    claim_session_identity=_claude_code_claim,
)

ADAPTERS: dict[str, HarnessAdapter] = {
    adapter.harness: adapter for adapter in (CODEX, CLAUDE_CODE)
}

HARNESS_DISPLAY = {adapter.harness: adapter.display for adapter in ADAPTERS.values()}


def adapter(harness: str) -> HarnessAdapter:
    """The adapter for a supported harness."""
    found = ADAPTERS.get(harness)
    if found is None:
        raise RuntimeError(f"unsupported harness: {harness}")
    return found


def override_claim(environ: Mapping[str, str]) -> SessionIdentityClaim | None:
    """The explicit ``DASHPOT_AGENT_SESSION`` claim, if the environment sets one."""
    raw = environ.get(SESSION_OVERRIDE_VARIABLE)
    if not raw:
        return None
    harness, separator, session_id = raw.partition(":")
    if not separator or harness not in ADAPTERS or _identity(session_id) is None:
        supported = ", ".join(ADAPTERS)
        raise RuntimeError(
            f"{SESSION_OVERRIDE_VARIABLE} must be '<harness>:<session id>' with "
            f"a supported harness ({supported}); got {raw!r}"
        )
    return SessionIdentityClaim(harness, session_id, SESSION_OVERRIDE_VARIABLE)


def native_claims(environ: Mapping[str, str]) -> list[SessionIdentityClaim]:
    """Every harness's own Agent Session Identity claim, in adapter order."""
    claims: list[SessionIdentityClaim] = []
    for candidate in ADAPTERS.values():
        claim = candidate.claim_session_identity(environ)
        if claim is not None:
            claims.append(claim)
    return claims


def _identity(value: str | None) -> str | None:
    if not value or not SESSION_ID.fullmatch(value):
        return None
    return value
