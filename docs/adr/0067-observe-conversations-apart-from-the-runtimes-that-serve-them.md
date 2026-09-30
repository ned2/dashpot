---
status: proposed
date: 2026-10-01
---

# Observe conversations apart from the runtimes that serve them

Codex, Claude Code and OpenCode separate a conversation from the processes that
serve it in different ways. One Codex app-server or managed daemon hosts many
threads, and a controller can move a loaded thread to another directory under
the same id with no lifecycle hook. A Claude Code background session runs in
its own worker below a PTY host and a transient supervisor; the worker's pid
changes under one session on a crash or `respawn`, the supervisor can be
replaced with no hook, and `EnterWorktree` moves a session in place. One
OpenCode backend serves many sessions, its plugin can be replaced inside a live
backend, and only `session.deleted` ends a session. #159 fixed the identity
defect this caused with existing evidence
([ADR 0038](0038-isolate-native-agent-session-identities.md)), and
[ADR 0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
decided when a run survives a new process. What remained undecided was which
facts to model, what each lifecycle boundary does to an Agent Run, how
delegated work aggregates, and what happens when a live session moves to
another Worktree without ending or declaring a Relocation Intent — the route
[#148](https://github.com/ned2/dashpot/issues/148) needs to relocate occupants
during Cleanup. The evidence, transition table, support and scenario matrices,
worked examples and per-Issue work are in the
[agent runtime lifecycle design](../agent-runtime-lifecycle-design.md).

Proposed here means decided but not yet implemented. The implementing Issues
(#161, #162, #163) mark this ADR accepted as they deliver it, and any deviation
needs its own ADR.

## Decision

Dashpot models three facts and no more:

- The **conversation**, identified by its Agent Session Identity
  `(harness, native session ID)`.
- Its **Host Process**: the nearest harness process that executes the
  session's turns, keyed by pid and start time, recorded as liveness and
  runtime evidence. It may serve several sessions; the Harness Adapter says
  whether it is exclusive (ADR 0053). A Claude Code supervised worker is its
  session's Host Process.
- An **incarnation boundary**, observed as `SessionStart` and persisted only
  as a hook-record stamp, `lastSessionStartAt`. OpenCode, whose plugin can be
  replaced inside a live backend, keeps its publisher generation as the
  [OpenCode design](../opencode-integration-design.md#track-publisher-lifetime-without-redefining-agent-session)
  proposes.

Supervisors, PTY hosts, attached clients and terminals are never recorded.
Supervisor replacement is not a lifecycle boundary and never a reason for
`work start`.

Ending needs positive evidence: `SessionEnd` for Codex and Claude Code,
`session.deleted` for OpenCode. Silence keeps last-known state, unknown
liveness is never gone, and `SessionEnd` ends only work from its own Host
Process that did not start after it. A daemon-hosted Codex terminal's `/exit`
therefore ends nothing until the thread's unload publishes `SessionEnd`.

An Agent Run keeps its identity, `startedAt` and Issue Binding across a
boundary only through one of four routes: [ADR 0029](0029-preserve-agent-runs-through-declared-codex-relocation.md)'s
declared sequential relocation, ADR 0053's orphan continuation, the Live
Relocation below, or no boundary at all. Otherwise it stays where it is or
ends. The restart policy follows: Claude Code continues through ADR 0053;
Codex and OpenCode need an explicit `work start` after their Host Process is
replaced; no route adopts a run from history, a Branch or a path.

Delegated work aggregates. An event that carries `agent_id` (Codex, Claude
Code) or a native `parentID` (OpenCode) updates only its parent's live
sub-agent set, extending [ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)
to Codex. It never sets the parent's Observation Location, turn clock, store
routing, Issue Binding or ending, and a child's claim never authorizes Issue
work.

A session's authoritative Observation Location comes only from the Harness
Adapter's designated, session-scoped location evidence: a Codex
`UserPromptSubmit`, a Claude Code `PostToolUse` of `EnterWorktree` or
`ExitWorktree` with `action: keep`, and a new incarnation's `SessionStart`. A tool call's working
directory is never location evidence.

**Live Relocation** is the new route. When a designated event for session S
arrives at Worktree B from the same Host Process that S's active run records,
the hook publisher carries the run from Worktree A to B, preserving its session
key, `run_id`, `startedAt` and Issue Binding. It does so only under the eight
conditions the design numbers in
[Live Relocation](../agent-runtime-lifecycle-design.md#live-relocation), which
this ADR adopts as written: the run's identity is the event's; the Host
Process is the same and observed on both sides; the event is designated,
session-scoped, and neither `SessionStart` nor `SessionEnd`; B is another Worktree of A's Repository; under the session's
hook-store locks the event is S's freshest record and the freshest record
outside B is at A, from the same Host Process, and not ended; B's store has
seen no `SessionStart` for S since that record; B holds no other run for S;
and any pending Relocation Intent names exactly B, which the carry then
completes and clears.

The carry reuses the Work Store's compare-and-move. It runs after ADR 0029's
completion and before ADR 0053's continuation, and never creates a run for an
unbound session. A refused carry leaves the run at A with a new
`work-session-elsewhere` Diagnostic. Because a shared Host Process such as the
Codex daemon outlives the session, a `SessionEnd` also removes the session's
records at the Repository's other Worktrees that name the Host Process the
`SessionEnd` itself came from, both keys observed, and that are not newer than
it, so a session that moved and then ended is not left live at its old
Worktree.
Who may trigger such a move stays #148's decision.

## Considered options

- **Model supervisors, attached clients or a heartbeat.** Rejected: every
  measured supervisor and client transition is fully described by the Host
  Process's own evidence, and no observation consumes the extra records.
- **A publisher generation for every harness.** Rejected: Codex and Claude
  Code hooks are dispatched by the Host Process itself, so a publisher cannot
  outlive or diverge from it. OpenCode keeps one.
- **Extend OpenCode's explicit restart to Claude Code.** Rejected: ADR 0053
  already decided Claude continuation on stronger evidence.
- **Require a Relocation Intent for every move.** Rejected: a controller or a
  worktree tool moves the session without its shell running a command, and
  #148 option 1 or 2 would have no declaration to wait for.
- **Carry on any fresher record at another Worktree.** Rejected: a Claude
  shell `cd` inside the project changes ordinary hook `cwd`, a sub-agent's
  hooks can carry another location, and a late or cold-resume event would move
  a run without a live move.
- **Recognise a restart as a move when the Host Process changed.** Rejected:
  that is ADR 0029's and ADR 0053's territory, and a new process proves
  nothing about intent.

## Consequences

- When implemented, this amends [ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md):
  a Claude Code session with a run that calls `EnterWorktree` or
  `ExitWorktree` (`keep`) has its run carried rather than left for `work start` to
  switch. It amends ADR 0016, whose live set extends to Codex, and ADR 0029,
  whose Relocation Intent a Live Relocation to exactly its target also
  completes; ADR 0029's own confirmation is unchanged. It also extends
  ADR 0015: a `SessionEnd` removes the session's older records at other
  Worktrees that name the ending event's own observed Host Process. Each gains `amended-by` when #161 or #162 delivers the change.
- The Harness Adapter gains a predicate naming its designated location
  evidence. The hook record gains the optional `lastSessionStartAt` and stays
  version 2. The Work Store, the published models and the Runtime Event
  fields are unchanged; a carry is reported as the existing `relocated`
  change.
- The publisher must stop letting a child-scoped event rewrite its parent's
  location and routing. Today an isolated Claude sub-agent can place its
  parent at `.claude/worktrees/agent-<id>`.
- The Issue-work skill checks `work show` after `EnterWorktree` before running
  `work start`, since the run may already have been carried.
- Supervised Claude workers are recognised as Host Processes since
  [#326](https://github.com/ned2/dashpot/issues/326), so a worker replaced
  after an abrupt exit continues its run under ADR 0053 (measured with the
  `--resume` shape; a `respawn` or spare replacement after an abrupt exit is
  unmeasured) and a worker's move can be a Live Relocation. `claude stop`
  publishes the worker's own `SessionEnd` and ends its run, so a later
  `claude respawn` has no run to continue.
- Every unmeasured mode is unsupported until its implementing Issue measures
  it: Claude idle eviction, a Codex terminal launched before the daemon,
  daemon autostart, input joined to a running Codex turn, a sub-agent live
  during a move, Remote Control on both harnesses, and every remote, SDK,
  cloud and V2 mode.
