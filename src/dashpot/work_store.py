from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .file_locks import locked_path
from .model import Diagnostic

WORK_STORE_VERSION = 1
SESSION_KEY = re.compile(r"^[A-Za-z0-9._-]+$")

BindingProvenance = Literal["explicit-reference", "explicit-identity"]


@dataclass(frozen=True, slots=True)
class SessionProcess:
    pid: int
    started_at: str

    def as_record(self) -> dict[str, Any]:
        return {"pid": self.pid, "startedAt": self.started_at}


@dataclass(frozen=True, slots=True)
class ActiveWork:
    """One active Agent Run recorded at a Worktree's Work Store."""

    session_key: str
    harness: str
    session_label: str
    session_process: SessionProcess | None
    issue_id: str
    issue_reference: str
    binding_provenance: BindingProvenance
    started_at: str
    working_directory: str
    branch: str | None

    @property
    def run_id(self) -> str:
        return f"work:{self.harness}:{self.session_key}:{self.started_at}"


class WorkStore:
    """Versioned, atomic, lock-serialized Issue work state for one Worktree."""

    def __init__(self, worktree: Path) -> None:
        self.directory = worktree / ".dashpot" / "state" / "work"

    def start(self, work: ActiveWork) -> Path:
        """Start or switch Issue work for one Agent Session."""
        destination = self._destination(work.session_key)
        record = {
            "version": WORK_STORE_VERSION,
            "harness": work.harness,
            "sessionLabel": work.session_label,
            "sessionProcess": (
                work.session_process.as_record() if work.session_process else None
            ),
            "issueId": work.issue_id,
            "issueReference": work.issue_reference,
            "bindingProvenance": work.binding_provenance,
            "startedAt": work.started_at,
            "workingDirectory": work.working_directory,
            "branch": work.branch,
        }
        with self._locked(work.session_key):
            self._replace(destination, record, work.session_key)
        return destination

    def stop(self, session_key: str) -> bool:
        """End the session's active Agent Run; the session itself stays alive.

        The record's lock file goes with it: a `start` queued behind this stop
        re-acquires on a fresh lock file rather than the unlinked one.
        """
        destination = self._destination(session_key)
        with self._locked(session_key):
            try:
                destination.unlink()
                stopped = True
            except FileNotFoundError:
                stopped = False
            self._lock_path(session_key).unlink(missing_ok=True)
            return stopped

    def active(self) -> tuple[list[ActiveWork], list[Diagnostic]]:
        """Read every active Agent Run, diagnosing malformed state."""
        if not self.directory.is_dir():
            return [], []
        work: list[ActiveWork] = []
        diagnostics: list[Diagnostic] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                work.append(self._parse(path))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                diagnostics.append(
                    Diagnostic(
                        f"work:{path}",
                        "warning",
                        f"Cannot read Work Store record {path}: {exc}",
                        "work-store-malformed",
                    )
                )
        return work, diagnostics

    def _destination(self, session_key: str) -> Path:
        if not SESSION_KEY.fullmatch(session_key):
            raise RuntimeError("Work Store session key contains unsupported characters")
        return self.directory / f"{session_key}.json"

    @staticmethod
    def _parse(path: Path) -> ActiveWork:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("record is not an object")
        if raw.get("version") != WORK_STORE_VERSION:
            raise ValueError(f"unsupported Work Store version: {raw.get('version')!r}")
        session_key = path.stem
        if not SESSION_KEY.fullmatch(session_key):
            raise ValueError("record filename is not a valid session key")
        harness = _required(raw, "harness")
        issue_id = _required(raw, "issueId")
        issue_reference = _required(raw, "issueReference")
        provenance = raw.get("bindingProvenance")
        if provenance not in ("explicit-reference", "explicit-identity"):
            raise ValueError(f"unsupported binding provenance: {provenance!r}")
        started_at = _required(raw, "startedAt")
        working_directory = _required(raw, "workingDirectory")
        session_label = _required(raw, "sessionLabel")
        branch = raw.get("branch")
        if branch is not None and not isinstance(branch, str):
            raise ValueError("branch must be a string or null")
        process = raw.get("sessionProcess")
        session_process = None
        if process is not None:
            if (
                not isinstance(process, dict)
                or not isinstance(process.get("pid"), int)
                or not isinstance(process.get("startedAt"), str)
            ):
                raise ValueError("sessionProcess needs pid and startedAt")
            session_process = SessionProcess(process["pid"], process["startedAt"])
        return ActiveWork(
            session_key=session_key,
            harness=harness,
            session_label=session_label,
            session_process=session_process,
            issue_id=issue_id,
            issue_reference=issue_reference,
            binding_provenance=provenance,
            started_at=started_at,
            working_directory=working_directory,
            branch=branch,
        )

    def _lock_path(self, session_key: str) -> Path:
        return self.directory / f".{session_key}.lock"

    @contextmanager
    def _locked(self, session_key: str) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with locked_path(self._lock_path(session_key)):
            yield

    def _replace(
        self, destination: Path, record: dict[str, Any], session_key: str
    ) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{session_key}.", dir=self.directory
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


def _required(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"record needs non-empty {key}")
    return value
