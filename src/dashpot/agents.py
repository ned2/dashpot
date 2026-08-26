from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence, cast

from .agent_bindings import IssueBindingPromotion
from .model import AgentRun, Diagnostic, ObservationTarget, RunState
from .repository import git, is_within


SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
ISSUE_VALUE = re.compile(r"^\S+$")
EVENT_STATES: dict[str, str] = {
    "SessionStart": "running",
    "UserPromptSubmit": "running",
    "PreToolUse": "running",
    "PostToolUse": "running",
    "Stop": "waiting",
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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def nearest_codex_process(lookup: ProcessLookup = process_info) -> ProcessIdentity | None:
    pid = os.getppid()
    seen: set[int] = set()
    for _ in range(12):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        info = lookup(pid)
        if info is None:
            break
        if is_codex_host_process(info):
            return info
        pid = info.parent_pid
    return None


def is_codex_host_process(process: ProcessIdentity) -> bool:
    name = Path(process.command).name.lower()
    arguments = (process.arguments or "").lower()
    if "codex-linux-sandbox" in arguments or "sandbox" in name:
        return False
    return name == "codex" or name.startswith("codex-")


def process_namespace_is_isolated() -> bool:
    try:
        return b"codex-linux-sandbox" in Path("/proc/1/cmdline").read_bytes()
    except OSError:
        return False


def build_hook_record(
    event: dict[str, Any],
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
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
        raise RuntimeError("DASHPOT_ISSUE_REF must be a whitespace-free Issue Reference")
    try:
        observed_target = git(cwd, "rev-parse", "--show-toplevel", timeout=2)
        branch = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=2)
    except RuntimeError:
        observed_target = None
        branch = None
    return {
        "version": 2,
        "sessionId": session_id,
        "harness": "codex",
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

    def promote(
        self, promotion: IssueBindingPromotion
    ) -> tuple[bool, Diagnostic | None]:
        prefix = "codex-session:"
        if not promotion.agent_run_id.startswith(prefix):
            return False, self._promotion_diagnostic(
                promotion,
                "Agent Run cannot be mapped to a hook session",
                "agent-issue-binding-conflict",
            )
        session_id = promotion.agent_run_id.removeprefix(prefix)
        if not SESSION_ID.fullmatch(session_id):
            return False, self._promotion_diagnostic(
                promotion,
                "Agent Run has an invalid hook session identifier",
                "agent-issue-binding-conflict",
            )
        destination = self.directory / f"{session_id}.json"
        try:
            with self._locked(session_id):
                current = self._read(destination)
                if current is None or current.get("version") != 2:
                    return False, self._promotion_diagnostic(
                        promotion,
                        "Hook record changed or disappeared before Issue binding",
                        "agent-issue-binding-race",
                    )
                current_issue_id = optional_string(current.get("issueId"))
                if current_issue_id == promotion.issue_id:
                    return True, None
                if current_issue_id is not None:
                    return False, self._promotion_diagnostic(
                        promotion,
                        "Agent Run is already bound to a different Issue Identity",
                        "agent-issue-binding-conflict",
                    )
                if not self._hint_is_current(current, promotion):
                    return False, self._promotion_diagnostic(
                        promotion,
                        "Issue hint changed before its binding could be persisted",
                        "agent-issue-binding-race",
                    )
                current["issueId"] = promotion.issue_id
                self._replace(destination, current, session_id)
                return True, None
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            return False, self._promotion_diagnostic(
                promotion,
                f"Cannot persist Issue binding: {exc}",
                "agent-issue-binding-race",
            )

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

    @staticmethod
    def _hint_is_current(
        record: dict[str, Any], promotion: IssueBindingPromotion
    ) -> bool:
        if record.get("lastActivityAt") != promotion.expected_last_activity_at:
            return False
        repository_root = optional_string(record.get("repositoryRoot"))
        if repository_root:
            target_is_current = (
                Path(repository_root).resolve()
                == Path(promotion.expected_observation_target).resolve()
            )
        else:
            cwd = optional_string(record.get("cwd"))
            target_is_current = bool(
                cwd
                and is_within(
                    Path(cwd).resolve(),
                    Path(promotion.expected_observation_target).resolve(),
                )
            )
        if not target_is_current:
            return False
        if promotion.hint_kind == "reference":
            return record.get("issueReferenceHint") == promotion.expected_hint
        return (
            record.get("issueReferenceHint") is None
            and record.get("branch") == promotion.expected_hint
        )

    @staticmethod
    def _promotion_diagnostic(
        promotion: IssueBindingPromotion, message: str, code: str
    ) -> Diagnostic:
        return Diagnostic(promotion.agent_run_id, "warning", message, code)


def publish_hook_event(
    event: dict[str, Any],
    directory: Path | None = None,
    environ: Mapping[str, str] | None = None,
    process: ProcessIdentity | None = None,
) -> Path:
    identity = process if process is not None else nearest_codex_process()
    return write_hook_record(
        build_hook_record(event, environ=environ, process=identity),
        directory or state_directory(),
    )


def observe_hook_runs(
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    directory: Path | None = None,
    lookup: ProcessLookup = process_info,
    isolated: bool | None = None,
) -> tuple[list[AgentRun], list[Diagnostic]]:
    root = directory or state_directory()
    if not root.exists():
        return [], []
    namespace_isolated = process_namespace_is_isolated() if isolated is None else isolated
    runs: list[AgentRun] = []
    diagnostics: list[Diagnostic] = []
    for path in sorted(root.glob("*.json")):
        try:
            raw: Any = json.loads(path.read_text())
            if not isinstance(raw, dict) or raw.get("version") != 2:
                raise ValueError("unsupported record shape or version")
            run, diagnostic = record_to_run(
                raw,
                targets_by_project,
                lookup,
                namespace_isolated,
                expected_session_id=path.stem,
            )
            if run:
                runs.append(run)
            if diagnostic:
                diagnostics.append(diagnostic)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            diagnostics.append(
                Diagnostic("dashpot-codex-hook", "warning", f"Cannot read {path}: {exc}")
            )
    return runs, diagnostics


def record_to_run(
    raw: dict[str, Any],
    targets_by_project: Mapping[str, Sequence[ObservationTarget]],
    lookup: ProcessLookup,
    isolated: bool,
    expected_session_id: str | None = None,
) -> tuple[AgentRun | None, Diagnostic | None]:
    session_id = optional_string(raw.get("sessionId"))
    event_state = optional_string(raw.get("state"))
    cwd = optional_string(raw.get("cwd"))
    if not session_id or not cwd:
        raise ValueError("record needs sessionId and cwd")
    if not SESSION_ID.fullmatch(session_id):
        raise ValueError("record sessionId contains unsupported characters")
    if expected_session_id is not None and session_id != expected_session_id:
        raise ValueError("record sessionId does not match its filename")
    issue_id = validated_optional_issue_value(raw.get("issueId"), "issueId")
    issue_reference_hint = validated_optional_issue_value(
        raw.get("issueReferenceHint"), "issueReferenceHint"
    )
    if event_state == "ended":
        return None, None
    if event_state not in {"running", "waiting"}:
        raise ValueError(f"unsupported active state: {event_state!r}")
    located, target_diagnostic = locate_observation_target(
        raw, cwd, targets_by_project
    )
    if target_diagnostic:
        return None, target_diagnostic
    if located is None:
        return None, None
    observation_project_id, target = located

    alive = process_is_same(raw.get("sessionProcess"), lookup, isolated)
    if alive is False:
        return None, Diagnostic(
            "dashpot-codex-hook",
            "warning",
            f"Ignoring orphaned Codex run {session_id}: its recorded process has exited",
        )
    state: RunState = cast(RunState, event_state) if alive is True else "unknown"
    diagnostic = None
    if alive is None:
        diagnostic = Diagnostic(
            "dashpot-codex-hook",
            "warning",
            f"Codex run {session_id} liveness is unknown: host process identity is unavailable",
        )
    return (
        AgentRun(
            id=f"codex-session:{session_id}",
            harness="codex",
            process_or_session=f"{session_id} hook",
            state=state,
            observation_target=target.path,
            observation_project_id=observation_project_id,
            branch=optional_string(raw.get("branch")) or target.branch,
            issue_id=issue_id,
            issue_reference_hint=issue_reference_hint,
            working_directory=cwd,
            last_activity_at=optional_string(raw.get("lastActivityAt")),
        ),
        diagnostic,
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
    cwd_target = max(
        cwd_matches, key=lambda item: len(item[1].path), default=None
    )
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
        return None, Diagnostic(
            "dashpot-codex-hook",
            "warning",
            f"Ignoring Codex run {session_id}: recorded Repository root and "
            "working directory resolve to different Observation Targets",
            "agent-target-mismatch",
        )
    return root_target, None


def process_is_same(
    expected: Any,
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


def require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"hook input needs non-empty {name}")
    return value


def optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def validated_optional_issue_value(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not ISSUE_VALUE.fullmatch(value):
        raise ValueError(f"record {name} must be a whitespace-free string or null")
    return value
