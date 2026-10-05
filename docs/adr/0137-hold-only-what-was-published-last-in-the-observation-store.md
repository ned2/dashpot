---
status: accepted
date: 2026-10-05
---

# Hold only what was published last in the observation store

The dashboard became query-driven
([ADR 0033](0033-query-pages-and-independent-issue-resolution.md)): its
Issue and Pull Request panes show the pages a Query Source answers, and its
coordinator schedules only each Project's Repository State and the Agent
Runs. The headless `--json` export observes each Project once, through the
same Query Source's Source Enumeration, into a fresh store.
[#548](https://github.com/ned2/dashpot/issues/548) found the observation store
and the collector still carrying the paths that served the snapshot-driven
dashboard before that, which nothing shipped consulted any more:

- **Retention in the store.** `WorkspaceObservationStore` kept a Project's
  last good Issues and Pull Requests across a failed replacement, and an
  Issue's Agent Run bindings across an unavailable one. A query-driven
  Project publishes no Issues to retain, and the export's store has no
  earlier Project, so only tests reached it.
- **A local query engine.** The store answered Issue and Pull Request
  queries from its snapshot, with the search text, lifecycle and qualifier
  semantics of a provider. The dashboard lists the accepted page instead;
  the tests' fake Query Source called the engine to fake GitHub's search.
- **Detail by identity.** `issue()`, `detail_for` and `IssueContext`
  resolved an Issue against the snapshot, with rules for an identity two
  Projects share. The paged store resolves a row against its page and the
  Resolved Issues.
- **Fine-grained change sets.** Each publish reported which Projects,
  Issues, Pull Requests, Observation Targets, Branches and Agent Runs it
  changed, and every read model carried the store revision. The dashboard
  reconciles after every publish and reads only whether a publish changed
  what Agent Run binding depends on.
- **Two construction paths.** `create_project_collector` built an Issue
  Source and a Pull Request source, then observed through a Query Source
  that builds its own; the first pair served only tests.
  [ADR 0043](0043-retain-distinct-query-and-collection-adapters.md) accepted
  these unused fallback sources as redundant construction.

## Decision

The store holds what was published last and nothing older.

- **Retention happens before publish.** A source that keeps its last good
  observation does so itself, and the coordinator keeps a key's last good
  half when its observation fails. The store accepts a Project as published.
- **The pages are the lists.** The Issue and Pull Request panes list the
  accepted page in the source's order. `PagedObservationStore.query_issues`
  takes no query, and `detail_for` resolves a row against the page and the
  Resolved Issues. The store has no Pull Request list of its own.
- **A store never forgets a Project.** `replace_project` adds or replaces
  one. A page's Issue therefore joins its Project once that Project is
  published, with no memory of Projects a page named earlier.
- **A publish reports what Agent Runs depend on.** `StoreChange` carries
  only the Projects whose binding facts changed, which is what schedules the
  Agent Runs' follow-up. The store's `revision` stays a count of commits;
  read models carry none.
- **One collector path.** A `ProjectCollector` observes Issues and Pull
  Requests through its Project's Query Source alone. Before building it,
  `create_project_collector` checks that the Repository Anchor can serve the
  configured Issue Source, so a GitHub Project without a GitHub origin
  remote still fails once. `build_issue_source` stays for Issue resolution,
  which reads one Issue Source directly. The coordinator builds each
  Project's collector once, however many of its halves ask at the same time.
- **`replace` stays as the seeding seam.** `replace(snapshot)` accepts a
  whole Workspace Snapshot in one commit. The test suite seeds stores and
  the scripted harness scheduler publishes through it; production publishes
  one Project and the Agent Runs at a time.

The fake search the harness's Query Source needs lives in test support, as a
stand-in for the provider rather than a copy of its semantics.

## Considered options

- **Keep the snapshot read path and name its consumer.** The Issue named
  this as the alternative. The only consumers were tests and the harness's
  fake search, so keeping it would preserve a second set of query semantics
  that no shipped path checks against the provider's.
- **Keep the retention for a future snapshot consumer.** A consumer that
  needs a last good observation can retain it at its source, as the
  coordinator and the retaining sources already do, without the store
  judging which failure may overwrite which success.

## Consequences

- Tests seed a store with `replace` and list an Issue page through the
  harness's Query Source, so they drive the paths the dashboard takes.
- A store-level test can no longer pin a change set finer than the Agent
  Run dependency; a test that needs one asserts the read model instead.
- The export enumerates each Project once, with one collector per Project.
- An Issue Identity two Projects observe is no longer listed once per
  Project, and the rule that no Worker counts toward such an Issue
  ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md))
  goes with the snapshot Issue list that applied it: a Query Page answers
  for one Project.
