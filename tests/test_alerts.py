from __future__ import annotations

from datetime import UTC, datetime

from dashpot.alerts import summarize_alerts
from dashpot.collect import AGENT_RUNS_KEY, ObservationKey
from dashpot.model import (
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def project(
    project_id: str,
    *,
    issue_status: str = "fresh",
    target_status: str = "fresh",
    last_good_at: str | None = "2026-08-28T11:48:00Z",
    targets: list[ObservationTarget] | None = None,
    missing: bool = False,
) -> ProjectObservation:
    snapshot = None
    if not missing:
        snapshot = ProjectSnapshot(
            project_id=project_id,
            display_label=project_id.title(),
            repository_id=f"repository:{project_id}",
            collected_at="2026-08-28T12:00:00Z",
            issue_source_status=issue_status,  # type: ignore[arg-type]
            issue_source_attempted_at="2026-08-28T12:00:00Z",
            issue_source_last_good_at=last_good_at,
            observation_targets=targets or [],
            issues=[],
            diagnostics=[],
            target_status=target_status,  # type: ignore[arg-type]
        )
    return ProjectObservation(
        project_id,
        project_id.title(),
        f"repository:{project_id}",
        ["test"],
        ["/repo"],
        "/repo",
        "unavailable" if missing else issue_status,  # type: ignore[arg-type]
        1,
        snapshot,
        [],
    )


def store(*projects: ProjectObservation, diagnostics=()) -> WorkspaceObservationStore:
    return WorkspaceObservationStore(
        WorkspaceSnapshot(
            "2026-08-28T12:00:00Z", 1, list(projects), diagnostics=list(diagnostics)
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
        "/repo/wt", "abc", "feature", False, None, "unavailable", 1, []
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
                    "workspace",
                    "warning",
                    "Cannot observe Agent Runs: boom",
                    "agent-observation",
                ),
                Diagnostic(
                    "run:x",
                    "warning",
                    "hint no longer matches",
                    "agent-issue-hint-stale",
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
        "Unavailable worktrees: Beta",
        "Stale worktrees: Alpha",
    ]
