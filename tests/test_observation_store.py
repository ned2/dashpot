from __future__ import annotations

import copy

import pytest

from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    WorkspaceSnapshot,
    to_jsonable,
)
from dashpot.observation_store import WorkspaceObservationStore


NOW = "2026-08-27T03:00:00Z"


def issue(issue_id: str, title: str) -> dict:
    return {
        "id": issue_id,
        "number": 1,
        "state": "open",
        "title": title,
        "labels": [],
        "assignees": [],
    }


def project(
    project_id: str,
    *issues: dict,
    status: str = "fresh",
) -> ProjectObservation:
    label = project_id.removeprefix("project:").title()
    snapshot = ProjectSnapshot(
        project_id=project_id,
        display_label=label,
        repository_id=f"repository:{project_id}",
        collected_at=NOW,
        issue_source_status=status,
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW if status != "unavailable" else None,
        observation_targets=[],
        issues=list(issues),
        diagnostics=[],
    )
    return ProjectObservation(
        project_id=project_id,
        display_label=label,
        repository_id=snapshot.repository_id,
        workspaces=["test"],
        anchors=[f"/{project_id}"],
        primary_anchor=f"/{project_id}",
        status=status,
        elapsed_ms=3,
        snapshot=snapshot,
        diagnostics=[],
    )


def workspace(
    *projects: ProjectObservation,
    runs: list[AgentRun] | None = None,
    issue_runs: dict[str, list[str]] | None = None,
) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        collected_at=NOW,
        elapsed_ms=9,
        projects=list(projects),
        agent_runs=runs or [],
        issue_runs=issue_runs or {},
        diagnostics=[],
    )


def run(run_id: str, project_id: str, issue_id: str | None) -> AgentRun:
    return AgentRun(
        id=run_id,
        harness="codex",
        process_or_session=run_id,
        state="waiting",
        observation_target=f"/{project_id}",
        observation_project_id=project_id,
        branch="issue/16-observation-store",
        issue_id=issue_id,
        issue_reference_hint=None,
    )


def test_seed_round_trips_checkpoint_and_isolates_owned_state() -> None:
    observed = workspace(project("project:one", issue("I_one", "First")))
    expected = copy.deepcopy(observed)

    store = WorkspaceObservationStore(observed)
    observed.projects[0].display_label = "Mutated by caller"

    assert store.revision == 1
    assert store.has_observations
    assert store.checkpoint() == expected
    assert to_jsonable(store.checkpoint()) == to_jsonable(expected)


def test_replace_updates_indexes_revision_query_and_stable_lookups() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    observed_run = run("codex:one", "project:one", "I_two")
    updated_project = project("project:one", issue("I_two", "Second"))
    updated_project.snapshot.observation_targets = [
        ObservationTarget(
            path="/project:one",
            head="abc123",
            branch="main",
            detached=False,
            dirty=False,
            availability="available",
            elapsed_ms=1,
            diagnostics=[],
        )
    ]
    second = workspace(
        updated_project,
        runs=[observed_run],
        issue_runs={"I_two": [observed_run.id]},
    )
    store = WorkspaceObservationStore(first)

    change = store.replace(second)
    result = store.query_issues()
    context = store.issue("I_two")

    assert change.revision == store.revision == result.revision == 2
    assert change.kinds == frozenset({"projects", "agent-runs"})
    assert change.project_ids == frozenset({"project:one"})
    assert change.issue_keys == frozenset(
        {("project:one", "I_one"), ("project:one", "I_two")}
    )
    assert change.observation_target_keys == frozenset(
        {("project:one", "/project:one")}
    )
    assert change.agent_run_ids == frozenset({observed_run.id})
    assert [row.key for row in result.rows] == [row_key("issue", "I_two")]
    assert result.rows[0].observed_runs == (observed_run,)
    assert store.project("project:one").display_label == "One"
    assert context is not None
    assert context.project.project_id == "project:one"
    assert context.issue["title"] == "Second"
    assert context.observed_runs == (observed_run,)
    assert store.issue("I_one") is None
    assert store.checkpoint() == second


def test_unavailable_project_replacement_retains_last_good_snapshot() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    unavailable = copy.deepcopy(available)
    unavailable.status = "unavailable"
    unavailable.snapshot = None
    unavailable.diagnostics = [
        Diagnostic(
            "project:project:one",
            "error",
            "repository is unavailable",
            "project-collection",
        )
    ]

    change = store.replace_project(unavailable)
    checkpoint = store.checkpoint()

    assert change.revision == 2
    assert change.kinds == frozenset({"projects"})
    assert checkpoint.projects[0].status == "unavailable"
    assert checkpoint.projects[0].snapshot is not None
    assert checkpoint.projects[0].snapshot.issues[0]["title"] == "Last good"
    assert checkpoint.projects[0].diagnostics == unavailable.diagnostics
    assert store.query_issues().observed_issue_count == 1


