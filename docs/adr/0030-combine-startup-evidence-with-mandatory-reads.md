---
status: accepted
date: 2026-09-06
---

# Combine startup evidence with mandatory reads

The GitHub Issue Source will collect startup probe evidence beside a request
it must already make, and will observe a pending Pull Request prefix before
Reconciliation. [Issue 138's measurements](../github-startup-latency-experiments.md)
show repeatable removal of serial requests: the final settled-seed median fell
from 2.79 to 2.31 seconds and pending-candidate startup from 5.30 to 3.33 seconds.
The Snapshot Seed remains untrusted until complete live Reconciliation succeeds.

For a seed without a pending candidate, startup observes every saved identity,
then the inclusive Issue delta. The delta's first page also supplies the live
Issue count, newest Issue timestamp, and newest all-state Pull Request timestamp.
A persisted Issue cursor beyond that live newest timestamp requires another
inclusive delta at the live boundary before publication. An empty live
collection supplies no publishable cursor; the next non-empty observation
starts with a sweep. Publishable marks derive from live evidence, never directly
from persisted values. A newly detected Pull Request change still receives its
ordinary inclusive prefix and affected-Issue observations.

For a seed with a pending candidate, the first Pull Request prefix page supplies
the probe evidence. That evidence bounds both persisted Pull Request cursors
before the scan boundary is chosen. The entire inclusive prefix completes
before identity Reconciliation begins. The identity set contains every seed
Issue plus every current closing target the prefix discovers, so previous
targets and removals are positively re-observed too. New relationship
counterparts absent from the seed are observed by identity. The Issue delta
remains after those identity reads and wins equal-timestamp ties. A complete
scan settles only a repeated live candidate; a future persisted candidate
cannot supply its own confirmation.

Every request, including combined pages, nested continuations, corrected deltas,
and each concurrent identity batch, remains inside one Refresh Budget. A
remaining count disagreement is confirmed by a fresh probe and schedules the
fallback sweep under the next refresh's own budget. A failure leaves startup
unavailable, with no Issue content or new Snapshot Seed published. Normal
Incremental Refresh, explicit/periodic Reconciliation, initial/fallback sweeps,
Repository Anchor validation, source independence, and the snapshot wire
version retain their existing contracts.

## Considered options

- Publishing the seed or skipping live cursor validation violates the trust
  contract and was excluded from the experiments.
- Keeping a separate startup probe and a second affected-Issue batch preserved
  correctness but added avoidable serial round trips. The reordered complete
  identity reads now supply the affected-Issue evidence.
- Increasing prefix width, replacing the transport, overlapping Repository
  Identity validation, starting during composition, and publishing pending
  Project parts did not clear their adoption gates. Their measured opportunities
  and outstanding evidence are recorded in the research note.

## Consequences

For the measured 94-Issue collection, settled startup uses five Issue GraphQL
requests instead of six. A pending two-page prefix uses seven instead of nine,
with four identity batches still bounded at twenty-four Issues and four requests
in flight. Invalid future Issue cursors intentionally keep an extra corrective
round trip. Neither freshness nor complete Issue/relationship evidence is
exchanged for speed.

This amends [ADR 0023](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md),
[ADR 0025](0025-observe-linked-pull-requests-from-pull-request-changes.md), and
[ADR 0028](0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md) for
startup ordering only. The authoritative GraphQL signals in
[ADR 0027](0027-keep-the-graphql-change-probe-authoritative.md) remain authoritative
when collected beside another mandatory request.
