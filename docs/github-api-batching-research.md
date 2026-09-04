---
status: research
date: 2026-09-05
---

# GitHub API batching and bulk queries for the GitHub Issue Source

Research dates: 2026-09-04–2026-09-05.

This note establishes what GitHub's API offers for batching and bulk queries,
to inform a later incremental-refresh design for
[`GitHubIssuesSource`](../src/dashpot/github_issues.py). It does not decide
the design. Every claim is checked against GitHub's documentation, the live
GraphQL schema (introspected through `gh api graphql`), the `cli/cli` and
`cli/go-gh` source at the installed release, or a read-only experiment
against `ned2/dashpot` (repository node id `R_kgDOUEerrg`; 81 Issues and 33
pull requests at the time, so numbers 1–114 are all in use). Experiments ran
GitHub CLI `2.98.0`. The initial research was read-only. The follow-up on
2026-09-05 made only the controlled scratch-Issue, relationship, and Milestone
mutations authorized by
[#128](https://github.com/ned2/dashpot/issues/128), then closed those scratch
objects. Anything the sources do not settle is marked **unverified**, and a
feature this repository cannot exercise is named as such rather than inferred.

## Summary

1. A Dashpot-shaped page of 100 Issues with six nested connections costs
   **6 primary points** and counts 52,100 nodes; the documented formula
   reproduces the observed `rateLimit.cost` exactly. A 2,000-Issue repository
   is therefore a 120-point, 20-request full sweep against a 5,000-point hourly
   budget. Points are not the constraint; wall time and secondary limits are.
2. `nodes(ids:)` takes **at most 100 ids** per call (`ARGUMENT_LIMIT`).
   Aliased `issue(number:)` lookups have no observed alias cap (600 aliases
   accepted), resolve independently, and report each missing number — and each
   pull request number — as an `errors[]` entry with `type: NOT_FOUND` and a
   `path` naming the alias, while sibling aliases still return data.
   `gh api` exits 1 whenever `errors` is present, so a batch must be judged
   from the body, not the exit code.
3. `filterBy: {since:}` is inclusive ("updated at or after") and matched a
   local computation exactly. Assignment and unassignment bump the Issue;
   Milestone assignment and removal bump both the Issue and the Milestone.
   Adding or removing a parent/sub-Issue relationship bumps **neither** Issue,
   even though GitHub records events on both. Cross-references and commit
   references also do not bump the Issue, and one observed case shows no bump
   on the blocker when a blocking relationship is added. Since Dashpot's
   Linked Pull Requests (`closedByPullRequestsReferences`) derive from
   cross-references, a `since` delta cannot see them change. Issue type changes
   remain unexercised for an explicit reason: `ned2/dashpot` is owned by a
   personal account and has no Issue types, which GitHub scopes to
   organizations.
4. Wide queries can **silently truncate nested connections**: requesting
   `timelineItems(first: 100)` for 60 or more Issues in one query returned
   fewer items *and a smaller `totalCount`* for some Issues, with no error and
   `hasNextPage` unable to reveal it. Dashpot's current 100-per-page query
   showed no such loss on 24 spot-checked Issues, but the mechanism exists.
5. A REST `304 Not Modified` costs nothing against the primary limit (verified:
   `x-ratelimit-used` unchanged), but the REST Issue list mixes pull requests
   in, carries only relationship *counts*, and has no linked-pull-request
   field, so it can serve as a change probe but not as a source of Dashpot's
   Issue profile.
6. `Repository.pullRequests` has no `filterBy`, `since`, or equivalent
   time-bound argument. It can order by `UPDATED_AT` in either direction and
   paginate by cursor, so a caller can scan newest-first to a client-side
   cutoff, but GitHub does not offer an exact server-side Pull Request delta
   through this connection.

## 1. GraphQL rate limits and query limits

### Primary limit and the point formula

The GraphQL primary limit for a user is "5,000 points per hour per user",
including personal access tokens; `GITHUB_TOKEN` in Actions gets "1,000 points
per hour per repository"; GitHub App installations get 5,000–12,500 depending
on size, or 10,000 on Enterprise Cloud
([GraphQL rate limits and query limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)).

The documented cost formula: "Add up the number of requests needed to fulfill
each unique connection in the call. Assume every request will reach the
`first` or `last` argument limits", then "Divide the number by 100 and round
the result to the nearest whole number", with "The minimum point value of a
call to the GraphQL API is 1" (same page). The worked example there scores a
100-repository × 50-issue × 60-label query at 5,101 requests → 51 points.

Verified against Dashpot's own `_ISSUES_QUERY` with `rateLimit { cost
nodeCount }` appended (experiment, `costs.py`): one page of 100 Issues, each
with `labels`, `assignees`, `subIssues`, `blockedBy`, `blocking` at `first:
100` and `closedByPullRequestsReferences(first: 20)`, is 1 + 100 × 6 = 601
requests → **cost 6**, and `nodeCount` 52,100 = 100 + 100 × (5 × 100 + 20).
Both matched the response (`{'cost': 6, 'nodeCount': 52100}`).

### Secondary limits

Same page, "Secondary rate limits":

- "No more than 100 concurrent requests are allowed. This limit is shared
  across the REST API and GraphQL API."
- "No more than 900 points per minute are allowed for REST API endpoints, and
  no more than 2,000 points per minute are allowed for the GraphQL API
  endpoint." These *secondary* points are a different currency: "For GraphQL
  requests, these point values are separate from the point value calculations
  for the primary rate limit", and "GraphQL requests without mutations" cost 1
  ([REST rate limits, "Calculating points for the secondary rate limit"](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)).
  So the per-minute GraphQL budget is effectively 2,000 read requests.
- "No more than 90 seconds of CPU time per 60 seconds of real time is allowed.
  No more than 60 seconds of this CPU time may be for the GraphQL API. You can
  roughly estimate the CPU time by measuring the total response time for your
  API requests."
- Content-creation and OAuth-token limits, and: "These secondary rate limits
  are subject to change without notice. You may also encounter a secondary
  rate limit for undisclosed reasons."
- "To avoid exceeding a rate limit, you should pause at least 1 second between
  mutative requests and avoid concurrent requests."

Exceeding limits: "If you exceed your primary rate limit, the response status
will still be `200`, but you will receive an error message, and the value of
the `x-ratelimit-remaining` header will be 0." For a secondary limit "the
response status will be `200` or `403`", and the client should honour
`retry-after`, then `x-ratelimit-reset`, "Otherwise, wait for at least one
minute before retrying" with exponential back-off (GraphQL limits page).

### Node limit, page cap, timeouts, other resource limits

- "Individual calls cannot request more than 500,000 total nodes"; nodes are
  counted by multiplying `first`/`last` values down the nesting (GraphQL
  limits page, "Node limit").
- "Values of `first` and `last` must be within 1-100" (same page); "The
  maximum number of items you can fetch using the `first` or `last` argument
  is 100"
  ([Using pagination in the GraphQL API](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api)).
- Timeouts: "If GitHub takes more than 10 seconds to process an API request,
  GitHub will terminate the request", and "If a timeout occurs for any of your
  API requests, additional points will be deducted from your primary rate
  limit for the next hour" (GraphQL limits page, "Timeouts").
- "If your GraphQL query consumes too many resources, GitHub will terminate
  the request and return partial results along with an error indicating that
  resource limits were exceeded" (same page, "Other resource limits"). See
  §3.4 for partial results observed *without* an error.

### The `rateLimit` object

Live schema descriptions (introspection, `intro2.json`): `cost` is "The point
cost for the current query counting against the rate limit"; `limit` "The
maximum number of points the client is permitted to consume in a 60 minute
window"; `remaining` "The number of points remaining in the current rate limit
window"; `used` "The number of points used in the current rate limit window";
`nodeCount` "The maximum number of nodes this query may return"; `resetAt` "The
time at which the current rate limit window resets in UTC epoch seconds". The
`rateLimit` root field takes `dryRun: Boolean` — "If true, calculate the cost
for the query without evaluating it".

Observed: `resetAt` is returned as an ISO 8601 string (`"2026-09-03T16:09:14Z"`)
despite the description's "epoch seconds". Querying `rateLimit` alone costs 1
point (`{"cost":1,"nodeCount":0}` observed with `dryRun: true`). The docs
prefer headers: "When possible, you should use the rate limit response headers
instead of querying the API"; GraphQL responses carry `x-ratelimit-*` with
`x-ratelimit-resource: graphql` (GraphQL limits page).

## 2. Aliases and bulk lookup

### `nodes(ids:)`

Schema: `Query.nodes` — "Lookup nodes by a list of IDs."; argument `ids` — "The
list of node IDs." Neither the schema nor the docs pages fetched state a
maximum. Experiment (81, 100, 101, 200 ids):

```text
[100] exit=0  nodes returned: 100  rateLimit: {'cost': 1, 'nodeCount': 100}
[101] exit=1  errors: [{"type": "ARGUMENT_LIMIT", "path": ["nodes"], ...,
       "message": "You may not provide more than 100 node ids; you provided 101."}]
