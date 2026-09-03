# GitHub API batching and bulk queries for the GitHub Issue Source

Research date: 2026-09-04

This note establishes what GitHub's API offers for batching and bulk queries,
to inform a later incremental-refresh design for
[`GitHubIssuesSource`](../src/dashpot/github_issues.py). It does not decide
the design. Every claim is checked against GitHub's documentation, the live
GraphQL schema (introspected through `gh api graphql`), the `cli/cli` and
`cli/go-gh` source at the installed release, or a read-only experiment
against `ned2/dashpot` (repository node id `R_kgDOUEerrg`; 81 Issues and 33
pull requests at the time, so numbers 1–114 are all in use). Experiments ran
GitHub CLI `2.98.0`. Nothing on GitHub was mutated. Anything the sources do not
settle is marked **unverified**.

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
   local computation exactly. But `updatedAt` is **not** bumped by
   cross-references (Issue or pull request mentions) or by commit references,
   and one observed case shows it is not bumped on the blocker when a blocking
   relationship is added. Since Dashpot's linked pull requests
   (`closedByPullRequestsReferences`) derive from cross-references, a
   `since`-delta cannot see them change. Whether assignment, sub-issue,
   parent, and blocked-by changes bump `updatedAt` could **not** be
   established from this repository's history.
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
| `AssignedEvent`, `BlockedByAddedEvent`, `ParentIssueAddedEvent`, `SubIssueAddedEvent`, `RenamedTitleEvent`, `ReopenedEvent` | **unverified** | every occurrence was followed by a bumping event before `updatedAt`, so neither outcome can be separated |
| `ConnectedEvent`, milestone, issue-type, project events | **unverified** | absent from this repository |

Consequences for a delta: a change to an Issue's linked pull requests
(`closedByPullRequestsReferences`, derived from cross-references) or to the
`blocking` side of a dependency can happen without the Issue entering a
`since` window. Whether a closing-keyword cross-reference
(`willCloseTarget: true`) bumps `updatedAt` is **unverified** (none present).
Whether the blocked side (`blockedBy`) is bumped is unverified, so a
relationship change may be invisible on both sides.

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
| (a) Change probe: `issues(first: 1, orderBy: UPDATED_AT DESC) { totalCount nodes { updatedAt } }` | 1 | 1 | ~0.6 s | any change that does not bump `updatedAt` (cross-references and so linked pull requests; blocker-side dependencies; unverified kinds in §3); a deletion or transfer offset by a creation; a transfer or deletion of an older Issue leaves `updatedAt` unchanged and only moves `totalCount` |
| (a′) REST probe: conditional `GET /repos/{o}/{r}/issues?state=all&sort=updated&per_page=1` | 1 | 0 on `304`, 1 REST request otherwise | ~0.5 s | same gaps; the list ETag also changes on pull request activity, so a `200` is not proof of Issue change; REST and GraphQL limits are separate |
| (b) Delta by `since`: `issues(first: 100, filterBy: {since}, orderBy: UPDATED_AT)` with full fields | ceil(changed/100) | 6 per 100 changed | ~3 s per 100 changed | everything in (a); needs an overlap window (inclusive boundary, clock skew); nested overflow pagination as today; wide-query truncation (§3.4) applies to the page shape |
| (c) Bulk fetch by `nodes(ids:)` of known identities | ceil(n/100) | 6 per 100 (1 per 100 with identity-only fields) | ~3 s per 100 | requires the identities first; a transferred or deleted Issue is a `null` with `NOT_FOUND`, indistinguishable from each other; ids only — the 100-id cap is hard |
| (d) Parallel full sweep by aliased `issue(number:)` | numbers span Issues *and* pull requests, e.g. ~3,000 numbers: 125 batches of 24 (1 point each) or 30 batches of 100 (6 points each) | ~125 or ~180 | bounded by concurrency limits (§6); each batch ~1.2–1.8 s observed at ~21 Issues | needs the current maximum number from a probe; Issues created after that probe are missed; every pull request number is an `errors[]` entry, so every batch exits 1 and stdout/stderr grow with the pull request count; the same truncation risk as (b) above 60 Issues per query (§3.4); a missing number cannot be told apart from a pull request |

Facts common to every delta shape: a `since` or `nodes` result lists only
Issues that still exist, so absence is never established by a delta (compare
[ADR 0002](adr/0002-require-complete-issue-profile-snapshots.md)); the
relationship facts Dashpot collects live on both ends of a relationship, and
the observed evidence shows at least one end (the blocker's `blocking`) does
not bump `updatedAt`; and the wide-query truncation in §3.4 is invisible to
`hasNextPage`, so any batch shape above about 40 Issues per query needs its
own completeness check before it can be trusted as a fresh observation.

## Experiment artefacts

Commands and raw outputs referenced above were captured in the session's
scratch directory: `aliased.graphql`, `aliased.out`, `aliased.err`,
`nodes_missing.out`, `intro1.json`–`intro3.json`, `since.json`,
`rest_issues.txt`, `rest_304.txt`, `costs.py`, `nested_check.py`,
`complete_timelines.json`, `aliased_timelines.json`, and the downloaded
documentation text under `docs/`. The queries are reproducible from the
descriptions in each section; all are read-only.

## Sources

- [Rate limits and query limits for the GraphQL API](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [Using pagination in the GraphQL API](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api)
- [Using global node IDs](https://docs.github.com/en/graphql/guides/using-global-node-ids)
- [GraphQL reference: queries](https://docs.github.com/en/graphql/reference/queries),
  [input objects (`IssueFilters`)](https://docs.github.com/en/graphql/reference/input-objects#issuefilters),
  and the live schema introspected with `gh api graphql` (`__type(name: "Query" | "IssueFilters" | "RateLimit" | "Repository" | "Issue" | "IssueConnection")`)
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Best practices for using the REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- [REST API endpoints for issues: List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues),
  [sub-issues](https://docs.github.com/en/rest/issues/sub-issues),
  [issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies)
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
