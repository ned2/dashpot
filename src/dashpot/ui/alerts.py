"""The dashboard's two readouts of exceptional state: the alert line and the Diagnostics box.

Both are derived from current facts, never stored. The alert is the concise,
high-visibility summary: it appears when something is stale, unavailable,
failing, or slow, and disappears on its own when the facts recover. The
Diagnostics box is the durable detail record, every Diagnostic in full.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ..core.ages import relative_age
from ..core.model import ProjectObservation, SourceStatus
from ..observation.keys import ObservationKey
from ..observation.observation_store import (
    ObservedDiagnostic,
    WorkspaceObservationStore,
)
from ..queries.page_navigation import PageQueryState
from ..queries.pages import ResourceKind
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


def list_diagnostics(
    own: Iterable[ObservedDiagnostic] = (),
    observed: Iterable[ObservedDiagnostic] = (),
) -> Alert | None:
    """List every Diagnostic in full for the Diagnostics box, or nothing while it is empty.

    Where the alert summarizes, the Diagnostics box is the durable detail:
    each line is one Diagnostic with the severity it was observed with,
    prefixed by the Project it was observed for, if any. The dashboard's
    ``own`` Diagnostics come first — failed refreshes and Remote Fetches, its
    launcher settings and its Event Log — and read as their message, which
    says what failed. The ``observed`` ones, such as a Query Source's or an
    Unattended Pause's, read with the source they speak for.
    """
    items = [
        AlertItem(entry.diagnostic.severity, _labelled(entry, entry.diagnostic.message))
        for entry in own
    ]
    items.extend(
        AlertItem(entry.diagnostic.severity, _diagnostic_line(entry))
        for entry in observed
    )
    return Alert(tuple(items)) if items else None


def _diagnostic_line(entry: ObservedDiagnostic) -> str:
    return _labelled(entry, f"{entry.diagnostic.source}: {entry.diagnostic.message}")


def _labelled(entry: ObservedDiagnostic, text: str) -> str:
    return text if entry.project_label is None else f"{entry.project_label} · {text}"


def summarize_alerts(
    store: WorkspaceObservationStore,
    *,
    failures: Mapping[ObservationKey, str] | None = None,
    refreshing: Iterable[ObservationKey] = (),
    fetching: Iterable[str] = (),
    now: Callable[[], datetime] | None = None,
    page_states: Mapping[ResourceKind, PageQueryState] | None = None,
    first_observations_in_flight: Iterable[ObservationKey] = (),
) -> Alert | None:
    """Summarize the impact of exceptional state, most severe first.

    ``failures`` are refresh failures or UI-boundary exceptions per
    observation key; ``refreshing`` lists keys whose observation has been in
    flight long enough to be worth showing; ``fetching`` names the Projects
    whose remotes an explicit fetch is fetching right now. ``page_states``
    distinguishes an accepted Query Page from a first query still in flight or
    one that failed without a page. ``first_observations_in_flight`` names
    pending observation placeholders that are not yet unavailable evidence.
    """
    items: list[AlertItem] = []
    # Frozen observations make these reads cheap shared views, not copies.
    projects = store.projects()
    workspace_diagnostics = store.checkpoint().diagnostics
    labels = _labels(projects)
    current = (now or _utc_now)()
    pending_observations = frozenset(first_observations_in_flight)
    # A Query Page spans the Workspace, so its state speaks for every Project.
    issue_state = page_states.get("issues") if page_states is not None else None
    pull_state = page_states.get("pull-requests") if page_states is not None else None
    pull_page = pull_state.page if pull_state is not None else None
    local_pull_requests = (
        pull_page is not None and pull_page.context.source == "local-markdown"
    )

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
        issue_status, issue_last_good_at = _source_status(
            issue_state,
            snapshot.issue_source_status,
            snapshot.issue_source_last_good_at,
        )
        if issue_status == "unavailable":
            unavailable_issues.append(label)
        elif issue_status == "stale":
            stale_issues.append((label, issue_last_good_at))
        pull_requests_configured = not local_pull_requests and not any(
            diagnostic.code == "pull-requests-not-configured"
            for diagnostic in snapshot.diagnostics
        )
        if pull_requests_configured:
            pull_status, pull_last_good_at = _source_status(
                pull_state,
                snapshot.pull_request_status,
                snapshot.pull_request_last_good_at,
            )
            if pull_status == "unavailable":
                unavailable_pull_requests.append(label)
            elif pull_status == "stale":
                stale_pull_requests.append((label, pull_last_good_at))
        targets_pending = (
            ObservationKey("targets", project.project_id) in pending_observations
        )
        if snapshot.target_status == "unavailable" and not targets_pending:
            unavailable_scans.append(label)
        elif snapshot.target_status == "stale":
            stale_scans.append(label)
        else:
            unavailable_targets.extend(
                f"{label} {target.path}"
                for target in snapshot.observation_targets
                if target.availability == "unavailable"
            )

    readouts = (
        _named_item("error", "Unavailable", unavailable_projects),
        _named_item("error", "Unavailable Issues", unavailable_issues),
        _named_item("error", "Unavailable Pull Requests", unavailable_pull_requests),
        *(
            AlertItem(
                "error" if diagnostic.severity == "error" else "warning",
                diagnostic.message,
            )
            for diagnostic in workspace_diagnostics
            if diagnostic.code in INTEGRATION_FAILURE_CODES
        ),
        _named_item("warning", "Unavailable worktrees and branches", unavailable_scans),
        _named_item("warning", "Unavailable worktrees", unavailable_targets, "targets"),
        _stale_item("Issues", stale_issues, current),
        _stale_item("Pull Requests", stale_pull_requests, current),
        _named_item("warning", "Stale worktrees and branches", stale_scans),
    )
    items.extend(item for item in readouts if item is not None)

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


def _source_status(
    state: PageQueryState | None,
    observed_status: SourceStatus,
    observed_last_good_at: str | None,
) -> tuple[SourceStatus | None, str | None]:
    """A source's status and when it last read well, from its Query Page where one is queried.

    Without a page state the Project's own observation speaks for the source.
    """
    if state is None:
        return observed_status, observed_last_good_at
    page = state.page
    return state.status, page.last_good_at if page else observed_last_good_at


def _named_item(
    severity: AlertSeverity,
    heading: str,
    names: Sequence[str],
    plural: str = "Projects",
) -> AlertItem | None:
    """Name what ``heading`` reports on, or count it past two; nothing when none."""
    if not names:
        return None
    return AlertItem(severity, f"{heading}: {_join(names, plural)}")


def _stale_item(
    noun: str, entries: Sequence[tuple[str, str | None]], current: datetime
) -> AlertItem | None:
    """Name the one Project whose ``noun`` are stale with their age, or count them."""
    if not entries:
        return None
    if len(entries) > 1:
        return AlertItem("warning", f"Stale {noun}: {len(entries)} Projects")
    label, last_good_at = entries[0]
    age = relative_age(last_good_at, current)
    detail = f" (last good {age})" if age else ""
    return AlertItem("warning", f"Stale {noun}: {label}{detail}")


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
