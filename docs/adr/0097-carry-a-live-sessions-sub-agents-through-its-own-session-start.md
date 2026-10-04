---
status: accepted
date: 2026-10-04
---

# Carry a live session's sub-agents through its own SessionStart

[ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md) has a
session's hook record list the sub-agents it observed started and not yet
stopped, and begins every `SessionStart` with none.
[ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)
made one exception: a `SessionStart` of the Host Process that kept an ended
record's sub-agents carries them on. A `SessionStart` that follows no end
still started the list over.

[#448](https://github.com/ned2/dashpot/issues/448) measured which
`SessionStart` each harness publishes for a session that is still live while
its sub-agent works
([spike](../spikes/session-start-on-a-live-session-spike.md)):

- **Compaction.** Claude Code 2.1.289 and Codex 0.160.0 publish a
  `SessionStart` with `source` `compact` when they compact a session, by
  command or automatically mid-turn. It names the same session and the same
  Host Process, and no `SessionEnd` comes before it. The sub-agent works on
  across it, and its `SubagentStop` follows on the same session. Dashpot
  emptied the list there: the sub-agent left the `sub-agent` Cleanup blocker
  of [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md),
  stopped holding the session running, and, under
  [ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md),
  an assigned Worker's Issue lost its activity and `work assign` refused it.
  On an automatic compaction the turn's `Stop` then recorded the session
  `waiting` while its worker still worked.
- **Nothing else** reached a live record of the same session and Host
  Process. A conversation switch (Claude Code `/clear`, `/resume`, `/branch`;
  Codex `/clear`, `/new`) starts another session id. A Codex client resuming a
  loaded thread publishes no `SessionStart`. OpenCode 2.0.22 publishes nothing
  Dashpot writes as `SessionStart` when it compacts.

## Decision

A `SessionStart` carries into the new incarnation the sub-agents that the
session's freshest live record of the same Host Process lists, and those an
ended record of that process in the same hook store kept.

- **The Host Process bounds it.** The process that started a sub-agent is
  the one that still runs it. A `SessionStart` from another process, such as
  `claude --resume`, `codex resume` or a replacement daemon, starts with
  none: the old process's sub-agents ended with it or are still that
  process's. A `SessionStart` that names no process starts with none too,
  since nothing shows it is the process that started them.
- **Only the list carries.** The `SessionStart` still begins an incarnation:
  it sets `lastSessionStartAt` and the record's state as before, and the turn
  clock carries as it does for any running record.
- **The freshest record of that process.** The carry reads the record this
  store holds, unless the session's record of the same process in another
  store is fresher: then a `SessionStart` seeds from that one, as
  [ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
  has every other session-scoped event do. A Claude Code session's shell
  `cd` moves its hooks with no hook of its own, so a session that worked
  elsewhere and came back can compact before any other event reaches the
  record it left here; that record's list is stale. An ended record of the
  same process here still adds the sub-agents it kept (ADR 0095).

The store's other rules stand. A `SubagentStop` removes its agent, a
`SessionEnd` keeps the list in an ended record (ADR 0095), and a sub-agent
whose stop is never reported stays listed until the session's process exits,
or until a person forgets it after the session ends.

## Considered options

- **Carry on only `source: compact`.** Rejected. Dashpot's hook records do
  not otherwise read the source, OpenCode's translated `SessionStart` has
  none, and the rule would not cover the next harness's name for the same
  boundary. The Host Process, which already bounds an ended record's carry,
  is what says the sub-agents may still be running.
- **Carry only this store's previous record.** Rejected after review: a
  session that came back without a hook would carry a list it no longer
  has, holding a stopped sub-agent listed, the session running, and Cleanup
  blocked until its process exits, with no command to forget it while the
  session lives.
- **Keep starting over and document the gap.** Rejected: compaction is
  routine for a long-running Lead, and the gap let Cleanup remove a Worktree
  a sub-agent worked in.

## Consequences

- Amends [ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md):
  a `SessionStart` begins with none only from another or an unnamed Host
  Process. An undelivered `SubagentStop`, such as a silently interrupted
  Codex child's, is no longer cleared by a `SessionStart` of the same
  process; it is bounded by the process's exit and, once the session ends,
  by `dashpot work forget-subagents`.
- Amends [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md):
  a compacted session's working sub-agents keep blocking removal.
- Closes the compaction boundary of
  [ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md):
  an assigned Worker reads `running` across its Lead's compaction, and
  `work assign` accepts it.
- [ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)'s
  carry of an ended record is now one case of this rule.
- Not changed, and measured under #448:
  - A Claude Code conversation switch (`/clear`, `/resume`, `/branch`) moves
    a working sub-agent to another session id in the same process. The old
    session's ended record keeps it listed until the process exits, because
    its `SubagentStop` names the new session; the new session does not list
    it. Cleanup errs toward blocking.
  - An OpenCode root moved to another Project starts that Project's record
    with no sub-agents, and the record it left keeps its child listed.
  - An OpenCode root prompted by a second, standalone Host Process starts
    with no sub-agents there, and that process's exit marks the record
    unobserved, which drops the `sub-agent` blocker while the service's
    child still works.
  - A Claude Code `/compact` publishes no `Stop`, so a waiting session reads
    `running` from the compaction until its next turn ends.
- Amended by [ADR 0100](0100-keep-a-compacted-sessions-turn-state.md)
  ([#461](https://github.com/ned2/dashpot/issues/461)): a compaction's
  `SessionStart` from the same Host Process keeps the main turn's state,
  `running` while the turn clock runs and `waiting` otherwise, so a waiting
  session stays `waiting` across a Claude Code `/compact`.
- Amended by [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)
  ([#458](https://github.com/ned2/dashpot/issues/458)): a Claude Code conversation switch's `SessionStart` takes over the
  sub-agents of the session its Host Process switched from, closing the
  "Not changed" item for `/clear`, `/resume` and `/branch`.
- Amended by [ADR 0107](0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)
  ([#460](https://github.com/ned2/dashpot/issues/460)): a `SessionStart` from another named Host Process carries the
  sub-agents of a process the publisher finds not gone, each tagged with the
  process that runs it, and drops those of a gone one. It closes the "Not
  changed" item for an OpenCode root prompted by a second, standalone Host
  Process: the `sub-agent` blocker holds until the service's child stops.
