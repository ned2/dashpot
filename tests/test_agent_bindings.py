from __future__ import annotations

from dashpot.agent_bindings import IssueBindingPromotion, plan_issue_bindings
from dashpot.model import (
    AgentRun,
    ProjectObservation,
    ProjectSnapshot,
)


NOW = "2026-08-27T00:00:00Z"


def project(
    project_id: str, *issues: dict, status: str = "fresh"
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
    branch: str | None = "issue/old/repository#7",
    observation_project_id: str = "project-a",
    observation_target: str | None = "/project-a",
) -> AgentRun:
    return AgentRun(
        id="codex-session:one",
        harness="codex",
        process_or_session="one hook",
        state="running",
        observation_target=observation_target,
        observation_project_id=observation_project_id,
        branch=branch,
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

    plan = plan_issue_bindings(
        [project("project-a"), project("project-b", transferred)],
        [run(issue_id="I_stable")],
    )

    assert plan.issue_runs == {"I_stable": ["codex-session:one"]}
    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-hint-stale"


def test_exact_reference_hint_plans_identity_promotion_in_observed_project() -> None:
    hinted = {
        "id": "I_hint",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }

    plan = plan_issue_bindings(
        [project("project-a", hinted)],
        [run(issue_id=None, reference_hint="owner/repository#15")],
    )

    assert plan.issue_runs == {"I_hint": []}
    assert plan.promotions == [
        IssueBindingPromotion(
            "codex-session:one",
            "I_hint",
            "reference",
            "owner/repository#15",
            "/project-a",
            NOW,
        )
    ]
    assert plan.diagnostics == []


def test_ambiguous_numeric_branch_hint_is_diagnosed_without_guessing() -> None:
    first = {
        "id": "I_one",
        "projectId": "project-a",
        "number": 7,
        "reference": "one/repo#7",
    }
    second = {
        "id": "I_two",
        "projectId": "project-a",
        "number": 7,
        "reference": "two/repo#7",
    }

    plan = plan_issue_bindings(
        [project("project-a", first, second)],
        [run(issue_id=None, reference_hint=None, branch="issue/7")],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-hint-ambiguous"


def test_numeric_branch_hint_resolves_local_reference_by_issue_number() -> None:
    local_issue = {
        "id": "I_local_17",
        "projectId": "project-a",
        "number": 17,
        "reference": "local-planning-note",
    }

    plan = plan_issue_bindings(
        [project("project-a", local_issue)],
        [run(issue_id=None, reference_hint=None, branch="issue/17")],
    )

    assert plan.promotions == [
        IssueBindingPromotion(
            "codex-session:one",
            "I_local_17",
            "branch",
            "issue/17",
            "/project-a",
            NOW,
        )
    ]
    assert plan.diagnostics == []


def test_explicit_stale_hint_does_not_fall_back_to_branch() -> None:
    issue = {
        "id": "I_branch",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }

    plan = plan_issue_bindings(
        [project("project-a", issue)],
        [
            run(
                issue_id=None,
                reference_hint="old/repository#15",
                branch="issue/owner/repository#15",
            )
        ],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-hint-stale"


def test_hint_resolution_is_deferred_when_observed_project_is_not_fresh() -> None:
    issue = {
        "id": "I_stale",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }

    plan = plan_issue_bindings(
        [project("project-a", issue, status="stale")],
        [run(issue_id=None, reference_hint="owner/repository#15")],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-resolution-deferred"


def test_duplicate_persisted_identity_across_projects_is_a_conflict() -> None:
    first = {"id": "I_duplicate", "projectId": "project-a", "reference": "a#1"}
    second = {"id": "I_duplicate", "projectId": "project-b", "reference": "b#2"}

    plan = plan_issue_bindings(
        [project("project-a", first), project("project-b", second)],
        [run(issue_id="I_duplicate")],
    )

    assert plan.issue_runs == {"I_duplicate": []}
    assert plan.diagnostics[0].code == "agent-issue-identity-conflict"


def test_duplicate_identity_is_diagnosed_even_without_an_agent_binding() -> None:
    first = {"id": "I_duplicate", "projectId": "project-a", "reference": "a#1"}
    second = {"id": "I_duplicate", "projectId": "project-b", "reference": "b#2"}

    plan = plan_issue_bindings(
        [project("project-a", first), project("project-b", second)], []
    )

    assert plan.diagnostics[0].code == "agent-issue-identity-conflict"


def test_persisted_identity_wins_over_stale_reference_hint_with_warning() -> None:
    current = {
        "id": "I_stable",
        "projectId": "project-a",
        "reference": "new/repository#70",
    }

    plan = plan_issue_bindings(
        [project("project-a", current)],
        [run(issue_id="I_stable", reference_hint="old/repository#7")],
    )

    assert plan.issue_runs == {"I_stable": ["codex-session:one"]}
    assert plan.diagnostics[0].code == "agent-issue-hint-stale"


def test_reference_hint_never_resolves_against_a_different_project() -> None:
    elsewhere = {
        "id": "I_elsewhere",
        "projectId": "project-b",
        "reference": "owner/repository#15",
    }

    plan = plan_issue_bindings(
        [project("project-a"), project("project-b", elsewhere)],
        [run(issue_id=None, reference_hint="owner/repository#15")],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-hint-stale"


def test_hint_cannot_promote_a_globally_conflicting_identity() -> None:
    first = {
        "id": "I_duplicate",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }
    second = {
        "id": "I_duplicate",
        "projectId": "project-b",
        "reference": "other/repository#20",
    }

    plan = plan_issue_bindings(
        [project("project-a", first), project("project-b", second)],
        [run(issue_id=None, reference_hint="owner/repository#15")],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-identity-conflict"
    assert len(plan.diagnostics) == 1


def test_hint_without_a_located_target_is_not_promoted() -> None:
    hinted = {
        "id": "I_hint",
        "projectId": "project-a",
        "reference": "owner/repository#15",
    }

    plan = plan_issue_bindings(
        [project("project-a", hinted)],
        [
            run(
                issue_id=None,
                reference_hint="owner/repository#15",
                observation_target=None,
            )
        ],
    )

    assert plan.promotions == []
    assert plan.diagnostics[0].code == "agent-issue-resolution-deferred"
