---
status: living
date: 2026-09-05
---

# Domain language

Dashpot uses the following terms consistently across its interface, code, and
documentation. The _Avoid_ notes distinguish similar concepts; they are usage
guidance rather than a conformance standard.

## Declared work

**Project**:
A durable body of work rooted in exactly one Git Repository. It remains the same
Project across checkout moves, clones, branches, and worktrees.

**Git Repository**:
The single logical Git repository that roots a Project. Its hosting location and
local checkouts may change without changing the Project.
_Avoid_: Repository when referring to a checkout path

**Repository Identity**:
A stable opaque identity for a Git Repository, independent of remote URLs and
local checkouts.

**Issue**:
A declared unit of Project work conforming to Dashpot's source-neutral Issue
model. An Issue may be represented on GitHub or in local Markdown.
_Avoid_: Task, work item

**Issue Profile**:
The source-neutral set of facts every Issue Source must provide for an Issue. A
profile is complete; unavailable source facts are observation failures rather
than ambiguous Issue values.

**Issue Provenance**:
Source-specific evidence identifying the representation from which an Issue was
observed. Provenance does not participate in semantic equivalence.

**GitHub Issue**:
The GitHub Issues representation of an Issue.

**Pull Request**:
An active proposal to integrate one head Branch into one base Branch of the
Project's Git Repository, observed from the configured GitHub repository. Its
opaque GitHub node ID is identity; its Pull Request Number is only a compact
Project-local label. Dashpot observes open Pull Requests, including drafts,
independently of the Project's Issue Source collection.
_Avoid_: Linked Pull Request for a repository-wide Pull Request; Issue for a
Pull Request merely because GitHub shares their number space

**Linked Pull Request**:
A pull request GitHub reports as closing a GitHub Issue, shown with the
Issue's engagement facts rather than in its profile. The first twenty are
listed in Pull Request Number order and the count of any beyond them is shown
beside the list; the GitHub Issue Source pages the complete connection for
incremental relationship evidence. A Linked Pull Request appearing or changing
state does not update the Issue. The GitHub Issue Source instead observes the
changed Pull Request's current and previous Issue targets by identity; the
next Reconciliation remains the fallback for a derived connection whose
indexing outlasts both confirming scans
([ADR 0025](adr/0025-observe-linked-pull-requests-from-pull-request-changes.md)).
_Avoid_: using this Issue relationship as the repository-wide Pull Request
observation

**Local Issue**:
The local Markdown representation of an Issue.

**Issue Source**:
The authoritative representation through which a Project declares its Issues.
A Project has exactly one active Issue Source.

**Project Identity**:
A stable opaque identity for a Project, independent of repository hosting and
local filesystem location.

**Project Display Label**:
A mutable, human-readable label for a Project. It helps people recognize a
Project but never participates in identity.
_Avoid_: Project name when identity is intended

**Issue Identity**:
A stable opaque identity for an Issue, globally unique within Dashpot's Issue
universe and independent of its Project membership, reference, and location.

**Issue Number**:
A positive Project-local integer used as an Issue's compact human label, such
as `#16`. It may change with Project membership and never participates in Issue
identity.

**Issue Reference**:
A mutable, human-readable shorthand for an Issue, such as `ned2/dashpot#9` or a
local slug.

**Issue Location**:
An actionable, mutable locator for an Issue, such as a GitHub URL or a Markdown
file and line number.

## Observation

**Workspace**:
The named set of Repository Anchors that resolves to the one Project a Dashpot
run observes. It owns no Project configuration or work state and never
participates in Project or Issue identity; anchors resolving to more than one
Project are refused before observation starts.

**Repository Anchor**:
A configured local checkout through which Dashpot locates a Project and asks Git
for its linked worktrees. It is also the authoritative checkout for Local Issues.

**Worktree**:
A local working tree of a Project's Git Repository, including its main working
tree and any Git-linked working trees.

**Observation Target**:
A Worktree Dashpot discovered and refreshes at runtime. It is observed state,
not persisted Workspace membership or durable identity.

