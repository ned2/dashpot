---
status: accepted
---

# Observe one Project per run

[ADR 0001](0001-own-project-and-issue-model.md) fixed the invariant that one
Project is one Git Repository with one Issue Source, and
[ADR 0003](0003-prefer-project-local-dashpot-state.md) made observing the
current Project from its checkout the primary experience while deferring the
question of whether several Projects may still be viewed together. Since then
every feature has been designed and verified against a single Project, and the
main screen has grown per-Project chrome — a PROJECT column in the Sessions and
Worktrees panes, a Project-scoped agent count — whose only purpose is to
disambiguate a composition nobody runs. Dashpot will therefore observe exactly
one Project per run. Whether to expand to multi-Project composition is a
separate product decision to be taken explicitly, with evidence, later.

Several Repository Anchors may still be configured for one run as long as they
resolve to the same Project Identity: independent clones of one repository are
one Project, and Git-linked worktrees are discovered from any anchor. A
Workspace is now simply the named set of anchors that resolves to the one
observed Project. Anchors that resolve to more than one Project are a
configuration error reported before observation starts, naming the Projects so
the user can pick one; nothing is silently chosen.

## Considered options

- **Keep multi-Project composition as an optional secondary view:** rejected
  because it is untested in practice, and its cost is paid on every screen in
  the form of Project disambiguation that the primary workflow never needs.
- **Remove Projects from the data model (`WorkspaceSnapshot.projects` becomes a
  single Project):** rejected for now because the plural shape is cheap to keep,
  is exercised by the merging of independent clones, and leaves later
  composition a product decision rather than a data migration. The invariant is
  enforced at the edge — Workspace resolution — not by reshaping observations.
- **Pick the first Project and diagnose the rest:** rejected because a passive
  view must not guess which Project the user meant.

## Consequences

- `resolve_workspace_projects` fails with an actionable error when the merged
  anchors resolve to more than one Project, for both a Workspace inventory and
  repeated `--workspace` arguments.
- The main screen may drop chrome that only distinguishes Projects: the
  PROJECT STATUS agent count (the Sessions pane count is the one number), and
  the PROJECT columns of the Sessions and Worktrees panes.
- Cross-Project behaviour that already exists — Issue transfer between
  configured Projects, the whole-Workspace refresh — becomes dormant rather
  than being removed; it is not exercised in a one-Project run.
- Projects spanning multiple Git repositories remain unsupported, as in ADR
  0003.
