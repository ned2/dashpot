from __future__ import annotations

import copy
import json
import threading
import unittest
from pathlib import Path
from typing import Any

import pydantic

from dashpot.core.commands import CommandResult
from dashpot.core.issue_profile import IssueProfile, conform_issue, issue_location
from dashpot.github.github import RefreshBudget
from dashpot.github.github_issues import GitHubIssuesSource, normalize_github_issue
from dashpot.issues.issue_sources import IssueSourceRefreshError, parse_issue_hint
from issue_source_conformance import (
    assert_duplicate_identity_is_refused,
    assert_duplicate_number_is_refused,
    assert_fresh_observation,
    assert_stale_observation,
    assert_unavailable_observation,
)

ROOT = Path(__file__).parents[1]
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "github-issue.json"
EXPECTED_FIXTURE = ROOT / "conformance" / "issue" / "fixtures" / "github.json"
PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"
REPOSITORY_ID = "R_kgDOUEerrg"
PULL_REQUEST_MARK = "2026-08-26T07:00:00Z"


def raw_fixture() -> dict[str, Any]:
    return json.loads(RAW_FIXTURE.read_text())


def expected_fixture() -> IssueProfile:
    return conform_issue(json.loads(EXPECTED_FIXTURE.read_text()))


def normalize(record: dict[str, Any], **overrides: str) -> IssueProfile:
    return normalize_github_issue(
        record,
        project_id=overrides.get("project_id", PROJECT_ID),
        repository_id=overrides.get("repository_id", REPOSITORY_ID),
    )


def issue_record(
    number: int, *, updated_at: str | None = None, title: str | None = None
) -> dict[str, Any]:
    record = raw_fixture()
    record["id"] = f"I_issue_{number}"
    record["number"] = number
    record["url"] = f"https://github.com/ned2/dashpot/issues/{number}"
    if updated_at is not None:
        record["updatedAt"] = updated_at
    if title is not None:
        record["title"] = title
    return record


def related(record: dict[str, Any], connection: str, *ids: str) -> dict[str, Any]:
    record[connection] = {
        "nodes": [{"id": issue_id} for issue_id in ids],
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    }
    return record


def unrelated(record: dict[str, Any]) -> dict[str, Any]:
    record["parent"] = None
    for connection in ("subIssues", "blockedBy", "blocking"):
        related(record, connection)
    return record


def probe_response(
    total_count: int,
    newest_updated_at: str | None,
    *,
    repository_id: str = REPOSITORY_ID,
    pull_request_updated_at: str | None = None,
) -> str:
    nodes = (
        []
        if newest_updated_at is None
        else [{"id": "I_newest", "updatedAt": newest_updated_at}]
    )
    return json.dumps(
        {
            "data": {
                "node": {
                    "id": repository_id,
                    "nameWithOwner": "ned2/dashpot",
                    "issues": {"totalCount": total_count, "nodes": nodes},
                    "pullRequests": {
                        "nodes": (
                            []
                            if pull_request_updated_at is None
                            else [{"updatedAt": pull_request_updated_at}]
                        )
                    },
                }
            }
        }
    )


def nodes_response(nodes: list[dict[str, Any] | None]) -> CommandResult:
    """A ``nodes(ids:)`` answer as gh relays it: exit 1 whenever one is missing."""
    errors = [
        {
            "type": "NOT_FOUND",
            "path": ["nodes", index],
            "message": "Could not resolve to a node with the given global id",
        }
        for index, node in enumerate(nodes)
        if node is None
    ]
    payload: dict[str, Any] = {"data": {"nodes": nodes}}
    if errors:
        payload["errors"] = errors
    return completed(
        stdout=json.dumps(payload),
        stderr="gh: Could not resolve to a node" if errors else "",
        returncode=1 if errors else 0,
    )


def by_id(record: dict[str, Any]) -> dict[str, Any]:
    return {"__typename": "Issue", **record}


class RoutedRunner:
    """Answer identity lookups from a map and everything else in sequence.

    Lookups are answered concurrently, so they are routed by the identities
    asked rather than taken in turn; ``hold_until_active`` keeps each lookup
    waiting until that many run at once, which measures the concurrency.
    """

    def __init__(
        self,
        results: list[CommandResult | Exception],
        by_id: dict[str, dict[str, Any] | None],
        *,
        hold_until_active: int = 0,
    ) -> None:
        self.results = iter(results)
        self.by_id = by_id
        self.calls: list[tuple[list[str], Path, float]] = []
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.hold_until_active = hold_until_active
        self.released = threading.Event()
        if not hold_until_active:
            self.released.set()

    def lookups(self) -> list[list[str]]:
        return [ids for call in self.calls if (ids := _asked_ids(call[0]))]

    def __call__(self, args, cwd, timeout):
        ids = _asked_ids(args)
        with self.lock:
            self.calls.append((list(args), cwd, timeout))
            if ids:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.active >= self.hold_until_active:
                    self.released.set()
        if not ids:
            with self.lock:
                result = next(self.results)
            if isinstance(result, Exception):
                raise result
            return result
        self.released.wait(timeout=2)
        with self.lock:
            self.active -= 1
        return nodes_response([self.by_id.get(issue_id) for issue_id in ids])


