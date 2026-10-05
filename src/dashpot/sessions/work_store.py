"""Persist and read each Agent Session's active Issue work at one Worktree."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

from ..core.errors import DashpotError
from ..core.model import Diagnostic, Harness
from ..core.pydantic import (
    FrozenDict,
    NonEmptyString,
    PersistedRecord,
    describe_validation_error,
)
from ..core.record_store import LockedRecordStore
from ..core.state_paths import project_state_directory
from ..core.timestamps import observed_instant
from ..core.worktree_paths import same_path
from .harnesses import HarnessName, HookSessionIdentity
from .processes import ProcessId, ProcessIdentity, ProcessKey
from .session_matching import SessionEvidence

WORK_STORE_VERSION = 2
SUPPORTED_WORK_STORE_VERSIONS = frozenset({1, WORK_STORE_VERSION})
SESSION_KEY = re.compile(r"^[A-Za-z0-9._-]+$")

BindingProvenance = Literal["explicit-reference", "explicit-identity"]


class SessionProcess(PersistedRecord):
    """The host process a Work Store record attributes its Agent Session to.

    ``pid_namespace`` is the PID namespace it was observed in, absent from a
    record written before it was kept, or where the host names none.
    """

    pid: ProcessId
    started_at: str
    pid_namespace: str | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_namespace(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        # The persisted shape omits ``pidNamespace`` rather than writing null.
        record: dict[str, Any] = handler(self)
        if self.pid_namespace is None:
            record.pop("pidNamespace", None)
        return record

    @classmethod
    def of(cls, identity: ProcessIdentity) -> SessionProcess:
        """Record an observed process, with the PID namespace it was observed in."""
        return cls(
            pid=identity.pid,
            started_at=identity.started_at,
            pid_namespace=identity.pid_namespace,
        )

    @property
    def key(self) -> ProcessKey:
        return self.pid, self.started_at


class RelocationIntentRecord(PersistedRecord):
    """The linked Worktree where an Agent Run is explicitly intended to resume."""

    target_worktree: NonEmptyString
    requested_at: NonEmptyString


class WorkerAssignmentRecord(PersistedRecord):
    """One Worker Assignment as its Lead's Work Store record persists it."""

    worker_id: HookSessionIdentity
    issue_id: NonEmptyString
    issue_reference: NonEmptyString
    worktree: NonEmptyString
    assigned_at: NonEmptyString


class WorkStoreRecord(PersistedRecord):
    """One Work Store record as persisted; the session key is its filename.

    Every object in it retains the fields a newer Dashpot wrote, and a rewrite
    carries them for as long as it carries that object (ADR 0013).
    """

    version: Literal[1, 2]
    harness: HarnessName
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
    relocation: RelocationIntentRecord | None = None
    # The Workers this run's Lead assigned to Issues (ADR 0096); a record
    # written before assignments existed carries none.
    workers: list[WorkerAssignmentRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _relocation_requires_version_two(self) -> Self:
        if self.version == 1 and self.relocation is not None:
            raise ValueError("Work Store version 1 cannot carry a relocation")
        return self

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
            relocation=(
                RelocationIntentRecord(
                    target_worktree=work.relocation.target_worktree,
                    requested_at=work.relocation.requested_at,
                ).carrying(work.relocation.retained)
                if work.relocation is not None
                else None
            ),
            workers=[
                WorkerAssignmentRecord(
                    worker_id=worker.worker_id,
                    issue_id=worker.issue_id,
                    issue_reference=worker.issue_reference,
                    worktree=worker.worktree,
                    assigned_at=worker.assigned_at,
                ).carrying(worker.retained)
                for worker in work.workers
            ],
        ).carrying(work.retained)

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
            relocation=(
                RelocationIntent(
                    target_worktree=self.relocation.target_worktree,
                    requested_at=self.relocation.requested_at,
                    retained=self.relocation.retained,
                )
                if self.relocation is not None
                else None
            ),
            workers=tuple(
                WorkerAssignment(
                    worker_id=worker.worker_id,
                    issue_id=worker.issue_id,
                    issue_reference=worker.issue_reference,
                    worktree=worker.worktree,
                    assigned_at=worker.assigned_at,
                    retained=worker.retained,
                )
                for worker in self.workers
            ),
            retained=self.retained,
        )


