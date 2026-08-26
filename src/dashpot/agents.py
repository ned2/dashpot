from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .model import AgentRun, Diagnostic, Repository, RunState
from .repository import git, is_within


SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
ISSUE_REFERENCE = re.compile(r"^\S+$")
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
    issue_reference = environment.get("DASHPOT_ISSUE_REF") or None
    if issue_reference and not ISSUE_REFERENCE.fullmatch(issue_reference):
        raise RuntimeError("DASHPOT_ISSUE_REF must be a whitespace-free Issue Reference")
    try:
        repository_root = git(cwd, "rev-parse", "--show-toplevel", timeout=2)
        branch = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=2)
    except RuntimeError:
        repository_root = None
        branch = None
    return {
        "version": 1,
        "sessionId": session_id,
        "harness": "codex",
        "state": state,
        "cwd": str(cwd),
        "repositoryRoot": repository_root,
        "branch": branch,
        "declaredIssueReference": issue_reference,
        "event": event_name,
        "source": event.get("source"),
        "turnId": event.get("turn_id"),
        "model": event.get("model"),
        "lastActivityAt": now_iso(),
        "sessionProcess": process.as_record() if process else None,
    }


def write_hook_record(record: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    session_id = str(record["sessionId"])
    destination = directory / f"{session_id}.json"
    if record.get("declaredIssueReference") is None and destination.exists():
        try:
            previous: Any = json.loads(destination.read_text())
            if isinstance(previous, dict) and isinstance(
                previous.get("declaredIssueReference"), str
            ):
                record["declaredIssueReference"] = previous[
                    "declaredIssueReference"
                ]
        except (OSError, json.JSONDecodeError):
            pass
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{session_id}.", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


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
    repository: Repository,
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
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("unsupported record shape or version")
            run, diagnostic = record_to_run(raw, repository, lookup, namespace_isolated)
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
    repository: Repository,
    lookup: ProcessLookup,
    isolated: bool,
) -> tuple[AgentRun | None, Diagnostic | None]:
    session_id = optional_string(raw.get("sessionId"))
    event_state = optional_string(raw.get("state"))
    cwd = optional_string(raw.get("cwd"))
    if not session_id or not cwd:
        raise ValueError("record needs sessionId and cwd")
    if event_state == "ended":
        return None, None
    if event_state not in {"running", "waiting"}:
        raise ValueError(f"unsupported active state: {event_state!r}")
    if not belongs_to_repository(raw, cwd, repository):
        return None, None

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
    cwd_path = Path(cwd).resolve()
    worktree = next(
        (
            candidate
            for candidate in repository.worktrees
            if is_within(cwd_path, Path(candidate.path))
        ),
        None,
    )
    return (
        AgentRun(
            id=f"codex-session:{session_id}",
            harness="codex",
            process_or_session=f"{session_id} hook",
            state=state,
            repository_root=repository.root,
            worktree=worktree.path if worktree else None,
            branch=optional_string(raw.get("branch")) or (worktree.branch if worktree else None),
            declared_issue_reference=optional_string(
                raw.get("declaredIssueReference")
            ),
            working_directory=cwd,
            last_activity_at=optional_string(raw.get("lastActivityAt")),
        ),
        diagnostic,
    )


def belongs_to_repository(raw: dict[str, Any], cwd: str, repository: Repository) -> bool:
    repository_root = optional_string(raw.get("repositoryRoot"))
    if repository_root:
        return Path(repository_root).resolve() == Path(repository.root).resolve()
    return is_within(Path(cwd).resolve(), Path(repository.root).resolve())


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
