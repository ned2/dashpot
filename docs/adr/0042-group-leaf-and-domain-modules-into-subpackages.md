---
status: accepted
date: 2026-09-17
---

# Group leaf and domain modules into subpackages

The [codebase review](../codebase-review-2026-09-13.md#proposed-subpackage-layout)
derives a package layout from the import graph and shared domain language.
[Issue #188](https://github.com/ned2/dashpot/issues/188) implements its first
stage: `core` holds shared infrastructure and observation values, `project`
holds configuration and Workspace resolution, `github` holds the gateway and
wire adapters, `issues` holds Issue Sources and resolution, and `queries` holds
source queries and page navigation. These groups make the existing boundaries
visible without changing behavior or introducing new dependency rules.

The Pydantic infrastructure is named `core/pydantic.py`, removing the ambiguous
`model.py` / `models.py` pair. `core/model.py` holds observation models;
`RepositoryAnchor`, `Workspace`, and `ResolvedProject` belong to
`project/workspace.py`. The leaf-package initializers stay empty, so importing one leaf module does
not load its siblings. Consumers import the owning module directly unless a
package defines an explicit public seam, as Cleanup does below.
No old-path re-export shims are added: Python internals are outside the
[alpha compatibility contract](0034-publish-an-alpha-with-patch-compatible-interfaces.md).
The existing top-level exports retain their names.

The first stage left sessions, repository observation, and UI modules at the
root for the following Issues, as #188's explicit scope required. Its acceptance
bullet describing a root containing only entry points, assets, and packages is
the eventual layout after those later moves. The CLI and hook entry points,
serialization, stylesheet, skills, and `py.typed` remain at their existing paths.
Tests, tools, and documentation follow moved modules; fresh-interpreter checks
continue to protect headless and lightweight import paths.

[Issue #189](https://github.com/ned2/dashpot/issues/189) implements the next
stage: `sessions` owns harness adapters, process and liveness observation,
session matching, the Work Store, hook records and publishing, claim validation,
scanning and Work Store reconciliation, Agent Run observation and binding,
Issue work, and integration installation. Shared timestamp helpers live in
`core/timestamps.py` because sessions, repository observation, and source
adapters all consume them. The `sessions` initializer stays empty and consumers
import each owning module directly, with no old-path shims.

`hook.py` remains the root entry point. Integration resolves the bundled
`skills/` from the package root rather than beside its relocated module, so
installed hook publishers and skill installation retain their existing paths
and behavior. Repository observation and UI follow in the stages below.

[Issue #190](https://github.com/ned2/dashpot/issues/190) groups Git observation,
Remote Fetch, Worktree launching, and Cleanup selection under `repository`.
Cleanup splits into `targets` (requests and preview evidence), `preview`
(read-only inspection), `perform` (confirmed execution and its report), and
`adapter` (the dashboard seam). Its package initializer exposes the public
Cleanup interface used by the CLI, serialization, and UI. Execution retains
preview re-inspection, explicit target selection, remote-first ordering, leased
remote deletion, and unforced Worktree removal.

Worktree creation and removability have separate owning modules beneath
`repository/worktrees`, sharing base-ref resolution in `base.py` and topology-record lookup helpers
in `records.py`. The Worktrees initializer stays empty: Cleanup imports removal
checks without loading Issue-worktree creation. The split modules are about
600 lines or fewer; the cohesive `repository/repository.py` observation module
is deliberately exempt from that size target.

Root-level `composition.py` owns observation options, collector and Query Source
construction, configured Cleanup protection, and preview/select/perform
orchestration returning a report. The CLI retains argument parsing, commands,
rendering, and exit-status mapping. Composition never imports the CLI. This is
an intentional root-level file beside the entry points and serialization.
The coordinator's `query_driven` flag names the existing mode in which source
pages are observed separately from local Repository State and Agent Runs;
its scheduling behavior is unchanged. The final stage below completes the Observation and UI moves.


## Completed layout

[Issue #191](https://github.com/ned2/dashpot/issues/191) completes the structural
arc. `observation` owns the coordinator, accepted stores, related-row joins,
and the five query read models. `keys.py` owns scheduling keys, tickets, and
outcomes, so alerts need not import the coordinator. `ui` owns the Textual
runners as well as widgets and rendering: both runners consume the Textual
messages and host protocols in `ui/messages.py`. No protocol split is needed
for the current consumers. Observation imports neither UI nor Textual; fresh
interpreter checks import the actual modules as well as the empty package.
Session-state ordering belongs to the session read model and is reused by the
Glyph legend, preserving that dependency direction.

One `ListResult[Row, Summary]` carries rows, revision, and count. The second
type parameter preserves the existing Issue counts, Pull Request counts and
freshness, and Branch repository facts in typed summaries; Sessions and
Worktrees use `None`. This refines the review's proposed `ListResult[Row]`:
the five old carriers were not interchangeable rows/revision pairs, and
flattening their distinct facts would weaken the interface. Their query
semantics stay unchanged. `WorkspaceObservationStore` alone indexes accepted
snapshots; tests use that seam instead of five snapshot-rebuilding functions.
Issue rows no longer carry a constant kind or unused Project-wide runs, and
pane refresh values no longer carry an unset title count.

`issues/retaining_source.py` belongs to complete-collection sources.
`core/observation_errors.py` supplies the shared failure classification without
requiring query adapters to import the coordinator. The stylesheet remains at
the root and `ui/app.py` resolves it through `../dashpot.tcss`, including in
installed distributions.

The ownership map below accounts for every shipped Python module. Package
initializers belong to their package; they are empty except the documented
Cleanup facade. Root `__init__.py` retains its existing public exports. Root
`__main__.py`, `cli.py`, and `hook.py` are entry points, `composition.py` wires
the application, and `serialization.py` owns published output. The only root
assets are `dashpot.tcss` and `py.typed`; `skills/` holds the bundled workflow.

| Package | Owned modules (excluding initializers) |
| --- | --- |
| `core` | `ages`, `commands`, `errors`, `file_locks`, `git`, `issue_profile`, `json_records`, `model`, `observation_errors`, `pydantic`, `record_store`, `timestamps` |
| `github` | `github`, `github_issues`, `github_pull_requests`, `github_repository`, `github_wire` |
| `issues` | `issue_resolution`, `issue_sources`, `local_markdown_issues`, `pull_request_search`, `pull_request_sources`, `retaining_source`, `search`, `source_factories` |
| `observation` | `branch_list`, `collect`, `issue_list`, `keys`, `list_result`, `observation_store`, `paged_store`, `pull_request_list`, `related_rows`, `session_list`, `worktree_list` |
| `project` | `init`, `project_config`, `settings`, `workspace` |
| `queries` | `github_queries`, `markdown_queries`, `page_navigation`, `query_source`, `source_queries` |
| `repository` | `cleanup/adapter`, `cleanup/perform`, `cleanup/preview`, `cleanup/targets`, `cleanup_selection`, `fetch`, `repository`, `worktree_launcher`, `worktrees/base`, `worktrees/create`, `worktrees/records`, `worktrees/removability` |
| `sessions` | `agent_bindings`, `agents`, `harnesses`, `hook_claims`, `hook_publish`, `hook_records`, `hook_scan`, `integrate`, `liveness`, `processes`, `session_matching`, `work`, `work_reconciliation`, `work_store` |
| `ui` | `alerts`, `app`, `branch_cells`, `cleanup_flow`, `cleanup_view`, `column_editor`, `detail_fields`, `fetch_flow`, `focus_table`, `glyphs`, `issue_cells`, `issue_table`, `issue_table_controller`, `issue_view`, `item_filter`, `keyed_table`, `legend`, `list_pane`, `list_rows`, `marked_widgets`, `messages`, `observation_runner`, `page_runner`, `pane_layout`, `panes`, `pull_request_cells`, `session_cells`, `spread_table`, `worktree_cells`, `worktree_table` |


## Residual review suggestions

The [original review](../codebase-review-2026-09-13.md) remains historical.
Completion means the planned structural arc is delivered, not that every
judgement suggestion is mandatory. These dispositions accompany #191:

- The package moves are delivered by #188, #189, #190, and #191. The preceding
  layer split, one-app consolidation, and flow extraction were delivered by
  #175, #179, #212, #213, and #182; the review's sequencing section records the
  earlier helper consolidations in #186. This change completes the shared
  result and store-index consolidation.
- Parallel Query Source and complete-collection source adapter families were
  assessed in [#232](https://github.com/ned2/dashpot/issues/232).
  [ADR 0043](0043-retain-distinct-query-and-collection-adapters.md) retains their
  distinct cache, failure, lookup, and export contracts with the existing shared
  implementation. The assessment is complete; a generic consolidation is rejected
  without evidence that it simplifies those contracts.
- Session-label formatting is deliberately deferred. The Work commands and
  hook records still format related labels at different seams; consolidating
  their fallback wording is a small independent change, not a dependency of
  this layout.
- Further `DashboardScreen` extraction is optional and deferred. Its flow,
  runner, pane, and Issue-table-controller extractions already establish the
  planned seams. The remaining composition, focus, layout, and delegation do
  not justify another extraction in this Issue.
- The review's proposed compatibility re-export shims are superseded by the
  alpha internal-interface decision above. Other point-in-time judgement
  smells remain advisory; they do not reopen the structural arc.
