---
status: accepted
date: 2026-09-05
---

# Keep the GraphQL change probe authoritative

[ADR 0022](0022-refresh-github-issues-incrementally-between-reconciliations.md)
deferred using a conditional REST Issues-list request ahead of the GraphQL
change probe. An authenticated `304 Not Modified` does not consume GitHub's
REST primary rate limit, so it appeared able to remove the GraphQL point an
unchanged tick spends. At the default fifteen-second polling period, that is
two hundred and forty of the hourly five thousand GraphQL points.

Research for [#129](https://github.com/ned2/dashpot/issues/129) found that the
validator cannot carry the same evidence as the combined GraphQL probe
([research](../github-api-batching-research.md#issue-129-validator-scope-and-probe-limits)):

- GitHub defines an ETag for the exact requested representation. The
  repository Issues endpoint returns a paginated array without an exact total
  count, and GitHub does not document page 1's validator as changing for every
  change on later pages. A `304` therefore cannot prove that an older Issue was
  not deleted or transferred.
- The REST endpoint mixes Issues and Pull Requests. A changed representation
  may be Pull Request activity alone, so any response other than `304` must
  still lead to the GraphQL probe rather than directly to an Issue delta.
- [ADR 0025](0025-observe-linked-pull-requests-from-pull-request-changes.md)
  added the newest Pull Request update to the same combined GraphQL query. It
  still costs one point, not a second point per tick.
- Live authenticated requests confirmed that `304` left `X-RateLimit-Used`
  unchanged. They also confirmed that a different page has a different ETag
  and that `gh api` reports the successful conditional result as exit 1 with
  `gh: HTTP 304`.

The GitHub Issue Source will keep sending its combined GraphQL change probe on
every Incremental Refresh. A conditional REST page will not gate it. The
GraphQL probe remains the authority for the exact Issue count and the newest
Issue and Pull Request update signals; the High-Water Marks advance only
through the data those signals cause Dashpot to fetch.

## Considered options

- **Gate the GraphQL probe on a page-1 `304`:** rejected. It would replace an
  exact collection count with an undocumented inference about invalidation of
  other pages, delaying some deletion or transfer evidence until
  Reconciliation.
- **Conditionally request every REST page:** rejected. It loses the one-request
  probe shape, introduces a moving-page race under `sort=updated`, and can
  spend many REST requests merely to decide whether to make the authoritative
  GraphQL request.
- **Treat a REST `200` as positive change evidence:** rejected. The represented
  change can be a Pull Request, and REST does not expose the complete Issue
  Profile or Linked Pull Request relationship Dashpot publishes.

## Consequences

- An unchanged tick continues to cost one GraphQL point. The requested
  zero-point optimization is not implemented because GitHub exposes no safe
  repository-wide conditional validator with the probe's evidence.
- Dashpot adds no REST latency, secondary-limit spend, or special parsing of
  `gh api`'s non-zero `304` result to every polling tick.
- The decision can be revisited if GitHub documents repository-wide validator
  invalidation or exposes an exact Issue count in a conditionally validated
  representation.
