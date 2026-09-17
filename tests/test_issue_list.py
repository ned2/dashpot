from __future__ import annotations

import copy
from dataclasses import replace
from typing import get_args

import pytest

import factories
from app_harness import with_first_project_snapshot
from dashpot.core.issue_profile import IssueProfile
from dashpot.core.model import AgentRun, IssueActivity, WorkspaceSnapshot
from dashpot.observation.issue_list import (
    ISSUE_SORT_COLUMNS,
    IssueListQuery,
    IssueSortColumn,
    empty_issue_message,
    is_issue_sort_column,
    issue_result_count_text,
    issue_sort_value,
    next_issue_states,
    sort_issue_rows,
)
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.queries.source_queries import AuxiliaryObservation
from dashpot.ui.issue_table import COLUMN_SPECS
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


def workspace(
    *issues: IssueProfile,
    runs: list[AgentRun] | None = None,
    issue_runs: dict[str, list[str]] | None = None,
) -> WorkspaceSnapshot:
    project = factories.project(
        "project:one",
        *issues,
        repository_id="repository:one",
        anchors=("/one",),
        elapsed_ms=1,
        now=NOW,
    )
    return factories.workspace(
        project,
        runs=runs,
        issue_runs={item.id: [] for item in issues} | (issue_runs or {}),
        elapsed_ms=1,
        now=NOW,
    )


def test_default_query_returns_open_issues_without_forgetting_observed_count() -> None:
    observed = workspace(issue("I_open", "open"), issue("I_closed", "closed"))

    result = WorkspaceObservationStore(observed).query_issues()

    assert result.summary.observed_issue_count == 2
    assert result.summary.matched_issue_count == 1
    assert [row.issue.id for row in result.rows] == ["I_open"]


def test_query_joins_bound_runs_and_keeps_unbound_runs_off_the_list() -> None:
    bound = agent_run("bound", issue_id="I_open")
    unbound = agent_run("unbound", issue_id=None)
    observed = workspace(
        issue("I_open", "open"),
        runs=[bound, unbound],
        issue_runs={"I_open": [bound.id]},
    )

    result = WorkspaceObservationStore(observed).query_issues()

    assert len(result.rows) == 1
    assert result.rows[0].observed_runs == (bound,)


def test_project_with_only_unbound_runs_has_no_rows() -> None:
    unbound = agent_run("unbound", issue_id=None)
    observed = workspace(issue("I_closed", "closed"), runs=[unbound])

    result = WorkspaceObservationStore(observed).query_issues()

    assert result.rows == ()
    assert result.summary.observed_issue_count == 1


