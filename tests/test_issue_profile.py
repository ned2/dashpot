from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from dashpot.issue_profile import (
    IssueProfileError,
    conform_issue_v1,
    semantic_projection_v1,
    semantically_equivalent_v1,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "conformance" / "issue" / "v1" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class IssueProfileV1Tests(unittest.TestCase):
    def test_github_and_markdown_fixtures_are_semantically_equivalent(self) -> None:
        github = fixture("github.json")
        markdown = fixture("markdown.json")

        self.assertTrue(semantically_equivalent_v1(github, markdown))
        self.assertEqual(fixture("semantic.json"), semantic_projection_v1(github))
        self.assertEqual(fixture("semantic.json"), semantic_projection_v1(markdown))

    def test_set_like_collections_are_canonicalized(self) -> None:
        candidate = fixture("github.json")
        candidate["labels"].reverse()
        candidate["assignees"].reverse()
        candidate["relationships"]["blockedBy"].reverse()

        issue = conform_issue_v1(candidate)

        self.assertEqual(
            ["enhancement", "needs-triage", "priority/P1"], issue["labels"]
        )
        self.assertEqual(["ned2", "octocat"], issue["assignees"])
        self.assertEqual(
            ["I_blocker_1", "I_blocker_2"], issue["relationships"]["blockedBy"]
        )

    def test_only_provenance_and_location_are_excluded_from_equivalence(self) -> None:
        issue = fixture("github.json")
        moved = copy.deepcopy(issue)
        moved["origin"] = {"kind": "markdown", "schemaVersion": 1}
        moved["location"] = {
            "kind": "markdown",
            "path": "docs/ISSUES.md",
            "line": 42,
        }

        self.assertTrue(semantically_equivalent_v1(issue, moved))

        moved["reference"] = "issue-model-uplift"
        self.assertFalse(semantically_equivalent_v1(issue, moved))

    def test_moving_markdown_storage_does_not_change_updated_at(self) -> None:
        before = fixture("markdown.json")
        after = copy.deepcopy(before)
        after["location"] = {
            "kind": "markdown",
            "path": "docs/ISSUES.md",
            "line": 42,
        }

        self.assertTrue(semantically_equivalent_v1(before, after))
        self.assertEqual(before["updatedAt"], after["updatedAt"])

    def test_missing_or_not_fetched_data_cannot_masquerade_as_absence(self) -> None:
        missing = fixture("github.json")
        del missing["labels"]
        with self.assertRaisesRegex(IssueProfileError, "missing fields: labels"):
            conform_issue_v1(missing)

        not_fetched = fixture("github.json")
        not_fetched["labels"] = {"availability": "not-fetched"}
        with self.assertRaisesRegex(IssueProfileError, "labels must be an array"):
            conform_issue_v1(not_fetched)

    def test_duplicate_relationships_and_self_relationships_are_rejected(self) -> None:
        duplicate = fixture("github.json")
        duplicate["relationships"]["blockedBy"] = ["I_blocker_1", "I_blocker_1"]
        with self.assertRaisesRegex(IssueProfileError, "must not contain duplicates"):
            conform_issue_v1(duplicate)

        self_related = fixture("github.json")
        self_related["relationships"]["parent"] = self_related["id"]
        with self.assertRaisesRegex(IssueProfileError, "cannot relate to itself"):
            conform_issue_v1(self_related)

    def test_open_issue_cannot_carry_closed_lifecycle_facts(self) -> None:
        issue = fixture("github.json")
        issue["closedAt"] = "2026-08-26T10:00:00Z"
        with self.assertRaisesRegex(IssueProfileError, "closedAt null"):
            conform_issue_v1(issue)

        issue = fixture("github.json")
        issue["stateReason"] = "completed"
        with self.assertRaisesRegex(IssueProfileError, "closed stateReason"):
            conform_issue_v1(issue)

    def test_local_location_is_anchor_relative_and_actionable(self) -> None:
        issue = fixture("markdown.json")
        issue["location"]["path"] = "/tmp/ISSUES.md"
        with self.assertRaisesRegex(IssueProfileError, "repository-relative"):
            conform_issue_v1(issue)

    def test_json_booleans_are_not_accepted_as_integer_versions(self) -> None:
        issue = fixture("markdown.json")
        issue["profileVersion"] = True
        with self.assertRaisesRegex(IssueProfileError, "profileVersion must be 1"):
            conform_issue_v1(issue)

        issue = fixture("markdown.json")
        issue["origin"]["schemaVersion"] = True
        with self.assertRaisesRegex(
            IssueProfileError, "origin.schemaVersion must be 1"
        ):
            conform_issue_v1(issue)


if __name__ == "__main__":
    unittest.main()