**Branch**:
A named line of development of a Project's Git Repository, observed as a
local ref (`refs/heads/*`) and as any Remote-Tracking Branches of the same
name. Identity is the full refname; a branch name that is only local or only
remote is a fact about the branch, not a different kind of record.

**Remote-Tracking Branch**:
The Repository's local copy of a remote's branch (`refs/remotes/<remote>/*`),
as of the last `git fetch`. Observation reads it and reports its age; only a
Remote Fetch brings it up to date.
_Avoid_: remote branch for the local copy, which may be behind the remote

**Remote Branch**:
A branch as it exists at a remote. Observation never sees it directly: its
Remote-Tracking Branch is the last-fetched copy, and only a Remote Fetch or
the outcome of a leased push says anything about its current state. A
Cleanup target is a Branch at one named remote, never the Remote-Tracking
Branch that stands for it.
_Avoid_: Remote-Tracking Branch for the branch at the remote

**Remote Fetch**:
A named mutation the dashboard performs, on the `f` key: `git fetch --prune`
of every configured remote, one remote at a time, at the single Repository
Anchor whose refs supplied the Branch observation. It is bounded by the Git
timeout, non-interactive, reported remote by remote, and followed by a
passive re-observation of that Project's Git state; a refresh never fetches.
_Avoid_: refresh for a fetch, or fetch for a refresh

