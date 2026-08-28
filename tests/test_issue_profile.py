from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from dashpot.issue_profile import (
    IssueProfileError,
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
        github = fixture("github.json")
        markdown = fixture("markdown.json")

        self.assertTrue(semantically_equivalent(github, markdown))
        self.assertEqual(fixture("semantic.json"), semantic_projection(github))
        self.assertEqual(fixture("semantic.json"), semantic_projection(markdown))

    def test_set_like_collections_are_canonicalized(self) -> None:
        candidate = fixture("github.json")
        candidate["labels"].reverse()
        candidate["assignees"].reverse()
        candidate["relationships"]["blockedBy"].reverse()

        issue = conform_issue(candidate)

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
        moved["origin"] = {"kind": "markdown"}
        moved["location"] = {
            "kind": "markdown",
            "path": "docs/ISSUES.md",
            "line": 42,
        }

        self.assertTrue(semantically_equivalent(issue, moved))

        moved["reference"] = "issue-model-uplift"
        self.assertFalse(semantically_equivalent(issue, moved))

        moved = copy.deepcopy(issue)
        moved["number"] = 41
        self.assertFalse(semantically_equivalent(issue, moved))

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

        self.assertTrue(semantically_equivalent(before, after))
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


if __name__ == "__main__":
    unittest.main()
