---
status: accepted
date: 2026-09-13
---

# Summarize integration across a Branch row's refs

The Branches pane presents one row for a local Branch and its same-name
Remote-Tracking Branches, and its `INTEGRATED` column exists so a person can
spot Branches whose work has landed and consider a Cleanup. Under
[ADR 0018](0018-assess-remote-tracking-branch-integration.md) the cell
reported the local ref's integration whenever a local ref existed, and a
remote-only row's result only when its Remote-Tracking Branches agreed on one
tip and one result. A row could therefore read

```text
LOCAL  REMOTE  UPSTREAM  INTEGRATED
  ✓       ✓       ↓4         ≡
```

while the four commits on the upstream had never landed
([#168](https://github.com/ned2/dashpot/issues/168)): the cell established
only that the local Branch's content was integrated and hid the additional
remote work, which is exactly what the column was meant to reveal. The
column meanings were also only discoverable through the `?` Legend, whose
`INTEGRATED` note read as if the cell were the Cleanup gate itself.

## Decision

`INTEGRATED` summarizes every ref the row represents: the local Branch when
present and every same-name Remote-Tracking Branch. Each ref keeps the
per-ref commit-reachability and content-integration observation of
[ADR 0012](0012-observe-branch-integration-by-reachability.md),
[ADR 0017](0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)
and ADR 0018 against the same Integration Branch, and the row aggregates
those per-ref states (`integration_summary` in
[`branch_list.py`](../../src/dashpot/observation/branch_list.py)):

| Aggregate observation | `INTEGRATED` |
| --- | --- |
| Every represented ref is integrated by commit reachability | `⊆` |
| Every represented ref is integrated, and at least one relies on content integration | `≡` |
| Any represented ref has retained commits and content integration has not been detected | `↑` |
| No ref is known unintegrated, but at least one comparison is unavailable | `⊘` |

Known unintegrated work outranks an unavailable comparison, and an
unavailable comparison outranks every integrated ref, so an integrated local
ref never masks unintegrated or unknown remote work and missing evidence
never produces an integrated result. Whether the refs share a tip is not part
of the rule: local and remote refs, or refs on several remotes, can differ
while all their work has landed, and the ADR 0018 requirement that remotes
agree on one commit is withdrawn. The upstream relation `UPSTREAM` shows is
not in scope: a differently named configured upstream is not one of the
row's refs, and the row does not add it.

The aggregate cell is the unnumbered `↑`. Per-ref counts can overlap across
refs, so adding them would overstate the work and reducing them to the local
count would restate the bug; the exact per-target counts stay in the Cleanup
preview, which continues to judge each concrete target on its own
([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
`↑` is also the Issues header sort marker, the one symbol the Legend now
lists with two meanings, because both say *above* and are read on different
surfaces — a Branches cell and an Issues header — where neither can be
mistaken for the other. `LOCAL`, `REMOTE` and `UPSTREAM` keep their meanings,
and remote facts stay only as fresh as the last Remote Fetch: observation
still never fetches ([ADR 0005](0005-observe-branches-without-fetching.md)).

An integrated row means that all observed work the row represents has
landed. It is the prerequisite for considering a Cleanup, not a promise
that every target is deletable: the preview still checks each concrete
target's own integration fact and count, its other blockers, explicit
selection, confirmation and the remote lease.

Each Branches column now carries a description and the Glyphs its cells
render on its `ListColumn` ([`branch_cells.py`](../../src/dashpot/ui/branch_cells.py)),
and both the header tooltip and the Legend's Branches sections are built from
that one definition — the tooltip as the description followed by each
Glyph's meaning, the Legend as the Glyph lines followed by the description as
its note — so the two cannot drift and a column without Glyphs, such as
`BRANCH`, is explained in both places too. The header-hover support that
[ADR 0010](0010-derive-the-legend-from-rendered-glyphs.md) added to the
Issues table's `SpreadTable` moves down to the shared `FocusCursorTable`,
where every list pane's table can offer it; the Issues tooltips are
unchanged. Hovering, opening the Legend and refreshing remain passive.

## Considered options

- **Keep the local-first cell and add a second column for the remotes:**
  rejected; the row already joins the refs by name so that a Branch is one
  row, and a person deciding on a Cleanup wants one answer to *has all of
  this landed?*, not a comparison to perform by eye.
- **Sum the per-ref counts into `↑N`:** rejected; commits reachable from
  both the local and a remote ref would be counted twice, and a number that
  is sometimes right invites trust the aggregate cannot earn. The exact
  counts belong to the per-target Cleanup preview.
- **Treat different tips as unknown, as ADR 0018 did for remote-only rows:**
  rejected; refs at different commits are the normal state of a Branch that
  has been rebased or squash-merged, and each of their integration facts is
  already known. Divergence is not missing evidence.
- **Let an integrated local ref stand for the row:** rejected; it is the
  reported bug.
- **Write the tooltips as their own strings:** rejected; a second copy of
  each Glyph's meaning is the drift ADR 0010 removed from the Legend.

## Consequences

- An integrated local Branch beside an unintegrated Remote-Tracking Branch
  now reads `↑`, and a row with an unassessed remote reads `⊘` where it read
  `⊆` before. Rows can therefore look less finished than they did; the
  earlier reading was the false one.
- `↑N` no longer appears in the pane. The count is in the Cleanup preview
  and in the headless JSON's per-ref `unintegratedCommits`, which is
  unchanged.
- Every Branches header explains itself on hover, the Legend lists all
  eight columns, and its `INTEGRATED` note distinguishes the row summary
  from the Cleanup's per-target checks.
- The app widens Textual's tooltip to 72 cells so that the `INTEGRATED`
  help is a short box beside the header rather than a column of text.
- This decision amends ADR 0012 and ADR 0017, whose `↑N` cell becomes the
  aggregate `↑`; ADR 0018, whose local-first cell and same-tip rule for
  remote-only rows it replaces; and ADR 0010, whose single-meaning rule now
  admits the shared `↑`. Per-ref assessment under those decisions is
  unchanged.
