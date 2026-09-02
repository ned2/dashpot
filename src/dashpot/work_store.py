"""Persist and read each Agent Session's active Issue work at one Worktree."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, ValidationError

from .harnesses import SESSION_ID
from .model import Diagnostic
from .models import (
    NonEmptyString,
    PersistedRecord,
    PublishedModel,
    describe_validation_error,
)
from .processes import ProcessKey
from .record_store import LockedRecordStore

WORK_STORE_VERSION = 1
SESSION_KEY = re.compile(r"^[A-Za-z0-9._-]+$")

BindingProvenance = Literal["explicit-reference", "explicit-identity"]


def _hook_session_identity(value: str) -> str:
    if not SESSION_ID.fullmatch(value):
        raise ValueError("must be a hook session identity or null")
    return value


HookSessionIdentity = Annotated[str, AfterValidator(_hook_session_identity)]


class SessionProcess(PublishedModel):
    """The host process a Work Store record attributes its Agent Session to."""

    pid: int
    started_at: str

    @property
    def key(self) -> ProcessKey:
        return self.pid, self.started_at


class WorkStoreRecord(PersistedRecord):
    """One Work Store record as persisted; the session key is its filename."""

    version: Literal[1]
    harness: NonEmptyString
    session_label: NonEmptyString
    session_process: SessionProcess | None
    issue_id: NonEmptyString
    issue_reference: NonEmptyString
    binding_provenance: BindingProvenance
    started_at: NonEmptyString
    working_directory: NonEmptyString
    branch: str | None
    # The harness's own Agent Session Identity, as its lifecycle hooks publish
    # it, when opt-in could confirm one; records written before it was
    # recorded, or without a hook record to confirm it, carry ``None``.
    session_id: HookSessionIdentity | None = None

    @classmethod
    def of(cls, work: ActiveWork) -> WorkStoreRecord:
        return cls(
            version=WORK_STORE_VERSION,
            harness=work.harness,
            session_label=work.session_label,
            session_process=work.session_process,
            issue_id=work.issue_id,
            issue_reference=work.issue_reference,
            binding_provenance=work.binding_provenance,
            started_at=work.started_at,
            working_directory=work.working_directory,
            branch=work.branch,
            session_id=work.session_id,
        )

    def active_work(self, session_key: str) -> ActiveWork:
        return ActiveWork(
            session_key=session_key,
            harness=self.harness,
            session_label=self.session_label,
            session_process=self.session_process,
            issue_id=self.issue_id,
            issue_reference=self.issue_reference,
            binding_provenance=self.binding_provenance,
            started_at=self.started_at,
            working_directory=self.working_directory,
            branch=self.branch,
            session_id=self.session_id,
        )


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
    session_id: str | None = None

    @property
    def run_id(self) -> str:
        return f"work:{self.harness}:{self.session_key}:{self.started_at}"


class WorkStore(LockedRecordStore):
    """Versioned, atomic, lock-serialized Issue work state for one Worktree."""

    def __init__(self, worktree: Path) -> None:
        super().__init__(
            worktree / ".dashpot" / "state" / "work",
            SESSION_KEY,
            "Work Store session key contains unsupported characters",
        )

    def start(self, work: ActiveWork) -> Path:
        """Start or switch Issue work for one Agent Session."""
        destination = self.record_path(work.session_key)
        record = WorkStoreRecord.of(work).model_dump(by_alias=True)
        with self.locked(work.session_key):
            self.replace(work.session_key, record)
        return destination

    def stop(self, session_key: str) -> bool:
        """End the session's active Agent Run; the session itself stays alive.

        The record's lock file goes with it: a `start` queued behind this stop
        re-acquires on a fresh lock file rather than the unlinked one.
        """
        destination = self.record_path(session_key)
        with self.locked(session_key):
            try:
                destination.unlink()
                stopped = True
            except FileNotFoundError:
                stopped = False
            self.lock_path(session_key).unlink(missing_ok=True)
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
                        source=f"work:{path}",
                        severity="warning",
                        message=f"Cannot read Work Store record {path}: {exc}",
                        code="work-store-malformed",
                    )
                )
        return work, diagnostics

    @staticmethod
    def _parse(path: Path) -> ActiveWork:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("record is not an object")
        # A future version is a distinct, actionable condition, not a
        # malformed field, so it is reported before validation.
        if raw.get("version") != WORK_STORE_VERSION:
            raise ValueError(f"unsupported Work Store version: {raw.get('version')!r}")
        session_key = path.stem
        if not SESSION_KEY.fullmatch(session_key):
            raise ValueError("record filename is not a valid session key")
        try:
            record = WorkStoreRecord.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(describe_validation_error(exc)) from exc
        return record.active_work(session_key)
