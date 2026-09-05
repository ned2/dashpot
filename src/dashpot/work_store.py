"""Persist and read each Agent Session's active Issue work at one Worktree."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, ValidationError, model_validator

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

WORK_STORE_VERSION = 2
SUPPORTED_WORK_STORE_VERSIONS = frozenset({1, WORK_STORE_VERSION})
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


class RelocationIntentRecord(PublishedModel):
    """The linked Worktree where an Agent Run is explicitly intended to resume."""

    target_worktree: NonEmptyString
    requested_at: NonEmptyString


class WorkStoreRecord(PersistedRecord):
    """One Work Store record as persisted; the session key is its filename."""

    version: Literal[1, 2]
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
    relocation: RelocationIntentRecord | None = None

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
                )
                if work.relocation is not None
                else None
            ),
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
            relocation=(
                RelocationIntent(
                    target_worktree=self.relocation.target_worktree,
                    requested_at=self.relocation.requested_at,
                )
                if self.relocation is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class RelocationIntent:
    """An explicit, not-yet-verified destination for one active Agent Run."""

    target_worktree: str
    requested_at: str


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
    relocation: RelocationIntent | None = None

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

    def replace_current(self, expected: ActiveWork, replacement: ActiveWork) -> bool:
        """Replace one run only while its previously read state is current."""
        if replacement.session_key != expected.session_key:
            raise ValueError("replacement must retain the Agent Run's session key")
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
    ) -> bool:
        """Move one unchanged pending run to its verified destination.

        Both record locks are acquired in path order. The destination is
        written durably before the source is removed, and a retry repairs the
        narrow crash window where both contain the same relocated run.
        """
        if self.directory.resolve() == destination.directory.resolve():
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
            if existing is not None and existing != relocated:
                return False
            if existing is None:
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
    harness: str,
    session_id: str,
    process_key: ProcessKey | None,
) -> list[tuple[Path, ActiveWork]]:
    """Reconcile an ended Agent Session's runs across its Repository.

    The session is matched the way observation joins it: by the Agent Session
    Identity its hooks published, or by the host process the hook observed.
    A declared Codex Relocation Intent remains pending; every other matching
    run ends. A Worktree whose Work Store cannot be read is skipped rather
    than raised: the caller is the SessionEnd hook, which must never break its
    harness, and an unreadable record stays for observation to diagnose.
    """
    ended: list[tuple[Path, ActiveWork]] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        try:
            active, _diagnostics = store.active()
        except OSError:
            continue
        for work in active:
            if work.harness != harness:
                continue
            by_identity = work.session_id == session_id
            by_process = (
                process_key is not None
                and work.session_process is not None
                and work.session_process.key == process_key
            )
            if by_identity and work.harness == "codex" and work.relocation is not None:
                # The explicit Relocation Intent says this process boundary is
                # not yet the end of the harness conversation. The next hook
                # at the named Worktree must still prove the continuation.
                continue
            if (by_identity or by_process) and store.stop(work.session_key):
                ended.append((worktree, work))
    return ended
