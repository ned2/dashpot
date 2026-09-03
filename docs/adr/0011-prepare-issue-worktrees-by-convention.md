---
status: amended
date: 2026-08-30
amended-by: 0019
---

# Prepare Issue Worktrees by convention, and only report their removability

[ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)
lets `dashpot worktree create` create one linked Worktree for an Issue. It
does not say where the Worktree goes, what its Branch is called, which commit
it starts from, or what happens when one already exists. The
[agent Worktree handoff proposal](../proposed-agent-worktree-protocol.md)
walked those decisions with the user on 2026-08-30 (review outcomes 4, 5, 6,
8, and 11, and recommendations 7 and 16); this ADR records them as the
conventions the command owns, so that no agent skill re-derives them.

- **Issue resolution is source-neutral and shared.** `dashpot issue show`
  and `worktree create` resolve an Issue Hint through the same module as
  `work start` (`issue_resolution.py`): a bare or `#`-prefixed Issue Number,
  a full Issue Reference, or a Local Issue slug, against a fresh Issue
  Source, to exactly one Issue. A full GitHub reference therefore resolves
  only in a GitHub Project and a slug only in a Local Issue Markdown one.
- **Worktree root.** `--worktree-root DIR`, else `DASHPOT_WORKTREE_ROOT`,
  else the machine-local `worktreeRoot` setting in
  `~/.config/dashpot/settings.json`, else the sibling directory
  `<anchor parent>/<anchor name>.worktrees/`. The root is real-path
  normalised, refused when it resolves inside any Worktree of the Project,
  and always reported with the source that chose it. An absolute machine
  path never belongs in the tracked Project configuration.
- **Base.** `--base REF`, else `origin/HEAD`, else the one local `main` or
  `master` when exactly one exists, else refusal naming `--base`. The base
  is resolved to an exact commit and never fetched
  ([ADR 0005](0005-observe-branches-without-fetching.md)); only the first
  step is Git's own notion, so the result reports which step chose it.
- **Branch.** `--branch NAME`, else GitHub's own Issue-branch convention
  `<number>-<title-slug>` (a Local Issue's slug). Every name is validated
  with `git check-ref-format --branch`; a name that would extend an existing
  Branch with `/`, or that an existing Branch extends, is refused before
  Git is called (the measured `cannot lock ref` conflict). The path leaf is
  the Branch name with `/` replaced by `-`. Names describe workstreams, are
  fixed at creation, and are never parsed back into an Issue Binding.
- **Compatibility.** `git show <base>:.dashpot/config.json` must carry the
  Repository Anchor's Project Identity and Repository Identity, checked
  before any mutation; a base predating configuration or configuring another
  Project is refused, because a session there could be observed but never
  opt in.
- **Multiplicity.** One Issue may own any number of Worktrees. With the
  default Branch name, an existing Worktree whose Branch starts with the
  Issue Number is a refusal that lists it as a hint; `--branch` names a
  second approach. Nothing persists an intended-Issue relationship: the
  Branch name is an Issue Hint, and the Work Store stays the sole authority.
- **Collisions and rollback.** A non-empty path, an empty directory the
  invocation did not create, an existing or checked-out Branch, and a
  registered Worktree — including one locked `initializing` by a killed
  `add`, reported with `git worktree remove -f -f` and `git branch -D` —
  are refused and left alone. When `git worktree add` fails in-process, the
  command deletes only a Branch it created that still points at the base
  commit and is checked out nowhere, and only the empty directories it
  created; everything else is reported and left in place.
- **Cleanup.** `dashpot worktree check <path>` is a read-only removability
  report: dirty state, a lock with its reason and whether the holding process
  is alive, Agent Sessions whose hooks place them at the path, Agent Runs
  recorded there, and unpushed or unmerged commits, each with the command
  that acts on it. Dashpot removes nothing; a `worktree remove` or Branch
  deletion would need its own decision.

## Considered options

- **Mandatory `--branch`:** rejected because it makes every agent invent a
  name, which is the deterministic policy the protocol exists to keep out of
  skills; a bare number was rejected as a default because numeric names
  collide with commit abbreviations and say nothing on a shared remote.
- **A tracked `branchPrefix` or Worktree root in `.dashpot/config.json`:**
  deferred; a prefix can be added inside the default later without changing
  anything created, and a machine path is not Project configuration.
- **Defaulting the base to the caller's HEAD:** rejected because it stacks
  new work on whatever happened to be checked out; the remote default Branch
  as last fetched is also what Claude Code's own `--worktree` uses.
- **Reusing or numbering a Worktree whose Branch matches the Issue:**
  rejected because reuse makes a naming convention an authority and a
  numbered sibling hides a decision.
- **A persisted "Dashpot created this" or intended-Issue record:** deferred
  until cleanup or identity-stable lookup needs it; it would be a new domain
  term.
- **`worktree remove`:** not planned; only the report exists until it proves
  insufficient.

## Consequences

- `dashpot issue show`, `dashpot worktree create` (with `--dry-run` and
  `--json`), and `dashpot worktree check` exist as described in the README's
  [Issue Worktrees](../../README.md#issue-worktrees) section, tested against
  disposable Local Issue Markdown repositories only.
- The domain language gains **Issue Worktree** and **Worktree Root**; a
  Worktree's path and Branch remain Issue Hints.
- `AGENTS.md` carries an interim *Preparing a Worktree for an Issue*
  sequence until the agent-facing skill ([#58](https://github.com/ned2/dashpot/issues/58))
  replaces it.
- The default Worktree root is a sibling of the Repository Anchor, so a
  command run from a linked Worktree that itself lives inside the main
  Worktree (Claude Code's `.claude/worktrees/`) must name a root explicitly.
- Amended by [ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md):
  the Cleanup convention above — "Dashpot removes nothing", and `worktree
  remove` as "not planned" — held only while the report was the whole
  answer. `dashpot worktree remove` and `dashpot branch delete` now exist,
  and the dashboard's `x` key invokes them; they remove only what their
  flags name, unforced, only when integrated, and only from a preview a
  person confirmed. `worktree check` is unchanged and still read-only.
