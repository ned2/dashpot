---
status: amended
date: 2026-09-04
amended-by: 0025-observe-linked-pull-requests-from-pull-request-changes.md
---

# Refresh GitHub Issues incrementally between Reconciliations

Every refresh of the GitHub Issue Source observed every Issue of the
repository: six rate-limit points and about three seconds per hundred Issues,
so a repository of two thousand Issues spent a hundred and twenty points and a
minute on every tick and its hour's five thousand points in ten minutes. The
Refresh Budget ([ADR 0021](0021-bound-each-github-refresh-by-a-budget.md))
made that failure visible; it did not lower the cost, and GitHub offers no
conditional GraphQL fetch. The research behind this decision
([`docs/github-api-batching-research.md`](../github-api-batching-research.md))
established what an incremental refresh can and cannot see:

- `issues(filterBy: {since})` lists exactly the Issues whose `updatedAt` is
  at or after `since`, inclusive; a close, a comment, a label, a body edit
  bump `updatedAt`, and a new Issue starts at its creation. A batch of up to
  twenty-four complete Issue nodes — a since-page or a `nodes(ids:)` lookup —
  costs one point, and a `nodes(ids:)` lookup answers each identity
  independently, a missing one as `null` beside a positional `NOT_FOUND`.
- `updatedAt` is not bumped by a cross-reference (so not by a linked pull
  request appearing or changing state), by a commit reference, or on the
  blocker when a `blocking` edge is added. Assignment and milestone assignment
  and removal bump the Issue; milestone assignment and removal also bump the
  milestone. Adding or removing a parent/sub-Issue relationship bumps neither
  Issue. Issue-type changes could not be exercised in this user-owned
  repository, where GitHub exposes no Issue Types; a deleted or transferred
  Issue leaves every `since` window without trace; and nested connections
  truncate silently in queries wider than about forty Issues.

The GitHub Issue Source now keeps the collection it last observed as a
snapshot by Issue identity and assembles each fresh observation from it:

- **A change probe every tick.** One query — the newest `updatedAt` and the
  Issue count, plus the newest Pull Request `updatedAt` since
  [ADR 0025](0025-observe-linked-pull-requests-from-pull-request-changes.md),
  one point, under a second — decides whether anything is to be fetched. If
  neither mark advances and the Issue count is unchanged, the snapshot is the
  observation.
- **A delta since the high-water mark.** Otherwise the Issues updated at or
  after the mark are fetched in pages of twenty-four, oldest change first,
  merged by identity, and the mark advances to the newest `updatedAt` seen.
  The inclusive boundary observes the Issue at the mark again; that overlap is
  what makes the boundary safe without any clock arithmetic.
- **The other end of every changed relationship.** A relationship is observed
  at both ends and a change may bump only one, so the counterparts a delta
  added or removed are observed by identity in the same refresh, and both
  ends land together.
- **A Reconciliation** — every Issue observed afresh by the cursor sweep
  (by identity since
  [ADR 0023](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md),
  which keeps the sweep as the fallback and the first observation) —
  runs when the Project's configured period (five minutes by default) has
  passed since the last one was attempted, when a person presses `r`, and
  whenever the merged count
  disagrees with the probe's, which is the only trace a deletion or transfer
  leaves. An Issue leaves the snapshot only on such positive evidence: a
  Reconciliation that no longer lists it, or an identity answered `null`, as
  a node that is not an Issue, or as another repository's Issue. Absence
  from a delta never removes anything,
  which keeps [ADR 0002](0002-require-complete-issue-profile-snapshots.md)'s
  guarantee that nothing partially fetched masquerades as a deletion.
- **The request rides the ticket.** `r` requests its observations with a
  Reconciliation, a timer tick without, and a press coalesced onto an
  observation in flight ([ADR 0020](0020-coalesce-requests-onto-the-observation-in-flight.md))
  reruns as the Reconciliation it asked for.

## Considered options

- **A REST conditional probe (`304 Not Modified` costs nothing):** deferred.
  The GraphQL probe costs one point a tick, two hundred and forty an hour;
  the REST list's ETag also moves on pull request activity and lives on a
  separate limit. Worth revisiting only if the probe's cost ever matters.
- **A full sweep by aliased `issue(number:)` in parallel batches:**
  rejected. Issue numbers are shared with pull requests, so every batch
  carries a `NOT_FOUND` per pull request and a missing Issue cannot be told
  from one. A Reconciliation by `nodes(ids:)` over the snapshot's identities,
  in batches of twenty-four with a bounded number in flight, is decided in
  [ADR 0023](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md);
  at the time of this decision the Reconciliation was the sweep the source
  has always run.
- **Persisting the snapshot across runs:** rejected for now. A run starts
  with a sweep, as it always has; the saving is on every tick after it.
- **Reporting an incremental observation as something other than fresh:**
  rejected. The snapshot is complete except for the enumerated blind spots,
  each closed by the next Reconciliation; an observation whose
  Reconciliation is more than two periods overdue carries a
  `github-reconciliation-overdue` warning naming the age and the facts that
  may lag, rather than being reported stale while every probe succeeds.

## Consequences

- An unchanged repository costs one point and under a second a tick, whatever
  its size; a tick with a handful of changes costs a probe, a delta page and
  at most a batch of counterparts. A repository of two thousand Issues spends
  about seventeen hundred points an hour at the default periods — twelve
  sweeps of a hundred and twenty points and two hundred and forty probes —
  instead of exhausting the limit.
- The blind spots are enumerated, and each is closed by the next
  Reconciliation, up to the configured period late, or by `r` on demand: a
  Linked Pull
  Request relationship whose derived connection remains unindexed across
  both confirming scans; a
  blocker-side dependency change; a parent/sub-Issue
  relationship change; a deletion or transfer whose Issue-count change is
  offset by another collection change in the same window; an update in the
  same second as the High-Water Mark that GitHub's one-second `updatedAt`
  cannot order after it; and a fact GitHub does not date on the Issue — a
  label's colour, a milestone or Issue type renamed — on an Issue that was
  not itself updated. Issue-type changes remain conservatively
  covered because this repository cannot exercise it. Ordinary Linked Pull
  Request changes use their own change mark and Issue identity observations
  ([ADR 0025](0025-observe-linked-pull-requests-from-pull-request-changes.md));
  the repository-wide Pull Requests pane remains an independent observation
  with its own last-good state.
- A Reconciliation the budget abandons is retried a period later while the
  ticks between keep refreshing incrementally, so a large repository is
  stale for one tick in the configured period rather than on every tick; the
  overdue
  warning says when that has gone on too long. A count disagreement found
  after such a failure is reported beside the fresh snapshot as a
  `github-issue-count` warning rather than sweeping again on every tick.
- Issue Profiles are published ordered by Issue Number rather than by the
  sweep's creation order, since a merged snapshot has no page order.
