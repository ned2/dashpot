from __future__ import annotations

import copy

import pytest

from dashpot.issue_list import (
    IssueListQuery,
    empty_issue_message,
    issue_inventory_text,
    issue_result_count_text,
    next_issue_states,
    query_issue_list,
)
from dashpot.issue_profile import IssueProfile
from dashpot.model import (
    AgentRun,
    ProjectObservation,
    ProjectSnapshot,
    WorkspaceSnapshot,
)
from helpers import make_issue

NOW = "2026-08-27T00:00:00Z"


def issue(issue_id: str, state: str, **overrides: object) -> IssueProfile:
    fields: dict[str, object] = {
        "id": issue_id,
        "number": 1,
        "state": state,
        "title": issue_id,
        "labels": [],
        "assignees": [],
        "author": None,
        "milestone": None,
        "issueType": None,
    }
    fields.update(overrides)
    return make_issue(**fields)


def workspace(*issues: IssueProfile) -> WorkspaceSnapshot:
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
        issue_runs={item.id: [] for item in issues},
    )


def test_default_query_returns_open_issues_without_forgetting_observed_count() -> None:
    observed = workspace(issue("I_open", "open"), issue("I_closed", "closed"))

    result = query_issue_list(observed)

    assert result.observed_issue_count == 2
    assert result.matched_issue_count == 1
    assert [(row.kind, row.issue.id) for row in result.rows] == [("issue", "I_open")]


def test_query_joins_bound_runs_and_keeps_unbound_runs_off_the_list() -> None:
    observed = workspace(issue("I_open", "open"))
    bound = agent_run("bound", issue_id="I_open")
    unbound = agent_run("unbound", issue_id=None)
    observed.agent_runs = [bound, unbound]
    observed.issue_runs["I_open"] = [bound.id]

    result = query_issue_list(observed)

    assert [row.kind for row in result.rows] == ["issue"]
    assert result.rows[0].observed_runs == (bound,)
    # The unbound session is still a Project fact, not a Work row.
    assert result.rows[0].project_runs == (bound, unbound)


def test_project_with_only_unbound_runs_has_no_rows() -> None:
    observed = workspace(issue("I_closed", "closed"))
    unbound = agent_run("unbound", issue_id=None)
    observed.agent_runs = [unbound]

    result = query_issue_list(observed)

    assert result.rows == ()
    assert result.observed_issue_count == 1


def test_default_query_lists_no_rows_for_only_closed_issues() -> None:
    observed = workspace(issue("I_closed", "closed"))

    result = query_issue_list(observed)

    assert result.observed_issue_count == 1
    assert result.matched_issue_count == 0
    assert result.rows == ()
    assert empty_issue_message(IssueListQuery()) == "no open Issues"
    assert (
        empty_issue_message(IssueListQuery(states=frozenset({"closed"})))
        == "no closed Issues"
    )
    assert empty_issue_message(IssueListQuery(text="x")) == (
        "no Issues match the current filters"
    )


