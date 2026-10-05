---
status: amended
date: 2026-10-05
amended-by: 0109-move-an-opencode-roots-working-sub-agents-with-it-to-another-project.md
---

# Clear a stopped sub-agent from the records a moved session left behind

Each checkout keeps its own hook store, so a session that moves between
Worktrees of one Repository has a record in each. On the session's first
event at the new Worktree, the store seeds the new record from the
session's freshest record of the same Host Process elsewhere, so the new
record lists the sub-agents the session had working
([ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md),
[ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)).
The record left behind lists them too.
[ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)
blocks removal of every Worktree of the Repository while any record of a
live or unknown session lists a sub-agent, taking the union over every
record of the session that is not over. That union is how a session that
moved on still blocks Cleanup for the sub-agents it dispatched elsewhere.

A sub-agent's `SubagentStop` goes to the store that holds its session's
freshest record. It removed the agent from that record only, and
[ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)
extended it to every ended record of the same Host Process. Nothing
removed the agent from a live record the session had left behind.
[#421](https://github.com/ned2/dashpot/issues/421) measured the result
with OpenCode 2.0.22 (trace `issue-421-opencode-trace.jsonl`, labels
`mv-before-move` to `mv-later`):

1. A bound lead at the main checkout launched a background worker, and
   its turn ended.
2. While the worker ran, the lead was moved to another Worktree.
3. The worker ended, and its notice woke the lead there.

The record at the new Worktree read `waiting` with no sub-agents. The
record at the main checkout still listed the worker and was never updated
again. `work show` and every Worktree's `sub-agent` blocker reported the
finished worker until the session ended or its process exited
([#427](https://github.com/ned2/dashpot/issues/427)). Claude Code's
`EnterWorktree` and a Codex Live Relocation reach the same seed and the same
stop path. They were not measured separately.

## Decision

A sub-agent's stop releases it from the records its session left behind.

- **The stop reaches the session's own live records.** After a
  `SubagentStop` is written, the publisher reads every record of the same
  harness and Host Process across the stores it can reach: the stores of
  the Repository's Worktrees and the global one. Each live record of the
  same session that lists the agent stops listing it. ADR 0101's rule for
  ended records of any session of that process is unchanged.
- **Only the list changes.** The record left behind keeps its state, turn
  clock, location and stamp. It never reads as fresher than the record the
  session moved to, so it never places the session back where it left. Its
  state, such as the `running` of the turn it moved in, is never read: the
  session's freshest record alone gives its state and location (ADR 0067).
  The dashboard, `work show` and Cleanup's `agent-session` occupant all read
  the session at the Worktree it moved to. The record stays when it lists
  none, because a live session's record goes only at the session's end or
  when observation prunes it.
- **The record the stop was written to is skipped.** A worker waiting on
  its own background work publishes an interim `SubagentStop`. When it
  resumes, it is started again on the session's freshest record
  ([#472](https://github.com/ned2/dashpot/issues/472)). A start written
  between the stop and its release must stay listed. Only records the stop
  was not written to are released, and a start goes to the session's
  freshest record, which is the one the stop was written to unless the
  session moves in between.
- **It reuses ADR 0101's machinery.** `stored_process_records` finds the
  records, and each store re-reads its record under that record's lock
  before changing it. `release_left_behind` on `HookRecordStore` sits
  beside `release_subagents` and shares its compare-and-update.
  `release_subagents` itself was not widened. Its contract is an ended
  record of any session, which goes when it lists none. This rule needs a
  live record of the stopping session, which stays.
- **The union stays.** A sub-agent still working is listed by the record
  it was dispatched from, and by every record seeded since. It blocks every
  Worktree of the Repository until its own stop, as ADR 0066 decides. A
  live or unknown session still blocks removal.

## Considered options

- **Ignore a left-behind record's sub-agents in the scan once the freshest
  record no longer lists them.** This is the Issue's second option.
  Rejected, because the scan cannot tell a sub-agent that stopped from one
  the freshest record never listed. A move inherits nothing when no named
  Host Process connects the two records, for example when the event at the
  new Worktree names no process, or names another one. A still-working
  sub-agent is then listed only in the record left behind. The scan would
  drop it, and Cleanup could remove the Worktree it works in. That errs
  toward allowing a removal, against ADR 0066. The rule would also have to
  be repeated in every reader of a non-freshest record's list. Its one
  advantage is that it would also correct records already left stale before
  this change. Those keep their bound: the session's end or its process's
  exit.
- **Release the agent from every live record of the Host Process,
  whichever session it belongs to.** Rejected as reach without evidence.
  No measured order lists one sub-agent on two live sessions, and ADR 0101
  kept other live sessions' records out of its rule for the same reason.
- **Write the stop into every store that lists the agent.** Rejected. A
  child-scoped write keeps the later of the record's stamp and its own
  (ADR 0067). The record left behind would become the freshest and place
  the session back at the Worktree it left.

## Consequences

- Amends [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md):
  within the Repository, a sub-agent that stops after its session moved to
  another Worktree no longer stays live in the record left behind. The
  union over every record of a session that is not over still holds.
- Amends [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md):
  its rule that a sub-agent's stop leaves a live session's records
  unchanged now covers other sessions' live records only. The stopping
  session's own records left behind let the agent go.
- `work show`, the `sub-agent` blocker and the Worker Assignments
  ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md))
  agree after a moved lead's worker stops. A Lead can move while a worker
  runs without Dashpot keeping the worker listed.
- Not changed:
  - A record left in a store the publisher cannot reach keeps the agent
    listed. That is a store of another Repository, such as one an OpenCode
    root left when it moved to another Project. It is bounded by the
    session's end or its process's exit, and it blocks only that
    Repository's Cleanup.
  - A record left stale by a stop published before this change is not
    revisited. A stop with no named Host Process releases nothing elsewhere.
  - A sub-agent whose stop is never reported, such as an interrupted Codex
    child, stays listed in every record, as ADRs 0016 and 0066 accept.
  - A move whose seed is read before a concurrent stop is written, and is
    itself written after the stop, lists the stopped agent on the record it
    moves to. That window is the length of one hook write, and ADR 0067's
    seed already had it.
  - A session that moves between a stop's write and its release, and whose
    worker starts again on the record it moved to in that time, has the
    worker released there too. It is not listed again until a later
    `SubagentStart`, if one comes.
    That errs toward allowing a removal, as an interim stop already does,
    and its window is also the length of one hook write.
  - An interim `SubagentStop` (#472) releases its worker from every record,
    as it already did from the freshest. Nothing here treats a stop as more
    final than ADR 0016 does.
- Amended by [ADR 0109](0109-move-an-opencode-roots-working-sub-agents-with-it-to-another-project.md)
  ([#459](https://github.com/ned2/dashpot/issues/459)): a record an OpenCode root left in another Project's
  store lets the moving Host Process's sub-agents go at the move, once the
  record the root begins there lists them. The "Not changed" item for a
  store the publisher cannot reach now covers only a record left some
  other way, and an OpenCode move's record, which names where the session
  went, never blocked the Repository it left.
