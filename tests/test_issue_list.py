from __future__ import annotations

from dashpot.issue_list import IssueListQuery, query_issue_list
from dashpot.model import AgentRun, ProjectObservation, ProjectSnapshot, WorkspaceSnapshot


NOW = "2026-08-27T00:00:00Z"


def issue(issue_id: str, state: str) -> dict:
    return {
        "id": issue_id,
        "state": state,
        "title": issue_id,
        "labels": [],
        "assignees": [],
    }


def workspace(*issues: dict) -> WorkspaceSnapshot:
    snapshot = ProjectSnapshot(
        project_id="project:one",
        display_label="One",
        repository_id="repository:one",
        collected_at=NOW,
        issue_source_status="fresh",
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW,
        observation_targets=[],
        issues=list(issues),
        diagnostics=[],
    )
    project = ProjectObservation(
        project_id="project:one",
        display_label="One",
        repository_id="repository:one",
        workspaces=["test"],
        anchors=["/one"],
        primary_anchor="/one",
        status="fresh",
        elapsed_ms=1,
        snapshot=snapshot,
        diagnostics=[],
    )
    return WorkspaceSnapshot(
        NOW,
        1,
        [project],
        issue_runs={item["id"]: [] for item in issues},
    )


def test_default_query_returns_open_issues_without_forgetting_observed_count() -> None:
    observed = workspace(issue("I_open", "open"), issue("I_closed", "closed"))

    result = query_issue_list(observed)

    assert result.observed_issue_count == 2
    assert result.matched_issue_count == 1
    assert [(row.kind, row.issue["id"]) for row in result.rows] == [
        ("issue", "I_open")
    ]


def test_query_joins_bound_runs_and_returns_unmatched_runs() -> None:
    observed = workspace(issue("I_open", "open"))
    bound = agent_run("bound", issue_id="I_open")
    unmatched = agent_run("unmatched", issue_id=None)
    observed.agent_runs = [bound, unmatched]
    observed.issue_runs["I_open"] = [bound.id]

    result = query_issue_list(observed)

    assert [row.kind for row in result.rows] == ["issue", "agent-run"]
    assert result.rows[0].observed_runs == (bound,)
    assert result.rows[1].run is unmatched


def test_default_query_explains_project_with_only_closed_issues() -> None:
    observed = workspace(issue("I_closed", "closed"))

    result = query_issue_list(observed)

    assert result.observed_issue_count == 1
    assert result.matched_issue_count == 0
    assert len(result.rows) == 1
    assert result.rows[0].kind == "project"
    assert result.rows[0].empty_message == "no open Issues"


def test_text_query_matches_catalogued_fields_and_preserves_observed_count() -> None:
    matching = issue("I_matching", "open")
    matching["title"] = "Fix launch controls"
    matching["assignees"] = ["navigation-owner"]
    hidden = issue("I_hidden", "open")
    hidden["labels"] = ["navigation-owner"]
    observed = workspace(matching, hidden)

    result = query_issue_list(observed, IssueListQuery(text="NAVIGATION-OWNER"))

    assert result.matched_issue_count == 1
    assert result.observed_issue_count == 2
    assert [row.issue["id"] for row in result.rows] == ["I_matching"]


def agent_run(session_id: str, *, issue_id: str | None) -> AgentRun:
    return AgentRun(
        id=f"codex-session:{session_id}",
        harness="codex",
        process_or_session=session_id,
        state="waiting",
        observation_target="/one",
        observation_project_id="project:one",
        branch="main",
        issue_id=issue_id,
        issue_reference_hint=None,
    )
