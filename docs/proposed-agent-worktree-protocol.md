---
status: proposal
---

# Propose an Issue worktree protocol for agent handoff

This document proposes a workflow for preparing a Git-linked Worktree, launching
any supported agent harness there, and explicitly starting and stopping Issue
work. It is a review artifact, not an accepted design: the commands below do not
exist, and the proposal does not revise Dashpot's passive product contract or
accepted ADRs.

The proposal is deliberately a protocol between callers and modules rather than
a draft agent skill. Product commands should first own every deterministic rule
that agents would otherwise duplicate. A later skill can then describe a short
sequence of calls with checkable completion criteria.

## Goals

- Place newly created linked Worktrees beneath one machine-local directory,
  independent of the harness that will use them.
- Accept the same Issue Hints people already use with `dashpot work start`, with
  bare Issue Numbers such as `35` as the documented default and quoted `'#35'`,
  full References, and Local Issue slugs also supported.
- Resolve and present Issues through the configured Issue Source so an agent
  never has to choose between `gh` and Local Issue Markdown.
- Start each new Agent Session in its actual Worktree before it creates an Issue
  Binding.
- Let Codex, Claude Code, another harness, or a human reuse the same Worktree.
- Preserve the Work Store as the sole authority for Issue Binding. A Worktree
  path, Branch, creation request, or launch prompt remains only an Issue Hint.
- Keep creation, launch, Issue Binding, handoff, and cleanup as separable
  decisions.

## Non-goals

- Accepting this proposal or changing the domain model through documentation.
- Assigning a harness to a Worktree.
- Inferring active Issue work from the presence of a Worktree.
- Treating one Issue as having exactly one Worktree.
- Fetching, pulling, pushing, merging, deleting Branches, or removing Worktrees
  implicitly.
- Specifying background supervision, resume behavior, or automatic cleanup.
- Writing the future agent-facing skill before its product commands stabilize.

## Evidence from the current harnesses

A disposable Local Issue simulation exercised Codex 0.151.0 and Claude Code
2.1.251 with the installed Dashpot lifecycle hooks:

- Both harnesses inherited the tracked `.dashpot/config.json` in a new linked
  Worktree and successfully ran `dashpot work start`, `show`, and `stop` there.
- Both agents first attempted to read a bare Issue Number through `gh`, even
  though the configured Issue Source was Local Issue Markdown. Dashpot's own
  Issue Hint resolution selected the correct Issue.
- Codex has a launch-directory option but no native worktree creator. When asked
  to create a Worktree during an existing session, it initially crossed the
  creation and execution-location concerns before recovering.
- Claude Code's native `--worktree` creates before the model or a model-invoked
  skill runs. In the tested version it chose `.claude/worktrees/`, made the main
  Worktree appear dirty when that path was not ignored, and retained its
  Worktree and Git lock after the non-interactive session ended.
- Dashpot discovered each new Worktree through Git without persisting it as
  Workspace membership. An explicit Work Store record, not the Worktree, made
  the active Agent Run visible on its Issue.

These observations support pre-launch preparation shared by all harnesses. They
do not yet decide whether Dashpot should calculate a directory, create a
Worktree, or also dispatch a harness.

## Actors and proposed ownership

| Actor or module | Proposed responsibility |
|---|---|
| Git | Own Worktree topology, refs, checkout mutation, and locks. |
| Tracked Project configuration | Own Project Identity, Repository Identity, display label, and Issue Source. |
| Machine-local Dashpot settings | Supply the common parent directory for new Worktrees. |
| Issue resolution module | Resolve an Issue Hint through the configured Issue Source and return the canonical Issue profile. |
| Worktree preparation module | Apply path, naming, base, collision, and configuration-inheritance policy and optionally perform explicit Git mutation. |
| Launcher | Start a selected harness with the prepared Worktree as its working root. |
| Harness adapter | Translate the common launch request into Codex or Claude Code invocation details. |
| Agent-facing skill | Select a protocol branch, call stable commands, and verify their completion criteria. |
| Work Store | Remain the sole authority for active Agent Runs and their Issue Bindings. |

The launcher may initially be a human, shell integration, or external
dispatcher. Making it a Dashpot module is a separate product decision from
Worktree preparation.

## Candidate interfaces

The proposal currently assumes two missing source-neutral interfaces:

```bash
dashpot issue show 35 --json
dashpot worktree create 35 --base main --json
```

Every Issue-taking command accepts the same forms:

```bash
dashpot issue show 35
dashpot issue show '#35'
dashpot issue show ned2/dashpot#35
dashpot issue show local-issue-slug
```

`35` is the ordinary form. A full Issue Reference is useful outside an
unambiguous configured Project, but should not burden the common workflow.

A candidate creation result is a value for the caller, not an Issue Binding or
persisted Observation Target:

