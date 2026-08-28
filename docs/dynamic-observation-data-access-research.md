# Dynamic observation and data access in Dashpot

Research date: 2026-08-27

## Implementation status

The core architecture of Stages 1 and 2 is implemented. The Issue table now has
explicit query and view state, and `WorkspaceObservationStore` owns the latest
accepted observations, revisioned replacement, stable lookups, diagnostic
projection, and checkpoint export. The optional composite-widget/fake-result
test seam and detailed timing telemetry remain deferred. The collector still
delivers whole `WorkspaceSnapshot` values into the store; Stage 3 will split
their scheduling and delivery. Sections describing the old snapshot-owned
application state remain below as the research baseline.

## Executive conclusion

Dashpot's current `WorkspaceSnapshot -> build_rows()` path is adequate for the
first configurable filters, sorts, and column layouts. Those interactions do not
require another GitHub request or a database: the complete Issue profile already
contains the relevant fields, and a few thousand in-memory records are cheap to
scan until measurement says otherwise.

The limiting part is not that snapshots exist. It is that one whole-workspace
snapshot is currently all of these things at once:

- the result of source observation;
- the unit of refresh scheduling and failure delivery;
- the application-held current state;
- the input to every UI projection; and
- the headless export format.

The recommended foundation is therefore:

1. retain complete, atomic snapshots at each Issue Source seam;
2. introduce a queryable in-memory observation store holding the latest result
   for each independently refreshable Project/source observation;
3. make filters and sorts explicit read-model queries, and keep column layout as
   presentation state;
4. let complete per-Project results update the TUI without waiting for the slowest
   Project, while preserving per-source freshness and last-good semantics; and
5. keep `WorkspaceSnapshot` as an export/checkpoint assembled from the store, not
   as the only data-access interface.

This creates the seam needed for dynamic behavior without prematurely adopting
SQLite, event sourcing, webhooks, partial Issue objects, or server-side UI
queries.

## What exists now

### Collection

At the time of this research, `WorkspaceCollector.refresh()` took a global
lock, refreshed up to eight Projects concurrently, waited for every Project
result, then observed Agent Runs, resolved and persisted Issue bindings, and
finally returned one `WorkspaceSnapshot`. The lock was necessary because a
cancelled Textual worker cannot stop its synchronous executor call and each
Issue Source owns a mutable in-process last-good cache. Stage 3 below has since
been implemented as the [`ObservationCoordinator`](../src/dashpot/collect.py),
which keeps that per-source serialization at key granularity.

Each [`ProjectCollector`](../src/dashpot/collect.py) refreshes its Issue Source and
then discovers and inspects every Git worktree. These have different costs and
useful cadences, but they are one refresh unit. GitHub collection walks every
Issue page and every nested connection before returning; Local Markdown
enumerates and parses every Issue document. This is consistent with
[`ADR 0002`](adr/0002-require-complete-issue-profile-snapshots.md): a fresh source
observation is a complete collection, and one malformed or unavailable record
must not masquerade as deletion.

The consequences are:

- a fast Project cannot become visible until the slowest Project and workspace
  binding pass have completed;
- a quick-changing Agent Run cannot be refreshed independently of GitHub and
  `git status`;
- one unavailable Project delays delivery of every successful Project even
  though failures are eventually isolated in the result;
- the last-good cache exists only inside the live adapter instance; and
- refreshing more often to improve one observation's latency repeats all other
  observation work.

### Application state and projection

[`DashpotApp`](../src/dashpot/app.py) owns the last accepted
`WorkspaceSnapshot`. One exclusive worker runs the whole collector, and a
generation check rejects obsolete results. `build_rows()` then scans all observed
Issues, applies the current hard-coded open-state predicate, joins Agent Runs,
creates display strings, and `reconcile_rows()` diffs those cells into Textual's
`DataTable`.

