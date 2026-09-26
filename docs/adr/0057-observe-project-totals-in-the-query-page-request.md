---
status: accepted
date: 2026-09-26
---

# Observe Project Totals in the Query Page request

Project Totals were observed by requests of their own. Every GitHub refresh
sent one `DashpotProjectTotals` request per kind beside the two Query Pages,
through two Query Sources kept only for them. That was 2 of the 7 requests a
GitHub refresh sent after
[ADR 0056](0056-refresh-github-queries-on-their-own-period.md), and 4 of the
14 a refresh sent when [#308](https://github.com/ned2/dashpot/issues/308) first measured it
([#305](https://github.com/ned2/dashpot/issues/305)).

Since [ADR 0055](0055-verify-the-query-context-in-the-response-that-carries-it.md),
every Query Page request already selects the Repository node to verify its
context. The open and closed counts are two more `totalCount` fields on that
node, and a query selecting both kinds' counts measured at 1 point, the same
as without them.

## Decision

- **A Query Page request counts its kind's Project Totals.** The Issues page
  selects the Repository's open and closed Issue counts; the Pull Requests
  page selects its open count and its closed and merged count together. The
  counts cover the whole Project whatever the page's query, lifecycle,
  ordering or position.
- **The totals keep their own status.** A Query Source reports the totals as
  soon as the response carries them. A search GitHub refuses (a GraphQL error
  whose path is the `search` field) fails the page but leaves the totals
  fresh, and so does a later part of the page failing, such as a batch of
  Issue Profiles. Any other GraphQL error, or a response that does not verify,
  fails both, and the totals go stale with their last good counts and a
  Diagnostic, as before.
- **The separate totals query retires.** The Query Source protocol's `totals`
  operation, the dashboard's two totals Query Sources and their messages are
  removed. The page runner lands a page and its totals together; the totals
  land even when the navigation rejects a superseded page, because they do not
  depend on what the page asked.
- **The Local Markdown Issue Source counts its totals in the same call.** It
  counts the complete local collection before it interprets the search, so a
  search it refuses still reports them.
- **`issue list` and `pr list` take the totals from the page.** Their JSON
  document keeps its `page` and `totals` keys.

## Consequences

- **Two requests fewer each GitHub refresh.** An open dashboard sends 5
  requests a GitHub refresh instead of 7, and `issue list` and `pr list` each
  send one request fewer. The measured figures are in
  [GitHub rate limits](../github-rate-limits.md#how-dashpot-spends-the-allowance).
- **The totals are as fresh as the page.** No separate cadence needs choosing,
  and a displayed page and its totals come from the same moment.
- **The totals refresh only when a page is queried.** An automatic refresh
  that finds a kind's page query still running asks nothing more of that kind;
  the running query brings the totals.
- **A malformed count fails the page too.** The counts arrive in the page's
  own response, so a response whose counts do not validate is not trusted for
  the page either.
- **[ADR 0033](0033-query-pages-and-independent-issue-resolution.md)'s count
  request is replaced.** Its statement that Project Totals take one count
  request now points here.

## Considered options

- **Observe the totals on a slower cadence** (every Nth refresh, a fixed
  period, or when a page's matching count changes). It adds a scheduling rule
  and lets the counts lag, which the dashboard would then have to show, to save
  fewer points than folding does.
- **Leave them as they are.** After ADR 0056 they cost about 240 points an
  hour, for nothing that folding does not also give.
- **Carry the totals inside the Query Page model.** A Query Page is one
  query's bounded result and never a Project inventory; the totals are
  Project-wide. A pair of the two observations keeps each model's meaning and
  keeps the published `issue list` document unchanged.
