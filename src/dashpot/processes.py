"""Observe host processes, harness ancestry, and PID-namespace isolation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import SerializerFunctionWrapHandler, model_serializer

from .harnesses import ADAPTERS
from .models import PublishedModel
from .repository import LockHolder

ProcessKey = tuple[int, str]


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """One host process as the ``ps`` probe observed it."""

    pid: int
    parent_pid: int
    command: str
    started_at: str
    arguments: str | None = None

    @property
    def key(self) -> ProcessKey:
        return self.pid, self.started_at

    def as_record(self) -> dict[str, Any]:
        return SessionProcessRecord.of(self).model_dump(by_alias=True)


class SessionProcessRecord(PublishedModel):
    """A hook record's ``sessionProcess``: the identity the hook published."""

    pid: int
    parent_pid: int
    command: str
    started_at: str
    arguments: str | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_arguments(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        # The persisted shape omits ``arguments`` rather than writing null.
        record: dict[str, Any] = handler(self)
        if not self.arguments:
            record.pop("arguments", None)
        return record

    @classmethod
    def of(cls, identity: ProcessIdentity) -> SessionProcessRecord:
        return cls(
            pid=identity.pid,
            parent_pid=identity.parent_pid,
            command=identity.command,
            started_at=identity.started_at,
            arguments=identity.arguments or None,
        )

    @property
    def identity(self) -> ProcessIdentity:
        return ProcessIdentity(
            self.pid, self.parent_pid, self.command, self.started_at, self.arguments
        )


@dataclass(frozen=True, slots=True)
class ProcessPresent:
    """A host process with this identity is running."""

    identity: ProcessIdentity


@dataclass(frozen=True, slots=True)
class ProcessAbsent:
    """The host authoritatively reports no process with this PID."""

    pid: int


@dataclass(frozen=True, slots=True)
class ProcessUnobservable:
    """The process could not be observed; nothing is known about its state.

    ``reason`` is one of ``isolated-namespace``, ``ps-unavailable``,
    ``ps-timeout``, ``ps-failed``, ``ps-unparseable``, or ``kill-failed``.
    """

    pid: int
    reason: str


ProcessObservation = ProcessPresent | ProcessAbsent | ProcessUnobservable
ProcessLookup = Callable[[int], ProcessObservation]


def lock_holder_probe(pid: int) -> LockHolder:
    """Answer a Worktree lock's question about its holder with the host probe."""
    observed = host_process_lookup(pid)
    if isinstance(observed, ProcessAbsent):
        return "gone"
    if isinstance(observed, ProcessUnobservable):
        return "unknown"
    return "live"


def host_process_lookup(pid: int) -> ProcessObservation:
    """Observe one host process with the portable ``kill -0`` and ``ps`` probes.

    Absent is reported only when the host itself says no such process exists.
    Every failure to observe is reported as unobservable with its reason, so a
    broken probe is never mistaken for an exited process.
    """
    if process_namespace_is_isolated():
        return ProcessUnobservable(pid, "isolated-namespace")
    if pid <= 0:
        return ProcessAbsent(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return ProcessAbsent(pid)
    except PermissionError:
        pass  # The process exists; it belongs to another user.
    except OSError:
        return ProcessUnobservable(pid, "kill-failed")
    # ``comm`` is free-form — on macOS it is the executable's full path, which
    # may contain spaces — so it comes last in its probe and the fixed-width
    # fields are parsed from the left. ``args`` is free-form too, so it gets a
    # probe of its own rather than sharing a line with ``comm``. A process that
    # exits between the two probes reads as unobservable, never as exited, and
    # ``arguments`` is only ever advisory beside the identity fields.
    identity_output = _ps_column_output(pid, ("pid", "ppid", "lstart", "comm"))
    if isinstance(identity_output, ProcessUnobservable):
        return identity_output
    fields = identity_output.strip().split(maxsplit=7)
    if len(fields) < 8:
        return ProcessUnobservable(pid, "ps-unparseable")
    arguments_output = _ps_column_output(pid, ("args",))
    if isinstance(arguments_output, ProcessUnobservable):
        return arguments_output
    try:
        identity = ProcessIdentity(
            int(fields[0]),
            int(fields[1]),
            fields[7],
            " ".join(fields[2:7]),
            arguments_output.strip() or None,
        )
    except ValueError:
        return ProcessUnobservable(pid, "ps-unparseable")
    return ProcessPresent(identity)


def _ps_column_output(pid: int, columns: tuple[str, ...]) -> str | ProcessUnobservable:
    """Read the selected ``ps`` columns for one process, or why they cannot be."""
    selectors: list[str] = []
    for column in columns:
        selectors.extend(("-o", f"{column}="))
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), *selectors],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
            # Start times are compared as strings across processes, so the
            # locale and time zone they render in must not vary.
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
        )
    except OSError:
        return ProcessUnobservable(pid, "ps-unavailable")
    except subprocess.TimeoutExpired:
        return ProcessUnobservable(pid, "ps-timeout")
    if result.returncode != 0:
        return ProcessUnobservable(pid, "ps-failed")
    return result.stdout


