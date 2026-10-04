---
status: accepted
date: 2026-10-05
---

# Record a session waiting after a SessionStart that begins no turn

A hook record mapped every `SessionStart` to `running` and started the
session's turn clock there.
[ADR 0006](0006-observe-agent-activity-at-turn-boundaries.md) lists
`SessionStart` among the turn boundaries, but no ADR decides that a session
nobody has prompted is working.
[ADR 0100](0100-keep-a-compacted-sessions-turn-state.md) changed the state
for a compaction only. [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)
left a Conversation Switch's state as it was. So a Claude Code session that
was opened and left idle read `running`, with a turn clock ticking from its
start, until its first turn ended. A `/clear` with no worker did the same.
In arc [#464](https://github.com/ned2/dashpot/issues/464) the Lead's own
session recorded `SessionStart` `running` at 13:50:58Z, and its first prompt
came at 13:51:26Z.

[#488](https://github.com/ned2/dashpot/issues/488) measured what follows a
`SessionStart` in Claude Code 2.1.289
([spike](../spikes/idle-session-start-and-fork-spike.md), trace
`issue-488-claude-trace.jsonl`). The same fixture measured `/fork` with a
working background Sub-agent for [#490](https://github.com/ned2/dashpot/issues/490).

- **Opened, resumed, headless.** An interactive session opened with no prompt
  publishes `SessionStart` `startup` (#5), and nothing more in the 20 s it is
  left idle. `claude --resume <id>` publishes `SessionStart` `resume` (#25)
  and nothing more. A stream-json `claude -p` publishes `SessionStart`
  `startup` before it is sent any input (#40), and nothing more until the
  first user message arrives.
- **`/clear` with no worker.** `SessionEnd` `clear`, then `SessionStart`
  `clear` for a new session id in the same Host Process (#70, #71), and
  nothing more while idle.
- **`/fork` while a worker works.** `/fork` publishes no `SessionEnd` for
  the session it copies. It publishes one `SessionStart` with `source`
  `fork` and a new session id, from another Host Process: the background
  session that a transient daemon, started by the forking process, runs
  (#98). The fork publishes nothing more until the daemon stops and it ends
  with `reason` `other` (#133). The worker stays with the session that
  started it. Its shells and model requests carry that session's id, and
  its `SubagentStop` names that session and Host Process (#117).

The other harnesses, from existing traces:

- **Codex 0.160.0** ([#448's trace](../spikes/session-start-on-a-live-session-spike.md#codex-01600),
  `issue-448-codex-trace.jsonl`). Each of the eight `SessionStart`s with
  `source` `startup` or `clear` is published at the start of its thread's
  first turn, and that thread's next event is the turn's `UserPromptSubmit`
  (for example #7–#8, #31–#32, #145–#146, #162–#163). A `/clear` or `/new`
  typed into a terminal publishes nothing until the next prompt is typed
  (#29–#31, #143–#145). A manual compaction behaves the same way (ADR 0100).
  No Codex session that starts and is never prompted was measured.
- **Codex `resume` and `fork`** (the [#160](../spikes/codex-identity-lifecycle-spike.md),
  [#161](../agent-sessions.md#codex-hosting-modes),
  [#269](../spikes/codex-declared-relocation-daemon-spike.md) and #356
  traces, Codex 0.155.1 and 0.160.0). Each of their eleven `SessionStart`s
  with `source` `resume` or `fork` is followed at once by its thread's
  `UserPromptSubmit`: `issue-160-codex-trace.jsonl` #39–#40, #110–#111 and
  #142–#143, `issue-161-codex-trace.jsonl` #56–#57, #217–#218, #291–#292
  and #401–#402, `issue-269-codex-trace.jsonl` #25–#26, #71–#72 and
  #113–#114, and `issue-356-codex-trace.jsonl` #143–#144. Codex was not
  measured again, because these traces show the order this decision needs.
- **OpenCode 2.0.22** ([#448's trace](../spikes/session-start-on-a-live-session-spike.md#opencode-2022),
  `issue-448-opencode-trace.jsonl`). Dashpot writes `SessionStart`, with no
  `source`, for a root's `session.created` and `session.forked`, and before
  the first event of an incarnation it had not seen begin. A fork wrote
  `SessionStart` alone and ran no execution, so its record read `running`
  for the rest of its scenario (#618–#699). OpenCode was not measured
  again.

No measured `SessionStart` other than a compaction's falls inside a turn.
Every turn is begun by a prompt that the harness publishes after the
`SessionStart`: `UserPromptSubmit`, or an execution's start in OpenCode.

## Decision

A session's own `SessionStart` records `waiting`, with no turn clock,
whatever its `source` and harness. A compaction's is the one exception, and
ADR 0100 still decides it.

| `source` | Harness | Recorded state |
| --- | --- | --- |
| `startup` | Claude Code, Codex | `waiting` |
| `resume` | Claude Code, Codex | `waiting` |
| `clear` | Claude Code, Codex | `waiting` |
| `fork` | Claude Code, Codex | `waiting` |
| none | OpenCode (created, forked, or a first publication) | `waiting` |
| `compact` | Claude Code, Codex | ADR 0100: the turn state of the live record it follows, or `running` with none to follow |
| any other | any | `waiting` |

- **Sub-agents still hold it running.** A `SessionStart` can list
  sub-agents: those it carries from a live record of its Host Process
  ([ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)),
  those of an ended record of that process
  ([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)),
  or those it takes over in a Conversation Switch (ADR 0101). Each one holds
  the session `running` until its `SubagentStop`
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)).
  The session's own turn has not begun, so it has no turn clock, and the
  last sub-agent's stop leaves it `waiting`.
- **The prompt starts the turn.** The session's next `UserPromptSubmit`
  records `running` and starts the turn clock at the prompt, not at the
  `SessionStart`.
- **One place decides.** `EVENT_STATES` in `sessions/hook_records.py` maps
  `SessionStart` to `waiting`. `carried_state` applies ADR 0100's exception
  for a compaction, which `session_start_kind` still recognises as the one
  reader of `source`. The Event Log's `hook.outcome` reports the state the
  record was stored with ([#489](https://github.com/ned2/dashpot/issues/489)),
  so it reports `waiting` with no change to the publisher.

## Considered options

- **Keep `running` until the session's first turn ends.** Rejected. A
  session nobody has prompted is not working, and the turn clock measured
  nothing. A session whose first turn never comes read `running` for its
  whole life. A Claude Code `/fork` copy publishes no turn at all, and
  neither does an OpenCode fork that is never prompted.
- **Decide per `source`: `waiting` for `startup` and `clear` only.**
  Rejected. `resume` and `fork` were measured idle too, and no source other
  than `compact` was measured beginning a turn. A table of sources would add
  readers of `source`, which ADR 0101 keeps to one.
- **Decide per harness, keeping `running` for Codex.** Rejected. A Codex
  `SessionStart` reads `waiting` for the moment before its `UserPromptSubmit`,
  0.2 to 0.4 s in the trace. Its turn clock then starts at the prompt, as ADR
  0100 already accepted for a Codex manual compaction. A rule named after a
  harness would not follow a harness that changes its order.
- **Read a compaction with no live record to follow as `waiting` too.**
  Rejected, as ADR 0100 rejected it: an automatic compaction runs inside a
  turn, and nothing says which turn state such a compaction keeps.

## Consequences

- A Claude Code session opened, resumed or `/clear`ed and left idle reads
  `waiting`, and the dashboard shows how long it has been idle since its
  start. A worker it lists still holds it `running`.
- A Conversation Switch's `SessionStart` reads `waiting` with no turn clock.
  With a worker it took over, the session reads `running` until the
  worker's stop, then `waiting`, not until its next turn ends.
- A Claude Code `/fork` copy, and an OpenCode root that is created or forked
  and never prompted, read `waiting` rather than `running` for as long as
  they live. A Host Process's last cleanup marks only running roots, or
  roots holding Sub-agents, as unknown (ADR 0090), so it no longer marks
  such a root: it has no execution whose end could be lost.
- A Codex turn's clock starts at its `UserPromptSubmit`, a moment after the
  `SessionStart` before it.
- `integrate` subscribes the same hooks as before. An installation picks up
  the rule when its publisher is updated.
- Amends [ADR 0100](0100-keep-a-compacted-sessions-turn-state.md): "every
  other `SessionStart` records `running`, as before" no longer holds; every
  other `SessionStart` records `waiting`. The rules for a compaction are
  unchanged.
- Amends [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md):
  - Its "Not changed" item that a switch's `SessionStart` records `running`
    with a turn clock is closed. With a worker, the session reads `running`
    until the worker stops, and without one it reads `waiting`.
  - Its `/fork` item, which was written from the command menu's
    description, is replaced by the measurement above. `/fork` ends no
    session and starts its copy in another Host Process, so the takeover
    never applies to it. That is right, because the worker stays with the
    session that started it and stops there. ADR 0101's rules are
    unchanged.
- Not changed:
  - [ADR 0102](0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)
    and ADR 0095's release of a stopped sub-agent through
    `release_subagents` and `release_left_behind`.
  - A child-scoped event still keeps its parent's state (ADR 0016).
  - ADR 0067's `lastSessionStartAt`.