```

So **100 ids per call** is the cap, reported as `ARGUMENT_LIMIT` with no
`data`. With Dashpot's full node fields, 81 ids cost 5 points and 42,201 nodes
(`costs.py`), i.e. the same per-Issue cost as a page.

Unknown, malformed, or pull-request ids: the array keeps positional order,
unknown and malformed ids become `null` with a `NOT_FOUND` error whose `path`
is `["nodes", <index>]`, and a pull request id resolves to a `PullRequest`
node that an `... on Issue` fragment renders as `{"__typename":"PullRequest"}`
(experiment `nodes_missing.out`):

```json
{"data":{"nodes":[{"__typename":"Issue","number":111,...},{"__typename":"PullRequest"},null,null],
 "rateLimit":{"cost":1}},
 "errors":[{"type":"NOT_FOUND","path":["nodes",2],...,"message":"Could not resolve to a node with the global id of 'I_kwDOUEerrs8AAAABPcDA6X'"},
           {"type":"NOT_FOUND","path":["nodes",3],...,"message":"Could not resolve to a node with the global id of 'not-an-id'"}]}
```

### Aliased `issue(number:)`

Schema: `Repository.issue` — "Returns a single issue from the current
repository by number." Experiment (`aliased.graphql`): aliases `a` = #111
(an Issue), `b` = #114 (a pull request), `c` = #99999 (missing), `d` = #110.

```text
exit=1
stdout: {"data":{"repository":{"a":{...#111...},"b":null,"c":null,"d":{...#110...}},
         "rateLimit":{"cost":1,"remaining":4931}},
         "errors":[{"type":"NOT_FOUND","path":["repository","b"],"locations":[{"line":3,"column":3}],
                    "message":"Could not resolve to an Issue with the number of 114."},
                   {"type":"NOT_FOUND","path":["repository","c"],...,
                    "message":"Could not resolve to an Issue with the number of 99999."}]}
stderr: gh: Could not resolve to an Issue with the number of 114.
        Could not resolve to an Issue with the number of 99999.
```

Established: aliases resolve independently; a missing alias is `null` in
`data` plus one `errors[]` entry with `type: "NOT_FOUND"` and `path:
["repository", "<alias>"]`; a pull request number is indistinguishable from a
missing number by `type` or wording; siblings keep their data. The current
adapter's substring test `"could not resolve to an issue"` in
[`find`](../src/dashpot/github_issues.py) matches this message.

Alias count: 100, 300, and 600 trivially-selected aliases were all accepted
(`exit=1` only because the pull-request numbers among 1–N are `NOT_FOUND`;
non-null aliases 78/81/81; cost 1 each). No alias cap was reached;
whether one exists above 600 is **unverified**.

Cost with Dashpot's full node fields: 81 aliases → **5 points**, 42,120 nodes
(81 × 520). Four parallel batches of ~21 aliases → **1 point each** (127
requests round down). By the formula, a batch of N full-field Issues costs
round((1 + 6N)/100), so N ≤ 24 costs 1 point and N = 100 costs 6.

## 3. `Repository.issues(filterBy: {since:})` and `updatedAt`

### Documented semantics

Schema (introspection, `intro1.json`): `IssueFilters.since` — "List issues
that have been updated at or after the given date." `Repository.issues` is "A
list of issues that have been opened in the repository" with `states` — "A
list of states to filter the issues by" — defaulting to none (all states).
`Issue.updatedAt` — "Identifies the date and time when the object was last
updated."; `Issue.lastEditedAt` — "The moment the editor made the last edit".
`IssueConnection.totalCount` — "Identifies the total count of items in the
connection." The docs describe the filter set generally
([Issue filters](https://docs.github.com/en/graphql/reference/input-objects#issuefilters)).

REST: `since` on `GET /repos/{owner}/{repo}/issues` is "Only show results that
were last updated after the given time. This is a timestamp in ISO 8601
format" ([List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues);
also the OpenAPI description, `openapi.json`).

### Verified behaviour

Experiment (`since.json`): `filterBy: {since: "2026-09-02T00:00:00Z"}`
returned 15 Issues, identical to the set computed locally from all 81
(`match: True`); all 15 were `CLOSED`, confirming `states` defaults to all.
The boundary is **inclusive** for both APIs: with `since` equal to #111's
`updatedAt` (`2026-09-03T01:39:03Z`), GraphQL returned #111 (3 Issues) and REST
returned #111 too, while REST with one second later excluded it. GraphQL
accepts `orderBy: {field: UPDATED_AT, direction: DESC}` on the same
connection; `issues(first: 1, orderBy: UPDATED_AT DESC) { totalCount nodes {
updatedAt } }` cost 1 point, 1 node, 0.58 s (`costs.py`).

### Which changes bump `updatedAt`

GitHub's documentation was found silent on this, so it was inspected on this
repository: complete `timelineItems(first: 100)` for all 81 Issues (fetched
three Issues per query after the truncation in §3.4 was found; ten random
Issues re-fetched singly matched exactly), comparing each event's `createdAt`
with the Issue's `updatedAt` and `lastEditedAt` (`complete_timelines.json`).
An event within 1.5 s of `updatedAt` is evidence that the event bumped it; an
event more than 1.5 s *after* `updatedAt` proves that event did not.

| Event | Verdict | Evidence |
|---|---|---|
| `ClosedEvent` (including close by merged pull request or commit) | bumps | 75 Issues with `updatedAt` at the close |
| `IssueComment` | bumps | 21 Issues |
| `LabeledEvent` / `UnlabeledEvent` | bumps | 5 and 4 Issues (e.g. #79, #80, #83 whose last change is a label) |
| Body edit | bumps | #4: `lastEditedAt == updatedAt` |
| `CrossReferencedEvent` (mention from an Issue or pull request) | **does not bump** | 17 Issues with cross-references up to days after `updatedAt`, e.g. #79 referenced by PR #115 on 2026-09-03 while `updatedAt` stayed 2026-08-31; all inspected cases had `willCloseTarget: false` |
| `ReferencedEvent` (commit reference) | **does not bump** | 7 Issues; the 6 exact coincidences were commits that closed the Issue |
| `BlockingAddedEvent` on the blocker | **does not bump** | #2: event 07:04:47 after `updatedAt` 06:17:25 |
| `AssignedEvent` / `UnassignedEvent` | bumps | Controlled #128 experiment on scratch Issue #132: `updatedAt` advanced to the exact second of each event |
| `SubIssueAddedEvent` / `ParentIssueAddedEvent` | **does not bump either Issue** | Controlled #128 experiment on scratch parent #132 and child #133: both timestamps stayed unchanged while both events were recorded |
| `SubIssueRemovedEvent` / `ParentIssueRemovedEvent` | **does not bump either Issue** | Controlled #128 experiment on the same pair: both timestamps again stayed unchanged while both events were recorded |
| `MilestonedEvent` / `DemilestonedEvent` | bumps the Issue and Milestone | Controlled #128 experiment on scratch Issue #132 and Milestone #1: both objects advanced to each event's second on assignment and removal |
| Issue type events | **not exercisable here** | `ned2/dashpot` is owned by a personal account; its `issueTypes` and named `issueType` fields returned `null`, and #132 returned `viewerCanType: false` |
| `BlockedByAddedEvent`, `RenamedTitleEvent`, `ReopenedEvent` | **unverified** | every historical occurrence was followed by a bumping event before `updatedAt`, so neither outcome can be separated |
| `ConnectedEvent`, project events | **unverified** | absent from this repository |

Consequences for a delta: a change to an Issue's linked pull requests
(`closedByPullRequestsReferences`, derived from cross-references) or to the
`blocking` side of a dependency can happen without the Issue entering a
`since` window. Adding or removing a parent/sub-Issue relationship enters
neither Issue in the window, so fetching the other end of a changed
relationship cannot recover this case. Assignment and Milestone assignment
or removal do enter the affected Issue in the window. Whether a
closing-keyword cross-reference
(`willCloseTarget: true`) bumps `updatedAt` is **unverified** (none present).
Whether the blocked side (`blockedBy`) is bumped is unverified, so a
dependency relationship change may be invisible on both sides. Issue type
change behavior has no verdict: GitHub exposes Issue types to organizations,
but this personal-account repository has no usable Issue Type identity.

#### Controlled #128 experiment

GitHub's GraphQL reference describes `Issue.updatedAt` only as the time the
object was last updated; it does not say which Issue operations update it. The
following controlled experiment therefore isolated each previously unresolved
operation on two scratch Issues and one scratch Milestone. All request windows
below are UTC on **2026-09-04**; the research was conducted on 2026-09-05 in
Australia/Melbourne. Client request windows bracket the complete `gh api`
process, while GitHub timestamps have one-second precision.

The scratch objects were:

| Object | Identity | Creation request window | GitHub creation state |
| --- | --- | --- | --- |
| Parent Issue #132 | `I_kwDOUEerrs8AAAABPuvAJw` | `16:31:19.363142036Z`–`16:31:20.123034383Z` | `createdAt = updatedAt = 16:31:19Z` |
| Child Issue #133 | `I_kwDOUEerrs8AAAABPuvFeQ` | `16:31:27.449512335Z`–`16:31:28.155256716Z` | `createdAt = updatedAt = 16:31:27Z` |
| Milestone #1, `Scratch: #128 updatedAt experiment` | `MI_kwDOUEerrs4BDWX-` | `16:31:36.899736242Z`–`16:31:37.483397526Z` | `createdAt = updatedAt = 16:31:37Z` |

The two Issues were created independently, without assignees, a parent,
sub-Issues, a Milestone, or an Issue type, so creation could not confound a
relationship result. The GraphQL creation shape was:

```graphql
mutation($repositoryId: ID!, $title: String!, $body: String!) {
  createIssue(
    input: {repositoryId: $repositoryId, title: $title, body: $body}
  ) {
    issue {
      id
      number
      url
      createdAt
      updatedAt
      viewerCanAssign
      viewerCanSetMilestone
      viewerCanType
    }
  }
}
```

A body string identifying the Issue as temporary #128 experiment data was
supplied for each creation.

GraphQL exposes no Milestone-creation mutation. Milestone #1 was created with
the documented REST endpoint and its returned `node_id` became the GraphQL
identity:

```console
gh api --method POST repos/ned2/dashpot/milestones \
  -f title='Scratch: #128 updatedAt experiment'
```

Every baseline and confirming state read used this query. In particular, it
observes the Milestone separately by repository Milestone Number so removing it
from an Issue does not also remove the only path by which its own `updatedAt`
can be read.

```graphql
query ExperimentState(
  $owner: String!
  $name: String!
  $parent: Int!
  $sub: Int!
  $milestone: Int!
) {
  repository(owner: $owner, name: $name) {
    parent: issue(number: $parent) {
      id
      number
      updatedAt
      assignees(first: 10) {
        nodes {
          id
          login
        }
      }
      parent {
        id
        number
      }
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
      milestone {
        id
        number
        title
        updatedAt
      }
      issueType {
        id
        name
      }
      viewerCanType
    }
    sub: issue(number: $sub) {
      id
      number
      updatedAt
      assignees(first: 10) {
        nodes {
          id
          login
        }
      }
      parent {
        id
        number
      }
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
      milestone {
        id
        number
        title
        updatedAt
      }
      issueType {
        id
        name
      }
      viewerCanType
    }
    milestone: milestone(number: $milestone) {
      id
      number
      updatedAt
      openIssueCount
      closedIssueCount
      issues(first: 10) {
        nodes {
          id
          number
        }
      }
    }
  }
}
```

The variables were `owner = "ned2"`, `name = "dashpot"`, `parent = 132`,
`sub = 133`, and `milestone = 1`.

The baseline read, from `16:31:57.847981360Z` through
`16:31:58.537073569Z`, confirmed the empty relationship facts and that all
three `updatedAt` values still matched the creation responses in the table
above.

##### Assignment and unassignment

The mutations were:

```graphql
mutation Assign($issue: ID!, $assignees: [ID!]!) {
  addAssigneesToAssignable(
    input: {assignableId: $issue, assigneeIds: $assignees}
  ) {
    assignable {
      ... on Issue {
        id
        number
        updatedAt
        assignees(first: 10) {
          nodes {
            id
            login
          }
        }
      }
    }
  }
}

mutation Unassign($issue: ID!, $assignees: [ID!]!) {
  removeAssigneesFromAssignable(
    input: {assignableId: $issue, assigneeIds: $assignees}
  ) {
    assignable {
      ... on Issue {
        id
        number
        updatedAt
        assignees(first: 10) {
          nodes {
            id
            login
          }
        }
      }
    }
  }
}
```

| Operation | Request window | #132 `updatedAt` | Timeline event |
| --- | --- | --- | --- |
| Assign `ned2` | `16:32:10.779998064Z`–`16:32:12.007764581Z` | `16:31:19Z` → `16:32:11Z` | `AssignedEvent.createdAt = 16:32:11Z` |
| Unassign `ned2` | `16:32:31.959462821Z`–`16:32:33.170524871Z` | `16:32:11Z` → `16:32:32Z` | `UnassignedEvent.createdAt = 16:32:32Z` |

An `ExperimentState` read from `16:32:22.189482052Z` through
`16:32:22.818613983Z` independently confirmed the assigned state and first
timestamp. The mutation results and the final timeline read confirmed the
unassigned state and second timestamp. **Assignment and unassignment bump the
Issue's `updatedAt`.**

##### Parent/sub-Issue addition and removal

The mutations returned both affected Issues:

```graphql
mutation AddRelationship($parent: ID!, $sub: ID!) {
  addSubIssue(input: {issueId: $parent, subIssueId: $sub}) {
    issue {
      id
      number
      updatedAt
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
      parent {
        id
        number
      }
    }
    subIssue {
      id
      number
      updatedAt
      parent {
        id
        number
      }
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
    }
  }
}

mutation RemoveRelationship($parent: ID!, $sub: ID!) {
  removeSubIssue(input: {issueId: $parent, subIssueId: $sub}) {
    issue {
      id
      number
      updatedAt
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
      parent {
        id
        number
      }
    }
    subIssue {
      id
      number
      updatedAt
      parent {
        id
        number
      }
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
    }
  }
}
```

| Operation | Request window | Parent #132 | Child #133 | Timeline events |
| --- | --- | --- | --- | --- |
| Add relationship | `16:32:49.243100854Z`–`16:32:50.113601248Z` | `subIssues` gained #133; `updatedAt` stayed `16:32:32Z` | `parent` became #132; `updatedAt` stayed `16:31:27Z` | `SubIssueAddedEvent` and `ParentIssueAddedEvent` at `16:32:50Z` |
| Remove relationship | `16:33:10.764322946Z`–`16:33:11.812701944Z` | `subIssues` emptied; `updatedAt` stayed `16:32:32Z` | `parent` became `null`; `updatedAt` stayed `16:31:27Z` | `SubIssueRemovedEvent` and `ParentIssueRemovedEvent` at `16:33:11Z` |

An `ExperimentState` read from `16:33:01.376461226Z` through
`16:33:02.018470961Z` independently confirmed the added relationship and
unchanged timestamps. The remove mutation and final timeline read confirmed
the cleared relationship and second event pair. **Adding and removing a
parent/sub-Issue relationship bump neither affected Issue**, even though
GitHub records a same-second event at both ends.

##### Milestone assignment and removal

The mutations were:

```graphql
mutation AssignMilestone($issue: ID!, $milestone: ID!) {
  updateIssue(input: {id: $issue, milestoneId: $milestone}) {
    issue {
      id
      number
      updatedAt
      milestone {
        id
        number
        title
        updatedAt
        openIssueCount
        closedIssueCount
        issues(first: 10) {
          nodes {
            id
            number
          }
        }
      }
    }
  }
}

mutation RemoveMilestone($issue: ID!) {
  updateIssue(input: {id: $issue, milestoneId: null}) {
    issue {
      id
      number
      updatedAt
      milestone {
        id
        number
        title
        updatedAt
      }
    }
  }
}
```

| Operation | Request window | #132 `updatedAt` | Milestone #1 `updatedAt` | Timeline event |
| --- | --- | --- | --- | --- |
| Assign | `16:33:22.644018954Z`–`16:33:23.761108700Z` | `16:32:32Z` → `16:33:23Z` | `16:31:37Z` → `16:33:23Z` | `MilestonedEvent.createdAt = 16:33:23Z` |
| Remove | `16:33:30.937718676Z`–`16:33:32.073800743Z` | `16:33:23Z` → `16:33:31Z` | `16:33:23Z` → `16:33:31Z` | `DemilestonedEvent.createdAt = 16:33:31Z` |

The `ExperimentState` read from `16:33:41.129337838Z` through
`16:33:41.712385912Z` confirmed the Issue no longer named a Milestone,
Milestone #1 listed no Issues, and both removal timestamps were
`16:33:31Z`. **Milestone assignment and removal bump both the Issue and the
Milestone.**

##### Complete event read

This final query captured all relevant event timestamps without relying on a
mutation payload. It ran from `16:34:39.004319093Z` through
`16:34:39.770494647Z` and confirmed the final pre-cleanup state and every event
listed above.

```graphql
query IssueSnapshots($ids: [ID!]!) {
  nodes(ids: $ids) {
    __typename
    ... on Issue {
      id
      number
      createdAt
      updatedAt
      assignees(first: 10) {
        nodes {
          id
          login
        }
      }
      parent {
        id
        number
      }
      subIssues(first: 10) {
        nodes {
          id
          number
        }
      }
      milestone {
        id
        number
        title
        updatedAt
      }
      issueType {
        id
        name
      }
      timelineItems(
        last: 20
        itemTypes: [
          ASSIGNED_EVENT
          UNASSIGNED_EVENT
          MILESTONED_EVENT
          DEMILESTONED_EVENT
          SUB_ISSUE_ADDED_EVENT
          SUB_ISSUE_REMOVED_EVENT
          PARENT_ISSUE_ADDED_EVENT
          PARENT_ISSUE_REMOVED_EVENT
          ISSUE_TYPE_ADDED_EVENT
          ISSUE_TYPE_CHANGED_EVENT
          ISSUE_TYPE_REMOVED_EVENT
        ]
      ) {
        nodes {
          __typename
          ... on AssignedEvent {
            createdAt
          }
          ... on UnassignedEvent {
            createdAt
          }
          ... on MilestonedEvent {
            createdAt
            milestoneTitle
          }
          ... on DemilestonedEvent {
            createdAt
            milestoneTitle
          }
          ... on SubIssueAddedEvent {
            createdAt
            subIssue {
              id
              number
            }
          }
          ... on SubIssueRemovedEvent {
            createdAt
            subIssue {
              id
              number
            }
          }
          ... on ParentIssueAddedEvent {
            createdAt
            parent {
              id
              number
            }
          }
          ... on ParentIssueRemovedEvent {
            createdAt
            parent {
              id
              number
            }
          }
          ... on IssueTypeAddedEvent {
            createdAt
            issueType {
              id
              name
            }
          }
          ... on IssueTypeChangedEvent {
            createdAt
            issueType {
              id
              name
            }
            prevIssueType {
              id
              name
            }
          }
          ... on IssueTypeRemovedEvent {
            createdAt
            issueType {
              id
              name
            }
          }
        }
      }
    }
  }
}
```

##### Issue type limitation

The live schema exposes `Issue.issueType`, `Repository.issueTypes`,
`Repository.issueType`, `UpdateIssueInput.issueTypeId`, and the dedicated
`updateIssueIssueType` mutation. A capable repository could use:

```graphql
mutation SetIssueType($issueId: ID!, $issueTypeId: ID) {
  updateIssueIssueType(
    input: {issueId: $issueId, issueTypeId: $issueTypeId}
  ) {
    issue {
      id
      number
      updatedAt
      issueType {
        id
        name
      }
    }
  }
}
```

This Project's repository cannot supply the required Issue Type identity. The
capability query ran from `16:34:55.561717510Z` through
`16:34:56.127091792Z`:

```graphql
query IssueTypeCapability(
  $owner: String!
  $name: String!
  $number: Int!
) {
  repository(owner: $owner, name: $name) {
    owner {
      __typename
      login
    }
    issueTypes(first: 20) {
      totalCount
      nodes {
        id
        name
        isEnabled
      }
    }
    issueType(name: "Task") {
      id
      name
      isEnabled
    }
    issue(number: $number) {
      id
      number
      updatedAt
      issueType {
        id
        name
      }
      viewerCanType
    }
  }
}
```

With `owner = "ned2"`, `name = "dashpot"`, and `number = 132`, it returned
an owner of `{"__typename":"User","login":"ned2"}`, `issueTypes: null`,
`issueType: null`, and an untyped #132 with `viewerCanType: false`. GitHub's
documentation defines Issue types as organization-level configuration and
says every *organization* receives the default Task, Bug, and Feature types
([Managing issue types in an organization](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-types-in-an-organization)).
`ned2/dashpot` is instead owned by a personal account. There was therefore no
valid type-setting mutation to perform, and **this experiment gives no verdict
on whether an Issue type change bumps `updatedAt`**.

##### Cleanup

After the final evidence reads, both scratch Issues were closed as not planned
with this mutation:

```graphql
mutation CloseScratch($issue: ID!) {
  closeIssue(input: {issueId: $issue, stateReason: NOT_PLANNED}) {
    issue {
      id
      number
      state
      stateReason
      updatedAt
      closedAt
    }
  }
}
```

| Cleanup | Request window | Result |
| --- | --- | --- |
| Close #132 | `16:35:04.132369709Z`–`16:35:05.140707130Z` | closed at `16:35:04Z` |
| Close #133 | `16:35:13.596861770Z`–`16:35:15.003516676Z` | closed at `16:35:14Z` |
| Close Milestone #1 through REST | `16:35:20.681929587Z`–`16:35:21.258246478Z` | closed and updated at `16:35:21Z` |

The final Milestone cleanup command was:

```console
gh api --method PATCH repos/ned2/dashpot/milestones/1 -f state=closed
```

The cleanup timestamps are later bumping operations and do not participate in
the relationship verdicts above.

### Transferred and deleted Issues

Transfer: "When you transfer an issue, comments and assignees are retained.
Labels and milestones are also retained if they're present in the target
repository", and "The original URL redirects to the new issue's URL"
([Transferring an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/transferring-an-issue-to-another-repository)).
Deletion: "When visiting the URL of a deleted issue, collaborators will see a
message stating that the web page can't be found (but they can use the API to
determine that it was deleted)"
([Deleting an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/deleting-an-issue)).
How the GraphQL API reports a transferred or deleted number (`NOT_FOUND`, a
redirect, or a `TransferredEvent` on the new Issue) could not be tested
without mutating and is **unverified**; the `TransferredEvent` timeline type
exists in the schema (accepted in the timeline queries above).

What a delta can and cannot show, by reasoning from the verified facts: a
`since` query lists only Issues that still exist in the repository, so a
transferred or deleted Issue never appears in it. `totalCount` moves only on a
net change; one addition and one removal in the same window leave it
unchanged. Issue numbers are shared with pull requests (§4), so a gap in
numbers is not evidence of deletion: here numbers 1–114 are 81 Issues plus 33
pull requests with no gap.

### Silent truncation of nested connections in wide queries

Experiment (`aliased_timelines.json` and the scaling run): the same
`timelineItems(first: 100) { totalCount nodes { __typename } }` selection on N
aliased Issues, with #100, #69, #76, #111, #2 always included:

```text
N=5  ... #100=(5, 5)  #69=(6, 6)  #76=(6, 6)  #111=(6, 6)  nodeCount 500
N=40 ... #100=(5, 5)  #69=(6, 6)  #76=(6, 6)  #111=(6, 6)  nodeCount 4000
N=60 ... #100=(3, 3)  #69=(6, 6)  #76=(6, 6)  #111=(3, 3)  nodeCount 6000   errors=None
N=81 ... #100=(2, 2)  #69=(3, 3)  #76=(0, 0)  #111=(2, 2)  nodeCount 8100   errors=None
```

The same loss appeared through `issues(first: 100) { nodes { timelineItems
... } }` (#100: 2 of 5; #76: 0 of 6) and was reproducible across reruns; single
Issue queries returned all items whatever the fragment list. `totalCount`
shrank with the nodes, `cost` stayed 1, `nodeCount` was far below 500,000, and
no `errors` entry was returned, unlike the documented "partial results along
with an error". The cause is **unverified**.

Dashpot's current page query was checked for the same effect: 24 of the 81
Issues from one `_ISSUES_QUERY` page (`nested_check.py`) were re-fetched
singly with `_ISSUE_QUERY`; labels, assignees, sub-issues, blocked-by,
blocking, linked pull requests, comment counts and parent matched on all 24
(16 Issues in the page carry relationships, 76 carry labels). No truncation
observed at this size; the check does not prove absence at 100 Issues or in
larger repositories.

## 4. REST conditional requests and the Issues list

- Conditional requests: "Making a conditional request does not count against
  your primary rate limit if a `304` response is returned and the request was
  made while correctly authorized with an `Authorization` header"
  ([REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)).
  Verified: `GET /repos/ned2/dashpot/issues?state=all&per_page=5` answered
  `200` with `Etag: W/"f210…"`, `Cache-Control: private, max-age=60`,
  `X-Ratelimit-Used: 9`; the same request with `If-None-Match` answered `304
  Not Modified` with `X-Ratelimit-Used: 9` (`rest_304.txt`). `gh api` exits 1
  on the 304 and prints `gh: HTTP 304` (see §5).
- The REST primary limit is separate: "The GraphQL API also has a separate
  primary rate limit"
  ([REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api));
  authenticated users get 5,000 requests per hour, and the responses above
  reported `X-Ratelimit-Resource: core`, `X-Ratelimit-Limit: 5000`. REST
  secondary limit: "No more than 900 points per minute".
- Pull requests are mixed in: "GitHub's REST API considers every pull request
  an issue, but not every issue is a pull request. For this reason, "Issues"
  endpoints may return both issues and pull requests in the response. You can
  identify pull requests by the `pull_request` key"
  ([List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues)).
  Verified: `since=2026-09-02T00:00:00Z` returned 33 items, 18 of them pull
  requests. The default `state` is `open`, so `state=all` is required for
  parity with Dashpot's `[OPEN, CLOSED]`.
- Fields (GitHub's OpenAPI description, schema `issue`, and the live body of
  `GET /repos/ned2/dashpot/issues/111`): `sub_issues_summary` is `{total,
  completed, percent_completed}`, `issue_dependencies_summary` is
  `{blocked_by, blocking, total_blocked_by, total_blocking}`, and
  `parent_issue_url` is "URL to get the parent issue of this issue, if it is a
  sub-issue". These are counts and one URL, not identities. There is **no
  linked-pull-request field**; identities require the per-Issue endpoints
  `GET .../issues/{n}/sub_issues`, `.../parent`,
  `.../dependencies/blocked_by`, `.../dependencies/blocking`
  ([Sub-issues](https://docs.github.com/en/rest/issues/sub-issues),
  [Issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies))
  and `.../timeline` for pull request links.

## 5. `gh api` behaviour

Source: `cli/cli` at `v2.98.0`, `pkg/cmd/api/api.go`, `pkg/cmd/api/pagination.go`,
`pkg/cmdutil/errors.go`, `internal/ghcmd/cmd.go`; `cli/go-gh` at `v2.13.0`
(the version pinned in cli's `go.mod`), `pkg/api/cache.go`,
`pkg/api/http_client.go`, `pkg/config/config.go`.

- **Errors.** `processResponse` (`api.go` lines 473–562) parses every GraphQL
  response body through `parseErrorResponse` (lines 651–722), which joins each
  `errors[].message` with `"\n"`. When that string is non-empty the body is
  still copied to stdout, `gh: <messages>` is printed to stderr, and the
  command returns `cmdutil.SilentError` (line 560), "an error that triggers
  exit code 1 without any error messaging" (`errors.go` line 34), mapped to
  `exitError = 1` in `cmd.go` lines 46 and 199–200. Verified live in §2: exit
  1, full `data` + `errors` JSON on stdout, joined messages on stderr. Two
  consequences: exit code 1 does not mean "no data", and `--jq` / `--template`
  are skipped when any error is present (`api.go` lines 505–515: `serverError
  == ""` guards both), so the raw body is printed instead of the filtered one.
  A non-JSON-error HTTP status above 299 becomes `HTTP <code>` (line 550),
  which is why a `304` also exits 1.
- **`--paginate`.** "all pages of results will sequentially be requested until
  there are no more pages of results. For GraphQL requests, this requires that
  the original query accepts an `$endCursor: String` variable and that it
  fetches the `pageInfo{ hasNextPage, endCursor }` set of fields from a
  collection. Each page is a separate JSON array or object" (`api.go` lines
  130–135; [`gh api` manual](https://cli.github.com/manual/gh_api)).
  `findEndCursor` (`pagination.go` lines 26–92) streams the JSON tokens and
  stops at the **first** `pageInfo` object whose `hasNextPage` and `endCursor`
  it sees. In a query shaped like Dashpot's, the nested connections' `pageInfo`
  precede the top-level one, so `--paginate` would follow a nested cursor
  (inferred from the source; not run).
- **`--slurp`.** "Use with "--paginate" to return an array of all pages of
  either JSON arrays or objects" (`api.go` line 295); mutually exclusive with
  `--jq` and `--template` (lines 256–260).
- **`--cache`.** The flag is a `time.Duration` (`api.go` line 301) and enables
  caching only when greater than zero (line 402). In go-gh, a request is
  cacheable when it is `GET`/`HEAD` or a `POST` to `/graphql` (`cache.go`
  lines 39–49); a response is cached when its status is below 500 and not 403
  (lines 51–53) — so a `200` GraphQL body carrying `errors`, and a `404`, are
  cached. The key is SHA-256 of method, URL, `Accept`, `Authorization`, and the
  request body (lines 55–73); the file lives at `<dir>/<k[0:2]>/<k[2:4]>/<k[4:]>`
  (lines 134–139); expiry is by file modification time against the TTL (lines
  158–161); the default TTL when caching is enabled without one is 24 h
  (`http_client.go` lines 74–76). The directory is `$XDG_CACHE_HOME/gh`, else
  `~/.cache/gh` on Linux (`config.go` lines 300–312). There is a `gh config
  clear-cache` command in the tree (`pkg/cmd/config/clear-cache/`).
- **Timing** (single samples, `costs.py`; not a benchmark): `gh --version`
  0.05 s; the 1-point probe 0.58 s; Dashpot's 81-Issue page 3.19 s; 81 aliased
  full-field Issues 2.68 s; 81 full-field `nodes(ids:)` 3.25 s; four parallel
  batches of ~21 full-field Issues 1.15–1.81 s each, 1.82 s wall.

## 6. Concurrency guidance for parallel GraphQL requests

The primary sources say, in order of specificity:

- "No more than 100 concurrent requests are allowed. This limit is shared
  across the REST API and GraphQL API" (GraphQL limits page).
- "No more than 2,000 points per minute are allowed for the GraphQL API
  endpoint", at 1 secondary point per read request (§1).
- "No more than 60 seconds of this CPU time may be for the GraphQL API" per 60
  s, estimated by response time (§1).
- "To avoid exceeding secondary rate limits, you should make requests serially
  instead of concurrently. To achieve this, you can implement a queue system
  for requests" (REST best practices); "avoid concurrent requests" (GraphQL
  limits page).
- Secondary-limit responses are `200` or `403` with `retry-after`; "Continuing
  to make requests while you are rate limited may result in the banning of
  your integration" (REST best practices).

Observed: four concurrent full-field batches completed without error (§5).
That is not evidence about where the limits bite. By the CPU-time rule and the
observed ~3 s per 100-Issue page, a 20-page sweep run fully in parallel would
place roughly 60 s of GraphQL response time inside one minute — at the
documented budget — which is arithmetic from single samples, not a measurement.

## 7. Options for an incremental refresh

Cost model for a 2,000-Issue repository with Dashpot's current node fields,
assuming no nested connection exceeds 100 items (each overflow adds one
1-point request today). Points are primary points; the budget is 5,000 per
hour per user.

Baseline, the current full sweep: 20 requests of 6 points = **120 points**,
about 60 s serial at ~3 s per page (extrapolated from an 81-Issue page).

| Option | Requests | Points | Wall time | What it cannot prove |
|---|---|---|---|---|
| (a) Change probe: `issues(first: 1, orderBy: UPDATED_AT DESC) { totalCount nodes { updatedAt } }` | 1 | 1 | ~0.6 s | any change that does not bump `updatedAt` (cross-references and so Linked Pull Requests; the blocker side of a dependency; both ends of a parent/sub-Issue relationship); Issue type changes, which this repository cannot exercise; a deletion or transfer offset by a creation; a transfer or deletion of an older Issue leaves `updatedAt` unchanged and only moves `totalCount` |
| (a′) REST probe: conditional `GET /repos/{o}/{r}/issues?state=all&sort=updated&per_page=1` | 1 | 0 on `304`, 1 REST request otherwise | ~0.5 s | same gaps; the list ETag also changes on pull request activity, so a `200` is not proof of Issue change; REST and GraphQL limits are separate |
| (b) Delta by `since`: `issues(first: 100, filterBy: {since}, orderBy: UPDATED_AT)` with full fields | ceil(changed/100) | 6 per 100 changed | ~3 s per 100 changed | everything in (a); needs an overlap window (inclusive boundary, clock skew); nested overflow pagination as today; wide-query truncation (§3.4) applies to the page shape |
| (c) Bulk fetch by `nodes(ids:)` of known identities | ceil(n/100) | 6 per 100 (1 per 100 with identity-only fields) | ~3 s per 100 | requires the identities first; a transferred or deleted Issue is a `null` with `NOT_FOUND`, indistinguishable from each other; ids only — the 100-id cap is hard |
| (d) Parallel full sweep by aliased `issue(number:)` | numbers span Issues *and* pull requests, e.g. ~3,000 numbers: 125 batches of 24 (1 point each) or 30 batches of 100 (6 points each) | ~125 or ~180 | bounded by concurrency limits (§6); each batch ~1.2–1.8 s observed at ~21 Issues | needs the current maximum number from a probe; Issues created after that probe are missed; every pull request number is an `errors[]` entry, so every batch exits 1 and stdout/stderr grow with the pull request count; the same truncation risk as (b) above 60 Issues per query (§3.4); a missing number cannot be told apart from a pull request |

Facts common to every delta shape: a `since` or `nodes` result lists only
Issues that still exist, so absence is never established by a delta (compare
[ADR 0002](adr/0002-require-complete-issue-profile-snapshots.md)); the
relationship facts Dashpot collects live on both ends of a relationship, and
the observed evidence shows the blocker's `blocking` end does not bump
`updatedAt` and neither end of a parent/sub-Issue relationship bumps it; and
the wide-query truncation in §3.4 is invisible to `hasNextPage`, so any batch
shape above about 40 Issues per query needs its own completeness check before
it can be trusted as a fresh observation. Assignment and Milestone assignment
or removal are not blind spots: each bumps the affected Issue.

### Pull Request refresh has ordering but no server-side delta

The live schema was introspected at `2026-09-04T17:38:44Z` with this exact
query (the response was projected to the `pullRequests` field with `jq`):

```graphql
query PullRequestArgumentsAndOrder {
  repositoryType: __type(name: "Repository") {
    fields(includeDeprecated: true) {
      name
      description
      args {
        name
        description
        defaultValue
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
            }
          }
        }
      }
    }
  }
  issueOrder: __type(name: "IssueOrder") {
    kind
    name
    description
    inputFields {
      name
      description
      defaultValue
      type {
        kind
        name
        ofType {
          kind
          name
        }
      }
    }
  }
  issueOrderField: __type(name: "IssueOrderField") {
    kind
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
  orderDirection: __type(name: "OrderDirection") {
    kind
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
}
```

`Repository.pullRequests` reported exactly these arguments: `states`,
`labels`, `headRefName`, `baseRefName`, `orderBy`, `after`, `before`, `first`,
and `last`. There is no `filterBy`, `since`, or other time-bound argument.
`orderBy` is an `IssueOrder`; `IssueOrderField` contains `CREATED_AT`,
`UPDATED_AT`, and `COMMENTS`, while `OrderDirection` contains `ASC` and
`DESC`.

The pagination types were introspected separately at
`2026-09-04T17:38:45Z` because GitHub limits repeated `__Type.fields`
selections in one request:

```graphql
query PullRequestPagination {
  pullRequestConnection: __type(name: "PullRequestConnection") {
    kind
    name
    description
    fields(includeDeprecated: true) {
      name
      description
      type {
        kind
        name
        ofType {
          kind
          name
        }
      }
    }
  }
  pageInfo: __type(name: "PageInfo") {
    kind
    name
    description
    fields(includeDeprecated: true) {
      name
      description
      type {
        kind
        name
        ofType {
          kind
          name
        }
      }
    }
  }
}
```

`PullRequestConnection` reported `edges`, `nodes`, `pageInfo`, and
`totalCount`. `PageInfo` reported `endCursor`, `hasNextPage`,
`hasPreviousPage`, and `startCursor`; the connection arguments supply both
forward (`first`, `after`) and backward (`last`, `before`) cursor pagination.

A read-only request at `2026-09-04T17:38:54Z` exercised the useful shape:

```graphql
query PullRequestsByUpdatedAt(
  $owner: String!
  $name: String!
  $first: Int!
  $after: String
) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: $first
      after: $after
      states: [OPEN, CLOSED, MERGED]
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        number
        updatedAt
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
```

With `$first: 2`, the first page returned #135 at
`2026-09-04T17:38:49Z` and #131 at `2026-09-04T12:39:43Z`, plus an
`endCursor` and `hasNextPage: true`. Repeating the same query at
`2026-09-04T17:39:02Z` with that cursor returned the next older Pull Requests,
#130 at `2026-09-04T12:38:12Z` and #119 at
`2026-09-04T01:03:59Z`. This verifies that a client can page a descending
`updatedAt` scan and stop after crossing its own overlap cutoff. It cannot ask
the server for only Pull Requests updated since that cutoff, so this is a
prefix scan rather than an exact delta. The schema does not document the
tie-break order for equal `updatedAt` values; a design that stops at a cutoff
must include every page containing the boundary timestamp rather than assume
a stable secondary key.

### Closing-reference changes bump the Pull Request, then index asynchronously

The controlled experiment for
[#123](https://github.com/ned2/dashpot/issues/123) used scratch Issue #134 and
scratch Pull Request #135. The PR targeted `main` and began without a closing
reference. Its branch contained an empty commit only. The setup was created
at `2026-09-04T17:38:03.658382666Z`–`17:38:28.241865852Z`; the first evidence
read at `17:38:39.662791501Z` found PR `updatedAt: 17:38:29Z`, Issue
`updatedAt: 17:38:04Z`, and empty connections at both ends.

Every evidence read used this exact query (the final read added
`includeClosedPrs: true` to the Issue connection after the PR was closed):

```graphql
query Issue123ClosingReference(
  $owner: String!
  $name: String!
  $pr: Int!
  $issue: Int!
) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      id
      number
      body
      state
      updatedAt
      closingIssuesReferences(first: 10) {
        nodes { id number updatedAt }
      }
    }
    issue(number: $issue) {
      id
      number
      updatedAt
      closedByPullRequestsReferences(first: 10) {
        nodes { id number state updatedAt }
      }
    }
  }
}
```

The link and unlink used the same exact mutation shape with different
`$body` values:

```graphql
mutation Issue123LinkOrUnlinkClosingReference(
  $pullRequestId: ID!
  $body: String!
) {
  updatePullRequest(
    input: {pullRequestId: $pullRequestId, body: $body}
  ) {
    pullRequest {
      id
      number
      body
      updatedAt
      closingIssuesReferences(first: 10) {
        nodes { id number updatedAt }
      }
    }
  }
}
```

Closing the linked PR used:

```graphql
mutation Issue123ClosePullRequest($pullRequestId: ID!) {
  closePullRequest(input: {pullRequestId: $pullRequestId}) {
    pullRequest {
      id
      number
      state
      updatedAt
      closingIssuesReferences(first: 10) {
        nodes { id number updatedAt }
      }
    }
  }
}
```

| Operation and request time | PR `updatedAt` before → after | Issue `updatedAt` | Connection evidence |
|---|---|---|---|
| Add `Closes #134`, `17:38:48.866379473Z` | `17:38:29Z` → `17:38:49Z` | stayed `17:38:04Z` | mutation response still empty; both ends named each other at `17:38:57.489434665Z` |
| Remove the closing reference, `17:39:05.265047571Z` | `17:38:49Z` → `17:39:05Z` | stayed `17:38:04Z` | mutation response still linked; both ends were empty at `17:39:12.746566766Z` |
| Add `Closes #134` again, `17:40:23.813795953Z` | `17:39:05Z` → `17:40:24Z` | stayed `17:38:04Z` | both ends named each other at `17:40:32.419016049Z` |
| Close PR #135, `17:40:39.111713032Z` | `17:40:24Z` → `17:40:39Z` | stayed `17:38:04Z` | the linked PR read `CLOSED` at both ends at `17:40:46.878242398Z` |

Thus adding and removing a body-derived closing reference, and closing the
linked PR, each bumps the Pull Request and not the Issue. The derived
connections are not transactionally current with the mutation: they lagged
the PR body and timestamp by 7–9 seconds in this experiment. GitHub publishes
no indexing-latency bound, so a consumer must not treat the first connection
read after a newer PR timestamp as conclusive. The experiment did not merge a
scratch PR; the issue's earlier premise that merge bumps the PR remains based
on GitHub's ordinary PR state semantics rather than this controlled sequence.

PR #135 and Issue #134 were closed after the final read, and the remote
scratch branch was deleted. No real Issue or branch was changed.

The combined steady-state probe was exercised at
`2026-09-04T17:56:15.448926555Z` with the exact production selections:

```graphql
query Issue123CombinedProbe($repositoryId: ID!) {
  rateLimit { cost limit remaining resetAt }
  node(id: $repositoryId) {
    ... on Repository {
      id
      nameWithOwner
      issues(
        first: 1
        states: [OPEN, CLOSED]
        orderBy: {field: UPDATED_AT, direction: DESC}
      ) {
        totalCount
        nodes { updatedAt }
      }
      pullRequests(
        first: 1
        states: [OPEN, CLOSED, MERGED]
        orderBy: {field: UPDATED_AT, direction: DESC}
      ) {
        nodes { updatedAt }
      }
    }
  }
}
```

GitHub reported `rateLimit.cost: 1`, an Issue count of 91, newest Issue
`updatedAt: 2026-09-04T17:40:59Z`, and newest Pull Request
`updatedAt: 2026-09-04T17:41:01Z`. Adding the Pull Request signal to the Issue
probe therefore does not add a request or a primary point on an unchanged
tick.

## Experiment artefacts

Commands and raw outputs referenced above were captured in the session's
scratch directory: `aliased.graphql`, `aliased.out`, `aliased.err`,
`nodes_missing.out`, `intro1.json`–`intro3.json`, `since.json`,
`rest_issues.txt`, `rest_304.txt`, `costs.py`, `nested_check.py`,
`complete_timelines.json`, `aliased_timelines.json`, and the downloaded
documentation text under `docs/`. The queries are reproducible from the
descriptions in each section; those initial experiments were read-only. The
controlled #128 queries, mutations, request windows, identities, and cleanup
are reproduced inline in §3. The #123 Pull Request schema, paging, and
closing-reference queries are reproduced inline in §7; only the explicitly
named scratch objects in the closing-reference experiment were mutated.

## Sources

- [Rate limits and query limits for the GraphQL API](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [Using pagination in the GraphQL API](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api)
- [Using global node IDs](https://docs.github.com/en/graphql/guides/using-global-node-ids)
- [GraphQL reference: Issues](https://docs.github.com/en/graphql/reference/issues)
- [GraphQL reference: queries](https://docs.github.com/en/graphql/reference/queries),
  [input objects (`IssueFilters`)](https://docs.github.com/en/graphql/reference/input-objects#issuefilters),
  [objects (`Repository`, `PullRequestConnection`, and `PageInfo`)](https://docs.github.com/en/graphql/reference/objects),
  and the live schema introspected with `gh api graphql` (`__type(name: "Query" | "IssueFilters" | "RateLimit" | "Repository" | "Issue" | "IssueConnection" | "PullRequestConnection" | "PageInfo" | "IssueOrder" | "IssueOrderField" | "OrderDirection")`)
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Best practices for using the REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- [REST API endpoints for issues: List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues),
  [sub-issues](https://docs.github.com/en/rest/issues/sub-issues),
  [issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies)
- [REST API endpoints for Milestones](https://docs.github.com/en/rest/issues/milestones)
- [Managing Issue types in an organization](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-types-in-an-organization)
- [GitHub's OpenAPI description, `descriptions/api.github.com/api.github.com.json`](https://github.com/github/rest-api-description)
- [Transferring an issue to another repository](https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/transferring-an-issue-to-another-repository)
- [Deleting an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/deleting-an-issue)
- [`gh api` manual](https://cli.github.com/manual/gh_api)
- `cli/cli` `v2.98.0`: [`pkg/cmd/api/api.go`](https://github.com/cli/cli/blob/v2.98.0/pkg/cmd/api/api.go),
  [`pkg/cmd/api/pagination.go`](https://github.com/cli/cli/blob/v2.98.0/pkg/cmd/api/pagination.go),
  [`pkg/cmdutil/errors.go`](https://github.com/cli/cli/blob/v2.98.0/pkg/cmdutil/errors.go),
  [`internal/ghcmd/cmd.go`](https://github.com/cli/cli/blob/v2.98.0/internal/ghcmd/cmd.go)
- `cli/go-gh` `v2.13.0`: [`pkg/api/cache.go`](https://github.com/cli/go-gh/blob/v2.13.0/pkg/api/cache.go),
  [`pkg/api/http_client.go`](https://github.com/cli/go-gh/blob/v2.13.0/pkg/api/http_client.go),
  [`pkg/config/config.go`](https://github.com/cli/go-gh/blob/v2.13.0/pkg/config/config.go)
- Read-only experiments against `ned2/dashpot` (`R_kgDOUEerrg`) with GitHub CLI 2.98.0 on 2026-09-04, as quoted in each section
- Controlled scratch-Issue, relationship, and Milestone experiments against
  `ned2/dashpot` with GitHub CLI 2.98.0 for #128 on 2026-09-05, with their UTC
  request windows from 2026-09-04 reproduced in §3
