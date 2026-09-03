---
status: research
date: 2026-08-28
---

# Evidence for multi-repository Workspaces

Research date: 2026-08-28

## Executive conclusion

Dashpot currently uses “multi-repository” for two different product shapes, and
only one of them is supported:

1. **One Workspace presenting several Projects, each rooted in one repository**
   is implemented and tested.
2. **One Project spanning several repositories** is explicitly unsupported and
   deferred.

There is also substantial implemented support for **several local execution
locations of the same repository**—independent clones and Git-linked
worktrees. Those are not evidence for a multi-repository Project, and they do
not necessarily require several Projects to be visible at once.

The repository contains strong architectural and executable evidence that
multi-Project Workspaces *can* work. It contains much weaker evidence that a
person has a concrete, recurring need to operate that way. Dashpot's recorded
live dogfooding is against its own single repository, and the no-argument path
was deliberately changed to make the current configured Project the natural
default. No issue or document found describes an observed user regularly
triaging unrelated repositories in one Dashpot screen.

## Terms that are currently easy to conflate

| Shape | Current meaning | Support |
|---|---|---|
| Multi-Project Workspace | One local observation scope contains several Projects; each Project has one repository | Implemented and tested |
| Multi-repository Project | One body of work spans zero or several repositories | Explicitly deferred / unsupported |
| Independent clones | Several unlinked local clones carry the same Project and Repository identities | Implemented and tested; grouped as one Project |
| Linked worktrees | Git-linked working trees discovered from an anchor | Implemented and tested as runtime Observation Targets |
| Several named Workspaces | The same Project may be tagged as belonging to several local groupings | Implemented and tested, although current startup loads all entries rather than offering an in-app Workspace switcher |

The accepted language is unambiguous on the first two distinctions. A Project
is rooted in “exactly one Git Repository,” while a Workspace is a local grouping
of Projects ([domain language](domain-language.md)). ADR 0001 says
that a multi-repository product is initially represented as several Projects
grouped in a Workspace and defers Projects with zero or several repositories
(`docs/adr/0001-own-project-and-issue-model.md:44-53`).

## Concrete and implemented workflows

### 1. Open one combined queue for several Projects

**Classification: implemented and tested, but not empirically validated as a
recurring user workflow.**

The original extracted-spike README advertised opening “one or more projects”
and showed two different named paths in one command (commit `ff57ecf`,
`README.md:38-47` in that commit). The current CLI still accepts repeated
`--workspace [NAME=]PATH` arguments (`src/dashpot/cli.py:54-69`) and the global
inventory accepts any non-empty list of repository anchors
(`src/dashpot/workspace.py:51-101`). Resolution groups anchors by Project
Identity and returns a list of resolved Projects (`src/dashpot/workspace.py:122-211`).

The collector refreshes all resolved Projects concurrently and returns them in
one Workspace checkpoint (`src/dashpot/collect.py:149-226`). The Issue read model
then iterates all Projects and emits all matching Issues into one result
(`src/dashpot/issue_list.py:66-103`, `src/dashpot/issue_list.py:121-220`). A
Project column and Project text search exist, although the Project column is
hidden by default (`src/dashpot/issue_table.py:93-128`).

Tests prove multi-Project failure isolation: one failed Project remains
unavailable without blanking a successful Project
(`tests/test_collectors.py:883-907`). Store and table tests also preserve
Project-qualified rows when identities collide (`tests/test_observation_store.py:578-595`,
`tests/test_app.py:1118-1141`).