```json
{
  "issueId": "I_kwDOUEerr...",
  "issueReference": "ned2/dashpot#35",
  "path": "/home/ned/agent-worktrees/dashpot/35",
  "branch": "dashpot/35",
  "baseRef": "refs/heads/main",
  "baseCommit": "e319d3c...",
  "created": true
}
```

The Worktree has no harness field. A launcher may start Codex there now and
Claude Code there later without recreating or renaming it.

An optional discriminator is only for intentionally separate approaches to the
same Issue:

```bash
dashpot worktree create 35 --name alternate-approach
dashpot worktree create 35 --name regression-test
```

Names describe workstreams, never harnesses or Issue Binding. Whether the
interface should say `--name`, `--slot`, or refuse all automatic leaf naming is
still open.

## Candidate protocol

### 1. Resolve the Issue

From a configured Repository Anchor, the caller supplies the ordinary Issue
Hint:

```bash
dashpot issue show 35 --json
```

Completion criterion: exactly one fresh Issue is returned with Issue Identity,
canonical Issue Reference, title, body, and actionable Issue Location. Source
unavailability or ambiguity stops the protocol before Git mutation.

This public interface should share one Issue resolution module with
`dashpot work start`; the caller does not select a GitHub or Local Markdown
adapter.

### 2. Select or create a Worktree

For new work, the caller requests an explicitly mutating operation:

```bash
dashpot worktree create 35 --base main --json
```

Completion criterion: the returned absolute path is a registered, clean
Git-linked Worktree at the reported base commit; its checked-out revision
contains a compatible `.dashpot/config.json`; and the original Worktree is
unchanged.

At minimum, the implementation would need to hide:

- machine-local root precedence and path normalization;
- Repository Anchor and independent-clone selection;
- source-neutral Issue resolution;
- human-readable leaf and Branch naming;
- base-ref resolution to an exact commit;
- existing path, ref, and checked-out Branch collisions;
- concurrent creation;
- compatible Project and Repository Identity at the selected revision;
- `git worktree add` execution and postcondition verification; and
- partial-failure diagnosis.

Splitting those rules between an environment variable and prose in a skill
would make the skill part of the implementation. An environment variable may
override machine-local configuration, but Dashpot rather than the agent should
interpret it:

```text
explicit command override
→ DASHPOT_WORKTREE_ROOT
→ machine-local Dashpot setting
→ deterministic default or actionable error
```

An absolute machine path does not belong in tracked Project configuration.

For existing work, the caller may instead supply a known Worktree path directly
to the launcher. Automatically finding "the Worktree for Issue 35" would require
either a path convention treated as authority or a durable intended-work
relationship. That relationship is not part of the current model and remains an
open decision.

### 3. Launch the selected harness

The launcher starts the harness in the returned path. Illustratively:

```bash
codex -C /home/ned/agent-worktrees/dashpot/35 \
  "Pick up Issue 35 using the Dashpot workflow."
```

```bash
cd /home/ned/agent-worktrees/dashpot/35
claude "Pick up Issue 35 using the Dashpot workflow."
```

The proposed Claude adapter sets process working directory and omits native
`--worktree`; the proposed Codex adapter passes `-C`. These are harness adapter
details, not Worktree identity.

Completion criterion: the new Agent Session begins with its harness working root
and recorded Observation Location inside the selected Worktree.

A skill invoked by an already-running Agent Session cannot retroactively satisfy
this criterion. It may prepare a Worktree for a child or subsequent session and
return a relaunch instruction, but should not claim that creating a directory
migrated its own session.

### 4. Establish the Issue Binding

Inside the launched Agent Session and selected Worktree, the portable skill
runs:

```bash
dashpot work start 35
dashpot work show
```

Completion criterion: `show` reports this Agent Session working on the intended
canonical Issue Reference, and observation locates its Agent Run at the selected
Worktree.

This explicit opt-in remains independent of Worktree creation. A later
`dashpot dispatch` design might establish opt-in differently, but doing so would
require a separate domain decision about Issue Binding provenance.

### 5. Perform the repository workflow

The skill follows repository instructions for setup, quality gates, commit, and
push. In Dashpot itself, for example, each Worktree owns its `.venv` and the
repository requires its full pre-commit and test gates.

Completion criterion: the repository's own definition of finished work is met;
the portable Dashpot skill does not duplicate it.

### 6. Stop or hand off the Agent Run

At the terminal outcome for this Agent Run, the skill runs:

```bash
dashpot work stop
dashpot work show
```

Completion criterion: `show` reports no active Issue work for this Agent
Session. The Agent Session may then end without leaving an Orphaned Agent Run.

Stopping does not remove the Worktree. A later Codex, Claude Code, or human
caller can reuse the same path. The next Agent Session creates its own Issue
Binding with `work start`, producing a distinct Agent Run.

### 7. Clean up separately

