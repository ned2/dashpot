---
status: superseded
date: 2026-09-05
superseded-by: adr/0011-prepare-issue-worktrees-by-convention.md, adr/0029-preserve-agent-runs-through-declared-codex-relocation.md
---

# Propose an Issue worktree protocol for agent handoff

> **Superseded.** The review this document drove was accepted on 2026-08-30 and
> its outcomes are recorded in
> [ADR 0011](adr/0011-prepare-issue-worktrees-by-convention.md), amended by
> [ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md).
> Active Codex Agent Run continuity is recorded separately in
> [ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md).
> `dashpot issue show`, `worktree create`, `worktree check`, `worktree remove`,
> `branch delete`, and the `dashpot-issue-work` skill distributed by
> `dashpot integrate` ship; the README's
> [Issue Worktrees](../README.md#issue-worktrees) section documents them as
> built. Read this document as the evidence and the walked decisions behind
> those ADRs, not as a description of the commands. Where it disagrees with an
> ADR, the ADR wins.

This document proposed a workflow for preparing a Git-linked Worktree,
launching any supported agent harness there, and explicitly starting and
stopping Issue work. It is a review artifact, not the current product contract;
the superseding ADRs and README describe the shipped commands and skill.
Candidate command spellings below record what the review considered.

The proposal is deliberately a protocol between callers and modules rather than
a draft agent skill. Product commands should first own every deterministic rule
that agents would otherwise duplicate. A later skill can then describe a short
sequence of calls with checkable completion criteria.

The document separates three kinds of statement, and a reader should be able to
tell them apart: **verified facts** (measured against the installed tools or
read from current code and documentation, see [Evidence](#evidence)),
**recommendations** (this review's preferred answer, with confidence), and
**review outcomes** (choices the user made on 2026-08-30 when walked through
the open decisions; see [Review outcomes](#review-outcomes)). An outcome is a
direction for the implementation and its ADRs, not an accepted ADR itself.

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

## Evidence

The review measured the claims below against Dashpot at commit `1117667`,
Git 2.53.0, Codex CLI 0.151.0, and Claude Code 2.1.251 on Linux, using
disposable Local Issue Markdown repositories under a temporary directory.
Anything not marked *measured* or *read from* code or documentation is marked
*unverified*.

### Dashpot behavior (read from `src/dashpot/`, measured where stated)

- **Issue Hint resolution** (`work.py:_resolve_issue`) refreshes the whole
  configured Issue Source and requires a `fresh` result, then matches a bare or
  `#`-prefixed number against `number`, and any other string against the
  Issue's `reference` exactly. Measured in a Markdown Project: `35`, `'#35'`
  and the slug `worktree-protocol` all resolve to the same Issue; `99` fails
  with an actionable message. **Correction:** a full Issue Reference such as
  `ned2/dashpot#35` is only ever the `reference` of a GitHub-sourced Issue, so
  it matches nothing in a Markdown Project (measured: "did not match an Issue
  in this Project"). The hint forms are source-neutral in spelling but not in
  outcome; a GitHub Project additionally needs a GitHub `origin` remote and an
  authenticated `gh` at resolution time.
- The resolution module is private today; `dashpot issue show` would be a thin
  public wrapper over it, not new policy.
- **Configuration inheritance.** `load_project_config` reads
  `<worktree root>/.dashpot/config.json`, where the root is
  `git rev-parse --show-toplevel`. A linked Worktree checked out at a revision
  containing the tracked file inherits it (measured); one checked out at a
  revision predating it makes `work start` fail with "Project configuration
  not found" (measured). Nothing compares the Project Identity in the checked
  out revision with the Repository Anchor's; a base revision from a fork or a
  re-initialized Project would pass silently.
- **Hook routing.** The publisher writes a record to
  `<repositoryRoot>/.dashpot/state/sessions/` only when that root has a
  `config.json`, else to the platform state directory (`DASHPOT_STATE_DIR`).
  Observation then locates the session by `cwd` inside any discovered
  Observation Target. Measured: a session at a Worktree that predates the
  configuration is still listed at that Worktree, but cannot opt in there.
- **Work Store locality.** `WorkStore(root)` is per Worktree; `work start`
  records the command's working directory and the checked-out Branch (`null`
  when detached, measured). The main Worktree's `.dashpot/state/` stayed
  absent while runs were recorded in linked Worktrees (measured).
- **Observation of runs.** `observe_work_runs` joins each Worktree's records
  to hook sessions by Agent Session Identity, then host process. A Work Store
  record with no hook record at that Worktree is reported with activity
  `unknown` (measured: a run recorded from this review's own session, whose
  harness `cwd` is elsewhere). A live session with records at two Worktrees
  produces a `work-session-conflict` warning and both runs are listed; neither
  is an Orphaned Agent Run because the session is live.
- **Harness launch probe (measured).** `codex exec -C <worktree>` and
  `cd <worktree> && claude -p` each ran `dashpot work start 35` and
  `work show` successfully in their own linked Worktree; after both sessions
  ended, `dashpot --json` from the main Worktree reported each as a
  `work-session-orphaned` diagnostic naming the right Worktree, Branch, Issue
  Identity, and `work stop --session` command. Codex ran in a directory that
  had no trust entry without prompting in `exec` mode; interactive trust
  behavior for a new path is unverified.
- **No JSON on management commands yet.** `dashpot --json` prints a complete
  observation snapshot (`serialization.py`), which is the only stable
  machine-readable contract today; `work start/show/stop` print lines.
- **Skills.** Both harnesses implement the Agent Skills directory convention.
  Claude Code reads personal skills from `~/.claude/skills/`; current Codex
  reads user skills from `~/.agents/skills/` (the earlier
  `~/.codex/skills/` observation is obsolete). `dashpot integrate` now installs
  the same managed skill for both, and the skill checks `dashpot --version`
  before it invokes the management contract.

### Git linked-Worktree semantics (measured)

- Adding into a **non-empty existing path** fails (`already exists`); an
  **empty existing directory is adopted** silently.
- `-b <branch>` with an **existing Branch** fails; naming an existing Branch
  without `-b` adopts it unless it is checked out elsewhere, which fails with
  `already used by worktree at <path>`.
- **Ref D/F conflict:** once `dashpot/35` exists, `dashpot/35/alt` cannot be
  created (`cannot lock ref`). A naming scheme must never extend an existing
  leaf with `/`.
- **Concurrent creators, same path:** one wins, the other fails on the path,
  but the loser's `-b` Branch had already been created and is left behind.
  Path failure is therefore not free of side effects.
- **Concurrent creators, same Branch, different paths:** the ref lock makes
  one fail cleanly.
- **SIGKILL during `git worktree add`** leaves a registered Worktree whose
  lock reason is `initializing`, a created Branch, and a partial checkout.
  Git does not report it as `prunable`; retrying at the same path or Branch
  fails. Recovery is `git worktree remove -f -f <path>` and `git branch -D`.
  Dashpot already surfaces locked targets (`target-locked`,
  `target-locked-stale`), so the `initializing` reason is a recognizable
  partial-creation signature.
- `git worktree add --lock --reason <text>` records a lock at creation.
- A Worktree created **inside the repository** (`.claude/worktrees/…`) shows
  as untracked in the main Worktree unless ignored; one outside leaves the main
  Worktree clean.
- A Worktree added through a **symlinked parent** is recorded under its
  resolved real path, which is also what `--show-toplevel` returns.
- An **independent clone** lists only its own linked Worktrees.
- `git worktree remove` refuses dirty (`use --force`) and locked
  (`remove -f -f` or unlock) Worktrees.

### Harness behavior (read from documentation, measured where stated)

- **Codex** has `-C/--cd <DIR>` for the working root (measured in `--help`)
  and no Worktree feature in its CLI. No in-session relocation mechanism was
  found; its absence is unverified.
- **Claude Code** has no working-directory flag; the caller must `cd`.
  `--add-dir` grants file access only.
- Claude Code's `--worktree [name]` creates `.claude/worktrees/<name>` on
  Branch `worktree-<name>` from `origin/<default>` after a bounded fetch
  (`worktree.baseRef` may be `fresh` or `head`, never a Branch name). It does
  not touch `.gitignore`. `-p` runs leave the Worktree on disk and locked.
  Reusing a name whose directory exists reopens it and, when it is clean and
  still on its generated Branch, may **reset it to the default branch**.
  Claude Code writes a marker into Worktrees it creates and its periodic sweep
  removes only marked, unlocked, work-free Worktrees older than
  `cleanupPeriodDays`.
- Claude Code has a **`WorktreeCreate` hook** that replaces its Git logic for
  `--worktree`, subagent isolation, and background sessions: input carries
  `name` and `cwd` (no Issue), the hook prints the absolute Worktree path, and
  any nonzero exit aborts the session. `WorktreeRemove` fires at exit.
- **Correction:** a running Claude Code session *can* relocate itself. The
  `EnterWorktree` tool creates a Worktree under `.claude/worktrees/` or enters
  any path listed by `git worktree list` (approval required outside
  `.claude/worktrees/`); hook `cwd` then follows the session, while
  `${CLAUDE_PROJECT_DIR}` stays at the launch directory. Codex has no
  equivalent. The original claim that no running session can be relocated
  holds only for Codex.
- A Claude Code session isolated by `--worktree`/`EnterWorktree` blocks tool
  calls whose working directory or Git redirect resolves to the main checkout.
  A session started by `cd <worktree> && claude` has no such enforcement.

### Not re-measured

- The original observation that both agents first reached for `gh` in a
  Markdown Project was made from transcripts of the author's earlier
  simulation and was not repeated. It remains plausible and is the motivation
  for `dashpot issue show`, not a load-bearing fact.

## Actors and proposed ownership

| Actor or module | Proposed responsibility |
|---|---|
| Git | Own Worktree topology, refs, checkout mutation, and locks. |
| Tracked Project configuration | Own Project Identity, Repository Identity, display label, and Issue Source. |
| Machine-local Dashpot settings | Supply the common parent directory for new Worktrees. |
| Issue resolution module | Resolve an Issue Hint through the configured Issue Source and return the canonical Issue Profile. |
| Worktree preparation module | Apply path, naming, base, collision, and configuration-compatibility policy and perform the explicit Git mutation. |
| Launcher | Start a selected harness with the prepared Worktree as its working root. |
| Harness adapter | Translate the common launch request into Codex or Claude Code invocation details. |
| Agent-facing skill | Select a protocol branch, call stable commands, and verify their completion criteria. |
| Work Store | Remain the sole authority for active Agent Runs and their Issue Bindings. |

The launcher may initially be a human, shell integration, or external
dispatcher. Making it a Dashpot module is a separate product decision from
Worktree preparation.

## Candidate interfaces

The proposal assumes two missing source-neutral interfaces (spelling
provisional):

```bash
dashpot issue show 35 --json
dashpot worktree create 35 --json
dashpot worktree create 35 --base main --branch 35-alternate-approach --json
```

Every Issue-taking command accepts the same forms, with the caveat measured
above that a full Issue Reference only resolves in the Project whose Issue
Source produces it:

```bash
dashpot issue show 35
dashpot issue show '#35'
dashpot issue show ned2/dashpot#35      # GitHub Projects only
dashpot issue show local-issue-slug     # Markdown Projects only
```

`35` is the ordinary form.

A candidate creation result is a value for the caller, not an Issue Binding or
persisted Observation Target:

```json
{
  "issueId": "I_kwDOUEerr...",
  "issueReference": "ned2/dashpot#35",
  "path": "/home/ned/projects/dashpot.worktrees/35-propose-an-issue-worktree-protocol",
  "branch": "35-propose-an-issue-worktree-protocol",
  "baseRef": "refs/remotes/origin/main",
  "baseSource": "origin/HEAD",
  "baseCommit": "e319d3c...",
  "worktreeRoot": "/home/ned/projects/dashpot.worktrees",
  "worktreeRootSource": "default-sibling",
  "created": true
}
```

The Worktree has no harness field. A launcher may start Codex there now and
Claude Code there later without recreating or renaming it.

The Branch is an explicit parameter with a default (review outcome 6):
`--branch NAME` names it; when omitted, Dashpot uses GitHub's own Issue-branch
convention, `<number>-<title-slug>` (for a Local Issue, its slug). The path
leaf follows the Branch name with `/` replaced by `-`. An intentionally
separate approach to the same Issue is simply another `--branch`:

```bash
dashpot worktree create 35 --branch 35-alternate-approach
```

Branch names describe workstreams, never harnesses or Issue Binding, and are
never parsed back into one. A name that would extend an existing Branch with
`/` is refused before Git is called (the measured D/F conflict).

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

This public interface shares the existing private resolution module with
`dashpot work start`; the caller does not select a GitHub or Local Markdown
adapter.

### 2. Select or create a Worktree

For new work, the caller requests an explicitly mutating operation:

```bash
dashpot worktree create 35 --json
```

Completion criterion: the returned absolute path is a registered, unlocked,
clean Git-linked Worktree at the reported base commit on a new Branch; the
checked-out revision's `.dashpot/config.json` carries the same Project Identity
and Repository Identity as the Repository Anchor; and the main Worktree is
unchanged (`git status` clean, no new refs other than the reported Branch).

Rules the implementation must own, each backed by a measurement above:

- Worktree root precedence (`--worktree-root` → `DASHPOT_WORKTREE_ROOT` →
  machine-local setting → sibling default), real-path normalization, and
  refusal of a root that resolves inside any Worktree of the Project;
- Repository Anchor selection (the checkout the command runs in);
- source-neutral Issue resolution before any Git call;
- the default Branch name `<number>-<title-slug>`, validation of any
  `--branch` with `git check-ref-format --branch`, and refusal of a name that
  extends an existing Branch with `/`;
- base-ref resolution to an exact commit without fetching (ADR 0005):
  `origin/HEAD`, else a local `main` or `master` when exactly one exists, else
  refusal naming `--base`, with the source of the choice reported;
- refusal of a non-empty path, an existing Branch, a checked-out Branch, and
  an empty directory that is not known to be Dashpot's own creation;
- a Project-compatibility check of the base revision's configuration before
  `git worktree add`;
- concurrent creation resolved by Git's own path and ref locks, with the
  stray-Branch side effect handled (see Failure ownership);
- `git worktree add` execution and postcondition verification; and
- recognition of the `initializing` lock signature on retry, with the exact
  recovery commands in the error.

Splitting those rules between an environment variable and prose in a skill
would make the skill part of the implementation. An environment variable may
override machine-local configuration, but Dashpot rather than the agent should
interpret it:

```text
--worktree-root DIR
→ DASHPOT_WORKTREE_ROOT
→ machine-local Dashpot setting (worktreeRoot)
→ <anchor parent>/<anchor name>.worktrees/    (review outcome 4)
```

An absolute machine path does not belong in tracked Project configuration.

For existing work, the caller supplies a known Worktree path directly to the
launcher. Automatically finding "the Worktree for Issue 35" would require
either a path or Branch convention treated as authority or a durable
intended-work relationship; neither is part of the current model. Git already
lists every Worktree with its Branch, so a read-only listing can *suggest*
candidates by Branch name while saying plainly that the suggestion is a hint.

### 3. Launch or resume the selected harness

For a fresh session, the launcher starts the harness in the returned path.
Illustratively:

```bash
codex -C /home/ned/projects/dashpot.worktrees/35-propose-an-issue-worktree-protocol \
  "Pick up Issue 35 using the Dashpot workflow."
```

```bash
cd /home/ned/projects/dashpot.worktrees/35-propose-an-issue-worktree-protocol
claude "Pick up Issue 35 using the Dashpot workflow."
```

The proposed Claude adapter sets the process working directory and omits native
`--worktree`; the proposed Codex adapter passes `-C`. These are harness adapter
details, not Worktree identity. Native `--worktree` is avoided because it
places, names, bases (with a fetch), locks, and may reset the Worktree by its
own rules, and because reusing a name can reset a clean Worktree.

Completion criterion: the new Agent Session begins with its harness working root
and recorded Observation Location inside the selected Worktree.

**Relocation.** A running Claude Code session relocates with `EnterWorktree
path=<worktree>` (the path must be in `git worktree list`), after which hook
`cwd` follows it. Codex CLI 0.153.4 can resume the exact Agent Session Identity
and conversation history in a new client with `codex resume <session-id> -C
<worktree>`; the old client must exit before the new one starts, and the first
resumed turn publishes the new `cwd`. A fresh `codex -C` session remains the
compatibility fallback when that interface is unavailable. Because the Work
Store is per Worktree, relocation interacts with the Work Store. Review outcome
14 (ADR 0009): `work start`
at the new Worktree ends the same session's record at the old one only when
the session's freshest hook record, across every store reachable from the
Worktree, places the harness there; a `work start` issued from a tool call
that merely `cd`ed elsewhere, or from a sub-agent sharing the session, is
refused as wrong-location, and `stop` ends the record wherever it is. Because
`EnterWorktree` fires no ordinary lifecycle event, the Claude Code integration
adds a `PostToolUse` hook matched to `EnterWorktree` and `ExitWorktree`.
ADR 0029 now preserves an active Agent Run through that sequential Codex resume
only when the old client first records an exact target with `work relocate` and
the target hook proves the same Agent Session Identity with no client live or
unobservable elsewhere. The resumed workflow checks `work show` before using
`work start`. Merely running `cd` inside a tool call relocates nothing
(measured: the run is recorded with `unknown` activity because the harness's
hooks publish elsewhere).

**Trust.** Both harnesses apply per-directory trust; a fresh path is a fresh
trust decision for an interactive session. Non-interactive Codex `exec` did not
prompt (measured); interactive behavior and whether trust can be granted for a
parent directory are unverified.

### 4. Establish the Issue Binding

Inside the launched Agent Session and selected Worktree, the portable skill
runs:

```bash
dashpot work start 35
dashpot work show
```

Completion criterion: `show` reports this Agent Session working on the intended
canonical Issue Reference, and observation locates its Agent Run at the selected
Worktree with the Worktree's Branch.

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
Binding with `work start`, producing a distinct Agent Run. Handoff to Claude
Code should launch with `cd`, not `--worktree <name>`, so the reopen-and-reset
rule never applies.

### 7. Clean up separately

The proposed protocol does not automatically remove Worktrees or Branches.
Cleanup is destructive and must account for dirty state, active Agent Sessions,
active Agent Runs, Git locks (including a harness's own session locks and the
`initializing` signature), unmerged and unpushed commits, clone ownership, and
whether Dashpot can distinguish a Worktree it created from an external one.

Completion criterion for a future cleanup protocol: removal happens only after
an explicit request and a conservative safety check, with Branch deletion a
separate opt-in. A read-only "is this removable, and why not" report can
precede any removal command and needs no management metadata.

## Invariants

The review adds these as protocol invariants; each is checkable.

1. Creation never fetches, pushes, or deletes; the only refs it creates are the
   one reported Branch, and on failure it leaves no ref it did not report.
2. No Worktree, Branch, path, or launch argument is ever read as an Issue
   Binding; only the Work Store is.
3. One Issue may own any number of Worktrees; the interface never assumes
   "the" Worktree of an Issue.
4. A live Agent Session holds an active Work Store record in at most one
   linked Worktree of a Git Repository (independent clones keep the conflict
   diagnostic). Today this is a protocol obligation on the skill; review
   outcome 14 (ADR 0009) makes it product behavior of `work start` and
   `stop` for sessions whose hooks are installed.
5. The main Worktree and every existing Worktree are unchanged by creation,
   including their `git status`.
6. Every mutating command has a read-only counterpart that reports the same
   facts, and every result is available as JSON.
7. Anything created at a path the caller did not name is reported by absolute
   real path.

## Decision analysis

Each decision lists the viable options, this review's recommendation, the
evidence, a confidence, and what depends on it. Where the user has since made
the call, an **Outcome** line records it; the recommendation text is kept so
the reasoning stays reviewable.

### 1. Product contract: may a named command mutate Git?

- Options: (a) observation stays passive and a verb-named management command
  may mutate Git when invoked; (b) all mutation lives in a separate tool.
- Recommendation: (a), scoped to `dashpot worktree create` (and later any
  cleanup), with the passive contract restated as "observation never mutates;
  a management command mutates only what its name says, on explicit
  invocation". `dashpot init` and `dashpot integrate` already write files on
  request, so the precedent exists.
- Confidence: medium-high. Depends on nothing; decisions 2, 9, 10, and 11
  depend on it.
- **Outcome:** (a). Recorded as
  [ADR 0008](adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
  (accepted), which restates the invariant, lists creation's exact side
  effects (one path, one Branch, no fetch), and says cleanup and dispatch are
  not covered by it.

### 2. Smallest interface: directory only, or atomic creation?

- Options: (a) `worktree directory` returns a path and the caller runs Git;
  (b) `worktree create` performs and verifies the creation.
- Recommendation: (b). The measured failure modes (empty directory adoption,
  stray Branch after a lost path race, D/F conflicts, `initializing` locks,
  unverified configuration compatibility) are exactly the rules a skill would
  otherwise re-derive in prose for two harnesses.
- Confidence: high. Depends on 1.

### 3. Dispatch inside or outside Dashpot?

- Options: (a) outside, in the first version; (b) a later Dashpot launcher
  module; (c) part of this protocol.
- Recommendation: (a), keeping the launcher a two-line shell or human step.
  The only harness-specific facts are `-C` versus `cd`, and both harnesses
  already opt in correctly from a prepared Worktree (measured).
- Confidence: high for the first version. Decision 12 depends on it.

### 4. Configuration: root location, precedence, default

- Options for the default when nothing is configured: (a) refuse with an
  actionable error; (b) a deterministic sibling such as
  `<anchor parent>/<anchor name>.worktrees/`; (c) inside the repository.
- Recommendation: precedence `--worktree-root` (spelled to mirror the
  variable, as `--state-dir` mirrors `DASHPOT_STATE_DIR`) →
  `DASHPOT_WORKTREE_ROOT` → machine-local setting beside the existing
  platform state location → default. (c) is rejected because it dirties the main Worktree unless
  ignored (measured) and collides with Claude Code's own directory. Between
  (a) and (b) the review leans to (b) for the unprimed-agent workflow, with
  the root always reported in output.
- Confidence: medium. Decisions 7 and 13 depend on the root being stable.
- **Outcome:** (b), the sibling default, with (a)'s error when the sibling is
  not writable; the root and its source are always reported.

### 5. Base selection

- Options: (a) always require `--base`; (b) default to the caller's HEAD;
  (c) default to the Project's default Branch as last fetched.
- Recommendation: (c) with `--base` override, resolved to an exact commit and
  reported with its fetch age (ADR 0005: Dashpot never fetches). (b) stacks
  new work on whatever the caller happened to have checked out; Claude Code's
  own default is also the remote default Branch. A `--base` naming a Branch
  whose Worktree is dirty should be allowed but reported.
- Confidence: medium-high.
- **Outcome:** (c), resolved as `origin/HEAD` → a local `main` or `master`
  when exactly one exists → refuse naming `--base`. Only the first step is
  Git's own notion; the middle step is a Dashpot convention (Git has no
  fallback from a missing `origin/HEAD`), so the result reports which step
  chose the base.

### 6. Naming

- Reframed during review: the Branch name is an explicit `--branch` parameter
  of `worktree create`; the decision is whether it is mandatory or defaulted,
  and a prefix would only ever live inside the default.
- Options: (a) `--branch` mandatory; (b) optional, default
  `<number>-<title-slug>` — GitHub's own "Create a branch" convention for an
  Issue, and for a Local Issue its existing slug; (c) optional, default
  `<prefix><number>-<title-slug>` with a tracked Project `branchPrefix`.
- Recommendation: (b). (a) makes every agent invent a name, which is the
  deterministic policy the protocol exists to keep out of skills. A bare
  number would be a valid but poor name (numeric names collide with commit
  abbreviations and produce `refname is ambiguous` warnings, and say nothing
  on a shared remote); the slug fixes both without a tool prefix, and it
  matches what a teammate using GitHub's button would get. The title is
  mutable but the name is fixed at creation and never parsed back. Every
  name, default or given, is validated with `git check-ref-format --branch`;
  the path leaf is the Branch name with `/` replaced by `-`. Renaming is out
  of scope: Git can `git worktree move` and `git branch -m`, and nothing in
  Dashpot depends on the spelling.
- Confidence: medium-high.
- **Outcome:** (b). The earlier `--name` discriminator is dropped; (c) can be
  added later as a tracked setting without changing anything created.

### 7. Multiplicity

- Options when a Worktree whose Branch matches the Issue's naming already
  exists: (a) refuse and list it; (b) reuse it silently; (c) create a
  numbered sibling.
- Recommendation: (a) — refuse, print the existing candidates as hints, and
  let the caller pass a different `--branch` for an intentionally separate
  approach. (b) would make a naming convention an authority; (c) hides a
  decision.
- Confidence: high. Depends on 6.

### 8. Reuse and handoff

- Options: (a) the caller passes an existing path explicitly; (b) Dashpot
  persists a non-authoritative intended-Issue relationship.
- Recommendation: (a) for the first version, plus a read-only listing
  (`dashpot worktree list --json`, or the existing snapshot's
  `observationTargets`) that shows each Worktree's Branch so callers can
  choose. (b) is deferred until a real workflow needs it; the Work Store
  already records the last Worktree each run used.
- Confidence: medium-high.
- **Outcome:** defer (b). Name-based hints only, labelled as hints; a
  provenance record is reconsidered when cleanup or identity-stable lookup
  needs it, and would be a new domain term.

### 9. Independent clones

- Options: (a) creation is per Repository Anchor, the checkout the command
  runs in; (b) a preferred anchor setting.
- Recommendation: (a). A clone lists only its own Worktrees (measured), so
  the command reports which Git common directory the Worktree joined; a
  handoff across clones is an explicit path, as in decision 8.
- Confidence: high.

### 10. Failure ownership and rollback

- Options: (a) never roll back, always leave evidence; (b) roll back
  everything the command created; (c) bounded rollback.
- Recommendation: (c): if `git worktree add` fails in-process, delete the
  Branch only when this invocation created it, it still points at the base
  commit, and it is checked out nowhere; remove a path only when this
  invocation created an empty directory. Anything else — a kill, an
  `initializing` lock, a path someone else populated — is reported with the
  exact recovery commands and never removed. After a harness has started
  there is no rollback.
- Confidence: high. Depends on 2.

### 11. Cleanup ownership

- Options: (a) none in Dashpot; (b) a read-only removability report; (c) an
  explicit `worktree remove` with conservative checks; (d) Branch deletion.
- Recommendation: (b) first, (c) only after (a)/(b) prove insufficient, (d)
  never implied by (c). A removability report needs no metadata: dirty
  state, locks and their reasons, active Agent Runs and Sessions at the path,
  and unmerged/unpushed commits are all observable.
- Confidence: medium.
- **Outcome:** (b) only: a read-only `dashpot worktree check <path>` (spelling
  provisional) that reports removable or exactly why not, with the Git
  commands for each state. Dashpot removes nothing; (c) and (d) are not
  planned and would need their own decision.

### 12. Launch and Issue Binding provenance

- Options: (a) explicit in-session `work start` remains required; (b) a
  managed dispatch action becomes a new `bindingProvenance`.
- Recommendation: (a). The Work Store schema has room for (b), but (b) means
  a session is bound before it has run a command, which contradicts "created
  by an explicit opt-in from the running session". Revisit only with a
  Dashpot launcher.
- Confidence: high for now. Remains conditional: reopened only if dispatch
  moves inside Dashpot.

### 13. Skill distribution and version skew

- Options: (a) bundled and installed by `dashpot integrate <harness>`;
  (b) separate package; (c) documented copy.
- Recommendation: (a), because `integrate` already pins the publisher to the
  installed environment's absolute path and repairs stale paths, which is the
  same lock-step property a skill needs. The skill should call
  `dashpot --version` and refuse on a mismatch with the version it was
  written for.
- Confidence: medium. Depends on the commands stabilizing.
- **Outcome:** (a). The managed skill is bundled with Dashpot, installed at the
  harness's current user skill location, reported by `--status`, removed only
  when Dashpot owns it, and guarded by its written-for version.

### 14. Relocation invariant (new)

- Options: (a) skill obligation only; (b) `work start` at Worktree B ends the
  same session's active record at Worktree A of the same Project; (c)
  `work start` refuses while a record exists elsewhere.
- A live session acting through one process can move in place; a resumed Codex
  conversation can also keep its Agent Session Identity under a new process.
  Plain (b) is unsafe in exactly those
  cases: a tool call that `cd`s to B while the harness stays at A (measured:
  the run lands at B with `unknown` activity), and a Claude Code sub-agent in
  its own Worktree, which shares the main session's key. In both, the hooks
  Dashpot subscribes to still fire from A. Sandboxed identity claims are
  already refused at B because the confirming hook record is at A.
- Recommendation: (b′): end the record at A only when the session's
  *freshest* hook record — by `lastActivityAt`, across the hook stores of
  every Worktree `git worktree list` reports plus the global store — places
  the harness at B (a verified relocation, after which nobody is left at A);
  otherwise refuse the `start` at B as wrong-location. `stop` acts wherever
  the record is. Sandboxed claims validate against the same freshest record
  (today they accept any live record in the current Worktree's store, so a
  stale record at A would confirm a `start` there). Scope: the linked
  Worktrees of one Git Repository, not independent clones (ADR 0003). Because
  `EnterWorktree` fires no subscribed event, Claude Code's integration adds
  `PostToolUse` matched to `EnterWorktree` only (one invocation per
  relocation, so ADR 0006's cost finding does not apply); whether its `cwd`
  is already the new Worktree is a probe. Without installed hooks the process
  route cannot tell the cases apart, so there the sub-agent rule stays an
  instruction. A `--here`/`--move` override is rejected: it asserts
  relocation without evidence.
- Confidence: medium-high. Touches the Work Store's authority statement, so
  it needs a domain-language update and an ADR.
- **Outcome:** (b′), recorded as
  [ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)
  after adversarial review and accepted once the `PostToolUse(EnterWorktree)`
  probe below measured the new location.

### 15. Claude Code `WorktreeCreate` hook (new)

- Options: (a) ignore; (b) `dashpot integrate claude-code` optionally installs
  a `WorktreeCreate` hook mapping `name` to an Issue Hint so
  `claude --worktree 35` calls `dashpot worktree create 35`.
- Recommendation: (a) for the first version. The hook is user-global and
  replaces creation for every subagent and background session in every
  repository, its input carries no Issue, its Worktrees are exempt from
  Claude's sweep but keep transcripts at the launch directory, and Codex has
  no counterpart, so it would reintroduce harness-specific behavior.
- Confidence: medium-high. Depends on 3.
- **Outcome:** (a). Document the `cd` launch; an explicit opt-in hook with
  pass-through for non-Projects may be reconsidered once `worktree create`
  is stable, and is not planned.

### 16. Configuration compatibility of the base revision (new)

- Options: (a) require `.dashpot/config.json` at the base commit with the
  anchor's Project and Repository Identity; (b) require the file only;
  (c) no check.
- Recommendation: (a), read with `git show <base>:.dashpot/config.json` before
  any mutation. (b) is what the current code effectively assumes and lets a
  fork's identity through; (c) yields a Worktree where sessions are observed
  but can never opt in (measured).
- Confidence: high.

### 17. Output contract (new)

- Options: (a) human text only; (b) `--json` from the first version.
- Recommendation: (b), with camelCase keys matching the observation snapshot
  and exit code 2 for every refusal, as the CLI does today.
- Confidence: high.

### 18. Environments (new)

- Remote SSH and headless use are covered by the same commands because
  nothing depends on a terminal or a GUI; CI is a non-goal (no Agent Session
  to bind). A shared checkout used by several OS users is unsupported: Work
  Store and hook records are per Worktree and Git's `dubious ownership` check
  applies. Recommendation: state this in the docs; no design change.
- Confidence: medium.

## Competing designs

| Design | Consistency across harnesses | Contract impact | Policy duplication | Race and recovery | Destructive risk | Interface depth | Complexity | Skill simplicity | Migration |
|---|---|---|---|---|---|---|---|---|---|
| 1. Directory only; caller runs Git | Low: each skill re-derives naming, collisions, base, compatibility | None | High, in prose, per harness | Caller-specific; stray Branches likely | Low from Dashpot, medium from callers | Shallow | Lowest | Poor: skill is the implementation | Trivial |
| 2. Atomic `worktree create`; external launcher | High | One verb-named mutating command | None | Owned once, with measured signatures | Low: creates only | Deep: one call hides ten rules | Moderate | Good: resolve, create, launch, `work start` | Additive |
| 3. Managed Worktrees with durable ownership metadata | High | New management state | None | Best, but adds state to keep consistent | Medium: metadata invites automated removal | Deep but wider | High | Good | Needs a state schema and migration |
| 4. Dashpot dispatches and supervises harnesses | High | Dashpot becomes a controller | None | Adds process supervision | Medium-high | Widest | Highest | Best on paper | Largest |

Recommendation: **design 2**, which is also the smallest interface that keeps
deterministic policy out of agents. Design 1 fails the consistency and
duplication criteria on the measured evidence. Design 3 is not justified: Git
topology, Branch names, and the Work Store already answer every question the
first version asks, and the only metadata a later cleanup might want (a
"Dashpot created this" marker) can be a per-Worktree Git config key added when
cleanup is designed. Design 4 changes what Dashpot is (ADR 0001 and the README
call it a passive view) and should be a separate proposal if ever.

## Minimum viable protocol

1. `dashpot issue show <hint> [--json]` — public wrapper over the existing
   resolution module.
2. `dashpot worktree create <hint> [--base REF] [--branch NAME]
   [--worktree-root DIR] [--json]` — atomic, verified, non-fetching, bounded
   rollback; default Branch `<number>-<title-slug>`, default root the sibling
   `<anchor name>.worktrees/`.
3. A read-only listing of Worktrees with Branch facts (or the existing
   `dashpot --json` snapshot) for choosing an existing Worktree, and a
   read-only `dashpot worktree check <path>` removability report.
3a. `work start`/`stop` cross-Worktree semantics per outcome 14 (verified
   relocation moves the record; wrong-location `start` is refused; `stop`
   acts wherever the record is), with the matched `PostToolUse` hook for
   Claude Code.
4. Relocate Claude Code with `EnterWorktree`; resume Codex sequentially with
   `codex resume <session-id> -C <path>`, or launch a fresh session when resume
   is unsupported.
5. Preserve an active Codex run with `dashpot work relocate <path>` before
   exit; after resume use `show`, or `start <hint>` when no run was preserved.
   `stop` remains the terminal action.
6. Keep dispatch outside Dashpot, and distribute the common model-invoked skill
   through `dashpot integrate`; cleanup remains its own explicit workflow.

## Agent-facing skill shape

The shipped skill is model-invoked when a user asks an agent to start,
switch, finish, hand off, or recover declared Issue work, or to prepare a
Worktree for it. Its common own-session path should remain short:

1. Read repository instructions and use their prescribed Dashpot invocation.
2. Resolve the Issue through `dashpot issue show`.
3. Confirm this Agent Session is already in the Worktree where work will occur.
4. Run `dashpot work show`; retain a verified relocated run, otherwise run
   `dashpot work start` and verify it with `work show`.
5. Perform the repository's own workflow.
6. Run `dashpot work stop` at the terminal outcome and verify it stopped.

Worktree preparation or moving an Agent Session is progressively disclosed
behind a dispatch reference, which for Claude Code includes the
`EnterWorktree path=` → `work start` sequence and for Codex prefers `work
relocate` → sequential resume → `work show` before a fresh-session fallback.
Wrong-location sessions,
collisions, partial
creation (`initializing` locks), missing or incompatible configuration, dirty
Worktrees, conflicts across Worktrees, and Orphaned Agent Runs should be
disclosed behind a recovery reference. Deterministic path, Git, and Issue
Source rules belong in commands rather than scripts or prose in the skill.

## Review outcomes

The user walked through every decision the review left open on 2026-08-30 and
made these calls. They direct the implementation and the ADRs that record
them; the document stays a proposal for the commands it describes, which do
not exist yet.

| # | Decision | Outcome |
|---|---|---|
| 1 | Product contract | Named management commands may mutate on explicit invocation; observation stays passive. ADR to record the boundary and creation's exact side effects. |
| 4 | Worktree root default | `--worktree-root` → `DASHPOT_WORKTREE_ROOT` → machine-local setting → sibling `<anchor parent>/<anchor name>.worktrees/`; error only when that is not writable. |
| 5 | Base default | `origin/HEAD` → local `main`/`master` when exactly one exists → refuse naming `--base`; source reported. |
| 6 | Branch name | `--branch` optional; default `<number>-<title-slug>` (GitHub's Issue-branch convention); no prefix; path leaf follows the Branch; `--name` dropped. |
| 8 | Intended-work relationship | Deferred; name-based hints only, labelled as hints. |
| 11 | Cleanup | Read-only removability report only; Dashpot removes nothing. |
| 14 | Relocation | `work start` moves the session's record only on a verified relocation (freshest hook record across the Repository's stores at the new Worktree); otherwise refused as wrong-location; `stop` acts wherever the record is; Claude Code gains a `PostToolUse(EnterWorktree)` hook. Scoped to one Git Repository's linked Worktrees. ADR 0009. |
| 15 | Claude `WorktreeCreate` hook | Not offered; document the `cd` launch. |

Outcomes 1 and 14 are recorded as
[ADR 0008](adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
and
[ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md),
both accepted on 2026-08-30 under
[#54](https://github.com/ned2/dashpot/issues/54) — ADR 0009 once the
`PostToolUse(EnterWorktree)` probe below had been measured — and their
consequences are applied to the README product statement and domain language
and to `AGENTS.md`. The implementation is
tracked as [#55](https://github.com/ned2/dashpot/issues/55) (`work start`
cross-Worktree semantics), [#56](https://github.com/ned2/dashpot/issues/56)
(`issue show`), [#57](https://github.com/ned2/dashpot/issues/57)
(`worktree create` and `worktree check`, with interim `AGENTS.md`
instructions), and [#58](https://github.com/ned2/dashpot/issues/58) (the
agent-facing skill and its `integrate` distribution).

Decision 12 (binding provenance) stays conditional on dispatch ever moving
inside Dashpot. Decisions 2, 3, 7, 9, 10, 13, 16, 17, and 18 carry
recommendations the review considers settled enough to implement against.

## Review probes

Each probe records either a measured result from this review or the exact
acceptance test to run once the command exists. "Sim" is a disposable Local
Issue Markdown repository with Issues 35 and 36, a `main` Branch, and a tag
predating `.dashpot/config.json`.

| Probe | Status | Result or acceptance test |
|---|---|---|
| Bare `35` resolves source-neutrally | Implemented (#56) | `35`, `'#35'`, and the slug resolve to one Issue in Sim; `ned2/sim#35` fails in a Markdown Project by design. Test for `issue show`: same four inputs, `--json` carries `id`, `reference`, `location`. |
| Codex and Claude Code start beneath one parent without harness names in identity | Measured | `codex exec -C sim/wt-35` and `cd sim/wt-36 && claude -p` each opted in; Worktree paths and Branches (`sim/35`, `sim/36`) carry no harness. |
| One harness hands an existing Worktree to the other | Partly measured | Handoff is a `cd`/`-C` into the same path; opt-in works from either harness at the same Worktree (measured with hook records of both harnesses at `wt-35`). Test: Codex `work stop`, then Claude launches at the same path, `work start 35`, snapshot lists one run at that Worktree with a new `startedAt`; `git worktree list` unchanged. |
| Two independent approaches to one Issue | Implemented (#57) | `worktree create 35` then `worktree create 35` refuses and lists the existing path; `worktree create 35 --branch 35-alternate` creates `35-alternate`; both opt in to the same Issue Identity as separate runs; no `work-session-conflict`. |
| Base predating configuration fails before creation | Implemented (#57) | A Worktree at the pre-config tag is observed but `work start` fails there. Test: `worktree create 35 --base pre-config` exits 2 naming the missing or mismatched configuration and creates no path or ref. |
| Existing path and Branch collisions | Implemented (#57) | Non-empty path and existing Branch fail; empty directory and unused Branch are adopted by Git. Test: `worktree create` refuses all four unless an explicit adoption option is passed, and refuses `35/alt`-style names. |
| Concurrent creators | Implemented (#57) | Same path: one wins, loser leaves a stray Branch. Test: two simultaneous `worktree create 35` yield exactly one Worktree, one Branch, and one exit-2 error naming the winner. |
| Partial Git failure and recovery evidence | Implemented (#57) | SIGKILL leaves `locked initializing`; retry fails. Test: a retry after a simulated kill reports the lock reason and the `remove -f -f` / `branch -D` recovery, mutating nothing. |
| Main Worktree stays clean, no machine-local state committed | Measured | Outside-repository Worktrees leave `git status` empty; `.dashpot/state/` stayed absent in the main Worktree. |
| Correct Agent Session, Agent Run, Worktree, Branch, and Issue Binding observed | Measured | Snapshot from the main Worktree listed each run with its Worktree, Branch, and Issue Identity; after the sessions ended, one `work-session-orphaned` diagnostic per run named the right Worktree. |
| Finished work leaves a reusable Worktree without automatic cleanup | Measured | Both Worktrees remained registered and clean after the sessions ended; nothing removed them. Cleanup refusal test deferred with decision 11. |
| Relocation leaves no stale binding | Implemented (#55) | `work start` at B for a session whose freshest hook record is at B ends its run at A and reports `switched from <ref> at A to <ref> at B`; observation lists one run at B, no conflict; `stop` at B ends a run held at A. A `start` where the freshest record places the session elsewhere — a tool-call `cd`, a sub-agent's Worktree, or a sandboxed `start` at A after the move — is refused and writes nothing. Covered by `tests/test_work.py` through the `WorkStore`, hook-record, and fake-process seams, and measured end to end (Claude Code 2.1.251, Sim with the matched `PostToolUse` hook): `work start 35` at A, `EnterWorktree path=B`, `work start 35`, `work show`, `work stop` in one turn reported the switch, listed one run at B, and ended it; the snapshot from the main Worktree afterwards listed no run and no diagnostic. |
| Active Codex run survives sequential resume | Implemented (#137) | `work relocate B` records an exact target without changing the run identity or `startedAt`; `SessionEnd` preserves it, and the first eligible same-identity hook at B moves the record and adopts the resumed process. Fake lifecycle tests cover process and sandboxed identity routes, concurrent clients, a killed old client, mismatched and missing target evidence, cancellation at the origin, passive pending observation, and unchanged Claude Code behavior. Live Codex 0.153.4 evidence from #58 established that sequential resume retains the identity, conversation, and target hook location; #137 does not generalise beyond that measured harness interface. |
| `PostToolUse(EnterWorktree)` reports the new location | Measured (2026-08-30, Claude Code 2.1.251) | With a project-level `PostToolUse` hook matched to `EnterWorktree` running the installed publisher in Sim (linked Worktrees A and B), a session started at A that called `EnterWorktree path=B` fired the hook once; its input carried `tool_name: EnterWorktree` and `cwd` at B, and the record written from that event had `cwd`, `repositoryRoot`, and `branch` at B and was the freshest for the session across both stores (A kept the earlier `UserPromptSubmit`). ADR 0009 is accepted without its fallback: `work start` may follow `EnterWorktree` in the same turn. The session's graceful `SessionEnd` at B removed only B's record; A's is pruned as gone. |
| Removability report | Implemented (#57) | `worktree check` on a clean idle Worktree reports removable; on a dirty one, a locked one (`initializing`, a live Claude session lock, a user lock), one with an active Agent Run, and one with unpushed commits it reports each reason with its Git command, and mutates nothing. |
| Default naming and root | Implemented (#57) | With no root configured, `worktree create 35` in `~/p/sim` creates `~/p/sim.worktrees/35-worktree-protocol` on Branch `35-worktree-protocol` from `origin/HEAD`, and the JSON names both sources; with no `origin/HEAD` and one local `main` it reports the guess; with neither it exits 2 naming `--base`. |
| Skill forward-test | Measured (2026-09-05, Codex 0.153.4 and Claude Code 2.1.261) | Given the same ordinary Issue-work prompt in separate disposable Local Markdown Projects, each unprimed harness selected the installed `dashpot-issue-work` skill. Codex resolved and created the Worktree, refused to treat a tool working directory as relocation, and its hook-enabled fresh-session fallback completed `work start` / `show` / `stop` / `show`; the separate sequential-resume probe above remains the evidence for identity and conversation continuity. Claude Code resolved and created the Worktree, required interactive confirmation for `EnterWorktree`, then its matched hook confirmed the new location and the same lifecycle completed. Both Worktrees stayed clean; the final snapshots had no Orphaned Agent Run. |

The forward test also bounded two harness behaviors rather than generalising
past them. A non-interactive Codex child did not publish lifecycle records after
the user hook file changed until the vetted acceptance invocation bypassed hook
trust; the ordinary workflow must instead have a person review the hook in an
interactive client. Claude Code refused `EnterWorktree` twice in print mode,
including with the tool allowlisted, because relocation outside
`.claude/worktrees/` requires interactive confirmation. In both cases the skill
stopped before `work start`, so neither missing permission became a false Issue
Binding. These are explicit automation limitations, not evidence that hook
trust or relocation confirmation may be bypassed in routine work.

The rows marked *Implemented (#56)* and *(#57)* are covered by
`tests/test_issue_resolution.py`, `tests/test_worktrees.py`, and
`tests/test_cli.py` against disposable Local Issue Markdown repositories, and
the conventions they exercise are recorded in
[ADR 0011](adr/0011-prepare-issue-worktrees-by-convention.md). Two
implementation choices go beyond the table: `worktree create` also refuses a
`--branch` that an existing Branch extends with `/` (the reverse of the D/F
conflict measured above), and a lost race whose winner is still adding the
Worktree is reported as `locked 'initializing'` with the recovery commands
qualified by "if it stays locked", since the same lock signature is both a
creation in progress and a killed one.

## Decision path

1. Accept ADRs 0008 and 0009 (#54) and update the README product statement
   and the domain language with them; command spelling stays provisional.
2. Implement outcome 14 in `work start` first (#55): it changes existing
   behavior and is testable through the `WorkStore` and fake process lookup
   seams without any new command.
3. Implement `issue show` (#56), then `worktree create` and `worktree check`
   (#57) with the acceptance tests in the probe table, against disposable
   repositories and both harnesses, adding interim `AGENTS.md` instructions.
   Done under ADR 0011; the harness end-to-end run is the skill's forward-test.
4. Rerun the review probes, including the relocation probe, before writing the
   model-invoked skill.
5. Write and distribute the skill through `dashpot integrate` (#58), pruning
   instructions that product behavior makes redundant, and run the unprimed
   live prompt as a release check.
6. Preserve an already-active Codex Agent Run through the measured sequential
   resume only after an explicit Relocation Intent and matching target hook
   evidence (#137, ADR 0029).
