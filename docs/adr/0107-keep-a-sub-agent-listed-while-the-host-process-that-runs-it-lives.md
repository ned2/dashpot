---
status: accepted
date: 2026-10-05
---

# Keep a Sub-agent listed while the Host Process that runs it lives

[ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
has a `SessionStart` carry the session's live sub-agents only from a record
of the same Host Process. One from another process starts with none, on the
reasoning that the old process's sub-agents "ended with it or are still that
process's".
[ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)
likewise drops an ended record's listing when an event of the session
arrives from another process. It noted that carrying a listing across Host
Processes "would need the publisher to probe the first one and keep each
sub-agent's own process in the record", and left that until the case was
measured.

[#448](https://github.com/ned2/dashpot/issues/448) measured it on OpenCode
2.0.22, in the `standalone` order of its trace
([`issue-448-opencode-trace.jsonl`](../spikes/measurements/issue-448-opencode-trace.jsonl)
receipts 1083 to 1168):

1. The shared service (pid 24606) ran a root's execution. The root started a
   child, and the root's execution ended while the child held a command
   (#1083, #1084).
2. A `--standalone` client's private server (pid 85917) resumed the root.
   Dashpot wrote the root's `SessionStart` from that process, and by ADR 0097
   stored it with no sub-agents (#1108).
3. The client's last plugin instance went, and Dashpot marked the record
   unobserved (#1125). The client exited, and the record's process read gone.
   Cleanup then found no obstacle (#1128) while the child still held its
   command, which ended at #1129.
4. The child's end reached the service, whose next publication began the
   root's incarnation there (#1164). Cleanup found nothing then either
   (#1168).

The child never stopped being the service's: OpenCode runs a session's
shells in the server that runs the session, and the child's command was the
service's child process throughout (#1086, #1129).

[#460](https://github.com/ned2/dashpot/issues/460) measured whether Codex
0.160.0 has the same gap
([spike](../spikes/second-host-process-resume-spike.md),
[trace](../spikes/measurements/issue-460-codex-trace.jsonl)). A managed
daemon hosted a lead whose worker was running long commands, and a second
terminal resumed the lead while the worker worked:

- **A plain `codex resume` attaches to the daemon.** The terminal's prompt
  and `Stop` were published by the daemon's process (#24, #27), and no
  `SessionStart` came. On exit the terminal reported "Disconnected from this
  task. Any running work continues." (#54). There is one Host Process, and
  the `sub-agent` blocker held until the worker's `SubagentStop` (#31, #49,
  #52).
- **`codex --no-daemon resume` of a thread the daemon holds publishes
  nothing.** The terminal's own process sat waiting for the minute it was
  given, then for 30 s past the worker's `SubagentStop` (#94), and exited
  without a hook of its own (#99). The blocker held until that stop (#88,
  #97).
- **Control:** once the daemon had stopped, the same `--no-daemon resume`
  published `SessionStart` `resume` and its turn from its own process (#206,
  #207, #210).

So Codex 0.160.0 has no second Host Process on a daemon thread whose worker
runs. The receipts above are the base publisher's; the same scenarios with
this change's publisher, built at `fb2e727`, read the same (#118, #121, #143,
#148 attached; #188, #193 with `--no-daemon`). The publisher changed after
that run, in behaviour only where no Codex scenario reaches: a process the
publisher did not probe now carries its sub-agents (below), where every
scenario's sub-agents run in the daemon, the event's own process. The rest
removed an unused helper and moved code without changing it.

## Decision

A Sub-agent belongs to the Host Process that runs it, and stays listed while
that process lives, whichever process the session's own events come from.

- **The process each sub-agent runs in.** A hook record names one Host
  Process, `sessionProcess`. A listed sub-agent that another process runs is
  tagged with that process in a new field, `subagentProcesses`, which maps
  the agent's id to the `sessionProcess` of its own Host Process. An agent
  with no tag is the record's own. A starting sub-agent's process is the one
  its `SubagentStart` came from. A record whose sub-agents are all its own
  carries no tags, so it keeps the shape it had.
- **Carried by its process.** Whenever the store carries a listing into a
  record (from the record it replaces, from a fresher record that seeds it,
  or from an ended record), each sub-agent is handled by its own Host
  Process:
  - one the event's process runs carries as the record's own;
  - one another named process runs carries, tagged, unless the publisher
    found that process gone;
  - one whose process no record names carries, except at a `SessionStart`
    (ADR 0097's rule for a process that cannot be named).

  So a `SessionStart` from another process keeps the sub-agents of a process
  still running, and drops those of one that is gone, such as the process a
  `claude --resume` replaced. ADR 0097's carry within one process is
  unchanged.
- **The publisher probes, not the store.** Before the store takes its locks,
  the publisher reads the session's records, collects the Host Processes
  they name for their sub-agents other than the event's own, and probes each
  one. The store receives those it found gone (`gone_hosts`), and drops only
  their sub-agents. A session whose sub-agents all run in the event's
  process probes nothing.
- **A race errs toward blocking.** Another process's `SubagentStart` can tag
  a sub-agent after the publisher read the records and before its write.
  That sub-agent's process went unprobed, so the write carries it, rather
  than treating every process it did not find living as gone, which would
  drop a working sub-agent and its blocker until nothing re-adds it. The
  next write reads the tag and probes the process.
- **A sub-agent's event speaks for itself.** A child-scoped event from a
  process other than the one the parent's record names keeps the record's
  Host Process. Its own boundary changes only its own entry; the carry
  above still applies to the record's other sub-agents.
- **Its stop clears it where its process listed it.** A `SubagentStop`
  reaches the record it is routed to as before, including an ended record of
  another process that lists the agent under the stop's process. It also
  reaches every other record of the session that lists the agent under that
  process. `release_subagents` and `release_left_behind` remove only the
  agents a record lists as run by the stopping process. For a record with no
  tags that is the record's own process, exactly as before.
- **Read by the process that runs it.** A scan probes each tagged process
  with the record's own. A tagged sub-agent whose process is gone is not
  listed. A live record that runs no main turn, held `running` only by such
  sub-agents, reads `waiting`. A record whose own process is gone but which
  still lists a sub-agent of another, live process
  (`retains_other_host_subagents`) holds the `sub-agent` Cleanup blocker,
  reported as `session gone`. Observation keeps that record, rather than
  pruning it, until no such process lives. An ended record retains, as
  ADR 0095 has it, while any sub-agent it lists runs in a process that is
  not gone.

## Considered options

- **Keep ADR 0097's rule and document the gap.** Rejected: it lets Cleanup
  remove a Worktree a working child may be in, the harm ADR 0066 exists to
  prevent.
- **Carry every listed sub-agent across a process change, and let the scan
  drop those of a gone process.** Rejected: without a probe at write time,
  the record's stored state would count a dead process's sub-agents, and a
  `claude --resume` would hold the session `running` until its next event.
- **Keep the session's first process as the record's own while it lives.**
  Rejected: the second process runs the session's turns and holds its Issue
  work. Its liveness and runtime evidence are what the record's process
  means
  ([domain language](../domain-language.md)).
- **Treat a gone record that lists sub-agents like an ended one.**
  Rejected: an ended record is the session's own word that it ended, and
  `forget-subagents` and the Worker evidence of ADR 0096 read it that way.
  A gone record keeps only the blocker, and only while another process that
  runs its sub-agents lives.

## Consequences

- A working child of another live Host Process stays listed as it was
  before the second Host Process's `SessionStart`. It holds the session
  `running` after that process's own turn ends
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)),
  `dashpot work show` reports it as listed as working, and it counts in the
  Worker evidence of
  [ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)
  as it did before that `SessionStart`. Each goes on the child's
  `SubagentStop`, or as soon as its process is gone, reported or not.
- The `sub-agent` blocker of
  [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)
  holds in #448's OpenCode order from the client's `SessionStart` to the
  child's `SubagentStop`, across the client's exit.
- A gone record kept for another process's sub-agent shows nowhere in the
  Sessions pane: it is no Agent Run, no row and no Worker line, and
  assignment ignores it. It still answers an Orphaned Agent Run's claim on
  the session's last activity, as every gone record does.
- `dashpot work forget-subagents` reads only ended records, so it does not
  reach a kept gone record. The record goes once the process running its
  sub-agents exits, which is also when that process's sub-agents end.
- Nothing keeps a gone process's sub-agent counted. Once a record names its
  process, every later write of the session probes it and drops the
  sub-agent when it is gone. A record that receives no later write keeps the
  tag in its stored listing and state, but every scan probes the tagged
  process: the sub-agent is not listed, the session reads `waiting` unless
  its own turn runs, `work show` does not name it, and the blocker goes.
- The publisher probes a process only for a session whose records name a
  sub-agent's process other than the event's. A record of one Host Process,
  the only kind before this decision, costs nothing more.
- Not changed:
  - OpenCode's `_forget_subagents` empties a marked root's whole listing on
    its own server's next publication, tagged sub-agents included, and
    registration recovers only the roots a server's records name as their
    own.
  - `dashpot integrate <harness> --status` reports a kept gone record as a
    gone record, without naming the sub-agents that keep it.
  - A conversation switch adopts only the sub-agents the switching process
    runs ([ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)).
- Amends ADR 0097: a `SessionStart` from another named Host Process carries
  the sub-agents of a process the publisher finds not gone. It also closes
  ADR 0097's "Not changed" item for an OpenCode root prompted by a second,
  standalone Host Process.
- Amends ADR 0095: an event of the session from another process no longer
  drops the kept record's listing outright. It keeps the sub-agents of a
  process still running, and a `SessionEnd` keeps those too.
- Amends ADR 0016: a sub-agent leaves a session's listing when the process
  that runs it is gone, as well as at its `SubagentStop`.
