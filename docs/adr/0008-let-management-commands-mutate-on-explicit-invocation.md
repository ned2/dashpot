---
status: amended
date: 2026-08-30
amended-by: 0014-fetch-remotes-on-explicit-key-press.md, 0019-remove-branches-and-worktrees-on-explicit-confirmation.md, 0029-preserve-agent-runs-through-declared-codex-relocation.md
---

# Let named management commands mutate on explicit invocation

Dashpot describes itself as a passive view that "observes and never controls"
(`AGENTS.md`, [ADR 0005](0005-observe-branches-without-fetching.md)). The
contract as implemented is narrower than the slogan. Three things write:
observation, which prunes ended or gone hook records and reclaims orphaned
lock files in the hook store and the Work Store — housekeeping of Dashpot's
own ignored state, never the Git Repository's refs, objects, or working trees
(its `git status` probe may refresh `.git/index`, as any status does); the
hook publisher, which the harness invokes on lifecycle events and which
writes only that session's own hook record; and explicitly invoked commands —
`dashpot init` writes `.dashpot/config.json`, `dashpot integrate` edits or
removes a harness's user-level hook file, and `dashpot work start`, `dashpot
work relocate`, and `dashpot work stop` write the Work Store — each touching
only what its name says.

The [agent Worktree handoff proposal](../proposed-agent-worktree-protocol.md)
needs a command that creates a Git-linked Worktree for an Issue. The review
measured why that cannot be left to callers: `git worktree add` silently
adopts an empty directory, a lost path race leaves the loser's `-b` Branch
behind, a Branch named `35` blocks `35/alt`, and a killed `add` leaves a
registered Worktree locked `initializing` that blocks every retry. Those rules
would otherwise be re-derived in prose by every agent skill, once per harness.

Dashpot will therefore keep observation passive and let a verb-named
management command mutate, on explicit invocation, exactly what its name says:

- Observation — the TUI, `dashpot --json`, and every refresh — never changes
  the Git Repository or anything outside Dashpot's own ignored state. Hook
  publishing writes only the publishing session's record.
- A management command performs only the mutation its name states, and
  reports what it changed, including anything left behind when it fails.
  `dashpot worktree create` creates one linked Worktree at one path outside
  every existing Worktree of the Project, and one new Branch; it never
  fetches, pushes, merges, deletes, or moves anything, and on failure it
  removes only what the same invocation created.
- Every management command introduced under this decision has a read-only
  counterpart that reports what the mutation would do or has done — for
  `worktree create`, a `--dry-run` that reports the path, Branch, base
  commit, and refusals without calling Git — and its result is available as
  JSON.

Launching harnesses is not covered by this decision. Removing Worktrees and
Branches was left out of it as well, until
[ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)
admitted it under the same boundary as a previewed, explicitly confirmed
mutation of the targets a person selects.

## Considered options

- **A separate tool or entry point for mutation:** rejected because it would
  need the same Issue resolution, Project configuration, and Work Store code,
  and agents would carry two version-skewed CLIs for one protocol; the split
  changes nothing that runs while `init`, `integrate`, and `work` stay where
  they are.
- **No Git mutation anywhere in Dashpot:** rejected because the only design
  it leaves — Dashpot names a directory and the caller runs Git — moves the
  measured collision, race, and recovery rules into agent skills, which is
  the outcome the protocol exists to prevent.
- **Let the harness create the Worktree** (Claude Code `--worktree` or a
  `WorktreeCreate` hook): rejected because it places, names, bases (with a
  fetch), locks, and may reset a reused Worktree by Claude Code's own rules,
  the hook is user-global and fires for every subagent in every repository,
  and Codex has no counterpart.
- **Mutation as a side effect of observation, such as pruning stale Worktrees
  during refresh:** rejected; housekeeping of Dashpot's own state stays the
  only write observation makes.

## Consequences

- The product statement in `README.md` and `AGENTS.md` is reworded to say
  that observation never mutates and that named management commands mutate
  only what they name on explicit invocation; ADR 0005's "passive view" is
  read as this ADR's "observation".
- `dashpot worktree create` may be implemented under this boundary with its
  `--dry-run` counterpart and JSON output, tested like `init` and `work` in
  `tests/test_cli.py`; its rollback is bounded to the Branch and empty
  directory the invocation itself created, and anything else — a kill, an
  `initializing` lock, a populated path — is reported with the exact recovery
  commands and left in place.
- `dashpot worktree check` is read-only and answers a different question
  (removability); `worktree remove` and Branch deletion are admitted by
  [ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md).
- Future management commands are argued against this boundary, not against
  the slogan.
- [ADR 0014](0014-fetch-remotes-on-explicit-key-press.md) admits one named
  mutation invoked from the TUI under the same boundary: the `f` key fetches
  and prunes the remotes of the Repository Anchor whose refs supplied the
  Branch observation, and nothing else.
- [ADR 0015](0015-reconcile-the-agent-run-at-session-end.md) classes ending
  the session's own Agent Run at its graceful `SessionEnd` with the hook's
  removal of its own record: housekeeping of Dashpot's state by the hook the
  harness invokes for that session, not a mutation of anyone else's work.
