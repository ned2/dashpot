"""Pin the headless JSON contract per command, independently of model defaults.

Every key set here is the documented first-release contract (#78): a key
added to or dropped from a model shows up as a failure in this module, and
an unknown value is asserted to be an explicit ``null``, never an omission.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dashpot.core.event_log_files import (
    EventLogFileRemoval,
    EventLogReading,
    EventLogRemoval,
    UnreadableEventLog,
)
from dashpot.core.model import Branch, Diagnostic, IssueActivity, LinkedPullRequest
from dashpot.core.runtime_events import (
    CommandAttributes,
    ProcessIdentity,
    ProcessStart,
    RuntimeEvent,
    SpanEnded,
)
from dashpot.queries.source_queries import PageObservation, QueryRequest
from dashpot.repository.cleanup import CleanupBlocker
from dashpot.repository.worktrees.create import WorktreePlan
from dashpot.repository.worktrees.removability import WorktreeRemovability
from dashpot.serialization import (
    event_log_reading_document,
    event_log_removal_document,
    issue_document,
    list_page_document,
    removability_document,
    render_json,
    snapshot_document,
    worktree_plan_document,
)
from factories import agent_run, project, pull_request, target, workspace
from helpers import make_issue
from test_source_queries import markdown

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
    "pullRequestStatus",
    "pullRequestAttemptedAt",
    "pullRequestLastGoodAt",
    "pullRequests",
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
    "orphaned",
    "hostRestarted",
}
DIAGNOSTIC_KEYS = {"source", "severity", "message", "code"}
ISSUE_ACTIVITY_KEYS = {"commentCount", "linkedPullRequests", "unlistedPullRequestCount"}
LINKED_PULL_REQUEST_KEYS = {"number", "url", "state"}
PULL_REQUEST_KEYS = {
    "id",
    "number",
    "title",
    "url",
    "state",
    "isDraft",
    "headBranch",
    "baseBranch",
    "author",
    "reviewDecision",
    "checkStatus",
    "mergeability",
    "createdAt",
    "updatedAt",
}
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
    "mainWorktree",
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
LIST_PAGE_KEYS = {"page", "totals"}
OBSERVATION_FACT_KEYS = {"status", "attemptedAt", "lastGoodAt", "diagnostics"}
QUERY_PAGE_KEYS = OBSERVATION_FACT_KEYS | {
    "context",
    "request",
    "effectiveOrdering",
    "issues",
    "pullRequests",
    "auxiliary",
    "returnedCount",
    "matchedCount",
    "nextCursor",
    "continuation",
    "resultLimit",
}
AUXILIARY_OBSERVATION_KEYS = OBSERVATION_FACT_KEYS | {
    "activity",
    "labelColors",
    "openBlockers",
}
OPEN_BLOCKER_KEYS = {"id", "reference", "number"}
PROJECT_TOTALS_KEYS = OBSERVATION_FACT_KEYS | {
    "context",
    "kind",
    "openCount",
    "closedCount",
}
SOURCE_CONTEXT_KEYS = {
    "projectId",
    "repositoryId",
    "source",
    "location",
    "principal",
    "revision",
    "configuration",
}
QUERY_REQUEST_KEYS = {"kind", "query", "state", "ordering", "pageSize", "cursor"}
EVENT_LOG_READING_KEYS = {"directories", "events", "unreadable"}
UNREADABLE_EVENT_LOG_KEYS = {"path", "lines", "error"}
# Every Runtime Event keeps its Event Log field names, and every field its
# kind has, known or not.
RUNTIME_EVENT_KEYS = {
    "schema",
    "time",
    "dashpot.level",
    "event.name",
    "service.instance.id",
    "dashpot.process.kind",
    "dashpot.agent_session.harness",
    "dashpot.agent_session.id",
    "dashpot.project.id",
    "dashpot.worktree.path",
    "dashpot.issue.id",
}
PROCESS_FACT_KEYS = {
    "service.version",
    "dashpot.install.kind",
    "vcs.ref.head.revision",
    "dashpot.source.dirty",
    "process.pid",
    "process.runtime.version",
    "process.working_directory",
    "dashpot.subcommand",
}
SPAN_KEYS = {
    "dashpot.span.name",
    "span_id",
    "parent_span_id",
    "dashpot.duration_seconds",
    "otel.status_code",
    "error.type",
    "attributes",
}
COMMAND_ATTRIBUTE_KEYS = {
    "process.executable.name",
    "dashpot.command.subcommand",
    "process.exit.code",
}
EVENT_LOG_REMOVAL_KEYS = {
    "directory",
    "before",
    "today",
    "dryRun",
    "files",
    "succeeded",
}
EVENT_LOG_FILE_REMOVAL_KEYS = {"path", "day", "sizeBytes", "outcome", "error"}


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
        pull_requests=[
            pull_request(
                83,
                author=None,
                review_decision=None,
                check_status=None,
                mergeability=None,
            )
        ],
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

    baseline = Path(__file__).parent / "fixtures" / "workspace-snapshot.json"
    assert render_json(document) + "\n" == baseline.read_text()
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
    (linked_pull_request,) = activity["linkedPullRequests"]
    assert set(linked_pull_request) == LINKED_PULL_REQUEST_KEYS
    (repository_pull_request,) = project_snapshot["pullRequests"]
    assert set(repository_pull_request) == PULL_REQUEST_KEYS
    assert repository_pull_request["author"] is None
    assert repository_pull_request["reviewDecision"] is None
    assert repository_pull_request["checkStatus"] is None
    assert repository_pull_request["mergeability"] is None
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
    assert document["projects"][0]["snapshot"]["pullRequests"] == []


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
        main_worktree="/w/x-main",
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
        obstacles=[CleanupBlocker(kind="dirty", detail="1 path")],
    )

    document = removability_document(report)

    assert set(document) == REMOVABILITY_KEYS
    assert document["branch"] is None
    (obstacle,) = document["obstacles"]
    assert set(obstacle) == REMOVAL_OBSTACLE_KEYS
    assert obstacle["command"] is None
    assert document["removeCommands"] == []


def test_the_list_page_document_keeps_its_keys_and_nulls(tmp_path: Path) -> None:
    source = markdown(tmp_path)
    page = source.query_page(QueryRequest(kind="issues", page_size=1)).page
    # A Markdown Project has no Pull Requests, so their totals are all nulls.
    totals = source.query_page(QueryRequest(kind="pull-requests")).totals

    document = list_page_document(PageObservation(page, totals))

    assert set(document) == LIST_PAGE_KEYS
    page_document = document["page"]
    assert set(page_document) == QUERY_PAGE_KEYS
    assert set(page_document["context"]) == SOURCE_CONTEXT_KEYS
    assert set(page_document["request"]) == QUERY_REQUEST_KEYS
    assert page_document["request"]["cursor"] is None
    assert page_document["pullRequests"] == []
    (issue_profile,) = page_document["issues"]
    assert set(issue_profile) == ISSUE_PROFILE_KEYS
    auxiliary = page_document["auxiliary"][issue_profile["id"]]
    assert set(auxiliary) == AUXILIARY_OBSERVATION_KEYS
    # A Local Issue has no engagement; its blockers are not local Issues, so
    # each counts as open and is named by its identity alone.
    assert auxiliary["activity"] is None
    assert [set(blocker) for blocker in auxiliary["openBlockers"]] == [
        OPEN_BLOCKER_KEYS,
        OPEN_BLOCKER_KEYS,
    ]
    assert auxiliary["openBlockers"][0] == {
        "id": "I_blocker_1",
        "reference": None,
        "number": None,
    }
    assert page_document["resultLimit"] is None
    assert page_document["lastGoodAt"] is not None
    totals_document = document["totals"]
    assert set(totals_document) == PROJECT_TOTALS_KEYS
    assert totals_document["kind"] == "pull-requests"
    assert totals_document["status"] == "unavailable"
    assert totals_document["openCount"] is None
    assert totals_document["lastGoodAt"] is None


def test_the_events_document_keeps_each_events_log_field_names_and_nulls() -> None:
    process = ProcessIdentity(run_id="a" * 32, kind="command:work-start")
    reading = EventLogReading(
        directories=["/w/x/.dashpot/state/events"],
        events=[
            RuntimeEvent(
                time="2026-09-27T12:00:00.000000Z",
                level="standard",
                process=process,
                body=ProcessStart(
                    version="0.1.0",
                    install_kind="wheel",
                    revision="unknown",
                    pid=42,
                    python_version="3.14.0",
                ),
            ),
            RuntimeEvent(
                time="2026-09-27T12:00:01.000000Z",
                level="full",
                process=process,
                body=SpanEnded(
                    span_name="command",
                    span_id="b" * 16,
                    duration_seconds=0.5,
                    status="OK",
                    attributes=CommandAttributes(program="git"),
                ),
            ),
        ],
        unreadable=[UnreadableEventLog(path="/w/x/events-2026-09-27.jsonl")],
    )

    document = event_log_reading_document(reading)

    assert set(document) == EVENT_LOG_READING_KEYS
    start, span = document["events"]
    assert set(start) == RUNTIME_EVENT_KEYS | PROCESS_FACT_KEYS
    assert start["dashpot.agent_session.id"] is None
    assert start["dashpot.source.dirty"] is None
    assert set(span) == RUNTIME_EVENT_KEYS | SPAN_KEYS
    assert span["parent_span_id"] is None
    assert set(span["attributes"]) == COMMAND_ATTRIBUTE_KEYS
    assert span["attributes"]["process.exit.code"] is None
    (unreadable,) = document["unreadable"]
    assert unreadable == {
        "path": "/w/x/events-2026-09-27.jsonl",
        "lines": [],
        "error": None,
    }


def test_the_events_remove_document_keeps_its_keys_and_nulls() -> None:
    removal = EventLogRemoval(
        directory="/w/x/.dashpot/state/events",
        before=date(2026, 9, 1),
        today=date(2026, 9, 27),
        dry_run=False,
        files=[
            EventLogFileRemoval(
                path="/w/x/.dashpot/state/events/events-2026-08-01.jsonl",
                day=date(2026, 8, 1),
                size_bytes=None,
                outcome="already-absent",
            )
        ],
    )

    document = event_log_removal_document(removal)

    assert set(document) == EVENT_LOG_REMOVAL_KEYS
    assert document["before"] == "2026-09-01"
    assert document["succeeded"] is True
    (file,) = document["files"]
    assert set(file) == EVENT_LOG_FILE_REMOVAL_KEYS
    assert file["sizeBytes"] is None
    assert file["error"] is None


def test_render_json_is_indented_unless_compact() -> None:
    document = {"a": None, "b": [1]}

    assert render_json(document) == json.dumps(document, indent=2)
    assert render_json(document, compact=True) == '{"a": null, "b": [1]}'


def test_pull_request_history_serializes_each_lifecycle_without_collapsing_merged() -> (
    None
):
    observation = project(
        "project:one",
        pull_requests=[
            pull_request(index, state=state, is_draft=draft)
            for index, (state, draft) in enumerate(
                [("open", True), ("closed", True), ("merged", False)], start=1
            )
        ],
    )
    document = snapshot_document(workspace(observation))
    records = document["projects"][0]["snapshot"]["pullRequests"]
    assert [(record["state"], record["isDraft"]) for record in records] == [
        ("open", True),
        ("closed", True),
        ("merged", False),
    ]
    assert all(set(record) == PULL_REQUEST_KEYS for record in records)
