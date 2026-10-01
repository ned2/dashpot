---
status: accepted
date: 2026-10-01
---

# Refuse a Live Relocation on evidence it cannot read

A Live Relocation
([ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md))
moves an Agent Run with its identity, `startedAt` and Issue Binding on hook
evidence alone, with no command from the session. The
[lifecycle design](../proposals/agent-runtime-lifecycle-design.md#live-relocation)
requires that the new record H be the session's freshest, that the record it
follows be from the same Host Process, and that the target Worktree B hold no
other run for the session. It does not say what the carry does when some of
that evidence cannot be read.

A hook record that cannot be read or validated may be the session's freshest,
or its record at another Worktree from another process, so the conditions
cannot be shown to hold. A Work Store record at B that cannot be read may be
a competing run of the session, and an unresolved legacy record there, which
names no Agent Session Identity, may be the session's own
([ADR 0038](0038-isolate-native-agent-session-identities.md)). ADR 0029's
declared completion already refuses on the same unreadable and unresolved
evidence.

Dashpot therefore refuses the carry, leaving the run where it is, when any of
the session's hook records in the Repository's reachable stores cannot be
read, when any Work Store record at B cannot be read, and when B holds an
unresolved record. A Work Store that cannot be read at all refuses too. The
refusal writes nothing and fails no hook; the next designated event retries,
and observation reports the run left behind as `work-session-elsewhere` until
the evidence is repaired or the session runs `work start` there.

## Considered options

- **Skip what cannot be read and decide on the rest:** rejected. A carry is
  the one route that moves Issue work without a command, and moving it on
  partial evidence could reassign a run the session no longer holds, or
  stack it on a competing one.
- **Refuse only on a competing run under another key (condition 7 alone):**
  rejected, since an unreadable record cannot be shown not to be one.

## Consequences

- An unreadable record of one session blocks only that session's carry;
  other sessions, the hook write itself, and ADR 0053 continuation are
  unaffected.
- A Codex session whose carry is refused this way continues on its next turn
  once the record is repaired, or through `dashpot work start` at B.
