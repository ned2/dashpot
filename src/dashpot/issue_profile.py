from __future__ import annotations

import copy
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit


ISSUE_PROFILE_VERSION = 1

_ISSUE_KEYS = {
    "profileVersion",
    "id",
    "projectId",
    "reference",
    "title",
    "body",
    "state",
    "stateReason",
    "labels",
    "assignees",
    "author",
    "relationships",
    "issueType",
    "milestone",
    "createdAt",
    "updatedAt",
    "closedAt",
    "origin",
    "location",
}
_RELATIONSHIP_KEYS = {"parent", "subIssues", "blockedBy", "blocking"}
_STATE_REASONS = {"completed", "duplicate", "not-planned", "reopened"}


class IssueProfileError(ValueError):
    """A source record cannot satisfy the complete Issue profile."""


def conform_issue_v1(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize one complete version 1 Issue snapshot."""

    if not isinstance(value, Mapping):
        raise IssueProfileError("issue must be an object")
    issue = copy.deepcopy(dict(value))
    _require_keys(issue, _ISSUE_KEYS, "issue")

    if (
        not isinstance(issue["profileVersion"], int)
        or isinstance(issue["profileVersion"], bool)
        or issue["profileVersion"] != ISSUE_PROFILE_VERSION
    ):
        raise IssueProfileError("profileVersion must be 1")
    for key in ("id", "projectId", "reference", "title"):
        _require_non_empty_string(issue[key], key)
    if not isinstance(issue["body"], str):
        raise IssueProfileError("body must be a string")

    state = issue["state"]
    if not isinstance(state, str) or state not in {"open", "closed"}:
        raise IssueProfileError("state must be 'open' or 'closed'")
    state_reason = issue["stateReason"]
    if state_reason is not None and (
        not isinstance(state_reason, str) or state_reason not in _STATE_REASONS
    ):
        raise IssueProfileError(
            "stateReason must be null, 'completed', 'duplicate', 'not-planned', "
            "or 'reopened'"
        )
    if state == "open" and state_reason not in {None, "reopened"}:
        raise IssueProfileError("an open Issue cannot have a closed stateReason")
    if state == "closed" and state_reason == "reopened":
        raise IssueProfileError("a closed Issue cannot have stateReason 'reopened'")

    issue["labels"] = _canonical_string_set(issue["labels"], "labels")
    issue["assignees"] = _canonical_string_set(issue["assignees"], "assignees")
    _require_optional_string(issue["author"], "author")
    _require_optional_string(issue["issueType"], "issueType")
    _require_optional_string(issue["milestone"], "milestone")

    relationships = issue["relationships"]
    if not isinstance(relationships, dict):
        raise IssueProfileError("relationships must be an object")
    _require_keys(relationships, _RELATIONSHIP_KEYS, "relationships")
    _require_optional_string(relationships["parent"], "relationships.parent")
    for key in ("subIssues", "blockedBy", "blocking"):
        relationships[key] = _canonical_string_set(
            relationships[key], f"relationships.{key}"
        )
    issue_id = issue["id"]
    related_ids = [
        relationships["parent"],
        *relationships["subIssues"],
        *relationships["blockedBy"],
        *relationships["blocking"],
    ]
    if issue_id in related_ids:
        raise IssueProfileError("an Issue cannot relate to itself")

    for key in ("createdAt", "updatedAt", "closedAt"):
        _require_optional_timestamp(issue[key], key)
    if state == "open" and issue["closedAt"] is not None:
        raise IssueProfileError("an open Issue must have closedAt null")

    _validate_origin(issue["origin"])
    _validate_location(issue["location"])
    return issue


def semantic_projection_v1(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the source-neutral facts used for v1 semantic equivalence."""

    issue = conform_issue_v1(value)
    del issue["origin"]
    del issue["location"]
    return issue


def semantically_equivalent_v1(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    """Compare complete v1 Issues after excluding provenance and location."""

    return semantic_projection_v1(left) == semantic_projection_v1(right)


def _require_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise IssueProfileError(f"{path} is missing fields: {', '.join(missing)}")
    if unexpected:
        raise IssueProfileError(
            f"{path} has unexpected fields: {', '.join(unexpected)}"
        )


def _require_non_empty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise IssueProfileError(f"{path} must be a non-empty string")


def _require_optional_string(value: Any, path: str) -> None:
    if value is not None:
        _require_non_empty_string(value, path)


def _canonical_string_set(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise IssueProfileError(f"{path} must be an array")
    for item in value:
        _require_non_empty_string(item, f"{path} item")
    if len(value) != len(set(value)):
        raise IssueProfileError(f"{path} must not contain duplicates")
    return sorted(value)


def _require_optional_timestamp(value: Any, path: str) -> None:
    if value is None:
        return
    _require_non_empty_string(value, path)
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        raise IssueProfileError(
            f"{path} must be an RFC 3339 UTC timestamp ending in Z"
        )
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise IssueProfileError(f"{path} must be a valid RFC 3339 timestamp") from exc


def _validate_origin(value: Any) -> None:
    if not isinstance(value, dict):
        raise IssueProfileError("origin must be an object")
    kind = value.get("kind")
    if kind == "github":
        _require_keys(value, {"kind", "repositoryId", "number"}, "origin")
        _require_non_empty_string(value["repositoryId"], "origin.repositoryId")
        if (
            not isinstance(value["number"], int)
            or isinstance(value["number"], bool)
            or value["number"] < 1
        ):
            raise IssueProfileError("origin.number must be a positive integer")
        return
    if kind == "markdown":
        _require_keys(value, {"kind", "schemaVersion"}, "origin")
        if (
            not isinstance(value["schemaVersion"], int)
            or isinstance(value["schemaVersion"], bool)
            or value["schemaVersion"] != 1
        ):
            raise IssueProfileError("origin.schemaVersion must be 1")
        return
    raise IssueProfileError("origin.kind must be 'github' or 'markdown'")


def _validate_location(value: Any) -> None:
    if not isinstance(value, dict):
        raise IssueProfileError("location must be an object")
    kind = value.get("kind")
    if kind == "github":
        _require_keys(value, {"kind", "url"}, "location")
        _require_non_empty_string(value["url"], "location.url")
        url = urlsplit(value["url"])
        if url.scheme != "https" or not url.netloc:
            raise IssueProfileError("location.url must be an absolute HTTPS URL")
        return
    if kind == "markdown":
        _require_keys(value, {"kind", "path", "line"}, "location")
        _require_non_empty_string(value["path"], "location.path")
        path = PurePosixPath(value["path"])
        if path.is_absolute() or ".." in path.parts:
            raise IssueProfileError(
                "location.path must be a repository-relative POSIX path"
            )
        if (
            not isinstance(value["line"], int)
            or isinstance(value["line"], bool)
            or value["line"] < 1
        ):
            raise IssueProfileError("location.line must be a positive integer")
        return
    raise IssueProfileError("location.kind must be 'github' or 'markdown'")
