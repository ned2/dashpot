"""Record what one management command did as its ``command.outcome`` Runtime Event.

A command wraps its work in :func:`record_command_outcome` and fills the
:class:`OutcomeNote` it is handed as it learns what it acts on and what it
did; the seam it calls may fill the note too, as ``work start`` names the
Agent Session and the Issue once it has confirmed them. When the block ends
— done, refused or failed — the note names the process's subject and the
outcome is recorded with the command's duration. A refusal is recorded by
its ``DashpotError`` code or class, never its message.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .errors import DashpotError
from .event_log import EventLog, error_type
from .model import Harness
from .runtime_events import (
    CommandAction,
    CommandOutcome,
    DiagnosticCode,
    ManagementCommand,
    OutcomeResult,
    fitting,
)


@dataclass(slots=True, kw_only=True)
class OutcomeNote:
    """What one management command has learned about its work so far.

    It is filled while the command runs, so unlike the values it collects it
    is not frozen; nothing but the command and the seams it calls holds it.
    """

    action: CommandAction | None = None
    dry_run: bool | None = None
    # Refusals a plan or report states without raising, counted.
    refusals: int = 0
    # Whether the command's work was left undone without a refusal.
    incomplete: bool = False
    target_path: Path | None = None
    target_branch: str | None = None
    target_harness: Harness | None = None
    harness: Harness | None = None
    session_id: str | None = None
    issue_id: str | None = None
    project_id: str | None = None

    def identify(
        self,
        *,
        harness: Harness | None = None,
        session_id: str | None = None,
        issue_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Name the Agent Session, Issue or Project the command works for, once known."""
        self.harness = harness or self.harness
        self.session_id = session_id or self.session_id
        self.issue_id = issue_id or self.issue_id
        self.project_id = project_id or self.project_id

    def result(self) -> OutcomeResult:
        """How the command came out when it raised nothing."""
        if self.refusals:
            return "refused"
        return "failed" if self.incomplete else "succeeded"


def outcome_error(error: BaseException) -> str:
    """Name an outcome's error by its code when it carries one, else by errno or class.

    A GitHub failure or an unavailable Issue Source carries a stable code
    (``github-authentication``) that says more than its class; neither is
    ever its message.
    """
    code = getattr(error, "code", None)
    if isinstance(code, str):
        try:
            return _ERROR_CODE.validate_python(code)
        except ValidationError:
            pass
    return error_type(error)


# An error that carries a code carries a Diagnostic's.
_ERROR_CODE: TypeAdapter[str] = TypeAdapter(DiagnosticCode)


@contextmanager
def record_command_outcome(
    log: EventLog | None,
    command: ManagementCommand,
    *,
    dry_run: bool | None = None,
) -> Iterator[OutcomeNote]:
    """Time one management command and record its outcome when the block ends.

    Without an Event Log the note is filled and nothing is recorded. An
    exception leaving the block is recorded by its class and goes on.
    """
    note = OutcomeNote(dry_run=dry_run)
    if log is None:
        yield note
        return
    started = log.monotonic()
    result: OutcomeResult = "failed"
    error: str | None = None
    try:
        yield note
    except DashpotError as exc:
        result, error = "refused", outcome_error(exc)
        raise
    except BaseException as exc:
        result, error = "failed", outcome_error(exc)
        raise
    else:
        result = note.result()
    finally:
        _record(log, command, note, result, error, log.monotonic() - started)


def _record(
    log: EventLog,
    command: ManagementCommand,
    note: OutcomeNote,
    result: OutcomeResult,
    error: str | None,
    duration: float,
) -> None:
    # The subject names process.end too, so every later event says whose
    # work this process did.
    log.identify(
        harness=note.harness,
        session_id=note.session_id,
        issue_id=note.issue_id,
        project_id=note.project_id,
    )
    log.record(
        fitting(
            CommandOutcome,
            {
                "command": command,
                "result": result,
                "duration_seconds": max(0.0, duration),
            },
            {
                "action": note.action,
                "error_type": error,
                "refusal_count": note.refusals or None,
                "dry_run": note.dry_run,
                "target_path": None
                if note.target_path is None
                else str(note.target_path),
                "target_branch": note.target_branch,
                "target_harness": note.target_harness,
            },
        )
    )
