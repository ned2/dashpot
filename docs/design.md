---
status: living
date: 2026-09-20
---

# Design

The leaf and domain layers live in nine packages: `core` for shared
infrastructure and observation values, `project` for configuration and Workspace
resolution, `github` for the gateway and wire adapters, `issues` for Issue
Sources and resolution, `queries` for source queries and page navigation, and `sessions` for Agent
Session observation, the Work Store, Issue work, and integration; and
`repository` for Git observation, Remote Fetch, Worktree operations, and Cleanup;
`observation` for coordination, stores, and read models; and `ui` for Textual
widgets, rendering, and runners.
[ADR 0042](adr/0042-group-leaf-and-domain-modules-into-subpackages.md) records
the layout and its staged scope. Pydantic bases live in
[`core/pydantic.py`](../src/dashpot/core/pydantic.py); observation models in
[`core/model.py`](../src/dashpot/core/model.py); trusted Workspace values in
[`project/workspace.py`](../src/dashpot/project/workspace.py).

Root-level [`composition.py`](../src/dashpot/composition.py) constructs the
collector and Query Sources and composes Cleanup into a report; the CLI parses
arguments and renders results. Cleanup has separate
[preview](../src/dashpot/repository/cleanup/preview.py),
[execution](../src/dashpot/repository/cleanup/perform.py), and
[dashboard adapter](../src/dashpot/repository/cleanup/adapter.py) modules over
shared [target values](../src/dashpot/repository/cleanup/targets.py) and
[obstacle assessments](../src/dashpot/repository/cleanup/obstacles.py). Worktree
[creation](../src/dashpot/repository/worktrees/create.py) and the
[removability report](../src/dashpot/repository/worktrees/removability.py) are
separate so removal checks never load creation.

Observation is scheduled per key rather than as one refresh: the Project's
Issue Source, Pull Request source and Repository State are observed
independently. Agent Runs are observed once per Workspace after a Project
publishes a changed binding input; Pull Request-only changes do not trigger
them. An [`ObservationCoordinator`](../src/dashpot/observation/collect.py) tracks a
generation per key so a superseded observation can never overwrite a newer
one, retains the last good result per key when a refresh fails, and composes
each Project from its latest accepted parts. The Issue Source and Pull
Request source a Project's configuration declares are built by
[`source_factories.py`](../src/dashpot/issues/source_factories.py), the one module
the coordinator and Issue resolution both go through, so resolving an Issue
Hint never loads the coordinator. The Textual interface publishes
every accepted observation into a process-local `WorkspaceObservationStore`
as soon as it lands, then re-queries read models carrying a store revision; a
slow GitHub call therefore never delays branch or dirty state.
A key is observed at most once at a time: a request for a key whose
observation is still in flight coalesces onto it rather than superseding it,
so a slow Issue Source that outlasts the polling period still publishes when
it lands instead of being discarded by every tick
([ADR 0020](adr/0020-coalesce-requests-onto-the-observation-in-flight.md)).
An automatic tick queues nothing further, the next tick being its rerun; a
key press, a Remote Fetch or Cleanup that changed the Repository, and a
follow-up of a publish each queue one more observation of the key for when
the running one lands. Two timers tick
([ADR 0056](adr/0056-refresh-github-queries-on-their-own-period.md)). The
local one observes every key. The query one repeats each displayed page and
its totals, and resolves the bound and selected Issues. The query timer runs
on the GitHub Refresh Period for a GitHub Query Source and on the local one
otherwise. An Agent Runs landing resolves the bound Issues only when they
changed. `r` refreshes every key in the Workspace, which with
one Project per run is the observed Project, and restarts both submitted source queries from page one, refreshing totals
and relevant identities. It never fetches: `f`
mutates, a Remote Fetch of the Repository Anchor whose refs
supplied the Branch observation ([`fetch.py`](../src/dashpot/repository/fetch.py),
[`fetch_flow.py`](../src/dashpot/ui/fetch_flow.py),
[ADR 0014](adr/0014-fetch-remotes-on-explicit-key-press.md)). It runs
off the event loop, once per Project at a time, and once any remote has been
fetched it schedules the passive Git observation of that Project, so the
Branches pane, the Integration Branch facts, and the fetch age reflect the
result without anything being inferred from the fetch itself.

