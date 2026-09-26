"""Record the Agent Session and Diagnostic changes a dashboard observes as Runtime Events.

Each tracker keeps what it last saw and records only what changed since:
an Agent Session appearing, being bound to an Issue, switching or losing
it, relocating or ending; a Diagnostic appearing or clearing. A refresh that
changes nothing records nothing. Every event names its subject in the
envelope (:meth:`EventLog.about`) and holds identifiers only: a Diagnostic
is its source and code, never its message.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pydantic import TypeAdapter, ValidationError

from ..core.event_log import EventLog
from ..core.model import AgentRun
from ..core.runtime_events import (
    AgentSessionChange,
    AgentSessionChanged,
    DiagnosticChange,
    DiagnosticChanged,
    DiagnosticCode,
    fitting,
)
from ..observation.observation_store import (
    ObservedDiagnostic,
    WorkspaceObservationStore,
)

# The code a Diagnostic without one is recorded under; its message never is.
UNCODED = "uncoded"
_DIAGNOSTIC_CODE: TypeAdapter[str] = TypeAdapter(DiagnosticCode)

# One Agent Session as a dashboard follows it: its Agent Session Identity
# (harness and native ID), or the harness and the row's own identity when
# the session has no native ID.
FollowedSession = tuple[str, str]
# One Diagnostic as a dashboard follows it: its Project, source and code.
DiagnosticKey = tuple[str | None, str, str]


def identify_one_project(log: EventLog, store: WorkspaceObservationStore) -> None:
    """Name the Project a dashboard observes on its own events, when it observes one.

    A dashboard over a Workspace of several Projects names each event's
    Project on the event instead.
    """
    projects = store.projects()
    if log.identity.project_id is None and len(projects) == 1:
        log.identify(project_id=projects[0].project_id)


def followed_session(run: AgentRun) -> FollowedSession:
    """The Agent Session a row of the Agent Sessions observation belongs to."""
    return run.harness, run.session_id or run.id


def session_changes(
    before: AgentRun | None, after: AgentRun
) -> Iterator[tuple[AgentSessionChange, AgentRun]]:
    """Each change from ``before`` to ``after``, with the row it changed from."""
    if before is None:
        yield "appeared", after
        return
    if before.issue_id != after.issue_id:
        if before.issue_id is None:
            yield "bound", before
        elif after.issue_id is None:
            yield "unbound", before
        else:
            yield "switched", before
    if before.observation_target != after.observation_target:
        yield "relocated", before


class AgentSessionChanges:
    """Record each Agent Session the dashboard observes appearing, changing or ending."""

    def __init__(self, log: EventLog) -> None:
        self.log = log
        self._known: dict[FollowedSession, AgentRun] = {}

    def observe(self, runs: Iterable[AgentRun]) -> None:
        """Compare the observed sessions with the last seen, recording each change."""
        current: dict[FollowedSession, AgentRun] = {}
        # A session's Agent Run row, which names its Issue, stands for it
        # over a bare hook row for the same session.
        for run in sorted(runs, key=lambda run: (run.issue_id is None, run.id)):
            current.setdefault(followed_session(run), run)
        for key, run in current.items():
            for change, before in session_changes(self._known.get(key), run):
                self._record(change, run, before)
        for key, run in self._known.items():
            if key not in current:
                self._record("ended", run, run)
        self._known = current

    def _record(
        self, change: AgentSessionChange, run: AgentRun, before: AgentRun
    ) -> None:
        self.log.record(
            fitting(
                AgentSessionChanged,
                {"change": change},
                {
                    "previous_issue_id": before.issue_id
                    if change in ("unbound", "switched")
                    else None,
                    "previous_worktree": before.observation_target
                    if change == "relocated"
                    else None,
                },
            ),
            about=self.log.about(
                harness=run.harness,
                session_id=run.session_id,
                project_id=run.observation_project_id,
                worktree=run.observation_target,
                issue_id=None if change == "unbound" else run.issue_id,
            ),
        )


class DiagnosticChanges:
    """Record each Diagnostic the dashboard shows appearing or clearing.

    A Diagnostic is followed by its Project, source and code: a changed
    message under the same code is the same Diagnostic still showing.
    """

    def __init__(self, log: EventLog) -> None:
        self.log = log
        self._shown: dict[DiagnosticKey, ObservedDiagnostic] = {}

    def observe(self, entries: Iterable[ObservedDiagnostic]) -> None:
        """Compare the Diagnostics shown now with the last shown, recording each change."""
        current: dict[DiagnosticKey, ObservedDiagnostic] = {}
        for entry in entries:
            current.setdefault(diagnostic_key(entry), entry)
        for key, entry in current.items():
            if key not in self._shown:
                self._record("appeared", entry)
        for key, entry in self._shown.items():
            if key not in current:
                self._record("cleared", entry)
        self._shown = current

    def _record(self, change: DiagnosticChange, entry: ObservedDiagnostic) -> None:
        diagnostic = entry.diagnostic
        self.log.record(
            fitting(
                DiagnosticChanged,
                {
                    "change": change,
                    "code": _code(diagnostic.code),
                    "severity": diagnostic.severity,
                },
                {"source": diagnostic.source},
            ),
            about=self.log.about(project_id=entry.project_id),
        )


def diagnostic_key(entry: ObservedDiagnostic) -> DiagnosticKey:
    """What makes a shown Diagnostic the same one from refresh to refresh."""
    return entry.project_id, entry.diagnostic.source, entry.diagnostic.code or UNCODED


def _code(code: str | None) -> str:
    # Anything that is not a code — free text passed as one by mistake — is
    # recorded as uncoded rather than failing the dashboard or leaking it.
    if code is None:
        return UNCODED
    try:
        return _DIAGNOSTIC_CODE.validate_python(code)
    except ValidationError:
        return UNCODED