The keyed reconciliation is already incremental at the widget seam: rows and
cells are added, removed, or changed by stable keys. Textual officially supports
keyed row removal and cell updates, as well as natural or key-function sorting
([DataTable data removal](https://textual.textualize.io/widgets/data_table/#removing-data),
[cell updates](https://textual.textualize.io/widgets/data_table/#update_cell), and
[sorting](https://textual.textualize.io/widgets/data_table/#sorting)). Replacing
the collection architecture is not a prerequisite for a better table.

The actual pressure point is that `build_rows()` is both query and rendering
code. Adding state, label, assignee, Project, text, and Agent Run filters directly
to it will turn the app module into an implicit query engine. Re-running a pure
in-memory query is acceptable; hiding the query specification inside widget code
is not.

## Separate four kinds of state

The architecture becomes clearer if Dashpot names four different things.

| Concern | Meaning | Atomicity / lifetime |
|---|---|---|
| Source observation | What one external source could establish at an attempt | Complete replacement for that source; carries attempted, last-good, and status metadata |
| Observation store | Latest accepted observations available to the application | Long-lived in memory; independently replaceable by Project/source observation |
| Read model | Rows or details answering a particular UI/headless query | Derived, disposable, and identified by a store revision |
| View state | Filter, sort, visible column order, and selection | User interaction state; must not alter source truth |

`WorkspaceSnapshot` currently spans the first three rows. It should remain a
valuable serializable view, but not be the only interface between collection and
consumption.

Column visibility and order belong entirely to view state. A hidden `updatedAt`
column must not mean Dashpot stopped observing `updatedAt`. Likewise, selecting
"open" in the table is a query over known Issues, not permission for the source
to forget closed Issues. That distinction is what preserves GitHub/Markdown
parity and complete-snapshot semantics.

## Recommended target shape

```text
Issue Sources      Git observers      Hook-record observer
     |                  |                      |
     +------- complete source observations -------+
                            |
                  ObservationCoordinator
             (scheduling, generations, binding promotion)
                            |
                   WorkspaceObservationStore
              (latest values, identities, revisions)
                     /                    \
       IssueListQuery -> rows        lookup Issue/Project
                     \                    /
                       Textual widgets

       store.checkpoint() -> WorkspaceSnapshot -> JSON
```

### Observation store

Start with a process-local implementation behind a narrow interface. The exact
names can change, but the responsibilities should look like:

```python
class WorkspaceObservationStore:
    def replace(self, snapshot: WorkspaceSnapshot) -> StoreChange: ...
    def replace_project(self, observation: ProjectObservation) -> StoreChange: ...
    def replace_agent_runs(self, agent_runs, issue_runs) -> StoreChange: ...
    def query_issues(self, query: IssueListQuery) -> IssueListResult: ...
    def project(self, project_id: str) -> ProjectObservation | None: ...
    def issue(self, issue_id: str, *, project_id=None) -> IssueContext | None: ...
    def diagnostics(self) -> tuple[ObservedDiagnostic, ...]: ...
    def checkpoint(self) -> WorkspaceSnapshot: ...
```

Internally, dictionaries keyed by stable Project, Issue, Observation Target, and
Agent Run identities are enough. A monotonically increasing `revision` lets a
consumer reject stale query results. `StoreChange` should report changed
observation kinds and identity sets so a consumer can choose between a targeted
detail update and a table re-query; it need not expose source-specific transport
events.

The store should retain conflicting Issue identities rather than overwrite them.
Project-qualified storage keys can preserve both observations while the existing
global-identity diagnostic remains visible.

Apply store changes on Textual's message-pump thread. Textual gives each App and
Widget a queued asyncio message pump
([Events and Messages](https://textual.textualize.io/guide/events/#message-queue)),
while its worker guidance says network, subprocess, and other work lasting more
than a few milliseconds should run concurrently
([Workers](https://textual.textualize.io/guide/workers/#concurrency)). Collector
workers can therefore post immutable result messages; the handler can replace
store state and query it without a second shared-state locking model.

Do not make the store's internal dictionaries Textual reactive collections.
Textual does not detect in-place mutation unless `mutate_reactive()` is called
([mutable reactives](https://textual.textualize.io/guide/reactivity/#mutable-reactives)).
A custom change message or a single replaced `revision` value is a clearer
invalidation signal.

### Explicit Issue-list query

The first read model can remain a simple scan and stable sort:

```python
@dataclass(frozen=True)
class IssueListQuery:
    states: frozenset[str] = frozenset({"open"})
    project_ids: frozenset[str] | None = None
    labels_all: frozenset[str] = frozenset()
    assignees_any: frozenset[str] = frozenset()
    text: str = ""
    sort: tuple[SortTerm, ...] = DEFAULT_SORT


@dataclass(frozen=True)
class IssueListResult:
    revision: int
    rows: tuple[IssueListRow, ...]
    matched_count: int
    observed_count: int
    coverage: tuple[SourceCoverage, ...]
```

Filter semantics should be source-neutral and tested against canonical Issue
profiles. `IssueListRow` should carry typed values used for sorting separately
from rendered Text/Rich strings. That avoids sorting priority glyphs or formatted
timestamps when the domain value is what matters.

The table's column catalogue is a different object: stable column key, heading,
cell renderer, sort extractor, and default visibility. The ordered set of visible
keys is a layout preference over a query result. Only a genuinely expensive or
not-yet-observed field should ever influence fetch planning.

Details should use `issue(issue_id)` and related lookups rather than retain the
entire nested `RowContext` from the last projection. Stable identity then remains
the selection contract even when filters, sorting, Project membership, or the
underlying observation revision changes.

### Freshness and consistency

The TUI does not need a fictitious workspace-wide instant. It needs honest
observation freshness:

- publish a Project's new Issue collection only after all pages, nested
  connections, normalization, and validation succeed;
- retain its previous Issues and mark the source stale on a failed refresh;
- never publish partially paginated GitHub results as a fresh replacement;
- preserve attempted and last-good timestamps per source observation; and
- show that different Projects or repository observations may have different
  observation ages.

GitHub requires cursor traversal until `hasNextPage` is false to complete a
connection ([GraphQL pagination](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api)).
Streaming each network page into the live store would therefore weaken the
existing meaning of `fresh` and make absence ambiguous. Pages may be accumulated
internally, but the store replacement remains atomic.

Issue binding also constrains progressive delivery. Bound identity is
Workspace-global and a hint is only reported after durable promotion. The
coordinator should continue to perform that promotion before publishing the
relationship. On cold start, it must distinguish "not observed yet" from
"observed absent" across configured Projects; otherwise a Project that has not
completed could make a transferred Issue appear missing. The store needs source
coverage/status, not just an Issue index.

For `--json`, run a coordinated refresh barrier and then call `checkpoint()` so
the command retains today's simple one-shot contract. An interactive TUI can
accept each completed Project/source observation immediately. This intentionally
gives the two consumers different delivery timing while keeping the same
observation facts and serialization.

## Staged migration

### Stage 1: extract the read model, keep collection unchanged — core implemented

This is the next Issue-list-pane slice.

1. Move filtering, domain sort keys, counts, and Issue/Run joining out of
   `build_rows()` into a framework-free `IssueListQuery` module.
2. Give the app explicit view state with the default `states={"open"}`.
3. Make `build_rows()` render an `IssueListResult` plus a column layout.
4. Keep the latest `WorkspaceSnapshot` as the query module's input for now.
5. Test queries synchronously and Textual interaction with a fake query result.

This supplies dynamic filters and sorts immediately, prevents table design from
dictating data collection, and establishes the eventual store query without an
infrastructure migration.

### Stage 2: put observations behind the in-memory store — core implemented

Seed the store from a `WorkspaceSnapshot`, have the query module read the store,
and make `checkpoint()` reproduce the existing headless shape. This is mostly a
change in ownership: application current state moves out of `DashpotApp`, while
the collector still delivers whole snapshots initially.

Measure query and reconciliation time separately. Useful telemetry is Issue and
visible-row counts, query milliseconds, table reconciliation milliseconds,
collection milliseconds by observation kind, and peak retained observation size.

### Stage 3: refresh and publish independently

Split the current Project refresh into independently scheduled observations:

- Issue Source per Project;
- worktree topology/status per Project or repository anchor group; and
- Agent Runs once per Workspace.

Use a worker group/generation per `(observation_kind, project_id)` rather than
one global refresh generation. A manual "refresh all" may fan these out, while a
Project action can refresh only that Project. Textual's exclusive workers cancel
older workers to prevent out-of-order UI results, but thread work itself cannot
be force-cancelled; the current subprocess timeouts and per-key generation
checks remain necessary. Textual documents both exclusive cancellation and the
need for thread workers not to update UI directly
([worker cancellation](https://textual.textualize.io/guide/workers/#cancelling-workers),
[thread workers](https://textual.textualize.io/guide/workers/#thread-workers)).

The first version can still poll. "Event-driven" here should mean that consumers
react to completed observation messages, not that Dashpot needs an event log or a
daemon. Polling GitHub, Git, and hook files at distinct cadences captures most of
the value with little operational cost.

### Stage 4: optimize inside sources only when measured

Keep any transport optimization behind the same complete-observation contract.

For Local Markdown, enumerate all configured files to detect addition and
deletion, but cache parsed canonical Issues by path plus verified content
fingerprint. Parse changed content and atomically assemble a complete new
collection. Modification time alone should be an optimization hint, not the
truth.

For GitHub, the schema supports Issue filtering by state, labels, assignee, and a
`since` timestamp, and ordering by created, updated, or comment count
([GitHub Issue filters and ordering](https://docs.github.com/en/graphql/reference/issues#issuefilters)).
GitHub also supports direct lookup by global node ID
([Using global node IDs](https://docs.github.com/en/graphql/guides/using-global-node-ids#3-do-a-direct-node-lookup-in-graphql)).
These are possible ingredients for an internal delta refresh or targeted detail
repair, not a reason to send each UI filter to GitHub.

An incremental GitHub adapter would require an initial full baseline, overlap in
the `since` window, complete re-fetch of every changed Issue and its nested
connections, and periodic full reconciliation. A delta from the old repository
does not by itself prove that an absent Issue was deleted, became inaccessible,
or transferred. Until those cases and relationship-update behavior have an
executable conformance contract, the current full sweep is the safer source of
truth.

Remote requests should be reduced deliberately. GitHub warns that deeply nested
or very large GraphQL queries can hit resource limits and recommends pagination,
filtering, splitting queries, and requesting only needed fields
([GraphQL rate and resource limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api#other-resource-limits)).
The `gh api` command also offers response caching
([GitHub CLI `gh api`](https://cli.github.com/manual/gh_api)), but a time-based
cache changes observable freshness and should only be used with explicit cache
semantics. REST conditional requests can make unchanged polling cheap, but that
is a REST transport option rather than an automatic fit for the current GraphQL
profile
([GitHub REST conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests)).

### Stage 5: adopt SQLite only behind the store interface, if needed

SQLite becomes justified if measurement shows one or more of:

- interactive scans/sorts exceed a chosen UI budget at realistic workspace size;
- startup or memory is dominated by retaining canonical Issue bodies;
- Dashpot needs durable offline last-good data across process restarts;
- users need indexed full-text search or observation history; or
- multiple processes need to share a read model.

At that point SQLite should be a rebuildable, schema-versioned read model, never
the authority for GitHub or Markdown domain state. Replace one Project's Issues
in a transaction, preserve conflicts with a Project-qualified key, and derive
indexes from actual query telemetry. SQLite can use indexes for lookup and
sorting, but its own documentation emphasizes that programmers must choose useful
indexes and that small full scans are acceptable
([SQLite query planning](https://sqlite.org/queryplanner.html)). FTS5 is available
if body/title search is the demonstrated need
([SQLite FTS5](https://sqlite.org/fts5.html)).

Do not share one default Python `sqlite3` connection across collector and UI
threads. Python defaults to enforcing same-thread connection use; disabling that
check requires the application to serialize writes
([Python `sqlite3.connect`](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.connect)).
WAL mode permits readers and a writer to proceed concurrently, but introduces
checkpoint and `SQLITE_BUSY` considerations
([SQLite WAL](https://sqlite.org/wal.html)). Neither complexity earns its keep for
an in-memory read model with one UI consumer.

## Alternatives assessed

### Query GitHub or Markdown directly for every table interaction

Reject as the default. It makes UI responsiveness depend on subprocess/network
latency, spends rate budget on reversible presentation choices, gives GitHub and
Markdown different query capabilities, and turns a filtered subset into an
ambiguous source observation. Server-side query features may optimize an adapter,
but should not define Dashpot's common Issue-list semantics.

### Fetch only the visible page or selected Issue

Defer. Viewport loading helps when the canonical collection itself is too large,
but global counts, filters, sorts, binding validation, transfers, and relationship
joins still need coverage semantics. The current complete Issue profile also
means the selected detail is already local. Introducing summary versus detail
profiles would be a domain-contract change, not merely a DataTable improvement.

### Make `WorkspaceSnapshot` immutable/reactive and recompute it more often

Insufficient. Replacing reactive state can trigger consumers cleanly, but it does
not separate observation scheduling, read queries, or freshness. In-place mutable
reactives add invalidation hazards; recomposition can also reset stateful widgets.
Use Textual reactivity for small view-state values or a store revision, not as the
data-access architecture.

### Event sourcing or a durable observation log

Reject for now. Dashpot observes current state from polling sources that do not
provide a complete ordered event stream. Fabricating domain events from snapshot
diffs adds replay, compaction, and schema-evolution obligations without helping
the next table uplifts. `StoreChange` is an ephemeral invalidation/delta, not a
claim about source history.

### GitHub webhooks

Defer unless Dashpot grows a daemon/service. A laptop TUI would need a reachable
receiver, authentication, delivery persistence, and reconciliation for missed
events. Distinct polling cadences and conditional/delta source work are a more
proportionate local-app path.

## Decision rules

The architectural commitments worth making now are:

- complete Issue Source observations remain the correctness seam;
- the latest all-workspace snapshot stops being the only query substrate;
- query/filter/sort semantics are owned by a source-neutral read model;
- visible columns are presentation state, not source selection;
- stable domain identities remain row, selection, join, and update keys;
- freshness and coverage travel with observations and query results;
- per-observation results may be delivered progressively, but partial source pages
  are never presented as complete fresh collections; and
- persistence and transport optimizations must fit behind the observation-store
  and source interfaces.

The concrete next move is Stage 3: independently schedule complete observations
and publish each accepted result into the store without weakening source coverage
or last-good semantics.
