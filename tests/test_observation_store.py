from __future__ import annotations

import copy

import pydantic
import pytest

import factories
from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.issue_profile import IssueProfile
from dashpot.model import (
    AgentRun,
    Branch,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    SourceStatus,
)
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.serialization import snapshot_document
from factories import NOW, workspace
from helpers import make_issue, required, snapshot_of


def issue(issue_id: str, title: str, state: str = "open") -> IssueProfile:
    return make_issue(
        id=issue_id,
        number=1,
        state=state,
        title=title,
        labels=[],
        assignees=[],
        author=None,
        milestone=None,
        issueType=None,
    )


def project(
    project_id: str,
    *issues: IssueProfile,
    status: SourceStatus = "fresh",
) -> ProjectObservation:
    return factories.project(project_id, *issues, status=status)


def run(run_id: str, project_id: str, issue_id: str | None) -> AgentRun:
    return factories.agent_run(
        run_id,
        project_id,
        branch="issue/16-observation-store",
        issue_id=issue_id,
        working_directory=None,
        last_activity_at=None,
    )


def test_seed_round_trips_checkpoint_and_isolates_owned_state() -> None:
    # Isolation from the caller's mutable inputs is proven in
    # test_observation_aliasing; the snapshot itself is frozen.
    observed = workspace(project("project:one", issue("I_one", "First")))
    expected = copy.deepcopy(observed)

    store = WorkspaceObservationStore(observed)

    assert store.revision == 1
    assert store.has_observations
    assert store.checkpoint() == expected
    assert snapshot_document(store.checkpoint()) == snapshot_document(expected)


def test_replace_updates_indexes_revision_query_and_stable_lookups() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    observed_run = run("codex:one", "project:one", "I_two")
    updated_project = factories.project(
        "project:one",
        issue("I_two", "Second"),
        targets=[
            ObservationTarget(
                path="/project:one",
                head="abc123",
                branch="main",
                detached=False,
                dirty=False,
                availability="available",
                elapsed_ms=1,
                diagnostics=[],
                role="main",
            )
        ],
        branches=[
            Branch(
                refname="refs/heads/main",
                name="main",
                remote=None,
                head="abc123",
                committed_at="2026-08-27T00:00:00Z",
            )
        ],
    )
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
    assert change.branch_keys == frozenset({("project:one", "refs/heads/main")})
    assert change.agent_run_ids == frozenset({observed_run.id})
    assert [row.key for row in result.rows] == [row_key("issue", "I_two")]
    assert [row.name for row in store.query_branches().rows] == ["main"]
    assert result.rows[0].observed_runs == (observed_run,)
    assert required(store.project("project:one")).display_label == "One"
    assert context is not None
    assert context.project.project_id == "project:one"
    assert context.issue.title == "Second"
    assert context.observed_runs == (observed_run,)
    assert store.issue("I_one") is None
    assert store.checkpoint() == second


def test_unavailable_project_replacement_retains_last_good_snapshot() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    unavailable = available.model_copy(
        update={
            "status": "unavailable",
            "snapshot": None,
            "diagnostics": (
                Diagnostic(
                    source="project:project:one",
                    severity="error",
                    message="repository is unavailable",
                    code="project-collection",
                ),
            ),
        }
    )

    change = store.replace_project(unavailable)
    checkpoint = store.checkpoint()

    assert change.revision == 2
    assert change.kinds == frozenset({"projects"})
    assert checkpoint.projects[0].status == "unavailable"
    assert checkpoint.projects[0].snapshot is not None
    assert snapshot_of(checkpoint.projects[0]).issues[0].title == "Last good"
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
    unavailable_snapshot = snapshot_of(available).model_copy(
        update={
            "collected_at": "2026-08-27T04:00:00Z",
            "issue_source_status": "unavailable",
            "issue_source_attempted_at": "2026-08-27T04:00:00Z",
            "issue_source_last_good_at": None,
            "issues": (),
            "observation_targets": (
                ObservationTarget(
                    path="/current-target",
                    head="def456",
                    branch="main",
                    detached=False,
                    dirty=True,
                    availability="available",
                    elapsed_ms=2,
                    diagnostics=[],
                    role="main",
                ),
            ),
            "diagnostics": (
                Diagnostic(
                    source="github",
                    severity="error",
                    message="GitHub unavailable",
                    code="github-command",
                ),
            ),
        }
    )
    unavailable = available.model_copy(
        update={"status": "fresh", "snapshot": unavailable_snapshot}
    )

    store.replace(workspace(unavailable, runs=[observed_run], issue_runs={}))
    accepted = store.checkpoint().projects[0]

    assert accepted.status == "stale"
    accepted_snapshot = snapshot_of(accepted)
    assert accepted_snapshot.issue_source_status == "stale"
    assert accepted_snapshot.issues[0].title == "Last good"
    assert accepted_snapshot.issue_source_last_good_at == NOW
    assert accepted_snapshot.issue_source_attempted_at == "2026-08-27T04:00:00Z"
    assert accepted_snapshot.collected_at == "2026-08-27T04:00:00Z"
    assert accepted_snapshot.observation_targets[0].path == "/current-target"
    assert accepted_snapshot.diagnostics == unavailable_snapshot.diagnostics
    assert store.query_issues().rows[0].observed_runs == (observed_run,)


