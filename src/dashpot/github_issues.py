from __future__ import annotations

import contextlib
import copy
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from typing_extensions import override

from .commands import CommandRunner, run_command
from .github import (
    DEFAULT_REFRESH_BUDGET,
    MAX_IN_FLIGHT,
    NOT_FOUND,
    RATE_LIMIT_SELECTION,
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    GraphQLVariables,
    RefreshBudget,
    RefreshMeter,
)
from .github_issue_snapshot import (
    GITHUB_ISSUE_SNAPSHOT_VERSION,
    GitHubIssueActivityRecord,
    GitHubIssueSnapshotRecord,
    GitHubIssueSnapshotStore,
    GitHubObservedIssueRecord,
    GitHubPullRequestMarksRecord,
)
from .issue_profile import (
    IssueProfile,
    IssueProfileError,
    IssueRelationships,
    conform_issue,
)
from .issue_sources import (
    Clock,
    CollectedIssues,
    IssueHint,
    IssueSource,
    IssueSourceDiagnostic,
    IssueSourceRefreshError,
)
from .model import IssueActivity, LinkedPullRequest, PullRequestState
from .project_config import DEFAULT_RECONCILIATION_SECONDS

_STATE_REASONS = {
    "COMPLETED": "completed",
    "DUPLICATE": "duplicate",
    "NOT_PLANNED": "not-planned",
    "REOPENED": "reopened",
}

