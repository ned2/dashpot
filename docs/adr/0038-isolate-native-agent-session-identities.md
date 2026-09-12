---
status: accepted
date: 2026-09-13
---

# Isolate native Agent Session identities

Distinct Codex conversations can share a backend process. Process-derived Work
Store keys and native-identity-or-process matching allowed one conversation to
adopt another's location or activity, replace its Issue Binding, or clear its
Agent Run ([Issue #159](https://github.com/ned2/dashpot/issues/159)). Four isolated
regressions reproduced these failures; the later disappearance of a live
binding was not traced to a particular lifecycle event.

## Decision

The confirmed `(harness, native session ID)` identifies an Agent Session on both
visible and sandboxed routes. One small matching interface distinguishes equal,
different, and unresolved identities. Different named identities never match by
process; unnamed records of the same harness remain unresolved, including when
the recorded process differs. Neither absence of another hook nor a process
match proves exclusive ownership of a shared backend. Commands require a claim
confirmed by the same harness's hook, and visible ancestry must corroborate its
full PID/start-time evidence. Ambiguous claims retain explicit disambiguation.

New named Agent Runs use a harness-prefixed full SHA-256 digest of the native ID
as their storage name. Stored identity is checked independently; a digest or
filename collision cannot authorize replacement. Named legacy process-keyed
records stay readable and retain their keys through observation and continuing
relocation. Explicit start may restart a run while retaining its selected key.
No bulk rename or passive migration changes existing Agent Run identities.

Hook records likewise retain full harness identity during lookup and folding.
When two harnesses publish the same native label into one store, a scoped digest
filename holds the second identity without overwriting the existing record.
Writers serialize both candidate filenames, and readers validate filename and
full stored identity. Existing hook filenames remain supported.

Mutations select only the named session's records, preflight ownership and
runtime guards, then compare the complete expected record under its lock before
replacement or deletion. A new destination must be empty; different-key target
runs also block relocation. SessionEnd requires compatible runtime evidence and
cannot clear work started after its ending evidence. The existing lock mechanism
rechecks its inode after acquisition, preserving exclusion when an old lock is
pruned. Cross-Worktree writes remain bounded operations, not a general transaction
system; concurrent changes are reported without deleting changed records.

## Compatibility and recovery

This deliberately tightens the process-only behavior of
[ADR 0007](0007-identify-sandboxed-sessions-by-agent-session-identity.md)
and the matching described in
[ADR 0015](0015-reconcile-the-agent-run-at-session-end.md).
[ADR 0029](0029-preserve-agent-runs-through-declared-codex-relocation.md) still
requires declared sequential continuation; equal identity does not waive runtime,
location, pending-intent, or concurrency guards. Claude Worktree movement and
parent-scoped delegated activity remain supported. Hooks and native child IDs
never establish Issue Bindings.

Unnamed legacy runs stay visible with `work-session-unresolved` and unknown
activity. They block a same-harness command from adopting them or creating work
beside them. After the recorded process is proved gone, a person can select the
exact run with `dashpot work stop --session KEY` at its Worktree. A live or
unobservable recorded process blocks that recovery; a legacy record carrying
neither native nor process identity can be ended by that explicit key selection.
The intended session then declares fresh Issue work. No recovery infers a lost
binding from Branches, paths, or conversation history.

## Considered options

- Retain process fallback when only one hook is visible: rejected because a
  missing hook does not prove that a backend has only one conversation.
- Rename all legacy records: rejected because the storage key participates in
  Agent Run identity and would break continuing runs and Relocation Intents.
- Require separate servers or terminals: rejected because isolation is a
  correctness requirement for already supported sessions.
- Add server registration, leases, or remote attachment tracking: deferred;
  those hosting contracts are outside this bounded identity correction.
