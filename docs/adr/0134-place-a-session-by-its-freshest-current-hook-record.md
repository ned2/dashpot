---
status: accepted
date: 2026-10-05
---

# Place a session by its freshest current hook record

Each checkout keeps its own hook store, so an Agent Session that moved
between Worktrees, or ran around an integration upgrade, has a record in
several stores. Every reader asked which of them places the session, and they
gave different answers ([#545](https://github.com/ned2/dashpot/issues/545)):

- **The dashboard** observed the freshest live or unknown record that placed
  the session at an Observation Target. It skipped ended and gone records
  however fresh, fell back to an older record when the freshest placed the
  session elsewhere, and of two records stamped alike kept the last one read.
- **Cleanup, `work start` / `show`, and claim validation** took the freshest
  record whatever its outcome. When it was ended or gone the session was
  over, even while an older record of another live Host Process placed it
  in a Worktree. Of two stamped alike they kept the first read.
- **Worker attribution** took the freshest live or unknown record and
  ignored ended and gone ones, as the dashboard did.

So the dashboard could show a session running in a Worktree that Cleanup
offered to remove, and Cleanup could remove a Worktree a live client of the
session still ran in, because a fresher record of another process was gone.

## Decision

One value, `SessionHistory` in
[`hook_scan.py`](../../src/dashpot/sessions/hook_scan.py), holds one Agent
Session Identity's readable records across every reachable store, and every
reader of placement asks it.

- **One order.** Records are ordered by `lastActivityAt`, freshest first. Of
  two stamped alike, the first read leads: a Worktree's own store before the
  next, and the global store last, in the order `reachable_hook_stores` gives.
- **A record is current** while it is live or unknown, unless a fresher record
  that is over (ended or gone) ends it.
- **An over record speaks for its own Host Process.** It ends an older record
  of the same process, or of one naming none, which is no evidence of another
  process ([ADR 0132](0132-refuse-a-session-end-only-on-another-named-host-process.md)).
  It never ends an older record another named process holds: that process
  may still run the session, as a Codex client does after the client it
  resumed beside exits.
- **The freshest current record places the session** and gives its state.
  A session with no current record is over, and its freshest record says how.
- **Its Sub-agents are listed by every current record, and by every record
  that keeps them after its session ended**
  ([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md),
  [ADR 0107](0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)).
  A current record the session moved on from still lists its Sub-agents
  ([ADR 0102](0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)).
  This assumes, as [ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)
  does, that no hook says where a Sub-agent itself works;
  [#474](https://github.com/ned2/dashpot/issues/474) re-measures that.

Observation, Worker attribution, Cleanup occupancy, `work start` / `show` /
`assign`, claim validation, a pending Relocation Intent's diagnosis and the
sequential Codex resume's confirmation are all built on it.

Observation prunes a live or unknown record that a fresher ended or gone
record superseded, as it prunes an ended record that keeps no Sub-agents. Otherwise the
superseded record would be current again once the ended record that
superseded it was pruned.

A Claude Code session's own move keeps the record it left behind
([#519](https://github.com/ned2/dashpot/issues/519)). `EnterWorktree` leaves
the `UserPromptSubmit` of the turn that called it running in the first
Worktree's store, while the tool's `PostToolUse` and the turn's `Stop` write
the session's record at the second. That record is neither retired nor
rewritten. A fresher current record exists, so nothing places the session by
it or reads its state. It stays a Sub-agent listing, as
[ADR 0102](0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)
keeps the records a moved session left behind for the Sub-agents it
dispatched before it moved, and a Sub-agent's stop clears it there. The
session's `SessionEnd`, which carries the first Worktree's `cwd`, removes it
and the session's record at the second Worktree. A test replays #466's
measured order.

The hook store derives the next record from typed `HookRecord` values and
reads its previous record as a scan reads it. Two deliberate divergences
remain, each named where it is coded:

- **The publisher's unprobed reads.** A hook probes no Host Process. It
  routes a Sub-agent's event, and seeds a session-scoped event that moves the
  session, from the freshest record that is not ended; a Sub-agent's event
  also routes to an ended record that keeps Sub-agents (ADR 0095). It cannot
  tell a gone record from a live one, and a superseded record may seed until
  an observation pass prunes it. A seed counts only when it names the event's
  own process. It shares the tie-break.
- **A Sub-agent's unreadable Host Process.** The publisher treats it as the
  session's own and writes it untagged, while the scan reads it as unknown
  ([#573](https://github.com/ned2/dashpot/issues/573)).

## Considered options

- **The freshest record, whatever its outcome**, as Cleanup used. Rejected:
  another process's end or exit would hide a client of the session still
  running, and Cleanup would offer its Worktree.
- **The freshest live or unknown record, ignoring over records**, as the
  dashboard used. Rejected: a record its own process's later end superseded
  would still be shown running, and whether a session is over would depend
  on whether its ended record had been pruned yet.
- **Retire the record a moved session left behind** (#519). Rejected: nothing
  places the session by it, and it may be the only record that lists a
  Sub-agent the session dispatched before it moved (ADR 0102).

## Consequences

- Amends [ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md):
  a session's current location is its freshest current record, not its
  freshest record.
- Amends [ADR 0132](0132-refuse-a-session-end-only-on-another-named-host-process.md):
  the store reads a recorded Host Process it cannot parse as naming none, as
  the scan does, so a newer end beside it is accepted. A rewrite drops such a
  value, and a malformed Sub-agent host tag, rather than copying it through.
  A previous record no scan can read, as one without a `cwd`, is no evidence:
  the store carries nothing from it and refuses no end beside it.
- The dashboard observes a session only where its freshest current record
  places it, so one placed outside every Observation Target is not observed
  at an older record's Worktree, and one whose own process's fresher end
  superseded a live record is not observed at all.
- Cleanup, placement and claims find a session that a fresher record of
  another Host Process left over still current where an older record of a
  live process places it.