def test_unavailable_issue_source_uses_store_last_good_with_current_attempt() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            available,
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )
    unavailable = copy.deepcopy(available)
    unavailable.status = "fresh"
    unavailable.snapshot.collected_at = "2026-08-27T04:00:00Z"
    unavailable.snapshot.issue_source_status = "unavailable"
    unavailable.snapshot.issue_source_attempted_at = "2026-08-27T04:00:00Z"
    unavailable.snapshot.issue_source_last_good_at = None
    unavailable.snapshot.issues = []
    unavailable.snapshot.observation_targets = [
        ObservationTarget(
            path="/current-target",
            head="def456",
            branch="main",
            detached=False,
            dirty=True,
            availability="available",
            elapsed_ms=2,
            diagnostics=[],
        )
    ]
    unavailable.snapshot.diagnostics = [
        Diagnostic("github", "error", "GitHub unavailable", "github-command")
    ]

    store.replace(workspace(unavailable, runs=[observed_run], issue_runs={}))
    accepted = store.checkpoint().projects[0]

    assert accepted.status == "stale"
    assert accepted.snapshot.issue_source_status == "stale"
    assert accepted.snapshot.issues[0]["title"] == "Last good"
    assert accepted.snapshot.issue_source_last_good_at == NOW
    assert accepted.snapshot.issue_source_attempted_at == "2026-08-27T04:00:00Z"
    assert accepted.snapshot.collected_at == "2026-08-27T04:00:00Z"
    assert accepted.snapshot.observation_targets[0].path == "/current-target"
    assert accepted.snapshot.diagnostics == unavailable.snapshot.diagnostics
    assert store.query_issues().rows[0].observed_runs == (observed_run,)


def test_fresh_empty_issue_source_clears_prior_issues() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    empty = copy.deepcopy(available)
    empty.snapshot.issues = []

    store.replace_project(empty)

    assert store.query_issues().observed_issue_count == 0
    assert store.issue("I_one") is None


def test_source_last_good_is_not_carried_across_repository_identity_change() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    unavailable = copy.deepcopy(available)
    unavailable.repository_id = "repository:replacement"
    unavailable.snapshot.repository_id = "repository:replacement"
    unavailable.status = "unavailable"
    unavailable.snapshot.issue_source_status = "unavailable"
    unavailable.snapshot.issue_source_last_good_at = None
    unavailable.snapshot.issues = []

    store.replace_project(unavailable)

    accepted = store.checkpoint().projects[0]
    assert accepted.status == "unavailable"
    assert accepted.snapshot.issues == []


def test_adapter_supplied_stale_collection_remains_authoritative() -> None:
    available = project("project:one", issue("I_one", "Old"))
    store = WorkspaceObservationStore(workspace(available))
    stale = copy.deepcopy(available)
    stale.status = "stale"
    stale.snapshot.issue_source_status = "stale"
    stale.snapshot.issue_source_attempted_at = "2026-08-27T04:00:00Z"
    stale.snapshot.issues[0]["title"] = "Adapter last good"

    store.replace_project(stale)

    assert store.issue("I_one").issue["title"] == "Adapter last good"


def test_conflicting_issue_identities_remain_project_qualified() -> None:
    duplicated = issue("I_shared", "Shared identity")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", copy.deepcopy(duplicated)),
            project("project:two", copy.deepcopy(duplicated)),
        )
    )

    result = store.query_issues()

    assert {row.key for row in result.rows} == {
        row_key("issue", "project:one", "I_shared"),
        row_key("issue", "project:two", "I_shared"),
    }
    assert store.issue("I_shared") is None
    assert store.issue("I_shared", project_id="project:one").project.project_id == (
        "project:one"
    )
    assert len(store.checkpoint().projects) == 2


def test_change_reports_only_the_changed_project_qualified_issue() -> None:
    duplicated = issue("I_shared", "Shared identity")
    first = workspace(
        project("project:one", copy.deepcopy(duplicated)),
        project("project:two", copy.deepcopy(duplicated)),
    )
    store = WorkspaceObservationStore(first)
    changed = copy.deepcopy(first)
    changed.projects[0].snapshot.issues[0]["title"] = "Changed in one"

    change = store.replace(changed)

    assert change.issue_keys == frozenset({("project:one", "I_shared")})


def test_binding_change_reports_every_conflicting_issue_key() -> None:
    duplicated = issue("I_shared", "Shared identity")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", copy.deepcopy(duplicated)),
            project("project:two", copy.deepcopy(duplicated)),
        )
    )
    observed_run = run("codex:shared", "project:one", "I_shared")

    change = store.replace_agent_runs(
        [observed_run], {"I_shared": [observed_run.id]}
    )

    assert change.issue_keys == frozenset(
        {("project:one", "I_shared"), ("project:two", "I_shared")}
    )