def test_fresh_empty_issue_source_clears_prior_issues() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    empty = available.model_copy(
        update={"snapshot": snapshot_of(available).model_copy(update={"issues": ()})}
    )

    store.replace_project(empty)

    assert store.query_issues().observed_issue_count == 0
    assert store.issue("I_one") is None


def test_source_last_good_is_not_carried_across_repository_identity_change() -> None:
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    unavailable_snapshot = snapshot_of(available).model_copy(
        update={
            "repository_id": "repository:replacement",
            "issue_source_status": "unavailable",
            "issue_source_last_good_at": None,
            "issues": (),
        }
    )
    unavailable = available.model_copy(
        update={
            "repository_id": "repository:replacement",
            "status": "unavailable",
            "snapshot": unavailable_snapshot,
        }
    )

    store.replace_project(unavailable)

    accepted = store.checkpoint().projects[0]
    assert accepted.status == "unavailable"
    assert snapshot_of(accepted).issues == ()


def test_adapter_supplied_stale_collection_remains_authoritative() -> None:
    available = project("project:one", issue("I_one", "Old"))
    store = WorkspaceObservationStore(workspace(available))
    stale_snapshot = snapshot_of(available).model_copy(
        update={
            "issue_source_status": "stale",
            "issue_source_attempted_at": "2026-08-27T04:00:00Z",
            "issues": (issue("I_one", "Adapter last good"),),
        }
    )
    stale = available.model_copy(update={"status": "stale", "snapshot": stale_snapshot})

    store.replace_project(stale)

    assert required(store.issue("I_one")).issue.title == "Adapter last good"


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
    shared = required(store.issue("I_shared", project_id="project:one"))
    assert shared.project.project_id == "project:one"
    assert len(store.checkpoint().projects) == 2


def test_change_reports_only_the_changed_project_qualified_issue() -> None:
    duplicated = issue("I_shared", "Shared identity")
    first = workspace(
        project("project:one", copy.deepcopy(duplicated)),
        project("project:two", copy.deepcopy(duplicated)),
    )
    store = WorkspaceObservationStore(first)
    changed = workspace(
        project("project:one", issue("I_shared", "Changed in one")),
        project("project:two", copy.deepcopy(duplicated)),
    )

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

    change = store.replace_agent_runs([observed_run], {"I_shared": [observed_run.id]})

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
    changed_run = observed_run.model_copy(update={"state": "running"})

    change = store.replace_agent_runs([changed_run], {"I_one": [changed_run.id]})

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
    transferred = observed_run.model_copy(update={"issue_id": "I_two"})

    change = store.replace_agent_runs([transferred], {"I_two": [transferred.id]})

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
    missing = observed_run.model_copy(update={"issue_id": "I_missing"})

    change = store.replace_agent_runs([missing], {"I_missing": [missing.id]})

    assert change.issue_keys == frozenset({("project:one", "I_one")})


