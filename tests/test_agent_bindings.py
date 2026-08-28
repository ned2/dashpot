from __future__ import annotations

from dashpot.agent_bindings import bind_issue_runs
from dashpot.model import (
    AgentRun,
    Issue,
    ProjectObservation,
    ProjectSnapshot,
    SourceStatus,
)

NOW = "2026-08-27T00:00:00Z"


def project(
    project_id: str, *issues: Issue, status: SourceStatus = "fresh"
) -> ProjectObservation:
    snapshot = ProjectSnapshot(
        project_id=project_id,
        display_label=project_id,
        repository_id=f"repository:{project_id}",
        collected_at=NOW,
        issue_source_status=status,
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW,
        observation_targets=[],
        issues=list(issues),
        diagnostics=[],
    )
    return ProjectObservation(
        project_id,
        project_id,
        f"repository:{project_id}",
        ["test"],
        [f"/{project_id}"],
        f"/{project_id}",
        status,
        1,
        snapshot,
        [],
    )


def run(
    *,
    issue_id: str | None,
    reference_hint: str | None = "old/repository#7",
    observation_project_id: str = "project-a",
) -> AgentRun:
    return AgentRun(
        id="work:codex:one:2026-08-27T00:00:00Z",
        harness="codex",
        process_or_session="codex pid 42",
        state="running",
        observation_target="/project-a",
        observation_project_id=observation_project_id,
        branch="main",
        issue_id=issue_id,
        issue_reference_hint=reference_hint,
        last_activity_at=NOW,
    )


def test_persisted_identity_survives_reference_change_and_project_transfer() -> None:
    transferred = {
        "id": "I_stable",
        "projectId": "project-b",
        "reference": "new/repository#70",
    }

    result = bind_issue_runs(
        [project("project-a"), project("project-b", transferred)],
        [run(issue_id="I_stable")],
    )

    assert result.issue_runs == {"I_stable": ["work:codex:one:2026-08-27T00:00:00Z"]}
    assert result.diagnostics[0].code == "agent-issue-hint-stale"


def test_unbound_run_is_left_alone_without_hint_resolution() -> None:
    hinted = {
        "id": "I_hint",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }

    result = bind_issue_runs(
        [project("project-a", hinted)],
        [run(issue_id=None, reference_hint="owner/repository#15")],
    )

    assert result.issue_runs == {"I_hint": []}
    assert result.agent_runs[0].issue_id is None
    assert result.diagnostics == []


def test_duplicate_persisted_identity_across_projects_is_a_conflict() -> None:
    first = {"id": "I_duplicate", "projectId": "project-a", "reference": "a#1"}
    second = {"id": "I_duplicate", "projectId": "project-b", "reference": "b#2"}

    result = bind_issue_runs(
        [project("project-a", first), project("project-b", second)],
        [run(issue_id="I_duplicate")],
    )

    assert result.issue_runs == {"I_duplicate": []}
    assert result.diagnostics[0].code == "agent-issue-identity-conflict"
    assert len(result.diagnostics) == 1


def test_duplicate_identity_is_diagnosed_even_without_an_agent_binding() -> None:
    first = {"id": "I_duplicate", "projectId": "project-a", "reference": "a#1"}
    second = {"id": "I_duplicate", "projectId": "project-b", "reference": "b#2"}

    result = bind_issue_runs(
        [project("project-a", first), project("project-b", second)], []
    )

    assert result.diagnostics[0].code == "agent-issue-identity-conflict"


def test_persisted_identity_wins_over_stale_reference_with_warning() -> None:
    current = {
        "id": "I_stable",
        "projectId": "project-a",
        "reference": "new/repository#70",
    }

    result = bind_issue_runs(
        [project("project-a", current)],
        [run(issue_id="I_stable", reference_hint="old/repository#7")],
    )

    assert result.issue_runs == {"I_stable": ["work:codex:one:2026-08-27T00:00:00Z"]}
    assert result.diagnostics[0].code == "agent-issue-hint-stale"


def test_unobserved_identity_is_deferred_while_any_source_is_not_fresh() -> None:
    result = bind_issue_runs(
        [project("project-a", status="stale")],
        [run(issue_id="I_unseen")],
    )

    assert result.diagnostics[0].code == "agent-issue-resolution-deferred"


def test_unobserved_identity_with_fresh_sources_is_diagnosed() -> None:
    result = bind_issue_runs(
        [project("project-a")],
        [run(issue_id="I_unseen")],
    )

    assert result.diagnostics[0].code == "agent-issue-binding-unobserved"


def test_two_runs_on_one_issue_are_independently_listed() -> None:
    issue = {
        "id": "I_shared",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }
    first = AgentRun(
        id="work:codex:one:t1",
        harness="codex",
        process_or_session="codex pid 41",
        state="running",
        observation_target="/project-a",
        observation_project_id="project-a",
        branch="main",
        issue_id="I_shared",
        issue_reference_hint="owner/repository#15",
    )
    second = AgentRun(
        id="work:codex:two:t2",
        harness="codex",
        process_or_session="codex pid 42",
        state="waiting",
        observation_target="/project-a",
        observation_project_id="project-a",
        branch="main",
        issue_id="I_shared",
        issue_reference_hint="owner/repository#15",
    )

    result = bind_issue_runs([project("project-a", issue)], [first, second])

    assert result.issue_runs == {"I_shared": ["work:codex:one:t1", "work:codex:two:t2"]}
    assert result.diagnostics == []
