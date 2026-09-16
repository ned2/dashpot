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
`project/workspace.py`. Package initializers stay empty, so importing one leaf
module does not load its siblings. Consumers import the owning module directly.
No old-path re-export shims are added: Python internals are outside the
[alpha compatibility contract](0034-publish-an-alpha-with-patch-compatible-interfaces.md).
The existing top-level exports retain their names.

This stage leaves sessions, repository observation, and UI modules at the root
for the following Issues, as #188's explicit scope requires. Its acceptance
bullet describing a root containing only entry points, assets, and packages is
the eventual layout after those later moves. The CLI and hook entry points,
serialization, stylesheet, skills, and `py.typed` remain at their existing paths.
Tests, tools, and documentation follow moved modules; fresh-interpreter checks
continue to protect headless and lightweight import paths.
