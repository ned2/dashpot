---
status: living
date: 2026-09-04
---

# Design

Observation is scheduled per key rather than as one refresh: the Project's
Issue Source and its worktree topology are observed independently, and Agent
Runs are observed once per Workspace whenever the Project has been published. An
[`ObservationCoordinator`](../src/dashpot/collect.py) tracks a generation per key
so a superseded observation can never overwrite a newer one, retains the last
good result per key when a refresh fails, and composes each Project from its
latest accepted halves. The Textual interface publishes every accepted
observation into a process-local `WorkspaceObservationStore` as soon as it
lands, then re-queries source-neutral Issue-list read models carrying a store
revision; a slow GitHub call therefore never delays branch or dirty state.
A key is observed at most once at a time: a request for a key whose
observation is still in flight coalesces onto it rather than superseding it,
so a slow Issue Source that outlasts the polling period still publishes when
it lands instead of being discarded by every tick
([ADR 0020](adr/0020-coalesce-requests-onto-the-observation-in-flight.md)).
An automatic tick queues nothing further, the next tick being its rerun; a
key press, a Remote Fetch or Cleanup that changed the Repository, and a
follow-up of a publish each queue one more observation of the key for when
the running one lands. `r` refreshes every key in the Workspace, which with
one Project per run is the observed Project, and asks the GitHub Issue
Source for a Reconciliation. It never fetches: `f`
mutates, a Remote Fetch of the Repository Anchor whose refs
supplied the Branch observation ([`fetch.py`](../src/dashpot/fetch.py),
[ADR 0014](adr/0014-fetch-remotes-on-explicit-key-press.md)). It runs
off the event loop, once per Project at a time, and once any remote has been
fetched it schedules the passive Git observation of that Project, so the
Branches pane, the Integration Branch facts, and the fetch age reflect the
result without anything being inferred from the fetch itself.

