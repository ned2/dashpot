---
status: accepted
date: 2026-09-23
---

# Continue an Orphaned Agent Run when its session resumes

`SessionEnd` ends a session's Agent Run
([ADR 0015](0015-reconcile-the-agent-run-at-session-end.md)), but it is not
guaranteed to fire: a crashed machine, a killed harness, or a closed terminal
delivers none. The run then outlives its process as an Orphaned Agent Run.
Until now observation excluded that run from the listed runs and raised a
`work-session-orphaned` warning in the dashboard's alert, and the only way out
was `dashpot work stop --session`. Resuming the conversation, which is what a
person whose machine crashed does, did not help: the resumed process is a new
host process, so its hooks never matched the recorded one and the warning
stayed until someone ran the stop command by hand
([#292](https://github.com/ned2/dashpot/issues/292)).

[#261](https://github.com/ned2/dashpot/issues/261) asks what happens to an
Agent Run and its Issue Binding across such boundaries, and requires an
explicit decision before any harness's behaviour extends or differs from the
declared Codex relocation of
[ADR 0029](0029-preserve-agent-runs-through-declared-codex-relocation.md).
This is that decision. It is one harness-agnostic rule; each harness adapter
states whether its evidence can satisfy it.

## Decision

A hook from a new host process continues an active Agent Run, carrying the
run over to that process with its Issue Binding and `startedAt` intact, only
when every one of these holds:

1. **Same native identity.** The hook publishes the harness-scoped Agent
   Session Identity the run records
   ([ADR 0038](0038-isolate-native-agent-session-identities.md)). A forked
   conversation has a new identity and continues nothing.
2. **The previous runtime is proven gone.** Session Liveness of the recorded
   host process is `gone`. `unknown` is never evidence that it ended, and a
   `live` recorded process means two clients claim the conversation, so
   neither case continues the run. The proof only means the session's own
   runtime ended when the harness's host process serves exactly one Agent
   Session; the adapter declares this as `exclusive_session_process`.
3. **Same Worktree.** The hook's Work Store is the one that records the run.
   A resume at another Worktree leaves the run where it was; moving work
   between Worktrees remains the declared relocation of ADR 0029.
4. **No other live claimant.** The carry-over is a compare-and-replace under
   the record's lock, so when two resumed clients race, the first keeps the
   run and the second finds the recorded process live. The check is the
   run's recorded process, not every hook record of the identity: a client
   that never reached this Worktree holds no run here to protect.

A run carrying a Relocation Intent is left to ADR 0029's verification. When
the hook continues a run on `SessionStart`, `UserPromptSubmit`, or
`PostToolUse`, it tells the resumed agent through the harness's additional
context that its Issue work continued, and names `dashpot work show` and
`dashpot work stop`.

Until a session resumes or someone ends its run, observation lists the run
marked `orphaned`, in place of the warning. The Agent Run's `state` stays
`unknown`, since nothing is running a turn. Its `lastActivityAt` is when the
gone session's hook record last saw it, so observation keeps that record while
an orphaned run still needs it. A gone record at a Worktree the pass did not
observe is kept only while that Worktree's Work Store holds the session's run,
so an unconfigured checkout's or a removed Worktree's records are still
pruned. `hostRestarted` says whether the host has
booted since the recorded process started, when both instants are known. The
dashboard gives the run its own activity Glyph and ranks it between waiting
and unknown. In the Sessions pane, `y` copies the command that resumes the
session where it ran.

### Per-harness evidence

| Harness | Exclusive session process | Continues |
|---|---|---|
| Claude Code | Yes: one `claude` process per conversation; sub-agents share it | Yes |
| Codex, daemon-hosted | No: one app-server serves many threads | No |
| Codex, no daemon | Unmeasured | No, until measured |
| OpenCode ([design](../opencode-integration-design.md)) | No: one backend serves many sessions | No |

Only Claude Code's adapter declares `exclusive_session_process`. A Codex
thread resumed at the same Worktree after a crash keeps showing an orphaned
run, and a person ends it or the session starts its work again. Claude Code's
background workers name their host process by version (`2.1.276`), and
Dashpot does not yet locate them as Claude Code hosts. The respawned-worker
case therefore only continues once that locating lands; the crash-and-resume
case works now.

## Considered options

- **Keep the warning and require `work stop`:** rejected. A crash is not a
  fault in Dashpot's state, and the warning could not be cleared by the most
  natural recovery, resuming the session.
- **End the run once its process is gone:** rejected. Observation must never
  treat a gone process as a graceful end (ADR 0015). A person who resumes
  after a crash expects the work to still be bound.
- **Continue whenever the identity reappears:** still rejected, as in ADR 0029.
  Condition 2 is what distinguishes this rule: it needs the previous runtime
  proven gone and exclusive to the session, and it never continues across
  Worktrees.
- **A Claude Code-only rule:** rejected in favour of one rule with declared
  per-harness evidence, so a future harness is admitted by measuring it, not
  by a new exception.
- **Ending the run from the Cleanup preview:** deferred. `work stop --session`
  remains the explicit end, and `dashpot worktree check` at the run's
  Worktree names it.

## Consequences

- The `work-session-orphaned` diagnostic is gone. An orphaned run is a
  visible, resumable row, not an alert.
- The published `AgentRun` gains `orphaned` and `hostRestarted`, a
  compatibility change to the JSON contract. `state` keeps its meaning.
- A gone session's hook record now survives observation while an Orphaned
  Agent Run needs it, and is pruned once the run is continued or stopped.
- Amends ADR 0015, where an Orphaned Agent Run was a person's to end, and
  narrows the rejection in ADR 0029 without changing declared relocation.
