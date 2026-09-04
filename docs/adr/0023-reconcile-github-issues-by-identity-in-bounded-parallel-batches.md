---
status: amended
date: 2026-09-04
amended-by: 0026-run-fallback-sweeps-under-their-own-refresh-budget.md
---

# Reconcile GitHub Issues by identity in bounded parallel batches

[ADR 0022](0022-refresh-github-issues-incrementally-between-reconciliations.md)
made every tick between Reconciliations cheap and left the Reconciliation
itself as the cursor sweep the source has always run: every Issue of the
repository listed in order of creation, six points and about three seconds
per hundred Issues, one page after another. A repository of two thousand
Issues therefore still spent a hundred and twenty points and a minute every
five minutes — most of the hour's cost — on observing Issues it already
held, and a Reconciliation the Refresh Budget abandoned stayed abandoned
until the same sweep was retried a period later. The research
([`docs/github-api-batching-research.md`](../github-api-batching-research.md))
established the alternative: a `nodes(ids:)` lookup answers up to
twenty-four complete Issue nodes for one point, answers each identity
independently — a missing one as `null` beside a positional `NOT_FOUND`, a
node that is no longer an Issue by its type — and four such lookups in
flight answer in under two seconds where the same Issues took more than
three in sequence. GitHub's secondary limits, not its points, bound the
parallelism: a hundred concurrent requests, sixty seconds of GraphQL CPU
time per minute, and the advice to avoid concurrent requests.

A Reconciliation is now an observation of every Issue the source already
knows, by identity, plus what its delta and count reveal:

- **Every known identity in batches of twenty-four.** The snapshot's
  identities are asked of `nodes(ids:)` in batches of twenty-four, in waves
  of at most four batches in flight, each batch one point and one request of
  the Refresh Budget, taken before its wave is sent. A `null`, a node that
  is not an Issue, or another repository's Issue is the positive evidence
  that removes an Issue from the snapshot; the rest are observed afresh,
  including the facts GitHub does not date — a linked pull request, the
  blocker's side of a dependency, a label's colour — which is what the
  Reconciliation exists to see.
- **Then the delta and the count.** The Issues updated since the old
  High-Water Mark are fetched as on any tick, so an Issue created since the
  last observation joins the snapshot, and the other end of every changed
  relationship with it. The probe's count is then checked against the
  merged collection, and once more against a fresh probe when it disagrees,
  since an Issue created or deleted while the identities were in flight
  moves the count after the probe. An Issue transferred in carries its old
  `updatedAt` and no known identity, so it appears in neither the
  identities nor the delta, and only when the count still disagrees does
  the Reconciliation fall back to the cursor sweep. The first observation of
  a run, and any Reconciliation without a High-Water Mark to delta from, is
  that sweep.
- **Four in flight, never more.** The gateway sends a batch of requests
  through a pool of four threads and returns the answers in the order asked;
  the first failure fails the batch and the refresh, and nothing partial is
  published. Four is well under every secondary limit, in step with the
  advice to avoid concurrency, and enough that a Reconciliation of two
  thousand Issues completes in the Refresh Budget's sixty seconds
  (eighty-four requests in twenty-one waves of about two seconds) where the
  sweep did not.
- **The Refresh Budget counts requests.** With batches in flight, "pages"
  no longer names what the budget bounds: it is a number of requests (a
  hundred and twenty) and a wall-clock duration (sixty seconds), each
  checked before the next request is sent. The `github-refresh-budget`
  Diagnostic names the requests, the time and what was fetched, as before.

## Considered options

- **Keep the cursor sweep as the Reconciliation:** rejected. It observes
  in order of creation, so a repository the budget cannot cover in full is
  never reconciled at all, and it spends the hour's points on Issues already
  held. It remains the fallback when a count disagrees for a reason no
  identity or delta explains, and the way a run starts.
- **A sweep by aliased `issue(number:)` in parallel batches:** rejected in
  [ADR 0022](0022-refresh-github-issues-incrementally-between-reconciliations.md);
  identities carry no such ambiguity with pull requests.
- **Larger batches or more in flight:** rejected. Nested connections
  truncate silently in queries much wider than twenty-four Issues, and the
  CPU-time limit is estimated by response time, so eight batches in flight
  would spend the minute's allowance in a Reconciliation of moderate size.
  The bound is a constant at the gateway, not a setting.
- **Reconciling in the background across ticks:** rejected. A refresh is
  one complete observation or a failed one
  ([ADR 0002](0002-require-complete-issue-profile-snapshots.md)); spreading
  it across ticks would publish a collection that is partly this period's
  and partly the last's, and the coordinator's ticket
  ([ADR 0020](0020-coalesce-requests-onto-the-observation-in-flight.md))
  already keeps one observation in flight per Project.

## Consequences

- A Reconciliation of two thousand Issues costs about eighty-six points
  and completes in a budget; the hour's cost for such a repository falls
  from about seventeen hundred points to about thirteen hundred, and for a
  repository of a few hundred Issues to a few hundred points.
- A Reconciliation can now remove an Issue only through what its identities
  and the sweep say, and it still cannot see an Issue transferred in without
  a bump except by count. When the count disagrees for that reason the
  fallback sweep runs after the identities and the delta, so that
  Reconciliation costs both; in a repository large enough that the two
  together outrun the sixty seconds it is abandoned and retried a period
  later, and the transferred Issue is seen once it is next updated, or by
  a Reconciliation that fits. A count disagreement found on an ordinary
  tick reconciles at once and reuses the delta already fetched; when an
  identity observation and the delta contain the same Issue, the newer
  `updatedAt` wins and a tie keeps the later identity observation.
- Requests in flight share one `gh` credential and one command runner; the
  runner is invoked from a pool of threads, so a runner passed to the
  gateway must be safe to call concurrently. The test fakes route identity
  lookups by the identities asked rather than answering in turn.
- The retry of an abandoned Reconciliation and the `github-issue-count`
  and `github-reconciliation-overdue` warnings keep their meaning; a
  Reconciliation abandoned for its budget is now one whose identities and
  delta together outran a hundred and twenty requests or sixty seconds.
