---
status: accepted
date: 2026-09-20
---

# Adopt long-lived peer dashboard screens

The dashboard's Sessions, Worktrees, Branches, Pull Requests and Issues compete
for vertical space, until a large Repository leaves too little room for the
Issues table. Dashpot replaces that single pane of glass with two
long-lived peer screens: `Dashboard`, containing Sessions, Worktrees and
Branches, and `Issues & Pull Requests`, containing a bounded Pull Requests pane
above a flexible Issues pane. A persistent status bar names both peers, marks
the active one, switches directly by mouse or the `1` and `2` keys, and carries
an exact open-Issue and open-Pull-Request summary. Switching peers replaces the
active peer without building screen history; Issue Detail, Legend and Cleanup
remain temporary screens that dismiss to the peer that opened them.

## Ownership

`DashpotApp` continues to own the `PagedObservationStore`, observation and page
runners, Project Totals, Query Pages and their navigation. It requests the
initial Issue and Pull Request pages eagerly and refreshes those facts whether
or not their screen is active. Each peer owns its own Textual presentation
state and long-lived widgets. The Dashboard owns the Sessions, Worktrees and
Branches panes and the Remote Fetch and Cleanup actions. The Issues & Pull
Requests screen owns both filter bars, their submitted and draft queries, the
Issue-table controller, the two tables and their contextual query actions.

The status bar is reusable chrome composed independently by each peer, driven
by the active peer and a small navigation-summary read model derived from the
authoritative Project Totals. It is not a generic status-indicator framework.
Query Pages remain filtered and paginated and never supply the global summary;
no new Pull Request attention observation is introduced. The alert,
Diagnostics and Footer are rendered on both peers from their existing shared
facts, while `f` and `x` remain Dashboard-only and `/`, `o`, `c`, `n`, `p` and
`g` belong to the focused query pane where that action is meaningful.

Long-lived widgets retain focus, lifecycle choice, submitted and unsubmitted
search text, chosen Issue columns, row cursor and scroll position when their
screen is inactive. Page history stays in the app-owned page runner; row and
scroll state stay in Textual's widgets. Dashpot does not add a second cursor
history over Textual's native `DataTable` behaviour. Refresh reconciles stable
row identities without stealing focus. A screen switch does not carry a cursor,
filter or relationship selection into the other peer.

The Dashboard therefore stops opening an Issue when a Session is activated and
stops highlighting Issue rows from Session focus. This keeps screen concerns
separate and avoids choosing one Issue on behalf of a Session before Sessions
can bind to multiple Issues. Relationship emphasis that is meaningful among
Dashboard panes remains on the Dashboard. Enter opens Issue Detail only from
the Issues table; Pull Requests deliberately have no Enter action until a Pull
Request detail contract is designed.

## Qualifying ADR 0047

[ADR 0047](0047-keep-the-dashboard-screen-as-one-textual-adapter.md) chose one
thin `DashboardScreen` adapter because every decision had already moved behind
plain modules and another adapter would only have forwarded the same Textual
events. It explicitly named a second screen needing shared handlers as a reason
to revisit that conclusion. This decision reaches that condition for a product
reason: the two peers have different content, actions, focus cycles and layout.

ADR 0047's thin-adapter rule remains. Each peer is one Textual adapter whose
handlers gather widget facts, call the module that owns the decision and paint
the result. Shared decisions live in plain read models or reusable widgets, not
in a handler-bearing base class or mixin; Textual dispatches a handler on every
class of the MRO that defines it, so handler inheritance would reintroduce the
double-dispatch hazard ADR 0047 avoided. Two adapters make the shared chrome
and app-owned state real seams, but do not justify protocols around one-line
widget forwarding.

## Summary semantics

The status bar renders `Open PRs: {value} | Open Issues: {value}` on both peers.
A fresh Glyph means every displayed number is fresh; a stale Glyph means at least
one displayed number is retained from a stale Project Total. Loading,
unavailable-without-a-value and unconfigured values render `-`, zero renders
`0`, and a stale value keeps its last known number. A placeholder contributes
no freshness state, and no freshness Glyph is shown when neither value is
numeric. The precise Glyphs, colours, breakpoint and Textual layout mechanism
are implementation choices; current location and freshness must remain
apparent without depending on colour alone.

At wide widths the screen choices stay left and the summary floats right on one
line. At compact widths the same status bar may wrap, with the summary
preferring the left edge on its second line. Both query panes remain visible at
every supported width: Pull Requests is content-sized to a cap and Issues owns
the remaining height. The complete interaction contract and representative
wireframes live in [the maintained design](../design.md#accepted-multi-screen-target).

## Considered options

- **Keep one single pane of glass**: rejected because the content-sized panes
  consume the Issues table's useful height as ordinary inventories grow.
- **Put Issues and Pull Requests behind an internal tab or collapsible pane**:
  rejected because it hides one of two closely related query surfaces and adds
  another navigation state inside the destination.
- **Push the second peer onto ordinary screen history**: rejected because the
  two main destinations are peers, while Back belongs to temporary contexts.
- **Derive attention from visible Pull Request rows**: rejected because a
  filtered Query Page cannot establish a repository-wide fact.
- **Introduce a generic status framework**: rejected because one concrete
  navigation summary does not earn that interface; Project Totals already own
  the required facts.
- **Split navigation, the dedicated screen and the summary into separately
  shipped features**: rejected for implementation planning because each leaves
  an incomplete intermediate UI and repeatedly changes the same screen, style
  and interaction seams. One implementation Issue will deliver the vertical
  feature through internal checkpoints.

## Consequences

- The default screen remains Dashboard, initially focused on Sessions; the
  first visit to Issues & Pull Requests focuses Pull Requests. Later visits
  restore each peer's last focused control.
- `Tab`, `Shift+Tab` and row-boundary arrows cycle tables only within the active
  peer. Direct screen keys are disabled while an editable text input has focus
  and on temporary screens.
- Pane inventory totals and accepted-page match counts remain alongside the
  global open-count summary because they report different facts.
- Legend, Footer, alert and Diagnostics must follow the active peer, including
  state changes accepted while the other peer is inactive.
- [Issue #270](https://github.com/ned2/dashpot/issues/270) delivers the decision
  as one vertical feature and replaces the maintained design's transitional
  account; exact layout is not a supported extension interface.
