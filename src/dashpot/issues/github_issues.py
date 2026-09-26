"""Observe a GitHub Issue Source and conform its Issues to the Issue Profile."""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

from ..core.commands import CommandRunner, run_command
from ..core.issue_profile import IssueProfile, IssueProfileError, conform_issue
from ..core.model import IssueActivity, LinkedPullRequest, OpenBlocker
from ..github.github import (
    DEFAULT_REFRESH_BUDGET,
    MALFORMED_RESPONSE,
    NOT_FOUND,
    RATE_LIMIT_SELECTION,
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    GraphQLVariables,
    LatestRateLimit,
    RefreshBudget,
    RefreshMeter,
    rate_limit_diagnostics,
)
from ..github.github_wire import ISSUE_NODE_FIELDS, PULL_REQUEST_STATES
from .issue_sources import (
    CollectedIssues,
    IssueHint,
    IssueSource,
    IssueSourceRefreshError,
)
from .retaining_source import Clock

_PAGE_SIZE = 100


_STATE_REASONS = {
    "COMPLETED": "completed",
    "DUPLICATE": "duplicate",
    "NOT_PLANNED": "not-planned",
    "REOPENED": "reopened",
}


_CONNECTION_FIELDS = {
    "labels": "name",
    "assignees": "login",
    "subIssues": "id",
    "blockedBy": "id",
    "blocking": "id",
}


# Presentation facts a connection's nodes carry beside the one the profile
# keeps: a label's colour, and whether a blocker is still open and its name.
_CONNECTION_EXTRA_FIELDS = {
    "labels": ("color",),
    "blockedBy": ("number", "state", "repository { nameWithOwner }"),
}


