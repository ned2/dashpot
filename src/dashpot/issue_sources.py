from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal


IssueSourceStatus = Literal["fresh", "stale", "unavailable"]
DiagnosticSeverity = Literal["info", "warning", "error"]
Clock = Callable[[], str]


@dataclass(frozen=True, slots=True)
class IssueSourceDiagnostic:
    source: str
    code: str
    severity: DiagnosticSeverity
    message: str


@dataclass(slots=True)
class IssueSourceObservation:
    status: IssueSourceStatus
    attempted_at: str
    last_good_at: str | None
    issues: list[dict[str, Any]]
    diagnostics: list[IssueSourceDiagnostic]
    # Presentation facts about the source's labels (name -> "rrggbb"). They
    # sit beside the Issue profile rather than inside it: a label's colour is
    # a property of the tracker, not of any one Issue.
    label_colors: dict[str, str] = field(default_factory=dict)


class IssueSourceRefreshError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IssueSource:
    """Refresh complete Issue collections while retaining the last good value."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or utc_now
        self._last_good: list[dict[str, Any]] | None = None
        self._last_good_at: str | None = None
        self._last_good_label_colors: dict[str, str] = {}

    @property
    def name(self) -> str:
        raise NotImplementedError

    def refresh(self) -> IssueSourceObservation:
        attempted_at = self._clock()
        try:
            issues = self._collect()
            label_colors = self._collect_label_colors()
        except IssueSourceRefreshError as exc:
            severity: DiagnosticSeverity = (
                "warning" if self._last_good is not None else "error"
            )
            return IssueSourceObservation(
                status="stale" if self._last_good is not None else "unavailable",
                attempted_at=attempted_at,
                last_good_at=self._last_good_at,
                issues=copy.deepcopy(self._last_good or []),
                label_colors=dict(self._last_good_label_colors),
                diagnostics=[
                    IssueSourceDiagnostic(
                        source=self.name,
                        code=exc.code,
                        severity=severity,
                        message=str(exc),
                    )
                ],
            )

        self._last_good = copy.deepcopy(issues)
        self._last_good_at = attempted_at
        self._last_good_label_colors = dict(label_colors)
        return IssueSourceObservation(
            status="fresh",
            attempted_at=attempted_at,
            last_good_at=attempted_at,
            issues=issues,
            diagnostics=[],
            label_colors=label_colors,
        )

    def _collect(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _collect_label_colors(self) -> dict[str, str]:
        """Colours for the labels observed by the latest ``_collect``.

        Sources without a palette (Local Markdown) leave every label neutral.
        """
        return {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
