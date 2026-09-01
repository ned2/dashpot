from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashpot.issue_profile import (
    IssueProfile,
    conform_issue,
    semantically_equivalent,
)
from dashpot.local_markdown_issues import LocalMarkdownIssuesSource
from factories import local_issue_document
from issue_source_conformance import (
    assert_duplicate_identity_is_refused,
    assert_duplicate_number_is_refused,
    assert_fresh_observation,
    assert_stale_observation,
    assert_unavailable_observation,
)

ROOT = Path(__file__).parents[1]
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "local-markdown" / "ISSUES.md"
EXPECTED_FIXTURE = ROOT / "conformance" / "issue" / "fixtures" / "markdown.json"
PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def location_path(issue: IssueProfile) -> str:
    """The Repository-relative path of a Local Issue's location."""
    assert issue.location.kind == "markdown"
    return issue.location.path


def local_document(
    *, issue_id: str, reference: str, title: str, number: int = 9
) -> str:
    return local_issue_document(
        issue_id=issue_id, reference=reference, title=title, number=number
    )


class LocalMarkdownIssuesSourceTests(unittest.TestCase):
    def test_refresh_matches_the_conformance_fixture(self) -> None:
        source = LocalMarkdownIssuesSource(
            RAW_FIXTURE.parent,
            issues_path=Path("ISSUES.md"),
            project_id=PROJECT_ID,
            clock=lambda: "2026-08-26T10:00:00Z",
        )

        observation = source.refresh()

        expected = conform_issue(json.loads(EXPECTED_FIXTURE.read_text()))
        assert_fresh_observation(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            expected_issues=[expected],
        )
        self.assertEqual({}, observation.label_colors)
        self.assertEqual({}, observation.issue_activity)

    def test_directory_refresh_orders_by_posix_path_not_by_path_parts(self) -> None:
        # "a-b.md" precedes "a/b.md" as text, and it is the text the contract
        # orders by; comparing Paths part by part would reverse them.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            (issues / "a").mkdir(parents=True)
            (issues / "a" / "b.md").write_text(
                local_document(
                    issue_id="I_nested", number=2, reference="nested", title="Nested"
                )
            )
            (issues / "a-b.md").write_text(
                local_document(
                    issue_id="I_flat", number=1, reference="flat", title="Flat"
                )
            )

            observation = LocalMarkdownIssuesSource(
                root, issues_path=Path("issues"), project_id=PROJECT_ID
            ).refresh()

        self.assertEqual(
            ["issues/a-b.md", "issues/a/b.md"],
            [location_path(issue) for issue in observation.issues],
        )

    def test_directory_refresh_collects_markdown_files_in_path_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            (issues / "z-last.md").write_text(
                local_document(
                    issue_id="I_last",
                    number=2,
                    reference="last",
                    title="Last by path",
                )
            )
            (issues / "a-first.md").write_text(
                local_document(
                    issue_id="I_first",
                    number=1,
                    reference="first",
                    title="First by path",
                )
            )

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual(
            ["I_first", "I_last"], [issue.id for issue in observation.issues]
        )
        self.assertEqual(
            ["issues/a-first.md", "issues/z-last.md"],
            [location_path(issue) for issue in observation.issues],
        )

    def test_version_genealogy_is_not_part_of_local_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_versioned",
                reference="versioned",
                title="Versioned",
            ).replace("{", '{\n  "schemaVersion": 1,', 1)
            (root / "versioned.md").write_text(document)

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("versioned.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-profile", observation.diagnostics[0].code)
        self.assertIn("schemaVersion", observation.diagnostics[0].message)

    def test_issue_number_is_required_local_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = local_document(
                issue_id="I_missing_number",
                reference="missing-number",
                title="Missing number",
            ).replace('  "number": 9,\n', "")
            (root / "missing-number.md").write_text(document)

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("missing-number.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-profile", observation.diagnostics[0].code)
        self.assertIn("missing fields: number", observation.diagnostics[0].message)

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

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("../outside.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual((), observation.issues)
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

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual("markdown-path", observation.diagnostics[0].code)

    def test_missing_source_is_not_an_empty_issue_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            observation = LocalMarkdownIssuesSource(
                Path(temporary_directory),
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual((), observation.issues)
        self.assertEqual("markdown-not-found", observation.diagnostics[0].code)

    def test_permission_failure_is_distinct_from_malformed_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issue_path = root / "issue.md"
            issue_path.touch()
            source = LocalMarkdownIssuesSource(
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
            source_name="local-markdown-issues",
            diagnostic_code="markdown-permission",
        )

    def test_existing_empty_directory_is_a_fresh_empty_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "issues").mkdir()

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual((), observation.issues)
        self.assertEqual((), observation.diagnostics)

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

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
                clock=lambda: "2026-08-26T10:00:00Z",
            ).refresh()

        assert_duplicate_identity_is_refused(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="local-markdown-issues",
            diagnostic_code="markdown-duplicate-identity",
            issue_id="I_duplicate",
            seen_at=("issues/first.md", "issues/second.md"),
        )

    def test_duplicate_issue_number_fails_the_whole_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            issues = root / "issues"
            issues.mkdir()
            for filename, issue_id in (
                ("first.md", "I_first"),
                ("second.md", "I_second"),
            ):
                (issues / filename).write_text(
                    local_document(
                        issue_id=issue_id,
                        number=17,
                        reference=filename.removesuffix(".md"),
                        title=issue_id,
                    )
                )

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
                clock=lambda: "2026-08-26T10:00:00Z",
            ).refresh()

        assert_duplicate_number_is_refused(
            self,
            observation,
            attempted_at="2026-08-26T10:00:00Z",
            source_name="local-markdown-issues",
            diagnostic_code="markdown-duplicate-number",
            issue_number=17,
            seen_at=("issues/first.md", "issues/second.md"),
        )

    def test_failure_retains_last_good_issues_isolated_from_the_caller(self) -> None:
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
            times = iter(["2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"])
            source = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issue.md"),
                project_id=PROJECT_ID,
                clock=lambda: next(times),
            )
            fresh = source.refresh()
            expected = list(fresh.issues)
            # The whole observation is frozen: a caller cannot swap an
            # element, so the retained collection needs no defensive copy.
            # The ty ignore silences the static rejection of exactly the
            # runtime mutation this test proves is refused.
            with self.assertRaises(TypeError):
                fresh.issues[0] = conform_issue(  # ty: ignore[invalid-assignment]
                    dict(
                        expected[0].model_dump(mode="json", by_alias=True),
                        title="caller mutation",
                    )
                )
            issue_path.write_text("not a Local Issue")

            stale = source.refresh()

        assert_stale_observation(
            self,
            stale,
            attempted_at="2026-08-26T10:01:00Z",
            last_good_at="2026-08-26T10:00:00Z",
            source_name="local-markdown-issues",
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
                '"id": "I_override",',
                '"id": "I_override",\n  "projectId": "project:other",',
            )
            (root / "override.md").write_text(document)

            observation = LocalMarkdownIssuesSource(
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

            observation = LocalMarkdownIssuesSource(
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

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("unavailable", observation.status)
        self.assertEqual((), observation.issues)
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

            observation = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("body.md"),
                project_id=PROJECT_ID,
            ).refresh()

        self.assertEqual("fresh", observation.status)
        self.assertEqual(body, observation.issues[0].body)

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
            source = LocalMarkdownIssuesSource(
                root,
                issues_path=Path("issues"),
                project_id=PROJECT_ID,
            )
            before = source.refresh().issues[0]
            moved_path = issues / "nested" / "moved.md"
            moved_path.parent.mkdir()
            original_path.rename(moved_path)

            after = source.refresh().issues[0]

        self.assertTrue(semantically_equivalent(before, after))
        self.assertEqual(before.updated_at, after.updated_at)
        self.assertEqual("issues/original.md", location_path(before))
        self.assertEqual("issues/nested/moved.md", location_path(after))


if __name__ == "__main__":
    unittest.main()
