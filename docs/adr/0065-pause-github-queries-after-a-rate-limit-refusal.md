---
status: accepted
date: 2026-10-01
---

# Pause GitHub queries after a rate limit refusal

When GitHub refused a query for its rate limit, the dashboard kept asking on
every GitHub tick: about five refused requests a minute until the hour
reset. GitHub asks clients not to. Repeated requests while rate-limited can
trigger a secondary limit, which lasts beyond the primary reset
([#306](https://github.com/ned2/dashpot/issues/306)). The refusal was already
classified as `github-rate-limit` and shown as a stale observation, but
nothing held the next request back.

The dashboard's Query Sources each ask GitHub through gateways of their own.
Since [ADR 0061](0061-warn-of-a-low-rate-limit-from-the-latest-reading-across-query-sources.md)
every one of those gateways records into one shared `LatestRateLimit`,
because the allowance is the account's, not one gateway's.

## Decision

- **A refusal pauses every gateway that shares the rate limit.** When
  GitHub refuses a GraphQL request with `github-rate-limit`, the shared
  `LatestRateLimit` starts a Rate Limit Pause. Until it ends, a gateway
  sharing it raises `github-rate-limit` for a GraphQL request without
  running `gh`: the request is held. A held request is not a
  `github.request` span, so it spends nothing and counts as no request.
  REST requests are not held: they draw on a separate allowance, and the
  only one Dashpot sends reads a GitHub repository's identity, at `init` and
  when a dashboard or workspace command first observes a Project.
- **The pause lasts until GitHub's reset, when the points explain the
  refusal.** A refused request carries no `data`, so it has no reading of
  its own. A refusal of the primary limit (the hour's points) waits until
  the `resetAt` of the latest reading when that reading showed fewer than a
  tenth of the hour's points left, the `github-rate-limit-low` threshold,
  and the reset is still ahead. Response headers are deliberately unused:
  `gh api` shows them only with `--include`, so `retry-after` and
  `x-ratelimit-reset` are not read.
- **Otherwise it backs off.** A secondary limit's refusal, named by
  `secondary` or `abuse detection` in GitHub's message, or a primary
  refusal the latest reading does not explain, waits one minute. Each further refusal in a
  row doubles the wait, up to an hour. The first request that GitHub
  answers resets the count. A request sent before the pause started, and
  answered or refused after it, neither extends the pause nor resets the
  count.
- **A manual refresh tries once.** `r` lifts the pause: exactly one
  GraphQL request, the first any Query Source sends after the press, goes to
  GitHub, and every other stays held. If GitHub answers it, the pause ends.
  If GitHub refuses it, the pause starts again, and the count of refusals in
  a row is kept, so a secondary limit's backoff keeps doubling. If it fails
  some other way, the pause stays in force, no longer lifted. The timers are not changed: a GitHub tick during a pause
  asks its sources as usual, and their held requests fail at once.
- **Local observation is unaffected.** Worktrees, Branches, Agent Sessions
  and Agent Runs do not go through the gateway.
- **The pause shows in three places.**
  - A GitHub Query Source reports `github-rate-limit-paused` in its
    `source_diagnostics`, beside `github-rate-limit-low`. It is one warning
    line in the Diagnostics box, naming when queries resume and that a
    manual refresh tries once. Each held observation adds its own
    `github-rate-limit` line, as a refused one does.
  - The gateway records a standalone `rate_limit_pause.changed` Runtime
    Event at `standard`: `started` by the refused request, `lapsed` by the
    first request admitted after the pause's due time, and `lifted` by a
    manual refresh's attempt that GitHub answered. Each carries the limit
    that refused (`primary` or `secondary`) and when the pause was due to
    end.
  - Runtime Stats leads its GitHub allowance section with the pause while
    one is in force.

## Consequences

- **A rate-limited dashboard sends nothing until the reset.** After the
  one refused request, a GitHub tick costs no request until the pause
  lapses or someone presses `r`. That means no refusals for GitHub to count
  toward a secondary limit.
- **Held observations read like refused ones.** A held Query Page, Project
  Totals or Resolved Issue keeps its last good observation as stale with a
  `github-rate-limit` Diagnostic whose message says the query was not sent.
  No new failure path was needed.
- **The pause is the process's, not the account's.** Two dashboards pause
  independently, and an agent's `gh` is never held. A one-shot command
  holds its own `LatestRateLimit`, so a refusal during a Source Enumeration
  stops that command's remaining requests at once.
- **A pause can outlast its limit.** If other consumers free no points, or
  GitHub resets early, queries still wait for the time recorded. `r` is the
  way out.
- **The pause ends when a request is admitted, not at its deadline.** Its
  Diagnostic clears on the first Query Source answer after the pause ends,
  so for up to one GitHub Refresh Period it can name a time already past.
  Its `lapsed` event is recorded by the request it lets through.
- **The pause follows the wall clock.** Its due time is a UTC instant, like
  the reset it waits for, so stepping the system clock shortens or
  lengthens it.

## Considered options

- **Stop the GitHub-query timer during a pause.** The timer would then
  need to know every way a pause ends, and a Resolved Issues request made
  outside a tick would still reach GitHub. Holding at the gateway catches
  every request, whatever asked for it.
- **Refuse a manual refresh during a pause.** This is safer for the
  allowance, but it leaves no way to find out whether the limit has lifted
  early. It also gives no way to recover a pause set from a stale reading.
- **Read `retry-after` and `x-ratelimit-reset` from the response
  headers.** That needs `gh api --include` on every request and header
  parsing ahead of the JSON body. The body's `rateLimit` reading already
  names the primary reset, and GitHub's documented backoff covers the rest.
- **Make the pause part of the account's state across processes.** Sharing
  observations between dashboards is the larger question
  [#308](https://github.com/ned2/dashpot/issues/308) leaves open. The pause
  follows the dashboard's own caches.