The proposed protocol does not automatically remove Worktrees or Branches.
Cleanup is destructive and must account for dirty state, active Agent Sessions,
active Agent Runs, locks, unmerged commits, clone ownership, and whether Dashpot
can distinguish a managed Worktree from an external one.

Completion criterion for a future cleanup protocol: removal happens only after
an explicit request and a conservative safety check, with Branch deletion a
separate opt-in.

## Candidate agent-facing skill shape

The eventual skill should be model-invoked when a user asks an agent to start,
switch, finish, hand off, or recover declared Issue work, or to prepare a
Worktree for it. Its common own-session path should remain short:

1. Read repository instructions and use their prescribed Dashpot invocation.
2. Resolve the Issue through `dashpot issue show`.
3. Confirm this Agent Session is already in the Worktree where work will occur.
4. Run `dashpot work start` and verify the intended Issue with `work show`.
5. Perform the repository's own workflow.
6. Run `dashpot work stop` at the terminal outcome and verify it stopped.

Worktree preparation or launching another Agent Session should be progressively
disclosed behind a dispatch reference. Wrong-location sessions, collisions,
partial creation, missing configuration, dirty Worktrees, and Orphaned Agent
Runs should be disclosed behind a recovery reference. Deterministic path, Git,
and Issue Source rules belong in commands rather than scripts or prose in the
skill.

## Open decisions

The proposal should not advance to implementation until these questions have
review outcomes:

1. **Product contract:** Can an explicitly named management command mutate Git
   while observation remains passive, or must creation live in a separate
   dispatcher/tool?
2. **Smallest interface:** Is a read-only `worktree directory` command enough,
   or must Dashpot own atomic creation to keep policy out of callers?
3. **Configuration:** What is the machine-local setting location, precedence,
   default, and behavior when the root is unavailable?
4. **Base selection:** Is a tracked default Branch safe, is the caller's current
   HEAD meaningful, or must every creation name a base ref?
5. **Naming:** Which human hints belong in paths and Branches, and how are
   invalid characters, renames, collisions, and length limits handled?
6. **Multiplicity:** What is the default when one Issue already has one or more
   Worktrees, and how does a caller request an independent approach without
   associating it with a harness?
7. **Reuse and handoff:** Does the user pass an existing path explicitly, or does
   Dashpot persist a non-authoritative intended-Issue relationship so callers
   can locate it later?
8. **Independent clones:** Which clone owns creation when several Repository
   Anchors preserve the same Project and Repository Identity?
9. **Failure ownership:** Which partial creation states may be rolled back, and
   when must Dashpot leave evidence and remediation instead?
10. **Cleanup:** Does Dashpot ever own removal, locks, or Branch deletion, and
    what durable management metadata would that require?
11. **Launch:** Is harness dispatch outside Dashpot, a later Dashpot module, or
    part of this protocol's first useful version?
12. **Issue Binding:** Does explicit in-session `work start` remain required for
    managed dispatch, or can a user dispatch action become a new binding
    provenance?
13. **Skill distribution:** Is the model-invoked skill bundled with Dashpot,
    installed separately, or added by an extension of `dashpot integrate`?

Questions 1, 6, 7, 10, and 12 may qualify as architectural decisions once
evidence supports an answer. Recording them here does not prejudge the ADRs.

## Review probes

Review should combine interface critique with another disposable simulation.
The protocol is credible when every probe has an explicit expected result:

- A user says `35`; source-neutral resolution returns the configured Project's
  Issue #35 without the agent choosing `gh` or a Markdown file.
- Codex and Claude Code start in different Worktrees beneath the same configured
  parent without harness names in their Worktree identity.
- Codex completes work and Claude Code later continues in that exact Worktree,
  with separate Agent Runs and no new Worktree creation.
- Two intentionally independent approaches to one Issue coexist without being
  mistaken for duplicate Issue Bindings.
- A base ref predating `.dashpot/config.json` fails before creation.
- Existing paths, existing Branches, concurrent creators, and partial Git
  failures produce deterministic, non-destructive results.
- The main Worktree stays clean, and machine-local state is never committed.
- During work, Dashpot observes the correct Agent Session, Agent Run, Worktree,
  Branch, and Issue Binding; after `work stop`, no Orphaned Agent Run remains.
- A finished session leaves a reusable Worktree, while an explicit cleanup
  request refuses dirty, active, locked, or unmerged state.
- The draft skill is forward-tested by giving unprimed Codex and Claude Code the
  same ordinary prompt and judging outcomes rather than transcript wording.

## Decision path

1. Review the open decisions without treating the candidate command spelling as
   settled.
2. Select the smallest interface that keeps deterministic policy out of agents
   and harness adapters.
3. Run the review probes against throwaway repositories and both supported
   harnesses.
4. Record accepted product and domain decisions in ADRs and update the shared
   domain language where necessary.
5. Implement the product commands before writing the model-invoked skill.
6. Forward-test the skill and prune instructions that product behavior makes
   redundant.
