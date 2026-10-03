"""Harness Adapters: how each supported harness identifies an Agent Session.

An adapter answers its harness's questions without Dashpot knowing the
harness's internals: which host process is the harness itself (never a
sandbox helper), what Agent Session Identity the harness lets a command
running inside the session see, whether that Host Process is exclusive to one
session, and which of its hook events are designated location evidence
(ADR 0067). No harness documents its identity variables as stable, so an
adapter's claim is never trusted on its own: Issue opt-in validates every
claim against the lifecycle hook record the harness published for the same
Worktree, and a claim that names no such record cannot create an Issue
Binding.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import AfterValidator, BeforeValidator

from ..core.errors import DashpotError
from ..core.model import HARNESS_DISPLAY, Harness, is_harness

# ``processes`` imports this module's adapters to walk a command's ancestry,
# and each adapter's host-process predicate is typed on the ``ProcessIdentity``
# that walk hands it. The cycle is between a leaf module and its one consumer
# and exists only in annotations, so it is kept type-only rather than broken by
# moving the identity dataclass out of the module that observes it.
if TYPE_CHECKING:
    from .processes import ProcessIdentity

SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")


class HarnessError(DashpotError):
    """A harness name Dashpot does not support, or an identity claim it cannot parse."""


def _hook_session_identity(value: str) -> str:
    if not SESSION_ID.fullmatch(value):
        raise ValueError(
            "must be a hook session identity: contains unsupported characters"
        )
    return value


def _supported_harness(value: object) -> object:
    if not is_harness(value):
        raise ValueError(f"unsupported harness: {value!r}")
    return value


# The native session identity a harness publishes; the hook and Work Store
# records share one rule for it.
HookSessionIdentity = Annotated[str, AfterValidator(_hook_session_identity)]
# A persisted harness name: the ``Harness`` union types it, and the validator
# ahead of the union keeps the record's refusal naming the harness.
HarnessName = Annotated[Harness, BeforeValidator(_supported_harness)]
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

    harness: Harness
    session_id: str
    source: str
    pid: int | None = None


# A native hook event, as the harness wrote it to the publisher's stdin.
HookEvent = Mapping[str, object]

# The native field naming the delegated work an event belongs to: Codex and
# Claude Code both put ``agent_id`` on a sub-agent's hook events beside the
# parent's ``session_id``.
CHILD_SCOPE_FIELD = "agent_id"


def delegate_id(value: object) -> str | None:
    """The delegate a child-scoped event or record names, if it names one."""
    return value if isinstance(value, str) and value else None


def is_child_scoped(event: HookEvent) -> bool:
    """Whether a native hook event belongs to a Sub-agent rather than its session.

    A child-scoped event updates only its parent's live sub-agents; it never
    places, routes, binds, ends, or moves the parent (ADR 0067).
    """
    return delegate_id(event.get(CHILD_SCOPE_FIELD)) is not None


def _designates_nothing(_event: HookEvent) -> bool:
    return False


def _defers_nothing(_process: ProcessIdentity) -> bool:
    return False


@dataclass(frozen=True, slots=True)
class HarnessAdapter:
    """One supported harness's process and session identity contract."""

    harness: Harness
    display: str
    is_host_process: Callable[[ProcessIdentity], bool]
    claim_session_identity: Callable[[Mapping[str, str]], SessionIdentityClaim | None]
    # Whether the host process serves exactly one Agent Session, so that
    # process being gone proves the session's own runtime ended. Only then can
    # a hook from a new process continue the session's Agent Run (ADR 0053).
    exclusive_session_process: bool = False
    # Whether a native hook event is this harness's designated location
    # evidence: where the harness itself says the session now executes, and
    # so the only evidence that may carry an Agent Run to another Worktree
    # (Live Relocation, ADR 0067). A tool call's working directory never is.
    locates: Callable[[HookEvent], bool] = _designates_nothing
    # Whether a ``SessionEnd`` from this Host Process may be the host's own
    # stop or restart rather than the session's end. Such an end is settled
    # by whether the host keeps running: a host that exits leaves the run an
    # Orphaned Agent Run, and nothing is ever continued (ADR 0086).
    defers_session_end: Callable[[ProcessIdentity], bool] = _defers_nothing


