from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dashpot.issue_profile import (
    GitHubIssueOrigin,
    IssueProfileError,
    MarkdownIssueLocation,
    conform_issue,
    semantic_projection,
    semantically_equivalent,
)

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "conformance" / "issue" / "fixtures"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


class IssueProfileTests(unittest.TestCase):
    def test_github_and_markdown_fixtures_are_semantically_equivalent(self) -> None:
        github = conform_issue(fixture("github.json"))
        markdown = conform_issue(fixture("markdown.json"))

        self.assertTrue(semantically_equivalent(github, markdown))
        self.assertEqual(fixture("semantic.json"), semantic_projection(github))
        self.assertEqual(fixture("semantic.json"), semantic_projection(markdown))

    def test_set_like_collections_are_canonicalized(self) -> None:
        candidate = fixture("github.json")
        candidate["labels"].reverse()
        candidate["assignees"].reverse()
        candidate["relationships"]["blockedBy"].reverse()

        issue = conform_issue(candidate)

        self.assertEqual(("enhancement", "needs-triage", "priority/P1"), issue.labels)
        self.assertEqual(("ned2", "octocat"), issue.assignees)
        self.assertEqual(("I_blocker_1", "I_blocker_2"), issue.relationships.blocked_by)

    def test_only_provenance_and_location_are_excluded_from_equivalence(self) -> None:
        issue = fixture("github.json")
        moved = copy.deepcopy(issue)
        moved["origin"] = {"kind": "markdown"}
        moved["location"] = {
            "kind": "markdown",
            "path": "docs/ISSUES.md",
            "line": 42,
        }

        self.assertTrue(
            semantically_equivalent(conform_issue(issue), conform_issue(moved))
        )

        moved["reference"] = "issue-model-uplift"
        self.assertFalse(
            semantically_equivalent(conform_issue(issue), conform_issue(moved))
        )

        moved = copy.deepcopy(issue)
        moved["number"] = 41
        self.assertFalse(
            semantically_equivalent(conform_issue(issue), conform_issue(moved))
        )

    def test_issue_number_is_a_required_positive_integer(self) -> None:
        missing = fixture("github.json")
        del missing["number"]
        with self.assertRaisesRegex(IssueProfileError, "missing fields: number"):
            conform_issue(missing)

        for invalid in (None, 0, -1, "9", 9.0, True):
            with self.subTest(invalid=invalid):
                issue = fixture("github.json")
                issue["number"] = invalid
                with self.assertRaisesRegex(
                    IssueProfileError, "number must be a positive integer"
                ):
                    conform_issue(issue)

    def test_moving_markdown_storage_does_not_change_updated_at(self) -> None:
        before = fixture("markdown.json")
        after = copy.deepcopy(before)
        after["location"] = {
            "kind": "markdown",
            "path": "docs/ISSUES.md",
            "line": 42,
        }

        self.assertTrue(
            semantically_equivalent(conform_issue(before), conform_issue(after))
        )
        self.assertEqual(before["updatedAt"], after["updatedAt"])

    def test_missing_or_not_fetched_data_cannot_masquerade_as_absence(self) -> None:
        missing = fixture("github.json")
        del missing["labels"]
        with self.assertRaisesRegex(IssueProfileError, "missing fields: labels"):
            conform_issue(missing)

        not_fetched = fixture("github.json")
        not_fetched["labels"] = {"availability": "not-fetched"}
        with self.assertRaisesRegex(IssueProfileError, "labels must be an array"):
            conform_issue(not_fetched)

    def test_duplicate_relationships_and_self_relationships_are_rejected(self) -> None:
        duplicate = fixture("github.json")
        duplicate["relationships"]["blockedBy"] = ["I_blocker_1", "I_blocker_1"]
        with self.assertRaisesRegex(IssueProfileError, "must not contain duplicates"):
            conform_issue(duplicate)

        self_related = fixture("github.json")
        self_related["relationships"]["parent"] = self_related["id"]
        with self.assertRaisesRegex(IssueProfileError, "cannot relate to itself"):
            conform_issue(self_related)

    def test_open_issue_cannot_carry_closed_lifecycle_facts(self) -> None:
        issue = fixture("github.json")
        issue["closedAt"] = "2026-08-26T10:00:00Z"
        with self.assertRaisesRegex(IssueProfileError, "closedAt null"):
            conform_issue(issue)

        issue = fixture("github.json")
        issue["stateReason"] = "completed"
        with self.assertRaisesRegex(IssueProfileError, "closed stateReason"):
            conform_issue(issue)

    def test_local_location_is_anchor_relative_and_actionable(self) -> None:
        issue = fixture("markdown.json")
        issue["location"]["path"] = "/tmp/ISSUES.md"
        with self.assertRaisesRegex(IssueProfileError, "repository-relative"):
            conform_issue(issue)

    def test_version_genealogy_is_not_part_of_the_profile(self) -> None:
        issue = fixture("markdown.json")
        issue["profileVersion"] = 1
        with self.assertRaisesRegex(
            IssueProfileError, "unexpected fields: profileVersion"
        ):
            conform_issue(issue)

        issue = fixture("markdown.json")
        issue["origin"]["schemaVersion"] = 1
        with self.assertRaisesRegex(
            IssueProfileError, "unexpected fields: schemaVersion"
        ):
            conform_issue(issue)