`x` is the other mutating key, a Cleanup
([`cleanup.py`](../src/dashpot/repository/cleanup/),
[`cleanup_flow.py`](../src/dashpot/ui/cleanup_flow.py),
[`cleanup_view.py`](../src/dashpot/ui/cleanup_view.py),
[ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
The highlighted Branches or Worktrees row is resolved through the observation
store into a request against its Repository Anchor, the read-only preview is
inspected off the event loop, and a modal lists every concrete target — the
local Branch, the Branch at each remote, the Worktree with its Branch locally
and at its push remote — with its integration fact, blockers, and
consequences beneath, disables the unavailable ones (a Worktree's Branches
among them while the Worktree cannot be removed), selects a Worktree's
local Branch by default on a first preview — and its Branch at the remote
only at the local Branch's tip — discloses the Worktree's ignored content
rather than asking for its acknowledgement, recaps what confirming removes
and deletes in a callout at the end of the list above a fixed-label button
([ADR 0054](adr/0054-finish-a-worktree-with-its-branch-by-default.md)),
and answers a premature press of the destructive button by deleting nothing,
saying why beneath the list and in a toast, and moving focus to what is
missing; the button stays pressable while the preview is idle and turns red
once the selection is one the performer accepts, and is disabled only through
a Remote Fetch, the post-fetch observation, and the re-inspection of the same
Cleanup request, or while that re-inspection has failed
([ADR 0036](adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md)).
`Escape` cancels. Confirmation performs off the
event loop through the injected cleanup adapter (a construction without one
refuses `x`, as one without a fetcher refuses `f`), one mutation per Project
at a time: a Cleanup and a Remote Fetch of the same Project exclude each
other, each refusal naming the other. A preview that changed in between
performs nothing and reopens the revised preview for another confirmation;
otherwise the per-target outcomes and recovery commands are shown (a refused
or unknown remote outcome among them, with the local ref retained for a
revised preview after the next `f`), the
Project's Worktrees and Git state are re-observed the passive way, and the
row cursor settles on the deleted row's neighbour. The same adapter is
exercised by the acceptance scenarios in
[`tests/test_cleanup_scenarios.py`](../tests/test_cleanup_scenarios.py), each a
disposable Repository in a shape a real Issue Worktree takes: a finished Issue
whose Branch the forge deleted after a squash merge, a merged Branch still at
`origin`, pushed but unintegrated work, a second approach with commits of its
own, and a dirty Worktree on a Branch named unlike its directory.

The configured source owns Query Pages, Project Totals, identity resolution and
explicit Source Enumeration ([source_queries.py](../src/dashpot/queries/source_queries.py),
[query_source.py](../src/dashpot/queries/query_source.py)). GitHub searches use advanced
syntax, scoped by current Repository name and validated by opaque identity and
resource type. Search pages contain IDs for Issues, completed in batches of 24;
Pull Requests carry their existing complete compact records. Each required page
is accepted atomically under a Refresh Budget. Auxiliary engagement and colour
observations have a separate budget and availability. The declared lowest-numbered
twenty Linked Pull Requests require deliberate connection completion when more
exist; there is no incremental bookkeeping or counterpart expansion.

Query and complete-collection adapters retain distinct cache and failure policies.
They share parsing, Profile completion, and collection retention; explicit export
crosses the Query Source enumeration seam before the collector shapes snapshot
output. [ADR 0043](adr/0043-retain-distinct-query-and-collection-adapters.md)
records the caller trace, remaining duplication, and rejected consolidation options.

The dashboard ([app.py](../src/dashpot/ui/app.py)) schedules Issue pages,
Pull Request pages, both kinds of Project Totals, targeted identities and local
observations independently: the page runner
([page_runner.py](../src/dashpot/ui/page_runner.py)) runs one source query per
key at a time and keeps each paged kind's navigation, and the observation
runner ([observation_runner.py](../src/dashpot/ui/observation_runner.py)) observes
each key at most once at a time, coalescing requests onto the observation in
flight ([ADR 0020](adr/0020-coalesce-requests-onto-the-observation-in-flight.md)).
Each drives the app through a narrow host protocol — run work off the loop
and, for the observation runner, start a timer and redraw the alert — so
their scheduling is tested without a running app. The two mutating flows
([`fetch_flow.py`](../src/dashpot/ui/fetch_flow.py),
[`cleanup_flow.py`](../src/dashpot/ui/cleanup_flow.py)) drive the app through
host protocols of their own: the Remote Fetch flow keeps the Projects being
fetched and the last failure per Project, and the Cleanup flow keeps the
Projects held from preview to report with the preview each holds, waits on
the observation runner's landings for the post-fetch Git facts, and asks the
app only to notify, push its screens and run its workers. Their refusals are
tested without a running app too; the previews and confirmations are driven
through the dashboard. Configured Projects are published before remote work.
The shipped Dashboard and Issues & Pull Requests peers are two thin Textual
adapters over those objects: their handlers gather widget facts, call the
module that owns the decision and paint the result. Both readouts — the alert
line and the Diagnostics box — are derived by
[`alerts.py`](../src/dashpot/ui/alerts.py). [ADR 0047](adr/0047-keep-the-dashboard-screen-as-one-textual-adapter.md)
set the thin-adapter rule, and [ADR 0051](adr/0051-adopt-long-lived-peer-dashboard-screens.md)
qualifies it as one adapter per long-lived peer rather than one for the whole
interface.
The page store ([paged_store.py](../src/dashpot/observation/paged_store.py)) never puts partial
query rows in complete snapshot inventory fields; every accepted page, total or
identity goes through a method that advances its `source_revision`, so a read
model's `revision` changes whenever what it was built from does. It joins Agent
Runs to targeted identity evidence without changing Work Store Issue Bindings.
Opening a selected Issue works from the Issues table; relationship titles in
Issue Detail are resolved one level deep. Relevant identities are
refreshed directly, including relationship changes without an Issue timestamp
change.

A Query Page has its submitted request, effective ordering, matching count,
returned count, continuation outcome and its own attempt/last-good times. Project
Totals have independent status and times. Source caches retain at most 16 pages
and 256 identities. Navigation retains eight accepted pages. Previous reuses its
retained observation; eviction requires restart instead of reconstructing history.
Refreshing a page discards its forward history. A failed Next leaves the accepted
page under its original request and displays the navigation error. New submissions,
lifecycle/sort changes and manual restart create generations; old completions are
discarded. Timer refresh does not supersede an in-flight user query.

Portable continuation includes a fingerprint of Project, Repository, effective
source configuration/location, authenticated principal, query, lifecycle, ordering
and page size. Markdown adds a deterministic digest of relevant paths and content.
Context must be observed before mismatch can be asserted. GitHub pages may change
between requests; only forward cursor traversal checks repetition. Search's
1,000-result ceiling is distinct from end of matches. Explicit export uses complete
repository connections, never search, and retains its existing wire semantics and
complete-last-good behavior. Incremental inventory processing and Snapshot Seeds
have been retired; deprecated `reconciliationSeconds` no longer schedules work.

Exceptional state is summarized in a
one-line alert above Diagnostics that takes no space while everything is
healthy: refresh failures, unavailable Projects and failed Pull Request
observations are errors; unavailable or stale worktrees and stale Issue or
Pull Request sources are warnings. A Local Markdown Project's intentionally
unconfigured Pull Request source is not an alert. A refresh that has
been running longer than a moment, or a Remote Fetch from the moment it
starts, is shown as information. The alert is
derived from current observations and clears itself on recovery; toasts are
reserved for manual-refresh, Remote Fetch, and Cleanup outcomes (an automatic
tick's failure or recovery changes the alert and Diagnostics only), and Diagnostics keeps
the durable detail: the box takes no space while it is empty and is coloured
by the most severe line it holds. Headless JSON runs a coordinated barrier
over every key and serializes the store's `checkpoint()`, so it remains one
complete snapshot. Collection happens off the UI thread, and the table is
reconciled by stable row keys.

## Accepted multi-screen target

[Issue #262](https://github.com/ned2/dashpot/issues/262) accepted the first
additional long-lived screen as one vertical design. [Issue #270](https://github.com/ned2/dashpot/issues/270)
ships that design: navigation, state restoration, both peers' contents and the
shared status summary are one coherent interface.

### Screen topology and layout

`Dashboard` and `Issues & Pull Requests` are long-lived peers. Dashboard keeps
Sessions, Worktrees and Branches; the second peer moves both paged query panes
off Dashboard, with a content-capped Pull Requests pane above an Issues pane
that receives the remaining height. Issue Detail, Legend and Cleanup stay
temporary screens and dismiss to the peer that opened them. Peer switching
does not add Back history.

The persistent top row is Dashpot's own status bar, not Textual's default
`Header`. It names both peers, marks the active one without relying on colour,
and makes each complete label clickable. `1` and `2` are the equivalent direct
keyboard paths. `Ctrl+Shift+Left` and `Ctrl+Shift+Right` move through the peers
in status-bar order and wrap at either end. Each choice is a distinct one-row
background-filled block, separated by one cell like a tmux window list. The
active block uses a contrasting fill and bold text, so current location does
not depend on colour.
The wireframes surround the active label with `*` to represent bold rather
than literal characters. `◆` marks fresh displayed totals and `◇` marks a
retained stale total; the wireframes spell those marks as `<fresh>` and
`<stale>` for clarity. The final separator makes either mark apply to both
totals, and both marks use the same muted neutral colour so the binary shape is
available without becoming an attention signal.

Every content pane owns the same one-row top gutter. The first gutter separates
the content stack from the persistent status bar; each later gutter separates
adjacent panes. One terminal row is the smallest positive Textual spacing unit,
so the layout uses no separate status-bar padding or trailing pane margin.

A representative wide Dashboard is:

```text
+--------------------------------------------------------------------------------------------------+
| *1 Dashboard*  2 Issues & Pull Requests        Open PRs: 2 | Open Issues: 18 | <fresh>             |
+--------------------------------------------------------------------------------------------------+
| SESSIONS · 4                                                                                     |
| ...active Agent Sessions...                                                                      |
+--------------------------------------------------------------------------------------------------+
| WORKTREES · 3                                                                                    |
| ...main and linked Worktrees...                                                                  |
+--------------------------------------------------------------------------------------------------+
| BRANCHES · 12                                                                                    |
| ...Branch rows fitted with the other Dashboard inventories to the live height...                 |
+--------------------------------------------------------------------------------------------------+
| Alert / Diagnostics when present                                                      r  ?  q    |
+--------------------------------------------------------------------------------------------------+
```

The wide Issues & Pull Requests peer keeps both queries visible:

```text
+--------------------------------------------------------------------------------------------------+
| 1 Dashboard  *2 Issues & Pull Requests*        Open PRs: 2 | Open Issues: 18 | <fresh>             |
+--------------------------------------------------------------------------------------------------+
| PULL REQUESTS · Open 2 · Closed 3                                                            |
| [Open v]  [Search Pull Requests____________________________]  2 pull requests                    |
| ...rows up to the content cap; the table scrolls beyond it...                                   |
+--------------------------------------------------------------------------------------------------+
| ISSUES · Open 18 · Closed 7                                                                      |
| [Open v]  [Search Issues___________________________________]  18 issues                           |
| ...the Issue table owns the remaining height...                                                  |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
| Alert / Diagnostics when present                                                      r  ?  q    |
+--------------------------------------------------------------------------------------------------+
```

At compact widths the same status bar may wrap instead of abbreviating a
screen name or hiding the summary. The wrapped summary prefers the left edge;
the shipped breakpoint is 100 columns:

```text
+----------------------------------------------------------+
| *1 Dashboard*  2 Issues & Pull Requests                   |
| Open PRs: 2 | Open Issues: 18 | <fresh>                    |
+----------------------------------------------------------+
| SESSIONS · 4                                             |
| ...                                                      |
+----------------------------------------------------------+
| WORKTREES · 3                                            |
| ...                                                      |
+----------------------------------------------------------+
| BRANCHES · 12                                            |
| ...scrolling rows...                                     |
+----------------------------------------------------------+
```

```text
+----------------------------------------------------------+
| 1 Dashboard  *2 Issues & Pull Requests*                   |
| Open PRs: 2 | Open Issues: 18 | <fresh>                    |
+----------------------------------------------------------+
| PULL REQUESTS · Open 2 · Closed 3                        |
| [Open v] [Search Pull Requests__________] 2 pull requests|
| ...bounded scrolling rows...                             |
+----------------------------------------------------------+
| ISSUES · Open 18 · Closed 7                              |
| [Open v] [Search Issues________________] 18 issues       |
| ...flexible scrolling table...                           |
| ...                                                      |
+----------------------------------------------------------+
```

An honest empty or unavailable Pull Requests pane still keeps its filter and
one-line state while height permits and gives unused height back to Issues. At
every supported width both panes remain present; there is no compact-only tab
or collapsed section. The existing content-fitting rule remains the starting
point for the exact Pull Request cap, rather than making terminal layout an
extension interface.

### Navigation, focus and state

Dashboard is the default peer and initially focuses Sessions. The first visit
to Issues & Pull Requests focuses its Pull Requests table because that is the
first pane in visual order. Thereafter each peer restores its last focused
control. Clicking the inactive status-bar label or pressing its number switches
directly; clicking the active label is a no-op. The number keys insert text
instead of switching while an editable input has focus, and neither peer key is
active on a temporary screen. Temporary screens cover the peer status bar and
`Escape` returns to the exact originating peer.

Within either peer, `Tab`, `Shift+Tab` and an arrow move at a table's row
boundary through only that peer's tables, wrapping in composition order. On the
query peer, `/` enters the focused pane's search; normal Textual traversal then
moves through that pane's lifecycle selector, search and table. A refresh never
steals focus.

| State | Owner | Screen-switch behaviour |
| --- | --- | --- |
| Workspace observations, Project Totals and Query Pages | `PagedObservationStore` on `DashpotApp` | Shared; collection and accepted results continue while either peer is active. |
| Accepted request, retained pages and current page | `PageRunner` and each kind's `PageNavigation` | Shared app state; initial Issue and Pull Request pages are requested eagerly. |
| Submitted query record and unsubmitted search text | `ListQueries` and controls on Issues & Pull Requests | Preserved with the long-lived query peer; switching alone submits nothing. |
| Issue columns and selected stable row identity | `IssueTableController` on Issues & Pull Requests | Preserved and reconciled against accepted pages. |
| Focus, active table row, table scroll and control cursor | Long-lived Textual screen and widgets | Preserved natively while the peer is inactive; not persisted across a Dashpot restart. |
| Active peer | App navigation | Replaced directly by `1`, `2` or a status-bar click, or cyclically with wrapping by `Ctrl+Shift+Left` / `Ctrl+Shift+Right`; no peer Back history. |
| Alert and Diagnostics content | Existing app-owned derivations | Rendered on both peers from the same facts, including changes accepted while one is inactive. |

Page Navigation history and table navigation are deliberately different. The
former retains accepted Query Pages and opaque continuation positions; the
latter is widget state. Dashpot does not layer a cursor-history abstraction
over Textual: the native `DataTable` behaviour restored by
[PR #268](https://github.com/ned2/dashpot/pull/268) remembers the active row and
scroll when focus leaves and returns, while reconciliation continues to use
stable row keys when data changes.

Screen actions follow ownership rather than whichever handler happens to see a
key:

| Key or action | Dashboard | Issues & Pull Requests |
| --- | --- | --- |
| `1`, `2`, clickable screen labels | Switch directly | Switch directly |
| `Ctrl+Shift+Left`, `Ctrl+Shift+Right` | Move through peers with wrapping | Move through peers with wrapping |
| `r`, `?`, `q` | Refresh, Legend, quit | Refresh, Legend, quit |
| `f`, `x` | Remote Fetch; Cleanup of the selected Branch or Worktree | Unavailable |
| `/`, `o`, `n`, `p`, `g` | Unavailable | Search, lifecycle and page action of the pane that owns focus, including its controls |
| `c` | Unavailable | Issue columns, only while the Issues pane owns focus |
| `Enter` | Keeps the Worktree table's existing open action; has no Session-to-Issue action | Opens Issue Detail from an Issue row; unbound for Pull Requests |

The Footer exposes the active peer's available actions. The Legend groups
global keys and each peer's keys rather than implying that a hidden screen's
actions are available. Peer Screen navigation stays out of the compact Footer
because the persistent status bar already presents the direct destinations;
the complete Legend still lists every navigation key. Number keys keep typing
in an editable query input, while the modified-arrow peer keys are priority
bindings and keep navigating from that focus; all peer keys are inactive on
temporary screens. A Session cursor no longer opens or highlights an Issue
across screens; relationship emphasis that is meaningful among Sessions,
Worktrees and Branches remains within Dashboard. An ordinary peer switch never
chases, filters or repositions the other screen.

### Navigation summary

The right side of the status bar renders exactly
`Open PRs: {value} | Open Issues: {value}` on both peers. It reads independent
Project Totals, never the filtered Query Pages. Pane titles retain their open
and closed inventories, and filter bars retain the accepted page's matching count:
the three readouts intentionally report different facts. No repository-wide
attention or changed-since-visit fact is inferred, so no new observation is
needed.

| Project Total state | Value | Aggregate freshness Glyph |
| --- | --- | --- |
| Fresh nonzero | Its exact open count | Fresh when every displayed number is fresh |
| Fresh zero | `0` | Fresh when every displayed number is fresh |
| Retained stale value | Its last known exact count | Stale if either displayed number is stale |
| Loading without a retained value | `-` | Contributes no freshness state |
| Unavailable without a retained value | `-` | Contributes no freshness state |
| Pull Requests intentionally unconfigured | `-` | Contributes no freshness state |

Thus a fresh Issue count beside an unavailable Pull Request count shows
`Open PRs: - | Open Issues: 18 | ◆`; when neither side is numeric neither the
final separator nor the freshness Glyph appears. Availability remains in the
placeholder and existing Diagnostics, while the one binary Glyph says only
whether the numbers actually shown are fresh or stale. Both states use the same
muted neutral colour; filled versus hollow carries the distinction.

### Adapter shape

Each peer remains a thin Textual adapter over app-owned runners and stores and
screen-owned presentation collaborators. Shared chrome and summary derivation
are plain modules or reusable widgets, not message handlers inherited through
a common screen base: Textual invokes every class in the MRO that defines a
handler. This is the second-screen condition that
[ADR 0047](adr/0047-keep-the-dashboard-screen-as-one-textual-adapter.md) said
would qualify its single-adapter conclusion; [ADR 0051](adr/0051-adopt-long-lived-peer-dashboard-screens.md)
records the selected ownership and rejected alternatives.

## Pane read models and presentation

Dashboard lists every active Agent Session, observed Worktree and Branch in
three full-width panes. Issues & Pull Requests keeps both query panes visible:
Pull Requests is content-sized to its cap and Issues receives the remaining
height. Both query pane titles show independently observed Project Totals.
Lifecycle selection constrains source results before pagination. Draft
filtering uses `draft:true` or `draft:false` in the query. Both search boxes
submit on Enter; clearing search submits the default source query. GitHub owns
advanced syntax and ordering; Markdown uses local lexical matching and local
ordering before pagination.

Dashboard panes seek enough height for their complete inventories. Small and
empty panes take only what they need; panes with remaining rows share the live
body height fairly and scroll when their combined content cannot fit. Terminal
resize and record-count changes rerun the same content-aware allocation, without
a fixed terminal-height assumption. Pull Requests alone has a record ceiling of
eight; its content-height cap shrinks before the Issue table would drop below
its minimum height. A horizontal scrollbar occupies one of those bounded
content lines when the table is narrow. An ordinary empty list pane costs three
lines. The Sessions list starts with focus on Dashboard and Pull Requests starts
with focus on the query peer. `Tab`, `Shift+Tab`, `Down` at the last row and `Up`
at the first row cycle within the active peer only; an empty list moves on
immediately, and each list keeps its row cursor when focus
returns — from another pane or from the terminal after a window switch, which
Textual reports as `AppBlur` and `AppFocus` and which a table cannot tell from
pane entry, so the cursor is left where a stock `DataTable` leaves it
([`focus_table.py`](../src/dashpot/ui/focus_table.py)). The row cursor
in the Sessions, Worktrees, Branches and Pull Requests panes is for scrolling,
copying and refresh scope (`r`); only
the Issue table drives the Issue selection, `Enter`
on an Issue opens it in the full-screen Issue view (its location on the left
of the heading line, `opened 3d ago by ned2` on the right, and both panes'
borders in the Issue's state colour). `Enter` is unbound on Sessions and Pull
Requests. Each list pane is declared once as a spec in
[`panes.py`](../src/dashpot/ui/panes.py) — its columns, empty state, the read
model it lists, its filtering controls, and how its rows take part in
relationship emphasis — so each peer composes, refreshes and cycles its own
spec tuple; the Issue table's query state and rows belong to
[`issue_table_controller.py`](../src/dashpot/ui/issue_table_controller.py), and
the messages the dashboard posts to itself — the outcomes of off-loop work
and the body's layout — are the dataclass messages of
[`messages.py`](../src/dashpot/ui/messages.py). The Sessions pane is its own read model
([`session_list.py`](../src/dashpot/observation/session_list.py), queried through
`WorkspaceObservationStore.query_sessions` and rendered by
[`session_cells.py`](../src/dashpot/ui/session_cells.py)): every active Agent Session of the
observed Project exactly once, sorted running → waiting → unknown and then by
most recent activity, with any bound Issue joined from the Work Store's
accepted bindings, an `outside Project` marker in place of a target the
observed Project does not own, an intentional `no active Issue work` value
when unbound, its working directory relative to its Observation Target, and
long paths, branches and titles clipped with an ellipsis. Its columns are
the agent-activity column (`◈`), `HARNESS`, `TARGET`, `BRANCH`, `ISSUE`,
`DIRECTORY`, and `ACTIVITY`. `TARGET` is dropped
altogether while every listed session shares one Observation Target, which is
the usual shape of a Project with no linked Worktrees; it returns as soon as a
session sits in another Worktree or outside the Project. Exactly one column
names the Target, so while `TARGET` is dropped the working directory is shown
in full (`~`-abbreviated) rather than relative to a Target the pane no longer
displays. `ACTIVITY` names the age it is showing rather than leaving one
number to mean two things: `running 14m` is how long the current turn has
been going, `idle 14m` is how long the session has been quiet since its last
observed event, and `started 3d ago` is a run nothing has observed yet, whose
Work Store start time is reported as the different fact it is. Activity is
observed at turn boundaries and not within a turn, which is a measured
decision rather than an omission
([ADR 0006](adr/0006-observe-agent-activity-at-turn-boundaries.md)). The Worktrees pane
is likewise its own read model
([`worktree_list.py`](../src/dashpot/observation/worktree_list.py),
`WorkspaceObservationStore.query_worktrees`, rendered by
[`worktree_cells.py`](../src/dashpot/ui/worktree_cells.py)): every observed Observation
Target of the Project, identified by `(Project Identity, target path)`
and sorted main before linked, then path, with its Git topology kind (`main` or
`linked`) reported in its own column,
and exceptional `stale` or `unavailable` state. Its columns are the
agent-activity column (`◈`), `SESSIONS`, `PATH`, `KIND`, `BRANCH`, and
`TREE`: `SESSIONS`
counts the active Agent Sessions located there, `KIND` distinguishes Git's
`main` and `linked` Worktrees, normal Branches omit HEAD, detached checkouts
include their short HEAD, and the working tree remains clean/dirty/unknown.
`PATH` keeps
the full home-abbreviated path and the table scrolls horizontally when its
content is wider than the pane. Healthy rows
do not repeat `available`. Target-specific diagnostics stay in Diagnostics
and the alert line; the row only points there. The
Branches pane ([`branch_list.py`](../src/dashpot/observation/branch_list.py),
`WorkspaceObservationStore.query_branches`, rendered by
[`branch_cells.py`](../src/dashpot/ui/branch_cells.py)) joins the local ref and the
Remote-Tracking Branches of one branch name into one row, so a branch is
never listed twice and never needs a second pane. `LOCAL` and `REMOTE` show
`✓` when a ref exists in that namespace: `LOCAL` is a ref under `refs/heads`,
and `REMOTE` is a Remote-Tracking Branch as of the last fetch, which can
outlive the Branch at the remote until a fetch prunes it, so the Legend
qualifies the check with the fetch age the border carries and the `f` key
that prunes. `UPSTREAM` is the local ref's
relation to its configured upstream (`=` in sync, `↑2 ↓1`, `∅` no upstream,
or `✗` upstream gone). `INTEGRATED` is whether the Integration Branch holds
all the work the row represents — the local Branch and every same-name
Remote-Tracking Branch, as of the last fetch — summarized across those refs
(`integration_summary` in `branch_list.py`,
[ADR 0040](adr/0040-summarize-integration-across-a-branch-rows-refs.md)):
`⊆` when every ref's commits are reachable, `≡` when every ref has landed and
at least one only by content, as after a squash merge, `↑` when any ref has
retained commits whose content is not found, or `⊘` when no ref is known
unintegrated but a comparison is unavailable. Known unintegrated work
outranks a missing comparison, which outranks integrated refs, so an
integrated local ref never hides remote work and missing evidence never
reads as integrated; refs at different tips can still all have landed. The
`↑` is unnumbered because per-ref counts overlap; the Cleanup preview keeps
the exact count per target. An integrated row is the prerequisite for
considering a Cleanup, not a promise that each target is deletable. The
result is followed by
the age of the row's newest commit. The pane subtitle names the Integration Branch
and the age of the Remote-Tracking Branches. The Worktrees pane names the
Branch checked out at every Worktree. Rows are sorted checked-out first, then
most recent commit. Its columns are the agent-activity column (`◈`),
`SESSIONS`, `BRANCH`, `LOCAL`, `REMOTE`, `UPSTREAM`, `INTEGRATED`, and
`LAST COMMIT`, each a `ListColumn` in `branch_cells.py` that carries its
description and the Glyphs its cells render, from which both its header
tooltip and its Legend section are built. The
refs are read with `git for-each-ref` from the first answering Repository
Anchor; observation never runs `git fetch`, so the lower-right pane border
carries the age of the last fetch (`remote last fetched 3h ago`, or
`remote never fetched`) as the honest freshness of everything remote
([ADR 0005](adr/0005-observe-branches-without-fetching.md)), and `f`
fetches and prunes that anchor's remotes on request
([ADR 0014](adr/0014-fetch-remotes-on-explicit-key-press.md)).

The panes trade words for Glyphs to stay narrow, and `?` opens the Legend
that explains every column and every Glyph
([`legend.py`](../src/dashpot/ui/legend.py)). Its sections follow the peers in
reading order, starting with status-bar freshness and then one per column of
each pane — Sessions, Worktrees, Branches, Pull Requests, and the Issue table,
its optional columns included whether or not they are chosen — each headed by
the surface and the column and holding the
column's Column Description: the Glyphs its cells render, one line each in
the colour the cell shows, followed by what the column reports. So the
Sessions family `●` running, `◐` waiting and `○` unknown appears under the
Sessions `◈` column, which describes the session's own state, and again
under the Worktrees, Branches, and Issues `◈` columns, which describe the
liveliest located Agent Session or, for Issues, the liveliest explicitly
bound Agent Run — one Glyph vocabulary, four facts, each named where it is
seen. The Branches presence, `UPSTREAM`, and `INTEGRATED` vocabularies, the
Pull Requests `STATE`, `REVIEW`, `CHECKS`, and `MERGE` vocabularies, the
Issues `◉` Issue state column (`■` in the state colour: open, completed, not
planned or duplicate) sit under their columns the same way, and the `✖`
error, `⚠` warning and `↻` observation severities the alert line and
Diagnostics share close the list. What is not a column has a section of
its own: the Worktrees pane's `x · Enter · y` actions, the Issues
`column headers` note that carries the `↕ ↑ ↓` sort markers and lists the
columns `c` can add, and the relationship emphasis under `RELATED ROWS`. The Legend is generated from the same column
definitions the panes build their tables from and the `Glyph` values the
cells render with ([`glyphs.py`](../src/dashpot/ui/glyphs.py)), each pane
owning its own vocabulary; a test scans the source for any symbol the
Legend does not explain, so a Glyph cannot be added without appearing there
and no symbol carries two meanings
([ADR 0010](adr/0010-derive-the-legend-from-rendered-glyphs.md)) — save the
`↑` that the Branches `INTEGRATED` cell and the Issues sort marker share,
each read on its own surface
([ADR 0040](adr/0040-summarize-integration-across-a-branch-rows-refs.md)) —
and an inventory test reads the pane specs and the Issue column catalogue,
so a column declared without a description or missing from the Legend fails
the gate
([ADR 0050](adr/0050-describe-every-pane-column-once-for-the-tooltip-and-the-legend.md)).
Its mouse complement is a header tooltip, offered by the shared
`FocusCursorTable` ([`focus_table.py`](../src/dashpot/ui/focus_table.py)) from
the segment meta the header render stamps, so it follows the hovered header
through scrolling, resizing, column choice and redeclaration, and the
conditional `PRIORITY` column, and clears over the body and on leaving.
Every header of every pane reads its column's description and Glyph
meanings from the same definition its Legend section is built from — the
list panes' `ListColumn` and the Issue table's `ColumnSpec` through the
`DescribedColumn` protocol in
[`list_rows.py`](../src/dashpot/ui/list_rows.py) — so neither can drift.
The descriptions are derived from the read models: each names the absent or
unknown value (`-`, `detached`, `no active Issue work`, `not fetched`,
`n/a`), which time an `ACTIVITY` or `UPDATED` age or a `LAST ACTION` date
names, and how fresh the fact is, and the Pull Requests `REVIEW`, `CHECKS`,
and `MERGE` descriptions say what each observation establishes and what it
leaves to the base Branch's protection rules. The Legend also lists every
shipped key, grouped by where it is pressed — global keys, each peer, the
Worktrees pane, and each temporary screen — and a test holds
it to every `BINDINGS` under `ui/`; the Branches `INTEGRATED` description
and the Worktrees actions note say what `x` checks — the `INTEGRATED` one
distinguishing the row summary from the Cleanup preview's per-target
checks — where the person deciding what to delete reads it. See
[`textual-implementation-notes.md`](textual-implementation-notes.md) for
the framework research behind the current implementation.

The completed [module ownership map](adr/0042-group-leaf-and-domain-modules-into-subpackages.md#completed-layout)
places coordination, accepted stores, and query read models in `observation/`,
and Textual runners, messages, widgets, and rendering in `ui/`. Observation
imports no UI modules. Shared list results carry typed summaries, and the
Workspace observation store owns snapshot indexing.
