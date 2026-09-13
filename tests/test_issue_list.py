from __future__ import annotations

import copy
from dataclasses import replace
from typing import get_args

import pytest

import factories
from app_harness import with_first_project_snapshot
from dashpot.issue_list import (
    ISSUE_SORT_COLUMNS,
    IssueListQuery,
    IssueSortColumn,
    empty_issue_message,
    is_issue_sort_column,
    issue_inventory_text,
    issue_result_count_text,
    issue_sort_value,
    next_issue_states,
    query_issue_list,
    sort_issue_rows,
)
from dashpot.issue_profile import IssueProfile
from dashpot.issue_table import COLUMN_SPECS, SortTerm, build_rows
from dashpot.model import (
    AgentRun,
    IssueActivity,
    WorkspaceSnapshot,
)
from dashpot.source_queries import AuxiliaryObservation
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

    result = query_issue_list(observed)

    assert result.observed_issue_count == 2
    assert result.matched_issue_count == 1
    assert [(row.kind, row.issue.id) for row in result.rows] == [("issue", "I_open")]


def test_query_joins_bound_runs_and_keeps_unbound_runs_off_the_list() -> None:
    bound = agent_run("bound", issue_id="I_open")
    unbound = agent_run("unbound", issue_id=None)
    observed = workspace(
        issue("I_open", "open"),
        runs=[bound, unbound],
        issue_runs={"I_open": [bound.id]},
    )

    result = query_issue_list(observed)

    assert [row.kind for row in result.rows] == ["issue"]
    assert result.rows[0].observed_runs == (bound,)
    # The unbound session is still a Project fact, not a Work row.
    assert result.rows[0].project_runs == (bound, unbound)


def test_project_with_only_unbound_runs_has_no_rows() -> None:
    unbound = agent_run("unbound", issue_id=None)
    observed = workspace(issue("I_closed", "closed"), runs=[unbound])

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
    observed = observed.model_copy(
        update={"projects": (*observed.projects, observed.projects[0])}
    )

    with pytest.raises(ValueError, match="Duplicate Project Identity"):
        query_issue_list(observed)


def test_query_rejects_duplicate_issue_identities_within_project() -> None:
    duplicated = issue("I_shared", "open")
    observed = workspace(duplicated, copy.deepcopy(duplicated))

    with pytest.raises(ValueError, match="Duplicate Issue Identity"):
        query_issue_list(observed)


def test_query_rejects_duplicate_agent_run_identities() -> None:
    duplicated = agent_run("shared", issue_id="I_open")
    observed = workspace(
        issue("I_open", "open"),
        runs=[duplicated, copy.deepcopy(duplicated)],
    )

    with pytest.raises(ValueError, match="Duplicate Agent Run Identity"):
        query_issue_list(observed)


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


@pytest.mark.parametrize("column", ISSUE_SORT_COLUMNS)
@pytest.mark.parametrize("descending", [False, True])
def test_sort_issue_rows_orders_like_the_issue_table(
    column: IssueSortColumn, *, descending: bool
) -> None:
    """A query page sorted by the read model lists what the table would."""
    issues = varied_issues()
    snapshot = with_first_project_snapshot(
        workspace(*issues),
        issue_activity={
            issues[0].id: IssueActivity(comment_count=2),
            issues[2].id: IssueActivity(comment_count=7),
        },
    )
    result = query_issue_list(snapshot)

    contexts, _cells = build_rows(
        result, sort=(SortTerm(column, descending=descending),)
    )
    ordered = sort_issue_rows(result.rows, column, descending=descending)

    assert [row.key for row in ordered] == list(contexts)
    assert len(ordered) == len(issues)


def test_sort_columns_are_the_sortable_table_columns() -> None:
    assert set(ISSUE_SORT_COLUMNS) == set(get_args(IssueSortColumn))
    assert set(ISSUE_SORT_COLUMNS) == {
        spec.key for spec in COLUMN_SPECS if spec.sortable
    }
    assert is_issue_sort_column("number")
    assert not is_issue_sort_column("title")


def test_missing_sort_values_rank_last_in_either_direction() -> None:
    result = query_issue_list(workspace(*varied_issues()))

    ascending = sort_issue_rows(result.rows, "author")
    descending = sort_issue_rows(result.rows, "author", descending=True)

    assert [row.issue.author for row in ascending] == ["ada", "Mia", "mia", None]
    assert [row.issue.author for row in descending] == ["Mia", "mia", "ada", None]


def test_queried_comment_activity_sorts_by_count_or_ranks_last() -> None:
    result = query_issue_list(workspace(*varied_issues()[:2]))
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