`x` is the other mutating key, a Cleanup
([`cleanup.py`](../src/dashpot/cleanup.py),
[`cleanup_view.py`](../src/dashpot/cleanup_view.py),
[ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
The highlighted Branches or Worktrees row is resolved through the observation
store into a request against its Repository Anchor, the read-only preview is
inspected off the event loop, and a modal lists every concrete target
unselected — the local Branch, the Branch at each remote, the Worktree — with
its integration fact, blockers, and consequences beneath, disables the
unavailable ones (a Worktree's Branch among them while the Worktree cannot be
removed), asks for the Worktree's ignored content to be acknowledged,
and answers a premature press of the destructive button by deleting nothing,
saying why beneath the list and in a toast, and moving focus to what is
missing; the button is never disabled, since Textual would still light it
under the mouse and swallow the click silently, and it turns red once the
selection is one the performer accepts. `Escape` cancels. Confirmation performs off the
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

The GitHub Issue Source observes every Issue once, then refreshes
incrementally ([`github_issues.py`](../src/dashpot/github_issues.py),
[ADR 0022](adr/0022-refresh-github-issues-incrementally-between-reconciliations.md)):
each tick asks GitHub one one-point question — the newest update and the
Issue count — and an unchanged repository is answered by that alone, whatever
its size. When something changed, only the Issues updated since the
High-Water Mark are fetched, in pages of twenty-four, together with the other
end of every relationship they added or removed, and merged by identity. A
Reconciliation runs every five minutes, on `r`, and whenever the count no
longer adds up, because a deletion, a transfer, a linked pull request and the
blocker's side of a dependency leave no trace a delta can see: every Issue
already known is observed afresh by identity, in batches of twenty-four sent
through the gateway with at most four in flight
([ADR 0023](adr/0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)),
then the delta since the High-Water Mark, and only a count those cannot
explain falls back to the sweep in order of creation; an Issue is removed
only on positive evidence. A Reconciliation the Refresh Budget abandons is
retried a period later while the ticks between keep refreshing
incrementally, and one more than two periods overdue is reported as a
warning. The research behind the shape of every query is in
[`docs/github-api-batching-research.md`](github-api-batching-research.md).

Exceptional state is summarized in a
one-line alert above Diagnostics that takes no space while everything is
healthy: refresh failures and unavailable Projects are errors, unavailable or
stale worktrees and stale Issue Sources are warnings, and a refresh that has
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

The main screen is a single pane of glass with no Header, so every row
belongs to a list: from the top,
the full-width `SESSIONS`, `WORKTREES` and `BRANCHES` panes stack above the
full-width `ISSUES` table. Nothing is switched to: every active Agent
Session, every observed Worktree and every Branch is listed in its pane, with
the count in the pane title and an honest one-line empty state. The panes are
sized to their content rather than sharing the flex height: each asks for the
rows it has up to a cap of eight and scrolls beyond it, the smallest wish is
granted first so an empty pane costs three lines, and the caps shrink before
the Issue table would drop below its minimum height, so the panes only ever
cost the Issue table what they actually use. The Sessions list starts with
focus, `Tab` and `Shift+Tab` cycle focus Sessions → Worktrees → Branches →
Issues, and `/` moves it to the Issue search. The row cursor in the Sessions,
Worktrees and Branches panes is for scrolling, copying and refresh scope (`r`); only
the Issue table drives the Issue selection, `Enter`
on an Issue opens it in the full-screen Issue view (its location on the left
of the heading line, `opened 3d ago by ned2` on the right, and both panes'
borders in the Issue's state colour), and `Enter` on a session with an Issue
Binding highlights that Issue in the Issue table. The Sessions pane is its own read model
([`session_list.py`](../src/dashpot/session_list.py), queried through
`WorkspaceObservationStore.query_sessions`): every active Agent Session of the
observed Project exactly once, sorted running → waiting → unknown and then by
most recent activity, with any bound Issue joined from the Work Store's
accepted bindings, an `outside Project` marker in place of a target the
observed Project does not own, an intentional `no active Issue work` value
when unbound, its working directory relative to its Observation Target, and
long paths, branches and titles clipped with an ellipsis. Its columns are
`STATE`, `HARNESS`, `TARGET`, `BRANCH`, `ISSUE`, `DIRECTORY`, and
`ACTIVITY`. `TARGET` is dropped
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
is likewise its own read model ([`worktree_list.py`](../src/dashpot/worktree_list.py),
`WorkspaceObservationStore.query_worktrees`): every observed Observation
Target of the Project, identified by `(Project Identity, target path)`
and sorted main before linked, then path, with its Git topology kind (`main` or
`linked`) reported in its own column,
and exceptional `stale` or `unavailable` state. Its five columns are `PATH`,
`KIND`, `BRANCH`, `TREE`, and `SESSIONS`: `KIND` distinguishes Git's `main`
and `linked` Worktrees, normal Branches omit HEAD, detached checkouts
include their short HEAD, the working tree remains clean/dirty/unknown, and
the last column counts the active Agent Sessions located there. `PATH` keeps
the full home-abbreviated path and the table scrolls horizontally when its
content is wider than the pane. Healthy rows
do not repeat `available`. Target-specific diagnostics stay in Diagnostics
and the alert line; the row only points there. The
Branches pane ([`branch_list.py`](../src/dashpot/branch_list.py),
`WorkspaceObservationStore.query_branches`) joins the local ref and the
Remote-Tracking Branches of one branch name into one row, so a branch is
never listed twice and never needs a second pane. `LOCAL` and `REMOTE` show
`✓` when a ref exists in that namespace: `LOCAL` is a ref under `refs/heads`,
and `REMOTE` is a Remote-Tracking Branch as of the last fetch, which can
outlive the Branch at the remote until a fetch prunes it, so the Legend
qualifies the check with the fetch age the border carries and the `f` key
that prunes. `UPSTREAM` is the local ref's
relation to its configured upstream (`=` in sync, `↑2 ↓1`, `∅` no upstream,
or `✗` upstream gone). `INTEGRATED` is whether the Integration Branch holds
the Branch's work (`⊆` when every commit is reachable, `≡` when its content is
there though its commits are not, as after a squash merge, `↑2` for two commits
of work that never landed, or `⊘` when no comparison is available). It uses the
local ref when present; a remote-only row uses its Remote-Tracking Branches
when they agree on one head and result, and reports `⊘` when they diverge. The
result is followed by the active sessions on the Branch and
the age of its last commit. The pane subtitle names the Integration Branch
and the age of the Remote-Tracking Branches. The Worktrees pane names the
Branch checked out at every Worktree. Rows are sorted checked-out first, then
most recent commit. Its seven columns are `BRANCH`, `LOCAL`, `REMOTE`,
`UPSTREAM`, `INTEGRATED`, `SESSIONS`, and `LAST COMMIT`. The
refs are read with `git for-each-ref` from the first answering Repository
Anchor; observation never runs `git fetch`, so the lower-right pane border
carries the age of the last fetch (`remote last fetched 3h ago`, or
`remote never fetched`) as the honest freshness of everything remote
([ADR 0005](adr/0005-observe-branches-without-fetching.md)), and `f`
fetches and prunes that anchor's remotes on request
([ADR 0014](adr/0014-fetch-remotes-on-explicit-key-press.md)).

The panes trade words for Glyphs to stay narrow, and `?` opens the Legend
that explains every one of them ([`legend.py`](../src/dashpot/legend.py)). Its
sections follow the screen top to bottom and name the column a Glyph appears
in: the Sessions family `●` running, `◐` waiting and `○` unknown (also
leading the Agent Session count in the Branches and Worktrees `SESSIONS`
columns), the Branches presence, `UPSTREAM`, and `INTEGRATED` vocabularies
above, the Issues table's `◉` Issue
state column (`■` in the state colour: open, completed, not planned or
duplicate), its `◈` Agent Run state column (`▶` running, `Ⅱ` waiting, `?`
unknown, blank for no Agent Run), the `↕ ↑ ↓` sort markers on its headers,
and the `✖` error, `⚠` warning and `↻` observation severities the alert line
and Diagnostics share. The Legend is generated from the `Glyph` values the
cells render with ([`glyphs.py`](../src/dashpot/glyphs.py)), each pane owning
its own vocabulary, and a test scans the source for any symbol the Legend
does not explain, so a Glyph cannot be added without appearing there and no
symbol carries two meanings
([ADR 0010](adr/0010-derive-the-legend-from-rendered-glyphs.md)). Its
mouse complement is a tooltip on the Issues table's `◉` and `◈` headers that
reads the same `Glyph.meaning` the Legend shows, so the two cannot drift. The
Legend also lists the key bindings, and the notes under the Branches
`INTEGRATED` and Worktrees `SESSIONS` sections state the gate `x` applies,
where the person deciding what to delete reads it. See
[`textual-implementation-notes.md`](textual-implementation-notes.md) for
the framework research behind the current implementation.
