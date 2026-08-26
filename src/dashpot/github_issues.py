from __future__ import annotations

from typing import Any, Mapping

from .issue_profile import IssueProfileError, conform_issue_v1


_STATE_REASONS = {
    "COMPLETED": "completed",
    "DUPLICATE": "duplicate",
    "NOT_PLANNED": "not-planned",
    "REOPENED": "reopened",
}


class GitHubIssueNormalizationError(ValueError):
    """A GraphQL Issue node is incomplete, malformed, or from another repository."""


def normalize_github_issue_v1(
    record: Mapping[str, Any], *, project_id: str, repository_id: str
) -> dict[str, Any]:
    """Normalize one completely fetched GitHub GraphQL Issue node to profile v1."""

    if not isinstance(record, Mapping):
        raise GitHubIssueNormalizationError("GitHub Issue must be an object")
    _required_string(project_id, "project_id")
    _required_string(repository_id, "repository_id")

    repository = _required_object(record, "repository", "issue")
    observed_repository_id = _required_string(
        _required(repository, "id", "issue.repository"), "issue.repository.id"
    )
    if observed_repository_id != repository_id:
        raise GitHubIssueNormalizationError(
            "issue.repository.id does not match the configured GitHub repository"
        )
    repository_reference = _required_string(
        _required(repository, "nameWithOwner", "issue.repository"),
        "issue.repository.nameWithOwner",
    )

    number = _required(record, "number", "issue")
    state = _required_string(_required(record, "state", "issue"), "issue.state")
    if state not in {"OPEN", "CLOSED"}:
        raise GitHubIssueNormalizationError("issue.state must be OPEN or CLOSED")

    state_reason = _required(record, "stateReason", "issue")
    if state_reason is not None:
        if not isinstance(state_reason, str) or state_reason not in _STATE_REASONS:
            raise GitHubIssueNormalizationError(
                "issue.stateReason is not supported by Issue profile v1"
            )
        state_reason = _STATE_REASONS[state_reason]

    parent = _required(record, "parent", "issue")
    if parent is not None:
        if not isinstance(parent, Mapping):
            raise GitHubIssueNormalizationError(
                "issue.parent must be an object or null"
            )
        parent = _required_string(
            _required(parent, "id", "issue.parent"), "issue.parent.id"
        )

    profile = {
        "profileVersion": 1,
        "id": _required_string(_required(record, "id", "issue"), "issue.id"),
        "projectId": project_id,
        "reference": f"{repository_reference}#{number}",
        "title": _required_string(
            _required(record, "title", "issue"), "issue.title"
        ),
        "body": _required_string_allow_empty(
            _required(record, "body", "issue"), "issue.body"
        ),
        "state": state.lower(),
        "stateReason": state_reason,
        "labels": _connection_strings(record, "labels", "name"),
        "assignees": _connection_strings(record, "assignees", "login"),
        "author": _optional_object_string(record, "author", "login"),
        "relationships": {
            "parent": parent,
            "subIssues": _connection_strings(record, "subIssues", "id"),
            "blockedBy": _connection_strings(record, "blockedBy", "id"),
            "blocking": _connection_strings(record, "blocking", "id"),
        },
        "issueType": _optional_object_string(record, "issueType", "name"),
        "milestone": _optional_object_string(record, "milestone", "title"),
        "createdAt": _required_string(
            _required(record, "createdAt", "issue"), "issue.createdAt"
        ),
        "updatedAt": _required_string(
            _required(record, "updatedAt", "issue"), "issue.updatedAt"
        ),
        "closedAt": _optional_string_field(record, "closedAt"),
        "origin": {
            "kind": "github",
            "repositoryId": observed_repository_id,
            "number": number,
        },
        "location": {
            "kind": "github",
            "url": _required_string(
                _required(record, "url", "issue"), "issue.url"
            ),
        },
    }
    try:
        return conform_issue_v1(profile)
    except IssueProfileError as exc:
        raise GitHubIssueNormalizationError(
            f"GitHub Issue does not conform to profile v1: {exc}"
        ) from exc


def _connection_strings(
    record: Mapping[str, Any], connection_name: str, item_field: str
) -> list[str]:
    path = f"issue.{connection_name}"
    connection = _required_object(record, connection_name, "issue")
    page_info = _required_object(connection, "pageInfo", path)
    has_next_page = _required(page_info, "hasNextPage", f"{path}.pageInfo")
    if not isinstance(has_next_page, bool):
        raise GitHubIssueNormalizationError(
            f"{path}.pageInfo.hasNextPage must be a Boolean"
        )
    if has_next_page:
        raise GitHubIssueNormalizationError(
            f"{path} is not completely fetched; pagination remains"
        )

    nodes = _required(connection, "nodes", path)
    if not isinstance(nodes, list):
        raise GitHubIssueNormalizationError(f"{path}.nodes must be an array")
    values: list[str] = []
    for index, node in enumerate(nodes):
        node_path = f"{path}.nodes[{index}]"
        if not isinstance(node, Mapping):
            raise GitHubIssueNormalizationError(f"{node_path} must be an object")
        values.append(
            _required_string(
                _required(node, item_field, node_path), f"{node_path}.{item_field}"
            )
        )
    return values


def _optional_object_string(
    record: Mapping[str, Any], object_name: str, item_field: str
) -> str | None:
    value = _required(record, object_name, "issue")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GitHubIssueNormalizationError(
            f"issue.{object_name} must be an object or null"
        )
    return _required_string(
        _required(value, item_field, f"issue.{object_name}"),
        f"issue.{object_name}.{item_field}",
    )


def _optional_string_field(record: Mapping[str, Any], field: str) -> str | None:
    value = _required(record, field, "issue")
    if value is None:
        return None
    return _required_string(value, f"issue.{field}")


def _required_object(
    record: Mapping[str, Any], field: str, path: str
) -> Mapping[str, Any]:
    value = _required(record, field, path)
    if not isinstance(value, Mapping):
        raise GitHubIssueNormalizationError(f"{path}.{field} must be an object")
    return value


def _required(record: Mapping[str, Any], field: str, path: str) -> Any:
    if field not in record:
        raise GitHubIssueNormalizationError(
            f"{path}.{field} was not fetched from GitHub"
        )
    return record[field]


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise GitHubIssueNormalizationError(f"{path} must be a non-empty string")
    return value


def _required_string_allow_empty(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise GitHubIssueNormalizationError(f"{path} must be a string")
    return value