def is_codex_host_process(process: ProcessIdentity) -> bool:
    """Whether a process is the Codex harness itself, never its sandbox helper."""
    name = Path(process.command).name.lower()
    arguments = (process.arguments or "").lower()
    if "codex-linux-sandbox" in arguments or "sandbox" in name:
        return False
    return name == "codex" or name.startswith("codex-")


def is_codex_managed_daemon(process: ProcessIdentity) -> bool:
    """Whether a Codex Host Process is the managed daemon, by its argument vector.

    Measured at 0.159.3 and 0.160.0, the daemon runs as ``codex app-server``
    with ``--managed-daemon``, beside ``--listen unix://`` and, when a
    terminal autostarted it, ``--remote-control``. A stop or restart of the
    daemon publishes ``SessionEnd`` for every thread it holds, as an idle
    unload does, and then exits (ADR 0086).
    """
    if not is_codex_host_process(process):
        return False
    tokens = (process.arguments or "").split()
    return "app-server" in tokens and "--managed-daemon" in tokens


def is_claude_code_host_process(process: ProcessIdentity) -> bool:
    """Whether a process is the Claude Code harness itself.

    A process started through the launcher is named ``claude``. A worker of
    the background supervisor is named after its version instead, as are the
    supervisor and each worker's PTY host, so a version-shaped name admits
    only a process whose argument vector has a measured worker shape.
    """
    if Path(process.command).name.lower() == "claude":
        return True
    return is_claude_code_supervised_worker(process)


# The native installer's executable, and so the name of every process the
# background supervisor runs, is its version: ``2.1.285``.
CLAUDE_CODE_VERSION_NAME = re.compile(r"^\d+\.\d+\.\d+$")
CLAUDE_CODE_SPARE_WORKER_ARGUMENTS = "claude bg-spare --bg-spare "
# The executable's path is matched whole, so a home directory with a space in
# it still reads as one path.
CLAUDE_CODE_SPAWNED_WORKER_ARGUMENTS = re.compile(
    r"^/.*/claude/versions/(\d+\.\d+\.\d+) (?:--session-id|--resume) \S"
)


def is_claude_code_supervised_worker(process: ProcessIdentity) -> bool:
    """Whether a version-named process is a worker of Claude Code's supervisor.

    Measured on Linux at 2.1.276 and 2.1.285, a worker starts in one of three
    shapes: the installer's versioned executable with ``--session-id`` when
    spawned for a new session, the same with ``--resume <transcript>`` when
    the supervisor replaces a worker that died, or ``claude bg-spare`` when it
    claimed a pre-warmed spare, as a new session or a respawn may. Only the
    start of the argument vector counts, since a PTY host's arguments carry
    its worker's whole command after ``--``. The supervisor (``daemon run``),
    the PTY host (``bg-pty-host``), and the ``agents`` and ``attach`` clients
    have other shapes and are no session's worker, so they are never the host.
    """
    version = Path(process.command).name
    if not CLAUDE_CODE_VERSION_NAME.fullmatch(version):
        return False
    arguments = process.arguments or ""
    if arguments.startswith(CLAUDE_CODE_SPARE_WORKER_ARGUMENTS):
        return True
    spawned = CLAUDE_CODE_SPAWNED_WORKER_ARGUMENTS.match(arguments)
    return spawned is not None and str(spawned.group(1)) == version


def _codex_locates(event: HookEvent) -> bool:
    # Codex hooks report the turn's own ``cwd``, which follows a controller's
    # ``turn/start`` override and a ``-C`` resume. ``locates_session`` leaves
    # out a sub-agent's prompt, which is its own thread's, never its root's.
    return event.get("hook_event_name") == "UserPromptSubmit"