def test_bound_run_record_change_reports_its_issue_key() -> None:
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", issue("I_one", "First")),
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )
    changed_run = copy.deepcopy(observed_run)
    changed_run.state = "running"

    change = store.replace_agent_runs(
        [changed_run], {"I_one": [changed_run.id]}
    )

    assert change.issue_keys == frozenset({("project:one", "I_one")})


def test_binding_transfer_reports_old_and_new_issue_keys() -> None:
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            project(
                "project:one",
                issue("I_one", "First"),
                issue("I_two", "Second"),
            ),
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )
    transferred = copy.deepcopy(observed_run)
    transferred.issue_id = "I_two"

    change = store.replace_agent_runs(
        [transferred], {"I_two": [transferred.id]}
    )

    assert change.issue_keys == frozenset(
        {("project:one", "I_one"), ("project:one", "I_two")}
    )


def test_binding_removal_and_missing_issue_do_not_fabricate_issue_keys() -> None:
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", issue("I_one", "First")),
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )
    missing = copy.deepcopy(observed_run)
    missing.issue_id = "I_missing"

    change = store.replace_agent_runs(
        [missing], {"I_missing": [missing.id]}
    )

    assert change.issue_keys == frozenset({("project:one", "I_one")})


def test_agent_run_observation_replaces_bindings_independently() -> None:
    selected_issue = issue("I_one", "First")
    store = WorkspaceObservationStore(
        workspace(project("project:one", selected_issue))
    )
    observed_run = run("codex:one", "project:one", "I_one")

    change = store.replace_agent_runs(
        [observed_run], {"I_one": [observed_run.id]}
    )
    result = store.query_issues()

    assert change.revision == result.revision == 2
    assert change.kinds == frozenset({"agent-runs"})
    assert change.project_ids == frozenset()
    assert change.issue_keys == frozenset({("project:one", "I_one")})
    assert change.agent_run_ids == frozenset({observed_run.id})
    assert result.rows[0].observed_runs == (observed_run,)
    assert store.checkpoint().issue_runs == {"I_one": [observed_run.id]}


def test_diagnostics_are_project_qualified_without_exposing_store_state() -> None:
    observed = project("project:one")
    observed.diagnostics.append(
        Diagnostic("project:one", "warning", "project warning")
    )
    snapshot = workspace(observed)
    snapshot.diagnostics.append(
        Diagnostic("workspace", "warning", "workspace warning")
    )
    store = WorkspaceObservationStore(snapshot)

    diagnostics = store.diagnostics()
    diagnostics[0].diagnostic.message = "mutated by caller"

    assert [entry.project_label for entry in diagnostics] == [None, "One"]
    assert [entry.diagnostic.message for entry in store.diagnostics()] == [
        "workspace warning",
        "project warning",
    ]


def test_invalid_replacement_is_rejected_atomically() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    store = WorkspaceObservationStore(first)
    duplicated = copy.deepcopy(first)
    duplicated.projects.append(copy.deepcopy(duplicated.projects[0]))

    with pytest.raises(ValueError, match="Duplicate Project Identity"):
        store.replace(duplicated)

    assert store.revision == 1
    assert store.checkpoint() == first


def test_invalid_project_replacement_is_rejected_atomically() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    store = WorkspaceObservationStore(first)
    duplicated = project(
        "project:one",
        issue("I_shared", "First copy"),
        issue("I_shared", "Second copy"),
    )

    with pytest.raises(ValueError, match="Duplicate Issue Identity"):
        store.replace_project(duplicated)

    assert store.revision == 1
    assert store.checkpoint() == first


def test_invalid_agent_run_replacement_is_rejected_atomically() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    store = WorkspaceObservationStore(first)
    duplicated = run("codex:one", "project:one", "I_one")

    with pytest.raises(ValueError, match="Duplicate Agent Run Identity"):
        store.replace_agent_runs(
            [duplicated, copy.deepcopy(duplicated)],
            {"I_one": [duplicated.id]},
        )

    assert store.revision == 1
    assert store.checkpoint() == first


def test_accepting_unchanged_state_advances_revision_without_changes() -> None:
    observed = workspace(project("project:one", issue("I_one", "First")))
    store = WorkspaceObservationStore(observed)

    change = store.replace(copy.deepcopy(observed))

    assert store.revision == change.revision == 2
    assert change.kinds == frozenset()
    assert change.project_ids == frozenset()
    assert change.issue_keys == frozenset()
    assert change.observation_target_keys == frozenset()
    assert change.agent_run_ids == frozenset()


