---
status: accepted
date: 2026-09-02
---

# Reconcile the session's Agent Run at SessionEnd

The Work Store is the sole authority for Issue association, and only an
explicit `dashpot work start` or `stop` from inside the session wrote to it.
An Agent Run left open when its Agent Session ended therefore became an
Orphaned Agent Run that a person had to end with `dashpot work stop --session`.
That cost pushed agents toward stopping early, after their own final push,
while delegated sub-agents sharing the same run kept working on the Issue
unobserved ([#89](https://github.com/ned2/dashpot/issues/89)). The guidance
that protects the invariant — any agent working on an Issue shows that
Issue's run — is *hold the binding until the whole engagement is done*, and
that guidance is only safe once a run cannot outlive its session.

Dashpot will end a session's Agent Run when the harness delivers the
session's graceful `SessionEnd`, at the same moment the hook removes the
session's own record:

- The hook publisher ends the Work Store record of the ended session and
  nothing else. The session is matched the way observation joins a run to
  its hook record: by the Agent Session Identity the hook published, or by
  the host process it observed. Every other session's run is untouched.
- The run is looked for at every Worktree of the Repository the session
  ended in, because a session holds one run across them
  ([ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md)). A
  session that ends outside any Repository has no Work Store to reconcile.
- The record is removed, as the hook record is, rather than kept as a
  tombstone. The Work Store holds *active* runs; an ended record would be an
  active-looking entry every reader had to skip, and the hook record it
  would be forensically paired with is already gone.
- A Work Store that cannot be read is left for observation to diagnose. The
  hook must never break its harness, so reconciliation never raises.

This is housekeeping of Dashpot's own ignored state by the hook that the
harness invokes for that session, the same class of write as removing the
hook record and pruning stale ones during observation, and so it stays inside
the boundary of
[ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md):
it never reassigns Issue work and never ends another session's run.

## Considered options

- **Keep the run and rely on orphan detection:** rejected; it is the status
  quo whose cost drove agents to stop early.
- **Tombstone the record as `ended`:** rejected, as above. `dashpot work show`
  lists active work, and a tombstone answers no question the hook record's
  absence does not already answer.
- **Reconcile during observation instead of in the hook:** rejected because
  observation cannot tell a gone session from an unobservable one and must
  never treat *cannot observe* as *exited*; only the harness's own
  `SessionEnd` states that the session ended.

## Consequences

- `SessionEnd` is not guaranteed to fire — a killed harness or a dead
  machine delivers none — so Orphaned Agent Run detection and
  `dashpot work stop --session` remain as the fallback. This removes the
  common case, not the concept.
- The Issue work lifecycle in `AGENTS.md` can stop warning that a session
  ending with a run open leaves work for a human, and can tell agents to
  hold the binding until the whole engagement is done.
- A harness event that ends the Agent Session Identity without ending the
  process — Claude Code delivers `SessionEnd` for `/clear` and for `/resume`
  to another session — ends the run too: the session that follows declares
  its own work with `dashpot work start`.
