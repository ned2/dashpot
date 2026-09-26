"""Observe host processes, harness ancestry, and PID-namespace isolation."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SerializerFunctionWrapHandler, model_serializer

from ..core.commands import recording_command
from ..core.model import Harness
from ..core.pydantic import PublishedModel
from .harnesses import ADAPTERS

ProcessKey = tuple[int, str]
# Whether the process holding a Worktree lock is still running: the answer the
# process adapter gives the Git observation of a lock Git reports.
# A process is live, gone, or could not be observed; unknown is never evidence
# that it ended.
ProcessLiveness = Literal["live", "gone", "unknown"]


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


def process_liveness(
    observed: ProcessObservation,
) -> tuple[ProcessLiveness, str | None]:
    """Read an observation as live, gone, or unknown with the adapter's reason."""
    if isinstance(observed, ProcessAbsent):
        return "gone", None
    if isinstance(observed, ProcessUnobservable):
        return "unknown", observed.reason
    return "live", None


def lock_holder_probe(pid: int) -> ProcessLiveness:
    """Answer a Worktree lock's question about its holder with the host probe."""
    return process_liveness(host_process_lookup(pid))[0]


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
    args = ["ps", "-p", str(pid), *selectors]
    with recording_command(args) as record:
        try:
            result = subprocess.run(
                args,
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
                # Start times are compared as strings across processes, so the
                # locale and time zone they render in must not vary.
                env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
            )
        except OSError as exc:
            record.could_not_run(exc)
            return ProcessUnobservable(pid, "ps-unavailable")
        except subprocess.TimeoutExpired as exc:
            record.could_not_run(exc)
            return ProcessUnobservable(pid, "ps-timeout")
        record.exited(result.returncode)
    if result.returncode != 0:
        return ProcessUnobservable(pid, "ps-failed")
    return result.stdout


def process_started_at(started_at: str) -> datetime | None:
    """The instant a recorded ``ps`` start time names, or ``None`` if unreadable.

    The probe renders ``lstart`` in the C locale and UTC, so the recorded
    text is an exact instant on every supported platform.
    """
    try:
        return datetime.strptime(started_at, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


# ``sysctl -n kern.boottime`` on macOS: ``{ sec = 1790159795, usec = 0 } ...``.
BOOT_SECONDS = re.compile(r"\bsec\s*=\s*(\d+)")


@cache
def host_boot_time() -> datetime | None:
    """When this host last booted, or ``None`` when the host cannot say.

    Read once per process: a reboot also ends the process asking.
    """
    return boot_time(Path("/proc/stat"))


def boot_time(stat: Path) -> datetime | None:
    """The boot time Linux's ``stat`` file records, else macOS's ``sysctl``."""
    try:
        for line in stat.read_text().splitlines():
            name, _, value = line.partition(" ")
            if name == "btime" and value.strip().isdigit():
                return datetime.fromtimestamp(int(value), tz=UTC)
    except OSError:
        pass
    args = ["sysctl", "-n", "kern.boottime"]
    with recording_command(args) as record:
        try:
            result = subprocess.run(
                args, text=True, capture_output=True, timeout=2, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.could_not_run(exc)
            return None
        record.exited(result.returncode)
    found = BOOT_SECONDS.search(result.stdout) if result.returncode == 0 else None
    if found is None:
        return None
    return datetime.fromtimestamp(int(found.group(1)), tz=UTC)


HARNESS_HOSTS: dict[Harness, Callable[[ProcessIdentity], bool]] = {
    adapter.harness: adapter.is_host_process for adapter in ADAPTERS.values()
}


@dataclass(frozen=True, slots=True)
class AgentAncestry:
    """What walking up from this command towards a harness process observed.

    ``located`` is the nearest enclosing supported harness process, if the
    walk reached one; ``unobservable_reason`` is why the walk stopped short
    when an ancestor could not be observed, such as ``isolated-namespace``.
    """

    located: tuple[Harness, ProcessIdentity] | None
    unobservable_reason: str | None = None


def observe_agent_ancestry(
    lookup: ProcessLookup = host_process_lookup,
    harness: Harness | None = None,
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
