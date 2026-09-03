from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from typing_extensions import override

from .commands import CommandRunner, run_command
from .github import (
    DEFAULT_REFRESH_BUDGET,
    NOT_FOUND,
    RATE_LIMIT_SELECTION,
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    RefreshBudget,
    RefreshMeter,
)
from .issue_profile import IssueProfile, IssueProfileError, conform_issue
from .issue_sources import (
    Clock,
    CollectedIssues,
    IssueHint,
    IssueSource,
    IssueSourceDiagnostic,
    IssueSourceRefreshError,
)
from .model import IssueActivity, LinkedPullRequest, PullRequestState

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

# The complete Issue node both queries fetch, so a single-Issue lookup
# normalizes through exactly the same profile pipeline as a full collection.
_ISSUE_NODE_FIELDS = """
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
          comments { totalCount }
          closedByPullRequestsReferences(first: 20, includeClosedPrs: true) {
            nodes { number url state }
          }
          createdAt
          updatedAt
          closedAt
          repository { id nameWithOwner }
""".strip("\n")

_ISSUES_QUERY = f"""
query DashpotIssues($repositoryId: ID!, $cursor: String) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      nameWithOwner
      issues(
        first: 100
        after: $cursor
        states: [OPEN, CLOSED]
        orderBy: {{field: CREATED_AT, direction: ASC}}
      ) {{
        nodes {{
{_ISSUE_NODE_FIELDS}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}
""".strip()

_ISSUE_QUERY = f"""
query DashpotIssue($repositoryId: ID!, $number: Int!) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      nameWithOwner
      issue(number: $number) {{
{_ISSUE_NODE_FIELDS}
      }}
    }}
  }}
}}
""".strip()


# The two ways a collection cycle goes wrong, told apart by diagnostic code:
# GitHub answered well-formed data but an Issue does not conform to the Issue
# profile, versus a response whose shape is not the GraphQL contract at all.
_PROFILE_CODE = "github-profile"
_RESPONSE_CODE = "github-malformed-response"


