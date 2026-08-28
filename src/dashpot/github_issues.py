from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .commands import CommandRunner, run_command
from .issue_profile import IssueProfileError, conform_issue
from .issue_sources import Clock, IssueSource, IssueSourceRefreshError


_STATE_REASONS = {
    "COMPLETED": "completed",
    "DUPLICATE": "duplicate",
    "NOT_PLANNED": "not-planned",
    "REOPENED": "reopened",
}

_PAGE_SIZE = 100
_CONNECTION_FIELDS = {
    "labels": "name",
    "assignees": "login",
    "subIssues": "id",
    "blockedBy": "id",
    "blocking": "id",
}
# Extra node fields fetched alongside the identifying field when paginating.
_CONNECTION_EXTRA_FIELDS = {"labels": ("color",)}
_LABEL_COLOR = re.compile(r"[0-9a-fA-F]{6}")

_ISSUES_QUERY = """
query DashpotIssues($repositoryId: ID!, $cursor: String) {
  node(id: $repositoryId) {
    ... on Repository {
      id
      nameWithOwner
      issues(
        first: 100
        after: $cursor
        states: [OPEN, CLOSED]
        orderBy: {field: CREATED_AT, direction: ASC}
      ) {
        nodes {
          id
          number
          url
          title
          body
          state
          stateReason
          labels(first: 100) {
            nodes { name color }
            pageInfo { hasNextPage endCursor }
          }
          assignees(first: 100) {
            nodes { login }
            pageInfo { hasNextPage endCursor }
          }
          author { login }
          parent { id }
          subIssues(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          blockedBy(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          blocking(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          issueType { name }
          milestone { title }
          createdAt
          updatedAt
          closedAt
          repository { id nameWithOwner }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""".strip()


class GitHubIssueNormalizationError(ValueError):
    """A GraphQL Issue node is incomplete, malformed, or from another repository."""


