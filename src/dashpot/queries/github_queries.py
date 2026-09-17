"""Query GitHub pages, totals and identities without observing whole history."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from typing_extensions import override

from ..core.commands import CommandRunner, run_command
from ..core.issue_profile import IssueProfile
from ..core.model import Diagnostic, PullRequest
from ..core.observation_errors import QUERY_OBSERVATION_FAILURES
from ..core.pydantic import WireModel
from ..github.github import (
    DEFAULT_REFRESH_BUDGET,
    GitHubGateway,
    GitHubRequestError,
    GraphQLVariables,
    RefreshBudget,
    RefreshMeter,
)
from ..github.github_wire import (
    ISSUE_NODE_FIELDS,
    PULL_REQUEST_FIELDS,
    Identity,
    Repository,
    SearchConnection,
)
from ..issues.github_issues import (
    GitHubIssuesSource,
    issue_activity,
    label_colors,
    normalize_github_issue,
)
from ..issues.github_pull_requests import (
    GitHubPullRequestsSource,
    normalize_github_pull_request,
)
from ..project.project_config import ProjectConfig, load_project_config
from .query_source import CachedQuerySource
from .source_queries import (
    AuxiliaryObservation,
    Continuation,
    InvalidContinuation,
    QueryPage,
    QueryRequest,
    ResolvedIssue,
    ResourceKind,
    SourceContext,
    SourceEnumeration,
    context_fingerprint,
    cursor_digest,
    encode_continuation,
)

_COLUMN_SORTS = {"created": "created", "last_action": "updated", "comments": "comments"}

_CONTEXT = """query DashpotQueryContext($repositoryId: ID!) {
  node(id: $repositoryId) { ... on Repository { id nameWithOwner } }
  viewer { id }
}"""
_PR_FIELDS = (
    " ".join(PULL_REQUEST_FIELDS[:9]) + "\n" + " ".join(PULL_REQUEST_FIELDS[9:])
)
_SEARCH = f"""query DashpotQueryPage($searchQuery: String!, $size: Int!, $cursor: String) {{
  search(query: $searchQuery, type: ISSUE_ADVANCED, first: $size, after: $cursor) {{
    issueCount nodes {{ __typename ... on Issue {{ id repository {{ id }} }}
      ... on PullRequest {{ {_PR_FIELDS} repository {{ id }} }} }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}"""
_IDENTITIES = f"""query DashpotResolvedIssues($ids: [ID!]!) {{
  nodes(ids: $ids) {{ __typename ... on Issue {{ {ISSUE_NODE_FIELDS} }} }}
}}"""


class _Context(WireModel):
    node: Repository
    viewer: Identity


def explicit_sort(query: str) -> bool:
    """Recognize an unquoted sort qualifier without interpreting provider syntax."""
    import re

    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+', query)
    return any(token.casefold().startswith("sort:") for token in tokens)


def validate_grouping(text: str) -> None:
    """Keep the submitted expression inside the Repository scope wrapper."""
    depth = 0
    quote: str | None = None
    escaped = False
    for character in text:
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif quote is not None:
            if character == quote:
                quote = None
        elif character == '"':
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                break
    if depth != 0 or quote is not None or escaped:
        raise GitHubRequestError(
            "github-search-syntax",
            "Close every quote and parenthesis before submitting the search",
        )


def effective_ordering(request: QueryRequest) -> str:
    """Let a submitted provider qualifier own ordering."""
    return "query" if explicit_sort(request.query) else request.ordering


class GitHubQuerySource(CachedQuerySource):
    result_limit = 1000

    def __init__(
        self,
        root: Path,
        config: ProjectConfig,
        *,
        timeout: float = 10,
        runner: CommandRunner = run_command,
        budget: RefreshBudget = DEFAULT_REFRESH_BUDGET,
    ) -> None:
        super().__init__(
            SourceContext(
                project_id=config.project_id,
                repository_id=config.repository_id,
                source="github",
                location=os.environ.get("GH_HOST", "github.com"),
            )
        )
        self.root = root
        self.config = config
        self.gateway = GitHubGateway(root, timeout=timeout, runner=runner)
        self.budget = budget
        self._meter: RefreshMeter = budget.start()
        self.profiles = GitHubIssuesSource(
            root,
            project_id=config.project_id,
            repository_id=config.repository_id,
            timeout=timeout,
            runner=runner,
            budget=budget,
        )
        self.pull_requests = GitHubPullRequestsSource(
            root,
            repository_id=config.repository_id,
            timeout=timeout,
            runner=runner,
            budget=budget,
        )
        self.repository_name = ""

    @property
    @override
    def search_prompt(self) -> str:
        return "GitHub advanced query (Enter)"

    @override
    def supports_sort(self, request: QueryRequest, column: str) -> bool:
        return column in _COLUMN_SORTS and not explicit_sort(request.query)

    @override
    def observe_context(self) -> SourceContext:
        """Observe Repository and principal identities before interpreting continuation."""
        self._meter = self.budget.start()
        self._meter.next_request("Repository and principal context")
        value = _Context.model_validate(
            self.gateway.graphql(_CONTEXT, {"repositoryId": self.context.repository_id})
        )
        if value.node.id != self.context.repository_id:
            raise ValueError("GitHub answered a different Repository Identity")
        self.repository_name = value.node.name_with_owner
        return self.context.model_copy(
            update={
                "principal": value.viewer.id,
                "configuration": load_project_config(self.root).model_dump_json(),
            }
        )

    @override
    def fetch_page(
        self,
        context: SourceContext,
        request: QueryRequest,
        token: Continuation | None,
        attempted: str,
    ) -> QueryPage:
        """Complete exactly one provider page and preserve its search ordering."""
        if context.configuration != self.config.model_dump_json():
            raise ValueError(
                "Project source configuration changed; reopen the dashboard"
            )
        validate_grouping(request.query)
        ordering = effective_ordering(request)
        expression = f"repo:{self.repository_name} is:{'issue' if request.kind == 'issues' else 'pr'}"
        if request.state != "all":
            expression += f" is:{request.state}"
        if request.query.strip():
            expression += f" ({request.query})"
        if ordering not in {"query", "provider-default"}:
            column, _, direction = ordering.rpartition(":")
            if column not in _COLUMN_SORTS or direction not in {"asc", "desc"}:
                raise ValueError("This column has no exact GitHub source ordering")
            expression += f" sort:{_COLUMN_SORTS[column]}-{direction}"
        offset = token.offset if token else 0
        if offset >= 1000:
            raise InvalidContinuation(
                "GitHub search exposes only the first 1,000 results; narrow the query"
            )
        meter = self._meter
        meter.next_request("Query Page")
        variables: GraphQLVariables = {
            "searchQuery": expression,
            "size": min(request.page_size, 1000 - offset),
        }
        if token:
            if (
                not token.provider_cursor
                or not token.trail
                or cursor_digest(token.provider_cursor) != token.trail[-1]
            ):
                raise InvalidContinuation(
                    "Invalid GitHub continuation; restart from page one"
                )
            variables["cursor"] = token.provider_cursor
        connection = SearchConnection.model_validate(
            self.gateway.graphql(_SEARCH, variables).get("search")
        )
        issues: list[IssueProfile] = []
        prs: list[PullRequest] = []
        auxiliary: dict[str, AuxiliaryObservation] = {}
        ids: list[str] = []
        for raw in connection.nodes:
            expected = "Issue" if request.kind == "issues" else "PullRequest"
            if (
                raw.get("__typename") != expected
                or Identity.model_validate(raw.get("repository")).id
                != context.repository_id
            ):
                raise ValueError(
                    "GitHub query escaped the configured Repository or resource kind"
                )
            ids.append(Identity.model_validate({"id": raw.get("id")}).id)
            if request.kind == "pull-requests":
                prs.append(
                    normalize_github_pull_request(
                        {
                            key: value
                            for key, value in raw.items()
                            if key not in {"repository", "__typename"}
                        }
                    )
                )
        if len(ids) != len(set(ids)):
            raise ValueError("GitHub returned duplicate Query Page identities")
        if request.kind == "issues":
            outcomes = self._resolve(context, ids, attempted, meter)
            for outcome in outcomes:
                if outcome.outcome != "resolved" or outcome.issue is None:
                    raise ValueError(
                        f"Cannot complete Query Page Issue {outcome.issue_id}: {outcome.outcome}"
                    )
                issues.append(outcome.issue)
                if outcome.auxiliary:
                    auxiliary[outcome.issue_id] = outcome.auxiliary
        count = len(ids)
        end = offset + count
        if count > request.page_size or (
            not count and connection.page_info.has_next_page
        ):
            raise ValueError("GitHub returned an invalid Query Page length")
        if not connection.page_info.has_next_page and end < min(
            connection.issue_count, 1000
        ):
            raise ValueError("GitHub returned an incomplete Query Page")
        trail = tuple(token.trail) if token else ()
        next_cursor: str | None = None
        continuation = "end"
        if end >= 1000 and (
            connection.issue_count > end or connection.page_info.has_next_page
        ):
            continuation = "provider-limit"
        elif connection.page_info.has_next_page:
            cursor = connection.page_info.end_cursor
            if not cursor or cursor_digest(cursor) in trail:
                raise ValueError(
                    "GitHub repeated or omitted its forward cursor; restart from page one"
                )
            next_cursor = encode_continuation(
                Continuation(
                    fingerprint=context_fingerprint(context, request),
                    offset=end,
                    provider_cursor=cursor,
                    trail=(*trail, cursor_digest(cursor)),
                )
            )
            continuation = "more"
        return QueryPage(
            context=context,
            request=request,
            effective_ordering=ordering,
            status="fresh",
            attempted_at=attempted,
            last_good_at=attempted,
            issues=issues,
            pull_requests=prs,
            auxiliary=auxiliary,
            returned_count=count,
            matched_count=connection.issue_count,
            next_cursor=next_cursor,
            continuation=continuation,
            result_limit=1000,
        )

    @override
    def fetch_totals(self, kind: ResourceKind) -> tuple[int, int]:
        """Observe lifecycle totals without fetching their constituent records."""
        field = "issues" if kind == "issues" else "pullRequests"
        closed = "CLOSED" if kind == "issues" else "CLOSED, MERGED"
        query = f"""query DashpotProjectTotals($repositoryId: ID!) {{
          node(id: $repositoryId) {{ ... on Repository {{ id
            opened: {field}(states: [OPEN]) {{ totalCount }}
            closed: {field}(states: [{closed}]) {{ totalCount }}
          }} }}
        }}"""
        self._meter.next_request("Project lifecycle totals")
        raw = self.gateway.graphql(query, {"repositoryId": self.context.repository_id})[
            "node"
        ]
        if raw["id"] != self.context.repository_id:
            raise ValueError("GitHub totals answered a different Repository")
        opened, closed_count = raw["opened"]["totalCount"], raw["closed"]["totalCount"]
        if (
            type(opened) is not int
            or type(closed_count) is not int
            or min(opened, closed_count) < 0
        ):
            raise ValueError("GitHub lifecycle totals are malformed")
        return opened, closed_count

    @override
    def fetch_identities(
        self, context: SourceContext, identities: Sequence[str], attempted: str
    ) -> tuple[ResolvedIssue, ...]:
        """Resolve only the requested identities under a bounded request budget."""
        return self._resolve(context, identities, attempted, self._meter)

    def _resolve(
        self,
        context: SourceContext,
        identities: Sequence[str],
        attempted: str,
        meter: RefreshMeter,
    ) -> tuple[ResolvedIssue, ...]:
        results: list[ResolvedIssue] = []
        completed: dict[str, Mapping[str, Any]] = {}
        for start in range(0, len(identities), 24):
            batch = identities[start : start + 24]
            try:
                meter.next_request(f"{start} resolved Issues")
                data, errors = self.gateway.graphql_result(
                    _IDENTITIES, {"ids": list(batch)}
                )
                attributed: dict[int, list[Mapping[str, Any]]] = {}
                for error in errors:
                    path = error.get("path")
                    if (
                        not isinstance(path, list)
                        or len(path) < 2
                        or path[0] != "nodes"
                        or type(path[1]) is not int
                        or not 0 <= path[1] < len(batch)
                    ):
                        raise ValueError(
                            "GitHub identity failure cannot be attributed to a requested identity"
                        )
                    attributed.setdefault(path[1], []).append(error)
                nodes = data.get("nodes")
                if not isinstance(nodes, list) or len(nodes) != len(batch):
                    raise ValueError(
                        "GitHub must answer one position per requested identity"
                    )
            except QUERY_OBSERVATION_FAILURES as exc:
                results.extend(
                    ResolvedIssue(
                        context=context,
                        issue_id=identity,
                        outcome="unavailable",
                        status="unavailable",
                        attempted_at=attempted,
                        last_good_at=None,
                        diagnostics=(self.diagnostic(exc),),
                    )
                    for identity in batch
                )
                continue
            for index, (identity, raw) in enumerate(zip(batch, nodes, strict=True)):
                try:
                    auxiliary_failed = False
                    for error in attributed.get(index, []):
                        path = error["path"]
                        if (
                            len(path) == 2
                            and error.get("type") == "NOT_FOUND"
                            and raw is None
                        ):
                            continue
                        if len(path) > 2 and (
                            path[2] in {"comments", "closedByPullRequestsReferences"}
                            or (path[2] == "labels" and path[-1] == "color")
                        ):
                            auxiliary_failed = True
                            continue
                        raise ValueError(
                            str(error.get("message", "Issue observation failed"))
                        )
                    result = self._resolve_record(
                        context, identity, raw, attempted, meter, completed
                    )
                    if auxiliary_failed and identity in completed:
                        completed[identity] = {
                            **completed[identity],
                            "auxiliaryError": "GitHub could not observe auxiliary Issue facts",
                        }
                except QUERY_OBSERVATION_FAILURES as exc:
                    result = ResolvedIssue(
                        context=context,
                        issue_id=identity,
                        outcome="unavailable",
                        status="unavailable",
                        attempted_at=attempted,
                        last_good_at=None,
                        diagnostics=(self.diagnostic(exc),),
                    )
                results.append(result)
        auxiliary_meter = self.budget.start()
        return tuple(
            result.model_copy(
                update={
                    "auxiliary": self._auxiliary(
                        completed[result.issue_id], attempted, auxiliary_meter
                    )
                }
            )
            if result.issue_id in completed
            else result
            for result in results
        )

    def _resolve_record(
        self,
        context: SourceContext,
        identity: str,
        raw: object,
        attempted: str,
        meter: RefreshMeter,
        completed: dict[str, Mapping[str, Any]],
    ) -> ResolvedIssue:
        if raw is None:
            return ResolvedIssue(
                context=context,
                issue_id=identity,
                status="fresh",
                attempted_at=attempted,
                last_good_at=attempted,
                outcome="not-resolved",
                diagnostics=(
                    Diagnostic(
                        source="github",
                        severity="warning",
                        code="issue-not-resolved",
                        message=f"Issue {identity} is missing or inaccessible",
                    ),
                ),
            )
        if (
            not isinstance(raw, dict)
            or raw.get("id") != identity
            or raw.get("__typename") != "Issue"
        ):
            raise ValueError(
                "GitHub identity response is malformed or answered another resource"
            )
        repository = Repository.model_validate(raw.get("repository"))
        if repository.id != context.repository_id:
            return ResolvedIssue(
                context=context,
                issue_id=identity,
                status="fresh",
                attempted_at=attempted,
                last_good_at=attempted,
                outcome="outside-repository",
                diagnostics=(
                    Diagnostic(
                        source="github",
                        severity="warning",
                        code="issue-outside-repository",
                        message=f"Issue {identity} is now outside the configured Repository",
                    ),
                ),
                observed_repository_id=repository.id,
                reference=f"{repository.name_with_owner}#{raw['number']}",
            )
        complete = self.profiles.complete_nested_connections(raw, meter)
        issue = normalize_github_issue(
            complete, project_id=context.project_id, repository_id=context.repository_id
        )
        completed[identity] = complete
        return ResolvedIssue(
            context=context,
            issue_id=identity,
            status="fresh",
            attempted_at=attempted,
            last_good_at=attempted,
            outcome="resolved",
            issue=issue,
            reference=issue.reference,
        )

    def _auxiliary(
        self, raw: Mapping[str, Any], attempted: str, meter: RefreshMeter
    ) -> AuxiliaryObservation:
        try:
            if "auxiliaryError" in raw:
                raise ValueError(str(raw["auxiliaryError"]))
            # Number ordering is not available on this connection. Complete it
            # deliberately to retain the declared lowest-numbered display subset.
            complete = self.profiles.complete_linked_pull_requests(raw, meter)
            comments = complete.get("comments")
            linked = complete.get("closedByPullRequestsReferences")
            if (
                not isinstance(comments, dict)
                or type(comments.get("totalCount")) is not int
                or comments["totalCount"] < 0
            ):
                raise ValueError("Comment count is unavailable")
            if (
                not isinstance(linked, dict)
                or type(linked.get("totalCount")) is not int
                or not isinstance(linked.get("nodes"), list)
            ):
                raise ValueError("Linked Pull Request observation is unavailable")
            if len(linked["nodes"]) != linked["totalCount"]:
                raise ValueError(
                    "Linked Pull Request display completion is unavailable"
                )
            activity = issue_activity(complete)
            if len(activity.linked_pull_requests) != min(linked["totalCount"], 20):
                raise ValueError("Linked Pull Request observation is malformed")
            colors = label_colors(complete)
            labels = complete["labels"]["nodes"]
            if len(colors) != len(labels):
                raise ValueError("Label colour observation is unavailable")
            return AuxiliaryObservation(
                status="fresh",
                attempted_at=attempted,
                last_good_at=attempted,
                activity=activity,
                label_colors=colors,
            )
        except QUERY_OBSERVATION_FAILURES as exc:
            return AuxiliaryObservation(
                status="unavailable",
                attempted_at=attempted,
                last_good_at=None,
                diagnostics=(self.diagnostic(exc),),
            )

    @override
    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration:
        """Enumerate complete repository connections with legacy export semantics."""
        if kind == "issues":
            observation = self.profiles.refresh()
            return SourceEnumeration(
                context=self.context,
                kind=kind,
                issues=observation.issues,
                auxiliary={
                    issue.id: AuxiliaryObservation(
                        status=observation.status,
                        attempted_at=observation.attempted_at,
                        last_good_at=observation.last_good_at,
                        activity=observation.issue_activity.get(issue.id),
                        label_colors=observation.label_colors,
                    )
                    for issue in observation.issues
                },
                status=observation.status,
                attempted_at=observation.attempted_at,
                last_good_at=observation.last_good_at,
                diagnostics=tuple(observation.diagnostics),
            )
        pulls = self.pull_requests.refresh()
        return SourceEnumeration(
            context=self.context,
            kind=kind,
            pull_requests=pulls.pull_requests,
            status=pulls.status,
            attempted_at=pulls.attempted_at,
            last_good_at=pulls.last_good_at,
            diagnostics=tuple(pulls.diagnostics),
        )