@dataclass(frozen=True, slots=True)
class RelocationIntent:
    """An explicit, not-yet-verified destination for one active Agent Run."""

    target_worktree: str
    requested_at: str
    # Fields a newer Dashpot wrote on this intent, carried while it is pending.
    retained: Mapping[str, object] = field(default_factory=FrozenDict, hash=False)


@dataclass(frozen=True, slots=True)
class WorkerAssignment:
    """A Worker of the run's session its Lead assigned to one Issue (ADR 0096).

    ``worker_id`` is the harness's own identity of the Sub-agent, the one its
    sub-agent hooks publish as ``agent_id``. ``worktree`` is where the Lead
    intends the Worker's commands to run: a declaration, never evidence
    that the Worker is there. The assignment says nothing about whether the
    Worker is working, which only its harness's hooks report.
    """

    worker_id: str
    issue_id: str
    issue_reference: str
    worktree: str
    assigned_at: str
    # Fields a newer Dashpot wrote on this assignment; a reassignment is a
    # new assignment and starts without them.
    retained: Mapping[str, object] = field(default_factory=FrozenDict, hash=False)


@dataclass(frozen=True, slots=True)
class ActiveWork:
    """One active Agent Run recorded at a Worktree's Work Store."""

    session_key: str
    harness: Harness
    session_label: str
    session_process: SessionProcess | None
    issue_id: str
    issue_reference: str
    binding_provenance: BindingProvenance
    started_at: str
    working_directory: str
    branch: str | None
    session_id: str | None = None
    relocation: RelocationIntent | None = None
    workers: tuple[WorkerAssignment, ...] = ()
    # The fields a newer Dashpot wrote on this run's record, carried through
    # every rewrite of the run; a new run starts without them.
    retained: Mapping[str, object] = field(default_factory=FrozenDict, hash=False)

    @property
    def evidence(self) -> SessionEvidence:
        """The session facts this run was recorded under, for matching."""
        return SessionEvidence(
            self.harness,
            self.session_id,
            self.session_process.key if self.session_process else None,
        )

    @property
    def run_id(self) -> str:
        return f"work:{self.harness}:{self.session_key}:{self.started_at}"


class WorkStoreError(DashpotError):
    """A Work Store write refused because another record occupies its destination."""


