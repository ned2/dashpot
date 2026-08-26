from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from dashpot.github_issues import (
    GitHubIssueNormalizationError,
    normalize_github_issue_v1,
)


ROOT = Path(__file__).parents[1]
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "github-issue-v1.json"
EXPECTED_FIXTURE = (
    ROOT / "conformance" / "issue" / "v1" / "fixtures" / "github.json"
)
PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"
REPOSITORY_ID = "R_kgDOUEerrg"


def raw_fixture() -> dict:
    return json.loads(RAW_FIXTURE.read_text())


def expected_fixture() -> dict:
    return json.loads(EXPECTED_FIXTURE.read_text())


def normalize(record: dict, **overrides) -> dict:
    return normalize_github_issue_v1(
        record,
        project_id=overrides.get("project_id", PROJECT_ID),
        repository_id=overrides.get("repository_id", REPOSITORY_ID),
    )


class GitHubIssueNormalizerV1Tests(unittest.TestCase):
    def test_complete_graphql_issue_matches_the_v1_conformance_fixture(self) -> None:
        self.assertEqual(expected_fixture(), normalize(raw_fixture()))

    def test_plural_assignees_and_all_relationships_are_preserved(self) -> None:
        issue = normalize(raw_fixture())

        self.assertEqual(["ned2", "octocat"], issue["assignees"])
        self.assertEqual("I_parent_1", issue["relationships"]["parent"])
        self.assertEqual(
            ["I_child_1", "I_child_2"], issue["relationships"]["subIssues"]
        )
        self.assertEqual(
            ["I_blocker_1", "I_blocker_2"], issue["relationships"]["blockedBy"]
        )
        self.assertEqual(
            ["I_blocked_1", "I_blocked_2"], issue["relationships"]["blocking"]
        )

    def test_repository_rename_changes_reference_not_identity(self) -> None:
        before = normalize(raw_fixture())
        renamed = raw_fixture()
        renamed["repository"]["nameWithOwner"] = "open-dashpot/dashpot"
        renamed["url"] = "https://github.com/open-dashpot/dashpot/issues/9"

        after = normalize(renamed)

        self.assertEqual(before["id"], after["id"])
        self.assertEqual(before["projectId"], after["projectId"])
        self.assertEqual("open-dashpot/dashpot#9", after["reference"])
        self.assertEqual(renamed["url"], after["location"]["url"])

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

        self.assertEqual(before["id"], after["id"])
        self.assertEqual("project:operations", after["projectId"])
        self.assertEqual("open-dashpot/operations#41", after["reference"])
        self.assertEqual("R_operations", after["origin"]["repositoryId"])

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

        self.assertIsNone(issue["author"])
        self.assertIsNone(issue["relationships"]["parent"])
        self.assertEqual([], issue["labels"])
        self.assertEqual([], issue["assignees"])
        self.assertEqual([], issue["relationships"]["blockedBy"])

    def test_closed_lifecycle_values_are_normalized(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "NOT_PLANNED"
        record["closedAt"] = "2026-08-26T10:00:00Z"

        issue = normalize(record)

        self.assertEqual("closed", issue["state"])
        self.assertEqual("not-planned", issue["stateReason"])
        self.assertEqual(record["closedAt"], issue["closedAt"])

    def test_duplicate_state_reason_is_preserved(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "DUPLICATE"
        record["closedAt"] = "2026-08-26T10:00:00Z"

        self.assertEqual("duplicate", normalize(record)["stateReason"])

    def test_unknown_state_reason_is_rejected_instead_of_erased(self) -> None:
        record = raw_fixture()
        record["state"] = "CLOSED"
        record["stateReason"] = "FUTURE_REASON"

        with self.assertRaisesRegex(
            GitHubIssueNormalizationError, "not supported by Issue profile v1"
        ):
            normalize(record)

    def test_normalization_does_not_mutate_the_graphql_record(self) -> None:
        record = raw_fixture()
        before = copy.deepcopy(record)

        normalize(record)

        self.assertEqual(before, record)


if __name__ == "__main__":
    unittest.main()