def test_default_query_lists_no_rows_for_only_closed_issues() -> None:
    observed = workspace(issue("I_closed", "closed"))

    result = WorkspaceObservationStore(observed).query_issues()

    assert result.summary.observed_issue_count == 1
    assert result.summary.matched_issue_count == 0
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

    result = WorkspaceObservationStore(observed).query_issues(
        IssueListQuery(text="NAVIGATION-OWNER")
    )

    assert result.summary.matched_issue_count == 1
    assert result.summary.observed_issue_count == 2
    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_text_query_matches_labels_like_the_tracker_feed() -> None:
    matching = issue("I_matching", "open", labels=["good first issue", "priority/P3"])
    hidden = issue("I_hidden", "open")

    result = WorkspaceObservationStore(workspace(matching, hidden)).query_issues(
        IssueListQuery(text='"good first"')
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_text_query_matches_the_author_without_requiring_one() -> None:
    matching = issue("I_matching", "open", author="octocat")
    hidden = issue("I_hidden", "open")

    result = WorkspaceObservationStore(workspace(matching, hidden)).query_issues(
        IssueListQuery(text="octocat")
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_lifecycle_counts_ignore_the_query_and_result_text_singularizes() -> None:
    observed = workspace(
        issue("I_one", "open"), issue("I_two", "open"), issue("I_done", "closed")
    )
    views = [
        (WorkspaceObservationStore(observed).query_issues(), "2 issues"),
        (
            WorkspaceObservationStore(observed).query_issues(
                IssueListQuery(text="I_one")
            ),
            "1 issue",
        ),
        (
            WorkspaceObservationStore(observed).query_issues(
                IssueListQuery(text="nothing-here")
            ),
            "0 issues",
        ),
        (
            WorkspaceObservationStore(observed).query_issues(
                IssueListQuery(states=frozenset({"closed"}))
            ),
            "1 issue",
        ),
        (
            WorkspaceObservationStore(observed).query_issues(
                IssueListQuery(states=frozenset({"open", "closed"}))
            ),
            "3 issues",
        ),
        (
            WorkspaceObservationStore(observed).query_issues(
                IssueListQuery(states=frozenset({"open", "closed"}), text="I_done")
            ),
            "1 issue",
        ),
    ]

    for view, expected in views:
        assert (view.summary.open_issue_count, view.summary.closed_issue_count) == (
            2,
            1,
        )
        assert issue_result_count_text(len(view.rows)) == expected
    for text in (issue_result_count_text(n) for n in range(4)):
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

    milestones = WorkspaceObservationStore(observed).query_issues(
        IssueListQuery(text="v1.0")
    )
    types = WorkspaceObservationStore(observed).query_issues(IssueListQuery(text="bug"))

    assert [row.issue.id for row in milestones.rows] == ["I_milestone"]
    assert [row.issue.id for row in types.rows] == ["I_type"]


def test_text_query_matches_the_rendered_issue_number() -> None:
    matching = issue("I_matching", "open", number=17)
    hidden = issue("I_hidden", "open", number=18)

    result = WorkspaceObservationStore(workspace(matching, hidden)).query_issues(
        IssueListQuery(text="#17")
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_unquoted_search_terms_are_anded_without_requiring_a_phrase() -> None:
    matching = issue(
        "I_matching", "open", title="Clipboard support for terminal failure"
    )
    wrong_order = issue(
        "I_wrong_order", "open", title="Failure while copying to clipboard"
    )
    missing_term = issue("I_missing", "open", title="Clipboard behavior")

    result = WorkspaceObservationStore(
        workspace(matching, wrong_order, missing_term)
    ).query_issues(IssueListQuery(text="clipboard failure"))

    assert [row.issue.id for row in result.rows] == [
        "I_matching",
        "I_wrong_order",
    ]


def test_quoted_search_phrase_still_requires_contiguous_text() -> None:
    matching = issue("I_matching", "open", title="Clipboard failure in terminal")
    separated = issue(
        "I_separated", "open", title="Clipboard support for terminal failure"
    )

    result = WorkspaceObservationStore(workspace(matching, separated)).query_issues(
        IssueListQuery(text='"clipboard failure"')
    )

    assert [row.issue.id for row in result.rows] == ["I_matching"]


def test_sort_qualifier_does_not_participate_in_lexical_matching() -> None:
    observed = workspace(issue("I_open", "open"))

    result = WorkspaceObservationStore(observed).query_issues(
        IssueListQuery(text="sort:created-asc")
    )

    assert [row.issue.id for row in result.rows] == ["I_open"]


def test_query_rejects_duplicate_project_identities() -> None:
    observed = workspace(issue("I_open", "open"))
    observed = observed.model_copy(
        update={"projects": (*observed.projects, observed.projects[0])}
    )

    with pytest.raises(ValueError, match="Duplicate Project Identity"):
        WorkspaceObservationStore(observed).query_issues()


def test_query_rejects_duplicate_issue_identities_within_project() -> None:
    duplicated = issue("I_shared", "open")
    observed = workspace(duplicated, copy.deepcopy(duplicated))

    with pytest.raises(ValueError, match="Duplicate Issue Identity"):
        WorkspaceObservationStore(observed).query_issues()


def test_query_rejects_duplicate_agent_run_identities() -> None:
    duplicated = agent_run("shared", issue_id="I_open")
    observed = workspace(
        issue("I_open", "open"),
        runs=[duplicated, copy.deepcopy(duplicated)],
    )

    with pytest.raises(ValueError, match="Duplicate Agent Run Identity"):
        WorkspaceObservationStore(observed).query_issues()


def agent_run(session_id: str, *, issue_id: str | None) -> AgentRun:
    return factories.agent_run(
        f"codex-session:{session_id}",
        "project:one",
        issue_id=issue_id,
        target_path="/one",
        working_directory=None,
        last_activity_at=None,
        process_or_session=session_id,
    )


def varied_issues() -> tuple[IssueProfile, ...]:
    """Issues whose every sortable fact differs, is missing, or ties."""
    return (
        issue(
            "issue:a",
            "open",
            number=3,
            labels=["priority/p2", "bug"],
            assignees=["Zed"],
            author="Mia",
            milestone="v2",
            issueType="Task",
            createdAt="2026-08-20T00:00:00Z",
            updatedAt="2026-08-26T00:00:00Z",
        ),
        issue(
            "issue:b",
            "open",
            number=1,
            labels=["enhancement", "Bug"],
            assignees=[],
            author=None,
            milestone=None,
            issueType=None,
            createdAt="2026-08-25T00:00:00Z",
            updatedAt=None,
        ),
        issue(
            "issue:c",
            "open",
            number=2,
            labels=["critical"],
            assignees=["amy", "bob"],
            author="ada",
            milestone="v1",
            issueType="Bug",
            createdAt="2026-08-25T00:00:00Z",
            updatedAt="2026-08-01T00:00:00Z",
        ),
        issue(
            "issue:d",
            "open",
            number=4,
            labels=[],
            assignees=["amy"],
            author="mia",
            milestone="v2",
            issueType="task",
            createdAt=None,
            updatedAt="2026-08-26T00:00:00Z",
        ),
    )


# Each sortable column's ascending order over ``varied_issues``: a missing
# value ranks last (an empty assignee tuple is a present, smallest value, so
# issue:b leads there), ties keep Issue Number order, and casefolding makes
# ``Mia`` and ``mia`` one value.
ASCENDING_ORDERS: dict[IssueSortColumn, list[str]] = {
    "number": ["issue:b", "issue:c", "issue:a", "issue:d"],
    "priority": ["issue:c", "issue:a", "issue:b", "issue:d"],
    "labels": ["issue:a", "issue:b", "issue:c", "issue:d"],
    "project": ["issue:b", "issue:c", "issue:a", "issue:d"],
    "assignees": ["issue:b", "issue:d", "issue:c", "issue:a"],
    "author": ["issue:c", "issue:a", "issue:d", "issue:b"],
    "milestone": ["issue:c", "issue:a", "issue:d", "issue:b"],
    "type": ["issue:c", "issue:a", "issue:d", "issue:b"],
    "comments": ["issue:b", "issue:d", "issue:a", "issue:c"],
    "created": ["issue:a", "issue:b", "issue:c", "issue:d"],
    "last_action": ["issue:c", "issue:a", "issue:d", "issue:b"],
}
# Descending reverses only the present values: the missing ones stay last,
# and a tie keeps its order rather than reversing it.
DESCENDING_ORDERS: dict[IssueSortColumn, list[str]] = {
    "number": ["issue:d", "issue:a", "issue:c", "issue:b"],
    "priority": ["issue:a", "issue:c", "issue:b", "issue:d"],
    "labels": ["issue:b", "issue:a", "issue:c", "issue:d"],
    "project": ["issue:b", "issue:c", "issue:a", "issue:d"],
    "assignees": ["issue:a", "issue:c", "issue:d", "issue:b"],
    "author": ["issue:a", "issue:d", "issue:c", "issue:b"],
    "milestone": ["issue:a", "issue:d", "issue:c", "issue:b"],
    "type": ["issue:a", "issue:d", "issue:c", "issue:b"],
    "comments": ["issue:c", "issue:a", "issue:b", "issue:d"],
    "created": ["issue:b", "issue:c", "issue:a", "issue:d"],
    "last_action": ["issue:a", "issue:d", "issue:c", "issue:b"],
}


@pytest.mark.parametrize("column", ISSUE_SORT_COLUMNS)
def test_sort_issue_rows_orders_every_column_with_missing_values_last(
    column: IssueSortColumn,
) -> None:
    """A Query Page ordered by the read model, as a Markdown Project's source serves it."""
    issues = varied_issues()
    snapshot = with_first_project_snapshot(
        workspace(*issues),
        issue_activity={
            issues[0].id: IssueActivity(comment_count=2),
            issues[2].id: IssueActivity(comment_count=7),
        },
    )
    result = WorkspaceObservationStore(snapshot).query_issues()

    ascending = sort_issue_rows(result.rows, column)
    descending = sort_issue_rows(result.rows, column, descending=True)

    assert [row.issue.id for row in ascending] == ASCENDING_ORDERS[column]
    assert [row.issue.id for row in descending] == DESCENDING_ORDERS[column]


def test_sort_columns_are_the_sortable_table_columns() -> None:
    assert set(ISSUE_SORT_COLUMNS) == set(get_args(IssueSortColumn))
    assert set(ISSUE_SORT_COLUMNS) == {
        spec.key for spec in COLUMN_SPECS if spec.sortable
    }
    assert is_issue_sort_column("number")
    assert not is_issue_sort_column("title")


def test_missing_sort_values_rank_last_in_either_direction() -> None:
    result = WorkspaceObservationStore(workspace(*varied_issues())).query_issues()

    ascending = sort_issue_rows(result.rows, "author")
    descending = sort_issue_rows(result.rows, "author", descending=True)

    assert [row.issue.author for row in ascending] == ["ada", "Mia", "mia", None]
    assert [row.issue.author for row in descending] == ["Mia", "mia", "ada", None]


def test_queried_comment_activity_sorts_by_count_or_ranks_last() -> None:
    result = WorkspaceObservationStore(workspace(*varied_issues()[:2])).query_issues()
    fetched, unfetched = (
        replace(
            row,
            queried=True,
            auxiliary=AuxiliaryObservation(
                status="fresh",
                attempted_at=NOW,
                last_good_at=NOW,
                activity=None if count is None else IssueActivity(comment_count=count),
            ),
        )
        for row, count in zip(result.rows, (5, None), strict=True)
    )

    assert issue_sort_value(fetched, "comments") == 5
    assert issue_sort_value(unfetched, "comments") is None
    assert sort_issue_rows([unfetched, fetched], "comments") == [fetched, unfetched]
