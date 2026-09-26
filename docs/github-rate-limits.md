---
status: living
date: 2026-09-26
---

# GitHub rate limits

A GitHub-backed Project observes GitHub continuously. An open dashboard asks
for its Query Pages, Project Totals and Resolved Issues on every automatic
refresh, whether or not anything changed. GitHub meters those requests
against an hourly allowance that belongs to the person, not to Dashpot. Every
dashboard, every agent running `gh`, and every other tool acting as the same
user draws on it. When it runs out, Dashpot's GitHub observations go stale
until the hour resets. This document records the limits for each way of
authenticating, how Dashpot spends them, and how to stay inside them.

GitHub notes that "the formula for calculating points and the rate limit are
subject to change". The figures here were checked against GitHub's
documentation on the date above. The evidence behind the cost figures is in
the [GitHub API batching research](github-api-batching-research.md#1-graphql-rate-limits-and-query-limits).

## How Dashpot authenticates

Dashpot keeps no credential. It asks GitHub every question by running
`gh api`, so it acts as whichever account the GitHub CLI resolves: a
`GH_TOKEN` or `GITHUB_TOKEN` in the environment when one is set, otherwise the
login stored by `gh auth login`. `GH_HOST` selects the GitHub host. Check the
account in use with `gh auth status`; the rate limit Dashpot works within is
that account's.

Almost everything Dashpot asks goes through GraphQL. Query Pages, Project
Totals, Resolved Issues, Issue Hint resolution and Source Enumeration are all
GraphQL queries. The one REST request resolves a Repository Anchor's GitHub
identity, once per anchor, when `dashpot init` runs or a Workspace is
resolved. The GraphQL allowance is therefore the limit that matters.

## Primary limits by authentication method

| Authentication | GraphQL points per hour | REST requests per hour |
| --- | --- | --- |
| None | GraphQL requires authentication | 60, per originating IP address |
| A user: `gh auth login`, a classic or fine-grained personal access token | 5,000 | 5,000 |
| A user in a GitHub Enterprise Cloud context | 10,000 | 15,000 |
| A GitHub App installation | 5,000, plus 50 for each repository and each user beyond 20, up to 12,500 | The same scaling |
| A GitHub App installation on GitHub Enterprise Cloud | 10,000 | 15,000 |
| `GITHUB_TOKEN` in GitHub Actions | 1,000 per repository | 1,000 per repository |
| `GITHUB_TOKEN` for an enterprise account's resources | 15,000 per repository | 15,000 per repository |

What the table implies for Dashpot:

- **Plan tier does not matter.** Free, Pro and Team personal accounts have the
  same limits. Only GitHub Enterprise Cloud raises a user's allowance.
- **A user's allowance is shared.** GitHub counts requests from all of a
  user's tokens and from apps acting on their behalf against the same 5,000
  points. A second token does not add capacity.
- **A personal account running Dashpot has 5,000 GraphQL points an hour.**
  That covers `gh auth login` and any personal access token.
- **Search is paid in GraphQL points.** REST search has its own per-minute
  limits, but Dashpot's Query Pages use GraphQL `search`, which draws on the
  GraphQL allowance instead.

## Secondary limits

GitHub also enforces limits that apply per minute rather than per hour, and
that no rate-limit query reports:

- No more than 100 concurrent requests, shared by REST and GraphQL.
- No more than 2,000 GraphQL requests a minute (a query costs one secondary
  point, whatever its primary cost), and 900 REST points a minute.
- No more than 60 seconds of GraphQL server CPU time in any 60 seconds.
- Limits GitHub does not disclose, which it may apply at any time.

Dashpot runs at most five queries at once, one per Query Source, plus up to
four during Source Enumeration. Its per-minute request count is far below
2,000. Secondary limits become a risk mainly when requests continue after a
refusal: GitHub asks clients to wait for `retry-after`, otherwise until
`x-ratelimit-reset`, otherwise at least a minute, backing off exponentially.

## How Dashpot spends the allowance

Every query below costs one GraphQL point, except one page of Source
Enumeration. Request count, not query shape, sets the spend.

| Operation | Requests |
| --- | --- |
| Issues Query Page | One search, which also counts the Issues' Project Totals, and one batch per 24 Issues on the page: 4 for a full page of 50 |
| Pull Requests Query Page | One search, which also counts the Pull Requests' Project Totals: 1 |
| Resolved Issues | One batch per 24 identities |
| Repository/principal context, on its own | Once for the first Query Page a source asks for, and before each continuation (a page after the first) |
| Issue Hint resolution (`work start`, `worktree create`, `issue show`) | 1 |
| `issue list` or `pr list` | One Query Page, which counts its Project Totals |
| Source Enumeration (`dashpot --json`) | 6 points per 100 Issues plus the Pull Request pages, bounded by the Refresh Budget |
| Lifecycle hooks, `work show`, `work stop`, local observation | None |

GitHub queries refresh on their own Refresh Period, 60 seconds by default,
while local observation keeps refreshing every 15 seconds and costs nothing
([ADR 0056](adr/0056-refresh-github-queries-on-their-own-period.md)). One
automatic GitHub refresh re-queries both Query Pages, each counting its kind's
Project Totals in the same request
([ADR 0057](adr/0057-observe-project-totals-in-the-query-page-request.md)),
and resolves the Issues that Agent Runs are bound to (plus the selected
Issue's relationships). Between GitHub refreshes, the bound and selected
Issues are resolved again only when the set of them changes, as when an Agent
Run starts or changes Issue work, or an opened Issue's relationships arrive.
Each request verifies the Repository and principal in its own response
([ADR 0055](adr/0055-verify-the-query-context-in-the-response-that-carries-it.md)),
so a refresh sends no separate context request.

On 2026-09-26 this Repository had 33 open Issues. Over four minutes, every
GitHub refresh sent 5 requests: 2 Query Pages, each counting its Project
Totals, the 2 Issue batches that complete the Issues page, and 1 Resolved
Issues batch. The local refreshes between them sent none. That is about 5 to 7
points a minute, depending on how many Issues the page and the bound Issues
span. One open dashboard spends roughly 300 to 420 points an hour, under a
tenth of a personal account's 5,000. Before ADR 0057, separate Project Totals
requests made it 7 a refresh, 420 to 540 an hour; before ADR 0056, the
15-second period spent 1,900 to 2,400.

[#308](https://github.com/ned2/dashpot/issues/308) tracks bringing an open
dashboard well inside the allowance; update this section as its sub-issues
land.

## Staying inside the limit

- **Keep one dashboard open.** Dashboards do not share observations, so each
  one costs the full amount. Close a dashboard left running in another
  terminal.
- **Lengthen the GitHub Refresh Period.** GitHub queries refresh on their own
  period, 60 seconds by default, while Worktrees and Agent Sessions keep
  refreshing every 15 seconds
  ([ADR 0056](adr/0056-refresh-github-queries-on-their-own-period.md)). Set
  `github_refresh_seconds` in the
  [machine-local settings](installation.md#machine-local-settings), or pass
  `--github-refresh-seconds` for one run: 120 spends half the default, and 0
  stops automatic GitHub refresh, while `r` still refreshes on demand.
- **Count the other consumers.** An agent running `gh` in a loop, or `gh pr
  checks --watch`, spends the same allowance as the dashboard.
- **Read the allowance from GraphQL itself:**

  ```bash
  gh api graphql -f query='{ rateLimit { limit used remaining resetAt } }'
  ```

  On 2026-09-26 the `graphql` entry of `gh api rate_limit` reported 96 points
  used, while the query above and the `x-ratelimit-*` response headers
  reported 1,016. Trust the figure a GraphQL response carries.

## When the allowance runs out

GitHub refuses further GraphQL queries until the hour's reset. Dashpot keeps
each Query Page's last good observation and shows it as stale, with a
`github-rate-limit` Diagnostic; a page it never observed is unavailable.
Project Totals and Resolved Issues degrade the same way. Worktrees, Branches
and Agent Sessions are local observations and keep refreshing.

Two gaps make this worse today. The dashboard keeps querying at its refresh
period while refused ([#306](https://github.com/ned2/dashpot/issues/306)), and
its queries do not read GitHub's remaining allowance, so the
`github-rate-limit-low` warning never appears before the allowance runs out
([#307](https://github.com/ned2/dashpot/issues/307)).

## Sources

- [Rate limits and query limits for the GraphQL API](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [ADR 0033](adr/0033-query-pages-and-independent-issue-resolution.md) for the
  Query Page, Project Totals and Resolved Issue request arithmetic