def _claude_code_locates(event: HookEvent) -> bool:
    # The worktree tools move the session itself and fire no lifecycle hook,
    # and their ``PostToolUse`` reports the Worktree it arrived at (ADR 0009).
    # ``ExitWorktree`` with ``remove`` deletes the Worktree it leaves, so only
    # ``keep`` is a move. Any other hook's ``cwd`` follows a persistent shell
    # ``cd``, which places the session but never carries its run (ADR 0074).
    if event.get("hook_event_name") != "PostToolUse":
        return False
    tool = event.get("tool_name")
    if tool == "EnterWorktree":
        return True
    tool_input = event.get("tool_input")
    if tool != "ExitWorktree" or not isinstance(tool_input, Mapping):
        return False
    action: object = tool_input.get("action")
    return action == "keep"


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


def is_opencode_host_process(process: ProcessIdentity) -> bool:
    """Whether a process is an OpenCode server: the ``opencode`` executable.

    Measured at 2.0.22, the shared service (``opencode serve --service``)
    and a ``--standalone`` client's private server each run every shell
    command and plugin helper of their sessions as direct children. The
    curl install names the executable ``opencode`` and the npm one
    ``opencode.exe``, on Linux too. A client, the TUI included, is never a
    shell's ancestor, so the nearest match is always the server.
    """
    return Path(process.command).name.lower() in {"opencode", "opencode.exe"}


# OpenCode sets these on a shell the model runs, after every plugin hook;
# Dashpot's plugin deletes both on every shell first, so only OpenCode's own
# step for a model's shell can have set them again (ADR 0090).
OPENCODE_SESSION_VARIABLE = "OPENCODE_SESSION_ID"
OPENCODE_MARKER_VARIABLE = "OPENCODE"
# The Host Process pid Dashpot's plugin gives every shell it prepares.
OPENCODE_PID_VARIABLE = "DASHPOT_OPENCODE_PID"
# The OpenCode release Dashpot is pinned to, whose plugin API, events and
# process shape were measured (ADR 0090). Another 2.x release is observed
# with a warning; v1 is refused.
OPENCODE_PINNED_VERSION = "2.0.22"
# The plugin's v1 entry sets this on each shell OpenCode v1's ``shell.env``
# hook prepares, to the reason it cannot opt in: Dashpot observes OpenCode v2
# only (ADR 0090).
OPENCODE_REFUSAL_VARIABLE = "DASHPOT_OPENCODE_REFUSAL"
OPENCODE_V1_REFUSAL = "opencode-v1"


def _opencode_claim(environ: Mapping[str, str]) -> SessionIdentityClaim | None:
    # A claim is OpenCode's own session variable, valid only beside its
    # marker and the plugin's pid: an inherited ``OPENCODE_SESSION_ID`` alone
    # can name any session, so it is never a claim.
    session_id = _identity(environ.get(OPENCODE_SESSION_VARIABLE))
    raw_pid = environ.get(OPENCODE_PID_VARIABLE, "")
    if (
        session_id is None
        or environ.get(OPENCODE_MARKER_VARIABLE) != "1"
        or not raw_pid.isdigit()
    ):
        return None
    return SessionIdentityClaim(
        "opencode", session_id, "OpenCode environment", int(raw_pid)
    )


