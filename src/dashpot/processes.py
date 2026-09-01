"""Observe host processes, harness ancestry, and PID-namespace isolation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from .harnesses import ADAPTERS
from .repository import LockHolder


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    parent_pid: int
    command: str
    started_at: str
    arguments: str | None = None

    def as_record(self) -> dict[str, Any]:
        record = {
            "pid": self.pid,
            "parentPid": self.parent_pid,
            "command": self.command,
            "startedAt": self.started_at,
        }
        if self.arguments:
            record["arguments"] = self.arguments
        return record


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
ProcessKey = tuple[int, str]


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
) -> AgentAncestry:
    """Walk this command's ancestry to the nearest supported harness process."""
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
        for harness, matches in HARNESS_HOSTS.items():
            if matches(info):
                return AgentAncestry((harness, info))
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
    pid = os.getppid()
    seen: set[int] = set()
    matches = HARNESS_HOSTS[harness]
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        observed = lookup(pid)
        if not isinstance(observed, ProcessPresent):
            break
        info = observed.identity
        if matches(info):
            return info
        pid = info.parent_pid
    return None


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


def process_identity_of(expected: object) -> ProcessIdentity | None:
    """The full process identity a hook record carries, if it is well-formed."""
    if not isinstance(expected, dict):
        return None
    pid = expected.get("pid")
    parent_pid = expected.get("parentPid")
    command = expected.get("command")
    started_at = expected.get("startedAt")
    if (
        not isinstance(pid, int)
        or not isinstance(parent_pid, int)
        or not isinstance(command, str)
        or not isinstance(started_at, str)
    ):
        return None
    arguments = expected.get("arguments")
    return ProcessIdentity(
        pid,
        parent_pid,
        command,
        started_at,
        arguments if isinstance(arguments, str) and arguments else None,
    )


def process_key_of(expected: object) -> ProcessKey | None:
    """The recorded PID and start time of a session process record, if any."""
    if not isinstance(expected, dict):
        return None
    pid = expected.get("pid")
    started_at = expected.get("startedAt")
    if not isinstance(pid, int) or not isinstance(started_at, str):
        return None
    return pid, started_at
