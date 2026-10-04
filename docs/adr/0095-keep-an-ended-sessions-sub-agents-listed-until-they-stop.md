---
status: accepted
date: 2026-10-04
---

# Keep an ended session's sub-agents listed until they stop

[ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)
blocks removal of every Worktree of a Repository while an Agent Session there
lists a live sub-agent, and
[ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md) let a
session's `SessionEnd` clear its live set with its record. That treated the
end of a session as the end of everything it delegated, and on the managed
Codex daemon it is not.

[#420](https://github.com/ned2/dashpot/issues/420) measured `codex-cli`
0.160.0 with Dashpot's real publisher
([spike](../spikes/codex-worker-mechanics-spike.md),
[trace](../spikes/measurements/issue-420-codex-trace.jsonl), scenario
`lead-unload`). A lead bound to an Issue spawned a v2 worker running four
25-second commands, and its last client left. The daemon unloaded the lead
60.3 s later, with `SessionEnd`, while the worker kept working. The settler of
[ADR 0086](0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)
found the daemon live and ended the lead's run 10.3 s after the `SessionEnd`.
The record's removal took the session's live sub-agents with it. The worker's
fourth command started 14.3 s after the `SessionEnd`, and its `SubagentStop`
arrived 29.3 s after the run ended. Under ADR 0067's rule that a stop finding
no parent record writes nothing, the publisher recorded it as changing
nothing. For about 29 s no run and no blocker covered a working sub-agent,
and a Cleanup could have removed the Worktree it worked in
([#431](https://github.com/ned2/dashpot/issues/431)).

Two more measurements bound what a `SessionEnd` can tell:

- A Codex v2 worker publishes no hook between its `SubagentStart` and its
  `SubagentStop`, so nothing after its lead's end shows whether it still
  works.
- In the same trace's `lead-delete` scenario, `thread/delete` of a lead ended
  the lead and its worker together. Its running command never finished, and
  no `SubagentStop` fired. A child interrupted through its own thread
  publishes none either
  ([#374](https://github.com/ned2/dashpot/issues/374),
  [openai/codex#38142](https://github.com/openai/codex/issues/38142)).

So at `SessionEnd` a sub-agent that is still working and one that will
never report look the same. Before this decision `SessionEnd` was the way
out for the second kind: a person ended the session's client, and the
daemon unloaded the thread about 60 s later.

## Decision

A session's end does not end the listing of the sub-agents it delegated to.

- **The end keeps them in an ended record.** A `SessionEnd` whose session
  lists live sub-agents still ends the session, and its runs end or defer
  exactly as before: ADR 0015, ADR 0075 and ADR 0086 are unchanged. Instead
  of removing the hook record, the store keeps an ended record listing those
  sub-agents. They are the ones the session's records of the ending Host
  Process list: the store's own previous record, plus the record the
  publisher seeds from in another store. An end that names no Host Process
  keeps nothing, because nothing but a `SubagentStop` could ever clear what
  it kept.
- **Only the sub-agent boundaries change it.** A `SubagentStop` from the same
  Host Process removes the agent, and the record goes once none is left. A
  `SubagentStart` adds one. Any other event of a sub-agent changes nothing:
  it neither revives the ended session nor lists it as waiting, which keeps
  the case ADR 0067 guards against. A sub-agent's event is routed to the
  session's freshest record, a kept one included, and a `SubagentStop` also
  reaches every kept record of the session in the Repository's other
  stores, so a session that started again at another Worktree still clears
  the record it left.
- **The Host Process bounds it.** The record holds its sub-agents while
  their Host Process is live or its liveness is unknown. Once that process
  is gone it holds nothing, and observation prunes it like any ended
  record. Before that, observation keeps it and never shows the ended
  session.
- **Cleanup and `work show` read it as an ended session's sub-agents.**
  `sessions_with_live_subagents` counts a kept record as well as live and
  unknown sessions. The `sub-agent` blocker says the session *ended with* its
  sub-agents listed as working. It says one that ended with its session, or
  was interrupted, may never report, and it carries the command that forgets
  them. A session's older records elsewhere that its `SessionEnd` removes
  never include a kept record.
- **A start on the same Host Process carries them.** A `SessionStart` of the
  session on the Host Process its ended record names, at the same
  Worktree, starts the new incarnation with those sub-agents still listed:
  a lead the daemon unloaded and a client resumed may still have its worker
  running. One at another Worktree leaves the kept record where it is, and
  each `SubagentStop` still clears it. An event from another Host Process,
  such as a restart's replacement daemon, treats the kept record as absent,
  as the session's record was before this decision, and its write replaces
  it.
- **`dashpot work forget-subagents <session-id>` forgets them.** It is a
  management command under
  [ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md).
  It removes the session's ended records that list sub-agents from every
  hook store of the Repository it runs in, and the global store, through
  the store's compare-and-delete. A record a hook changed since it was read
  is kept, and the command reports that it changed. It touches no live
  session's record, no Agent Run and no Work Store record. `--harness`
  chooses between two harnesses' ended sessions that share the id. A person
  runs it once they have checked that none of the listed sub-agents still
  works. Its outcome is recorded in the Event Log as
  `work forget-subagents`, with the action `forgotten`.

### The other harnesses

The rule is the store's, not Codex's, so it applies to every harness. What
each one does at its own session's end decides whether it ever keeps
anything for long:

- **Claude Code.** [#419](https://github.com/ned2/dashpot/issues/419)
  measured each way a session ends while a worker runs
  ([spike](../spikes/claude-code-worker-mechanics-spike.md)). `/exit` with
  "Exit and stop tasks", a closed terminal, and `claude stop` or
  `claude rm` on a `--bg` lead each stop the worker without a
  `SubagentStop`, publish `SessionEnd`, and end the Claude Code process.
  `/exit` left unanswered publishes the worker's `SubagentStop` first.
  Either way a kept record either lists nothing or loses its Host Process at
  once. A `SessionEnd` whose process lives on, such as `/clear`, was not
  measured with a worker running. There a kept record blocks until the
  process exits or a person forgets it, which errs toward blocking.
- **OpenCode.** [#421](https://github.com/ned2/dashpot/issues/421) measured
  a lead deleted while its worker ran
  ([trace](../spikes/measurements/issue-421-opencode-trace.jsonl), scenario
  `delete`). The server published the worker's
  `session.execution.interrupted` and `session.deleted`, both
  `SubagentStop`, before the lead's `session.deleted`. The listing is empty
  when the lead's `SessionEnd` arrives, and nothing is kept.
- **Codex.** A standalone terminal's or `exec`'s Host Process exits right
  after its `SessionEnd` (ADR 0086). Only a daemon-hosted thread keeps a
  record for long, and that is the case this decision is for.

## Considered options

- **Let the settler keep the run while sub-agents are listed.** Rejected.
  It needs a new path for a parent-less `SubagentStop` to end a run. A lead
  whose worker was deleted with it would hold a run bound to a live daemon,
  with no session left in which `work stop` could run.
- **Leave the run orphaned while sub-agents are listed.** Rejected. Every
  unload during a wave of workers would need a person's `work stop
  --session`, and a later `SubagentStop` would have nothing to clear.
- **Keep clearing at `SessionEnd`, and tell the lead to keep a client
  attached for the whole wave.** Rejected by the maintainer. The #420 spike
  already gives that advice; the gap stays wherever it is not followed, and
  Cleanup's safety should not depend on it.
- **Keep the sub-agents with no way to forget them.** Rejected by the
  maintainer. A deleted lead's worker and an interrupted child would block
  every Worktree of the Repository until the daemon stopped. `codex
  app-server daemon stop` or `restart` would be the only way out, and it
  leaves every other run on the daemon orphaned.
- **Time a kept sub-agent out.** Rejected, as ADR 0016's #374 clarification
  rejected it for a live session: no clock tells a long command from a
  stranded child.

## Consequences

- Amends [ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md):
  a `SessionEnd` no longer clears a live set. The bounded risk of an
  undelivered `SubagentStop` is now bounded by the Host Process, or by a
  person's `work forget-subagents`, rather than by the session's end.
- Amends [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md):
  the evidence of a sub-agent outlives its session's `SessionEnd`, and an
  ended session's sub-agents block removal as a live session's do.
- Amends [ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md):
  `work forget-subagents` is a management command. It removes only the hook
  records the person names, and only ended ones.
- ADR 0067's rule stands: a `SubagentStop` that finds no record of its
  session writes nothing. A stop that finds a kept record updates that
  record.
- ADR 0086 is unchanged. The unloaded lead's run still ends when the settler
  finds the daemon live. The Issue work is over when the lead's conversation
  is, and the worker's protection is the `sub-agent` blocker, not a run.
- The way out for a silently interrupted Codex child now takes two steps.
  The person ends the session's client, as before, and once the daemon has
  unloaded the thread, runs the command the `sub-agent` blocker names.
- A kept record shows in `dashpot integrate <harness> --status` as stale,
  naming the sub-agents that keep it and the process it waits for.
- A session's event from another Host Process drops the listing of the
  kept record it replaces without probing whether the first process lives
  on. A store holds one record per session, and the only measured case of
  a session's id on a second Host Process is a restart's replacement
  daemon, whose predecessor is gone (ADR 0086). A standalone client resuming
  a daemon-hosted thread while the daemon still runs that thread's worker
  was not measured. Carrying the listing across Host Processes would need
  the publisher to probe the first one and keep each sub-agent's own
  process in the record, and is left until that case is measured.
- A session that ended while it listed a sub-agent dispatched from a
  Worktree it moved on from keeps only what its records of the ending Host
  Process list. ADR 0066's union over every record of the session still
  holds while that session lives.
- Amended by [ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
  ([#448](https://github.com/ned2/dashpot/issues/448)): a `SessionStart` of
  the same Host Process carries a live record's sub-agents too, so this
  decision's carry of an ended record is one case of that rule. #448 also
  measured a Claude Code `/clear`, `/resume` and `/branch` with a worker
  running: each ends the session and moves the worker to another session
  id in the same process, so the ended record keeps it listed until the
  process exits, as this decision expected.
