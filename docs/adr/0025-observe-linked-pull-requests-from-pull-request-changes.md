---
status: accepted
date: 2026-09-05
---

# Observe Linked Pull Requests from Pull Request changes

The GitHub Issue Source's Incremental Refresh cannot see a Linked Pull Request
appear, disappear, close, or merge because none of those changes bumps the
Issue's `updatedAt`. Reconciliation closes the gap, but can leave the fact a
polling interval to five minutes behind. The repository-wide Pull Request
observation cannot supply the missing evidence: it is an independently
scheduled, complete collection of active Pull Requests with its own failure
state, while an Issue's engagement includes closed and merged Linked Pull
Requests.

Live research for
[#123](https://github.com/ned2/dashpot/issues/123) established the available
change signal. Adding or removing a body-derived closing reference, and
closing the linked Pull Request, bumped the Pull Request's `updatedAt` without
bumping the Issue. `Repository.pullRequests` can be ordered by `UPDATED_AT`
and cursor-paged, but has no `since` or other time filter. Its derived
`closingIssuesReferences` connection lagged the body and timestamp changes by
7–9 seconds in the controlled experiment, and GitHub documents neither an
indexing bound nor the tie order of equal timestamps
([research](../github-api-batching-research.md#pull-request-refresh-has-ordering-but-no-server-side-delta)).

The GitHub Issue Source will therefore extend its existing snapshot and
Incremental Refresh:

- The one-point Issue change probe also asks for the newest Pull Request
  `updatedAt` across open, closed, and merged Pull Requests. One combined
  GraphQL request remains sufficient on an unchanged tick.
- The snapshot keeps a separate Pull Request High-Water Mark. When the probe
  advances beyond it, the source scans Pull Requests newest-first in pages of
  twenty-four until it crosses the inclusive mark. Every page containing the
  boundary timestamp is read; no undocumented secondary order is assumed.
- The source re-observes by Issue identity every current closing target of a
  changed Pull Request and every Issue whose previous activity listed that
  Pull Request. Additions, removals, and state changes therefore update only
  through a complete Issue node. Absence from the Pull Request scan never
  removes a Linked Pull Request.
- A candidate Pull Request mark is scanned on two consecutive ticks before it
  is settled. The second scan lets the empirically delayed derived connection
  catch up without adding steady-state requests. A newer candidate restarts
  that confirmation. This reduces the observed indexing race; it cannot turn
  GitHub's undocumented eventual consistency into a guarantee.
- The initial sweep and fallback sweep ask for the Pull Request probe beside
  every Issue page and retain the newest answer. Their complete Issue nodes
  establish the Linked Pull Request activity; later Pull Request changes use
  the separate mark.

The repository-wide Pull Request Source remains independent. Combining it
with the GitHub Issue Source would couple two scheduled observations, their
Refresh Budgets and last-good states, and would make one source's failure
degrade the other. It may adopt the same prefix-scan mechanism separately if
its full active-collection sweep becomes material.

## Considered options

- **Wait for Reconciliation:** rejected. It leaves the dashboard's landing
  signal behind for up to five minutes despite a one-point change signal.
- **Use `pullRequests(filterBy: {since})`:** unavailable. Live schema
  introspection found no time-bound argument.
- **Advance the mark after the first prefix scan:** rejected. The controlled
  mutation responses carried the new `updatedAt` with the old derived
  connection; settling that read could hide the eventual link indefinitely.
- **Parse closing keywords from the Pull Request body:** rejected. GitHub's
  derived connection, not Dashpot's imitation of its syntax and repository
  rules, is the authority.
- **Reconcile on any Pull Request change:** rejected. It finds both ends but
  turns a small change into a full Issue collection.

## Consequences

- An unchanged Incremental Refresh still uses one combined probe request. A
  Pull Request change adds a newest-first prefix scan and bounded Issue
  identity batches on two ticks; a connection beyond one hundred closing
  targets is paged under the same Refresh Budget.
- A Linked Pull Request addition, removal, close, or merge that GitHub exposes
  through the changed Pull Request is normally observed by the next two
  ticks, without waiting for Reconciliation. The Issue-side connection is
  completed for relationship evidence while the published activity remains
  the lowest-numbered twenty plus an unlisted count. No relationship is
  removed without the positive evidence of a complete Issue identity answer.
- Equal-second changes beyond the settled mark remain indistinguishable to a
  timestamp probe, as they are for Issue changes. The two-scan confirmation
  covers observed indexing lag, not an unbounded delay. Both limitations stay
  among the Reconciliation blind spots and in its overdue Diagnostic.
- The Pull Request prefix is not an exact delta and may grow with a burst of
  recent activity or a large equal-timestamp boundary. The Refresh Budget
  abandons the whole observation rather than publishing partial Issue
  activity.