_LABEL_COLOR = re.compile(r"[0-9a-fA-F]{6}")


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
{ISSUE_NODE_FIELDS}
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
{ISSUE_NODE_FIELDS}
      }}
    }}
  }}
}}
""".strip()


_ISSUE_LINKED_PULL_REQUESTS_QUERY = f"""
query DashpotIssueLinkedPullRequests($id: ID!, $cursor: String!) {{
  {RATE_LIMIT_SELECTION}
  node(id: $id) {{
    ... on Issue {{
      closedByPullRequestsReferences(
        first: 100
        after: $cursor
        includeClosedPrs: true
      ) {{
        nodes {{ number url state }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}
""".strip()


_PROFILE_CODE = "github-profile"


@dataclass(frozen=True, slots=True)
class _ObservedIssue:
    """One Issue as last observed, with what is presented beside it."""

    issue: IssueProfile
    updated_at: str
    activity: IssueActivity
    label_colors: Mapping[str, str]


class GitHubIssuesSource(IssueSource):
    """Resolve Issue Hints and explicitly enumerate complete GitHub collections."""

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
        latest_rate_limit: LatestRateLimit | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.root = root
        self.project_id = project_id
        self.repository_id = repository_id
        self.timeout = timeout
        self.runner = runner
        self.budget = budget
        self.gateway = GitHubGateway(
            root,
            timeout=timeout,
            runner=runner,
            latest_rate_limit=latest_rate_limit,
        )
        self._monotonic = monotonic or time.monotonic

    @property
    @override
    def name(self) -> str:
        return "github-issues"

    @property
    @override
    def code_prefix(self) -> str:
        return "github"

    def _start_meter(self) -> RefreshMeter:
        return self.budget.start(self._monotonic)

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
        meter.next_request("no Issue yet")
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
        repository = self._own_repository(data)
        record = _fetched(repository, "issue", "data.repository", MALFORMED_RESPONSE)
        if record is None:
            return None
        if not isinstance(record, dict):
            raise IssueSourceRefreshError(
                MALFORMED_RESPONSE, "data.repository.issue must be an object or null"
            )
        issue = self._observe_record(record, meter).issue
        if reference is not None and issue.reference != reference:
            return None
        return issue

    def _observe_records(
        self, records: Sequence[Mapping[str, Any]], meter: RefreshMeter
    ) -> list[_ObservedIssue]:
        """Observe the Issues of one listing, refusing a repeated identity.

        The listing is checked before it is keyed by identity, so a repeat
        GitHub answered is refused rather than collapsed into one Issue.
        """
        entries = [self._observe_record(record, meter) for record in records]
        self._check_collection_invariants(
            CollectedIssues(issues=tuple(entry.issue for entry in entries))
        )
        return entries

    def _observe_record(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> _ObservedIssue:
        complete = self.complete_nested_connections(record, meter)
        complete = self.complete_linked_pull_requests(complete, meter)
        issue = normalize_github_issue(
            complete, project_id=self.project_id, repository_id=self.repository_id
        )
        return _ObservedIssue(
            issue=issue,
            updated_at=_fetched_string(
                complete, "updatedAt", "issue", MALFORMED_RESPONSE
            ),
            activity=issue_activity(complete),
            label_colors=label_colors(complete),
        )

    def complete_nested_connections(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> dict[str, Any]:
        complete = copy.deepcopy(dict(record))
        issue_id = _fetched_string(complete, "id", "issue", MALFORMED_RESPONSE)
        for connection_name, item_field in _CONNECTION_FIELDS.items():
            connection = _object(complete, connection_name, "issue", MALFORMED_RESPONSE)
            nodes, has_next, end_cursor = _connection_page(
                connection, f"issue.{connection_name}", MALFORMED_RESPONSE
            )
            nodes, end_cursor = self._complete_issue_connection_pages(
                issue_id,
                nodes,
                has_next,
                end_cursor,
                meter,
                query=_nested_connection_query(connection_name, item_field),
                response_field="connection",
                response_path=f"issue.{connection_name}",
                trail_subject=f"Issue {issue_id} {connection_name}",
                request_subject=f"{connection_name} of Issue {issue_id}",
            )
            connection["nodes"] = nodes
            connection["pageInfo"] = {"hasNextPage": False, "endCursor": end_cursor}
        return complete

    def complete_linked_pull_requests(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> dict[str, Any]:
        """Complete Linked Pull Requests while keeping engagement best-effort."""
        complete = copy.deepcopy(dict(record))
        issue_id = _fetched_string(complete, "id", "issue", MALFORMED_RESPONSE)
        connection = complete.get("closedByPullRequestsReferences")
        if not isinstance(connection, dict):
            return complete
        nodes = connection.get("nodes")
        page_info = connection.get("pageInfo")
        if (
            not isinstance(nodes, list)
            or not all(isinstance(node, dict) for node in nodes)
            or not isinstance(page_info, dict)
            or not isinstance(page_info.get("hasNextPage"), bool)
        ):
            return complete
        has_next = page_info["hasNextPage"]
        end_cursor = page_info.get("endCursor")
        nodes, end_cursor = self._complete_issue_connection_pages(
            issue_id,
            nodes,
            has_next,
            end_cursor,
            meter,
            query=_ISSUE_LINKED_PULL_REQUESTS_QUERY,
            response_field="closedByPullRequestsReferences",
            response_path="data.node.closedByPullRequestsReferences",
            trail_subject=f"Issue {issue_id} Linked Pull Requests",
            request_subject=f"Linked Pull Requests of Issue {issue_id}",
        )
        connection["nodes"] = nodes
        connection["pageInfo"] = {"hasNextPage": False, "endCursor": end_cursor}
        return complete

    def _complete_issue_connection_pages(
        self,
        issue_id: str,
        nodes: list[dict[str, Any]],
        has_next: bool,
        end_cursor: object,
        meter: RefreshMeter,
        *,
        query: str,
        response_field: str,
        response_path: str,
        trail_subject: str,
        request_subject: str,
    ) -> tuple[list[dict[str, Any]], object]:
        """Complete one already-validated connection owned by an Issue."""
        trail = CursorTrail(trail_subject)
        while has_next:
            cursor = trail.follow(end_cursor)
            meter.next_request(f"{len(nodes)} {request_subject}")
            data = self.gateway.graphql(query, {"id": issue_id, "cursor": cursor})
            issue = _object(data, "node", "data", MALFORMED_RESPONSE)
            connection = _object(issue, response_field, "data.node", MALFORMED_RESPONSE)
            next_nodes, has_next, end_cursor = _connection_page(
                connection, response_path, MALFORMED_RESPONSE
            )
            nodes.extend(next_nodes)
        return nodes, end_cursor

    def _own_repository(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        """The repository node of an answer, checked to be the configured one."""
        repository = _object(data, "node", "data", MALFORMED_RESPONSE)
        observed_repository_id = _fetched_string(
            repository, "id", "data.repository", MALFORMED_RESPONSE
        )
        if observed_repository_id != self.repository_id:
            raise IssueSourceRefreshError(
                "github-repository-identity",
                "GitHub repository identity does not match Project configuration",
            )
        _fetched_string(
            repository, "nameWithOwner", "data.repository", MALFORMED_RESPONSE
        )
        return repository

    def _repository_query(
        self, query: str, variables: GraphQLVariables
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

    @override
    def _collect(self) -> CollectedIssues:
        """Enumerate one complete Issue collection under a single Refresh Budget."""
        meter = self._start_meter()
        cursor: str | None = None
        trail = CursorTrail("Issue collection")
        entries: list[_ObservedIssue] = []
        try:
            while True:
                variables: GraphQLVariables = {"repositoryId": self.repository_id}
                if cursor is not None:
                    variables["cursor"] = cursor
                meter.next_request(f"{len(entries)} Issues")
                repository = self._own_repository(
                    self._repository_query(_ISSUES_QUERY, variables)
                )
                connection = _object(
                    repository, "issues", "data.repository", MALFORMED_RESPONSE
                )
                nodes, has_next, end_cursor = _connection_page(
                    connection, "data.repository.issues", MALFORMED_RESPONSE
                )
                entries.extend(self._observe_records(nodes, meter))
                if not has_next:
                    break
                cursor = trail.follow(end_cursor)
        except GitHubRequestError as exc:
            raise IssueSourceRefreshError(exc.code, str(exc)) from exc
        entries.sort(key=lambda entry: entry.issue.number)
        colors: dict[str, str] = {}
        for entry in sorted(entries, key=lambda entry: entry.updated_at):
            colors.update(entry.label_colors)
        return CollectedIssues(
            issues=tuple(entry.issue for entry in entries),
            label_colors=colors,
            issue_activity={entry.issue.id: entry.activity for entry in entries},
            diagnostics=rate_limit_diagnostics(self.gateway.rate_limit, self.name),
        )


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


def label_colors(record: Mapping[str, Any]) -> dict[str, str]:
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


def open_blockers(record: Mapping[str, Any]) -> tuple[OpenBlocker, ...]:
    """Read the still-open Issues of a completely fetched ``blockedBy`` connection.

    Unlike engagement, a blocker that cannot be read is not skipped: dropping
    it would show a blocked Issue as Ready, so the observation fails instead.
    """
    connection = record.get("blockedBy")
    nodes = connection.get("nodes") if isinstance(connection, Mapping) else None
    if not isinstance(nodes, list):
        raise ValueError("Blocking Issue observation is unavailable")
    blockers: list[OpenBlocker] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            raise ValueError("Blocking Issue observation is malformed")
        identity = node.get("id")
        number = node.get("number")
        state = node.get("state")
        repository = node.get("repository")
        name = (
            repository.get("nameWithOwner") if isinstance(repository, Mapping) else None
        )
        if (
            not isinstance(identity, str)
            or not identity
            or type(number) is not int
            or number <= 0
            or state not in {"OPEN", "CLOSED"}
            or not isinstance(name, str)
            or not name
        ):
            raise ValueError("Blocking Issue observation is malformed")
        if state == "OPEN":
            blockers.append(
                OpenBlocker(id=identity, reference=f"{name}#{number}", number=number)
            )
    return tuple(blockers)


def issue_activity(record: Mapping[str, Any]) -> IssueActivity:
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
            and state in PULL_REQUEST_STATES
        ):
            linked_pull_requests.append(
                LinkedPullRequest(
                    number=number, url=url, state=PULL_REQUEST_STATES[state]
                )
            )
    linked_pull_requests.sort(key=lambda pull: pull.number)
    linked_pull_requests = linked_pull_requests[:20]
    # Relationship evidence uses the completed connection, while presentation
    # keeps the lowest-numbered twenty and says how many remain unlisted.
    unlisted = 0
    total = references.get("totalCount") if isinstance(references, Mapping) else None
    if isinstance(total, int) and not isinstance(total, bool):
        unlisted = max(0, total - len(linked_pull_requests))
    return IssueActivity(
        comment_count=comment_count,
        linked_pull_requests=linked_pull_requests,
        unlisted_pull_request_count=unlisted,
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
