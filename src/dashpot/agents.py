from __future__ import annotations

import fcntl
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
from typing import Any, cast

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


ProcessLookup = Callable[[int], ProcessIdentity | None]


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


def process_info(pid: int) -> ProcessIdentity | None:
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
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    fields = result.stdout.strip().split(maxsplit=8)
    if result.returncode != 0 or len(fields) < 8:
        return None
    try:
        return ProcessIdentity(
            int(fields[0]),
            int(fields[1]),
            fields[2],
            " ".join(fields[3:8]),
            fields[8] if len(fields) == 9 else None,
        )
    except ValueError:
        return None


def nearest_codex_process(
    lookup: ProcessLookup = process_info,
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
    lookup: ProcessLookup = process_info,
) -> tuple[str, ProcessIdentity] | None:
    """Find the nearest enclosing supported harness process, if any."""
    pid = os.getppid()
    seen: set[int] = set()
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        info = lookup(pid)
        if info is None:
            break
        for harness, matches in HARNESS_HOSTS.items():
            if matches(info):
                return harness, info
        pid = info.parent_pid
    return None


def nearest_harness_process(
    harness: str, lookup: ProcessLookup = process_info
) -> ProcessIdentity | None:
    pid = os.getppid()
    seen: set[int] = set()
    matches = HARNESS_HOSTS[harness]
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        info = lookup(pid)
        if info is None:
            break
        if matches(info):
            return info
        pid = info.parent_pid
    return None