def test_agent_run_observation_replaces_bindings_independently() -> None:
    selected_issue = issue("I_one", "First")
    store = WorkspaceObservationStore(workspace(project("project:one", selected_issue)))
    observed_run = run("codex:one", "project:one", "I_one")

    change = store.replace_agent_runs([observed_run], {"I_one": [observed_run.id]})
    result = store.query_issues()

    assert change.revision == result.revision == 2
    assert change.kinds == frozenset({"agent-runs"})
    assert change.project_ids == frozenset()
    assert change.issue_keys == frozenset({("project:one", "I_one")})
    assert change.agent_run_ids == frozenset({observed_run.id})
    assert result.rows[0].observed_runs == (observed_run,)
    assert store.checkpoint().issue_runs == {"I_one": (observed_run.id,)}


def test_diagnostics_are_project_qualified_without_exposing_store_state() -> None:
    observed = project("project:one").model_copy(
        update={
            "diagnostics": (
                Diagnostic(
                    source="project:one", severity="warning", message="project warning"
                ),
            )
        }
    )
    snapshot = workspace(
        observed,
        diagnostics=[
            Diagnostic(
                source="workspace", severity="warning", message="workspace warning"
            )
        ],
    )
    store = WorkspaceObservationStore(snapshot)

    diagnostics = store.diagnostics()
    with pytest.raises(pydantic.ValidationError):
        diagnostics[0].diagnostic.message = "mutated by caller"  # ty: ignore[invalid-assignment]

    assert [entry.project_label for entry in diagnostics] == [None, "One"]
    assert [entry.diagnostic.message for entry in store.diagnostics()] == [
        "workspace warning",
        "project warning",
    ]


def test_invalid_replacement_is_rejected_atomically() -> None:
    first = workspace(project("project:one", issue("I_one", "First")))
    store = WorkspaceObservationStore(first)
    duplicated = first.model_copy(
        update={"projects": (*first.projects, first.projects[0])}
    )

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
    replacement_project = project("project:one", issue("I_two", "Second"))
    replacement_run = run("codex:two", "project:one", "I_two")
    replacement_bindings = {"I_two": [replacement_run.id]}

    store.replace_project(replacement_project)
    store.replace_agent_runs([replacement_run], replacement_bindings)
    # The published values are frozen; the caller's own binding map is not,
    # and clearing it after publication must not reach the store.
    replacement_bindings["I_two"].clear()

    context = store.issue("I_two", project_id="project:one")
    assert context is not None
    assert context.issue.title == "Second"
    assert context.observed_runs[0].state == "waiting"
    assert store.checkpoint().issue_runs == {"I_two": ("codex:two",)}


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
    old_rows = {row.project.project_id: row for row in store.query_issues().rows}
    changed = project("project:one", issue("I_shared", "Changed"))

    store.replace_project(changed)

    assert required(store.detail_for(old_rows["project:one"])).issue.title == "Changed"
    assert required(store.detail_for(old_rows["project:two"])).issue.title == "Original"


def test_detail_for_unique_issue_follows_transfer_but_not_ambiguity() -> None:
    transferred = issue("I_shared", "Transfer")
    store = WorkspaceObservationStore(
        workspace(project("project:one", copy.deepcopy(transferred)))
    )
    old_row = store.query_issues().rows[0]

    store.replace(workspace(project("project:two", copy.deepcopy(transferred))))
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
    closed = issue("I_closed", "Closed navigation", state="closed")
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
        IssueListQuery(states=frozenset({"open", "closed"}), text="navigation"),
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
    # Every observation value a query returns is frozen, so a caller cannot
    # reach the store's owned state through one.
    with pytest.raises(pydantic.ValidationError):
        row.project.display_label = "Caller Project"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        snapshot_of(row.project).issues[0] = issue(  # ty: ignore[invalid-assignment]
            "I_one", "Caller Issue"
        )
    with pytest.raises(pydantic.ValidationError):
        row.observed_runs[0].state = "running"  # ty: ignore[invalid-assignment]

    current = store.query_issues().rows[0]
    checkpoint = store.checkpoint()
    assert current.project.display_label == "One"
    assert current.issue.title == "First"
    assert current.observed_runs[0].state == "waiting"
    assert checkpoint.projects[0].display_label == "One"
    assert snapshot_of(checkpoint.projects[0]).issues[0].title == "First"
    assert checkpoint.agent_runs[0].state == "waiting"
