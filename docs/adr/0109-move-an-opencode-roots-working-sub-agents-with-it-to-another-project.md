---
status: accepted
date: 2026-10-05
---

# Move an OpenCode root's working Sub-agents with it to another Project

[ADR 0090](0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md)
writes an OpenCode root's move to another Repository at the store it left,
naming where it went, so it no longer reads as there. The root's first
event in the new Project's store then writes `SessionStart`. That
`SessionStart` seeds from the session's freshest record of the same Host
Process
([ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md),
[ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)),
but the publisher reads only the stores of the Repository the event places
the session in, and the global one. The store of the Project the session
left is not among them.

[#448](https://github.com/ned2/dashpot/issues/448) measured the case on
OpenCode 2.0.22, in the `move-other-project` order of its trace
([`issue-448-opencode-trace.jsonl`](../spikes/measurements/issue-448-opencode-trace.jsonl)
receipts 863 to 1021):

1. The shared service (pid 24606) ran a root at the first Project. The
   root started a child, and the root's execution ended while the child
   held a command (#924, #925).
2. The root was moved to another Project. The move ran as an execution of
   the root (#948), and Dashpot wrote the move in the first Project's
   store, naming the new location, with the child listed (#950).
3. The move's execution ended at the new location. Dashpot wrote
   `SessionStart` and `Stop` in the other Project's store, from the same
   Host Process, with no Sub-agents (#951).
4. The child's execution ended. Its `SubagentStop` went to the other
   Project's store, where its root's record did not list it, and removed
   nothing (#1017). The record left in the first store still listed the
   child, `running`, until the service exits (#1020).

The child worked for a session that now belongs to the other Project, yet
that Project's Cleanup did not see it: no `sub-agent` blocker held there
while the child worked. [#459](https://github.com/ned2/dashpot/issues/459)
also reported that the record left behind kept blocking the first
Project's Cleanup. It did not: that record places the session at the new
location, which is in no Worktree of the first Repository (#952). Cleanup
there found no obstacle after the child ended (#1021). The trace took no
Cleanup reading while the child worked, but the record placed the session
at the new location then too. The record left behind blocked nothing, but
it listed the child where no stop would ever reach.

## Decision

A move to another Project hands the session's Sub-agent listing to the
store of the Project it moved to, at the move.

- **The move begins the incarnation there.** After the move is written
  where the session was, as before, the helper writes the root's
  `SessionStart` in the new Project's store, under that store's own
  Publisher Record lock. It holds one Publisher Record lock at a time, so
  two moves in opposite directions never wait on each other. The move's
  sequence is recorded in both Publisher Records. The root's next event in
  the new store finds a record of its Host Process there and writes only
  itself. A store whose Publisher Record refuses the session, or has seen
  a later event of it, takes nothing from the move.
- **It seeds from the record the move left.** The publisher reads the
  session's records in the store the move left beside those it reads
  already. The record the move just wrote there is the session's freshest,
  so the `SessionStart` seeds from it as ADR 0097 has any `SessionStart` of
  the same Host Process do: each sub-agent the moving process runs carries
  as the record's own, and one another live Host Process runs carries,
  tagged with it
  ([ADR 0107](0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)).
- **Then the record left behind lets them go.** Once the new record lists
  a sub-agent, the record the move left stops listing it, through
  `release_left_behind`
  ([ADR 0102](0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)),
  which re-reads the record under its lock and changes only its list. A
  publisher that fails between the two writes leaves the sub-agent listed
  twice, which errs toward blocking, as
  [ADR 0101](0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)'s
  switch does. The release happens at the move, not at the sub-agent's
  stop, because the stop reaches only the stores of the Repository the
  session is in now.
- **The plugin's order keeps it sound.** The plugin publishes a root's
  events and its children's one at a time, in the order admitted, so no
  child event reaches the new store before the move's `SessionStart`.

## Considered options

- **Hand the listing over at the root's next event.** Rejected: that
  publication names only the new location. Finding the store the session
  left would need a pointer kept in the new Project's Publisher Record, a
  second record of where the session was, which the move publication
  already knows.
- **Write the move itself in both stores.** Rejected: a `SessionMoved` in
  the new store is designated location evidence, which may carry an Agent
  Run within that Repository (ADR 0067). A move across Repositories never
  carries a run, and ADR 0090 already has the new store begin an
  incarnation, which a `SessionStart` is and which ADR 0067's Live
  Relocation refuses to read as a move.
- **Keep the listing in the record left behind, and widen the stop's
  reach to every store.** Rejected: the stop would have to search every
  Project the session ever visited, and the new Project's Cleanup would
  still not see the child.
- **Document the gap.** Rejected: it lets the new Project's Cleanup remove
  a Worktree a working child may be in, the harm
  [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)
  exists to prevent.

## Consequences

- A child working when its root moves to another Project is listed only
  where the root now is. It holds the session `running` and blocks the new
  Project's Cleanup until its stop, which now finds it.
- The root's incarnation in the new Project's store begins at the move,
  not at its next event. The record reads `running` while the child works,
  and `waiting` otherwise until that event, which is the end of the move's
  own execution in the measured order.
- The record left behind keeps its state and stamp, as ADR 0102 has it. It
  places the session at the new location, so it reads nowhere in the first
  Project.
- Not changed:
  - A move to a location outside every Project is written where the
    session was, and its record keeps listing the child until the service
    exits. It places the session outside the Repository, so it blocks
    nothing.
  - A sub-agent that another Host Process runs stays listed in the record
    left behind as well, since only the moving process's own sub-agents
    leave it. That record blocks nothing in the first Project, and the
    sub-agent goes from it once that process is gone.
  - A move within one Repository is unchanged (ADR 0067, ADR 0102).
- Amends ADR 0090: a move to another Repository writes `SessionStart` in
  the new Project's store at the move, and the session's next event there
  writes only itself.
- Amends ADR 0067: the seed of that `SessionStart` reads the store of the
  Project the move left, as well as the new Repository's stores.
- Amends ADR 0097: closes its "Not changed" item for an OpenCode root moved
  to another Project.
- Amends ADR 0102: a record an OpenCode root left in another Project's
  store releases the moving process's sub-agents at the move. Its "Not
  changed" item now covers only a store left some other way, and its claim
  that such a record blocks that Repository's Cleanup does not hold for an
  OpenCode move, whose record names where the session went.