class WorkStore(LockedRecordStore):
    """Versioned, atomic, lock-serialized Issue work state for one Worktree."""

    def __init__(self, worktree: Path) -> None:
        super().__init__(
            project_state_directory(worktree) / "work",
            SESSION_KEY,
            "Work Store session key contains unsupported characters",
            checkout=worktree,
        )

    def start(self, work: ActiveWork) -> Path:
        """Create a run without replacing occupied or unreadable state."""
        with self.locked(work.session_key):
            current = self._active_record(work.session_key)
            if current is not None:
                if current == work:
                    return self.record_path(work.session_key)
                raise WorkStoreError(
                    "the destination is occupied; use conditional replacement"
                )
            self.replace(
                work.session_key, WorkStoreRecord.of(work).model_dump(by_alias=True)
            )
        return self.record_path(work.session_key)

    def stop_current(self, expected: ActiveWork) -> bool:
        """End a run only while its complete previously read state is current."""
        with self.locked(expected.session_key):
            if self._active_record(expected.session_key) != expected:
                return False
            self.record_path(expected.session_key).unlink()
            return True

    def replace_current(self, expected: ActiveWork, replacement: ActiveWork) -> bool:
        """Replace one run only while its previously read state is current."""
        if replacement.session_key != expected.session_key:
            raise ValueError("replacement must retain the Agent Run's session key")
        if (expected.harness, expected.session_id) != (
            replacement.harness,
            replacement.session_id,
        ):
            raise ValueError("replacement must retain the Agent Session Identity")
        with self.locked(expected.session_key):
            if self._active_record(expected.session_key) != expected:
                return False
            self.replace(
                replacement.session_key,
                WorkStoreRecord.of(replacement).model_dump(by_alias=True),
            )
            return True

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

    def complete_relocation(
        self,
        expected: ActiveWork,
        destination: WorkStore,
        relocated: ActiveWork,
        *,
        repairing: ActiveWork | None = None,
    ) -> bool:
        """Move one unchanged pending run to its verified destination.

        Both record locks are acquired in path order. The destination is
        written durably before the source is removed, so a crash between the
        two leaves the run at both. The destination must hold ``relocated``
        itself or, when given, exactly ``repairing``: the copy such a crash
        left there, which a retry from any process replaces with
        ``relocated`` before removing the source's copy. Without
        ``repairing`` it may also hold nothing.
        """
        if repairing is not None and repairing.run_id != expected.run_id:
            raise ValueError("a repaired copy must be the relocating Agent Run")
        if same_path(self.directory, destination.directory):
            return False
        stores = sorted(
            (self, destination),
            key=lambda store: str(store.lock_path(expected.session_key)),
        )
        with ExitStack() as stack:
            for store in stores:
                stack.enter_context(store.locked(expected.session_key))
            current = self._active_record(expected.session_key)
            if current != expected:
                return False
            existing = destination._active_record(expected.session_key)
            if existing != repairing and existing != relocated:
                return False
            if existing != relocated:
                destination.replace(
                    relocated.session_key,
                    WorkStoreRecord.of(relocated).model_dump(by_alias=True),
                )
            self.record_path(expected.session_key).unlink()
            return True

    @staticmethod
    def _parse(path: Path) -> ActiveWork:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("record is not an object")
        # A future version is a distinct, actionable condition, not a
        # malformed field, so it is reported before validation.
        if raw.get("version") not in SUPPORTED_WORK_STORE_VERSIONS:
            raise ValueError(f"unsupported Work Store version: {raw.get('version')!r}")
        session_key = path.stem
        if not SESSION_KEY.fullmatch(session_key):
            raise ValueError("record filename is not a valid session key")
        try:
            record = WorkStoreRecord.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(describe_validation_error(exc)) from exc
        return record.active_work(session_key)

    def _active_record(self, session_key: str) -> ActiveWork | None:
        try:
            return self._parse(self.record_path(session_key))
        except FileNotFoundError:
            return None


def end_session_runs(
    worktrees: Iterable[Path],
    harness: Harness,
    session_id: str,
    process_key: ProcessKey | None,
    *,
    ended_at: str | None = None,
) -> list[tuple[Path, ActiveWork]]:
    """End unchanged runs owned by the named session and ending Host Process."""
    ended: list[tuple[Path, ActiveWork]] = []
    for worktree, work in session_runs_to_end(
        worktrees, harness, session_id, process_key, ended_at=ended_at
    ):
        try:
            if WorkStore(worktree).stop_current(work):
                ended.append((worktree, work))
        except (OSError, ValueError):
            continue
    return ended


def session_runs_to_end(
    worktrees: Iterable[Path],
    harness: Harness,
    session_id: str,
    process_key: ProcessKey | None,
    *,
    ended_at: str | None = None,
) -> list[tuple[Path, ActiveWork]]:
    """The runs a ``SessionEnd`` of the named session and Host Process would end.

    A run is the session's when it carries the session's identity and records
    no process or the ending one. A run that started after the end, or a Codex
    run carrying a Relocation Intent (ADR 0029), is never one of them.
    """
    found: list[tuple[Path, ActiveWork]] = []
    identity = SessionEvidence(harness, session_id, process_key)
    for worktree in worktrees:
        try:
            active, _diagnostics = WorkStore(worktree).active()
        except OSError:
            continue
        for work in active:
            recorded = work.evidence
            if identity.match(recorded) != "same":
                continue
            if recorded.process_key is not None and recorded.process_key != process_key:
                continue
            if ended_at is not None and observed_instant(
                work.started_at
            ) > observed_instant(ended_at):
                continue
            if work.harness == "codex" and work.relocation is not None:
                continue
            found.append((worktree, work))
    return found
