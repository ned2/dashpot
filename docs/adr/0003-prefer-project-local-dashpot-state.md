---
status: amended
amended-by: 0004-observe-one-project-per-run.md
date: 2026-08-28
---

# Prefer Project-local Dashpot configuration and work state

Dashpot's proven primary workflow is observing the current one-repository
Project, while evidence for routinely operating several unrelated Projects in
one Workspace is weak. Dashpot will therefore make the relevant repository
checkout the owner and discovery point for its configuration and mutable local
work state. Tracked configuration lives in `.dashpot/config.json`; ignored
runtime state lives beneath `.dashpot/state/`. Issues #18 and #19 implemented
this ownership model before the first release. The supporting evidence is captured in
[the multi-repository Workspace audit](../multi-repository-workspace-evidence.md).

A Project remains rooted in exactly one Git Repository. Running Dashpot from a
configured checkout is the primary experience. As amended by
[ADR 0004](0004-observe-one-project-per-run.md), a Workspace
resolves to exactly one Project and may aggregate its configured anchors and
discovered Worktrees. It never owns configuration or work state. Machine-wide
agent integrations locate the relevant checkout from observed working-directory and repository facts rather
than publishing to a Workspace-global state authority.

## Considered options

- **Keep Workspace-global configuration and work state:** rejected because it
  makes the common Project-local workflow depend on machine-global identity,
  routing, storage, and cleanup without demonstrated multi-Project demand.
- **Remove multi-Project Workspaces:** deferred because repo-local ownership does
  not prevent later composition, and the combined queue, failure isolation, and
  cross-Project Issue-transfer behavior already exist.
- **Use Project-local ownership with optional Workspace composition:** accepted
  because it simplifies the primary workflow without coupling storage placement
  to the separate product decision of whether several Projects may be viewed
  together.

## Consequences

- Project configuration and mutable work state can be found from a repository
  checkout without first loading a global Workspace inventory.
- Runtime state is local and ignored; it must never dirty the repository or be
  committed with the tracked Project configuration.
- Independent clones and linked worktrees may hold distinct local state. Dashpot
  aggregates those observations when their locations are in scope rather than
  treating one copy as a global authority or synchronizing them implicitly.
- Removing a checkout naturally removes its local state. Moved or missing
  locations become explicit diagnostics instead of silently transferring state.
- The first published release establishes the current configuration and state
  baseline. There are no external users requiring migration from unreleased
  formats; the older path is not a supported release interface.
- Projects spanning multiple Git repositories remain unsupported; that is a
  separate deferred domain decision.
