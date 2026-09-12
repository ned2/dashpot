from dataclasses import replace

import pytest

from app_harness import issue
from dashpot.issue_list import IssueListQuery
from dashpot.model import AgentRun
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.related_rows import query_related_rows
from factories import agent_run, project, target, workspace
from test_branch_list import local


def related_snapshot(*, runs=None, bindings=None):
    first = issue("alpha#1", "First", projectId="project:alpha")
    second = issue("alpha#2", "Second", projectId="project:alpha")
    alpha = project(
        "project:alpha",
        first,
        second,
        targets=[target("/alpha", role="main"), target("/linked", branch="feature")],
        branches=[local("main"), local("feature")],
    )
    beta = project("project:beta", targets=[target("/alpha")], branches=[local("main")])
    if runs is None:
        runs = [
            agent_run(
                "one",
                target_path="/alpha",
                issue_id=second.id,
                hint=second.reference,
                state="running",
            ).model_copy(update={"session_id": "conversation-one"}),
            agent_run("two", target_path="/linked", branch="feature"),
        ]
    return workspace(
        alpha,
        beta,
        runs=runs,
        issue_runs=bindings if bindings is not None else {first.id: ["one"]},
    )


def related(store, run_id, query=IssueListQuery()):
    return query_related_rows(
        run_id,
        worktrees=store.query_worktrees().rows,
        branches=store.query_branches().rows,
        issues=store.query_issues(query).rows,
    )


def test_relationships_use_scoped_location_and_accepted_binding_not_hint():
    store = WorkspaceObservationStore(related_snapshot())
    result = related(store, "one")
    assert result.worktrees == frozenset(
        {
            next(
                row.key
                for row in store.query_worktrees().rows
                if row.project.project_id == "project:alpha"
                and row.target.path == "/alpha"
            )
        }
    )
    assert result.branches == frozenset(
        {
            next(
                row.key
                for row in store.query_branches().rows
                if row.project.project_id == "project:alpha" and row.name == "main"
            )
        }
    )
    assert result.issues == frozenset(
        {next(row.key for row in store.query_issues().rows if row.issue.number == 1)}
    )
    assert not related(store, "two").issues
    assert not related(store, "one", IssueListQuery(text="Second")).issues
    assert not related(store, None).worktrees


@pytest.mark.parametrize(
    ("updates", "worktree", "branch"),
    [
        ({"branch": None}, True, False),
        ({"observation_target": "/missing", "branch": "missing"}, False, False),
        ({"observation_project_id": "outside"}, False, False),
    ],
)
def test_missing_detached_and_outside_locations_have_no_invented_matches(
    updates, worktree, branch
):
    run = agent_run("one", target_path="/alpha").model_copy(update=updates)
    result = related(
        WorkspaceObservationStore(related_snapshot(runs=[run], bindings={})), "one"
    )
    assert bool(result.worktrees) is worktree
    assert bool(result.branches) is branch
    assert not result.issues


def test_shared_rows_and_only_current_page_issue_membership_are_highlighted():
    runs = [agent_run(name, target_path="/alpha") for name in ("one", "two")]
    store = WorkspaceObservationStore(related_snapshot(runs=runs))
    assert related(store, "one").worktrees == related(store, "two").worktrees
    assert related(store, "one").branches == related(store, "two").branches
    assert not query_related_rows("one", worktrees=(), branches=(), issues=()).issues
    assert not query_related_rows(
        "one",
        worktrees=(),
        branches=(),
        issues=(replace(store.query_issues().rows[0], observed_runs=()),),
    ).issues


def test_session_cursor_keys_survive_binding_switches_without_collapsing_conflicts():
    snapshot = related_snapshot()
    store = WorkspaceObservationStore(snapshot)
    before = next(
        row.key for row in store.query_sessions().rows if row.session.id == "one"
    )
    switched = snapshot.agent_runs[0].model_copy(
        update={"id": "new-run", "issue_id": None}
    )
    store.replace(
        snapshot.model_copy(update={"agent_runs": (switched,), "issue_runs": {}})
    )
    assert store.query_sessions().rows[0].key == before
    duplicate = switched.model_copy(update={"id": "conflicting-run"})
    store.replace(
        snapshot.model_copy(
            update={"agent_runs": (switched, duplicate), "issue_runs": {}}
        )
    )
    assert len({row.key for row in store.query_sessions().rows}) == 2
    assert {row.session.id for row in store.query_sessions().rows} == {
        "new-run",
        "conflicting-run",
    }
    wire = switched.model_dump(mode="json", by_alias=True)
    assert switched.session_id == "conversation-one"
    assert "sessionId" not in wire
    assert AgentRun.model_validate(wire).session_id is None
