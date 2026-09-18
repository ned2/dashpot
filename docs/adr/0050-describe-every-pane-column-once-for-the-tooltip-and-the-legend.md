---
status: accepted
date: 2026-09-18
---

# Describe every pane column once for the tooltip and the Legend

[ADR 0040](0040-summarize-integration-across-a-branch-rows-refs.md) gave
each Branches column a Column Description on its `ListColumn` and built both
the header tooltip and the Legend's Branches sections from it. Every other
pane was left as it was ([#169](https://github.com/ned2/dashpot/issues/169)):
the Sessions, Worktrees and Pull Requests headers offered no tooltip at all,
the Issues table's `◉` and `◈` headers offered the bare `Glyph.meaning` from
a `tooltip` field of their own, and the Legend explained only the columns
that render a Glyph, with the activity column's meaning stated once for
Sessions although the same `◈` heads four columns that summarize four
different facts — a session's own state, the liveliest session located at a
Worktree or on a Branch, and the liveliest Agent Run bound to an Issue.
Text, numeric and date columns (`ACTIVITY`, `COMMENTS`, `UPDATED`,
`LAST ACTION`) had no explanation anywhere, although each carries a
qualification a reader needs: which age `ACTIVITY` names, what `COMMENTS`
reports when engagement was not fetched, what `REVIEW`, `CHECKS` and `MERGE`
establish and what they leave to the base Branch's protection.

## Decision

Every column of every pane — Sessions, Worktrees, Branches, Pull Requests and
the Issue table, optional and conditional Issue columns included — carries
its own Column Description beside the Glyphs its cells render, and the
header tooltip and the Legend section for the column are both built from
that one definition, as ADR 0040 did for Branches. The seam is the
`DescribedColumn` protocol in
[`list_rows.py`](../../src/dashpot/ui/list_rows.py): a `label`, a
`description` and the `glyphs`, which the list panes' `ListColumn` and the
Issue table's `ColumnSpec` both satisfy, so `column_help` formats one
tooltip for either and `legend.column_sections` builds one Legend section
per column for either. The Issue table's `ColumnSpec.tooltip` field is gone;
its `description` is required, and the controller passes `column_help(spec)`
to the shared `FocusCursorTable` when it declares the columns, so there is
one header-hover implementation and one catalogue.

Descriptions are derived from the read models and the cells, not from the
label: each says what the observed value is, what its absent or unknown
value means (`-`, `detached`, `no active Issue work`, `not fetched`,
`n/a`), which time an age names, and how fresh the fact is (as of the
page's query, as of the last fetch, observed at turn boundaries). Genuinely
shared meanings are shared by construction — the Worktrees and Branches
activity and `SESSIONS` columns call the same `activity_description` and
`sessions_description` with their own location, and every activity column
lists the same `ACTIVITY_LEGEND` Glyphs — while pane-specific semantics stay
distinct: the Sessions column describes the session's own state and the
Issues column the explicitly bound Agent Run, and neither says what the
other does. Glyph meanings are never restated in a description; the
tooltip and the Legend format the `Glyph` values themselves.

The Legend therefore lists one section per column of each pane, in pane
order, whether or not the column renders a Glyph and whether or not an
Issue column is currently chosen, so a person learns from the keyboard what
a column they have not shown would tell them. What is not a column keeps a
section of its own: the Worktrees pane's `x · Enter · y` actions, the Issue
table's `column headers` (the sort markers and the `c` choice of columns,
listing the optional columns from the catalogue), and the relationship
emphasis the panes share under `RELATED ROWS`. The inventory test reads the
pane specs and the Issue column catalogue rather than a list of labels, so
a column declared without a description, or missing from the Legend, fails
the gate.

## Considered options

- **A second description catalogue for the Issue table**, keyed by
  `ColumnKey`: rejected; the Issue is explicit that Issues adopt the shared
  approach, and a catalogue beside `COLUMN_SPECS` is the drift ADR 0040
  removed for Branches.
- **Make `ColumnSpec` a `ListColumn`**: rejected; the Issue table's columns
  carry sortability, search fields, spread weights and conditional
  visibility that no list pane has, and a protocol over the three shared
  fields is the whole of what the tooltip and the Legend read.
- **One shared activity description for the four `◈` columns**: rejected;
  the Issue names this as the error to avoid. A located Agent Session and an
  explicitly bound Agent Run are different facts, and the column that shows
  one must not be explained as the other.
- **Legend sections only for Glyph columns, descriptions only in tooltips**:
  rejected; the tooltip is mouse-only, and the keyboard-accessible Legend is
  the acceptance criterion for every column, text and date columns included.
- **Fold the pane-level notes into a column**: rejected; the Cleanup gate
  and the relationship emphasis are not what any one column shows, and a
  note attached to `◈` reads as if it were.

## Consequences

- Every visible header of every pane explains itself on hover, and the
  Legend grows from eighteen sections to one per column of every pane plus
  the three pane-level notes; it scrolls, and `End` and `Home` reach its
  ends from the keyboard.
- The Legend is no longer "every Glyph" but "every column and every Glyph":
  the domain language's Legend and Column Description entries say so, and
  this decision amends ADR 0040, whose Issues tooltips are no longer
  unchanged, and [ADR 0010](0010-derive-the-legend-from-rendered-glyphs.md),
  whose Legend now derives from column definitions as well as Glyph values.
- A new pane column cannot ship without a description: the list panes'
  `ListColumn` still allows `None` for a bare table, but the inventory test
  fails on any column of a shipped pane or of the Issue catalogue that
  lacks one, and on any such column missing from the Legend.