def _asked_ids(args: list[str]) -> list[str]:
    return [arg.removeprefix("ids[]=") for arg in args if arg.startswith("ids[]=")]


def issue_page(
    nodes: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
    repository_id: str = REPOSITORY_ID,
    repository_reference: str = "ned2/dashpot",
    pull_request_updated_at: str | None = None,
    probe: str | None = None,
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "id": repository_id,
                    "nameWithOwner": repository_reference,
                    **(
                        {"probeIssues": json.loads(probe)["data"]["node"]["issues"]}
                        if probe
                        else {}
                    ),
                    "issues": {
                        "nodes": nodes,
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    },
                    "pullRequests": {
                        "nodes": (
                            []
                            if pull_request_updated_at is None
                            else [{"updatedAt": pull_request_updated_at}]
                        )
                    },
                }
            }
        }
    )


def pull_request_changes_page(
    nodes: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
    probe: str | None = None,
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "id": REPOSITORY_ID,
                    "nameWithOwner": "ned2/dashpot",
                    **(
                        {"issues": json.loads(probe)["data"]["node"]["issues"]}
                        if probe
                        else {}
                    ),
                    "pullRequests": {
                        "nodes": nodes,
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    },
                }
            }
        }
    )


def pull_request_change(
    number: int, updated_at: str, *closing_issue_ids: str
) -> dict[str, Any]:
    return {
        "id": f"PR_{number}",
        "number": number,
        "updatedAt": updated_at,
        "closingIssuesReferences": {
            "nodes": [{"id": issue_id} for issue_id in closing_issue_ids],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }


def with_linked_pull_requests(
    record: dict[str, Any], *pull_requests: tuple[int, str]
) -> dict[str, Any]:
    record["closedByPullRequestsReferences"] = {
        "totalCount": len(pull_requests),
        "nodes": [
            {
                "number": number,
                "url": f"https://github.com/ned2/dashpot/pull/{number}",
                "state": state,
            }
            for number, state in pull_requests
        ],
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    }
    return record


def nested_page(
    nodes: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "connection": {
                        "nodes": nodes,
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    }
                }
            }
        }
    )


def linked_pull_request_page(
    nodes: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "closedByPullRequestsReferences": {
                        "nodes": nodes,
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    }
                }
            }
        }
    )


def issue_response(
    node: dict[str, Any] | None,
    *,
    repository_id: str = REPOSITORY_ID,
    repository_reference: str = "ned2/dashpot",
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "id": repository_id,
                    "nameWithOwner": repository_reference,
                    "issue": node,
                }
            }
        }
    )


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult([], returncode, stdout, stderr)


class SequenceRunner:
    def __init__(self, results: list[CommandResult | Exception]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[list[str], Path, float]] = []

    def __call__(self, args, cwd, timeout):
        self.calls.append((list(args), cwd, timeout))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def source(
    runner: SequenceRunner | RoutedRunner,
    timestamps: list[str] | None = None,
    *,
    budget: RefreshBudget | None = None,
    monotonic: Any = None,
    root: Path = Path("/repo"),
) -> GitHubIssuesSource:
    stamps = timestamps or ["2026-08-26T10:00:00Z"]
    times = iter(stamps)
    return GitHubIssuesSource(
        root,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        runner=runner,
        # A refresh past the scripted stamps keeps the last one.
        clock=lambda: next(times, stamps[-1]),
        budget=budget or RefreshBudget(),
        monotonic=monotonic,
    )


def query_of(call: tuple[list[str], Path, float]) -> str:
    return call[0][4]


def _linked_numbers(observation: Any, issue_id: str) -> set[int]:
    return {
        pull_request.number
        for pull_request in observation.issue_activity[issue_id].linked_pull_requests
    }


def graphql_failure(type: str, path: list[str], message: str) -> CommandResult:
    """The shape a real ``gh api graphql`` failure takes: body first, prose after."""
    body = json.dumps(
        {
            "data": {"node": None},
            "errors": [{"type": type, "path": path, "message": message}],
        }
    )
    return completed(stdout=body, stderr=f"gh: {message}", returncode=1)


def with_rate_limit(response: str, remaining: int, limit: int = 5000) -> str:
    payload = json.loads(response)
    payload["data"]["rateLimit"] = {
        "cost": 6,
        "limit": limit,
        "remaining": remaining,
        "resetAt": "2026-08-26T11:00:00Z",
    }
    return json.dumps(payload)


