"""Pin the headless JSON contract per command, independently of model defaults.

Every key set here is the documented first-release contract (#78): a key
added to or dropped from a model shows up as a failure in this module, and
an unknown value is asserted to be an explicit ``null``, never an omission.
"""

from __future__ import annotations

import json

from dashpot.model import Branch, Diagnostic, IssueActivity, LinkedPullRequest
from dashpot.serialization import (
    issue_document,
    removability_document,
    render_json,
    snapshot_document,
    worktree_plan_document,
)
from dashpot.worktrees import RemovalObstacle, WorktreePlan, WorktreeRemovability
from factories import agent_run, project, target, workspace
from helpers import make_issue

SNAPSHOT_KEYS = {
    "collectedAt",
    "elapsedMs",
    "projects",
    "agentRuns",
    "issueRuns",
    "diagnostics",
}
PROJECT_OBSERVATION_KEYS = {
    "projectId",
    "displayLabel",
    "repositoryId",
    "workspaces",
    "anchors",
    "primaryAnchor",
    "status",
    "elapsedMs",
    "snapshot",
    "diagnostics",
}
PROJECT_SNAPSHOT_KEYS = {
    "projectId",
    "displayLabel",
    "repositoryId",
    "collectedAt",
    "issueSourceStatus",
    "issueSourceAttemptedAt",
    "issueSourceLastGoodAt",
    "observationTargets",
    "issues",
    "diagnostics",
    "targetStatus",
    "targetAttemptedAt",
    "targetLastGoodAt",
    "labelColors",
    "branches",
    "fetchedAt",
    "branchAnchor",
    "integrationRef",
    "issueActivity",
}
OBSERVATION_TARGET_KEYS = {
    "path",
    "head",
    "branch",
    "detached",
    "dirty",
    "availability",
    "elapsedMs",
    "diagnostics",
    "role",
}
BRANCH_KEYS = {
    "refname",
    "name",
    "remote",
    "head",
    "committedAt",
    "upstream",
    "ahead",
    "behind",
    "upstreamGone",
    "checkedOutAt",
    "unintegratedCommits",
    "contentIntegrated",
}
AGENT_RUN_KEYS = {
    "id",
    "harness",
    "processOrSession",
    "state",
    "observationTarget",
    "observationProjectId",
    "branch",
    "issueId",
    "issueReferenceHint",
    "workingDirectory",
    "lastActivityAt",
    "turnStartedAt",
    "startedAt",
}
DIAGNOSTIC_KEYS = {"source", "severity", "message", "code"}
ISSUE_ACTIVITY_KEYS = {"commentCount", "linkedPullRequests", "unlistedPullRequestCount"}
LINKED_PULL_REQUEST_KEYS = {"number", "url", "state"}
ISSUE_PROFILE_KEYS = {
    "id",
    "projectId",
    "number",
    "reference",
    "title",
    "body",
    "state",
    "stateReason",
    "labels",
    "assignees",
    "author",
    "issueType",
    "milestone",
    "relationships",
    "createdAt",
    "updatedAt",
    "closedAt",
    "origin",
    "location",
}
WORKTREE_PLAN_KEYS = {
    "issueId",
    "issueReference",
    "path",
    "branch",
    "baseRef",
    "baseSource",
    "baseCommit",
    "worktreeRoot",
    "worktreeRootSource",
    "dryRun",
    "created",
    "refusals",
    "hints",
    "warnings",
}
REMOVABILITY_KEYS = {
    "path",
    "branch",
    "head",
    "role",
    "removable",
    "obstacles",
    "removeCommands",
}
REMOVAL_OBSTACLE_KEYS = {"kind", "detail", "command"}