class IssueProfileModelTests(unittest.TestCase):
    def test_aliases_expose_snake_case_fields_for_camel_case_keys(self) -> None:
        profile = conform_issue(fixture("github.json"))

        self.assertEqual(
            "project:01947e42-3f67-7c38-a41c-218df18a169b", profile.project_id
        )
        self.assertIsNone(profile.state_reason)
        self.assertEqual(("I_child_1", "I_child_2"), profile.relationships.sub_issues)
        self.assertEqual("2026-08-26T05:33:04Z", profile.created_at)
        self.assertEqual(
            fixture("github.json"), profile.model_dump(mode="json", by_alias=True)
        )

    def test_the_profile_is_frozen_after_validation(self) -> None:
        profile = conform_issue(fixture("github.json"))

        with self.assertRaises(ValidationError):
            # The frozen refusal is the behavior under test.
            profile.title = "Renamed"  # ty: ignore[invalid-assignment]
        self.assertIsInstance(hash(profile), int)

    def test_strict_validation_refuses_coerced_scalars(self) -> None:
        coercions: list[tuple[str, object, str]] = [
            ("number", "9", "number must be a positive integer"),
            ("number", True, "number must be a positive integer"),
            ("body", 5, "body must be a string"),
            ("state", 1, "state must be 'open' or 'closed'"),
            ("title", 7, "title must be a non-empty string"),
        ]
        for key, invalid, message in coercions:
            with self.subTest(key=key, invalid=invalid):
                issue = fixture("github.json")
                issue[key] = invalid
                with self.assertRaisesRegex(IssueProfileError, message):
                    conform_issue(issue)

    def test_set_like_collections_accept_only_arrays(self) -> None:
        issue = fixture("github.json")
        issue["labels"] = tuple(issue["labels"])

        with self.assertRaisesRegex(IssueProfileError, "labels must be an array"):
            conform_issue(issue)

    def test_origin_and_location_discriminate_on_kind(self) -> None:
        profile = conform_issue(fixture("github.json"))
        self.assertIsInstance(profile.origin, GitHubIssueOrigin)

        moved = fixture("github.json")
        moved["origin"] = {"kind": "markdown"}
        moved["location"] = {"kind": "markdown", "path": "ISSUES.md", "line": 3}
        self.assertIsInstance(conform_issue(moved).location, MarkdownIssueLocation)

        crossed = fixture("github.json")
        crossed["origin"] = {"kind": "markdown", "repositoryId": "R_kgDOUEerrg"}
        with self.assertRaisesRegex(
            IssueProfileError, "origin has unexpected fields: repositoryId"
        ):
            conform_issue(crossed)

        unlocated = fixture("github.json")
        unlocated["location"] = {"kind": "markdown", "path": "ISSUES.md"}
        with self.assertRaisesRegex(
            IssueProfileError, "location is missing fields: line"
        ):
            conform_issue(unlocated)

        unkinded = fixture("github.json")
        unkinded["origin"] = {"repositoryId": "R_kgDOUEerrg"}
        with self.assertRaisesRegex(
            IssueProfileError, "origin.kind must be 'github' or 'markdown'"
        ):
            conform_issue(unkinded)

    def test_nested_unexpected_fields_are_rejected(self) -> None:
        issue = fixture("github.json")
        issue["relationships"]["notes"] = []

        with self.assertRaisesRegex(
            IssueProfileError, "relationships has unexpected fields: notes"
        ):
            conform_issue(issue)

    def test_timestamps_must_round_trip_as_real_rfc3339_instants(self) -> None:
        for invalid, message in (
            ("2026-13-01T05:33:04Z", "must be a valid RFC 3339 timestamp"),
            ("2026-02-30T05:33:04Z", "must be a valid RFC 3339 timestamp"),
            ("2026-08-26T05:33:04", "RFC 3339 UTC timestamp ending in Z"),
            ("2026-08-26 05:33:04Z", "RFC 3339 UTC timestamp ending in Z"),
        ):
            with self.subTest(invalid=invalid):
                issue = fixture("github.json")
                issue["updatedAt"] = invalid
                with self.assertRaisesRegex(IssueProfileError, message):
                    conform_issue(issue)

        fractional = fixture("github.json")
        fractional["updatedAt"] = "2026-08-26T08:32:48.500Z"
        self.assertEqual(
            "2026-08-26T08:32:48.500Z", conform_issue(fractional).updated_at
        )

    def test_conform_issue_leaves_the_caller_input_unchanged(self) -> None:
        issue = fixture("github.json")
        issue["labels"].reverse()
        snapshot = copy.deepcopy(issue)

        conformed = conform_issue(issue)

        self.assertEqual(snapshot, issue)
        self.assertEqual(
            ("enhancement", "needs-triage", "priority/P1"), conformed.labels
        )


if __name__ == "__main__":
    unittest.main()
