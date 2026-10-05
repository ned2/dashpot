from __future__ import annotations

import copy

import pydantic
import pytest

import factories
from dashpot.core.issue_profile import IssueProfile
from dashpot.core.model import (
    AgentRun,
    Branch,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    SourceStatus,
)
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.serialization import snapshot_document
from factories import workspace
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
    pull_requests=(),
) -> ProjectObservation:
    return factories.project(
        project_id, *issues, status=status, pull_requests=pull_requests
    )


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


def test_replace_updates_indexes_revision_and_read_models() -> None:
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

    assert store.revision == 2
    assert change.agent_dependency_project_ids == frozenset({"project:one"})
    assert [row.name for row in store.query_branches().rows] == ["main"]
    assert [row.target.path for row in store.query_worktrees().rows] == ["/project:one"]
    [session] = store.query_sessions().rows
    assert session.session == observed_run
    assert required(session.issue).title == "Second"
    assert required(store.project("project:one")).display_label == "One"
    assert store.checkpoint() == second


def test_a_replaced_project_shows_what_was_published_last() -> None:
    # Retention happens before publish, where a source keeps its last good
    # observation; the store accepts the failure as published (ADR 0137).
    available = project("project:one", issue("I_one", "Last good"))
    store = WorkspaceObservationStore(workspace(available))
    unavailable = available.model_copy(
        update={
            "status": "unavailable",
            "snapshot": snapshot_of(available).model_copy(
                update={
                    "issue_source_status": "unavailable",
                    "issue_source_last_good_at": None,
                    "issues": (),
                }
            ),
        }
    )

    store.replace_project(unavailable)

    accepted = required(store.project("project:one"))
    assert accepted.status == "unavailable"
    assert snapshot_of(accepted).issue_source_status == "unavailable"
    assert snapshot_of(accepted).issues == ()


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


def test_a_pull_request_change_asks_nothing_of_the_agent_runs() -> None:
    first_pull_request = factories.pull_request(1, title="First")
    second_pull_request = factories.pull_request(1, title="Changed")
    store = WorkspaceObservationStore(
        workspace(project("project:one", pull_requests=[first_pull_request]))
    )

    change = store.replace_project(
        project("project:one", pull_requests=[second_pull_request])
    )

    assert change.agent_dependency_project_ids == frozenset()


def test_an_issue_change_asks_for_its_projects_agent_runs_only() -> None:
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", issue("I_one", "First")),
            project("project:two", issue("I_two", "Second")),
        )
    )

    change = store.replace_project(project("project:one", issue("I_one", "Changed")))

    assert change.agent_dependency_project_ids == frozenset({"project:one"})


def test_a_new_project_asks_for_the_agent_runs() -> None:
    store = WorkspaceObservationStore()

    change = store.replace_project(project("project:one"))

    assert change.agent_dependency_project_ids == frozenset({"project:one"})


def test_agent_run_observation_replaces_bindings_independently() -> None:
    selected_issue = issue("I_one", "First")
    store = WorkspaceObservationStore(workspace(project("project:one", selected_issue)))
    observed_run = run("codex:one", "project:one", "I_one")

    change = store.replace_agent_runs([observed_run], {"I_one": [observed_run.id]})

    assert store.revision == 2
    assert change.agent_dependency_project_ids == frozenset()
    [session] = store.query_sessions().rows
    assert session.session == observed_run
    assert required(session.issue).id == "I_one"
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

    assert store.revision == 2
    assert change.agent_dependency_project_ids == frozenset()


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

    [session] = store.query_sessions().rows
    assert required(session.issue).title == "Second"
    assert session.session.state == "waiting"
    assert store.checkpoint().issue_runs == {"I_two": ("codex:two",)}


def test_store_query_result_cannot_mutate_owned_observations() -> None:
    observed_run = run("codex:one", "project:one", "I_one")
    store = WorkspaceObservationStore(
        workspace(
            project("project:one", issue("I_one", "First")),
            runs=[observed_run],
            issue_runs={"I_one": [observed_run.id]},
        )
    )

    row = store.query_sessions().rows[0]
    project_row = required(row.project)
    # Every observation value a query returns is frozen, so a caller cannot
    # reach the store's owned state through one.
    with pytest.raises(pydantic.ValidationError):
        project_row.display_label = "Caller Project"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        snapshot_of(project_row).issues[0] = issue(  # ty: ignore[invalid-assignment]
            "I_one", "Caller Issue"
        )
    with pytest.raises(pydantic.ValidationError):
        row.session.state = "running"  # ty: ignore[invalid-assignment]

    current = store.query_sessions().rows[0]
    checkpoint = store.checkpoint()
    assert required(current.project).display_label == "One"
    assert required(current.issue).title == "First"
    assert current.session.state == "waiting"
    assert checkpoint.projects[0].display_label == "One"
    assert snapshot_of(checkpoint.projects[0]).issues[0].title == "First"
    assert checkpoint.agent_runs[0].state == "waiting"
