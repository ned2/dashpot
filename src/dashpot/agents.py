from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .file_locks import locked_path, prune_lock_file
from .model import AgentRun, Diagnostic, ObservationTarget, RunState
from .repository import git, is_within
from .work_store import WorkStore

SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
ISSUE_VALUE = re.compile(r"^\S+$")
EVENT_STATES: dict[str, str] = {
    "SessionStart": "running",
    "UserPromptSubmit": "running",
    "PreToolUse": "running",
    "PostToolUse": "running",
    "Stop": "waiting",
    "Interrupt": "waiting",
    "SessionEnd": "ended",
}
# Diagnostics about hook Agent Session records are harness-neutral.
SESSION_DIAGNOSTIC_SOURCE = "agent-sessions"


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

SessionLiveness = Literal["live", "gone", "unknown"]


@dataclass(frozen=True, slots=True)
class LivenessObservation:
    """Whether an Agent Session's recorded host process is live, gone, or unknown.

    Unknown means the process could not be observed; it is never evidence that
    the session ended.
    """

    liveness: SessionLiveness
    reason: str | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def state_directory() -> Path:
    override = os.environ.get("DASHPOT_STATE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "dashpot" / "runs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dashpot" / "runs"
    return Path.home() / ".local" / "state" / "dashpot" / "runs"


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
    try:
        result = subprocess.run(
            [
                "ps",
                "-p",
                str(pid),
                "-o",
                "pid=",
                "-o",
                "ppid=",
                "-o",
                "comm=",
                "-o",
                "lstart=",
                "-o",
                "args=",
            ],
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
    fields = result.stdout.strip().split(maxsplit=8)
    if len(fields) < 8:
        return ProcessUnobservable(pid, "ps-unparseable")
    try:
        identity = ProcessIdentity(
            int(fields[0]),
            int(fields[1]),
            fields[2],
            " ".join(fields[3:8]),
            fields[8] if len(fields) == 9 else None,
        )
    except ValueError:
        return ProcessUnobservable(pid, "ps-unparseable")
    return ProcessPresent(identity)


def nearest_codex_process(
    lookup: ProcessLookup = host_process_lookup,
) -> ProcessIdentity | None:
    return nearest_harness_process("codex", lookup)


def is_codex_host_process(process: ProcessIdentity) -> bool:
    name = Path(process.command).name.lower()
    arguments = (process.arguments or "").lower()
    if "codex-linux-sandbox" in arguments or "sandbox" in name:
        return False
    return name == "codex" or name.startswith("codex-")


def is_claude_code_host_process(process: ProcessIdentity) -> bool:
    return Path(process.command).name.lower() == "claude"


HARNESS_HOSTS: dict[str, Callable[[ProcessIdentity], bool]] = {
    "codex": is_codex_host_process,
    "claude-code": is_claude_code_host_process,
}

HARNESS_DISPLAY = {"codex": "Codex", "claude-code": "Claude Code"}


def nearest_agent_process(
    lookup: ProcessLookup = host_process_lookup,
) -> tuple[str, ProcessIdentity] | None:
    """Find the nearest enclosing supported harness process, if any."""
    pid = os.getppid()
    seen: set[int] = set()
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        observed = lookup(pid)
        if not isinstance(observed, ProcessPresent):
            break
        info = observed.identity
        for harness, matches in HARNESS_HOSTS.items():
            if matches(info):
                return harness, info
        pid = info.parent_pid
    return None


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


def process_namespace_is_isolated() -> bool:
    try:
        return b"codex-linux-sandbox" in Path("/proc/1/cmdline").read_bytes()
    except OSError:
        return False


def process_key_of(expected: object) -> ProcessKey | None:
    """The recorded PID and start time of a session process record, if any."""
    if not isinstance(expected, dict):
        return None
    pid = expected.get("pid")
    started_at = expected.get("startedAt")
    if not isinstance(pid, int) or not isinstance(started_at, str):
        return None
    return pid, started_at


def session_liveness(
    expected: object, lookup: ProcessLookup = host_process_lookup
) -> LivenessObservation:
    """Derive Session Liveness from a recorded process identity.

    A PID that is absent or reused by a process with a different start time is
    gone; an unobservable process is unknown, with the adapter's reason.
    """
    key = process_key_of(expected)
    if key is None:
        return LivenessObservation("unknown", "no recorded process identity")
    pid, started_at = key
    observed = lookup(pid)
    if isinstance(observed, ProcessAbsent):
        return LivenessObservation("gone")
    if isinstance(observed, ProcessUnobservable):
        return LivenessObservation("unknown", observed.reason)
    if observed.identity.started_at != started_at:
        return LivenessObservation("gone")
    return LivenessObservation("live")


class _LivenessProbe:
    """Memoize Session Liveness per process identity for one observation pass.

    The hook Agent Session pass and the Work Store pass then probe each
    recorded process once and always agree about it.
    """

    def __init__(self, lookup: ProcessLookup) -> None:
        self._lookup = lookup
        self._observed: dict[ProcessKey, LivenessObservation] = {}

    def observe(self, expected: object) -> LivenessObservation:
        key = process_key_of(expected)
        if key is None:
            return session_liveness(expected, self._lookup)
        observation = self._observed.get(key)
        if observation is None:
            observation = session_liveness(expected, self._lookup)
            self._observed[key] = observation
        return observation


def build_hook_record(
    event: dict[str, Any],
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
    harness: str = "codex",
) -> dict[str, Any]:
    session_id = require_string(event.get("session_id"), "session_id")
    if not SESSION_ID.fullmatch(session_id):
        raise RuntimeError("hook session_id contains unsupported characters")
    event_name = require_string(event.get("hook_event_name"), "hook_event_name")
    state = EVENT_STATES.get(event_name)
    if state is None:
        raise RuntimeError(f"unsupported hook event: {event_name}")
    cwd = Path(require_string(event.get("cwd"), "cwd")).expanduser().resolve()
    environment = environ if environ is not None else os.environ
    issue_id = environment.get("DASHPOT_ISSUE_ID") or None
    issue_reference = environment.get("DASHPOT_ISSUE_REF") or None
    if issue_id and not ISSUE_VALUE.fullmatch(issue_id):
        raise RuntimeError("DASHPOT_ISSUE_ID must be a whitespace-free Issue Identity")
    if issue_reference and not ISSUE_VALUE.fullmatch(issue_reference):
        raise RuntimeError(
            "DASHPOT_ISSUE_REF must be a whitespace-free Issue Reference"
        )
    try:
        observed_target = git(cwd, "rev-parse", "--show-toplevel", timeout=2)
        branch = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=2)
    except RuntimeError:
        observed_target = None
        branch = None
    return {
        "version": 2,
        "sessionId": session_id,
        "harness": harness,
        "state": state,
        "cwd": str(cwd),
        "repositoryRoot": observed_target,
        "branch": branch,
        "issueId": issue_id,
        "issueReferenceHint": issue_reference,
        "event": event_name,
        "source": event.get("source"),
        "turnId": event.get("turn_id"),
        "model": event.get("model"),
        "lastActivityAt": now_iso(),
        "sessionProcess": process.as_record() if process else None,
    }


def write_hook_record(record: dict[str, Any], directory: Path) -> Path:
    return HookRecordStore(directory).write(record)


class HookRecordStore:
    """Own the lifecycle of hook Agent Session records in one directory.

    Events are published atomically, stable Issue bindings are promoted, a
    graceful ``SessionEnd`` removes the session's record, and confirmed stale
    records can be pruned without racing a concurrent hook write.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, record: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        session_id = require_string(record.get("sessionId"), "sessionId")
        if not SESSION_ID.fullmatch(session_id):
            raise RuntimeError("hook sessionId contains unsupported characters")
        destination = self.directory / f"{session_id}.json"
        if record.get("state") == "ended":
            # A graceful SessionEnd ends the Agent Session; a tombstone would
            # only be an active-looking record that observers have to skip.
            with self._locked(session_id):
                destination.unlink(missing_ok=True)
            return destination
        current = dict(record)
        try:
            current_issue_id = validated_optional_issue_value(
                current.get("issueId"), "issueId"
            )
            current_issue_hint = validated_optional_issue_value(
                current.get("issueReferenceHint"), "issueReferenceHint"
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        current["issueId"] = current_issue_id
        current["issueReferenceHint"] = current_issue_hint
        with self._locked(session_id):
            previous = self._read(destination)
            if previous is not None:
                try:
                    previous_issue_id = validated_optional_issue_value(
                        previous.get("issueId"), "issueId"
                    )
                    previous_issue_hint = validated_optional_issue_value(
                        previous.get("issueReferenceHint"), "issueReferenceHint"
                    )
                except ValueError as exc:
                    raise RuntimeError(str(exc)) from exc
                if (
                    previous_issue_id
                    and current_issue_id
                    and previous_issue_id != current_issue_id
                ):
                    raise RuntimeError(
                        "an Agent Run cannot be rebound to a different Issue Identity"
                    )
                if current_issue_id is None:
                    current["issueId"] = previous_issue_id
                if current_issue_hint is None:
                    current["issueReferenceHint"] = previous_issue_hint
            self._replace(destination, current, session_id)
        return destination

    def prune(self, session_id: str, observed: Mapping[str, Any]) -> bool:
        """Delete a stale record only if it still equals ``observed``.

        The conditional re-read under the session's lock means a record that a
        hook updated between observation and cleanup is kept. The lock file
        is left for ``prune_lock`` to reclaim on a later pass. Returns whether
        the record was removed.
        """
        destination = self._record_path(session_id)
        with self._locked(session_id):
            try:
                current = self._read(destination)
            except (RuntimeError, ValueError):
                return False
            if current is None or current != dict(observed):
                return False
            destination.unlink(missing_ok=True)
            return True

    def prune_lock(self, session_id: str) -> bool:
        """Delete the session's lock file once no record remains behind it.

        A record is absent only when the session ended gracefully, was pruned
        as gone, or has not published yet; the last case holds the lock while
        it writes, so the pruner waits for it and then finds the record.
        Returns whether the lock file was removed.
        """
        return prune_lock_file(
            self._lock_path(session_id), self._record_path(session_id)
        )

    def orphaned_locks(self) -> list[str]:
        """Session ids of lock files in this store that guard no record."""
        if not self.directory.is_dir():
            return []
        orphaned: list[str] = []
        for path in sorted(self.directory.glob(".*.lock")):
            session_id = path.name[1 : -len(".lock")]
            if not SESSION_ID.fullmatch(session_id):
                continue
            if not self._record_path(session_id).exists():
                orphaned.append(session_id)
        return orphaned

    def _record_path(self, session_id: str) -> Path:
        if not SESSION_ID.fullmatch(session_id):
            raise RuntimeError("hook sessionId contains unsupported characters")
        return self.directory / f"{session_id}.json"

    def _lock_path(self, session_id: str) -> Path:
        return self.directory / f".{session_id}.lock"

    @contextmanager
    def _locked(self, session_id: str) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with locked_path(self._lock_path(session_id)):
            yield

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            raw: Any = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            raise RuntimeError(f"hook record is not an object: {path}")
        return raw

    def _replace(
        self, destination: Path, record: dict[str, Any], session_id: str
    ) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{session_id}.", dir=self.directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(record, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def session_directory(worktree: Path) -> Path:
    """The Project-local session record store beneath one Worktree."""
    return worktree / ".dashpot" / "state" / "sessions"


def route_record_directory(record: Mapping[str, Any]) -> Path:
    """Choose the Project-local store for a configured checkout, else global."""
    root = optional_string(record.get("repositoryRoot"))
    if root and (Path(root) / ".dashpot" / "config.json").is_file():
        return session_directory(Path(root))
    return state_directory()


def publish_hook_event(
    event: dict[str, Any],
    directory: Path | None = None,
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
    harness: str = "codex",
) -> Path:
    identity = process if process is not None else nearest_harness_process(harness)
    record = build_hook_record(
        event, environ=environ, process=identity, harness=harness
    )
    return write_hook_record(record, directory or route_record_directory(record))


HookRecordOutcome = Literal["ended", "live", "unknown", "gone"]


@dataclass(frozen=True, slots=True)
class HookRecordClassification:
    """One validated hook Agent Session record and its reconciled outcome."""

    session_id: str
    harness: str
    state: str
    cwd: str
    branch: str | None
    event: str | None
    last_activity_at: str | None
    process_key: ProcessKey | None
    outcome: HookRecordOutcome
    reason: str | None = None

    @property
    def display(self) -> str:
        return HARNESS_DISPLAY[self.harness]

    @property
    def run_id(self) -> str:
        return f"{self.harness}-session:{self.session_id}"


@dataclass(frozen=True, slots=True)
class HookSessionObservation:
    run: AgentRun
    process_key: ProcessKey | None
    liveness: LivenessObservation


@dataclass(frozen=True, slots=True)
class StaleSessionRecord:
    """A hook record whose Agent Session is over: gone, or ended gracefully."""

    session_id: str
    harness: str
    event: str | None
    last_activity_at: str | None
    pid: int | None
    outcome: Literal["gone", "ended"]


@dataclass(frozen=True, slots=True)
class SessionRecordSummary:
    """Point-in-time classification of every hook record in one store."""

    directory: Path
    live: int
    unknown: int
    unknown_reasons: tuple[tuple[str, int], ...]
    stale: tuple[StaleSessionRecord, ...]
    unreadable: int

    @property
    def total(self) -> int:
        return self.live + self.unknown + len(self.stale) + self.unreadable


def observe_agent_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Observe Work Store Agent Runs and unmatched hook Agent Sessions.

    This is the only place Session Liveness becomes an outcome. Callers
    receive active runs plus actionable diagnostics: a gone session with an
    Issue Binding is an Orphaned Agent Run and is reported once; a gone
    unbound session is stale observation state and is dropped silently.
    """
    probe = _LivenessProbe(lookup)
    sessions, diagnostics = observe_hook_sessions(targets_by_project, directory, probe)
    state_by_process: dict[ProcessKey, tuple[RunState, str | None]] = {
        session.process_key: (session.run.state, session.run.last_activity_at)
        for session in sessions
        if session.process_key is not None
    }
    work_runs, consumed, work_diagnostics = observe_work_runs(
        targets_by_project, probe, state_by_process
    )
    diagnostics.extend(work_diagnostics)
    runs = list(work_runs)
    runs.extend(
        session.run
        for session in sessions
        if session.process_key is None or session.process_key not in consumed
    )
    return runs, diagnostics


def observe_work_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    probe: _LivenessProbe,
    state_by_process: Mapping[ProcessKey, tuple[RunState, str | None]],
) -> tuple[list[AgentRun], set[ProcessKey], list[Diagnostic]]:
    """Turn each Worktree's active Work Store records into bound Agent Runs."""
    runs: list[AgentRun] = []
    consumed: set[ProcessKey] = set()
    diagnostics: list[Diagnostic] = []
    sessions_seen: dict[ProcessKey, str] = {}
    for project_id, targets in sorted(targets_by_project.items()):
        for target in targets:
            if target.availability != "available":
                continue
            store = WorkStore(Path(target.path))
            active, store_diagnostics = store.active()
            diagnostics.extend(store_diagnostics)
            # Runs stopped before their lock files were reclaimed leave
            # orphaned locks behind; sweep those that guard nothing.
            for session_key in store.orphaned_locks():
                with contextlib.suppress(OSError):
                    store.prune_lock(session_key)
            for work in active:
                process_key: ProcessKey | None = None
                if work.session_process is not None:
                    process_key = (
                        work.session_process.pid,
                        work.session_process.started_at,
                    )
                    liveness = probe.observe(work.session_process.as_record())
                    if liveness.liveness == "gone":
                        diagnostics.append(
                            Diagnostic(
                                work.run_id,
                                "warning",
                                f"{work.session_label} is gone but still "
                                f"records Issue work on "
                                f"{work.issue_reference} ({work.issue_id}) at "
                                f"{target.path}; run 'dashpot work stop "
                                f"--session {work.session_key}' at that "
                                f"Worktree to end the orphaned Agent Run",
                                "work-session-orphaned",
                            )
                        )
                        continue
                    if process_key in sessions_seen:
                        diagnostics.append(
                            Diagnostic(
                                work.run_id,
                                "warning",
                                f"{work.session_label} has Issue work recorded "
                                f"at more than one Worktree; each recorded run "
                                f"is listed",
                                "work-session-conflict",
                            )
                        )
                    sessions_seen[process_key] = work.run_id
                observed = (
                    state_by_process.get(process_key)
                    if process_key is not None
                    else None
                )
                if observed is not None:
                    state, last_activity_at = observed
                else:
                    state, last_activity_at = "unknown", None
                if process_key is not None:
                    consumed.add(process_key)
                runs.append(
                    AgentRun(
                        id=work.run_id,
                        harness=work.harness,
                        process_or_session=work.session_label,
                        state=state,
                        observation_target=target.path,
                        observation_project_id=project_id,
                        branch=work.branch or target.branch,
                        issue_id=work.issue_id,
                        issue_reference_hint=work.issue_reference,
                        working_directory=work.working_directory,
                        last_activity_at=last_activity_at or work.started_at,
                    )
                )
    return runs, consumed, diagnostics


