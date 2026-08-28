"""Concise, high-visibility summary of exceptional observation state.

The alert is a readout derived from current facts, never stored: it appears
when something is stale, unavailable, failing, or slow, and disappears on its
own when the facts recover. Diagnostics remains the durable detail record.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .collect import ObservationKey
from .issue_table import relative_age
from .observation_store import WorkspaceObservationStore


AlertSeverity = Literal["error", "warning", "info"]

SEVERITY_RANK: dict[AlertSeverity, int] = {"error": 0, "warning": 1, "info": 2}
SEVERITY_SYMBOL: dict[AlertSeverity, str] = {
    "error": "✖",
    "warning": "⚠",
    "info": "↻",
}
SEPARATOR = "  ·  "

# Workspace-level diagnostic codes that describe a failing integration rather
# than a per-run binding quirk; only those are promoted to the alert.
INTEGRATION_FAILURE_CODES = frozenset(
    {
        "agent-observation",
        "agent-global-binding-rejected",
        "agent-target-mismatch",
        "work-session-conflict",
        "work-session-orphaned",
    }
)


@dataclass(frozen=True, slots=True)
class AlertItem:
    severity: AlertSeverity
    text: str

    @property
    def display(self) -> str:
        return f"{SEVERITY_SYMBOL[self.severity]} {self.text}"


@dataclass(frozen=True, slots=True)
class Alert:
    items: tuple[AlertItem, ...]

    @property
    def severity(self) -> AlertSeverity:
        return min(
            (item.severity for item in self.items),
            key=lambda severity: SEVERITY_RANK[severity],
        )

    @property
    def text(self) -> str:
        return SEPARATOR.join(item.display for item in self.items)


def summarize_alerts(
    store: WorkspaceObservationStore,
    *,
    failures: Mapping[ObservationKey, str] | None = None,
    refreshing: Iterable[ObservationKey] = (),
    now: Callable[[], datetime] | None = None,
) -> Alert | None:
    """Summarize the impact of exceptional state, most severe first.

    ``failures`` are refresh failures or UI-boundary exceptions per
    observation key; ``refreshing`` lists keys whose observation has been in
    flight long enough to be worth showing.
    """
    items: list[AlertItem] = []
    labels = _labels(store)
    current = (now or _utc_now)()

    failed_scopes = _ordered_scopes(failures or {}, labels)
    if failed_scopes:
        items.append(AlertItem("error", f"Refresh failed: {_join(failed_scopes)}"))

    unavailable_projects: list[str] = []
    unavailable_issues: list[str] = []
    stale_issues: list[tuple[str, str | None]] = []
    unavailable_targets: list[str] = []
    stale_targets: list[str] = []
    for project in store.checkpoint().projects:
        label = project.display_label
        snapshot = project.snapshot
        if snapshot is None:
            unavailable_projects.append(label)
            continue
        if snapshot.issue_source_status == "unavailable":
            unavailable_issues.append(label)
        elif snapshot.issue_source_status == "stale":
            stale_issues.append((label, snapshot.issue_source_last_good_at))
        if snapshot.target_status == "unavailable":
            unavailable_targets.append(label)
        elif snapshot.target_status == "stale":
            stale_targets.append(label)
        else:
            unavailable_targets.extend(
                f"{label} {target.path}"
                for target in snapshot.observation_targets
                if target.availability == "unavailable"
            )

    if unavailable_projects:
        items.append(
            AlertItem(
                "error",
                f"Unavailable: {_join(unavailable_projects, 'Projects')}",
            )
        )
    if unavailable_issues:
        items.append(
            AlertItem(
                "error",
                f"Unavailable Issues: {_join(unavailable_issues, 'Projects')}",
            )
        )
    for diagnostic in store.checkpoint().diagnostics:
        if diagnostic.code in INTEGRATION_FAILURE_CODES:
            severity: AlertSeverity = (
                "error" if diagnostic.severity == "error" else "warning"
            )
            items.append(AlertItem(severity, diagnostic.message))
    if unavailable_targets:
        items.append(
            AlertItem(
                "warning",
                f"Unavailable worktrees: {_join(unavailable_targets, 'targets')}",
            )
        )
    if stale_issues:
        if len(stale_issues) == 1:
            label, last_good_at = stale_issues[0]
            age = relative_age(last_good_at, current)
            detail = f" (last good {age})" if age else ""
            items.append(AlertItem("warning", f"Stale Issues: {label}{detail}"))
        else:
            items.append(
                AlertItem(
                    "warning",
                    f"Stale Issues: {len(stale_issues)} Projects",
                )
            )
    if stale_targets:
        items.append(
            AlertItem(
                "warning",
                f"Stale worktrees: {_join(stale_targets, 'Projects')}",
            )
        )

    refreshing_scopes = _ordered_scopes(refreshing, labels)
    if refreshing_scopes:
        text = "refreshing" if items else f"refreshing {_join(refreshing_scopes)}"
        items.append(AlertItem("info", text))

    if not items:
        return None
    items.sort(key=lambda item: SEVERITY_RANK[item.severity])
    return Alert(tuple(items))


def _labels(store: WorkspaceObservationStore) -> dict[str, str]:
    return {
        project.project_id: project.display_label
        for project in store.checkpoint().projects
    }


def _ordered_scopes(
    keys: Iterable[ObservationKey], labels: Mapping[str, str]
) -> list[str]:
    """Scope labels in Workspace order: Projects first, then Agent Runs.

    Keys arrive in scheduling order, which depends on timing; the readout
    must not.
    """
    rank = {label: index for index, label in enumerate(labels.values())}
    scopes = _unique(_scope_label(key, labels) for key in keys)
    return sorted(scopes, key=lambda scope: (rank.get(scope, len(rank)), scope))


def _scope_label(key: ObservationKey, labels: Mapping[str, str]) -> str:
    if key.kind == "agent-runs":
        return "Agent Runs"
    if key.kind == "workspace":
        # A single-shot collector observes every Project at once; name them
        # when there are few enough to be meaningful.
        return _join(list(labels.values())) if labels else "Workspace"
    return labels.get(key.project_id, key.project_id)


def _unique(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _join(labels: Sequence[str], plural: str = "Projects") -> str:
    if len(labels) <= 2:
        return ", ".join(labels)
    return f"{len(labels)} {plural}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
