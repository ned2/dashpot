---
status: amended
date: 2026-09-05
amended-by: 0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md
---

# Run fallback sweeps under their own Refresh Budget

[ADR 0023](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)
made a Reconciliation observe every known Issue by identity, then merge the
delta since the High-Water Mark. When the resulting collection still disagreed
with GitHub's Issue count, it ran the cursor sweep in the same refresh because
an Issue transferred in can retain an old `updatedAt` and have no known Issue
Identity. For a large repository the identity batches, delta, and sweep could
together exceed the sixty-second Refresh Budget. The whole refresh was then
abandoned and repeated the same work one Reconciliation period later.

A count that remains unexplained after the identities, delta, and confirming
probe now separates the two complete observations:

- The identity-based Reconciliation publishes its complete collection with a
  `github-issue-count` warning and marks the fallback sweep due. Nothing from a
  partial sweep is present in that observation.
- The next refresh consumes the due mark before making a request and runs only
  the cursor sweep, under the fresh Refresh Budget every refresh receives. A
  successful sweep atomically replaces the snapshot with its complete
  collection and clears the warning.
- The mark is cleared when the sweep is attempted, not when it completes. If
  the Refresh Budget abandons the sweep, the Issue Source retains its last good
  collection and does not spend every subsequent polling tick on the same
  attempt. After the configured Reconciliation period, identities and the
  delta can mark another fallback sweep due if the count still disagrees.
- A first observation without a valid Snapshot Seed, and a Reconciliation
  without a High-Water Mark, remain direct cursor sweeps. They have no earlier
  complete collection to publish while deferring their work
  ([ADR 0028](0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md)).

## Considered options

- **Keep the fallback in the Reconciliation's refresh:** rejected. It gives the
  only path that needs both algorithms no practical way to complete in a
  repository where each algorithm fits the Refresh Budget separately.
- **Give every Reconciliation a larger budget:** rejected. Most
  Reconciliations fit the existing bound, and the polling period is
  deliberately not a Refresh Budget input
  ([ADR 0021](0021-bound-each-github-refresh-by-a-budget.md)). Deferring only
  the exceptional fallback keeps one predictable bound for every refresh.
- **Spread one sweep's pages across refreshes:** rejected. A refresh is one
  complete observation or a failed one
  ([ADR 0002](0002-require-complete-issue-profile-snapshots.md)); no collection
  may be published partly from the Reconciliation and partly from the sweep.

## Consequences

- A transferred Issue can remain absent for one additional polling period
  after its count first reveals it. The `github-issue-count` warning makes that
  temporary disagreement explicit.
- The identity-based Reconciliation and the fallback sweep each publish
  atomically. Together they may spend more points than one Refresh Budget, but
  neither can cause the other to be abandoned for their combined wall time or
  request count.
- A successful fallback sweep retains its newest observed Pull Request update
  as a candidate. Its required inclusive prefix scan runs on the next refresh,
  under that refresh's own budget, before the candidate settles.
- An abandoned fallback sweep is retried only after another Reconciliation
  period and confirming count disagreement, matching the existing rule for an
  abandoned Reconciliation rather than turning every tick into a sweep.