def observe_hook_sessions(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None,
    probe: _LivenessProbe,
) -> tuple[list[HookSessionObservation], list[Diagnostic]]:
    """Read every visible hook store into live and unknown Agent Sessions.

    Ended and gone records are stale observation state: they are pruned and
    never reported here. Pruning is the only write observation performs, and
    it is conditional so a concurrently updated record survives.
    """
    directories: list[Path] = [directory or state_directory()]
    for _project_id, targets in sorted(targets_by_project.items()):
        for target in targets:
            if target.availability == "available":
                directories.append(session_directory(Path(target.path)))
    # A session's record may exist both globally and Project-locally around
    # an integration upgrade; the freshest observation per session wins.
    latest: dict[str, HookSessionObservation] = {}
    diagnostics: list[Diagnostic] = []
    seen_directories: set[Path] = set()
    for candidate in directories:
        root = candidate.resolve()
        if root in seen_directories or not root.exists():
            continue
        seen_directories.add(root)
        store = HookRecordStore(root)
        for path in sorted(root.glob("*.json")):
            try:
                raw = read_hook_record(path)
                record = classify_hook_record(raw, probe, expected_session_id=path.stem)
            except (OSError, ValueError) as exc:
                diagnostics.append(
                    Diagnostic(
                        SESSION_DIAGNOSTIC_SOURCE,
                        "warning",
                        f"Cannot read {path}: {exc}",
                    )
                )
                continue
            if record.outcome in {"ended", "gone"}:
                # A gone session's Issue work, if any, is reported by the
                # Work Store pass; cleanup failures are not observations.
                with contextlib.suppress(OSError):
                    store.prune(record.session_id, raw)
                continue
            session, record_diagnostics = record_to_session(
                record, raw, targets_by_project
            )
            diagnostics.extend(record_diagnostics)
            if session is None:
                continue
            previous = latest.get(session.run.id)
            if previous is None or (session.run.last_activity_at or "") >= (
                previous.run.last_activity_at or ""
            ):
                latest[session.run.id] = session
        # Records pruned above, or ended gracefully, leave their lock files
        # behind; reclaim those that guard nothing.
        for session_id in store.orphaned_locks():
            with contextlib.suppress(OSError):
                store.prune_lock(session_id)
    unknown_by_reason: dict[str, int] = {}
    for session in latest.values():
        if session.liveness.liveness == "unknown":
            reason = session.liveness.reason or "host process identity is unavailable"
            unknown_by_reason[reason] = unknown_by_reason.get(reason, 0) + 1
    diagnostics.extend(
        Diagnostic(
            SESSION_DIAGNOSTIC_SOURCE,
            "info",
            f"Liveness of {count} Agent Session(s) is unknown: {reason}",
            "agent-session-liveness-unknown",
        )
        for reason, count in sorted(unknown_by_reason.items())
    )
    return list(latest.values()), diagnostics


