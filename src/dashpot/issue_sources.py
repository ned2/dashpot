from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from .errors import DashpotError
from .issue_profile import IssueProfile
from .model import IssueActivity
from .models import FrozenDict

IssueSourceStatus = Literal["fresh", "stale", "unavailable"]
DiagnosticSeverity = Literal["info", "warning", "error"]
Clock = Callable[[], str]


@dataclass(frozen=True, slots=True)
class IssueSourceDiagnostic:
    source: str
    code: str
    severity: DiagnosticSeverity
    message: str


@dataclass(frozen=True, slots=True)
class IssueSourceObservation:
    """One adapter refresh outcome, constructed by the source it came from.

    Constructed from already-validated Issue Profiles rather than parsed, so
    it stays a frozen dataclass (ADR 0013); the mappings are frozen views so
    a consumer cannot corrupt the source's retained last-good state.
    """

    status: IssueSourceStatus
    attempted_at: str
    last_good_at: str | None
    issues: tuple[IssueProfile, ...]
    diagnostics: tuple[IssueSourceDiagnostic, ...]
    # Presentation facts about the source's labels (name -> "rrggbb"). They
    # sit beside the Issue profile rather than inside it: a label's colour is
    # a property of the tracker, not of any one Issue.
    label_colors: Mapping[str, str] = field(default_factory=dict)
    # Comment counts and linked pull requests keyed by Issue Identity.
    issue_activity: Mapping[str, IssueActivity] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CollectedIssues:
    """One complete collection cycle, returned whole by an adapter's ``_collect``.

    Built from already-validated Issue Profiles, so it stays a frozen
    dataclass (ADR 0013). Returning the palette and activity beside the
    Issues keeps a cycle self-consistent and leaves the adapter stateless
    across cycles: a failed ``_collect`` has no instance stash to leak into
    the next observation.
    """

    issues: tuple[IssueProfile, ...]
    label_colors: Mapping[str, str] = field(default_factory=dict)
    issue_activity: Mapping[str, IssueActivity] = field(default_factory=dict)


class IssueSourceRefreshError(DashpotError, RuntimeError):
    """A refresh the Issue Source itself diagnosed, with its diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IssueSource(ABC):
    """Refresh complete Issue collections while retaining the last good value."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now
        self._last_good: list[IssueProfile] | None = None
        self._last_good_at: str | None = None
        self._last_good_label_colors: dict[str, str] = {}
        self._last_good_issue_activity: dict[str, IssueActivity] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Name this source as it appears on its diagnostics."""

    @property
    def code_prefix(self) -> str:
        """Prefix the shared diagnostic codes; defaults to the source name."""
        return self.name

    def refresh(self) -> IssueSourceObservation:
        attempted_at = self._clock()
        try:
            collected = self._collect()
            self._check_collection_invariants(collected)
        except IssueSourceRefreshError as exc:
            return self._failed(attempted_at, exc.code, str(exc))
        except Exception as exc:
            # An adapter fault the source did not foresee (an unexpected
            # response shape, an OSError from its command) is still a failed
            # refresh: the last good collection is retained and the fault is
            # reported as a diagnostic rather than raised into the observer.
            return self._failed(
                attempted_at, f"{self.name}-internal", f"{type(exc).__name__}: {exc}"
            )

        # Issue Profiles and Issue Activity are frozen values, so retaining
        # them needs fresh containers, never deep copies.
        self._last_good = list(collected.issues)
        self._last_good_at = attempted_at
        self._last_good_label_colors = dict(collected.label_colors)
        self._last_good_issue_activity = dict(collected.issue_activity)
        return IssueSourceObservation(
            status="fresh",
            attempted_at=attempted_at,
            last_good_at=attempted_at,
            issues=collected.issues,
            diagnostics=(),
            label_colors=FrozenDict(collected.label_colors),
            issue_activity=FrozenDict(collected.issue_activity),
        )

    def _check_collection_invariants(self, collected: CollectedIssues) -> None:
        """Refuse a collection that repeats an Issue identity or Issue Number.

        The Issue Profile contract makes both unique within a complete Project
        collection, so the invariant lives here rather than in each adapter.
        """
        issues_by_id: dict[str, IssueProfile] = {}
        issues_by_number: dict[int, IssueProfile] = {}
        for issue in collected.issues:
            previous = issues_by_id.get(issue.id)
            if previous is not None:
                raise IssueSourceRefreshError(
                    f"{self.code_prefix}-duplicate-identity",
                    f"{self.name} collected duplicate Issue identity {issue.id}, "
                    f"seen at {_seen_at(previous)} and {_seen_at(issue)}",
                )
            previous = issues_by_number.get(issue.number)
            if previous is not None:
                raise IssueSourceRefreshError(
                    f"{self.code_prefix}-duplicate-number",
                    f"{self.name} collected duplicate Issue Number #{issue.number}, "
                    f"seen at {_seen_at(previous)} and {_seen_at(issue)}",
                )
            issues_by_id[issue.id] = issue
            issues_by_number[issue.number] = issue

    def _failed(
        self, attempted_at: str, code: str, message: str
    ) -> IssueSourceObservation:
        """The observation of a failed refresh: last good values, one diagnostic."""
        severity: DiagnosticSeverity = (
            "warning" if self._last_good is not None else "error"
        )
        return IssueSourceObservation(
            status="stale" if self._last_good is not None else "unavailable",
            attempted_at=attempted_at,
            last_good_at=self._last_good_at,
            issues=tuple(self._last_good or ()),
            label_colors=FrozenDict(self._last_good_label_colors),
            issue_activity=FrozenDict(self._last_good_issue_activity),
            diagnostics=(
                IssueSourceDiagnostic(
                    source=self.name, code=code, severity=severity, message=message
                ),
            ),
        )

    @abstractmethod
    def _collect(self) -> CollectedIssues:
        """Observe one complete collection cycle, with its labels and activity.

        The one adapter hook: diagnose a failed cycle by raising
        ``IssueSourceRefreshError``; sources without a palette or activity
        (Local Markdown) leave those mappings empty.
        """


def _seen_at(issue: IssueProfile) -> str:
    """The Issue Location as one actionable string.

    A local twin of ``issue_resolution.issue_location``: importing it here
    would cycle through the adapters this module is the base of.
    """
    location = issue.location
    if location.kind == "github":
        return location.url
    return f"{location.path}:{location.line}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
