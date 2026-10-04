---
status: accepted
date: 2026-10-05
---

# Keep a compacted session's turn state

A hook record maps every `SessionStart` to `running`.
[ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
kept that: a compaction's `SessionStart` carries the session's sub-agents but
"sets the record's state as before". It recorded the consequence under "Not
changed": a waiting session reads `running` from a Claude Code `/compact`
until its next turn ends.

[#448](https://github.com/ned2/dashpot/issues/448) measured the orders
([spike](../spikes/session-start-on-a-live-session-spike.md), trace
`issue-448-claude-trace.jsonl`):

- **Manual `/compact`, Claude Code 2.1.289.** `PreCompact`, the summarizer's
  `SubagentStop` with no `SubagentStart`, `SessionStart` `compact` on the same
  session and Host Process, then `PostCompact`, with no `UserPromptSubmit`
  and no `Stop` (scenario `compact`, #16–#21). Headless `/compact` over
  stream-json publishes the same order (`headless-compact`, #312–#318).
- **Automatic compaction, Claude Code 2.1.289.** The same events mid-turn,
  then that turn's `Stop` with no new prompt (`auto-compact`, #112–#119).
- **Codex 0.160.0.** A manual compaction publishes its `SessionStart`
  `compact` at the start of the next turn, just before that turn's
  `UserPromptSubmit`; an automatic one publishes it inside the turn, before
  the turn's `Stop`.

[#461](https://github.com/ned2/dashpot/issues/461) asks what state a
compaction records.

## Decision

A `SessionStart` whose `source` is `compact`, from the Host Process that the
live record it follows names, keeps the main turn's state: `running` if that
record's turn clock (`turnStartedAt`) runs, `waiting` if it does not. Every
other `SessionStart` records `running`, as before. That includes a
compaction from another Host Process or one Dashpot cannot name, and a
compaction that follows an ended record or none, unless a fresher live record
of the same Host Process in another store is the one it carries from.

- **The turn clock, not the recorded state.** A record's `state` already
  counts its sub-agents: a waiting session whose worker still works is
  stored `running` with no turn clock. Carrying that `running` would start a
  turn clock, and the worker's `SubagentStop` would then read the main turn as
  in flight and keep the session running after the worker stopped. The
  sub-agents carried under ADR 0097 still hold a waiting session running until
  each stops
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)).
- **The record ADR 0097 carries from.** The kept state is that of the
  record whose sub-agents the compaction carries. That is the session's
  freshest record of the same Host Process, which may be in another store
  when a Claude Code shell `cd` left this store's record behind.
- **Only the state changes.** A compaction still sets `lastSessionStartAt`,
  which [ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
  reads to tell a Live Relocation from a restart, and carries the sub-agents
  as ADR 0097 decides. A kept turn keeps its clock; a waiting compaction has
  none.
- **One place decides.** `continues_turn` in `sessions/hook_records.py` is
  the only rule that decides on a `SessionStart`'s `source`, and
  `carried_state` is the only place that applies it.

Auto-compaction reads `running` until its turn's `Stop`, and then reads
`waiting` unless a sub-agent still works. A manual Claude Code `/compact`
leaves a waiting session `waiting`. A Codex manual compaction reads
`waiting` until the `UserPromptSubmit` that follows it, a moment later, and
that turn's clock now starts at the prompt rather than at the
`SessionStart`.

## Considered options

- **Let `PostCompact` restore the state.** Rejected. No Dashpot integration
  subscribes `PostCompact` or `PreCompact`: the #448 fixture subscribed them
  to observe them only. Subscribing one would add an event to Claude Code's
  `integrate` hook set, so `dashpot integrate claude-code --status` would
  report every existing installation as missing hook events until
  `integrate` ran again. The session would also read `running` between the
  `SessionStart` and the `PostCompact`, and stay `running` if the
  `PostCompact` were lost. The `SessionStart` already says everything the
  `PostCompact` would.
- **Keep the state across any `SessionStart` of the same Host Process.**
  Rejected. ADR 0097 bounded the sub-agent carry by the Host Process, not by
  `source`, because whether sub-agents survive depends on the process.
  Whether a turn goes on depends on why the harness published the
  `SessionStart`, and only `source` says that. OpenCode publishes no
  `SessionStart` when it compacts, so its translated `SessionStart`, which
  has no `source`, loses nothing. No other source was measured reaching a
  live record of the same session and Host Process, so every other source
  keeps the existing rule until one is.
- **Record every compaction `waiting`.** Rejected. Automatic compaction
  runs inside a turn, which must read `running`, with its clock, until its
  `Stop`.
- **Keep the previous record's stored state.** Rejected for the reason under
  "The turn clock, not the recorded state" above.

## Consequences

- Amends ADR 0097: a compaction's `SessionStart` no longer sets the record's
  state "as before". The "Not changed" item that a waiting session reads
  `running` from a Claude Code `/compact` until its next turn ends is
  closed.
- `integrate` subscribes the same hooks as before, so `integrate --status`
  reports nothing new for an existing installation. An installation picks up
  the rule when its publisher is updated.
- The Event Log's `hook.outcome` still reports the state the hook event maps
  to (`running` for every `SessionStart`), as it already does for a `Stop`
  whose sub-agents keep the record `running`. The hook record and the
  dashboard read the kept state.
- A compaction with no live record of its Host Process to follow, such as
  the first event after hooks were installed partway through a session,
  still reads `running` until the session's next `Stop`: nothing says
  which turn state it would keep.
- A later rule for other `SessionStart` sources extends `continues_turn`,
  which reads `source` in one place.
- Amended by [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)
  ([#458](https://github.com/ned2/dashpot/issues/458)): `session_start_kind` is now the one reader of a `SessionStart`'s
  `source`, and `continues_turn` applies its compaction answer; this
  decision is unchanged.