What is missing is direct product evidence. The tracked configuration in this
repository declares only Dashpot itself (`.dashpot.json:1-8`). The dogfooding
issue was specifically about observing Dashpot's own repository
([GitHub issue #1](https://github.com/ned2/dashpot/issues/1)). No issue found
records a live combined queue of unrelated repositories or names the set of
repositories a user needs to triage together.

### 2. Observe several independent clones as one Project

**Classification: explicitly designed, implemented, and tested. This is
multi-location, not multi-Project.**

The README's current repeated-anchor example is not two unrelated repositories;
it is `first-clone` and `second-clone` under the same Workspace name
(`README.md:38-53`). Clones with matching Project and Repository identities are
presented as one Project, with the first anchor authoritative for Issue
collection (`README.md:75-79`).

The resolver implements that grouping (`src/dashpot/workspace.py:154-210`), and
tests prove that two independent clones become one Project with one primary
anchor (`tests/test_workspace.py:86-107`). Collection observes every anchor but
refreshes the Project Issue Source only once (`tests/test_collectors.py:210-251`,
`tests/test_collectors.py:856-881`).

This workflow came from the explicit acceptance scenarios for
[GitHub issue #13](https://github.com/ned2/dashpot/issues/13), implemented in
commit `1ea78fe`. However, the issue describes representational gaps and
acceptance cases rather than evidence of a real user currently switching
between two independent clones.

### 3. Observe the main checkout and linked worktrees

**Classification: explicitly requested, implemented, and tested. This is also
multi-location, not multi-repository.**

Git-linked worktrees are runtime Observation Targets, never persisted Workspace
members ([domain language](domain-language.md#observation)).
[GitHub issue #14](https://github.com/ned2/dashpot/issues/14) names concrete
behaviour: observe a main worktree plus linked worktree, show per-target Git and
agent facts, and react to adding or removing worktrees without changing saved
membership. It was implemented in commit `94a3d4c`.

This is the strongest concrete workflow around multiple checkout locations. It
does not by itself justify combining unrelated repositories in one screen.

### 4. Preserve an Agent Run binding when an Issue transfers Projects

**Classification: implemented and tested; uncommon but genuinely depends on a
Workspace-level view when both Projects are configured.**

Issue Binding is defined to survive Project membership changes
([domain language](domain-language.md#observation)). ADR 0001 makes binding
Workspace-global and explicitly
separates execution location from Issue membership across transfers
(`docs/adr/0001-own-project-and-issue-model.md:65-71`). The resolver searches
persisted Issue Identity across all observed Projects, while only resolving a
new mutable hint within the run's observed Project
(`src/dashpot/agent_bindings.py:39-126`).

Tests prove that a run still correlates after its Issue transfers from Project A
to Project B (`tests/test_agent_bindings.py:65-79`,
`tests/test_collectors.py:725-763`) and that UI selection follows a transferred
Issue (`tests/test_app.py:1235-1261`). This was the acceptance target of
[GitHub issue #15](https://github.com/ned2/dashpot/issues/15), implemented in
commit `12df673`.

This workflow is real in the model and tests, but the repository does not record
a live transfer encountered during dogfooding.

## Explicitly planned workflows

### 5. Refresh a selected Project without waiting for unrelated Projects

**Classification: explicitly planned, not yet implemented.**

The architecture research identifies a current multi-Project cost: a fast
Project cannot be displayed until the slowest Project completes, and one
unavailable Project delays delivery of every successful Project
(`docs/dynamic-observation-data-access-research.md:49-79`). Its Stage 3 proposes
per-Project scheduling and targeted refresh
(`docs/dynamic-observation-data-access-research.md:287-308`).

[GitHub issue #17](https://github.com/ned2/dashpot/issues/17) turns that into an
open product task: a fast Project should become visible while unrelated work is
still running, and a selected Project should be refreshable without refreshing
unrelated Projects. This is meaningful only if a Dashpot process observes more
than one Project, but it is a response to architectural capability, not evidence
that a user has already reported the latency in a real multi-repository space.

### 6. Install agent observation once and use it across repositories

**Classification: explicitly planned; it does not necessarily require a
simultaneous multi-Project UI.**

[GitHub issue #3](https://github.com/ned2/dashpot/issues/3) asks for one opt-in
Codex integration that observes Issue-bound sessions “across repositories.”
That supports machine-wide integration and avoids copying hook configuration
into every checkout. A user could still run a one-Project Dashpot instance per
repository, so this is evidence for harness-neutral/global discovery rather
than decisive evidence for one combined Workspace.

## Architectural allowances and hypotheses

### 7. Personal/client/saved Workspace groupings

**Classification: architectural allowance with fixture coverage; no complete
user interaction is specified.**

The model allows a Project to belong to several named Workspaces
(`src/dashpot/model.py:73-86`), and a test demonstrates the same Project in
`personal` and `client` (`tests/test_workspace.py:109-127`). ADR 0001 says named
Workspaces “earn their place only as saved Project groupings”
(`docs/adr/0001-own-project-and-issue-model.md:77-78`).

There is no in-app Workspace chooser, add/remove command, or documented workflow
for switching between those groupings. The current config loader loads the
whole `workspaces` array and the resolver unions Project membership. Therefore
“personal” and “client” are currently metadata on a combined observation, not
fully realised separate spaces.

### 8. Workspace-wide status across other observations

**Classification: planned, but not evidence specific to unrelated
repositories.**

[GitHub issue #12](https://github.com/ned2/dashpot/issues/12) says the selected
Project pane cannot report exceptions elsewhere and proposes an exceptional
Workspace status display. Its acceptance cases include multiple Observation
Targets, which can be worktrees of a single repository. This supports an
aggregate observation concept but does not establish a multi-Project need.

### 9. Projects spanning multiple repositories

**Classification: explicitly hypothetical and out of scope.**

ADR 0001 defers Projects with zero or several repositories until concrete
behaviour requires them (`docs/adr/0001-own-project-and-issue-model.md:48-53`).
The closeout for [GitHub issue #9](https://github.com/ned2/dashpot/issues/9)
again lists Projects spanning multiple repositories as deferred and
multi-repository Projects as out of scope. There is no source model, config
grammar, or test for one Project owning several repositories.

## Decision signal

The evidence supports three conclusions for the proposed simplification:

1. **Dropping multi-repository Projects sacrifices nothing currently shipped,**
   because they were never supported.
2. **Dropping multi-Project Workspaces removes real implementation and test
   coverage, but no demonstrated dogfooding workflow was found.** The clearest
   losses would be a combined Issue queue, cross-Project transfer tracking,
   Project-level failure isolation, and the planned targeted-refresh model.
3. **Multiple clones and linked worktrees should be judged separately.** They
   account for much of the apparent “multi-repo” complexity but represent one
   Project in several local execution locations. Choosing repository-local
   state does not automatically answer how state is shared across independent
   clones or linked worktrees.

The current evidence therefore justifies treating a one-Project repository-local
experience as the proven primary workflow. It does not provide concrete demand
for an always-visible multi-Project space. If multi-Project aggregation is kept,
it should be kept as a deliberate secondary workflow with an explicit user story,
not because clones, worktrees, and multi-repository Projects are treated as the
same requirement.

## Sources reviewed

- the README domain language and `.dashpot.json`
- ADRs 0001 and 0002
- `docs/dynamic-observation-data-access-research.md`
- workspace, collector, model, Issue-list, binding, and observation-store source
- workspace, collector, app, binding, and observation-store tests
- commits `ff57ecf`, `d30c4eb`, `1ea78fe`, `94a3d4c`, and `12df673`
- GitHub issues #1, #3, #7, #9, #12–#17 and their available comments, queried
  2026-08-28
