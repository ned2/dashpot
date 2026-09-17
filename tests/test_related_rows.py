from dataclasses import replace

import pytest

from app_harness import issue
from dashpot.core.model import AgentRun
from dashpot.observation.issue_list import IssueListQuery
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.observation.related_rows import query_related_rows
from factories import agent_run, project, target, workspace
from test_branch_list import local


def records(store, query=IssueListQuery(), *, issues=None):
    """Every pane's rows from ``store``, as the dashboard hands them over."""
    return (
        *store.query_sessions().rows,
        *store.query_worktrees().rows,
        *store.query_branches().rows,
        *(store.query_issues(query).rows if issues is None else issues),
    )


def query_source(store, source, *, issues=None):
    return query_related_rows(source, records(store, issues=issues))


def test_every_source_uses_direct_membership_without_recursive_expansion():
    runs = [
        agent_run("one", target_path="/alpha"),
        agent_run("two", target_path="/alpha"),
        agent_run("three", target_path="/linked", branch="main"),
    ]
    store = WorkspaceObservationStore(
        related_snapshot(
            runs=runs, bindings={"I_alpha#1": ["one"], "I_alpha#2": ["three"]}
        )
    )
    sessions = {row.session.id: row for row in store.query_sessions().rows}
    worktrees = {
        row.target.path: row
        for row in store.query_worktrees().rows
        if row.project.project_id == "project:alpha"
    }
    branches = {
        row.name: row
        for row in store.query_branches().rows
        if row.project.project_id == "project:alpha"
    }
    issues = {row.issue.number: row for row in store.query_issues().rows}
    selected = query_source(store, worktrees["/alpha"])
    assert selected.sessions == {sessions["one"].key, sessions["two"].key}
    assert selected.branches == {branches["main"].key}
    assert selected.issues == {issues[1].key}
    assert not selected.worktrees
    selected = query_source(store, branches["main"])
    assert selected.sessions == {row.key for row in sessions.values()}
    assert selected.worktrees == {worktrees["/alpha"].key}
    assert selected.issues == {row.key for row in issues.values()}
    assert not selected.branches
    selected = query_source(store, issues[1])
    assert selected.sessions == {sessions["one"].key}
    assert selected.worktrees == {worktrees["/alpha"].key}
    assert selected.branches == {branches["main"].key}
    assert not selected.issues
    selected = query_source(store, worktrees["/alpha"], issues=())
    assert selected.sessions == {sessions["one"].key, sessions["two"].key}
    assert selected.branches == {branches["main"].key}
    assert not selected.issues


def test_unoccupied_topology_is_scoped_and_excludes_detached_unavailable_locations():
    store = WorkspaceObservationStore(related_snapshot(runs=[], bindings={}))
    for worktree in store.query_worktrees().rows:
        selected = query_source(store, worktree)
        branch = next(
            row
            for row in store.query_branches().rows
            if row.project.project_id == worktree.project.project_id
            and row.name == worktree.target.branch
        )
        assert selected.branches == {branch.key}
        assert not selected.sessions and not selected.issues
        assert worktree.key in query_source(store, branch).worktrees
        unavailable = replace(
            worktree,
            target=worktree.target.model_copy(update={"availability": "unavailable"}),
        )
        assert not query_source(store, unavailable).branches
        detached = replace(
            worktree,
            target=worktree.target.model_copy(
                update={"detached": True, "branch": None}
            ),
        )
        assert not query_source(store, detached).branches
    for issue_row in store.query_issues().rows:
        result = query_source(store, issue_row)
        assert not result.sessions and not result.worktrees and not result.branches


def test_distinct_native_sessions_sharing_backend_do_not_leak_issue_context():
    runs = [
        agent_run("one", target_path="/alpha", process_or_session="4242").model_copy(
            update={"session_id": "native-one"}
        ),
        agent_run("two", target_path="/alpha", process_or_session="4242").model_copy(
            update={"session_id": "native-two"}
        ),
    ]
    store = WorkspaceObservationStore(
        related_snapshot(
            runs=runs, bindings={"I_alpha#1": ["one"], "I_alpha#2": ["two"]}
        )
    )
    sessions = store.query_sessions().rows
    assert len({row.key for row in sessions}) == 2
    for issue_row in store.query_issues().rows:
        result = query_source(store, issue_row)
        expected_run = "one" if issue_row.issue.number == 1 else "two"
        assert result.sessions == {
            row.key for row in sessions if row.session.id == expected_run
        }
        assert len(result.worktrees) == len(result.branches) == 1
        session = next(row for row in sessions if row.session.id == expected_run)
        assert query_source(store, session).issues == {issue_row.key}


def test_branch_highlights_all_checked_out_worktrees_without_sessions():
    snapshot = related_snapshot(runs=[], bindings={})
    alpha = snapshot.projects[0]
    alpha = alpha.model_copy(
        update={
            "snapshot": alpha.snapshot.model_copy(
                update={
                    "observation_targets": (
                        target("/alpha", branch="main"),
                        target("/other", branch="main"),
                        target("/detached", branch=None),
                    )
                }
            )
        }
    )
    store = WorkspaceObservationStore(
        snapshot.model_copy(update={"projects": (alpha, snapshot.projects[1])})
    )
    branch = next(
        row
        for row in store.query_branches().rows
        if row.project.project_id == "project:alpha" and row.name == "main"
    )
    result = query_source(store, branch)
    assert result.worktrees == {
        row.key
        for row in store.query_worktrees().rows
        if row.project.project_id == "project:alpha"
        and row.target.path in {"/alpha", "/other"}
    }
    assert not result.sessions and not result.issues


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
        next(
            (row for row in store.query_sessions().rows if row.session.id == run_id),
            None,
        ),
        records(store, query),
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
    source = store.query_sessions().rows[0]
    assert not query_related_rows(source, ()).issues
    assert not query_related_rows(
        source, (replace(store.query_issues().rows[0], observed_runs=()),)
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