def read_hook_record(path: Path) -> dict[str, Any]:
    """Load one version-2 hook record, raising ``ValueError`` otherwise."""
    raw: Any = json.loads(path.read_text())
    if not isinstance(raw, dict) or raw.get("version") != 2:
        raise ValueError("unsupported record shape or version")
    return raw


def classify_hook_record(
    raw: Mapping[str, Any],
    probe: _LivenessProbe,
    expected_session_id: str | None = None,
) -> HookRecordClassification:
    """Validate one hook record and derive its lifecycle outcome.

    Independent of Observation Targets, so integration status can classify a
    store's records without an observation scope. Raises ``ValueError`` for
    records Dashpot cannot interpret.
    """
    session_id = optional_string(raw.get("sessionId"))
    event_state = optional_string(raw.get("state"))
    cwd = optional_string(raw.get("cwd"))
    if not session_id or not cwd:
        raise ValueError("record needs sessionId and cwd")
    if not SESSION_ID.fullmatch(session_id):
        raise ValueError("record sessionId contains unsupported characters")
    if expected_session_id is not None and session_id != expected_session_id:
        raise ValueError("record sessionId does not match its filename")
    harness = optional_string(raw.get("harness")) or "codex"
    if harness not in HARNESS_DISPLAY:
        raise ValueError(f"unsupported harness: {harness!r}")
    if event_state == "ended":
        liveness = LivenessObservation("unknown")
        outcome: HookRecordOutcome = "ended"
    elif event_state in {"running", "waiting"}:
        liveness = probe.observe(raw.get("sessionProcess"))
        outcome = liveness.liveness
    else:
        raise ValueError(f"unsupported active state: {event_state!r}")
    return HookRecordClassification(
        session_id=session_id,
        harness=harness,
        state=event_state,
        cwd=cwd,
        branch=optional_string(raw.get("branch")),
        event=optional_string(raw.get("event")),
        last_activity_at=optional_string(raw.get("lastActivityAt")),
        process_key=process_key_of(raw.get("sessionProcess")),
        outcome=outcome,
        reason=liveness.reason,
    )