def test_the_snapshot_document_pins_every_nested_shape() -> None:
    branch = Branch(
        refname="refs/heads/main",
        name="main",
        remote=None,
        head="abc123",
        committed_at="2026-08-24T15:00:00Z",
    )
    issue = make_issue(id="I_one")
    observation = project(
        "project:one",
        issue,
        targets=[target("/project:one", branch=None)],
        branches=[branch],
        diagnostics=[Diagnostic(source="s", severity="info", message="m")],
    )
    snapshot = observation.snapshot
    assert snapshot is not None
    observation = observation.model_copy(
        update={
            "snapshot": snapshot.model_copy(
                update={
                    "issue_activity": {
                        "I_one": IssueActivity(
                            linked_pull_requests=[
                                LinkedPullRequest(number=1, url="u", state="open")
                            ]
                        )
                    }
                }
            )
        }
    )
    run = agent_run("codex:one", "project:one", branch=None, last_activity_at=None)

    document = snapshot_document(workspace(observation, runs=[run]))

    assert set(document) == SNAPSHOT_KEYS
    (project_document,) = document["projects"]
    assert set(project_document) == PROJECT_OBSERVATION_KEYS
    project_snapshot = project_document["snapshot"]
    assert set(project_snapshot) == PROJECT_SNAPSHOT_KEYS
    (target_document,) = project_snapshot["observationTargets"]
    assert set(target_document) == OBSERVATION_TARGET_KEYS
    (branch_document,) = project_snapshot["branches"]
    assert set(branch_document) == BRANCH_KEYS
    (issue_profile,) = project_snapshot["issues"]
    assert set(issue_profile) == ISSUE_PROFILE_KEYS
    (diagnostic,) = project_snapshot["diagnostics"]
    assert set(diagnostic) == DIAGNOSTIC_KEYS
    activity = project_snapshot["issueActivity"]["I_one"]
    assert set(activity) == ISSUE_ACTIVITY_KEYS
    (pull_request,) = activity["linkedPullRequests"]
    assert set(pull_request) == LINKED_PULL_REQUEST_KEYS
    (run_document,) = document["agentRuns"]
    assert set(run_document) == AGENT_RUN_KEYS


def test_unknown_values_are_explicit_nulls_not_omitted_keys() -> None:
    observation = project("project:one", targets=[target("/project:one", branch=None)])
    run = agent_run("codex:one", "project:one", branch=None, last_activity_at=None)

    document = snapshot_document(workspace(observation, runs=[run]))

    (target_document,) = document["projects"][0]["snapshot"]["observationTargets"]
    assert target_document["branch"] is None
    (run_document,) = document["agentRuns"]
    assert run_document["issueId"] is None
    assert run_document["lastActivityAt"] is None
    assert run_document["turnStartedAt"] is None
    assert document["projects"][0]["snapshot"]["fetchedAt"] is None
    assert document["projects"][0]["snapshot"]["targetAttemptedAt"] is None


def test_a_missing_project_snapshot_is_an_explicit_null() -> None:
    document = snapshot_document(workspace(project("project:one", missing=True)))

    assert document["projects"][0]["snapshot"] is None
    assert document["projects"][0]["status"] == "unavailable"


def test_the_issue_document_is_the_profile_on_the_wire() -> None:
    issue = make_issue(milestone=None, closedAt=None)

    document = issue_document(issue)

    assert set(document) == ISSUE_PROFILE_KEYS
    assert document["milestone"] is None
    assert document["closedAt"] is None
    assert set(document["relationships"]) == {
        "parent",
        "subIssues",
        "blockedBy",
        "blocking",
    }


def test_the_worktree_plan_document_keeps_its_keys_and_nulls() -> None:
    plan = WorktreePlan(
        issue_id="I_35",
        issue_reference="ned2/dashpot#35",
        path="/w/x",
        branch="35-x",
        base_ref=None,
        base_source=None,
        base_commit=None,
        worktree_root="/w",
        worktree_root_source="default-sibling",
        dry_run=True,
        refusals=["no base"],
    )

    document = worktree_plan_document(plan)

    assert set(document) == WORKTREE_PLAN_KEYS
    assert document["baseRef"] is None
    assert document["baseCommit"] is None
    assert document["refusals"] == ["no base"]
    assert document["hints"] == []
    assert document["created"] is False


def test_the_removability_document_keeps_its_keys_and_nulls() -> None:
    report = WorktreeRemovability(
        path="/w/x",
        branch=None,
        head="abc",
        role="linked",
        removable=False,
        obstacles=[RemovalObstacle(kind="dirty", detail="1 path")],
    )

    document = removability_document(report)

    assert set(document) == REMOVABILITY_KEYS
    assert document["branch"] is None
    (obstacle,) = document["obstacles"]
    assert set(obstacle) == REMOVAL_OBSTACLE_KEYS
    assert obstacle["command"] is None
    assert document["removeCommands"] == []


def test_render_json_is_indented_unless_compact() -> None:
    document = {"a": None, "b": [1]}

    assert render_json(document) == json.dumps(document, indent=2)
    assert render_json(document, compact=True) == '{"a": null, "b": [1]}'
