"""Identify the Agent Session that encloses a ``work`` command.

The identity a harness claims in the environment is confirmed by its
freshest lifecycle hook record and, where the enclosing harness process can
be observed, corroborated by it. Every ``work`` command identifies its
session through :func:`enclosing_session`, which also refuses a command that
changes Issue work when a Sub-agent runs it (ADR 0067).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.command_outcomes import OutcomeNote
from ..core.errors import DashpotError
from ..core.model import HARNESS_DISPLAY, Harness, harness_alternatives
from .harnesses import (
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    native_claims,
    opencode_shell_refusal,
    override_claim,
)
from .hook_claims import (
    SessionClaimError,
    ValidatedSessionIdentity,
    validate_session_claim,
)
from .hook_scan import reachable_hook_stores
from .processes import (
    AgentAncestry,
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .session_labels import work_session_label
from .session_matching import SessionEvidence
from .work_store import SessionProcess


class IssueWorkError(DashpotError):
    """A refusal of a work management command, for the enclosing or a named Agent Session."""


@dataclass(frozen=True, slots=True)
class AgentSessionIdentity:
    """Represent a confirmed Agent Session and its corroborating process evidence.

    ``delegate`` names the Sub-agent the command runs in, when its harness
    tells a Sub-agent's shell apart from its session's own: the identity is
    still the session's, so reading resolves to it, but every command that
    changes the session's Issue work refuses (ADR 0067). Only Codex sets it:
    an OpenCode child session's claim is refused at validation instead
    (ADR 0090), and a Claude Code Sub-agent's shell carries its session's
    own identity.
    """

    harness: Harness
    session_key: str
    session_label: str
    process: ProcessIdentity | None
    session_id: str
    delegate: str | None = None

    @property
    def session_process(self) -> SessionProcess | None:
        if self.process is None:
            return None
        return SessionProcess.of(self.process)

    @property
    def process_key(self) -> ProcessKey | None:
        if self.process is None:
            return None
        return self.process.pid, self.process.started_at


def enclosing_session(
    root: Path,
    worktrees: Sequence[Path],
    *,
    command: str | None,
    lookup: ProcessLookup,
    environ: Mapping[str, str] | None,
    note: OutcomeNote | None = None,
) -> tuple[AgentSessionIdentity, list[Path]]:
    """Identify the Agent Session enclosing a ``work`` command run at ``root``.

    Returns the session with the hook stores reachable from the Repository's
    ``worktrees``, which confirmed it. ``note`` hears the session once it is
    confirmed. ``command`` names a ``work`` subcommand that changes the
    session's Issue work, which a Sub-agent is refused (ADR 0067); a command
    that only reads passes ``None`` and resolves to the Sub-agent's session.
    """
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    if note is not None:
        note.identify(harness=session.harness, session_id=session.session_id)
    if command is not None:
        _refuse_delegate(session, command)
    return session, stores


def identify_agent_session(
    lookup: ProcessLookup = host_process_lookup,
    *,
    environ: Mapping[str, str] | None = None,
    worktree: Path | None = None,
    stores: Sequence[Path] | None = None,
) -> AgentSessionIdentity:
    """Identify the enclosing session by a hook-confirmed native identity.

    A Sub-agent's command identifies its session, with ``delegate`` set, so
    a caller that changes Issue work refuses it, as :func:`enclosing_session`
    does.
    """
    environment = environ if environ is not None else os.environ
    ancestry = observe_agent_ancestry(lookup)
    claims = _session_claims(environment)
    if not claims:
        raise IssueWorkError(_no_session_message(ancestry, environment))
    if worktree is None:
        raise IssueWorkError(
            "an Agent Session Identity claimed by the environment can only be "
            "validated at a Worktree with a Project-local hook record store"
        )
    validated: list[ValidatedSessionIdentity] = []
    failures: list[str] = []
    for claim in claims:
        try:
            validated.append(
                validate_session_claim(claim, worktree, lookup, stores=stores)
            )
        except SessionClaimError as exc:
            failures.append(str(exc))
    if len(validated) == 1:
        confirmed = validated[0]
        if ancestry.located is not None:
            harness, process = ancestry.located
            if harness != confirmed.harness or (
                confirmed.process is not None and confirmed.process.key != process.key
            ):
                raise IssueWorkError(
                    "the claimed Agent Session Identity does not corroborate the "
                    "enclosing harness process; nothing was written"
                )
            return _process_identity(
                harness, process, confirmed.session_id, confirmed.delegate
            )
        return _session_identity(confirmed)
    if validated:
        names = " and ".join(
            f"{HARNESS_DISPLAY[item.harness]} session {item.session_id}"
            for item in validated
        )
        raise IssueWorkError(
            f"the environment claims more than one live Agent Session ({names}); "
            f"set {SESSION_OVERRIDE_VARIABLE}=<harness>:<session id> to say which "
            f"session this command belongs to"
        )
    raise IssueWorkError(
        _no_session_message(ancestry, environment) + "; " + "; ".join(failures)
    )


def _session_claims(environment: Mapping[str, str]) -> list[SessionIdentityClaim]:
    """The identities to validate: an explicit override alone, else every native claim."""
    explicit = override_claim(environment)
    if explicit is not None:
        return [explicit]
    return native_claims(environment)


def _no_session_message(ancestry: AgentAncestry, environment: Mapping[str, str]) -> str:
    unobservable_reason = ancestry.unobservable_reason
    message = (
        "no supported agent session encloses this command; Issue work opt-in "
        f"must run from inside a running {harness_alternatives()} session"
    )
    in_opencode = ancestry.located is not None and ancestry.located[0] == "opencode"
    refusal = opencode_shell_refusal(environment, in_opencode)
    if refusal is not None:
        message += f" ({refusal})"
    if unobservable_reason == "isolated-namespace":
        message += (
            " (this command runs in a sandbox's isolated process namespace, so "
            "the harness must be identified by the Agent Session Identity its "
            "lifecycle hooks publish; check 'dashpot integrate <harness> --status')"
        )
    elif unobservable_reason is not None:
        message += (
            f" (the enclosing process could not be observed: {unobservable_reason})"
        )
    return message


def _process_identity(
    harness: Harness,
    process: ProcessIdentity,
    session_id: str,
    delegate: str | None,
) -> AgentSessionIdentity:
    return AgentSessionIdentity(
        harness=harness,
        session_key=SessionEvidence(harness, session_id).storage_key(),
        session_label=work_session_label(harness, session_id, pid=process.pid),
        process=process,
        session_id=session_id,
        delegate=delegate,
    )


def _session_identity(confirmed: ValidatedSessionIdentity) -> AgentSessionIdentity:
    """Identify a session by its confirmed native identity on either route."""
    return AgentSessionIdentity(
        harness=confirmed.harness,
        session_key=SessionEvidence(
            confirmed.harness, confirmed.session_id
        ).storage_key(),
        session_label=work_session_label(
            confirmed.harness,
            confirmed.session_id,
            pid=confirmed.process.pid if confirmed.process is not None else None,
        ),
        process=confirmed.process,
        session_id=confirmed.session_id,
        delegate=confirmed.delegate,
    )


def _refuse_delegate(session: AgentSessionIdentity, command: str) -> None:
    """Refuse a command that changes Issue work when a Sub-agent runs it.

    A Sub-agent's work belongs to its session's Agent Run, so only the
    session itself starts, moves, ends or assigns that run (ADR 0067), as an
    OpenCode child session is refused (ADR 0090).
    """
    if session.delegate is None:
        return
    raise IssueWorkError(
        f"{HARNESS_DISPLAY[session.harness]} sub-agent {session.delegate} is "
        f"refused (delegated-session): it is a sub-agent of session "
        f"{session.session_id}, whose Agent Run its work belongs to; run "
        f"'dashpot work {command}' from session {session.session_id}, so "
        f"nothing was written"
    )