def opencode_shell_refusal(environ: Mapping[str, str], in_opencode: bool) -> str | None:
    """Why a command OpenCode ran without a claim cannot opt in; ``None`` for any other.

    A shell OpenCode v1 prepared carries the plugin's v1 refusal. A user
    shell, run through OpenCode's shell route (the TUI's ``!``),
    keeps the plugin's pid but loses the variables OpenCode sets only for a
    model's shell. A terminal runs no plugin hook, so it carries no pid;
    ``in_opencode`` says whether an OpenCode server is its ancestor.
    """
    if _opencode_claim(environ) is not None:
        return None
    if environ.get(OPENCODE_REFUSAL_VARIABLE) == OPENCODE_V1_REFUSAL:
        return (
            "this command runs in OpenCode v1, and Dashpot observes OpenCode v2 "
            f"only; install OpenCode {OPENCODE_PINNED_VERSION} and run "
            "'dashpot integrate opencode'"
        )
    if environ.get(OPENCODE_PID_VARIABLE, "").isdigit():
        return (
            "this command runs in a shell the user started in OpenCode, not "
            "one its agent ran; only an agent's command can opt in"
        )
    if in_opencode:
        return (
            "this command runs in an OpenCode terminal, which is no agent's "
            "command; only an agent's command can opt in"
        )
    return None


def _opencode_locates(event: HookEvent) -> bool:
    # OpenCode's ``session.moved`` keeps the session's identity and server
    # and changes where its later shells run; the helper writes a root's
    # move as this event alone (ADR 0090).
    return event.get("hook_event_name") == "SessionMoved"


# A daemon-hosted Codex terminal records the daemon, which serves many threads
# and outlives any one of them. The managed daemon's own stop or restart
# publishes the same ``SessionEnd`` as an unload, so its end is deferred.
CODEX = HarnessAdapter(
    harness="codex",
    display=HARNESS_DISPLAY["codex"],
    is_host_process=is_codex_host_process,
    claim_session_identity=_codex_claim,
    locates=_codex_locates,
    defers_session_end=is_codex_managed_daemon,
)

# One Claude Code process per session: its sub-agents share the parent's
# session as well as its process, and each supervised worker, a spare
# included, hosts one session for its whole life. Its worktree tools'
# ``PostToolUse`` are its designated location evidence, so a session that
# enters or returns from a Worktree takes its run with it (ADR 0067).
CLAUDE_CODE = HarnessAdapter(
    harness="claude-code",
    display=HARNESS_DISPLAY["claude-code"],
    is_host_process=is_claude_code_host_process,
    claim_session_identity=_claude_code_claim,
    exclusive_session_process=True,
    locates=_claude_code_locates,
)

# One OpenCode server serves every session of every location it has an
# instance for, and outlives each of them, so its exit never proves one
# session ended and a run never continues on its own (ADR 0090). A root
# session's move is its designated location evidence (ADR 0067).
OPENCODE = HarnessAdapter(
    harness="opencode",
    display=HARNESS_DISPLAY["opencode"],
    is_host_process=is_opencode_host_process,
    claim_session_identity=_opencode_claim,
    locates=_opencode_locates,
)

ADAPTERS: dict[Harness, HarnessAdapter] = {
    adapter.harness: adapter for adapter in (CODEX, CLAUDE_CODE, OPENCODE)
}


def locates_session(harness: Harness, event: HookEvent) -> bool:
    """Whether a hook event is its harness's designated, session-scoped location evidence.

    Only such an event may carry an Agent Run (ADR 0067): it is never a
    child-scoped event, and never ``SessionStart`` or ``SessionEnd``, which
    begin and end an incarnation rather than move one.
    """
    if is_child_scoped(event) or event.get("hook_event_name") in {
        "SessionStart",
        "SessionEnd",
    }:
        return False
    return adapter(harness).locates(event)


def adapter(harness: Harness) -> HarnessAdapter:
    """The adapter for a supported harness."""
    found = ADAPTERS.get(harness)
    if found is None:
        raise HarnessError(f"unsupported harness: {harness}")
    return found


def override_claim(environ: Mapping[str, str]) -> SessionIdentityClaim | None:
    """The explicit ``DASHPOT_AGENT_SESSION`` claim, if the environment sets one."""
    raw = environ.get(SESSION_OVERRIDE_VARIABLE)
    if not raw:
        return None
    harness, separator, session_id = raw.partition(":")
    if not separator or not is_harness(harness) or _identity(session_id) is None:
        supported = ", ".join(ADAPTERS)
        raise HarnessError(
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