def record_to_session(
    record: HookRecordClassification,
    raw: Mapping[str, Any],
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[HookSessionObservation | None, list[Diagnostic]]:
    """Place a live or unknown Agent Session at its Observation Target."""
    diagnostics: list[Diagnostic] = []
    # The Work Store is the sole Issue-association authority; a global hook
    # record carrying a binding is rejected rather than silently combined.
    if raw.get("issueId") is not None or raw.get("issueReferenceHint") is not None:
        diagnostics.append(
            Diagnostic(
                record.run_id,
                "warning",
                f"Rejecting the global Issue binding recorded for "
                f"{record.display} session {record.session_id}: bindings are "
                f"Project-local now; run 'dashpot work start' from the "
                f"session instead",
                "agent-global-binding-rejected",
            )
        )
    located, target_diagnostic = locate_observation_target(
        raw, record.cwd, targets_by_project
    )
    if target_diagnostic:
        diagnostics.append(target_diagnostic)
        return None, diagnostics
    if located is None:
        return None, diagnostics
    observation_project_id, target = located
    state: RunState = (
        cast(RunState, record.state) if record.outcome == "live" else "unknown"
    )
    return (
        HookSessionObservation(
            AgentRun(
                id=record.run_id,
                harness=record.harness,
                process_or_session=f"{record.session_id} hook",
                state=state,
                observation_target=target.path,
                observation_project_id=observation_project_id,
                branch=record.branch or target.branch,
                issue_id=None,
                issue_reference_hint=None,
                working_directory=record.cwd,
                last_activity_at=record.last_activity_at,
            ),
            record.process_key,
            LivenessObservation(
                "live" if record.outcome == "live" else "unknown", record.reason
            ),
        ),
        diagnostics,
    )


def summarize_session_records(
    directory: Path, lookup: ProcessLookup = host_process_lookup
) -> SessionRecordSummary:
    """Classify one hook store's records for troubleshooting, without pruning."""
    probe = _LivenessProbe(lookup)
    live = unknown = unreadable = 0
    unknown_by_reason: dict[str, int] = {}
    stale: list[StaleSessionRecord] = []
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in paths:
        try:
            raw = read_hook_record(path)
            record = classify_hook_record(raw, probe, expected_session_id=path.stem)
        except (OSError, ValueError):
            unreadable += 1
            continue
        if record.outcome == "live":
            live += 1
        elif record.outcome == "unknown":
            unknown += 1
            reason = record.reason or "host process identity is unavailable"
            unknown_by_reason[reason] = unknown_by_reason.get(reason, 0) + 1
        else:
            stale.append(
                StaleSessionRecord(
                    session_id=record.session_id,
                    harness=record.harness,
                    event=record.event,
                    last_activity_at=record.last_activity_at,
                    pid=record.process_key[0] if record.process_key else None,
                    outcome="gone" if record.outcome == "gone" else "ended",
                )
            )
    return SessionRecordSummary(
        directory=directory,
        live=live,
        unknown=unknown,
        unknown_reasons=tuple(sorted(unknown_by_reason.items())),
        stale=tuple(stale),
        unreadable=unreadable,
    )


def locate_observation_target(
    raw: Mapping[str, Any],
    cwd: str,
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
) -> tuple[tuple[str, ObservationTarget] | None, Diagnostic | None]:
    available = [
        (project_id, target)
        for project_id, targets in targets_by_project.items()
        for target in targets
        if target.availability == "available"
    ]
    cwd_path = Path(cwd).resolve()
    cwd_matches = [
        (project_id, target)
        for project_id, target in available
        if is_within(cwd_path, Path(target.path).resolve())
    ]
    cwd_target = max(cwd_matches, key=lambda item: len(item[1].path), default=None)
    repository_root = optional_string(raw.get("repositoryRoot"))
    if not repository_root:
        return cwd_target, None
    root_path = Path(repository_root).resolve()
    root_target = next(
        (
            (project_id, target)
            for project_id, target in available
            if Path(target.path).resolve() == root_path
        ),
        None,
    )
    if root_target is None:
        return None, None
    if cwd_target is None or cwd_target[1].path != root_target[1].path:
        session_id = optional_string(raw.get("sessionId")) or "unknown"
        display = HARNESS_DISPLAY.get(
            optional_string(raw.get("harness")) or "codex", "agent"
        )
        return None, Diagnostic(
            SESSION_DIAGNOSTIC_SOURCE,
            "warning",
            f"Ignoring {display} session {session_id}: recorded Repository root "
            "and working directory resolve to different Observation Targets",
            "agent-target-mismatch",
        )
    return root_target, None


def require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"hook input needs non-empty {name}")
    return value


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def validated_optional_issue_value(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not ISSUE_VALUE.fullmatch(value):
        raise ValueError(f"record {name} must be a whitespace-free string or null")
    return value
