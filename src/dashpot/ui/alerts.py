"""Concise, high-visibility summary of exceptional observation state.

The alert is a readout derived from current facts, never stored: it appears
when something is stale, unavailable, failing, or slow, and disappears on its
own when the facts recover. Diagnostics remains the durable detail record.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ..core.ages import relative_age
from ..core.model import Diagnostic, ProjectObservation
from ..observation.keys import ObservationKey
from ..observation.observation_store import (
    ObservedDiagnostic,
    WorkspaceObservationStore,
)
from ..queries.source_queries import QueryPage, ResourceKind
from .glyphs import Glyph

AlertSeverity = Literal["error", "warning", "info"]

SEVERITY_RANK: dict[AlertSeverity, int] = {"error": 0, "warning": 1, "info": 2}
# The alert line and the Diagnostics box share one severity vocabulary; the
# colour comes from the stylesheet of whichever box shows the line.
SEVERITY_GLYPH: dict[AlertSeverity, Glyph] = {
    "error": Glyph("✖", "error", theme_color="error"),
    "warning": Glyph("⚠", "warning", theme_color="warning"),
    "info": Glyph(
        "↻", "an observation, reported without alarm", theme_color="text-muted"
    ),
}
LEGEND = tuple(SEVERITY_GLYPH.values())
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
        return f"{SEVERITY_GLYPH[self.severity].symbol} {self.text}"


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
        """The items on one line, for the alert readout."""
        return SEPARATOR.join(item.display for item in self.items)

    @property
    def lines(self) -> str:
        """One line per item, for the Diagnostics box."""
        return "\n".join(item.display for item in self.items)


def summarize_diagnostics(
    store: WorkspaceObservationStore,
    *,
    failures: Mapping[ObservationKey, str] | None = None,
    launcher_diagnostics: Iterable[Diagnostic] = (),
    fetch_failures: Mapping[str, str] | None = None,
) -> Alert | None:
    """List every Diagnostic in full for the Diagnostics box, or nothing while it is empty.

    Where the alert summarizes, the Diagnostics box is the durable detail:
    each line is one Diagnostic with the severity it was observed with, a
    Project's prefixed by the Project it was observed for. The app's own
    errors come first — ``failures`` per observation key and
    ``fetch_failures`` per Project are refresh and Remote Fetch failures,
    and ``launcher_diagnostics`` are what loading the launcher settings
    reported.
    """
    items = [AlertItem("error", message) for message in (failures or {}).values()]
    items.extend(
        AlertItem(diagnostic.severity, diagnostic.message)
        for diagnostic in launcher_diagnostics
    )
    items.extend(
        AlertItem("error", message) for message in (fetch_failures or {}).values()
    )
    items.extend(
        AlertItem(entry.diagnostic.severity, _diagnostic_line(entry))
        for entry in store.diagnostics()
    )
    return Alert(tuple(items)) if items else None


def _diagnostic_line(entry: ObservedDiagnostic) -> str:
    text = f"{entry.diagnostic.source}: {entry.diagnostic.message}"
    return text if entry.project_label is None else f"{entry.project_label} · {text}"


def summarize_alerts(
    store: WorkspaceObservationStore,
    *,
    failures: Mapping[ObservationKey, str] | None = None,
    refreshing: Iterable[ObservationKey] = (),
    fetching: Iterable[str] = (),
    now: Callable[[], datetime] | None = None,
    source_pages: Mapping[ResourceKind, QueryPage] | None = None,
) -> Alert | None:
    """Summarize the impact of exceptional state, most severe first.

    ``failures`` are refresh failures or UI-boundary exceptions per
    observation key; ``refreshing`` lists keys whose observation has been in
    flight long enough to be worth showing; ``fetching`` names the Projects
    whose remotes an explicit fetch is fetching right now.
    """
    items: list[AlertItem] = []
    # Frozen observations make these reads cheap shared views, not copies.
    projects = store.projects()
    workspace_diagnostics = store.checkpoint().diagnostics
    labels = _labels(projects)
    current = (now or _utc_now)()

    failed_scopes = _ordered_scopes(failures or {}, labels)
    if failed_scopes:
        items.append(AlertItem("error", f"Refresh failed: {_join(failed_scopes)}"))

    unavailable_projects: list[str] = []
    unavailable_issues: list[str] = []
    stale_issues: list[tuple[str, str | None]] = []
    unavailable_pull_requests: list[str] = []
    stale_pull_requests: list[tuple[str, str | None]] = []
    unavailable_scans: list[str] = []
    stale_scans: list[str] = []
    unavailable_targets: list[str] = []
    for project in projects:
        label = project.display_label
        snapshot = project.snapshot
        if snapshot is None:
            unavailable_projects.append(label)
            continue
        issue_page = source_pages.get("issues") if source_pages is not None else None
        pull_page = (
            source_pages.get("pull-requests") if source_pages is not None else None
        )
        issue_status = (
            (issue_page.status if issue_page else "unavailable")
            if source_pages is not None
            else snapshot.issue_source_status
        )
        pull_status = (
            (pull_page.status if pull_page else "unavailable")
            if source_pages is not None
            else snapshot.pull_request_status
        )
        if issue_status == "unavailable":
            unavailable_issues.append(label)
        elif issue_status == "stale":
            stale_issues.append(
                (
                    label,
                    issue_page.last_good_at
                    if issue_page
                    else snapshot.issue_source_last_good_at,
                )
            )
        pull_requests_configured = not any(
            diagnostic.code == "pull-requests-not-configured"
            for diagnostic in snapshot.diagnostics
        )
        if pull_page is not None and pull_page.context.source == "local-markdown":
            pull_requests_configured = False
        if pull_requests_configured and pull_status == "unavailable":
            unavailable_pull_requests.append(label)
        elif pull_requests_configured and pull_status == "stale":
            stale_pull_requests.append(
                (
                    label,
                    pull_page.last_good_at
                    if pull_page
                    else snapshot.pull_request_last_good_at,
                )
            )
        if snapshot.target_status == "unavailable":
            unavailable_scans.append(label)
        elif snapshot.target_status == "stale":
            stale_scans.append(label)
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
    if unavailable_pull_requests:
        items.append(
            AlertItem(
                "error",
                "Unavailable Pull Requests: "
                f"{_join(unavailable_pull_requests, 'Projects')}",
            )
        )
    for diagnostic in workspace_diagnostics:
        if diagnostic.code in INTEGRATION_FAILURE_CODES:
            severity: AlertSeverity = (
                "error" if diagnostic.severity == "error" else "warning"
            )
            items.append(AlertItem(severity, diagnostic.message))
    if unavailable_scans:
        items.append(
            AlertItem(
                "warning",
                "Unavailable worktrees and branches: "
                f"{_join(unavailable_scans, 'Projects')}",
            )
        )
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
    if stale_pull_requests:
        if len(stale_pull_requests) == 1:
            label, last_good_at = stale_pull_requests[0]
            age = relative_age(last_good_at, current)
            detail = f" (last good {age})" if age else ""
            items.append(AlertItem("warning", f"Stale Pull Requests: {label}{detail}"))
        else:
            items.append(
                AlertItem(
                    "warning",
                    f"Stale Pull Requests: {len(stale_pull_requests)} Projects",
                )
            )
    if stale_scans:
        items.append(
            AlertItem(
                "warning",
                f"Stale worktrees and branches: {_join(stale_scans, 'Projects')}",
            )
        )

    # An explicit fetch is shown from the moment it starts: the person asked
    # for it and is waiting on it, unlike a background observation.
    fetching_labels = _unique(
        labels.get(project_id, project_id) for project_id in fetching
    )
    if fetching_labels:
        items.append(AlertItem("info", f"fetching remotes {_join(fetching_labels)}"))
    refreshing_scopes = _ordered_scopes(refreshing, labels)
    if refreshing_scopes:
        text = "refreshing" if items else f"refreshing {_join(refreshing_scopes)}"
        items.append(AlertItem("info", text))

    if not items:
        return None
    items.sort(key=lambda item: SEVERITY_RANK[item.severity])
    return Alert(tuple(items))


def _labels(projects: Sequence[ProjectObservation]) -> dict[str, str]:
    return {project.project_id: project.display_label for project in projects}


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
    return datetime.now(UTC)
