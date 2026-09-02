from __future__ import annotations

from datetime import UTC, datetime

import factories
from dashpot.alerts import summarize_alerts
from dashpot.collect import AGENT_RUNS_KEY, ObservationKey
from dashpot.model import (
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    SourceStatus,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def project(
    project_id: str,
    *,
    issue_status: SourceStatus = "fresh",
    target_status: SourceStatus = "fresh",
    last_good_at: str | None = "2026-08-28T11:48:00Z",
    targets: list[ObservationTarget] | None = None,
    missing: bool = False,
) -> ProjectObservation:
    return factories.project(
        project_id,
        label=project_id.title(),
        targets=targets,
        anchors=("/repo",),
        status=issue_status,
        target_status=target_status,
        last_good_at=last_good_at,
        elapsed_ms=1,
        now="2026-08-28T12:00:00Z",
        missing=missing,
    )


def store(*projects: ProjectObservation, diagnostics=()) -> WorkspaceObservationStore:
    return WorkspaceObservationStore(
        WorkspaceSnapshot(
            collected_at="2026-08-28T12:00:00Z",
            elapsed_ms=1,
            projects=list(projects),
            diagnostics=list(diagnostics),
        )
    )


def clock() -> datetime:
    return NOW


def test_healthy_state_has_no_alert() -> None:
    assert summarize_alerts(store(project("alpha")), now=clock) is None
    assert summarize_alerts(WorkspaceObservationStore(), now=clock) is None


def test_stale_issue_source_names_the_project_and_its_age() -> None:
    alert = summarize_alerts(store(project("alpha", issue_status="stale")), now=clock)

    assert alert is not None
    assert alert.severity == "warning"
    assert alert.text == "⚠ Stale Issues: Alpha (last good 12m ago)"


def test_many_stale_projects_are_counted_not_listed() -> None:
    alert = summarize_alerts(
        store(
            project("alpha", issue_status="stale"),
            project("beta", issue_status="stale"),
            project("gamma", issue_status="stale"),
        ),
        now=clock,
    )

    assert alert is not None
    assert alert.text == "⚠ Stale Issues: 3 Projects"


def test_unavailable_states_outrank_stale_and_refreshing() -> None:
    unavailable_target = ObservationTarget(
        path="/repo/wt",
        head="abc",
        branch="feature",
        detached=False,
        dirty=None,
        availability="unavailable",
        elapsed_ms=1,
        diagnostics=[],
        role="linked",
    )
    alert = summarize_alerts(
        store(
            project("alpha", issue_status="stale"),
            project("beta", missing=True),
            project("gamma", targets=[unavailable_target]),
        ),
        refreshing=[ObservationKey("issues", "alpha")],
        now=clock,
    )

    assert alert is not None
    assert alert.severity == "error"
    assert [item.text for item in alert.items] == [
        "Unavailable: Beta",
        "Unavailable worktrees: Gamma /repo/wt",
        "Stale Issues: Alpha (last good 12m ago)",
        "refreshing",
    ]
    assert alert.text.startswith("✖ Unavailable: Beta  ·  ⚠ ")


def test_refresh_failures_and_integration_failures_are_errors() -> None:
    alert = summarize_alerts(
        store(
            project("alpha"),
            diagnostics=[
                Diagnostic(
                    source="workspace",
                    severity="warning",
                    message="Cannot observe Agent Runs: boom",
                    code="agent-observation",
                ),
                Diagnostic(
                    source="run:x",
                    severity="warning",
                    message="hint no longer matches",
                    code="agent-issue-hint-stale",
                ),
            ],
        ),
        failures={
            ObservationKey("issues", "alpha"): "Refresh failed: GitHub down",
            AGENT_RUNS_KEY: "Refresh failed: ps missing",
        },
        now=clock,
    )

    assert alert is not None
    assert [item.display for item in alert.items] == [
        "✖ Refresh failed: Alpha, Agent Runs",
        "⚠ Cannot observe Agent Runs: boom",
    ]


def test_refreshing_alone_is_informational_and_names_the_scope() -> None:
    alert = summarize_alerts(
        store(project("alpha"), project("beta")),
        refreshing=[
            AGENT_RUNS_KEY,
            ObservationKey("issues", "beta"),
            ObservationKey("targets", "beta"),
        ],
        now=clock,
    )

    assert alert is not None
    assert alert.severity == "info"
    # Scheduling order varies with timing; the readout is Workspace-ordered.
    assert alert.text == "↻ refreshing Beta, Agent Runs"


def test_stale_and_unavailable_worktree_observations_are_warnings() -> None:
    alert = summarize_alerts(
        store(
            project("alpha", target_status="stale"),
            project("beta", target_status="unavailable"),
        ),
        now=clock,
    )

    assert alert is not None
    assert alert.severity == "warning"
    assert [item.text for item in alert.items] == [
        "Unavailable worktrees and branches: Beta",
        "Stale worktrees and branches: Alpha",
    ]


def test_an_explicit_fetch_in_flight_is_informational_and_names_the_project() -> None:
    alert = summarize_alerts(
        store(project("alpha"), project("beta")),
        fetching=["beta", "unknown"],
        now=clock,
    )

    assert alert is not None
    assert alert.severity == "info"
    assert alert.text == "↻ fetching remotes Beta, unknown"