def nearest_codex_process(
    lookup: ProcessLookup = host_process_lookup,
) -> ProcessIdentity | None:
    return nearest_harness_process("codex", lookup)


HARNESS_HOSTS: dict[str, Callable[[ProcessIdentity], bool]] = {
    adapter.harness: adapter.is_host_process for adapter in ADAPTERS.values()
}


@dataclass(frozen=True, slots=True)
class AgentAncestry:
    """What walking up from this command towards a harness process observed.

    ``located`` is the nearest enclosing supported harness process, if the
    walk reached one; ``unobservable_reason`` is why the walk stopped short
    when an ancestor could not be observed, such as ``isolated-namespace``.
    """

    located: tuple[str, ProcessIdentity] | None
    unobservable_reason: str | None = None


def observe_agent_ancestry(
    lookup: ProcessLookup = host_process_lookup,
    harness: str | None = None,
) -> AgentAncestry:
    """Walk this command's ancestry to the nearest supported harness process.

    With ``harness`` the walk matches only that harness's host processes;
    without it, any supported harness. Either way an unobservable ancestor
    stops the walk with its reason, so "sandboxed, cannot see" is never read
    as "no harness here".
    """
    hosts = HARNESS_HOSTS if harness is None else {harness: HARNESS_HOSTS[harness]}
    pid = os.getppid()
    seen: set[int] = set()
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        observed = lookup(pid)
        if isinstance(observed, ProcessUnobservable):
            return AgentAncestry(None, observed.reason)
        if not isinstance(observed, ProcessPresent):
            break
        info = observed.identity
        for name, matches in hosts.items():
            if matches(info):
                return AgentAncestry((name, info))
        pid = info.parent_pid
    return AgentAncestry(None)


def nearest_agent_process(
    lookup: ProcessLookup = host_process_lookup,
) -> tuple[str, ProcessIdentity] | None:
    """Find the nearest enclosing supported harness process, if any."""
    return observe_agent_ancestry(lookup).located


def nearest_harness_process(
    harness: str, lookup: ProcessLookup = host_process_lookup
) -> ProcessIdentity | None:
    """Find the nearest enclosing process of one named harness, if any."""
    located = observe_agent_ancestry(lookup, harness=harness).located
    return None if located is None else located[1]


# Sandbox helpers that run a command as PID 2 of a fresh PID namespace: the
# Codex Linux sandbox and bubblewrap, which Claude Code's Linux sandbox uses.
# Neither is ever the host harness, and nothing on the host is visible from
# inside them, so probing a recorded PID there would only ever find PID reuse.
ISOLATING_INITS = ("codex-linux-sandbox", "bwrap")
# Docker and Podman leave a marker file at the container root; other engines
# name themselves in PID 1's control groups on cgroup v1 layouts. A markerless
# engine under cgroup v2 (PID 1's cgroup reads ``0::/``) is a known gap that
# still errs toward the old behaviour, never toward a false "gone".
CONTAINER_MARKERS = (".dockerenv", "run/.containerenv")
CONTAINER_CGROUP_TOKENS = ("docker", "libpod", "kubepods", "lxc", "containerd")


@cache
def process_namespace_is_isolated() -> bool:
    """Whether this command runs inside a sandbox's isolated PID namespace.

    A process cannot leave its PID namespace, so the answer is computed once
    per process rather than re-read from ``/proc`` on every liveness probe.
    """
    return namespace_is_isolated(Path("/"))


def namespace_is_isolated(root: Path) -> bool:
    """Whether the PID namespace at this filesystem root hides host processes.

    Sandbox helpers run as PID 1 of the namespace they unshare, and a
    container's PID 1 is its entrypoint; in both layouts a harness running
    outside is unobservable from inside, never gone.
    """
    for marker in CONTAINER_MARKERS:
        if (root / marker).exists():
            return True
    try:
        cmdline = (root / "proc/1/cmdline").read_bytes()
    except OSError:
        cmdline = b""
    executable = Path(cmdline.split(b"\0", 1)[0].decode(errors="replace")).name
    if executable in ISOLATING_INITS:
        return True
    try:
        cgroup = (root / "proc/1/cgroup").read_text()
    except OSError:
        return False
    return any(token in cgroup for token in CONTAINER_CGROUP_TOKENS)
