---
status: amended
date: 2026-08-31
amended-by: 0017, 0018
---

# Observe Branch integration by commit reachability

The Branches pane already reports how a local Branch relates to its upstream,
but upstream synchronization does not answer whether the Branch can be cleaned
up. A Branch may have no upstream because it was never pushed, because its
remote ref was deleted after integration, or because its commits landed on a
different Branch. Calling every local Branch without an upstream "unpushed"
therefore turns an absent configuration into an unsupported conclusion.

Dashpot observes a separate Integration Branch: `origin/HEAD`, else the unique
local `main` or `master`, using the same selection rule as Issue Worktree base
resolution. For each local Branch it counts commits not reachable from that
Integration Branch. Zero is exact evidence that deleting the Branch ref would
not make those commits unreachable from the Integration Branch; a positive
count is retained work. Dashpot never fetches, so a Remote-Tracking Integration
Branch is qualified by the pane's existing remote-fetch age.

The pane keeps synchronization and integration separate:

- `LOCAL` and `REMOTE` show whether a ref exists in each namespace. A remote
  check means at least one Remote-Tracking Branch exists; every remote name
  remains present in the observed model and headless JSON.
- `UPSTREAM` reports `=` in sync, ahead/behind counts, `∅` no configured
  upstream, or `✗` upstream gone. It makes no claim about publication or
  integration.
- `INTEGRATED` reports `⊆` when all commits are reachable, `↑N` for the exact
  number that are not, `⊘` when no comparison is available, and `-` when the
  row has no local ref (amended by
  [ADR 0018](0018-assess-remote-tracking-branch-integration.md): a
  remote-only row now reports its Remote-Tracking Branches' result, or `⊘`
  when they disagree).

The Worktrees `PATH` cell also stops shortening paths to a fixed character
limit. Home-directory abbreviation remains presentation rather than data loss;
when the full rendered table is wider than the pane, its existing horizontal
scrolling exposes it.

## Considered options

- **Use upstream ahead/behind:** rejected because it describes transport
  configuration, not whether commits landed on the Integration Branch.
- **Treat presence on any remote as integrated:** rejected because publication
  makes commits recoverable but says nothing about whether work is complete.
- **Recognise squash merges and cherry-picks by patch identity:** deferred as a
  weaker review hint. Patch equivalence cannot provide the conservative commit
  preservation guarantee of reachability, especially for merge commits and
  conflict resolutions.
- **Fetch or query a hosting provider:** rejected under the passive observation
  rule and because Branch observation remains independent of the Issue Source.
- **Automatically delete integrated Branches:** rejected. Integration is one
  cleanup signal beside checked-out Worktrees, dirty state, Agent Sessions, and
  Agent Runs; observation never mutates.

## Consequences

- `ProjectSnapshot` reports `integrationRef`, and each local Branch reports
  `unintegratedCommits`; both are observed facts and are stale with the rest of
  repository topology.
- A squash-merged Branch remains visibly unintegrated until a person reviews
  it. Dashpot prefers a conservative false negative over a destructive false
  positive.
- The Branches pane no longer exposes remote names inline, but the complete
  Remote-Tracking Branch records remain in the model and JSON.
- Worktree removability and the Branches pane share one Integration Branch
  selection policy and the same reachability meaning.
- [ADR 0017](0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)
  adds a content answer for the retained commits reachability reports: a
  squash-merged Branch whose content the Integration Branch holds is shown
  as integrated by content, `↑N` stays for work that never landed, and this
  decision's conservative reachability count is kept beside it.
- Amended by [ADR 0018](0018-assess-remote-tracking-branch-integration.md):
  integration is assessed for every concrete local and Remote-Tracking Branch
  ref, so `unintegratedCommits` is reported on Remote-Tracking records too
  and a remote-only row renders their result.
