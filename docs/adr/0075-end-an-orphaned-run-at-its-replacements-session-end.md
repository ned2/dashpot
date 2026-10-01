---
status: accepted
date: 2026-10-01
---

# End an orphaned run at its replacement's SessionEnd

[ADR 0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
continues an Orphaned Agent Run when a hook of the same Agent Session arrives
from a new Host Process at the Worktree holding the run, once the recorded
process is proven gone and the harness runs each session in its own process.
`SessionEnd` ends a run only when it comes from the Host Process the run
records ([ADR 0015](0015-reconcile-the-agent-run-at-session-end.md),
[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)),
and the publisher handled it before, and instead of, any continuation.

The [#162 acceptance run](../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286)
on Claude Code 2.1.286 found a sequence those two rules leave stuck. A
supervised worker bound to an Issue entered a sibling Worktree with
`EnterWorktree`, carrying its run there, and was killed with SIGKILL. The
supervisor replaced it with a `--resume` process whose cwd was the sibling,
but whose `SessionStart` (`source` = `resume`) reported the directory the
worker was first launched in, so that hook reached the wrong Worktree and
continued nothing. The run waits, orphaned, for the replacement's first
turn. When the replacement is stopped with `claude stop` before any turn,
its only hook at the sibling is `SessionEnd`, from a process the run does not
record, so it ended nothing and the run stayed orphaned with no hook left to
end it.

## Decision

A session's own `SessionEnd`, one that carries no `agent_id`, first applies
ADR 0053's continuation and then ends the session's run. The continuation's
conditions are unchanged: the same Agent Session Identity, the recorded Host
Process proven `gone` (never `unknown`, and not `live`), a harness whose
adapter declares `exclusive_session_process`, the run held at the Worktree
whose store receives the `SessionEnd`, no pending Relocation Intent, and the
compare-and-replace under the record's lock. When they hold, the run now
names the ending process, and the ordinary ending removes it.

The hook's `hook.outcome` Runtime Event reports its Work Store change as
`ended`, not as a continuation followed by an end. The continuation is a
step of the ending, and nothing reads the agent context a continuation would
otherwise add to a `SessionEnd`.

## Considered options

- **End any orphaned run of the identity on `SessionEnd`.** Rejected: an
  unobservable or live recorded process is not proven ended, a run at another
  Worktree may belong to a resumed client still there, and Codex's shared
  daemon outlives its threads.
- **Leave it, and rely on `work stop --session`.** Rejected: the run would
  stay orphaned after the person had explicitly stopped the worker, which is
  exactly the positive ending evidence ADR 0067 asks for.
- **Prefer the replacement's process `cwd` over the stale `SessionStart`
  `cwd`.** Rejected: the hook's `cwd` is the only location evidence a hook
  publishes, and correcting it from `/proc` would make one harness release's
  quirk part of the location rule.

## Consequences

- A replaced Claude Code worker stopped before its first turn ends its run,
  as a stopped worker that was never replaced already did.
- Codex, whose adapter declares no exclusive process, is unchanged.
- This amends ADR 0053 without changing when a run continues, only that a
  `SessionEnd` may be the hook that continues it, and amends ADR 0015, whose
  `SessionEnd` now ends a run it first continued.
