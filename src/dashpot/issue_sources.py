from __future__ import annotations

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


class IssueSourceRefreshError(DashpotError, RuntimeError):
    """A refresh the Issue Source itself diagnosed, with its diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IssueSource:
    """Refresh complete Issue collections while retaining the last good value."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now
        self._last_good: list[IssueProfile] | None = None
        self._last_good_at: str | None = None
        self._last_good_label_colors: dict[str, str] = {}
        self._last_good_issue_activity: dict[str, IssueActivity] = {}

    @property
    def name(self) -> str:
        raise NotImplementedError

    def refresh(self) -> IssueSourceObservation:
        attempted_at = self._clock()
        try:
            issues = self._collect()
            label_colors = self._collect_label_colors()
            issue_activity = self._collect_issue_activity()
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
        self._last_good = list(issues)
        self._last_good_at = attempted_at
        self._last_good_label_colors = dict(label_colors)
        self._last_good_issue_activity = dict(issue_activity)
        return IssueSourceObservation(
            status="fresh",
            attempted_at=attempted_at,
            last_good_at=attempted_at,
            issues=tuple(issues),
            diagnostics=(),
            label_colors=FrozenDict(label_colors),
            issue_activity=FrozenDict(issue_activity),
        )

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

    def _collect(self) -> list[IssueProfile]:
        raise NotImplementedError

    def _collect_label_colors(self) -> dict[str, str]:
        """Colours for the labels observed by the latest ``_collect``.

        Sources without a palette (Local Markdown) leave every label neutral.
        """
        return {}

    def _collect_issue_activity(self) -> dict[str, IssueActivity]:
        """Engagement facts for the Issues observed by the latest ``_collect``.

        Sources without comments or pull requests (Local Markdown) report none.
        """
        return {}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
