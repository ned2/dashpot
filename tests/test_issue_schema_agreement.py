"""Prove the Issue profile schema and model agree on one shared fixture corpus."""

from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from dashpot.issue_profile import (
    GitHubIssueLocation,
    GitHubIssueOrigin,
    IssueProfile,
    IssueProfileError,
    IssueRelationships,
    MarkdownIssueLocation,
    MarkdownIssueOrigin,
    conform_issue,
)

ROOT = Path(__file__).parents[1]
CONFORMANCE = ROOT / "conformance" / "issue"

SCHEMA = json.loads((CONFORMANCE / "issue.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)

Mutation = Callable[[dict[str, Any]], Any]


def github_issue() -> dict[str, Any]:
    return json.loads((CONFORMANCE / "fixtures" / "github.json").read_text())


def markdown_issue() -> dict[str, Any]:
    return json.loads((CONFORMANCE / "fixtures" / "markdown.json").read_text())


def mutated(mutation: Mutation) -> dict[str, Any]:
    issue = github_issue()
    mutation(issue)
    return issue


def closed_issue(state_reason: str | None) -> dict[str, Any]:
    def close(issue: dict[str, Any]) -> None:
        issue["state"] = "closed"
        issue["stateReason"] = state_reason
        issue["closedAt"] = "2026-08-27T10:00:00Z"

    return mutated(close)


def positively_absent(issue: dict[str, Any]) -> None:
    issue["stateReason"] = None
    issue["labels"] = []
    issue["assignees"] = []
    issue["author"] = None
    issue["relationships"] = {
        "parent": None,
        "subIssues": [],
        "blockedBy": [],
        "blocking": [],
    }
    issue["issueType"] = None
    issue["milestone"] = None
    issue["createdAt"] = None
    issue["updatedAt"] = None
    issue["body"] = ""


# name -> payload accepted by both the schema and the model.
VALID_CASES: dict[str, dict[str, Any]] = {
    "github-fixture": github_issue(),
    "markdown-fixture": markdown_issue(),
    "closed-completed": closed_issue("completed"),
    "closed-duplicate": closed_issue("duplicate"),
    "closed-not-planned": closed_issue("not-planned"),
    "closed-without-reason": closed_issue(None),
    "open-reopened": mutated(lambda issue: issue.update(stateReason="reopened")),
    "positively-absent-values": mutated(positively_absent),
    "fractional-seconds": mutated(
        lambda issue: issue.update(createdAt="2026-08-26T05:33:04.250Z")
    ),
    "dotted-relative-path": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "docs/notes/ISSUES.md", "line": 7},
    },
}

# name -> payload rejected by both the schema and the model.
INVALID_CASES: dict[str, dict[str, Any]] = {
    "missing-number": mutated(lambda issue: issue.pop("number")),
    "missing-relationship-key": mutated(
        lambda issue: issue["relationships"].pop("parent")
    ),
    "unexpected-top-level-field": mutated(lambda issue: issue.update(profileVersion=1)),
    "unexpected-origin-field": mutated(
        lambda issue: issue["origin"].update(schemaVersion=1)
    ),
    "zero-number": mutated(lambda issue: issue.update(number=0)),
    "negative-number": mutated(lambda issue: issue.update(number=-1)),
    "string-number": mutated(lambda issue: issue.update(number="9")),
    "boolean-number": mutated(lambda issue: issue.update(number=True)),
    "empty-id": mutated(lambda issue: issue.update(id="")),
    "non-string-body": mutated(lambda issue: issue.update(body=5)),
    "uppercase-state": mutated(lambda issue: issue.update(state="OPEN")),
    "unknown-state-reason": mutated(lambda issue: issue.update(stateReason="wontfix")),
    "open-with-closed-reason": mutated(
        lambda issue: issue.update(stateReason="completed")
    ),
    "closed-reopened": mutated(
        lambda issue: issue.update(
            state="closed", stateReason="reopened", closedAt="2026-08-27T10:00:00Z"
        )
    ),
    "open-with-closed-at": mutated(
        lambda issue: issue.update(closedAt="2026-08-27T10:00:00Z")
    ),
    "labels-not-an-array": mutated(
        lambda issue: issue.update(labels={"availability": "not-fetched"})
    ),
    "empty-label": mutated(lambda issue: issue.update(labels=[""])),
    "duplicate-labels": mutated(
        lambda issue: issue.update(labels=["duplicate", "duplicate"])
    ),
    "relationships-not-an-object": mutated(
        lambda issue: issue.update(relationships=[])
    ),
    "month-thirteen-timestamp": mutated(
        lambda issue: issue.update(createdAt="2026-13-01T05:33:04Z")
    ),
    # RFC 3339 forbids ISO 8601's end-of-day 24:00:00, and `fromisoformat`
    # accepts it only on some Python versions; the shared timestamp pattern
    # closes that version-dependent leniency.
    "end-of-day-timestamp": mutated(
        lambda issue: issue.update(createdAt="2026-08-26T24:00:00Z")
    ),
    "past-end-of-day-timestamp": mutated(
        lambda issue: issue.update(createdAt="2026-08-26T24:30:00Z")
    ),
    "leap-second-timestamp": mutated(
        lambda issue: issue.update(createdAt="2026-08-26T23:59:60Z")
    ),
    "timestamp-without-z": mutated(lambda issue: issue.update(createdAt="2026-08-26")),
    "empty-timestamp": mutated(lambda issue: issue.update(createdAt="")),
    "unknown-origin-kind": mutated(lambda issue: issue.update(origin={"kind": "web"})),
    "origin-not-an-object": mutated(lambda issue: issue.update(origin=5)),
    "github-origin-without-repository": mutated(
        lambda issue: issue.update(origin={"kind": "github"})
    ),
    "http-location-url": mutated(
        lambda issue: issue["location"].update(url="http://github.com/ned2/dashpot/9")
    ),
    "hostless-location-url": mutated(
        lambda issue: issue["location"].update(url="https:///issues/9")
    ),
    "markdown-location-without-line": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "ISSUES.md"},
    },
    "absolute-markdown-path": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "/tmp/ISSUES.md", "line": 1},
    },
    "parent-traversal-markdown-path": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "../ISSUES.md", "line": 1},
    },
    "inner-traversal-markdown-path": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "docs/../ISSUES.md", "line": 1},
    },
    "zero-location-line": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "ISSUES.md", "line": 0},
    },
    "boolean-location-line": {
        **markdown_issue(),
        "location": {"kind": "markdown", "path": "ISSUES.md", "line": True},
    },
}