def test_text_query_matches_catalogued_fields_and_preserves_observed_count() -> None:
    matching = issue(
        "I_matching",
        "open",
        title="Fix launch controls",
        assignees=["navigation-owner"],
    )
    hidden = issue("I_hidden", "open", body="navigation-owner")
    observed = workspace(matching, hidden)

    result = query_issue_list(observed, IssueListQuery(text="NAVIGATION-OWNER"))

    assert result.matched_issue_count == 1
    assert result.observed_issue_count == 2
    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_text_query_matches_labels_like_the_tracker_feed() -> None:
    matching = issue("I_matching", "open", labels=["good first issue", "priority/P3"])
    hidden = issue("I_hidden", "open")

    result = query_issue_list(
        workspace(matching, hidden), IssueListQuery(text='"good first"')
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_text_query_matches_the_author_without_requiring_one() -> None:
    matching = issue("I_matching", "open", author="octocat")
    hidden = issue("I_hidden", "open")

    result = query_issue_list(
        workspace(matching, hidden), IssueListQuery(text="octocat")
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_inventory_text_ignores_the_query_and_result_text_singularizes() -> None:
    observed = workspace(
        issue("I_one", "open"), issue("I_two", "open"), issue("I_done", "closed")
    )
    inventory = "Open 2 · Closed 1"

    open_view = query_issue_list(observed)
    assert (open_view.open_issue_count, open_view.closed_issue_count) == (2, 1)
    assert issue_inventory_text(open_view) == inventory
    assert issue_result_count_text(len(open_view.rows)) == "2 issues"

    narrowed = query_issue_list(observed, IssueListQuery(text="I_one"))
    assert issue_inventory_text(narrowed) == inventory
    assert issue_result_count_text(len(narrowed.rows)) == "1 issue"

    unmatched = query_issue_list(observed, IssueListQuery(text="nothing-here"))
    assert issue_inventory_text(unmatched) == inventory
    assert issue_result_count_text(len(unmatched.rows)) == "0 issues"

    closed_view = query_issue_list(
        observed, IssueListQuery(states=frozenset({"closed"}))
    )
    assert issue_inventory_text(closed_view) == inventory
    assert issue_result_count_text(len(closed_view.rows)) == "1 issue"

    all_view = query_issue_list(
        observed, IssueListQuery(states=frozenset({"open", "closed"}))
    )
    assert issue_inventory_text(all_view) == inventory
    assert issue_result_count_text(len(all_view.rows)) == "3 issues"

    all_narrowed = query_issue_list(
        observed, IssueListQuery(states=frozenset({"open", "closed"}), text="I_done")
    )
    assert issue_inventory_text(all_narrowed) == inventory
    assert issue_result_count_text(len(all_narrowed.rows)) == "1 issue"

    produced = [
        issue_inventory_text(view)
        for view in (
            open_view,
            narrowed,
            unmatched,
            closed_view,
            all_view,
            all_narrowed,
        )
    ] + [
        issue_result_count_text(len(view.rows))
        for view in (
            open_view,
            narrowed,
            unmatched,
            closed_view,
            all_view,
            all_narrowed,
        )
    ]
    for text in produced:
        assert " of " not in text
        assert "/" not in text


def test_next_issue_states_cycles_open_closed_all() -> None:
    assert next_issue_states(frozenset({"open"})) == frozenset({"closed"})
    assert next_issue_states(frozenset({"closed"})) == frozenset({"open", "closed"})
    assert next_issue_states(frozenset({"open", "closed"})) == frozenset({"open"})
    assert next_issue_states(frozenset()) == frozenset({"open"})


def test_text_query_matches_milestone_and_issue_type() -> None:
    by_milestone = issue("I_milestone", "open", milestone="v1.0")
    by_type = issue("I_type", "open", issueType="Bug")
    hidden = issue("I_hidden", "open")
    observed = workspace(by_milestone, by_type, hidden)

    milestones = query_issue_list(observed, IssueListQuery(text="v1.0"))
    types = query_issue_list(observed, IssueListQuery(text="bug"))

    assert [row.issue.id for row in milestones.rows] == ["I_milestone"]
    assert [row.issue.id for row in types.rows] == ["I_type"]


def test_text_query_matches_the_rendered_issue_number() -> None:
    matching = issue("I_matching", "open", number=17)
    hidden = issue("I_hidden", "open", number=18)

    result = query_issue_list(workspace(matching, hidden), IssueListQuery(text="#17"))

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_unquoted_search_terms_are_anded_without_requiring_a_phrase() -> None:
    matching = issue(
        "I_matching", "open", title="Clipboard support for terminal failure"
    )
    wrong_order = issue(
        "I_wrong_order", "open", title="Failure while copying to clipboard"
    )
    missing_term = issue("I_missing", "open", title="Clipboard behavior")

    result = query_issue_list(
        workspace(matching, wrong_order, missing_term),
        IssueListQuery(text="clipboard failure"),
    )

    assert [row.issue.id for row in result.rows] == [
        "I_matching",
        "I_wrong_order",
    ]


def test_quoted_search_phrase_still_requires_contiguous_text() -> None:
    matching = issue("I_matching", "open", title="Clipboard failure in terminal")
    separated = issue(
        "I_separated", "open", title="Clipboard support for terminal failure"
    )

    result = query_issue_list(
        workspace(matching, separated),
        IssueListQuery(text='"clipboard failure"'),
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_sort_qualifier_does_not_participate_in_lexical_matching() -> None:
    observed = workspace(issue("I_open", "open"))

    result = query_issue_list(observed, IssueListQuery(text="sort:created-asc"))

    assert [row.issue.id for row in result.rows] == ["I_open"]


def test_query_rejects_duplicate_project_identities() -> None:
    observed = workspace(issue("I_open", "open"))
    observed.projects.append(copy.deepcopy(observed.projects[0]))

    with pytest.raises(ValueError, match="Duplicate Project Identity"):
        query_issue_list(observed)


def test_query_rejects_duplicate_issue_identities_within_project() -> None:
    duplicated = issue("I_shared", "open")
    observed = workspace(duplicated, copy.deepcopy(duplicated))

    with pytest.raises(ValueError, match="Duplicate Issue Identity"):
        query_issue_list(observed)


def test_query_rejects_duplicate_agent_run_identities() -> None:
    observed = workspace(issue("I_open", "open"))
    duplicated = agent_run("shared", issue_id="I_open")
    observed.agent_runs = [duplicated, copy.deepcopy(duplicated)]

    with pytest.raises(ValueError, match="Duplicate Agent Run Identity"):
        query_issue_list(observed)


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
