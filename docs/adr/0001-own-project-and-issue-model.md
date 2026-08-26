---
status: accepted
---

# Own the Project and Issue model

Dashpot will own a bounded, GitHub-Issues-compatible domain model rather than
use TASKS.md as its model or backend interface. The upstream adapters expose
different schemas, semantics, failure modes, and capabilities; inheriting that
contract would make source discrepancies part of Dashpot's foundation. The
evidence is recorded in the
[upstream backend audit](../tasks-md-upstream-backend-audit.md).

A Project is a durable body of work rooted in exactly one Git repository and
has exactly one active Issue Source. GitHub-backed Projects require that
repository to be hosted on GitHub; other Git repositories use Dashpot's local
Markdown representation. Both sources produce the same versioned Issue profile.
Project Identity and Issue Identity are opaque and stable, while references,
URLs, file locations, repository hosting, branches, and checkout paths are
mutable facts.

Dashpot will remove TASKS.md as a dependency and will own the local Markdown
format, parser, schema evolution, and conformance fixtures. The canonical model
is a deliberately bounded profile of GitHub Issues, not a copy of GitHub's
entire evolving object graph. Assignment is plural, blocking is represented by
Issue relationships, and priority is a derived interpretation rather than an
intrinsic Issue field.

The executable version 1 profile contract and fixtures live in
[`conformance/issue/v1`](../../conformance/issue/v1/README.md). Issue adapters
produce complete snapshots under the availability and equality rules recorded
in [ADR 0002](0002-require-complete-issue-profile-snapshots.md).

A Workspace is a named local grouping of Projects. Its configuration records a
repository anchor for each Project, not individual worktrees. On refresh,
Dashpot asks Git for the repository's current worktrees and treats them as
runtime Observation Targets. The configured anchor is authoritative for Local
Issues; other worktrees contribute repository and agent observations. Separate
clones require separate anchors.

## Considered options

- **Keep TASKS.md as the common backend interface:** rejected because its file,
  git-native, and GitHub paths are not substitutable and silently lose data.
- **Model an Issue Collection without a Project:** rejected because Dashpot's
  current scope has a useful simplifying invariant: one Project is one Git
  repository with one Issue Source.
- **Allow Projects with zero or several repositories:** deferred until concrete
  Project behavior requires it. A multi-repository product is initially several
  Projects grouped in a Workspace.
- **Persist every checkout or worktree:** rejected because Git already owns
  linked-worktree topology and exposes a stable machine-readable listing.

## Consequences

- Project configuration must carry a tracked, backend-independent Project
  Identity and a versioned Issue Source definition.
- A GitHub Issue transferred to another repository preserves Issue Identity
  when GitHub does, but changes Project membership, reference, and location.
- Clones and worktrees preserve Project Identity. Forks and intentional copies
  must receive a new identity; conflicting repository identities require a
  diagnostic rather than silent aggregation.
- Existing `.tasksmd.json` configuration, Task keys, hook bindings, terminology,
  and tests require an explicit migration.
- Named Workspaces earn their place only as saved Project groupings; worktree
  state and target diagnostics remain runtime observations.
