from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashpot.issue_profile import semantically_equivalent_v1
from dashpot.local_markdown_issues import LocalMarkdownIssuesV1Source
from issue_source_conformance import (
    assert_fresh_observation,
    assert_stale_observation,
    assert_unavailable_observation,
)


ROOT = Path(__file__).parents[1]
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "local-markdown-v1" / "ISSUES.md"
EXPECTED_FIXTURE = (
    ROOT / "conformance" / "issue" / "v1" / "fixtures" / "markdown.json"
)
PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def local_document(*, issue_id: str, reference: str, title: str) -> str:
    fixture_lines = RAW_FIXTURE.read_text().splitlines()
    front_matter_end = fixture_lines.index("---", 1)
    metadata = json.loads("\n".join(fixture_lines[1:front_matter_end]))
    metadata["id"] = issue_id
    metadata["reference"] = reference
    return "\n".join(
        [
            "---",
            json.dumps(metadata, indent=2),
            "---",
            f"# {title}",
            "",
            "A complete local Issue.",
            "",
        ]
    )


class LocalMarkdownIssuesV1SourceTests(unittest.TestCase):
    def test_refresh_matches_the_v1_conformance_fixture(self) -> None:
        source = LocalMarkdownIssuesV1Source(
            RAW_FIXTURE.parent,
            issues_path=Path("ISSUES.md"),
            project_id=PROJECT_ID,
            clock=lambda: "2026-08-26T10:00:00Z",
        )

        observation = source.refresh()

        expected = json.loads(EXPECTED_FIXTURE.read_text())
        assert_fresh_observation(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            expected_issues=[expected],
        )

    def test_directory_refresh_collects_markdown_files_in_path_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            (issues / "z-last.md").write_text(
                local_document(
                    issue_id="I_last",
                    reference="last",
                    title="Last by path",
                )
            )
            (issues / "a-first.md").write_text(
                local_document(
                    issue_id="I_first",
                    reference="first",
                    title="First by path",
                )
            )

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual(
            ["I_first", "I_last"], [issue["id"] for issue in observation.issues]
        )
        self.assertEqual(
            ["issues/a-first.md", "issues/z-last.md"],
            [issue["location"]["path"] for issue in observation.issues],
        )

    def test_future_document_version_is_an_unsupported_version_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_future",
                reference="future",
                title="From the future",
            ).replace('"schemaVersion": 1', '"schemaVersion": 2')
            (root / "future.md").write_text(document)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("future.md"),
                project_id=PROJECT_ID,
            ).refresh()

        assert_unavailable_observation(
            self,
            observation,
            attempted_at=observation.attempted_at,
            source_name="local-markdown-issues-v1",
            diagnostic_code="markdown-unsupported-version",
        )

    def test_boolean_is_not_a_local_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_boolean_version",
                reference="boolean-version",
                title="Boolean version",
            ).replace('"schemaVersion": 1', '"schemaVersion": true')
            (root / "boolean-version.md").write_text(document)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("boolean-version.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual(
            "markdown-unsupported-version", observation.diagnostics[0].code
        )

    def test_configured_path_cannot_escape_the_repository_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "repository"
            root.mkdir()
            outside = parent / "outside.md"
            outside.write_text(
                local_document(
                    issue_id="I_outside",
                    reference="outside",
                    title="Outside the repository",
                )
            )

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("../outside.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual([], observation.issues)
        self.assertEqual("markdown-path", observation.diagnostics[0].code)

    def test_discovered_file_symlink_cannot_escape_the_repository_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "repository"
            issues = root / "issues"
            issues.mkdir(parents=True)
            outside = parent / "outside.md"
            outside.write_text(
                local_document(
                    issue_id="I_outside",
                    reference="outside",
                    title="Outside the repository",
                )
            )
            (issues / "linked.md").symlink_to(outside)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-path", observation.diagnostics[0].code)

    def test_missing_source_is_not_an_empty_issue_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            observation = LocalMarkdownIssuesV1Source(
                Path(temporary_directory),
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual([], observation.issues)
        self.assertEqual("markdown-not-found", observation.diagnostics[0].code)

    def test_permission_failure_is_distinct_from_malformed_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issue_path = root / "issue.md"
            issue_path.touch()
            source = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issue.md"),
                project_id=PROJECT_ID,
                clock=lambda: "2026-08-26T10:00:00Z",
            )

            with patch.object(
                Path, "read_text", side_effect=PermissionError("permission denied")
            ):
                observation = source.refresh()

        assert_unavailable_observation(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="local-markdown-issues-v1",
            diagnostic_code="markdown-permission",
        )

    def test_existing_empty_directory_is_a_fresh_empty_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "issues").mkdir()

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual([], observation.issues)
        self.assertEqual([], observation.diagnostics)

    def test_duplicate_issue_identity_fails_the_whole_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            for filename, reference in (("first.md", "first"), ("second.md", "second")):
                (issues / filename).write_text(
                    local_document(
                        issue_id="I_duplicate",
                        reference=reference,
                        title=reference.title(),
                    )
                )

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual([], observation.issues)
        self.assertEqual(
            "markdown-duplicate-identity", observation.diagnostics[0].code
        )

    def test_failure_retains_a_deep_copy_of_last_good_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issue_path = root / "issue.md"
            issue_path.write_text(
                local_document(
                    issue_id="I_last_good",
                    reference="last-good",
                    title="Last good",
                )
            )
            times = iter(
                ["2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"]
            )
            source = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issue.md"),
                project_id=PROJECT_ID,
                clock=lambda: next(times),
            )
            fresh = source.refresh()
            expected = json.loads(json.dumps(fresh.issues))
            fresh.issues[0]["title"] = "caller mutation"
            issue_path.write_text("not a Local Issue")

            stale = source.refresh()

        assert_stale_observation(
            self,
            stale,
            attempted_at="2026-08-26T10:01:00Z",
            last_good_at="2026-08-26T10:00:00Z",
            source_name="local-markdown-issues-v1",
            diagnostic_code="markdown-malformed",
            expected_issues=expected,
        )

    def test_document_cannot_override_source_owned_project_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_override",
                reference="override",
                title="Override",
            ).replace(
                '"schemaVersion": 1,',
                '"schemaVersion": 1,\n  "projectId": "project:other",',
            )
            (root / "override.md").write_text(document)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("override.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-profile", observation.diagnostics[0].code)
        self.assertIn("projectId", observation.diagnostics[0].message)

    def test_duplicate_json_metadata_keys_are_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_first_value",
                reference="duplicate-key",
                title="Duplicate key",
            ).replace(
                '"id": "I_first_value",',
                '"id": "I_first_value",\n  "id": "I_second_value",',
            )
            (root / "duplicate-key.md").write_text(document)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("duplicate-key.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-malformed", observation.diagnostics[0].code)
        self.assertIn("duplicate metadata key", observation.diagnostics[0].message)

    def test_one_malformed_file_names_the_file_and_fails_the_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            (issues / "good.md").write_text(
                local_document(
                    issue_id="I_good",
                    reference="good",
                    title="Good",
                )
            )
            (issues / "bad.md").write_text("not a Local Issue")

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual([], observation.issues)
        self.assertEqual("markdown-malformed", observation.diagnostics[0].code)
        self.assertIn("issues/bad.md", observation.diagnostics[0].message)

    def test_body_preserves_nested_markdown(self) -> None:
        body = "\n".join(
            [
                "Introduction.",
                "",
                "## Details",
                "",
                "```text",
                "---",
                "```",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_markdown_body",
                reference="markdown-body",
                title="Markdown body",
            ).replace("A complete local Issue.", body)
            (root / "body.md").write_text(document)

            observation = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("body.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual(body, observation.issues[0]["body"])

    def test_moving_a_document_changes_only_its_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            original_path = issues / "original.md"
            original_path.write_text(
                local_document(
                    issue_id="I_moved",
                    reference="moved",
                    title="Moved",
                )
            )
            source = LocalMarkdownIssuesV1Source(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            )
            before = source.refresh().issues[0]
            moved_path = issues / "nested" / "moved.md"
            moved_path.parent.mkdir()
            original_path.rename(moved_path)

            after = source.refresh().issues[0]

        self.assertTrue(semantically_equivalent_v1(before, after))
        self.assertEqual(before["updatedAt"], after["updatedAt"])
        self.assertEqual("issues/original.md", before["location"]["path"])
        self.assertEqual("issues/nested/moved.md", after["location"]["path"])


if __name__ == "__main__":
    unittest.main()
