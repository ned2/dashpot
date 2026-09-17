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
and behavior. Repository observation and UI moves remain with #190 and #191.

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
its scheduling behavior is unchanged. Observation and UI package moves remain
with #191.
