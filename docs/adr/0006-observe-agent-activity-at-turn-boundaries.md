---
status: accepted
---

# Observe Agent Session activity at turn boundaries

The Sessions pane reports how long a run has been doing what it is doing:
`running 14m` for a turn in flight, `idle 14m` for a session quiet since its
last observed event, `started 3d ago` for a run nothing has observed. That age
is only as fine as the events Dashpot subscribes to. Both harness
integrations install `SessionStart`, `UserPromptSubmit`, `Stop` and
`SessionEnd` (Codex adds `Interrupt`), so the clock ticks when a turn begins
and when it ends, and not once in between.

`EVENT_STATES` also maps `PreToolUse` and `PostToolUse` to `running`, and
installing `PostToolUse` is the obvious way to see inside a turn: it would
distinguish an agent working from one wedged, and would let Dashpot warn about
a session that has gone quiet while still running. It was prototyped against
the real hook command and rejected on the measurements.

One invocation costs a median 89 ms: ~11 ms to start the interpreter, ~26 ms
more to import `dashpot.agents`, ~42 ms more for `nearest_harness_process` to
walk the process tree, and ~2 ms for the two Git probes. Measured against 108
local Claude Code transcripts — 1276 turns, 13369 tool calls, mean 10.5 per
turn — that is 0.9 s of hook time on an average turn, 2.6 s at p90 and 11.6 s
at p99. The cost is process startup rather than I/O, so a debounce inside
`HookRecordStore.write` cannot recover it: the interpreter, the import and the
process walk are all spent before the write is reached.

Dashpot therefore observes activity at turn boundaries, and the pane says
which age it is showing rather than implying a precision it does not have.

## Considered options

- **Install `PostToolUse` as it stands:** rejected on cost, and because it
  buys nothing visible on its own. A running row's age comes from
  `turn_started_at`, which a per-tool-call stamp does not move, so the cell is
  identical with and without the hook until something reads last activity
  instead of turn age.
- **Debounce the record write:** rejected because it saves only the write,
  which is the cheapest part of an invocation.
- **One timestamp for both questions:** rejected because a turn's age and a
  session's idle time are different facts that read alike as a bare age. The
  record keeps `turnStartedAt` beside `lastActivityAt`, and the store carries
  the turn's clock across a turn's events.
- **Borrowing the Work Store's `startedAt` as an activity:** rejected because
  nothing observed the run doing anything. The run carries that timestamp as
  its own fact and the pane labels it `started 3d ago`.

## Consequences

- A long turn and a hung session are the same observation. Warning about a
  quiet running session is undeliverable until intra-turn observation is
  affordable, and is not attempted.
- `ACTIVITY` names which age it shows, so the reader is never left to infer
  the meaning from `STATE`.
- Making this reversible is a costing exercise, not a design one: the two
  large components are the process-tree walk, which a hook that already knows
  its session could avoid by reusing the recorded process identity, and the
  import, which a minimal heartbeat entry point would avoid.
- Hook records are stamped at fixed width and ordered by instant, so the
  freshest record for a session wins regardless of a stamp's precision.
