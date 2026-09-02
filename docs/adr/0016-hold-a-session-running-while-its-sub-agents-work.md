---
status: accepted
---

# Hold a session running while its sub-agents work

Dashpot observes an Agent Session's activity at turn boundaries
([ADR 0006](0006-observe-agent-activity-at-turn-boundaries.md)): the session
is running from `UserPromptSubmit` to `Stop` and waiting after. A Claude Code
session can end its own turn while a background sub-agent it spawned keeps
working — the normal shape of delegated work. Measured in a live session
([#90](https://github.com/ned2/dashpot/issues/90)): the main turn's `Stop`
recorded the session as waiting with the sub-agent still running, no
subscribed event fired during the sub-agent's two and a half minutes of work,
and the run flipped back to running only when the sub-agent's completion
re-invoked the main session as a `UserPromptSubmit`. Sub-agents share the
session's Agent Run, so a bound run showed **waiting** for the whole
delegated interval — a quiet break of the invariant that any agent working
on an Issue shows that Issue's run as running.

Dashpot will treat a sub-agent's boundaries as boundaries of the session, and
hold the session running while any sub-agent it started is alive:

- The Claude Code integration subscribes to `SubagentStart` and
  `SubagentStop` beside the turn events. They fire once per sub-agent, not
  per tool call, so the per-invocation cost that ADR 0006 measured and
  rejected for `PostToolUse` does not arise. Codex has no counterpart and is
  unchanged.
- The hook record carries the session's live sub-agents (`liveSubagents`,
  the `agent_id` of each observed started and not yet stopped). The store
  derives it against the previous record, as it does the turn clock:
  `SubagentStart` adds the agent, `SubagentStop` removes it, `SessionStart`
  begins a session with none, and every other event carries the set.
- The recorded state is reconciled against that set. A `Stop` that arrives
  while a sub-agent is alive records the session as running; the
  `SubagentStop` that empties the set after the main turn has stopped records
  it as waiting; a `SubagentStop` while the main turn is still in flight
  leaves it running.
- The turn clock stays the main turn's. A sub-agent's event carries
  `turnStartedAt` unchanged, and a main turn's `Stop` clears it even while
  sub-agents hold the session running, so the Sessions pane ages a delegated
  interval from the last observed event rather than from a turn that has
  ended.
- The field degrades like every non-fatal record field: a malformed
  `liveSubagents` reads as none, with a diagnostic, and the record stays
  version 2. A sub-agent event that names no agent changes nothing rather
  than guessing.

## Considered options

- **Subscribe to the sub-agent events without recording the live set:**
  rejected because `SubagentStart` fires before the main turn's `Stop`, which
  would then overwrite running with waiting, reproducing the gap exactly.
- **Observe the sub-agent's tool calls through `PostToolUse`:** rejected on
  the cost ADR 0006 measured; a per-tool-call hook is the option that ADR
  already declined.
- **Record the main turn's state as a separate field:** rejected as a second
  state beside the one observation reads. The main turn's clock already
  says whether the main turn is in flight, and the live set says whether
  delegated work is.

## Consequences

- The Sessions pane reports a session with a live background sub-agent as
  running, and a bound Issue's run with it, until both the main turn has
  stopped and the last sub-agent has.
- ADR 0006's event table gains the two sub-agent events for Claude Code; the
  turn-boundary decision itself is unchanged.
- A `SubagentStop` the harness never delivers leaves a sub-agent in the live
  set until the next `SessionStart` or `SessionEnd`, holding the session
  running. This is the same class of risk as an undelivered `Stop`, and is
  bounded the same way, by the session's own lifecycle.
- Existing installations report the two events as missing from
  `dashpot integrate claude-code --status` until re-run.
