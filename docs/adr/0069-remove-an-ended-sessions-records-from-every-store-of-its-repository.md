---
status: accepted
date: 2026-10-01
---

# Remove an ended session's records from every store of its Repository

[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
has a `SessionEnd` remove the session's older hook records "at the
Repository's other Worktrees", so that a record a Live Relocation left behind
does not become the session's freshest, read live and occupy its Worktree
while a shared Codex process keeps running. The
[lifecycle design](../agent-runtime-lifecycle-design.md#live-relocation)
lists the guards: the record carries the session's own identity, names the
Host Process the `SessionEnd` itself was observed from (both observed), and
is not newer than the `SessionEnd`.

A session's record is not always in a Worktree's own store. A Worktree whose
checkout carries no Dashpot configuration routes its records to the global
store ([ADR 0003](0003-prefer-project-local-dashpot-state.md)), and a record
there still places the session at that Worktree for `work start`, `work show`
and Cleanup occupancy. Reading "other Worktrees" as "other Worktrees' own
stores" would leave exactly the stale live record the rule exists to remove
whenever the session had passed through such a Worktree.

Dashpot therefore removes, under the session's hook-store locks, the
session's records in every reachable hook store of its Repository other than
the one the `SessionEnd` was written to (each Worktree's store and the global
store), but only a record that places the session at a Worktree of that
Repository and passes every guard the design lists. A record in the global
store that places the session outside the Repository is untouched.

## Considered options

- **Only the other Worktrees' own stores:** rejected. A record left in the
  global store by an unconfigured Worktree would keep reading live after the
  session ended, which is the defect the rule fixes.
- **Every record of the session in any store, wherever it places it:**
  rejected. A record outside the Repository is not this Repository's
  evidence, and the `SessionEnd` was not observed there.

## Consequences

- A session that ends leaves no live record in its Repository written by its
  own Host Process before the end, whichever store held it.
- The guards are unchanged, so another process's `SessionEnd` for the same
  identity, an unobservable Host Process, and a record written after the
  `SessionEnd` (a cold resume's `SessionStart` at the target) remove nothing.
