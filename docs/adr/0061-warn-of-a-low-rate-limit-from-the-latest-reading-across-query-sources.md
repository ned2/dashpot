---
status: accepted
date: 2026-09-27
---

# Warn of a low rate limit from the latest reading across Query Sources

[ADR 0021](0021-bound-each-github-refresh-by-a-budget.md) had every GitHub
query select `rateLimit { cost limit remaining resetAt }` so a complete
refresh could warn with `github-rate-limit-low` beside its fresh data. Only
Source Enumeration kept that promise. Since
[ADR 0033](0033-query-pages-and-independent-issue-resolution.md) the dashboard
observes through Query Pages and Resolved Issues, and none of their queries
selected the rate limit, so a person got no warning before GitHub refused the
dashboard's queries ([#307](https://github.com/ned2/dashpot/issues/307)).

The dashboard runs one Query Source per query, each behind gateways of its
own. The allowance they draw on is the account's, so a reading from any of
them describes all of them.

## Decision

- **Every query a Query Source sends selects the rate limit.** The context,
  Query Page and Resolved Issues queries carry `RATE_LIMIT_SELECTION` beside
  their data, like the enumeration queries already did; it remains the one
  definition of the selection.
- **The gateway reads the reading from the response that carried it.**
  `graphql_result` returns a `GraphQLResponse` whose `rate_limit` is that
  response's own reading, and both `graphql` and `graphql_result` record it
  as the latest. Each request can therefore be accounted for by its own
  reading rather than by whatever the latest one is.
- **The dashboard's Query Sources share one latest reading.** Every gateway
  behind them records into one `LatestRateLimit`, so the warning reports the
  most recent reading GitHub gave any of them, not the reading of whichever
  source last published. A one-shot command's source holds its own.
- **The warning is the source's, not an observation's.** A Query Source
  reports what it knows about itself through `source_diagnostics`, apart
  from the Diagnostics of the observations it returns: a GitHub source
  reports `github-rate-limit-low` while its latest reading shows fewer than a
  tenth of the hour's points left, naming what remains and when the hour
  resets; a Local Markdown source reports nothing. The page runner lands them
  in the page store after every query answers, failed or not, one line each
  however many sources report it, and the Diagnostics box lists them.
  `issue list` and `pr list` add them to the Diagnostics of the page they
  print.

## Consequences

- **The warning appears before the allowance runs out** and clears once a
  reading shows enough points again, such as the first after the hour
  resets.
- **A failed request keeps the warning.** The warning comes from the last
  reading received, so a refused query does not hide what the account had
  left; a pause that waits for the reset
  ([#306](https://github.com/ned2/dashpot/issues/306)) can use that reading's
  `resetAt`.
- **Nothing is sent to learn the limit.** The selection rides on queries the
  dashboard sends anyway and adds no request of its own; the REST `rate_limit`
  endpoint, which was measured reporting stale GraphQL figures, is never
  read.
- **A warning can outlive its hour while nothing is asked.** With the GitHub
  Refresh Period off, no query is sent, and the last warning stays, naming a
  reset time already past, until `r` or another query brings a new reading.

## Considered options

- **Put the warning in each Query Page's Diagnostics.** Both pages would
  carry it, from readings taken at different moments, so the Diagnostics box
  would show two warnings with different counts, and a failed page would drop
  it just when it matters.
- **Let each source warn from its own gateways' reading.** A source that
  sent nothing recently would report an older figure than one that did.
