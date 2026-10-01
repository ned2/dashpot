---
status: accepted
date: 2026-10-01
---

# Carry a Claude Code run only on its worktree tools

[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
names Claude Code's designated location evidence as the `PostToolUse` of
`EnterWorktree` or of `ExitWorktree` with `action: keep`, and leaves two
questions to [#162](https://github.com/ned2/dashpot/issues/162): what a
persistent shell `cd` into another Worktree does to the session's Agent Run,
and what `ExitWorktree` with `action: remove` does. A Claude Code session
reaches another Worktree in three ways, measured on Linux against 2.1.286 by
the [acceptance runner](../../scripts/experiments/claude-162/run.mjs) through
Dashpot's real publisher
([measurement](../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286)):

- **The worktree tools.** `EnterWorktree` and `ExitWorktree` move the
  session's process, its shell and its later hooks. Each fires its matched
  `PostToolUse` once, with `cwd` already at the Worktree it reached, and
  fires no lifecycle hook.
- **A persistent shell `cd`.** The main conversation's `cd` into a directory
  inside the project persists to its next Bash call, and every later hook
  reports the new `cwd`
  ([2.1.285 measurement](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)).
  The `Stop` of a turn whose shell entered a nested linked Worktree reported
  that Worktree, so the session's freshest record placed it there, and a
  later `EnterWorktree` to that Worktree failed with "Cannot enter worktree:
  … is the current working directory". A `cd` outside the project is reset
  and moves nothing.
- **`ExitWorktree` with `action: remove`.** On a Worktree the session entered
  by `path`, which is how the Issue-work skill enters one, Claude Code refuses
  it ("This session is not the owner of the worktree") and fires no
  `PostToolUse`. On a Worktree `EnterWorktree` created by `name` under
  `.claude/worktrees/`, it deletes the Worktree, Work Store included, and its
  `PostToolUse` arrives at the original checkout afterwards.

## Decision

Only the worktree tools carry a Claude Code session's run. The adapter
designates the `PostToolUse` of `EnterWorktree`, and of `ExitWorktree` whose
`tool_input.action` is `keep`; a run the same Host Process holds moves with
the session under ADR 0067's Live Relocation conditions, and a session
without a run gains none.

A persistent shell `cd` is not location evidence. Its later hooks still place
the session where its shell is, since Observation Location follows the
freshest hook record, but the run stays where it is and observation reports
it with `work-session-elsewhere`, naming the Worktree the session is now in.
The session recovers by `work start` there, which switches the run under
[ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md), or by
a `cd` back to the Worktree holding the run. Dashpot does not subscribe
`CwdChanged`.

`ExitWorktree` with `action: remove` is not designated. On a Worktree entered
by path it never succeeds, and on a managed Worktree the run it would carry
is deleted with the Worktree before the hook fires, so there is nothing left
to move. A run held in a managed Worktree is lost with it, as with any
Worktree removed outside Dashpot's Cleanup.

## Considered options

- **Carry on a persistent `cd`, through `CwdChanged` or the next hook's
  `cwd`.** Rejected. A shell `cd` is the ordinary way to run a command
  somewhere, often in a nested checkout for a moment; a `cd` outside the
  project fires `CwdChanged` naming a directory the shell was then reset
  from; and ADR 0067 rejected carrying on any fresher record because a
  `cd`, a sub-agent's hook or a late event would move a run without a live
  move. Codex keeps the same rule: a `cd` inside a tool call is wrong-location
  evidence ([ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md)).
- **Treat the `cd` as a move once the session runs a turn there.** Rejected:
  a turn boundary says where the shell is, not that the session meant to
  move its Issue work, and the explicit route, `work start`, is one command
  away and named by the diagnostic.
- **Designate `ExitWorktree(remove)` to carry the run back.** Rejected: the
  run's Work Store no longer exists when the hook arrives, and on a
  path-entered Worktree the call is refused.

## Consequences

- A Claude Code session that enters a Worktree, or returns from one with
  `keep`, takes its run along; the Issue-work skill runs `work show` after
  `EnterWorktree` and `work start` only when no carried run is shown, and
  returns with `ExitWorktree(keep)`.
- A session whose shell `cd`s into another Worktree is shown with its run
  left behind until it runs `work start` there or its shell returns. Killed
  in that state, its run is orphaned where it was bound.
- `ExitWorktree(remove)` of a Worktree that `EnterWorktree` created by `name`
  is unsupported for Issue work: the run is lost with the managed Worktree.