def test_partial_replacements_isolate_store_owned_state() -> None:
    store = WorkspaceObservationStore(
        workspace(project("project:one", issue("I_one", "First")))
    )
    replacement_project = project(
        "project:one", issue("I_two", "Second")
    )
    replacement_run = run("codex:two", "project:one", "I_two")
    replacement_bindings = {"I_two": [replacement_run.id]}

    store.replace_project(replacement_project)
    store.replace_agent_runs([replacement_run], replacement_bindings)
    replacement_project.snapshot.issues[0]["title"] = "Caller mutation"
    replacement_run.state = "running"
    replacement_bindings["I_two"].clear()

    context = store.issue("I_two", project_id="project:one")
    assert context is not None
    assert context.issue["title"] == "Second"
    assert context.observed_runs[0].state == "waiting"
    assert store.checkpoint().issue_runs == {"I_two": ["codex:two"]}


def test_detail_for_refreshes_all_issue_and_project_run_fields() -> None:
    store = WorkspaceObservationStore(
        workspace(project("project:one", issue("I_one", "First")))
    )
    old_row = store.query_issues().rows[0]
    observed_run = run("codex:one", "project:one", "I_one")

    store.replace_agent_runs(
        [observed_run], {"I_one": [observed_run.id, "missing-run"]}
    )
    detail = store.detail_for(old_row)

    assert detail is not None
    assert detail.observed_runs == (observed_run,)
    assert detail.project_runs == (observed_run,)
    assert detail.session_states == ("waiting", "unknown")


def test_detail_for_keeps_conflicting_issues_project_qualified() -> None:
    duplicated = issue("I_shared", "Original")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", copy.deepcopy(duplicated)),
            project("project:two", copy.deepcopy(duplicated)),
        )
    )
    old_rows = {
        row.project.project_id: row for row in store.query_issues().rows
    }
    changed = project("project:one", issue("I_shared", "Changed"))

    store.replace_project(changed)

    assert store.detail_for(old_rows["project:one"]).issue["title"] == "Changed"
    assert store.detail_for(old_rows["project:two"]).issue["title"] == "Original"


def test_detail_for_unique_issue_follows_transfer_but_not_ambiguity() -> None:
    transferred = issue("I_shared", "Transfer")
    store = WorkspaceObservationStore(
        workspace(project("project:one", copy.deepcopy(transferred)))
    )
    old_row = store.query_issues().rows[0]

    store.replace(
        workspace(project("project:two", copy.deepcopy(transferred)))
    )
    moved = store.detail_for(old_row)

    assert moved is not None
    assert moved.project.project_id == "project:two"

    store.replace(
        workspace(
            project("project:one", copy.deepcopy(transferred)),
            project("project:two", copy.deepcopy(transferred)),
        )
    )
    assert store.detail_for(old_row) is None


def test_detail_for_returns_none_for_disappeared_domain_identities() -> None:
    issue_store = WorkspaceObservationStore(
        workspace(project("project:one", issue("I_one", "First")))
    )
    issue_row = issue_store.query_issues().rows[0]
    issue_store.replace_project(project("project:one"))

    assert issue_store.detail_for(issue_row) is None


def test_store_query_matches_standalone_query_across_rich_state() -> None:
    shared = issue("I_shared", "Shared")
    closed = issue("I_closed", "Closed navigation")
    closed["state"] = "closed"
    bound = run("codex:bound", "project:one", "I_shared")
    unmatched = run("codex:unmatched", "project:two", None)
    store = WorkspaceObservationStore(
        workspace(
            project(
                "project:one",
                copy.deepcopy(shared),
                closed,
            ),
            project("project:two", copy.deepcopy(shared)),
            runs=[bound, unmatched],
            issue_runs={"I_shared": [bound.id, "missing-run"]},
        )
    )
    queries = (
        IssueListQuery(),
        IssueListQuery(states=frozenset({"open", "closed"})),
        IssueListQuery(
            states=frozenset({"open", "closed"}), text="navigation"
        ),
    )

    for query in queries:
        assert store.query_issues(query) == query_issue_list(
            store.checkpoint(),
            query,
            revision=store.revision,
        )


def test_store_query_result_cannot_mutate_owned_observations() -> None:
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", issue("I_one", "First")),
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )

    returned = store.query_issues()
    row = returned.rows[0]
    row.project.display_label = "Caller Project"
    row.issue["title"] = "Caller Issue"
    row.observed_runs[0].state = "running"

    current = store.query_issues().rows[0]
    checkpoint = store.checkpoint()
    assert current.project.display_label == "One"
    assert current.issue["title"] == "First"
    assert current.observed_runs[0].state == "waiting"
    assert checkpoint.projects[0].display_label == "One"
    assert checkpoint.projects[0].snapshot.issues[0]["title"] == "First"
    assert checkpoint.agent_runs[0].state == "waiting"