**Cleanup**:
The explicitly confirmed removal of concrete targets a person selected from
a read-only preview: a local Branch, a Branch at one remote, or a linked
Worktree, each with its own gate, outcome, and recovery facts. Integration
makes a Branch target eligible; the selection is the authority. Confirmation
re-inspects and performs nothing when the preview has changed; a successful
mutation is never rolled back, and the Project is re-observed afterwards
([ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
Invoked from the dashboard's `x` key on a Branches or Worktrees row and from
the `branch delete` and `worktree remove` commands.
_Avoid_: prune for a Cleanup, which is the Remote Fetch's removal of gone
Remote-Tracking Branches; cleanup for anything observation does

**Integration Branch**:
The Branch against which Dashpot observes whether every commit of an observed
Branch ref is reachable: `origin/HEAD`, else the unique local `main` or
`master`. It is selected from local Git facts and never fetched. Integration
is exact commit reachability first; a Branch whose commits are not reachable
is then integrated by content when merging it would leave the Integration
Branch's tree unchanged or its squash commit is found there. A
Remote-Tracking Branch's result is only as fresh as the last Remote Fetch
([ADR 0017](adr/0017-observe-branch-integration-by-content-when-commits-are-unreachable.md),
[ADR 0018](adr/0018-assess-remote-tracking-branch-integration.md)).
Patch equivalence is not used, so a cherry-pick remains unintegrated until a
person reviews it.
_Avoid_: upstream, which is a local Branch's configured synchronization target

**Repository State**:
The observed Git facts of one Project's Repository as one carrier: its
Observation Targets and Branches, with when the Remote-Tracking facts were
last fetched, which Integration Branch reachability compares against, and
which Repository Anchor supplied the Branches. It is observation, never
configuration or identity.

**Diagnostic**:
One line an observation reports beside its data: its source, a stable code, a
severity, and a message a person can act on. A failed refresh reports one
Diagnostic and retains the last good result; a complete refresh may still
carry a warning (a rate limit running low). Codes are prefixed by the source
family — a GitHub Issue Source reports `github-authentication`,
`github-permission`, `github-not-found`, `github-repository`,
`github-rate-limit`, `github-rate-limit-low`, `github-refresh-budget`,
`github-reconciliation-overdue`, `github-issue-count`, `github-timeout`,
`github-network`,
`github-pagination`, `github-malformed-response` and `github-profile` — and
are read from the tracker's structured signals before its prose. A Project
whose Issue Source is Local Markdown reports `pull-requests-not-configured`
rather than inferring GitHub hosting from a Git remote
([ADR 0021](adr/0021-bound-each-github-refresh-by-a-budget.md)).

**Refresh Budget**:
The bound on what one refresh of a GitHub observation may fetch before it is
abandoned: a number of requests and a wall-clock duration, each checked
before the next request is sent. An abandoned refresh is a failed refresh,
reported by one `github-refresh-budget` Diagnostic naming what it fetched,
with that observation's last good collection retained; nothing partial is
ever published
([ADR 0002](adr/0002-require-complete-issue-profile-snapshots.md),
[ADR 0021](adr/0021-bound-each-github-refresh-by-a-budget.md),
[ADR 0023](adr/0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)).

**Incremental Refresh**:
How a GitHub Issue Source refreshes after its first complete observation: a
one-point combined change probe, then only the Issues updated since their
High-Water Mark and the other ends of any relationship they changed, plus a
newest-first Pull Request prefix when its separate mark advances, merged by
Issue identity into the collection it last observed. A fresh observation may
be assembled this way; an Issue or Linked Pull Request leaves the collection
only on positive evidence, never for being absent from a delta or prefix scan
([ADR 0022](adr/0022-refresh-github-issues-incrementally-between-reconciliations.md),
[ADR 0025](adr/0025-observe-linked-pull-requests-from-pull-request-changes.md),
[ADR 0027](adr/0027-keep-the-graphql-change-probe-authoritative.md)).

**High-Water Mark**:
The newest `updatedAt` the GitHub Issue Source has observed in one change
stream, the inclusive start of its next delta or newest-first prefix scan. It
keeps separate Issue and Pull Request marks. A mark advances only through what
a refresh fetched, so no clock of Dashpot's ever enters the boundary; a Pull
Request candidate is scanned on two ticks before it is settled because
GitHub's derived closing-reference connection indexes asynchronously.

**Reconciliation**:
An observation of every GitHub Issue afresh, which alone can see a Linked Pull
Request's derived closing-reference connection when its indexing outlasts
both confirming scans; a blocker-side dependency change; a parent/sub-Issue
relationship change; a deletion or transfer whose Issue-count change is
offset by another collection change in the same window; an update in the same
second as its High-Water Mark; or a fact GitHub does not date on the Issue — a
label's colour, a milestone or Issue type renamed — on an Issue that was not
itself updated. Issue-type changes are also covered conservatively because
their `updatedAt` behaviour could not be exercised in the user-owned
repository where it was researched. Every Issue already known is observed by
identity, in batches of twenty-four with at most four in flight, then the
delta since the High-Water Mark. Only a count those cannot explain marks the
sweep in order of creation for the next refresh, under a Refresh Budget of its
own; that sweep is also how a run starts. Each refresh publishes one complete
observation or fails; it never mixes the identity Reconciliation with a partial
sweep. Reconciliation runs on the Project's configured period (five minutes by
default), on `r`, and whenever
the Issue count no longer adds up; the period must be positive and at least the
polling period. An observation whose Reconciliation is more than two periods
overdue carries a
`github-reconciliation-overdue` warning, and one whose count remains
unexplained after a Reconciliation carries
`github-issue-count`
([ADR 0022](adr/0022-refresh-github-issues-incrementally-between-reconciliations.md),
[ADR 0023](adr/0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md),
[ADR 0025](adr/0025-observe-linked-pull-requests-from-pull-request-changes.md),
[ADR 0026](adr/0026-run-fallback-sweeps-under-their-own-refresh-budget.md)).
_Avoid_: reconciling for the dashboard's own reuse of table rows and pane
entries, which is a widget concern, not an observation.

**Observation Location**:
Where an agent session is executing, such as a branch, Worktree, or working
directory. It is evidence about execution, never Project or Issue identity.

**Agent Session**:
The lifetime of one harness conversation or process, such as a single Codex
run. A session is never permanently bound to an Issue; its lifecycle state
(running, waiting, or unknown) and activity age (how long the current turn
has run, or how long it has been idle) are observations of the session
itself, taken at turn boundaries.

**Agent Run**:
A time-bounded period during one Agent Session when it is explicitly working
on exactly one Issue. Starting, switching, or stopping Issue work begins or
ends Agent Runs without ending or restarting the session. A live Agent
Session holds at most one active Agent Run across the linked Worktrees of one
Git Repository: a session that has moved to another Worktree of the same
Repository and starts work there switches its run rather than adding one
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
_Avoid_: Agent Run as a synonym for the whole session; a second run at
another Worktree for a session that has relocated

**Agent Session Identity**:
The stable, opaque identity a harness gives one Agent Session, as its
lifecycle hooks publish it. It identifies the session where its host process
cannot be observed, such as from a sandbox's isolated process namespace, and
is only ever accepted when the harness's own hook record confirms it.
_Avoid_: session key, which is the Work Store's record name, and process
identity, which is evidence of Session Liveness

**Harness Adapter**:
The per-harness contract through which Dashpot identifies an Agent Session
from a command running inside it: which host process is the harness itself
(never a sandbox helper) and what Agent Session Identity the command can see.
Work Store and observation code speak to the adapters and never to one
harness's internals.

**Session Liveness**:
An observation of whether an Agent Session's recorded host process is live,
gone, or unknown. Unknown means the process could not be observed and is never
evidence that the session ended.

**Orphaned Agent Run**:
An active Work Store record whose Agent Session is gone. It is actionable
because it affects declared Issue work; a gone session without one is only
stale observation state.
_Avoid_: orphaned session for a gone unbound session

**Work Store**:
The versioned, Project-local record of active Agent Runs. Each record is
stored beneath the Worktree its run is at (`.dashpot/state/`), and the records
at all linked Worktrees of one Git Repository are jointly the sole authority
for which sessions are working on which Issues in that Repository
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
Independent clones keep distinct Work Stores
([ADR 0003](adr/0003-prefer-project-local-dashpot-state.md)).
_Avoid_: treating one Worktree's records as the whole authority for a session
that may have moved to another Worktree of the same Repository

**Issue Binding**:
A durable association between an Agent Run and an Issue by Issue Identity,
created by an explicit opt-in from the running session and stored in the Work
Store. It survives changes to Project membership, Issue Reference, and Issue
Location and is observed relationship state rather than part of the Issue
entity.

**Issue Hint**:
A mutable Issue Reference used only to establish an Issue Binding at opt-in
time. A hint never becomes identity and must resolve unambiguously within the
observed Project.

**Issue Worktree**:
A linked Worktree `dashpot worktree create` prepared for an Issue, on a new
Branch from a base commit that carries the Project's configuration
([ADR 0011](adr/0011-prepare-issue-worktrees-by-convention.md)). Its
path and Branch name are Issue Hints for people and launchers; only a
`work start` run inside a session there creates an Issue Binding, and one
Issue may have any number of Issue Worktrees.
_Avoid_: "the" Worktree of an Issue; reading a Worktree or Branch as Issue work

**Worktree Root**:
The machine-local directory new Issue Worktrees are created under:
`--worktree-root`, else `DASHPOT_WORKTREE_ROOT`, else the `worktreeRoot`
setting, else the sibling `<anchor name>.worktrees/` of the Repository
Anchor. It is never part of the tracked Project configuration.

## Presentation

**Glyph**:
One rendered symbol paired with the fact it stands for and, when the cell
colours it, its light and dark colour. Every pane renders from `Glyph`
values, so a symbol is never separated from its meaning, and a symbol has one
meaning wherever it is seen.
_Avoid_: icon or symbol for the value; the symbol is one field of a Glyph

**Legend**:
The listing of every Glyph the main screen renders, generated from the same
`Glyph` values the cells render, organised by the pane and column the Glyph
appears in and reachable with `?` from inside the app.
_Avoid_: help screen; the Legend also lists the keys, but it explains what is
on screen rather than how to use the app
