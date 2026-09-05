---
status: accepted
date: 2026-09-05
---

# Preserve Agent Runs through declared Codex relocation

A Codex conversation can resume under a new client process at another linked
Worktree while retaining its Agent Session Identity, but an ordinary
`SessionEnd` correctly ends that session's Agent Run. Dashpot will distinguish
the sequential resume from a genuine end with an explicit, two-phase
Relocation Intent; identity reuse or a changed working directory alone remains
insufficient authority.

Before exiting, the active Codex session runs `dashpot work relocate PATH` at
its current Worktree. The command requires one active Agent Run, a confirmed
Agent Session Identity, fresh hook evidence placing the session there, and an
exact target among the Repository's linked Worktrees. It records the target and
request time on the existing Work Store record without changing the Issue
Binding, Agent Run identity, or `startedAt`. `work relocate .` cancels a pending
intent after the same session resumes at its original Worktree.

The old client's `SessionEnd` preserves a run carrying that intent before it
removes the old hook record. A later Codex hook completes the relocation only
when all of these facts agree:

- the hook publishes the same Agent Session Identity from the intended target;
- no hook record describes a live or unobservable client for that identity at
  another Worktree; and
- exactly one pending source record exists, with no competing Work Store
  record for that session. An identical record already written at the target
  is accepted only to repair the write-before-delete crash window.

Completion writes the record durably at the target before removing it from the
origin, clears the intent, adopts the resumed process, working directory, and
Branch, and preserves the session key, Issue Binding, and `startedAt`. The hook
locks every reachable same-session record while checking the location and
moving the run; the Work Stores lock the record in deterministic path order.
A retry recognizes an already-written identical destination, closing the
narrow write-before-delete crash window without overwriting different work.

A live or unobservable old client prevents completion. A hook at a mismatched
target leaves the intent unchanged, emits `work-relocation-mismatched`, and
`work start` there refuses rather than reassigning the run. A killed old
process is sufficient evidence that it is no longer concurrent, so the
correct target hook may complete even when `SessionEnd` was lost. Missing
hooks, unreadable state, or an abandoned resume
leave the run pending and visible with an actionable
`work-relocation-pending` Diagnostic; Dashpot neither expires nor ends it from
a clock. The same session may resume at the origin and cancel, or a person may
explicitly end the exact pending run with `work stop --session`.

Claude Code's live `EnterWorktree` and `ExitWorktree` relocation remains
unchanged. A new Agent Session cannot complete another session's intent, and a
tool-call `cd` or sub-agent still lacks target hook evidence. Hook completion
mutates only Dashpot's ignored Work Store state for the publishing session, so
observation remains passive.

## Considered options

- **Always end on `SessionEnd` and call `work start` after resume:** rejected
  because it turns one engagement into two Agent Runs and loses `startedAt`.
- **Infer continuity whenever an identity reappears:** rejected because it can
  resurrect work a genuinely ended session left behind and cannot distinguish
  concurrent clients.
- **Move the record before the old client exits:** rejected because the target
  has not yet been observed and a failed resume would publish work where no
  session ran.
- **Expire a pending intent automatically:** rejected because elapsed time is
  not evidence that the conversation ended; the pending run remains explicit
  and recoverable instead.

## Consequences

- Work Store version 2 adds the optional Relocation Intent. Version-1 records
  remain readable and have no relocation meaning.
- The Agent-facing Issue-work skill prepares active Codex runs before resume
  and checks `work show` first after arrival; unbound and fresh-session paths
  still use `work start`.
- [ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md) and
  [ADR 0015](0015-reconcile-the-agent-run-at-session-end.md) are amended by
  the declared exception; an undeclared `SessionEnd` still ends the run.
