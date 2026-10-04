---
status: accepted
date: 2026-10-05
---

# Move a conversation switch's sub-agents to the session that runs them

[ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)
keeps the sub-agents a session lists in an ended hook record when the session
ends. Only a `SubagentStop` of that session clears them, or the exit of the
Host Process the record names.
[ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
carries a session's sub-agents through its own `SessionStart` on the same
Host Process. Neither rule covers a sub-agent that goes on under another
session id.

[#448](https://github.com/ned2/dashpot/issues/448) measured Claude Code
2.1.289 switching conversation while a background worker worked
([spike](../spikes/session-start-on-a-live-session-spike.md#claude-code-21289),
trace `issue-448-claude-trace.jsonl`):

- `/clear` publishes `SessionEnd` with `reason` `clear`, then `SessionStart`
  with `source` `clear` for a new session id, from the same Host Process
  (scenario `clear`, #162, #163). Headless `/clear` over stream-json does the
  same (`headless-clear`, #380, #382).
- `/resume <id>` publishes `SessionEnd` `resume`, then `SessionStart`
  `resume` naming the other session (`resume-switch`, #217, #218).
- `/branch` publishes `SessionEnd` `resume`, then `SessionStart` `fork` with
  a new id (`branch`, #261, #262).

In each case the worker goes on under the new id. Its shell and its model
requests carry the new id, and its `SubagentStop` names the new session
(#174, #229, #273, #398). The old session's ended record kept the worker
listed, and nothing ever cleared it. It blocked Cleanup of every Worktree in
the Repository until the process exited. The new session did not list the
worker, so the worker did not hold it `running`.

[#458](https://github.com/ned2/dashpot/issues/458) measured the one switch
#448 left unmeasured that can be driven safely: `/resume` through the
interactive picker
([spike](../spikes/conversation-switch-picker-spike.md), trace
`issue-458-claude-trace.jsonl`). It publishes the same order as
`/resume <id>`: `SessionEnd` `resume`, then `SessionStart` `resume` of the
chosen session from the same Host Process, and the worker follows. That run
used the publisher this decision describes.

Codex differs ([spike](../spikes/session-start-on-a-live-session-spike.md#codex-01600)).
A Codex `/clear` or `/new` publishes a `SessionStart` (`clear`, `startup`)
for another thread and no `SessionEnd`. The old thread's worker stops under
the old thread's id. A managed daemon unloads a thread with `SessionEnd`
`reason` `other`, and that thread's worker stays its own (ADR 0095). One
daemon process serves many threads, so a Codex `SessionStart` `clear` can
come from the same Host Process as an unrelated thread's ended record.

## Decision

A sub-agent listing follows its Host Process's conversation. Two rules
apply, and both are bounded by the Host Process.

- **A Conversation Switch takes over the sub-agents of the session it
  left.** Take a `SessionStart` whose `source` is `clear`, `resume` or
  `fork`, from a Host Process the hook names. It takes over the sub-agents
  listed by every ended record of the same harness and Host Process that
  belongs to another session and that ended with `reason` `clear` or
  `resume`. The new record lists them. Then each of those ended records
  stops listing them, and a record left listing none is removed.
  - **Both sides must show the switch.** The `source` says the process
    switched to this conversation. The ended record's `reason` says it
    switched away from that one. Neither alone is enough. Codex publishes
    `SessionStart` `clear` from a daemon that may also hold an unloaded
    thread's ended record, and that record ended `other`. A Claude Code
    session that ended any other way ended its process with it ([ADR 0095,
    "The other harnesses"](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md#the-other-harnesses)).
    Every `SessionEnd`'s `reason` is now kept in its hook record, copied
    through like `source`, so the ended record can show it.
  - **The new record lists them first.** If the publisher fails between
    the two writes, both records list the sub-agent. That errs toward
    blocking Cleanup, never toward forgetting a working sub-agent
    ([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
  - **Every reachable store is read.** The ended record may be in any store
    of the Repository's Worktrees, or the global store, wherever the
    session it left last published. The publisher reads those records
    without probing a process, as it reads the seed (ADR 0097), and each
    store re-reads its record under that record's lock before changing it.
    An ended record in another Repository's store is out of reach, and keeps
    its sub-agents as ADR 0095 keeps them.
  - **Only the listing moves.** The switch's `SessionStart` still begins a
    new incarnation of its own session. Its state and turn clock follow the
    rule every `SessionStart` other than a compaction follows
    ([ADR 0100](0100-keep-a-compacted-sessions-turn-state.md)), and the
    sub-agents it took over hold it `running` until each one stops
    ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)).
- **A sub-agent's stop releases it from every ended record of its Host
  Process.** ADR 0095's `SubagentStop` reached the session's own kept
  records in every store. It now reaches every ended record of the same
  harness and Host Process that lists the agent, whichever session the
  record belongs to. An agent id names one sub-agent, so its stop is
  evidence wherever it is listed. This covers the orders the takeover cannot
  see:
  - a worker that stops before its new session's `SessionStart` is written;
  - a `SessionStart` that is lost;
  - an ended record written before its publisher kept `reason`, which gives
    no evidence of a switch.

  The rule changes only ended records. A live or unknown session's records
  are left as they are, including a record that a relocated session left
  behind ([#427](https://github.com/ned2/dashpot/issues/427)). ADR 0066's
  union over every record of a live session stands.
- **One place reads `source`.** `session_start_kind` in
  `sessions/hook_records.py` maps a session's `SessionStart` to a
  compaction, a switch, or neither. `continues_turn` (ADR 0100) applies its
  compaction answer to the session's own previous record. `switched_from`
  applies its switch answer to another session's ended record. The two
  rules need separate predicates because they answer different questions
  about different records: whether this session's turn goes on, and which
  other session's sub-agents this one now runs. `release_subagents` on
  `HookRecordStore` is the one compare-and-update that removes sub-agents
  from an ended record. `stored_process_records` in `sessions/hook_scan.py`
  reads a Host Process's records across stores. Both rules use these two
  functions.

## Considered options

- **Let the stop alone clear the old record.** This is the Issue's second
  option, and it is kept as the second rule. It is not enough on its own:
  - the new session would not list the worker, and would not be held
    `running` by it;
  - a Worker Assignment or Issue Binding that moved with the conversation
    would lose its worker
    ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md));
  - until the stop, the ended record would name a session that no longer
    runs the worker.
- **Take over on `source` alone.** Rejected. A Codex daemon's `/clear` on
  one thread would take over the worker of a thread the daemon unloaded.
  That worker's stop names its own thread, so the new thread would read
  `running` until the daemon exited.
- **Take over by harness: Claude Code only.** Rejected. The evidence for
  the switch is on the records: the start's `source` and the end's
  `reason`. A rule named after the harness would not follow when another
  harness publishes the same pair, and would act on a Claude Code record
  that ended for another reason.
- **Extend `continues_turn`.** Rejected for the takeover. That predicate
  asks whether a `SessionStart` goes on with its own session's turn, from
  that session's live record. A switch begins a new session with no turn
  to go on with, and takes over a different session's ended record.
  `session_start_kind` keeps the reading of `source` in one place instead.

## Consequences

- Amends [ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md):
  its "Not changed" item for a Claude Code `/clear`, `/resume` or `/branch`
  is closed. The worker is listed on the session that runs it, from the
  switch until its stop, and no record lists it after the stop.
- Amends [ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md):
  - An ended record keeps its sub-agents until their stop, the exit of
    their Host Process, or a Conversation Switch of that process that takes
    them over.
  - A `SubagentStop` reaches every ended record of its Host Process, not
    only its own session's.
  - A `SessionEnd`'s `reason` is now kept in the record.
- Amends [ADR 0100](0100-keep-a-compacted-sessions-turn-state.md)'s "One
  place decides": `session_start_kind` is now the one reader of `source`,
  and `continues_turn` applies its compaction answer. ADR 0100's decision is
  unchanged.
- A hook record has a `reason` field. A record written before it has none,
  and reads as before. Such an ended record gives no evidence of a switch,
  so it is never taken over. The worker's stop still releases it.
- A `SubagentStop`, and a `SessionStart` whose `source` is a switch, read
  every record in the Repository's stores, not only the session's own. Each
  store holds one record per session, and observation prunes ended records
  whose process is gone.
- Not changed:
  - A switch's `SessionStart` still records `running` with a turn clock,
    as every `SessionStart` other than a compaction does. With a worker,
    the session reads `running` from the switch until its next turn ends.
    In the measured orders that turn is the task notification that follows
    the worker's stop. Without a worker, a `/clear` reads `running` until
    the session's next turn ends, as a fresh `SessionStart` does.
  - `/fork` in Claude Code 2.1.289 is described in its command menu as
    copying the conversation into a new background session and keeping
    the current one working. It was not run, because the background
    session would be hosted by the shared background daemon. A fork in
    another Host Process takes over nothing under this rule. A fork that
    ended the current session in the same process, with a switch `reason`,
    would be taken over like `/branch`.
  - A worker that stops after its new session's `SessionStart` is read but
    before that record is written is still listed there. It holds that
    session `running` until the process exits, or until the session ends
    and a person runs `dashpot work forget-subagents`. The window is the
    length of one hook write.
- Amended by [ADR 0102](0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)
  ([#427](https://github.com/ned2/dashpot/issues/427)): a `SubagentStop`
  also removes its agent from the stopping session's own live records of
  the same Host Process, the records a moved session left behind. Another
  live session's records are still left as they are.
