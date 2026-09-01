from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from dashpot.commands import CommandResult
from dashpot.github_issues import (
    GitHubIssueNormalizationError,
    GitHubIssuesSource,
    normalize_github_issue,
)
from dashpot.issue_profile import IssueProfile, conform_issue
from issue_source_conformance import (
    assert_fresh_observation,
    assert_stale_observation,
    assert_unavailable_observation,
)

ROOT = Path(__file__).parents[1]
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "github-issue.json"
EXPECTED_FIXTURE = ROOT / "conformance" / "issue" / "fixtures" / "github.json"
PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"
REPOSITORY_ID = "R_kgDOUEerrg"


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


def issue_record(number: int) -> dict[str, Any]:
    record = raw_fixture()
    record["id"] = f"I_issue_{number}"
    record["number"] = number
    record["url"] = f"https://github.com/ned2/dashpot/issues/{number}"
    return record


def issue_page(
    nodes: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
    repository_id: str = REPOSITORY_ID,
    repository_reference: str = "ned2/dashpot",
) -> str:
    return json.dumps(
        {
            "data": {
                "node": {
                    "id": repository_id,
                    "nameWithOwner": repository_reference,
                    "issues": {
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
    runner: SequenceRunner, timestamps: list[str] | None = None
) -> GitHubIssuesSource:
    times = iter(timestamps or ["2026-08-26T10:00:00Z"])
    return GitHubIssuesSource(
        Path("/repo"),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        runner=runner,
        clock=lambda: next(times),
    )


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
                    GitHubIssueNormalizationError,
                    "number must be a positive integer",
                ):
                    normalize(record)

    def test_conflicting_configured_repository_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            GitHubIssueNormalizationError, "does not match the configured"
        ):
            normalize(raw_fixture(), repository_id="R_another_repository")

    def test_incomplete_nested_connections_are_rejected(self) -> None:
        for field in ("labels", "assignees", "subIssues", "blockedBy", "blocking"):
            with self.subTest(field=field):
                record = raw_fixture()
                record[field]["pageInfo"]["hasNextPage"] = True
                with self.assertRaisesRegex(
                    GitHubIssueNormalizationError, "pagination remains"
                ):
                    normalize(record)

    def test_missing_field_is_not_interpreted_as_known_absence(self) -> None:
        record = raw_fixture()
        del record["author"]

        with self.assertRaisesRegex(
            GitHubIssueNormalizationError, "issue.author was not fetched"
        ):
            normalize(record)

    def test_non_null_github_timestamp_cannot_be_reported_as_absent(self) -> None:
        record = raw_fixture()
        record["createdAt"] = None

        with self.assertRaisesRegex(
            GitHubIssueNormalizationError, "issue.createdAt must be a non-empty string"
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
            GitHubIssueNormalizationError, "not supported by the Issue profile"
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

    def test_duplicate_issue_number_is_a_pagination_diagnostic(self) -> None:
        first = issue_record(9)
        second = issue_record(9)
        second["id"] = "I_other_identity"
        runner = SequenceRunner([completed(issue_page([first, second]))])

        observation = source(runner).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("github-pagination", observation.diagnostics[0].code)
        self.assertIn("duplicate Issue Number #9", observation.diagnostics[0].message)

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
        self.assertEqual([], activity.linked_pull_requests)

        bare = raw_fixture()
        del bare["comments"]
        del bare["closedByPullRequestsReferences"]
        observation = source(SequenceRunner([completed(issue_page([bare]))])).refresh()
        self.assertEqual("fresh", observation.status)
        self.assertEqual(
            0, observation.issue_activity[observation.issues[0].id].comment_count
        )

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

    def test_failure_retains_a_deep_copy_of_last_good_issues(self) -> None:
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
        # The profile is frozen, so a caller can only swap a list element.
        fresh.issues[0] = normalize(dict(raw_fixture(), title="caller mutation"))
        fresh.label_colors["enhancement"] = "000000"
        fresh.issue_activity[fresh.issues[0].id].comment_count = 99

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
        self.assertEqual([], observation.issues)
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
        self.assertEqual([], observation.issues)
        self.assertEqual("github-profile", observation.diagnostics[0].code)

    def test_empty_repository_is_a_fresh_empty_collection(self) -> None:
        observation = source(SequenceRunner([completed(issue_page([]))])).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual([], observation.issues)


if __name__ == "__main__":
    unittest.main()