# Rules the model enforces that JSON Schema 2020-12 cannot express: the schema
# accepts these payloads while conform_issue rejects or canonicalizes them.
# Each entry records why the drift is irreducible rather than a schema bug.
#
# - self-reference: comparing `id` against the relationship collections needs
#   cross-field data references, which the draft has no keyword for.
# - calendar-invalid dates (February 30): a regex bounds field ranges but
#   cannot encode month lengths; the model round-trips `fromisoformat`.
# - integral floats (9.0): JSON Schema defines `integer` by mathematical
#   value, so 9.0 conforms; the strict model refuses the Python float.
SCHEMA_ONLY_VALID_CASES: dict[str, dict[str, Any]] = {
    "self-referencing-parent": mutated(
        lambda issue: issue["relationships"].update(parent=issue["id"])
    ),
    "self-referencing-blocker": mutated(
        lambda issue: issue["relationships"].update(blockedBy=[issue["id"]])
    ),
    "february-thirtieth-timestamp": mutated(
        lambda issue: issue.update(createdAt="2026-02-30T05:33:04Z")
    ),
    "float-number": mutated(lambda issue: issue.update(number=9.0)),
}


def model_accepts(payload: dict[str, Any]) -> bool:
    try:
        conform_issue(payload)
    except IssueProfileError:
        return False
    return True


class SchemaAgreementTests(unittest.TestCase):
    def test_schema_and_model_accept_the_same_valid_cases(self) -> None:
        for name, payload in VALID_CASES.items():
            with self.subTest(case=name):
                self.assertTrue(VALIDATOR.is_valid(payload), name)
                self.assertTrue(model_accepts(payload), name)

    def test_schema_and_model_reject_the_same_invalid_cases(self) -> None:
        for name, payload in INVALID_CASES.items():
            with self.subTest(case=name):
                self.assertFalse(VALIDATOR.is_valid(payload), name)
                self.assertFalse(model_accepts(payload), name)

    def test_recorded_divergences_stay_schema_only(self) -> None:
        # A recorded divergence that stops diverging means the schema was
        # tightened; move the case into INVALID_CASES then.
        for name, payload in SCHEMA_ONLY_VALID_CASES.items():
            with self.subTest(case=name):
                self.assertTrue(VALIDATOR.is_valid(payload), name)
                self.assertFalse(model_accepts(payload), name)

    def test_unsorted_string_sets_are_canonicalized_not_rejected(self) -> None:
        # Canonical order is a property of conform_issue's output; neither
        # authority rejects unsorted input, and the schema cannot require
        # sortedness of the canonical form (no ordering keyword exists).
        unsorted = mutated(lambda issue: issue["labels"].reverse())

        self.assertTrue(VALIDATOR.is_valid(unsorted))
        issue = conform_issue(unsorted)
        self.assertEqual(sorted(unsorted["labels"]), issue["labels"])
        self.assertTrue(VALIDATOR.is_valid(issue))

    def test_valid_cases_stay_valid_after_canonicalization(self) -> None:
        for name, payload in VALID_CASES.items():
            with self.subTest(case=name):
                self.assertTrue(VALIDATOR.is_valid(conform_issue(payload)), name)

    def test_schema_required_matches_the_model_field_set(self) -> None:
        model_fields = [field.alias for field in IssueProfile.model_fields.values()]

        self.assertEqual(model_fields, SCHEMA["required"])
        self.assertEqual(set(model_fields), set(SCHEMA["properties"]))

    def test_nested_required_matches_the_nested_model_field_sets(self) -> None:
        relationships = SCHEMA["properties"]["relationships"]
        self.assertEqual(
            {field.alias for field in IssueRelationships.model_fields.values()},
            set(relationships["required"]),
        )

        for property_name, models in (
            ("origin", (GitHubIssueOrigin, MarkdownIssueOrigin)),
            ("location", (GitHubIssueLocation, MarkdownIssueLocation)),
        ):
            members = SCHEMA["properties"][property_name]["oneOf"]
            self.assertEqual(len(models), len(members))
            for model, member in zip(models, members, strict=True):
                with self.subTest(property=property_name, model=model.__name__):
                    self.assertEqual(
                        {field.alias for field in model.model_fields.values()},
                        set(member["required"]),
                    )

    def test_conform_issue_does_not_mutate_its_input(self) -> None:
        payload = github_issue()
        payload["labels"].reverse()
        snapshot = copy.deepcopy(payload)

        conform_issue(payload)

        self.assertEqual(snapshot, payload)


if __name__ == "__main__":
    unittest.main()