class GitHubIssueNormalizerTests(unittest.TestCase):
    def test_complete_graphql_issue_matches_the_conformance_fixture(self) -> None:
        self.assertEqual(expected_fixture(), normalize(raw_fixture()))

    def test_plural_assignees_and_all_relationships_are_preserved(self) -> None:
        issue = normalize(raw_fixture())

        self.assertEqual(("ned2", "octocat"), issue.assignees)
        self.assertEqual("I_parent_1", issue.relationships.parent)
        self.assertEqual(("I_child_1", "I_child_2"), issue.relationships.sub_issues)
        self.assertEqual(("I_blocker_1", "I_blocker_2"), issue.relationships.blocked_by)
        self.assertEqual(("I_blocked_1", "I_blocked_2"), issue.relationships.blocking)

    def test_repository_rename_changes_reference_not_identity(self) -> None:
        before = normalize(raw_fixture())
        renamed = raw_fixture()
        renamed["repository"]["nameWithOwner"] = "open-dashpot/dashpot"
        renamed["url"] = "https://github.com/open-dashpot/dashpot/issues/9"

        after = normalize(renamed)

        self.assertEqual(before.id, after.id)
        self.assertEqual(before.project_id, after.project_id)
        self.assertEqual(before.number, after.number)
        self.assertEqual("open-dashpot/dashpot#9", after.reference)
        assert after.location.kind == "github"
        self.assertEqual(renamed["url"], after.location.url)

    def test_transfer_preserves_issue_identity_and_changes_membership(self) -> None:
        before = normalize(raw_fixture())
        transferred = raw_fixture()
        transferred["number"] = 41
        transferred["url"] = "https://github.com/open-dashpot/operations/issues/41"
        transferred["repository"] = {
            "id": "R_operations",
            "nameWithOwner": "open-dashpot/operations",
        }

        after = normalize(
            transferred,
            project_id="project:operations",
            repository_id="R_operations",
        )

        self.assertEqual(before.id, after.id)
        self.assertEqual("project:operations", after.project_id)
        self.assertEqual(41, after.number)
        self.assertEqual("open-dashpot/operations#41", after.reference)
        assert after.origin.kind == "github"
        self.assertEqual("R_operations", after.origin.repository_id)

    def test_number_must_be_a_positive_integer(self) -> None:
        for invalid in (None, 0, -1, "9", 9.0, True):
            with self.subTest(invalid=invalid):
                record = raw_fixture()
                record["number"] = invalid
                with self.assertRaisesRegex(
                    IssueSourceRefreshError,
                    "number must be a positive integer",
                ):
                    normalize(record)

    def test_conflicting_configured_repository_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            IssueSourceRefreshError, "does not match the configured"
        ):
            normalize(raw_fixture(), repository_id="R_another_repository")

    def test_incomplete_nested_connections_are_rejected(self) -> None:
        for field in ("labels", "assignees", "subIssues", "blockedBy", "blocking"):
            with self.subTest(field=field):
                record = raw_fixture()
                record[field]["pageInfo"]["hasNextPage"] = True
                with self.assertRaisesRegex(
                    IssueSourceRefreshError, "pagination remains"
                ):
                    normalize(record)

    def test_missing_field_is_not_interpreted_as_known_absence(self) -> None:
        record = raw_fixture()
        del record["author"]

        with self.assertRaisesRegex(
            IssueSourceRefreshError, "issue.author was not fetched"
        ):
            normalize(record)

    def test_non_null_github_timestamp_cannot_be_reported_as_absent(self) -> None:
        record = raw_fixture()
        record["createdAt"] = None

        with self.assertRaisesRegex(
            IssueSourceRefreshError, "issue.createdAt must be a non-empty string"
        ):
            normalize(record)

    def test_known_absence_is_preserved_as_null_and_empty_collections(self) -> None:
        record = raw_fixture()
        record["author"] = None
        record["parent"] = None
        record["issueType"] = None
        record["milestone"] = None
        for field in ("labels", "assignees", "subIssues", "blockedBy", "blocking"):
            record[field]["nodes"] = []

        issue = normalize(record)

        self.assertIsNone(issue.author)
        self.assertIsNone(issue.relationships.parent)
        self.assertEqual((), issue.labels)
        self.assertEqual((), issue.assignees)
        self.assertEqual((), issue.relationships.blocked_by)

    def test_closed_lifecycle_values_are_normalized(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "NOT_PLANNED"
        record["closedAt"] = "2026-08-26T10:00:00Z"

        issue = normalize(record)

        self.assertEqual("closed", issue.state)
        self.assertEqual("not-planned", issue.state_reason)
        self.assertEqual(record["closedAt"], issue.closed_at)

    def test_duplicate_state_reason_is_preserved(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "DUPLICATE"
        record["closedAt"] = "2026-08-26T10:00:00Z"

        self.assertEqual("duplicate", normalize(record).state_reason)

    def test_unknown_state_reason_is_rejected_instead_of_erased(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "FUTURE_REASON"

        with self.assertRaisesRegex(
            IssueSourceRefreshError, "not supported by the Issue profile"
        ):
            normalize(record)

    def test_normalization_does_not_mutate_the_graphql_record(self) -> None:
        record = raw_fixture()
        before = copy.deepcopy(record)

        normalize(record)

        self.assertEqual(before, record)


class GitHubIssuesSourceTests(unittest.TestCase):
    def test_refresh_collects_all_profile_fields_without_a_marker_label(self) -> None:
        runner = SequenceRunner([completed(issue_page([raw_fixture()]))])

        observation = source(runner).refresh()

        assert_fresh_observation(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            expected_issues=[expected_fixture()],
        )
        query = runner.calls[0][0][4]
        self.assertIn("states: [OPEN, CLOSED]", query)
        self.assertIn("nodes { name color }", query)
        self.assertIn("comments { totalCount }", query)
        self.assertIn("closedByPullRequestsReferences", query)
        self.assertNotIn("tasks.md", query)
        activity = observation.issue_activity[observation.issues[0].id]
        self.assertEqual(3, activity.comment_count)
        self.assertEqual(
            [(12, "open"), (41, "merged")],
            [(pull.number, pull.state) for pull in activity.linked_pull_requests],
        )
        self.assertEqual(
            "https://github.com/ned2/dashpot/pull/41",
            activity.linked_pull_requests[1].url,
        )
        self.assertEqual(0, activity.unlisted_pull_request_count)

    def test_pull_requests_beyond_the_first_twenty_are_counted(self) -> None:
        record = raw_fixture()
        record["closedByPullRequestsReferences"] = {
            "totalCount": 23,
            "nodes": [
                {
                    "number": number,
                    "url": f"https://github.com/ned2/dashpot/pull/{number}",
                    "state": "MERGED",
                }
                for number in range(1, 21)
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "linked-20"},
        }
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(
                    linked_pull_request_page(
                        [
                            {
                                "number": number,
                                "url": (
                                    f"https://github.com/ned2/dashpot/pull/{number}"
                                ),
                                "state": "MERGED",
                            }
                            for number in range(21, 24)
                        ]
                    )
                ),
            ]
        )

        observation = source(runner).refresh()

        self.assertIn(
            "totalCount\n            nodes { number url state }", runner.calls[0][0][4]
        )
        activity = observation.issue_activity[observation.issues[0].id]
        self.assertEqual(20, len(activity.linked_pull_requests))
        self.assertEqual(3, activity.unlisted_pull_request_count)
        self.assertIn("cursor=linked-20", runner.calls[1][0])
        self.assertIn("includeClosedPrs: true", query_of(runner.calls[1]))
        self.assertEqual(
            {
                "priority/P1": "b60205",
                "enhancement": "a2eeef",
                "needs-triage": "ededed",
            },
            observation.label_colors,
        )
        self.assertIn(f"repositoryId={REPOSITORY_ID}", runner.calls[0][0])
        self.assertNotIn("owner=ned2", runner.calls[0][0])

    def test_outer_pagination_collects_more_than_two_hundred_issues(self) -> None:
        runner = SequenceRunner(
            [
                completed(
                    issue_page(
                        [issue_record(number) for number in range(1, 101)],
                        has_next_page=True,
                        end_cursor="issues-100",
                    )
                ),
                completed(
                    issue_page(
                        [issue_record(number) for number in range(101, 201)],
                        has_next_page=True,
                        end_cursor="issues-200",
                    )
                ),
                completed(issue_page([issue_record(201)])),
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual(201, len(observation.issues))
        self.assertEqual("I_issue_1", observation.issues[0].id)
        self.assertEqual("I_issue_201", observation.issues[-1].id)
        self.assertEqual(3, len(runner.calls))
        self.assertIn("cursor=issues-100", runner.calls[1][0])
        self.assertIn("cursor=issues-200", runner.calls[2][0])

    def test_duplicate_issue_identity_fails_the_whole_collection(self) -> None:
        first = issue_record(9)
        second = issue_record(10)
        second["id"] = first["id"]
        runner = SequenceRunner([completed(issue_page([first, second]))])

        observation = source(runner).refresh()

        assert_duplicate_identity_is_refused(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-duplicate-identity",
            issue_id="I_issue_9",
            seen_at=(
                "https://github.com/ned2/dashpot/issues/9",
                "https://github.com/ned2/dashpot/issues/10",
            ),
        )

    def test_duplicate_issue_number_fails_the_whole_collection(self) -> None:
        first = issue_record(9)
        second = issue_record(9)
        second["id"] = "I_other_identity"
        runner = SequenceRunner([completed(issue_page([first, second]))])

        observation = source(runner).refresh()

        assert_duplicate_number_is_refused(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-duplicate-number",
            issue_number=9,
            seen_at=(
                "https://github.com/ned2/dashpot/issues/9",
                "https://github.com/ned2/dashpot/issues/9",
            ),
        )

    def test_repeated_outer_cursor_is_a_pagination_diagnostic(self) -> None:
        runner = SequenceRunner(
            [
                completed(
                    issue_page(
                        [issue_record(1)],
                        has_next_page=True,
                        end_cursor="issues-1",
                    )
                ),
                completed(
                    issue_page(
                        [issue_record(2)],
                        has_next_page=True,
                        end_cursor="issues-1",
                    )
                ),
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-pagination", observation.diagnostics[0].code)

    def test_every_nested_connection_is_completed_before_normalizing(self) -> None:
        cases = {
            "labels": ("name", "first-label", "later-label"),
            "assignees": ("login", "first-user", "later-user"),
            "subIssues": ("id", "I_first_child", "I_later_child"),
            "blockedBy": ("id", "I_first_blocker", "I_later_blocker"),
            "blocking": ("id", "I_first_blocked", "I_later_blocked"),
        }
        for connection_name, (item_field, first, later) in cases.items():
            with self.subTest(connection=connection_name):
                record = raw_fixture()
                record[connection_name]["nodes"] = [{item_field: first}]
                record[connection_name]["pageInfo"] = {
                    "hasNextPage": True,
                    "endCursor": f"{connection_name}-1",
                }
                runner = SequenceRunner(
                    [
                        completed(issue_page([record])),
                        completed(nested_page([{item_field: later}])),
                    ]
                )

                observation = source(runner).refresh()

                self.assertEqual("fresh", observation.status)
                self.assertIn(f"cursor={connection_name}-1", runner.calls[1][0])
                self.assertIn(f"connection: {connection_name}", runner.calls[1][0][4])
                dumped = observation.issues[0].model_dump(mode="json", by_alias=True)
                if connection_name in {"labels", "assignees"}:
                    actual = dumped[connection_name]
                else:
                    actual = dumped["relationships"][connection_name]
                self.assertEqual(sorted([first, later]), actual)

    def test_label_colors_follow_nested_pagination_and_stay_out_of_the_profile(
        self,
    ) -> None:
        record = raw_fixture()
        record["labels"]["nodes"] = [
            {"name": "first-label", "color": "0E8A16"},
            {"name": "no-colour", "color": None},
            {"name": "bad-colour", "color": "#0e8a16"},
        ]
        record["labels"]["pageInfo"] = {"hasNextPage": True, "endCursor": "labels-1"}
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(nested_page([{"name": "later-label", "color": "5319e7"}])),
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertIn("nodes { name color }", runner.calls[1][0][4])
        self.assertEqual(
            {"first-label": "0e8a16", "later-label": "5319e7"},
            observation.label_colors,
        )
        self.assertEqual(
            ("bad-colour", "first-label", "later-label", "no-colour"),
            observation.issues[0].labels,
        )
        # Colors stay beside the issues: the strict profile model cannot carry
        # a labelColors field, so no dump assertion is needed (or possible).

    def test_missing_or_malformed_engagement_reads_as_none(self) -> None:
        record = raw_fixture()
        record["comments"] = {"totalCount": "three"}
        record["closedByPullRequestsReferences"] = {
            "nodes": [
                {"number": 7, "url": "", "state": "MERGED"},
                {"number": 8, "url": "https://example.test/8", "state": "DRAFT"},
                "not a node",
            ]
        }
        runner = SequenceRunner([completed(issue_page([record]))])

        observation = source(runner).refresh()

        self.assertEqual("fresh", observation.status)
        activity = observation.issue_activity[observation.issues[0].id]
        self.assertEqual(0, activity.comment_count)
        self.assertEqual((), activity.linked_pull_requests)
        # No count, or one below what was listed, leaves nothing unlisted.
        self.assertEqual(0, activity.unlisted_pull_request_count)

        bare = raw_fixture()
        del bare["comments"]
        del bare["closedByPullRequestsReferences"]
        observation = source(SequenceRunner([completed(issue_page([bare]))])).refresh()
        self.assertEqual("fresh", observation.status)
        self.assertEqual(
            0, observation.issue_activity[observation.issues[0].id].comment_count
        )

    def test_a_malformed_required_nested_connection_fails_the_refresh(self) -> None:
        record = raw_fixture()
        record["labels"] = {
            "nodes": "not an object array",
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }

        observation = source(
            SequenceRunner([completed(issue_page([record]))])
        ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-malformed-response", observation.diagnostics[0].code)

    def test_repeated_nested_cursor_is_a_pagination_diagnostic(self) -> None:
        record = raw_fixture()
        record["labels"]["pageInfo"] = {
            "hasNextPage": True,
            "endCursor": "labels-1",
        }
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(
                    nested_page(
                        [{"name": "later"}],
                        has_next_page=True,
                        end_cursor="labels-1",
                    )
                ),
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-pagination", observation.diagnostics[0].code)
        self.assertIn("repeated pagination cursor", observation.diagnostics[0].message)

    def test_initial_network_failure_is_unavailable_with_no_issues(self) -> None:
        runner = SequenceRunner(
            [completed(stderr="error connecting to api.github.com", returncode=1)]
        )

        observation = source(runner).refresh()

        assert_unavailable_observation(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-network",
        )

    def test_transport_failures_have_distinct_diagnostic_codes(self) -> None:
        cases = [
            (
                completed(stderr="HTTP 401: Bad credentials", returncode=1),
                "github-authentication",
            ),
            (RuntimeError("command timed out after 20s: gh"), "github-timeout"),
            (RuntimeError("command not found: gh"), "github-cli-unavailable"),
            (OSError("[Errno 24] Too many open files"), "github-request"),
        ]
        for result, expected_code in cases:
            with self.subTest(code=expected_code):
                observation = source(SequenceRunner([result])).refresh()
                self.assertEqual("unavailable", observation.status)
                self.assertEqual(expected_code, observation.diagnostics[0].code)

    def test_failure_retains_last_good_issues_isolated_from_the_caller(self) -> None:
        runner = SequenceRunner(
            [
                completed(issue_page([raw_fixture()])),
                completed(stderr="API rate limit exceeded", returncode=1),
            ]
        )
        github = source(
            runner,
            ["2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"],
        )
        fresh = github.refresh()
        # The whole observation is frozen: every caller mutation is rejected,
        # so the retained last-good values need no defensive copies.
        # Each ty ignore silences the static rejection of exactly the
        # runtime mutation this test proves is refused.
        with self.assertRaises(TypeError):
            fresh.issues[0] = normalize(  # ty: ignore[invalid-assignment]
                dict(raw_fixture(), title="caller mutation")
            )
        with self.assertRaises(TypeError):
            fresh.label_colors["enhancement"] = "000000"  # ty: ignore[invalid-assignment]
        with self.assertRaises(pydantic.ValidationError):
            fresh.issue_activity[fresh.issues[0].id].comment_count = 99  # ty: ignore[invalid-assignment]

        stale = github.refresh()

        assert_stale_observation(
            self,
            stale,
            attempted_at="2026-08-26T10:01:00Z",
            last_good_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-rate-limit",
            expected_issues=[expected_fixture()],
        )
        self.assertEqual("a2eeef", stale.label_colors["enhancement"])
        self.assertEqual(3, stale.issue_activity[stale.issues[0].id].comment_count)

    def test_graphql_errors_are_diagnostics_and_partial_data_is_discarded(self) -> None:
        response = json.dumps(
            {
                "data": {"repository": {"issues": {"nodes": [raw_fixture()]}}},
                "errors": [{"message": "Resource not accessible by integration"}],
            }
        )

        observation = source(SequenceRunner([completed(response)])).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual((), observation.issues)
        self.assertEqual("github-permission", observation.diagnostics[0].code)

    def test_malformed_json_is_a_structured_diagnostic(self) -> None:
        observation = source(SequenceRunner([completed("not-json")])).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-malformed-response", observation.diagnostics[0].code)

    def test_malformed_graphql_errors_are_not_ignored(self) -> None:
        response = json.dumps({"data": {"node": {}}, "errors": "not-an-array"})

        observation = source(SequenceRunner([completed(response)])).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-malformed-response", observation.diagnostics[0].code)

    def test_repository_identity_conflict_rejects_the_collection(self) -> None:
        runner = SequenceRunner(
            [completed(issue_page([raw_fixture()], repository_id="R_fork"))]
        )

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-repository-identity", observation.diagnostics[0].code)

    def test_repository_rename_uses_current_reference_after_identity_match(
        self,
    ) -> None:
        renamed = raw_fixture()
        renamed["repository"]["nameWithOwner"] = "ned2/renamed-dashpot"
        renamed["url"] = "https://github.com/ned2/renamed-dashpot/issues/9"
        runner = SequenceRunner(
            [
                completed(
                    issue_page([renamed], repository_reference="ned2/renamed-dashpot")
                )
            ]
        )
        github = GitHubIssuesSource(
            Path("/repo"),
            project_id=PROJECT_ID,
            repository_id=REPOSITORY_ID,
            runner=runner,
            clock=lambda: "2026-08-26T10:00:00Z",
        )

        observation = github.refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual("ned2/renamed-dashpot#9", observation.issues[0].reference)
        location = observation.issues[0].location
        assert location.kind == "github"
        self.assertEqual(
            "https://github.com/ned2/renamed-dashpot/issues/9", location.url
        )

    def test_missing_repository_is_a_repository_diagnostic(self) -> None:
        response = json.dumps({"data": {"node": None}})

        observation = source(SequenceRunner([completed(response)])).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-repository", observation.diagnostics[0].code)

    def test_one_malformed_issue_fails_the_whole_refresh(self) -> None:
        malformed = issue_record(2)
        del malformed["author"]
        runner = SequenceRunner([completed(issue_page([issue_record(1), malformed]))])

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual((), observation.issues)
        self.assertEqual("github-profile", observation.diagnostics[0].code)

    def test_empty_repository_is_a_fresh_empty_collection(self) -> None:
        observation = source(SequenceRunner([completed(issue_page([]))])).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual((), observation.issues)

    def test_every_query_observes_the_rate_limit_beside_its_data(self) -> None:
        record = raw_fixture()
        record["labels"]["pageInfo"] = {"hasNextPage": True, "endCursor": "l1"}
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(nested_page([{"name": "later", "color": "5319e7"}])),
            ]
        )

        source(runner).refresh()

        for args, _cwd, _timeout in runner.calls:
            self.assertIn("rateLimit { cost limit remaining resetAt }", args[4])

    def test_a_low_rate_limit_warns_beside_a_fresh_collection(self) -> None:
        runner = SequenceRunner(
            [completed(with_rate_limit(issue_page([raw_fixture()]), remaining=499))]
        )

        observation = source(runner).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual([expected_fixture()], list(observation.issues))
        (diagnostic,) = observation.diagnostics
        self.assertEqual(
            ("github-issues", "github-rate-limit-low", "warning"),
            (diagnostic.source, diagnostic.code, diagnostic.severity),
        )
        self.assertIn(
            "499 of 5000 points remain until 2026-08-26T11:00:00Z", diagnostic.message
        )

        # A tenth of the hour left is not yet low.
        runner = SequenceRunner(
            [completed(with_rate_limit(issue_page([raw_fixture()]), remaining=500))]
        )
        self.assertEqual((), source(runner).refresh().diagnostics)

    def test_a_refresh_over_its_request_budget_is_abandoned_as_stale(self) -> None:
        pages: list[CommandResult | Exception] = [
            completed(
                issue_page([issue_record(1)], has_next_page=True, end_cursor="p1")
            ),
            completed(
                issue_page([issue_record(2)], has_next_page=True, end_cursor="p2")
            ),
            completed(issue_page([issue_record(3)])),
        ]
        runner = SequenceRunner(pages)
        github = source(
            runner,
            ["2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"],
            budget=RefreshBudget(seconds=60, requests=2),
        )
        first = github.refresh()
        assert_unavailable_observation(
            self,
            first,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-refresh-budget",
        )
        self.assertEqual(
            "GitHub refresh abandoned after 2 requests in 0.0s with 2 Issues; "
            "the budget is 2 requests or 60s",
            first.diagnostics[0].message,
        )
        # Two pages were fetched and the third was never asked for.
        self.assertEqual(2, len(runner.calls))

        # The budget covers a whole cycle: a good cycle within it stays good
        # and the next export exceeding its page budget retains it.
        record = issue_record(1)
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(issue_page([record], has_next_page=True, end_cursor="p1")),
                completed(
                    issue_page([issue_record(2)], has_next_page=True, end_cursor="p2")
                ),
            ]
        )
        github = source(
            runner,
            ["2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"],
            budget=RefreshBudget(seconds=60, requests=2),
        )
        github.refresh()
        stale = github.refresh()
        assert_stale_observation(
            self,
            stale,
            attempted_at="2026-08-26T10:01:00Z",
            last_good_at="2026-08-26T10:00:00Z",
            source_name="github-issues",
            diagnostic_code="github-refresh-budget",
            expected_issues=[normalize(issue_record(1))],
        )

    def test_a_refresh_over_its_time_budget_is_abandoned_between_requests(self) -> None:
        clock = iter([0.0, 0.5, 61.0])
        runner = SequenceRunner(
            [
                completed(
                    issue_page([issue_record(1)], has_next_page=True, end_cursor="p1")
                ),
                completed(issue_page([issue_record(2)])),
            ]
        )

        observation = source(
            runner,
            budget=RefreshBudget(seconds=60, requests=25),
            monotonic=lambda: next(clock),
        ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-refresh-budget", observation.diagnostics[0].code)
        self.assertIn(
            "after 1 requests in 61.0s with 1 Issues",
            observation.diagnostics[0].message,
        )
        self.assertEqual(1, len(runner.calls))

    def test_nested_pages_spend_the_same_budget(self) -> None:
        record = raw_fixture()
        record["labels"]["pageInfo"] = {"hasNextPage": True, "endCursor": "l1"}
        runner = SequenceRunner(
            [
                completed(issue_page([record])),
                completed(nested_page([{"name": "later", "color": "5319e7"}])),
            ]
        )

        observation = source(runner, budget=RefreshBudget(requests=1)).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertIn(
            "after 1 requests in 0.0s with 3 labels of Issue",
            observation.diagnostics[0].message,
        )

    def test_a_repository_not_found_by_identity_is_a_repository_diagnostic(
        self,
    ) -> None:
        runner = SequenceRunner(
            [
                graphql_failure(
                    "NOT_FOUND",
                    ["node"],
                    "Could not resolve to a node with the global id of 'R_gone'",
                )
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-repository", observation.diagnostics[0].code)

    def test_a_typed_error_names_the_code_whatever_its_prose_says(self) -> None:
        runner = SequenceRunner(
            [
                graphql_failure(
                    "RATE_LIMITED",
                    ["node"],
                    "Something went wrong while executing your query.",
                )
            ]
        )

        observation = source(runner).refresh()

        self.assertEqual("github-rate-limit", observation.diagnostics[0].code)


class GitHubIssuesFindTests(unittest.TestCase):
    def test_find_by_number_issues_exactly_one_command(self) -> None:
        runner = SequenceRunner([completed(issue_response(raw_fixture()))])

        issue = source(runner).find(parse_issue_hint("9"))

        self.assertEqual(expected_fixture(), issue)
        self.assertEqual(1, len(runner.calls))
        query = runner.calls[0][0][4]
        self.assertIn("issue(number: $number)", query)
        self.assertIn("-F", runner.calls[0][0])
        self.assertIn("number=9", runner.calls[0][0])

    def test_find_round_trips_the_printed_issue_url(self) -> None:
        runner = SequenceRunner([completed(issue_response(raw_fixture()))])
        url = issue_location(expected_fixture())

        issue = source(runner).find(parse_issue_hint(url))

        self.assertEqual(expected_fixture(), issue)
        self.assertEqual(1, len(runner.calls))

    def test_find_with_another_repositorys_reference_misses(self) -> None:
        runner = SequenceRunner([completed(issue_response(raw_fixture()))])

        issue = source(runner).find(parse_issue_hint("ned2/sim#9"))

        self.assertIsNone(issue)
        self.assertEqual(1, len(runner.calls))

    def test_find_slug_hint_misses_without_a_request(self) -> None:
        runner = SequenceRunner([])

        issue = source(runner).find(parse_issue_hint("worktree-protocol"))

        self.assertIsNone(issue)
        self.assertEqual(0, len(runner.calls))

    def test_find_unresolved_issue_number_is_a_miss_not_an_outage(self) -> None:
        runner = SequenceRunner(
            [
                graphql_failure(
                    "NOT_FOUND",
                    ["node", "issue"],
                    "Could not resolve to an Issue with the number of 99.",
                )
            ]
        )

        self.assertIsNone(source(runner).find(parse_issue_hint("99")))

    def test_find_reads_a_miss_told_only_in_prose(self) -> None:
        runner = SequenceRunner(
            [
                completed(
                    stderr=(
                        "GraphQL: Could not resolve to an Issue or PullRequest "
                        "with the number of 99. (repository.issue)"
                    ),
                    returncode=1,
                )
            ]
        )

        self.assertIsNone(source(runner).find(parse_issue_hint("99")))

    def test_find_in_a_missing_repository_is_an_outage(self) -> None:
        runner = SequenceRunner(
            [
                graphql_failure(
                    "NOT_FOUND",
                    ["node"],
                    "Could not resolve to a node with the global id of 'R_gone'",
                )
            ]
        )

        with self.assertRaises(IssueSourceRefreshError) as caught:
            source(runner).find(parse_issue_hint("99"))

        self.assertEqual("github-repository", caught.exception.code)

    def test_find_null_issue_is_a_miss(self) -> None:
        runner = SequenceRunner([completed(issue_response(None))])

        self.assertIsNone(source(runner).find(parse_issue_hint("99")))

    def test_find_raises_the_sources_diagnosis_on_an_outage(self) -> None:
        runner = SequenceRunner([OSError("network is unreachable")])

        with self.assertRaises(IssueSourceRefreshError) as caught:
            source(runner).find(parse_issue_hint("9"))

        self.assertEqual("github-network", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