def process_namespace_is_isolated() -> bool:
    try:
        return b"codex-linux-sandbox" in Path("/proc/1/cmdline").read_bytes()
    except OSError:
        return False


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
    """Atomically publish hook events and promote stable Issue bindings."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, record: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        session_id = require_string(record.get("sessionId"), "sessionId")
        if not SESSION_ID.fullmatch(session_id):
            raise RuntimeError("hook sessionId contains unsupported characters")
        destination = self.directory / f"{session_id}.json"
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

    @contextmanager
    def _locked(self, session_id: str) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / f".{session_id}.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

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


ProcessKey = tuple[int, str]


@dataclass(frozen=True, slots=True)
class HookSessionObservation:
    run: AgentRun
    process_key: ProcessKey | None


def observe_agent_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = process_info,
    isolated: bool | None = None,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """Observe Work Store Agent Runs and unmatched hook Agent Sessions."""
    namespace_isolated = (
        process_namespace_is_isolated() if isolated is None else isolated
    )
    sessions, diagnostics = observe_hook_sessions(
        targets_by_project, directory, lookup, namespace_isolated
    )
    state_by_process: dict[ProcessKey, tuple[RunState, str | None]] = {
        session.process_key: (session.run.state, session.run.last_activity_at)
        for session in sessions
        if session.process_key is not None
    }
    work_runs, consumed, work_diagnostics = observe_work_runs(
        targets_by_project, lookup, namespace_isolated, state_by_process
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
    lookup: ProcessLookup,
    isolated: bool,
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
            active, store_diagnostics = WorkStore(Path(target.path)).active()
            diagnostics.extend(store_diagnostics)
            for work in active:
                process_key: ProcessKey | None = None
                if work.session_process is not None:
                    process_key = (
                        work.session_process.pid,
                        work.session_process.started_at,
                    )
                    alive = process_is_same(
                        work.session_process.as_record(), lookup, isolated
                    )
                    if alive is False:
                        diagnostics.append(
                            Diagnostic(
                                work.run_id,
                                "warning",
                                f"Ignoring orphaned Agent Run for "
                                f"{work.session_label}: its recorded process "
                                f"has exited",
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
    directory: Path | None = None,
    lookup: ProcessLookup = process_info,
    isolated: bool | None = None,
) -> tuple[list[HookSessionObservation], list[Diagnostic]]:
    namespace_isolated = (
        process_namespace_is_isolated() if isolated is None else isolated
    )
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
        for path in sorted(root.glob("*.json")):
            try:
                raw: Any = json.loads(path.read_text())
                if not isinstance(raw, dict) or raw.get("version") != 2:
                    raise ValueError("unsupported record shape or version")
                session, record_diagnostics = record_to_session(
                    raw,
                    targets_by_project,
                    lookup,
                    namespace_isolated,
                    expected_session_id=path.stem,
                )
                diagnostics.extend(record_diagnostics)
                if session is None:
                    continue
                previous = latest.get(session.run.id)
                if previous is None or (session.run.last_activity_at or "") >= (
                    previous.run.last_activity_at or ""
                ):
                    latest[session.run.id] = session
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                diagnostics.append(
                    Diagnostic(
                        "dashpot-codex-hook", "warning", f"Cannot read {path}: {exc}"
                    )
                )
    return list(latest.values()), diagnostics


def observe_hook_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = process_info,
    isolated: bool | None = None,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    sessions, diagnostics = observe_hook_sessions(
        targets_by_project, directory, lookup, isolated
    )
    return [session.run for session in sessions], diagnostics


def record_to_session(
    raw: dict[str, Any],
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    lookup: ProcessLookup,
    isolated: bool,
    expected_session_id: str | None = None,
) -> tuple[HookSessionObservation | None, list[Diagnostic]]:
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
    display = HARNESS_DISPLAY.get(harness)
    if display is None:
        raise ValueError(f"unsupported harness: {harness!r}")
    run_id = f"{harness}-session:{session_id}"
    if event_state == "ended":
        return None, []
    if event_state not in {"running", "waiting"}:
        raise ValueError(f"unsupported active state: {event_state!r}")
    diagnostics: list[Diagnostic] = []
    # The Work Store is the sole Issue-association authority; a global hook
    # record carrying a binding is rejected rather than silently combined.
    if raw.get("issueId") is not None or raw.get("issueReferenceHint") is not None:
        diagnostics.append(
            Diagnostic(
                run_id,
                "warning",
                f"Rejecting the global Issue binding recorded for {display} "
                f"session {session_id}: bindings are Project-local now; run "
                f"'dashpot work start' from the session instead",
                "agent-global-binding-rejected",
            )
        )
    located, target_diagnostic = locate_observation_target(raw, cwd, targets_by_project)
    if target_diagnostic:
        diagnostics.append(target_diagnostic)
        return None, diagnostics
    if located is None:
        return None, diagnostics
    observation_project_id, target = located

    alive = process_is_same(raw.get("sessionProcess"), lookup, isolated)
    if alive is False:
        diagnostics.append(
            Diagnostic(
                "dashpot-codex-hook",
                "warning",
                f"Ignoring orphaned {display} run {session_id}: its recorded process has exited",
            )
        )
        return None, diagnostics
    state: RunState = cast(RunState, event_state) if alive is True else "unknown"
    if alive is None:
        diagnostics.append(
            Diagnostic(
                "dashpot-codex-hook",
                "warning",
                f"{display} run {session_id} liveness is unknown: host process identity is unavailable",
            )
        )
    process_key: ProcessKey | None = None
    process = raw.get("sessionProcess")
    if isinstance(process, dict):
        pid = process.get("pid")
        started_at = process.get("startedAt")
        if isinstance(pid, int) and isinstance(started_at, str):
            process_key = (pid, started_at)
    return (
        HookSessionObservation(
            AgentRun(
                id=run_id,
                harness=harness,
                process_or_session=f"{session_id} hook",
                state=state,
                observation_target=target.path,
                observation_project_id=observation_project_id,
                branch=optional_string(raw.get("branch")) or target.branch,
                issue_id=None,
                issue_reference_hint=None,
                working_directory=cwd,
                last_activity_at=optional_string(raw.get("lastActivityAt")),
            ),
            process_key,
        ),
        diagnostics,
    )


def locate_observation_target(
    raw: dict[str, Any],
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
            "dashpot-codex-hook",
            "warning",
            f"Ignoring {display} run {session_id}: recorded Repository root "
            "and working directory resolve to different Observation Targets",
            "agent-target-mismatch",
        )
    return root_target, None


def process_is_same(
    expected: object,
    lookup: ProcessLookup = process_info,
    isolated: bool = False,
) -> bool | None:
    if not isinstance(expected, dict):
        return None
    pid = expected.get("pid")
    started_at = expected.get("startedAt")
    if not isinstance(pid, int) or not isinstance(started_at, str):
        return None
    actual = lookup(pid)
    if actual is None:
        return None if isolated else False
    return actual.started_at == started_at


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