_PAGE_SIZE = 100
# The widest batch of complete Issue nodes GitHub charges one rate-limit point
# for, and well under the width at which nested connections were seen to
# truncate silently (docs/github-api-batching-research.md).
_BATCH_SIZE = 24
_PULL_REQUEST_PAGE_SIZE = 24
# How long a snapshot is refreshed incrementally before every Issue is
# observed afresh to close what a delta cannot see (ADR 0022).
DEFAULT_RECONCILE_SECONDS = DEFAULT_RECONCILIATION_SECONDS
_RECONCILIATION_OVERDUE = "github-reconciliation-overdue"
_ISSUE_COUNT = "github-issue-count"
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
            totalCount
            nodes { number url state }
            pageInfo { hasNextPage endCursor }
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
      pullRequests(
        first: 1
        states: [OPEN, CLOSED, MERGED]
        orderBy: {{field: UPDATED_AT, direction: DESC}}
      ) {{
        nodes {{ updatedAt }}
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

# The Issues updated at or after the snapshot's High-Water Mark, oldest
# change first so the mark advances monotonically through the pages. The
# boundary is inclusive, so the Issue at the mark is observed again: that
# overlap is what makes the boundary safe without any clock arithmetic.
_ISSUES_SINCE_QUERY = f"""
query DashpotIssuesSince($repositoryId: ID!, $since: DateTime!, $cursor: String) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      nameWithOwner
      issues(
        first: {_BATCH_SIZE}
        after: $cursor
        states: [OPEN, CLOSED]
        filterBy: {{since: $since}}
        orderBy: {{field: UPDATED_AT, direction: ASC}}
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

# The change probe: the newest update and the Issue count, one point.
_ISSUE_PROBE_QUERY = f"""
query DashpotIssueProbe($repositoryId: ID!) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      nameWithOwner
      issues(
        first: 1
        states: [OPEN, CLOSED]
        orderBy: {{field: UPDATED_AT, direction: DESC}}
      ) {{
        totalCount
        nodes {{ updatedAt }}
      }}
      pullRequests(
        first: 1
        states: [OPEN, CLOSED, MERGED]
        orderBy: {{field: UPDATED_AT, direction: DESC}}
      ) {{
        nodes {{ updatedAt }}
      }}
    }}
  }}
}}
""".strip()

_PULL_REQUEST_CHANGES_QUERY = f"""
query DashpotPullRequestChanges($repositoryId: ID!, $cursor: String) {{
  {RATE_LIMIT_SELECTION}
  node(id: $repositoryId) {{
    ... on Repository {{
      id
      nameWithOwner
      pullRequests(
        first: {_PULL_REQUEST_PAGE_SIZE}
        after: $cursor
        states: [OPEN, CLOSED, MERGED]
        orderBy: {{field: UPDATED_AT, direction: DESC}}
      ) {{
        nodes {{
          id
          number
          updatedAt
          closingIssuesReferences(first: 100) {{
            nodes {{ id }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}
""".strip()

_PULL_REQUEST_CLOSING_ISSUES_QUERY = f"""
query DashpotPullRequestClosingIssues($id: ID!, $cursor: String!) {{
  {RATE_LIMIT_SELECTION}
  node(id: $id) {{
    ... on PullRequest {{
      closingIssuesReferences(first: 100, after: $cursor) {{
        nodes {{ id }}
        pageInfo {{ hasNextPage endCursor }}
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

# Issues by identity: each answers independently, a missing one as null.
_ISSUES_BY_ID_QUERY = f"""
query DashpotIssuesById($ids: [ID!]!) {{
  {RATE_LIMIT_SELECTION}
  nodes(ids: $ids) {{
    __typename
    ... on Issue {{
{_ISSUE_NODE_FIELDS}
    }}
  }}
}}
""".strip()


# The two ways a collection cycle goes wrong, told apart by diagnostic code:
# GitHub answered well-formed data but an Issue does not conform to the Issue
# profile, versus a response whose shape is not the GraphQL contract at all.
_PROFILE_CODE = "github-profile"
_RESPONSE_CODE = "github-malformed-response"


@dataclass(frozen=True, slots=True)
class _ObservedIssue:
    """One Issue as last observed, with what is presented beside it."""

    issue: IssueProfile
    updated_at: str
    activity: IssueActivity
    linked_pull_request_numbers: frozenset[int]
    label_colors: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _PullRequestMarks:
    """Keep the settled Pull Request mark and its candidate together."""

    settled: str | None
    candidate: str | None = None


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Retain the complete Issue collection and its observation marks."""

    issues: Mapping[str, _ObservedIssue]
    high_water: str | None
    pull_request_marks: _PullRequestMarks
    reconciled_at: float
    reported_count: int | None = None
    sweep_due: bool = False


@dataclass(frozen=True, slots=True)
class _Probe:
    """Report the Issue count and newest Issue and Pull Request changes."""

    total_count: int
    newest_updated_at: str | None
    pull_request_newest_updated_at: str | None


@dataclass(frozen=True, slots=True)
class _Delta:
    """Carry the Issues observed since a High-Water Mark."""

    issues: Mapping[str, _ObservedIssue]
    high_water: str


@dataclass(frozen=True, slots=True)
class _IssuePages:
    """Carry Issue pages and the newest Pull Request observed beside them."""

    records: tuple[dict[str, Any], ...]
    pull_request_newest_updated_at: str | None


@dataclass(frozen=True, slots=True)
class _PullRequestChange:
    """Identify one changed Pull Request and its current closing targets."""

    id: str
    number: int
    updated_at: str
    closing_issue_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _PullRequestDelta:
    """Carry the Pull Requests observed through an inclusive boundary."""

    pull_requests: tuple[_PullRequestChange, ...]
    high_water: str | None


class GitHubIssuesSource(IssueSource):
    """Observe GitHub Issues incrementally from complete profile snapshots."""

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
        reconcile_seconds: float = DEFAULT_RECONCILE_SECONDS,
        monotonic: Callable[[], float] | None = None,
        snapshot_store: GitHubIssueSnapshotStore | None = None,
    ) -> None:
        super().__init__(clock=clock)
        self.root = root
        self.project_id = project_id
        self.repository_id = repository_id
        self.timeout = timeout
        self.runner = runner
        self.budget = budget
        self.reconcile_seconds = reconcile_seconds
        self.gateway = GitHubGateway(root, timeout=timeout, runner=runner)
        self._monotonic = monotonic or time.monotonic
        self._snapshot_store = snapshot_store
        self._snapshot: _Snapshot | None = None
        self._snapshot_seed = self._load_snapshot_seed()
        self._reconcile_attempted_at: float | None = None

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
        now = meter.started
        snapshot = self._snapshot
        previous_snapshot = snapshot
        seed = self._snapshot_seed
        if snapshot is None and seed is not None:
            probe = self._probe(meter)
            snapshot = self._reconcile(seed, meter, now, probe=probe)
            snapshot = self._refresh_linked_pull_requests(snapshot, probe, meter)
        elif snapshot is not None and snapshot.sweep_due:
            # Clearing before the attempt prevents a sweep that exhausts its
            # own budget from being retried on every polling tick.
            snapshot = replace(snapshot, sweep_due=False)
            self._snapshot = snapshot
            self._reconcile_attempted_at = now
            snapshot = self._sweep(meter, now)
        elif snapshot is None or snapshot.high_water is None:
            snapshot = self._reconcile(snapshot, meter, now)
        else:
            probe = self._probe(meter)
            if self.reconcile_requested or self._reconciliation_due(now):
                snapshot = self._reconcile(snapshot, meter, now, probe=probe)
            else:
                snapshot = self._refresh_incrementally(snapshot, meter, now, probe)
            snapshot = self._refresh_linked_pull_requests(snapshot, probe, meter)
        collected = self._collected(snapshot, now)
        # The merge is the one place two listings meet, so the snapshot is
        # kept only once the collection it makes has passed the invariants.
        self._check_collection_invariants(collected)
        self._snapshot = snapshot
        self._snapshot_seed = None
        if snapshot is not previous_snapshot:
            self._persist_snapshot(snapshot)
        return collected

    def _start_meter(self) -> RefreshMeter:
        return self.budget.start(self._monotonic)

    def _load_snapshot_seed(self) -> _Snapshot | None:
        """Load a valid persisted seed without making it observed state."""

        store = self._snapshot_store
        if store is None:
            return None
        record = store.load(
            repository_id=self.repository_id, project_id=self.project_id
        )
        if record is None:
            return None
        return _Snapshot(
            issues={
                entry.issue.id: _ObservedIssue(
                    issue=entry.issue,
                    updated_at=entry.updated_at,
                    activity=entry.activity.issue_activity(),
                    linked_pull_request_numbers=frozenset(
                        entry.linked_pull_request_numbers
                    ),
                    label_colors=entry.label_colors,
                )
                for entry in record.issues
            },
            high_water=record.high_water,
            pull_request_marks=_PullRequestMarks(
                settled=record.pull_request_marks.settled,
                candidate=record.pull_request_marks.candidate,
            ),
            # The seed is never published with this placeholder. Its mandatory
            # live Reconciliation replaces it with this process's monotonic time.
            reconciled_at=0.0,
        )

    def _persist_snapshot(self, snapshot: _Snapshot) -> None:
        """Persist a useful complete snapshot without affecting observation."""

        store = self._snapshot_store
        if store is None or snapshot.high_water is None:
            return
        # Persistence is only a restart optimization. A local persistence
        # failure cannot turn a complete live GitHub observation into a failed
        # one, including if this model is ever stricter than valid source state.
        with contextlib.suppress(OSError, ValidationError):
            record = GitHubIssueSnapshotRecord(
                version=GITHUB_ISSUE_SNAPSHOT_VERSION,
                project_id=self.project_id,
                repository_id=self.repository_id,
                issues=[
                    GitHubObservedIssueRecord(
                        issue=entry.issue,
                        updated_at=entry.updated_at,
                        activity=GitHubIssueActivityRecord.of(entry.activity),
                        linked_pull_request_numbers=sorted(
                            entry.linked_pull_request_numbers
                        ),
                        label_colors=dict(entry.label_colors),
                    )
                    for entry in sorted(
                        snapshot.issues.values(), key=lambda item: item.issue.number
                    )
                ],
                high_water=snapshot.high_water,
                pull_request_marks=GitHubPullRequestMarksRecord(
                    settled=snapshot.pull_request_marks.settled,
                    candidate=snapshot.pull_request_marks.candidate,
                ),
            )
            store.replace(record)

    def _reconciliation_due(self, now: float) -> bool:
        attempted_at = self._reconcile_attempted_at
        return attempted_at is None or now - attempted_at >= self.reconcile_seconds

    def _reconciliation_failed_this_period(
        self, snapshot: _Snapshot, now: float
    ) -> bool:
        attempted_at = self._reconcile_attempted_at
        return (
            attempted_at is not None
            and attempted_at > snapshot.reconciled_at
            and now - attempted_at < self.reconcile_seconds
        )

    def _reconcile(
        self,
        snapshot: _Snapshot | None,
        meter: RefreshMeter,
        now: float,
        probe: _Probe | None = None,
        delta: _Delta | None = None,
    ) -> _Snapshot:
        """Observe every Issue afresh."""
        # Attempted rather than completed: a Reconciliation the budget
        # abandons is retried after a period, while the ticks in between
        # keep refreshing incrementally instead of failing the same way.
        self._reconcile_attempted_at = now
        if snapshot is None or snapshot.high_water is None:
            return self._sweep(meter, now)
        if probe is None:
            probe = self._probe(meter)
        observed: dict[str, _ObservedIssue] = {}
        for issue_id, record in self._fetch_by_identity(
            sorted(snapshot.issues), meter, "Issues of the collection"
        ).items():
            entry = self._own_issue(record, meter)
            if entry is not None:
                observed[issue_id] = entry
        high_water = snapshot.high_water
        for entry in observed.values():
            high_water = _later(high_water, entry.updated_at)
        previous = dict(observed)
        if delta is None:
            delta = self._changes_since(snapshot.high_water, high_water, meter)
            # This delta was observed after the identities, so it wins a tie.
            observed.update(delta.issues)
            applied = delta.issues
        else:
            # This delta preceded the identities, so only a newer value wins.
            reused: dict[str, _ObservedIssue] = {}
            for issue_id, entry in delta.issues.items():
                identity_entry = observed.get(issue_id)
                if identity_entry is None or _is_later(
                    entry.updated_at, identity_entry.updated_at
                ):
                    observed[issue_id] = entry
                    reused[issue_id] = entry
            applied = reused
        high_water = _later(high_water, delta.high_water)
        self._observe_counterparts(observed, applied, previous, meter)
        if len(observed) != probe.total_count:
            # An Issue created or deleted while the identities were in flight
            # moved the count after the probe: one more probe says whether
            # the collection now agrees with GitHub.
            probe = self._probe(meter)
        if len(observed) != probe.total_count:
            # An Issue transferred in carries its old updatedAt and no known
            # identity: only a sweep under a fresh Refresh Budget lists it.
            return _Snapshot(
                issues=observed,
                high_water=high_water,
                pull_request_marks=snapshot.pull_request_marks,
                reconciled_at=now,
                reported_count=probe.total_count,
                sweep_due=True,
            )
        return _Snapshot(
            issues=observed,
            high_water=high_water,
            pull_request_marks=snapshot.pull_request_marks,
            reconciled_at=now,
        )

    def _sweep(self, meter: RefreshMeter, now: float) -> _Snapshot:
        """Observe the whole collection page by page, the ground truth."""
        pages = self._collect_issue_pages(
            _ISSUES_QUERY, {}, meter, "Issue collection", observe_pull_request=True
        )
        entries = self._observe_records(pages.records, meter)
        high_water: str | None = None
        for entry in entries:
            high_water = _later(high_water, entry.updated_at)
        return _Snapshot(
            issues={entry.issue.id: entry for entry in entries},
            high_water=high_water,
            pull_request_marks=_PullRequestMarks(
                settled=pages.pull_request_newest_updated_at
            ),
            reconciled_at=now,
        )

    def _refresh_incrementally(
        self, snapshot: _Snapshot, meter: RefreshMeter, now: float, probe: _Probe
    ) -> _Snapshot:
        """Bring the snapshot up to date with what changed since its mark."""
        if snapshot.high_water is None:
            # An empty collection has no mark to observe since.
            return self._reconcile(snapshot, meter, now, probe=probe)
        if (
            probe.newest_updated_at is not None
            and not _is_later(probe.newest_updated_at, snapshot.high_water)
            and probe.total_count == len(snapshot.issues)
        ):
            return snapshot
        delta = self._changes_since(snapshot.high_water, snapshot.high_water, meter)
        observed = dict(snapshot.issues)
        observed.update(delta.issues)
        self._observe_counterparts(observed, delta.issues, snapshot.issues, meter)
        reported_count: int | None = None
        if len(observed) != probe.total_count:
            # Something left without a trace a delta can see — a deletion, a
            # transfer — and only observing everything afresh can say what.
            # But a Reconciliation the budget already abandoned this period
            # would fail the same way on every tick, so the disagreement is
            # reported beside what is known until the next attempt is due.
            if not self._reconciliation_failed_this_period(snapshot, now):
                return self._reconcile(snapshot, meter, now, probe=probe, delta=delta)
            reported_count = probe.total_count
        return _Snapshot(
            issues=observed,
            high_water=delta.high_water,
            pull_request_marks=snapshot.pull_request_marks,
            reconciled_at=snapshot.reconciled_at,
            reported_count=reported_count,
        )

    def _changes_since(
        self, since: str, high_water: str, meter: RefreshMeter
    ) -> _Delta:
        """List the Issues updated at or after ``since`` and advance the mark."""
        changed: dict[str, _ObservedIssue] = {}
        for record in self._collect_issue_pages(
            _ISSUES_SINCE_QUERY, {"since": since}, meter, "Issue delta"
        ).records:
            entry = self._observe_record(record, meter)
            # An Issue updated again while the delta paged moves past the
            # cursor and is listed once more; the later observation wins.
            previous = changed.get(entry.issue.id)
            if previous is None or not _is_later(previous.updated_at, entry.updated_at):
                changed[entry.issue.id] = entry
            high_water = _later(high_water, entry.updated_at)
        return _Delta(issues=changed, high_water=high_water)

    def _refresh_linked_pull_requests(
        self, snapshot: _Snapshot, probe: _Probe, meter: RefreshMeter
    ) -> _Snapshot:
        """Re-observe Issues named since the Pull Request High-Water Mark."""
        newest = probe.pull_request_newest_updated_at
        marks = snapshot.pull_request_marks
        mark = marks.settled
        if newest is None or (mark is not None and not _is_later(newest, mark)):
            return snapshot
        delta = self._pull_request_changes_since(mark, meter)
        changed_numbers = {pull_request.number for pull_request in delta.pull_requests}
        affected = {
            issue_id
            for issue_id, entry in snapshot.issues.items()
            if changed_numbers & entry.linked_pull_request_numbers
        }
        for pull_request in delta.pull_requests:
            affected.update(pull_request.closing_issue_ids)
        observed = dict(snapshot.issues)
        changed: dict[str, _ObservedIssue] = {}
        for issue_id, record in self._fetch_by_identity(
            sorted(affected), meter, "Issues named by changed Pull Requests"
        ).items():
            entry = self._own_issue(record, meter)
            if entry is None:
                observed.pop(issue_id, None)
            else:
                observed[issue_id] = entry
                changed[issue_id] = entry
        self._observe_counterparts(observed, changed, snapshot.issues, meter)
        settled = delta.high_water is not None and delta.high_water == marks.candidate
        return _Snapshot(
            issues=observed,
            high_water=snapshot.high_water,
            pull_request_marks=_PullRequestMarks(
                settled=delta.high_water if settled else marks.settled,
                candidate=None if settled else delta.high_water,
            ),
            reconciled_at=snapshot.reconciled_at,
            reported_count=snapshot.reported_count,
            sweep_due=snapshot.sweep_due,
        )

    def _pull_request_changes_since(
        self, since: str | None, meter: RefreshMeter
    ) -> _PullRequestDelta:
        """Scan through the inclusive Pull Request High-Water Mark."""
        changed: dict[str, _PullRequestChange] = {}
        high_water = since
        cursor: str | None = None
        trail = CursorTrail("Pull Request changes")
        while True:
            variables: dict[str, str | int | Sequence[str]] = {
                "repositoryId": self.repository_id
            }
            if cursor is not None:
                variables["cursor"] = cursor
            meter.next_request(f"{len(changed)} changed Pull Requests")
            data = self._repository_query(_PULL_REQUEST_CHANGES_QUERY, variables)
            repository = self._own_repository(data)
            connection = _object(
                repository, "pullRequests", "data.repository", _RESPONSE_CODE
            )
            nodes, has_next, end_cursor = _connection_page(
                connection, "data.repository.pullRequests", _RESPONSE_CODE
            )
            crossed_boundary = False
            for record in nodes:
                pull_request = self._pull_request_change(record, meter)
                if since is not None and _is_later(since, pull_request.updated_at):
                    crossed_boundary = True
                    continue
                previous = changed.get(pull_request.id)
                if previous is None or not _is_later(
                    previous.updated_at, pull_request.updated_at
                ):
                    changed[pull_request.id] = pull_request
                high_water = _later(high_water, pull_request.updated_at)
            if crossed_boundary or not has_next:
                return _PullRequestDelta(
                    pull_requests=tuple(changed.values()), high_water=high_water
                )
            cursor = trail.follow(end_cursor)

    def _pull_request_change(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> _PullRequestChange:
        """Validate one Pull Request change and complete its closing targets."""
        pull_request_id = _fetched_string(record, "id", "pull request", _RESPONSE_CODE)
        number = _fetched(record, "number", "pull request", _RESPONSE_CODE)
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise IssueSourceRefreshError(
                _RESPONSE_CODE, "pull request.number must be a positive Int"
            )
        updated_at = _fetched_string(
            record, "updatedAt", "pull request", _RESPONSE_CODE
        )
        connection = _object(
            record, "closingIssuesReferences", "pull request", _RESPONSE_CODE
        )
        nodes, has_next, end_cursor = _connection_page(
            connection, "pull request.closingIssuesReferences", _RESPONSE_CODE
        )
        closing_issue_ids = {
            _fetched_string(
                node,
                "id",
                "pull request.closingIssuesReferences.nodes[]",
                _RESPONSE_CODE,
            )
            for node in nodes
        }
        trail = CursorTrail(f"Pull Request {pull_request_id} closing Issues")
        while has_next:
            cursor = trail.follow(end_cursor)
            meter.next_request(
                f"{len(closing_issue_ids)} closing Issues of Pull Request #{number}"
            )
            data = self.gateway.graphql(
                _PULL_REQUEST_CLOSING_ISSUES_QUERY,
                {"id": pull_request_id, "cursor": cursor},
            )
            node = _object(data, "node", "data", _RESPONSE_CODE)
            connection = _object(
                node, "closingIssuesReferences", "data.node", _RESPONSE_CODE
            )
            nodes, has_next, end_cursor = _connection_page(
                connection, "data.node.closingIssuesReferences", _RESPONSE_CODE
            )
            closing_issue_ids.update(
                _fetched_string(
                    item,
                    "id",
                    "data.node.closingIssuesReferences.nodes[]",
                    _RESPONSE_CODE,
                )
                for item in nodes
            )
        return _PullRequestChange(
            id=pull_request_id,
            number=number,
            updated_at=updated_at,
            closing_issue_ids=frozenset(closing_issue_ids),
        )

    def _observe_counterparts(
        self,
        observed: dict[str, _ObservedIssue],
        changed: Mapping[str, _ObservedIssue],
        previous: Mapping[str, _ObservedIssue],
        meter: RefreshMeter,
    ) -> None:
        """Observe the other end of every relationship ``changed`` added or removed.

        A relationship is observed at both its ends and a change may bump
        only one of them, so the other ends are observed by identity too.
        """
        counterparts = _relationship_counterparts(changed, previous)
        for issue_id, record in self._fetch_by_identity(
            counterparts, meter, "related Issues"
        ).items():
            entry = self._own_issue(record, meter)
            if entry is None:
                observed.pop(issue_id, None)
            else:
                observed[issue_id] = entry

    def _collected(self, snapshot: _Snapshot, now: float) -> CollectedIssues:
        entries = sorted(snapshot.issues.values(), key=lambda entry: entry.issue.number)
        label_colors: dict[str, str] = {}
        # The most recently updated Issue carries the latest colour of a label.
        for entry in sorted(entries, key=lambda entry: _timestamp(entry.updated_at)):
            label_colors.update(entry.label_colors)
        return CollectedIssues(
            issues=tuple(entry.issue for entry in entries),
            label_colors=label_colors,
            issue_activity={entry.issue.id: entry.activity for entry in entries},
            diagnostics=(
                *self._rate_limit_diagnostics(),
                *self._reconciliation_diagnostics(snapshot, now),
            ),
        )

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

    def _reconciliation_diagnostics(
        self, snapshot: _Snapshot, now: float
    ) -> tuple[IssueSourceDiagnostic, ...]:
        """Warn while a Reconciliation is overdue or the Issue count disagrees."""
        diagnostics: list[IssueSourceDiagnostic] = []
        if snapshot.reported_count is not None:
            diagnostics.append(
                IssueSourceDiagnostic(
                    source=self.name,
                    code=_ISSUE_COUNT,
                    severity="warning",
                    message=(
                        f"GitHub reports {snapshot.reported_count} Issues but "
                        f"{len(snapshot.issues)} are known; a deleted or "
                        "transferred Issue may be shown until the fallback "
                        "sweep succeeds"
                    ),
                )
            )
        age = now - snapshot.reconciled_at
        period = self.reconcile_seconds
        if age > 2 * period:
            diagnostics.append(
                IssueSourceDiagnostic(
                    source=self.name,
                    code=_RECONCILIATION_OVERDUE,
                    severity="warning",
                    message=(
                        f"GitHub Issues were last observed in full {age:.0f}s ago "
                        f"against a Reconciliation period of {period:g}s; a "
                        "Linked Pull Request whose derived targets remain "
                        "unindexed, a blocker's dependency, a parent/sub-Issue "
                        "relationship or a deleted or transferred Issue may be "
                        "out of date until one succeeds"
                    ),
                )
            )
        return tuple(diagnostics)

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
        record = _fetched(repository, "issue", "data.repository", _RESPONSE_CODE)
        if record is None:
            return None
        if not isinstance(record, dict):
            raise IssueSourceRefreshError(
                _RESPONSE_CODE, "data.repository.issue must be an object or null"
            )
        issue = self._observe_record(record, meter).issue
        if reference is not None and issue.reference != reference:
            return None
        return issue

    def _probe(self, meter: RefreshMeter) -> _Probe:
        meter.next_request("the change probe")
        data = self._repository_query(
            _ISSUE_PROBE_QUERY, {"repositoryId": self.repository_id}
        )
        repository = self._own_repository(data)
        issues = _object(repository, "issues", "data.repository", _RESPONSE_CODE)
        total_count = _fetched(
            issues, "totalCount", "data.repository.issues", _RESPONSE_CODE
        )
        if not isinstance(total_count, int) or isinstance(total_count, bool):
            raise IssueSourceRefreshError(
                _RESPONSE_CODE, "data.repository.issues.totalCount must be an Int"
            )
        newest_updated_at = _connection_newest_updated_at(
            issues, "data.repository.issues"
        )
        pull_requests = _object(
            repository, "pullRequests", "data.repository", _RESPONSE_CODE
        )
        return _Probe(
            total_count=total_count,
            newest_updated_at=newest_updated_at,
            pull_request_newest_updated_at=_connection_newest_updated_at(
                pull_requests, "data.repository.pullRequests"
            ),
        )

    def _collect_issue_pages(
        self,
        query: str,
        variables: GraphQLVariables,
        meter: RefreshMeter,
        subject: str,
        *,
        observe_pull_request: bool = False,
    ) -> _IssuePages:
        nodes: list[dict[str, Any]] = []
        pull_request_newest_updated_at: str | None = None
        cursor: str | None = None
        trail = CursorTrail(subject)
        while True:
            page_variables: dict[str, str | int | Sequence[str]] = {
                "repositoryId": self.repository_id,
                **variables,
            }
            if cursor is not None:
                page_variables["cursor"] = cursor
            meter.next_request(f"{len(nodes)} Issues")
            data = self._repository_query(query, page_variables)
            repository = self._own_repository(data)
            if observe_pull_request:
                pull_requests = _object(
                    repository, "pullRequests", "data.repository", _RESPONSE_CODE
                )
                newest = _connection_newest_updated_at(
                    pull_requests, "data.repository.pullRequests"
                )
                if newest is not None:
                    pull_request_newest_updated_at = _later(
                        pull_request_newest_updated_at, newest
                    )
            issues = _object(repository, "issues", "data.repository", _RESPONSE_CODE)
            page_nodes, has_next, end_cursor = _connection_page(
                issues, "data.repository.issues", _RESPONSE_CODE
            )
            nodes.extend(page_nodes)
            if not has_next:
                return _IssuePages(
                    records=tuple(nodes),
                    pull_request_newest_updated_at=pull_request_newest_updated_at,
                )
            cursor = trail.follow(end_cursor)

    def _fetch_by_identity(
        self, ids: Sequence[str], meter: RefreshMeter, subject: str
    ) -> dict[str, dict[str, Any] | None]:
        """Observe Issues by identity, a missing one answered as ``None``.

        Identities go in batches of the size GitHub charges one point for,
        and the batches in waves of MAX_IN_FLIGHT, each wave spent against
        the budget before it is sent.
        """
        batches = [
            list(ids[start : start + _BATCH_SIZE])
            for start in range(0, len(ids), _BATCH_SIZE)
        ]
        records: dict[str, dict[str, Any] | None] = {}
        for wave_start in range(0, len(batches), MAX_IN_FLIGHT):
            wave = batches[wave_start : wave_start + MAX_IN_FLIGHT]
            for _ in wave:
                meter.next_request(f"{len(records)} of {len(ids)} {subject}")
            answers = self.gateway.graphql_many(
                _ISSUES_BY_ID_QUERY,
                [{"ids": batch} for batch in wave],
                tolerated=frozenset({"NOT_FOUND"}),
            )
            for batch, data in zip(wave, answers, strict=True):
                nodes = _fetched(data, "nodes", "data", _RESPONSE_CODE)
                if not isinstance(nodes, list) or len(nodes) != len(batch):
                    raise IssueSourceRefreshError(
                        _RESPONSE_CODE, "data.nodes must answer one node per identity"
                    )
                for issue_id, node in zip(batch, nodes, strict=True):
                    if node is not None and not isinstance(node, dict):
                        raise IssueSourceRefreshError(
                            _RESPONSE_CODE, "data.nodes must hold objects or nulls"
                        )
                    records[issue_id] = node
        return records

    def _own_issue(
        self, record: dict[str, Any] | None, meter: RefreshMeter
    ) -> _ObservedIssue | None:
        """An Issue of the configured repository, or ``None`` when it is not one.

        A missing node, another kind of node, and an Issue of another
        repository (a transfer, or a relationship across repositories) are
        each positive evidence that no Issue of this collection is there.
        """
        if record is None:
            return None
        if _fetched_string(record, "__typename", "data.nodes[]", _RESPONSE_CODE) != (
            "Issue"
        ):
            return None
        repository = _object(record, "repository", "issue", _RESPONSE_CODE)
        if (
            _fetched_string(repository, "id", "issue.repository", _RESPONSE_CODE)
            != self.repository_id
        ):
            return None
        return self._observe_record(record, meter)

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
        complete = self._complete_nested_connections(record, meter)
        complete = self._complete_linked_pull_requests(complete, meter)
        issue = normalize_github_issue(
            complete, project_id=self.project_id, repository_id=self.repository_id
        )
        return _ObservedIssue(
            issue=issue,
            updated_at=_fetched_string(complete, "updatedAt", "issue", _RESPONSE_CODE),
            activity=_issue_activity(complete),
            linked_pull_request_numbers=frozenset(
                _all_linked_pull_request_numbers(complete)
            ),
            label_colors=_label_colors(complete),
        )

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
                meter.next_request(
                    f"{len(nodes)} {connection_name} of Issue {issue_id}"
                )
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

    def _complete_linked_pull_requests(
        self, record: Mapping[str, Any], meter: RefreshMeter
    ) -> dict[str, Any]:
        """Complete Linked Pull Requests while keeping engagement best-effort."""
        complete = copy.deepcopy(dict(record))
        issue_id = _fetched_string(complete, "id", "issue", _RESPONSE_CODE)
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
        trail = CursorTrail(f"Issue {issue_id} Linked Pull Requests")
        while has_next:
            cursor = trail.follow(end_cursor if isinstance(end_cursor, str) else None)
            meter.next_request(f"{len(nodes)} Linked Pull Requests of Issue {issue_id}")
            data = self.gateway.graphql(
                _ISSUE_LINKED_PULL_REQUESTS_QUERY,
                {"id": issue_id, "cursor": cursor},
            )
            issue = _object(data, "node", "data", _RESPONSE_CODE)
            next_connection = _object(
                issue,
                "closedByPullRequestsReferences",
                "data.node",
                _RESPONSE_CODE,
            )
            next_nodes, has_next, end_cursor = _connection_page(
                next_connection,
                "data.node.closedByPullRequestsReferences",
                _RESPONSE_CODE,
            )
            nodes.extend(next_nodes)
        connection["nodes"] = nodes
        connection["pageInfo"] = {"hasNextPage": False, "endCursor": end_cursor}
        return complete

    def _own_repository(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        """The repository node of an answer, checked to be the configured one."""
        repository = _object(data, "node", "data", _RESPONSE_CODE)
        observed_repository_id = _fetched_string(
            repository, "id", "data.repository", _RESPONSE_CODE
        )
        if observed_repository_id != self.repository_id:
            raise IssueSourceRefreshError(
                "github-repository-identity",
                "GitHub repository identity does not match Project configuration",
            )
        _fetched_string(repository, "nameWithOwner", "data.repository", _RESPONSE_CODE)
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


def _relationship_counterparts(
    changed: Mapping[str, _ObservedIssue], previous: Mapping[str, _ObservedIssue]
) -> list[str]:
    """The Issues whose relationship to a changed Issue was added or removed."""
    counterparts: set[str] = set()
    for issue_id, entry in changed.items():
        before = previous.get(issue_id)
        related_before = _related_ids(before.issue.relationships) if before else set()
        counterparts |= related_before ^ _related_ids(entry.issue.relationships)
    counterparts -= changed.keys()
    return sorted(counterparts)


def _related_ids(relationships: IssueRelationships) -> set[str]:
    related = {
        *relationships.sub_issues,
        *relationships.blocked_by,
        *relationships.blocking,
    }
    if relationships.parent is not None:
        related.add(relationships.parent)
    return related


def _connection_newest_updated_at(
    connection: Mapping[str, Any], path: str
) -> str | None:
    """Read the optional first `updatedAt` node of a change probe."""
    nodes = _fetched(connection, "nodes", path, _RESPONSE_CODE)
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        raise IssueSourceRefreshError(
            _RESPONSE_CODE, f"{path}.nodes must be an object array"
        )
    return (
        _fetched_string(nodes[0], "updatedAt", f"{path}.nodes[0]", _RESPONSE_CODE)
        if nodes
        else None
    )


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IssueSourceRefreshError(
            _RESPONSE_CODE, f"issue.updatedAt {value!r} is not an ISO 8601 timestamp"
        ) from exc


def _is_later(value: str, than: str) -> bool:
    return _timestamp(value) > _timestamp(than)


def _later(mark: str | None, value: str) -> str:
    return value if mark is None or _is_later(value, mark) else mark


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


def _all_linked_pull_request_numbers(record: Mapping[str, Any]) -> set[int]:
    """Identify every valid Linked Pull Request in the completed connection."""
    references = record.get("closedByPullRequestsReferences")
    nodes = references.get("nodes") if isinstance(references, Mapping) else None
    if not isinstance(nodes, list):
        return set()
    numbers: set[int] = set()
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        number = node.get("number")
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            numbers.add(number)
    return numbers


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
    linked_pull_requests = linked_pull_requests[:20]
    # The connection is unpaged: the count says how many the first twenty
    # left unlisted, so the dashboard can say so rather than show a
    # complete-looking list.
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