class GitHubIssuesSource(IssueSource):
    """Collect open and closed GitHub Issues as complete Issue snapshots."""

    def __init__(
        self,
        root: Path,
        *,
        project_id: str,
        repository_id: str,
        timeout: float = 10,
        runner: CommandRunner = run_command,
        clock: Clock | None = None,
        budget: RefreshBudget = DEFAULT_REFRESH_BUDGET,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.root = root
        self.project_id = project_id
        self.repository_id = repository_id
        self.timeout = timeout
        self.runner = runner
        self.budget = budget
        self.gateway = GitHubGateway(root, timeout=timeout, runner=runner)
        self._monotonic = monotonic

    @property
    @override
    def name(self) -> str:
        return "github-issues"

    @property
    @override
    def code_prefix(self) -> str:
        return "github"

    @override
    def _collect(self) -> CollectedIssues:
        try:
            return self._collect_from_github()
        except GitHubRequestError as exc:
            raise IssueSourceRefreshError(exc.code, str(exc)) from exc

    def _collect_from_github(self) -> CollectedIssues:
        meter = self._start_meter()
        records = self._collect_issue_nodes(meter)
        issues: list[IssueProfile] = []
        label_colors: dict[str, str] = {}
        issue_activity: dict[str, IssueActivity] = {}
        for record in records:
            complete_record = self._complete_nested_connections(record, meter)
            label_colors.update(_label_colors(complete_record))
            issue = normalize_github_issue(
                complete_record,
                project_id=self.project_id,
                repository_id=self.repository_id,
            )
            issues.append(issue)
            issue_activity[issue.id] = _issue_activity(complete_record)
        return CollectedIssues(
            issues=tuple(issues),
            label_colors=label_colors,
            issue_activity=issue_activity,
            diagnostics=self._rate_limit_diagnostics(),
        )

    def _start_meter(self) -> RefreshMeter:
        if self._monotonic is None:
            return self.budget.start()
        return self.budget.start(self._monotonic)

    def _rate_limit_diagnostics(self) -> tuple[IssueSourceDiagnostic, ...]:
        """Warn while the hour's GraphQL points run low; never fail for it."""
        rate_limit = self.gateway.rate_limit
        if rate_limit is None or not rate_limit.low:
            return ()
        return (
            IssueSourceDiagnostic(
                source=self.name,
                code="github-rate-limit-low",
                severity="warning",
                message=(
                    f"GitHub GraphQL rate limit is low: {rate_limit.remaining} of "
                    f"{rate_limit.limit} points remain until {rate_limit.reset_at}; "
                    f"the last request cost {rate_limit.cost}"
                ),
            ),
        )

    @override
    def find(self, hint: IssueHint) -> IssueProfile | None:
        """Resolve a numbered Issue Hint with one GraphQL Issue lookup.

        A GitHub Issue Reference is always ``owner/repo#number``, so a hint
        without a number (a Local Issue slug) misses without a request. A
        repository-qualified hint must round-trip: the resolved Issue's
        Reference has to equal it, so another repository's reference misses.
        """
        if hint.number is None:
            return None
        try:
            return self._find_on_github(hint.number, hint.reference)
        except GitHubRequestError as exc:
            raise IssueSourceRefreshError(exc.code, str(exc)) from exc

    def _find_on_github(
        self, number: int, reference: str | None
    ) -> IssueProfile | None:
        meter = self._start_meter()
        meter.next_page("no Issue yet")
        try:
            data = self._repository_query(
                _ISSUE_QUERY,
                {"repositoryId": self.repository_id, "number": number},
            )
        except GitHubRequestError as exc:
            # GitHub reports a missing Issue number as a NOT_FOUND error at
            # the issue field rather than a null field; that is a miss, not
            # an outage. A not-found described only in prose is read the
            # same way, since the one thing asked for by number is the Issue.
            if exc.code == NOT_FOUND and exc.path[-1:] in ((), ("issue",)):
                return None
            raise
        repository = _object(data, "node", "data", _RESPONSE_CODE)
        observed_repository_id = _fetched_string(
            repository, "id", "data.repository", _RESPONSE_CODE
        )
        if observed_repository_id != self.repository_id:
            raise IssueSourceRefreshError(
                "github-repository-identity",
                "GitHub repository identity does not match Project configuration",
            )
        record = _fetched(repository, "issue", "data.repository", _RESPONSE_CODE)
        if record is None:
            return None
        if not isinstance(record, dict):
            raise IssueSourceRefreshError(
                _RESPONSE_CODE, "data.repository.issue must be an object or null"
            )
        issue = normalize_github_issue(
            self._complete_nested_connections(record, meter),
            project_id=self.project_id,
            repository_id=self.repository_id,
        )
        if reference is not None and issue.reference != reference:
            return None
        return issue

    def _collect_issue_nodes(self, meter: RefreshMeter) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        trail = CursorTrail("Issue collection")
        while True:
            variables: dict[str, str | int] = {"repositoryId": self.repository_id}
            if cursor is not None:
                variables["cursor"] = cursor
            meter.next_page(f"{len(nodes)} Issues")
            data = self._repository_query(_ISSUES_QUERY, variables)
            repository = _object(data, "node", "data", _RESPONSE_CODE)
            observed_repository_id = _fetched_string(
                repository, "id", "data.repository", _RESPONSE_CODE
            )
            if observed_repository_id != self.repository_id:
                raise IssueSourceRefreshError(
                    "github-repository-identity",
                    "GitHub repository identity does not match Project configuration",
                )
            _fetched_string(
                repository, "nameWithOwner", "data.repository", _RESPONSE_CODE
            )
            issues = _object(repository, "issues", "data.repository", _RESPONSE_CODE)
            page_nodes, has_next, end_cursor = _connection_page(
                issues, "data.repository.issues", _RESPONSE_CODE
            )
            nodes.extend(page_nodes)
            if not has_next:
                return nodes
            cursor = trail.follow(end_cursor)

    def _complete_nested_connections(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> dict[str, Any]:
        complete = copy.deepcopy(dict(record))
        issue_id = _fetched_string(complete, "id", "issue", _RESPONSE_CODE)
        for connection_name, item_field in _CONNECTION_FIELDS.items():
            connection = _object(complete, connection_name, "issue", _RESPONSE_CODE)
            nodes, has_next, end_cursor = _connection_page(
                connection, f"issue.{connection_name}", _RESPONSE_CODE
            )
            trail = CursorTrail(f"Issue {issue_id} {connection_name}")
            while has_next:
                cursor = trail.follow(end_cursor)
                meter.next_page(f"{len(nodes)} {connection_name} of Issue {issue_id}")
                data = self.gateway.graphql(
                    _nested_connection_query(connection_name, item_field),
                    {"id": issue_id, "cursor": cursor},
                )
                node = _object(data, "node", "data", _RESPONSE_CODE)
                next_connection = _object(
                    node, "connection", "data.node", _RESPONSE_CODE
                )
                next_nodes, has_next, end_cursor = _connection_page(
                    next_connection, f"issue.{connection_name}", _RESPONSE_CODE
                )
                nodes.extend(next_nodes)
            connection["nodes"] = nodes
            connection["pageInfo"] = {"hasNextPage": False, "endCursor": end_cursor}
        return complete

    def _repository_query(
        self, query: str, variables: Mapping[str, str | int]
    ) -> Mapping[str, Any]:
        """Run a query rooted at the configured repository node.

        The one node asked for by identity is the repository, so a null or
        not-found node is the configured repository gone or inaccessible.
        """
        try:
            data = self.gateway.graphql(query, variables)
        except GitHubRequestError as exc:
            if exc.code == NOT_FOUND and exc.path == ("node",):
                raise GitHubRequestError(
                    "github-repository",
                    "Configured GitHub repository was not found or is inaccessible",
                ) from exc
            raise
        if data.get("node") is None:
            raise GitHubRequestError(
                "github-repository",
                "Configured GitHub repository was not found or is inaccessible",
            )
        return data


def normalize_github_issue(
    record: Mapping[str, Any], *, project_id: str, repository_id: str
) -> IssueProfile:
    """Normalize one completely fetched GitHub GraphQL Issue node.

    Every refusal is an ``IssueSourceRefreshError`` with the ``github-profile``
    code: GitHub answered well, but this Issue does not conform.
    """

    if not isinstance(record, Mapping):
        raise IssueSourceRefreshError(_PROFILE_CODE, "GitHub Issue must be an object")
    _string(project_id, "project_id", _PROFILE_CODE)
    _string(repository_id, "repository_id", _PROFILE_CODE)

    repository = _object(record, "repository", "issue", _PROFILE_CODE)
    observed_repository_id = _fetched_string(
        repository, "id", "issue.repository", _PROFILE_CODE
    )
    if observed_repository_id != repository_id:
        raise IssueSourceRefreshError(
            _PROFILE_CODE,
            "issue.repository.id does not match the configured GitHub repository",
        )
    repository_reference = _fetched_string(
        repository, "nameWithOwner", "issue.repository", _PROFILE_CODE
    )

    number = _fetched(record, "number", "issue", _PROFILE_CODE)
    state = _fetched_string(record, "state", "issue", _PROFILE_CODE)
    if state not in {"OPEN", "CLOSED"}:
        raise IssueSourceRefreshError(
            _PROFILE_CODE, "issue.state must be OPEN or CLOSED"
        )

    state_reason = _fetched(record, "stateReason", "issue", _PROFILE_CODE)
    if state_reason is not None:
        if not isinstance(state_reason, str) or state_reason not in _STATE_REASONS:
            raise IssueSourceRefreshError(
                _PROFILE_CODE, "issue.stateReason is not supported by the Issue profile"
            )
        state_reason = _STATE_REASONS[state_reason]

    parent = _fetched(record, "parent", "issue", _PROFILE_CODE)
    if parent is not None:
        if not isinstance(parent, Mapping):
            raise IssueSourceRefreshError(
                _PROFILE_CODE, "issue.parent must be an object or null"
            )
        parent = _fetched_string(parent, "id", "issue.parent", _PROFILE_CODE)

    profile = {
        "id": _fetched_string(record, "id", "issue", _PROFILE_CODE),
        "projectId": project_id,
        "number": number,
        "reference": f"{repository_reference}#{number}",
        "title": _fetched_string(record, "title", "issue", _PROFILE_CODE),
        "body": _string_allow_empty(
            _fetched(record, "body", "issue", _PROFILE_CODE),
            "issue.body",
            _PROFILE_CODE,
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
        "createdAt": _fetched_string(record, "createdAt", "issue", _PROFILE_CODE),
        "updatedAt": _fetched_string(record, "updatedAt", "issue", _PROFILE_CODE),
        "closedAt": _optional_string_field(record, "closedAt"),
        "origin": {
            "kind": "github",
            "repositoryId": observed_repository_id,
        },
        "location": {
            "kind": "github",
            "url": _fetched_string(record, "url", "issue", _PROFILE_CODE),
        },
    }
    try:
        return conform_issue(profile)
    except IssueProfileError as exc:
        raise IssueSourceRefreshError(
            _PROFILE_CODE,
            f"GitHub Issue does not conform to the Issue profile: {exc}",
        ) from exc


def _connection_strings(
    record: Mapping[str, Any], connection_name: str, item_field: str
) -> list[str]:
    path = f"issue.{connection_name}"
    connection = _object(record, connection_name, "issue", _PROFILE_CODE)
    nodes, has_next_page, _end_cursor = _connection_page(
        connection, path, _PROFILE_CODE
    )
    if has_next_page:
        raise IssueSourceRefreshError(
            _PROFILE_CODE, f"{path} is not completely fetched; pagination remains"
        )
    values: list[str] = []
    for index, node in enumerate(nodes):
        node_path = f"{path}.nodes[{index}]"
        values.append(_fetched_string(node, item_field, node_path, _PROFILE_CODE))
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


_PULL_REQUEST_STATES: dict[str, PullRequestState] = {
    "OPEN": "open",
    "CLOSED": "closed",
    "MERGED": "merged",
}


def _issue_activity(record: Mapping[str, Any]) -> IssueActivity:
    """Read comment count and linked pull requests from a GraphQL Issue node.

    Engagement is presentation only, so anything missing or malformed reads
    as no engagement rather than failing the observation.
    """
    comment_count = 0
    comments = record.get("comments")
    if isinstance(comments, Mapping):
        total = comments.get("totalCount")
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            comment_count = total
    linked_pull_requests: list[LinkedPullRequest] = []
    references = record.get("closedByPullRequestsReferences")
    nodes = references.get("nodes") if isinstance(references, Mapping) else None
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, Mapping):
            continue
        number = node.get("number")
        url = node.get("url")
        state = node.get("state")
        if (
            isinstance(number, int)
            and not isinstance(number, bool)
            and number > 0
            and isinstance(url, str)
            and url
            and isinstance(state, str)
            and state in _PULL_REQUEST_STATES
        ):
            linked_pull_requests.append(
                LinkedPullRequest(
                    number=number, url=url, state=_PULL_REQUEST_STATES[state]
                )
            )
    linked_pull_requests.sort(key=lambda pull: pull.number)
    return IssueActivity(
        comment_count=comment_count, linked_pull_requests=linked_pull_requests
    )


def _optional_object_string(
    record: Mapping[str, Any], object_name: str, item_field: str
) -> str | None:
    value = _fetched(record, object_name, "issue", _PROFILE_CODE)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise IssueSourceRefreshError(
            _PROFILE_CODE, f"issue.{object_name} must be an object or null"
        )
    return _fetched_string(value, item_field, f"issue.{object_name}", _PROFILE_CODE)


def _optional_string_field(record: Mapping[str, Any], field: str) -> str | None:
    value = _fetched(record, field, "issue", _PROFILE_CODE)
    if value is None:
        return None
    return _string(value, f"issue.{field}", _PROFILE_CODE)


# The one validator family over raw GitHub JSON: each validator narrows one
# value and refuses with the caller's diagnostic code — ``github-profile``
# when a well-formed response carries an Issue that does not conform,
# ``github-malformed-response`` when the response shape itself is wrong.
def _fetched(record: Mapping[str, Any], field: str, path: str, code: str) -> Any:  # ruff: ignore[any-type]
    if field not in record:
        raise IssueSourceRefreshError(
            code, f"{path}.{field} was not fetched from GitHub"
        )
    return record[field]


def _object(
    record: Mapping[str, Any], field: str, path: str, code: str
) -> dict[str, Any]:
    value = _fetched(record, field, path, code)
    if not isinstance(value, dict):
        raise IssueSourceRefreshError(code, f"{path}.{field} must be an object")
    return value


def _string(value: object, path: str, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise IssueSourceRefreshError(code, f"{path} must be a non-empty string")
    return value


def _string_allow_empty(value: object, path: str, code: str) -> str:
    if not isinstance(value, str):
        raise IssueSourceRefreshError(code, f"{path} must be a string")
    return value


def _fetched_string(record: Mapping[str, Any], field: str, path: str, code: str) -> str:
    return _string(_fetched(record, field, path, code), f"{path}.{field}", code)


def _connection_page(
    connection: Mapping[str, Any], path: str, code: str
) -> tuple[list[dict[str, Any]], bool, object]:
    nodes = _fetched(connection, "nodes", path, code)
    if not isinstance(nodes, list):
        raise IssueSourceRefreshError(code, f"{path}.nodes must be an object array")
    records: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            raise IssueSourceRefreshError(code, f"{path}.nodes must be an object array")
        records.append(node)
    page_info = _object(connection, "pageInfo", path, code)
    has_next = _fetched(page_info, "hasNextPage", f"{path}.pageInfo", code)
    if not isinstance(has_next, bool):
        raise IssueSourceRefreshError(
            code, f"{path}.pageInfo.hasNextPage must be a Boolean"
        )
    return records, has_next, page_info.get("endCursor")


def _nested_connection_query(connection_name: str, item_field: str) -> str:
    node_fields = " ".join(
        (item_field, *_CONNECTION_EXTRA_FIELDS.get(connection_name, ()))
    )
    return (
        "query DashpotIssueConnection($id: ID!, $cursor: String!) { "
        f"{RATE_LIMIT_SELECTION} "
        "node(id: $id) { ... on Issue { "
        f"connection: {connection_name}(first: {_PAGE_SIZE}, after: $cursor) {{ "
        f"nodes {{ {node_fields} }} "
        "pageInfo { hasNextPage endCursor } "
        "} } } }"
    )
