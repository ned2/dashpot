---
status: accepted
date: 2026-09-04
---

# Bound each GitHub refresh by a budget

A refresh of the GitHub Issue Source fetched every Issue of the repository,
one hundred to a page, with the per-command timeout as its only bound. Each
page costs about six GraphQL rate-limit points and, measured against this
repository, two seconds; GitHub allows five thousand points an hour. At the
default fifteen-second period a repository of two thousand Issues spends its
hour's points in about ten minutes, and one of seven hundred outlasts the
period on every tick ([#79](https://github.com/ned2/dashpot/issues/79)).
Failures were read from `gh`'s one-line stderr by substring, although `gh`
writes GitHub's JSON body — with its typed `errors[].type` and `errors[].path`
— to stdout before it, so a missing Issue, a forbidden resource and a rate
limit were told apart by prose GitHub may reword and `gh` may localise.

Every GitHub request now goes through one gateway
([`github.py`](../../src/dashpot/github.py)), which the Issue Source, the repository identity check, and the Pull Requests
pane ([#83](https://github.com/ned2/dashpot/issues/83)) use:

- **A failure is read from its structured signals first.** The JSON body on
  stdout is parsed even when `gh` exited non-zero: a GraphQL error's `type`
  names the code (`NOT_FOUND`, `FORBIDDEN`, `INSUFFICIENT_SCOPES`,
  `RATE_LIMITED`, `UNAUTHORIZED`), its `path` says where, and a REST body's
  `status` does the same. Without a body, the `HTTP <status>` `gh` writes —
  as a suffix after a REST message, as a prefix in its other commands — is
  read wherever it appears; the runner's own failures (no `gh`, a timeout)
  keep their codes; and only then are substrings consulted, with a forbidden
  resource checked before an expired login so the one is never reported as
  the other. A missing Issue is a `github-not-found` at the `issue` path,
  which `find` reads as a miss; a missing node at the query's root is the
  configured repository gone.
- **Every refresh runs under a Refresh Budget** of pages and seconds, each
  checked before the next page, so a refresh overruns by at most one page
  plus the command timeout. The default is twenty-five pages or sixty
  seconds, set at the source rather than by a flag. (Since
  [ADR 0023](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)
  sends batches in flight, the budget counts requests, a hundred and twenty
  of them, checked before each is sent, and a refresh overruns by at most
  the requests in flight; the Diagnostic names the requests.) Nested pagination of an
  Issue's labels, assignees and relationships spends the same budget as the
  Issue pages, and a `find` runs under its own. An overrun is a failed
  refresh with one `github-refresh-budget` Diagnostic naming the pages, the
  time and what was fetched; the last good collection is retained and
  nothing partial is published, which keeps
  [ADR 0002](0002-require-complete-issue-profile-snapshots.md) intact.
- **Every query carries `rateLimit { cost limit remaining resetAt }`** beside
  its data, so the hour's balance is observed on the way. A complete refresh
  that finds fewer than a tenth of the points remaining reports a
  `github-rate-limit-low` warning beside its fresh data; it never refuses to
  refresh for it.
- **Pagination follows a cursor trail** that refuses a missing or repeated
  cursor, so a source can never loop on a cursor GitHub keeps returning.

## Considered options

- **Refuse to refresh while the rate limit is low:** deferred. The token is
  shared with every other tool a person runs, the cost of the next refresh
  is a guess, and a refusal is self-inflicted staleness until the reset; when
  GitHub does refuse, the `RATE_LIMITED` type already yields a stale
  observation naming the reset. Fetching less — an incremental refresh —
  removes the cause and is the next decision under the same Issue.
- **Derive the time budget from the polling period:** rejected. With
  `--refresh-seconds 0` there is no period, and a fifteen-second bound would
  make every repository of a few hundred Issues permanently stale exactly
  where coalescing ([ADR 0020](0020-coalesce-requests-onto-the-observation-in-flight.md))
  had just made a slow refresh land. The time bound catches pathological
  slowness; the page bound is the operative cap.
- **Cache `gh api` responses by time (`--cache`):** rejected, as the
  observation research already argued: a time-based cache hides freshness,
  which the dashboard exists to show.

## Consequences

- A repository too large for the budget is reported stale with a diagnostic
  that says how far the refresh got, rather than silently never landing. The
  budget does not lower the cost of a large repository: twenty-five pages at
  every tick can still spend the hour's points, which is accepted until the
  incremental refresh.
- The linked pull requests beside an Issue remain the first twenty GitHub
  returns, unpaged; they are presentation, outside the complete profile, and
  are documented as such on `IssueActivity`.
- Diagnostic codes are now a documented family in the README's domain
  language rather than strings each adapter chose.
