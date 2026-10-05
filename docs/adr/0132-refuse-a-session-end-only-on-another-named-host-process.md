---
status: accepted
date: 2026-10-05
---

# Refuse a session's end only on another named Host Process

A hook store writes a session's `SessionEnd` over the session's previous
record in that store. It refused the end, and kept the previous record as it
was, unless both records named the same Host Process or neither named one. A
record names no Host Process when the hook's ancestry probe could not observe
an ancestor: `ps` timed out or failed, or `kill` could not probe a pid. The
record then carries only `sessionProcessUnobservable` with the reason.

[#543](https://github.com/ned2/dashpot/issues/543) reproduced the refusal
through the store in both directions:

- **The previous record names none.** A `Stop` whose probe timed out, then a
  `SessionEnd` naming the session's real process. The end was refused. A
  record with no process reads `unknown` for good and is never pruned, so
  the session stayed listed, and Cleanup blocked on it until the session
  "publishes its end", although it had.
- **The end names none.** A `Stop` naming a Codex daemon, then a `SessionEnd`
  whose probe failed. The end was refused, and the session read waiting
  until the daemon exited.

The rule exists so that one process cannot end a session another process
runs. Claude Code `2.1.285`'s refused `claude -p --resume <id>` publishes a
`SessionEnd` for the running session from its own process
([spike](../spikes/claude-code-2-1-285-changes-spike.md)). A record that
names no process is no evidence of another process, so the rule had nothing
to protect in either case above.

## Decision

A `SessionEnd` is refused only on contrary evidence.

- **Another named process refuses.** When the end and the previous record
  each name a Host Process and they differ, the end is refused, as before.
  Two unreadable process records still match only when they are identical.
- **A newer record refuses.** A previous record newer than the end by
  `lastActivityAt` is kept, as before.
- **A side that names none is no evidence.** When only one of the two names
  a Host Process, the end is accepted. Two records that name none still
  match, as before.
- **The accepted end is the named process's.** An end that names no process
  beside a previous record that names one takes that record's
  `sessionProcess` and `sessionProcessUnobservable`. An ended record it keeps
  for its sub-agents
  ([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md))
  then waits on that process and is pruned once it is gone.
- **The previous record's sub-agents are the ending process's.** An end
  that names a Host Process keeps the sub-agents the store's previous record
  lists when that record names the same process or none: the end was
  accepted beside it as the session's end, so nothing says another process
  runs them. A listed sub-agent with no process of its own is the session's,
  as the store already treats it when carrying a live record's sub-agents
  ([ADR 0107](0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)).
  The record the publisher seeds from in another store still counts only
  when it names the ending process, as for every other event.

The rule is the store's, so it applies to every harness.

## Considered options

- **Keep the refusal.** Rejected. The way out, resuming the session and ending
  it again, is documented, but nothing tells a person that it is needed. The
  refusal reaches the Event Log only as a publication with no state.
- **Carry the previous record's process forward into every session-scoped
  event whose probe failed.** Rejected as broader than the fault. It would
  attribute a turn's events, not only its end, to a process nothing observed
  publishing them.
- **Accept the end but keep no sub-agents when it names no process.**
  Rejected. A Codex daemon's worker can outlive its lead's `SessionEnd`
  (ADR 0095), and dropping it would let a Cleanup remove the Worktree it works
  in. The refusal erred toward blocking; the fix keeps that direction.

## Consequences

- Amends [ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md):
  an end that names no Host Process keeps the sub-agents of the process its
  session's previous record names, and keeps nothing only when that record
  names none either. An end that names one keeps, beside its own process's
  sub-agents, those the store's previous record lists when that record names
  none.
- A `SessionEnd` that another process publishes for a session whose last
  record lost its process evidence now ends that session. That needs a
  transient probe failure on the session's last event before a foreign
  `SessionEnd`, and is the trade the triage of #543 accepted.
- The mirror case is the same trade. A foreign `SessionEnd` whose own probe
  failed, such as a refused `claude -p --resume` whose ancestry could not be
  observed, is now accepted beside a live record naming the session's Host
  Process, and is recorded as that process's end. Its hook record lists the
  session no longer, until that process's next event writes a new one. It
  too needs a transient probe failure, on the foreign end.
- [ADR 0069](0069-remove-an-ended-sessions-records-from-every-store-of-its-repository.md)
  is unchanged. A `SessionEnd` still removes the session's records in other
  stores only when both its own and the record's Host Process are observed.
- The Work Store's reconciliation at `SessionEnd`
  ([ADR 0015](0015-reconcile-the-agent-run-at-session-end.md),
  [ADR 0086](0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md))
  is unchanged: the publisher runs it before the store's write, whatever the
  write keeps.
- This is not the cause of [#518](https://github.com/ned2/dashpot/issues/518).
  In #466's pinned Claude Code `2.1.289` trace, a `claude -p` session that
  exits invokes no `SessionEnd` hook at all, so the store never sees an end
  to refuse.