class GitHubIssuesSource(IssueSource):
    """Collect open and closed GitHub Issues as complete Issue snapshots."""

    def __init__(
        self,
        root: Path,
        *,
        project_id: str,
        repository_id: str,
        timeout: float = 20,
        runner: CommandRunner = run_command,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.root = root
        self.project_id = project_id
        self.repository_id = repository_id
        self.timeout = timeout
        self.runner = runner
        self._label_colors: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "github-issues"

    def _collect(self) -> list[dict[str, Any]]:
        records = self._collect_issue_nodes()
        issues: list[dict[str, Any]] = []
        label_colors: dict[str, str] = {}
        seen_issue_ids: set[str] = set()
        seen_issue_numbers: set[int] = set()
        for record in records:
            complete_record = self._complete_nested_connections(record)
            label_colors.update(_label_colors(complete_record))
            try:
                issue = normalize_github_issue(
                    complete_record,
                    project_id=self.project_id,
                    repository_id=self.repository_id,
                )
            except GitHubIssueNormalizationError as exc:
                raise IssueSourceRefreshError("github-profile", str(exc)) from exc
            issue_id = issue["id"]
            if issue_id in seen_issue_ids:
                raise IssueSourceRefreshError(
                    "github-pagination",
                    f"GitHub returned duplicate Issue identity {issue_id}",
                )
            issue_number = issue["number"]
            if issue_number in seen_issue_numbers:
                raise IssueSourceRefreshError(
                    "github-pagination",
                    f"GitHub returned duplicate Issue Number #{issue_number}",
                )
            seen_issue_ids.add(issue_id)
            seen_issue_numbers.add(issue_number)
            issues.append(issue)
        self._label_colors = label_colors
        return issues

    def _collect_label_colors(self) -> dict[str, str]:
        return dict(self._label_colors)

    def _collect_issue_nodes(self) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            variables = {"repositoryId": self.repository_id}
            if cursor is not None:
                variables["cursor"] = cursor
            data = self._graphql(_ISSUES_QUERY, variables)
            if data.get("node") is None:
                raise IssueSourceRefreshError(
                    "github-repository",
                    "Configured GitHub repository was not found or is inaccessible",
                )
            repository = _response_object(data, "node", "data")
            observed_repository_id = _response_string(
                repository, "id", "data.repository"
            )
            if observed_repository_id != self.repository_id:
                raise IssueSourceRefreshError(
                    "github-repository-identity",
                    "GitHub repository identity does not match Project configuration",
                )
            _response_string(repository, "nameWithOwner", "data.repository")
            issues = _response_object(repository, "issues", "data.repository")
            page_nodes, has_next, end_cursor = _connection_page(
                issues, "data.repository.issues"
            )
            nodes.extend(page_nodes)
            if not has_next:
                return nodes
            cursor = _next_cursor(end_cursor, seen_cursors, "Issue collection")

    def _complete_nested_connections(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        complete = copy.deepcopy(dict(record))
        issue_id = _response_string(complete, "id", "issue")
        for connection_name, item_field in _CONNECTION_FIELDS.items():
            connection = _response_object(complete, connection_name, "issue")
            nodes, has_next, end_cursor = _connection_page(
                connection, f"issue.{connection_name}"
            )
            seen_cursors: set[str] = set()
            while has_next:
                cursor = _next_cursor(
                    end_cursor, seen_cursors, f"Issue {issue_id} {connection_name}"
                )
                data = self._graphql(
                    _nested_connection_query(connection_name, item_field),
                    {"id": issue_id, "cursor": cursor},
                )
                node = _response_object(data, "node", "data")
                next_connection = _response_object(node, "connection", "data.node")
                next_nodes, has_next, end_cursor = _connection_page(
                    next_connection, f"issue.{connection_name}"
                )
                nodes.extend(next_nodes)
            connection["nodes"] = nodes
            connection["pageInfo"] = {"hasNextPage": False, "endCursor": end_cursor}
        return complete

    def _graphql(self, query: str, variables: Mapping[str, str]) -> Mapping[str, Any]:
        args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            args.extend(["-f", f"{key}={value}"])
        try:
            result = self.runner(args, self.root, self.timeout)
        except RuntimeError as exc:
            raise IssueSourceRefreshError(
                _classify_github_error(str(exc)), str(exc)
            ) from exc
        if result.returncode != 0:
            message = result.stderr.strip() or (
                f"gh api graphql exited {result.returncode}"
            )
            raise IssueSourceRefreshError(_classify_github_error(message), message)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise IssueSourceRefreshError(
                "github-malformed-response",
                f"GitHub returned malformed JSON: {exc.msg}",
            ) from exc
        if not isinstance(payload, dict):
            raise IssueSourceRefreshError(
                "github-malformed-response", "GitHub response is not an object"
            )
        errors = payload.get("errors")
        if errors is not None and not isinstance(errors, list):
            raise IssueSourceRefreshError(
                "github-malformed-response",
                "GitHub response has a malformed GraphQL errors value",
            )
        if errors:
            message = _graphql_error_message(errors)
            raise IssueSourceRefreshError(_classify_github_error(message), message)
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise IssueSourceRefreshError(
                "github-malformed-response", "GitHub response has no data object"
            )
        return data


def normalize_github_issue(
    record: Mapping[str, Any], *, project_id: str, repository_id: str
) -> dict[str, Any]:
    """Normalize one completely fetched GitHub GraphQL Issue node."""

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
                "issue.stateReason is not supported by the Issue profile"
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
        "id": _required_string(_required(record, "id", "issue"), "issue.id"),
        "projectId": project_id,
        "number": number,
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
        },
        "location": {
            "kind": "github",
            "url": _required_string(
                _required(record, "url", "issue"), "issue.url"
            ),
        },
    }
    try:
        return conform_issue(profile)
    except IssueProfileError as exc:
        raise GitHubIssueNormalizationError(
            f"GitHub Issue does not conform to the Issue profile: {exc}"
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


def _label_colors(record: Mapping[str, Any]) -> dict[str, str]:
    """Read the ``name -> rrggbb`` palette from a completely fetched label
    connection.

    Colour is presentation only, so a missing or malformed colour leaves the
    label neutral rather than failing the observation.
    """
    connection = record.get("labels")
    if not isinstance(connection, Mapping):
        return {}
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        return {}
    colors: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        name = node.get("name")
        color = node.get("color")
        if (
            isinstance(name, str)
            and name
            and isinstance(color, str)
            and _LABEL_COLOR.fullmatch(color)
        ):
            colors[name] = color.lower()
    return colors


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


def _response_object(
    value: Mapping[str, Any], field: str, path: str
) -> dict[str, Any]:
    if field not in value:
        raise IssueSourceRefreshError(
            "github-malformed-response", f"GitHub response has no {path}.{field}"
        )
    item = value[field]
    if item is None and field == "repository":
        raise IssueSourceRefreshError(
            "github-repository", "GitHub repository was not found or is inaccessible"
        )
    if not isinstance(item, dict):
        raise IssueSourceRefreshError(
            "github-malformed-response", f"GitHub {path}.{field} is not an object"
        )
    return item


def _response_string(value: Mapping[str, Any], field: str, path: str) -> str:
    if field not in value:
        raise IssueSourceRefreshError(
            "github-malformed-response", f"GitHub response has no {path}.{field}"
        )
    item = value[field]
    if not isinstance(item, str) or not item:
        raise IssueSourceRefreshError(
            "github-malformed-response",
            f"GitHub {path}.{field} is not a non-empty string",
        )
    return item


def _connection_page(
    connection: Mapping[str, Any], path: str
) -> tuple[list[dict[str, Any]], bool, Any]:
    nodes = connection.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        raise IssueSourceRefreshError(
            "github-malformed-response", f"GitHub {path}.nodes is not an object array"
        )
    page_info = connection.get("pageInfo")
    if not isinstance(page_info, Mapping):
        raise IssueSourceRefreshError(
            "github-malformed-response", f"GitHub {path}.pageInfo is not an object"
        )
    has_next = page_info.get("hasNextPage")
    if not isinstance(has_next, bool):
        raise IssueSourceRefreshError(
            "github-malformed-response",
            f"GitHub {path}.pageInfo.hasNextPage is not a Boolean",
        )
    return list(nodes), has_next, page_info.get("endCursor")


def _next_cursor(end_cursor: Any, seen: set[str], subject: str) -> str:
    if not isinstance(end_cursor, str) or not end_cursor:
        raise IssueSourceRefreshError(
            "github-pagination", f"{subject} has another page but no end cursor"
        )
    if end_cursor in seen:
        raise IssueSourceRefreshError(
            "github-pagination", f"{subject} repeated pagination cursor {end_cursor}"
        )
    seen.add(end_cursor)
    return end_cursor


def _nested_connection_query(connection_name: str, item_field: str) -> str:
    node_fields = " ".join(
        (item_field, *_CONNECTION_EXTRA_FIELDS.get(connection_name, ()))
    )
    return (
        "query DashpotIssueConnection($id: ID!, $cursor: String!) { "
        "node(id: $id) { ... on Issue { "
        f"connection: {connection_name}(first: {_PAGE_SIZE}, after: $cursor) {{ "
        f"nodes {{ {node_fields} }} "
        "pageInfo { hasNextPage endCursor } "
        "} } } }"
    )


def _graphql_error_message(errors: Any) -> str:
    messages = [
        error.get("message")
        for error in errors
        if isinstance(error, Mapping) and isinstance(error.get("message"), str)
    ]
    return "; ".join(messages) or "GitHub GraphQL request failed"


def _classify_github_error(message: str) -> str:
    normalized = message.casefold()
    if "rate limit" in normalized:
        return "github-rate-limit"
    if any(
        text in normalized
        for text in ("bad credentials", "not logged", "authentication", "unauthorized")
    ):
        return "github-authentication"
    if any(
        text in normalized
        for text in ("forbidden", "permission", "resource not accessible")
    ):
        return "github-permission"
    if any(
        text in normalized
        for text in ("could not resolve to a repository", "repository not found")
    ):
        return "github-repository"
    if "timed out" in normalized or "timeout" in normalized:
        return "github-timeout"
    if any(
        text in normalized
        for text in (
            "network",
            "connection",
            "could not resolve host",
            "error connecting",
        )
    ):
        return "github-network"
    if "command not found" in normalized:
        return "github-cli-unavailable"
    return "github-request"
