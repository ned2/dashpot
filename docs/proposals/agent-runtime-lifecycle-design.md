---
status: proposal
date: 2026-10-01
---

# Agent runtime lifecycle design

The shared contract for observing a harness conversation apart from the
processes, supervisors and clients that serve it, designed for
[Issue #261](https://github.com/ned2/dashpot/issues/261) against Codex, Claude
Code and OpenCode together. The decision it rests on is
[ADR 0067](../adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md);
this document holds the evidence, the transition table, the support and
scenario matrices, the worked examples and the work each consumer takes on.
Reusable upstream facts stay in the
[harness reference](../agent-harness-server-client-reference.md), and the dated
experiments stay as they were written.

[#161](https://github.com/ned2/dashpot/issues/161) implemented the shared
core and the Codex part of Q4 to Q6: the `locates` predicate, the child-scope
rule and seeding, `lastSessionStartAt`, the Live Relocation step, the guarded
`SessionEnd` removal, `work-session-elsewhere`, and the Codex sub-agent
subscription. Claude Code still designates no location evidence, and the
unmeasured rows below stay unsupported. The contract is concrete enough that
its consumers implement it rather than choose it:
[#161](https://github.com/ned2/dashpot/issues/161) (the Codex slice and the
shared core), [#162](https://github.com/ned2/dashpot/issues/162) (Claude Code),
[#163](https://github.com/ned2/dashpot/issues/163) (OpenCode),
[#278](https://github.com/ned2/dashpot/issues/278) (the Live Relocation route)
and step 2 of [#148](https://github.com/ned2/dashpot/issues/148) (relocating
occupants during confirmed Cleanup). A consumer that needs a policy this
document does not state records its own ADR rather than inventing one.

## Evidence base

| Harness | Evidence | Where |
| --- | --- | --- |
| Codex | `0.155.1`: two root threads, fork, sub-agent, second client, interrupt, unload, SIGKILL/SIGTERM and stored-thread resume on `app-server --listen` and `exec`; the managed daemon with plain and `--remote` terminals, controller `turn/start` and `thread/resume` `cwd` overrides, a turn joined mid-turn, `/exit` and unload; the sequential `codex resume -C` route with no daemon, a loaded daemon thread and an unloaded one; pinned `rust-v0.154.0` source | [Codex experiment](../spikes/codex-identity-lifecycle-spike.md), [handoff experiment](../spikes/cleanup-session-handoff-feasibility-spike.md#scenario-results-codex), [declared-relocation experiment](../spikes/codex-declared-relocation-daemon-spike.md#scenario-results), [reference](../agent-harness-server-client-reference.md#measured-lifecycle-at-01551) |
| Claude Code | `2.1.276`: headless, resume, fork, sub-agent, supervisor and workers; `2.1.278`: interactive sessions with a development channel, `EnterWorktree`/`ExitWorktree`; `2.1.285`: sub-agents, resume of a running background session; `2.1.285` under [#326](https://github.com/ned2/dashpot/issues/326): supervised worker, spare and PTY host process shapes, abrupt exit, stop and respawn; `2.1.285` under [#279](https://github.com/ned2/dashpot/issues/279): where `SubagentStart`, `SubagentStop` and a sub-agent's tool hooks place it | [Claude experiment](../spikes/claude-code-identity-lifecycle-spike.md), [handoff experiment](../spikes/cleanup-session-handoff-feasibility-spike.md#scenario-results-claude-code), [2.1.285 experiment](../spikes/claude-code-2-1-285-changes-spike.md), [supervised worker experiment](../spikes/claude-code-supervised-worker-process-spike.md), [sub-agent experiment](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285), [reference](../agent-harness-server-client-reference.md#measured-supervisor-and-worker-lifecycle-at-21276) |
| OpenCode | `1.18.30` legacy plugin path: sessions sharing one backend, attached client exit, plugin disposal, deletion, backend replacement, child sessions and forks | [OpenCode experiment](../spikes/opencode-identity-lifecycle-spike.md), [OpenCode design](opencode-integration-design.md) |

Two statements in #261's evidence section are superseded. The #269 question
(does the daemon break ADR 0029's sequential resume) was answered by #272: the
sequential route relocates a daemon-hosted thread unchanged, with the origin's
`SessionEnd` before the target's `SessionStart`
([declared-relocation experiment](../spikes/codex-declared-relocation-daemon-spike.md#scenario-results)).
And Q3's runtime-replacement boundary is decided by
[ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md);
this design cites it and does not decide it again.

## The contract in brief

- **Three facts, no more.** The conversation is identified by its Agent
  Session Identity. The Host Process that executes it is liveness and runtime
  evidence, keyed by pid and start time. An incarnation boundary is observed
  as `SessionStart`. Supervisors, PTY hosts, attached clients and terminals
  are not modelled or recorded.
- **Ending needs positive evidence.** Each harness has one positive ended
  signal. Silence is last-known state, and unknown liveness is never gone.
- **Continuity has four routes and no fifth.** A run survives only through
  ADR 0029 (declared sequential relocation), ADR 0053 (orphan continuation in
  the same Worktree), Live Relocation (below), or no boundary at all. Anything
  else keeps the run where it is or ends it.
- **Delegated work aggregates.** A sub-agent or native child holds its parent
  running and never places, binds, ends or moves the parent.
- **Live Relocation.** A same-identity, same-Host-Process move to another
  Worktree of the Repository, observed on the harness's designated location
  evidence, carries the active Agent Run unchanged. This is the seam #148
  consumes, and it works under each of #148's opt-in options.
- **Minimal persistence.** The hook record gains one optional field; the Work
  Store and every published model are unchanged; one Diagnostic is added.

## Q1. Conversation, Host Process, incarnation and supervisor

A process key is not a conversation identity: Claude Code replaces a worker's
pid and start time under one session, and OpenCode and the Codex app-server
serve many sessions from one pid. The evidence requires three separate facts
and does not require a fourth.

| Fact | What identifies it | Codex | Claude Code | OpenCode | Persisted as |
| --- | --- | --- | --- | --- | --- |
| Conversation (Agent Session) | `(harness, native session ID)`, [ADR 0038](../adr/0038-isolate-native-agent-session-identities.md) | Thread id = hook `session_id` = `CODEX_THREAD_ID` for a root or fork | Hook `session_id` = `CLAUDE_CODE_SESSION_ID` | Native session id | Hook record and Work Store identity, as today |
| Host Process | The nearest harness process that executes the session's turns, by pid and start time | `exec` or TUI process, or the one app-server / daemon process for every thread it hosts | Interactive or headless process, or the supervised worker | The backend process | `sessionProcess` on the hook record and Work Store record, as today |
| Incarnation | A span of one Host Process holding the conversation, begun by `SessionStart` | `SessionStart` at the first turn after load or resume | `SessionStart` `startup`/`resume`/`clear`/`fork` | Publisher generation registration ([OpenCode design](opencode-integration-design.md#track-publisher-lifetime-without-redefining-agent-session)) | New hook-record stamp `lastSessionStartAt` (Q6); OpenCode keeps its generation document |
| Supervisor | — | None; the daemon is itself the Host Process | Transient supervisor above PTY hosts | None | Not recorded |
| Attached client | — | Terminal, `--remote` client, controller | `attach` client, terminal | Attached CLI, web client | Not recorded |

The Host Process is the harness process itself, never a sandbox helper, and
for Claude Code's supervised topology it is the worker, not the supervisor or
the `bg-pty-host`. Since [#326](https://github.com/ned2/dashpot/issues/326)
the Harness Adapter recognises a supervised worker, whose executable is named
after its version, by the start of its argument vector: the versioned
executable with `--session-id` or `--resume`, or `claude bg-spare`, claimed or
not. The supervisor, the PTY hosts and the `agents` and `attach` clients are
not Host Processes
([measurement at `2.1.285`](../spikes/claude-code-supervised-worker-process-spike.md#implications-for-dashpot);
macOS is unmeasured).

Why nothing more is modelled:

- **Supervisor.** Measured on Claude `2.1.276`, supervisor replacement with
  `--keep-workers` changes no worker pid and publishes no hook, and
  `daemon stop --any` without it publishes `SessionEnd` per worker. Both
  outcomes are fully described by the worker's own evidence. A supervisor
  record would add a claimant that can only be wrong.
- **Attached clients.** On every harness a client's departure changes
  nothing about execution (Codex and OpenCode measured, Claude `attach`
  measured). An attachment inventory would need a heartbeat to stay true and
  has no observation that consumes it.
- **Publisher generation.** OpenCode's plugin can be disposed and replaced
  inside one live backend, so its generation is required there. Codex and
  Claude hooks are dispatched by the Host Process itself, so a publisher is
  never separate from the process it describes.

## Q2. Lifecycle evidence and transitions

### Evidence kinds

Every native signal Dashpot subscribes to translates, at the edge, into one of
these kinds. They are a vocabulary for this design, not a new type.

| Kind | Codex | Claude Code | OpenCode |
| --- | --- | --- | --- |
| Began (new incarnation) | `SessionStart` (`startup`, `resume`, `fork`) at the first turn | `SessionStart` (`startup`, `resume`, `clear`, `fork`) | A new plugin generation's registration for the session |
| Turn started | `UserPromptSubmit` | `UserPromptSubmit` | `session.status` busy |
| Turn ended | `Stop` | `Stop`, reconciled against live sub-agents ([ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)) | `session.status` idle, which can repeat |
| Interrupted | `Interrupt` | — | The interrupted command aborts; its event is #163's to translate |
| Delegate started / ended | `SubagentStart` / `SubagentStop` (emitted at `0.155.1`, subscribed since #161) | `SubagentStart` / `SubagentStop` | Child session events with `parentID` |
| Moved (designated location evidence, Q5) | Session-scoped `UserPromptSubmit` | Session-scoped `PostToolUse` of `EnterWorktree`, or of `ExitWorktree` with `action: keep` | None (unsupported) |
| Ended (positive) | `SessionEnd` | `SessionEnd` | `session.deleted` |

### Positive ended evidence and what silence means

| Harness | The only positive ended evidence | What silence means |
| --- | --- | --- |
| Codex | `SessionEnd`, from unload of a subscriber-less idle thread (60 s measured, 30 min documented), graceful server or daemon exit, SIGTERM, `exec` exit, or a standalone TUI's `/exit`. A daemon-hosted terminal's `/exit` runs no hook; its `SessionEnd` arrives only at the later unload. | A daemon-hosted thread whose terminal has exited stays live until unload. After SIGKILL no hook arrives at all, so the session reads gone only by its Host Process. |
| Claude Code | `SessionEnd` (`prompt_input_exit`, `clear`, `resume`, `other` on `claude stop`, `daemon stop`, headless exit). A crash, a respawn and a supervisor replacement publish none. | No `Stop` between turns while a channel event is queued behind a running turn, so an absent `Stop` never means idle. An idle unattached worker may be evicted after about an hour; whether that publishes `SessionEnd` is unmeasured. |
| OpenCode | `session.deleted` | Backend exit and plugin disposal publish nothing that ends a session. Disposal is observation loss, not ending. |

Three rules follow for every harness:

1. **Silence is last-known state.** No time-based expiry turns running,
   waiting or live into ended. A record whose Host Process is gone reads gone;
   a Host Process that cannot be observed reads unknown.
2. **Unknown is never gone.** Unknown liveness blocks every rule that needs a
   process proved gone (ADR 0053 continuation, ADR 0029 confirmation,
   OpenCode restart), exactly as ADR 0038 already requires, and Live
   Relocation, which needs the recorded Host Process observed as the same
   live one.
3. **`SessionEnd` ends only its own runtime's work.** ADR 0038's guard stays:
   a `SessionEnd` ends a run only when its Host Process matches the run's
   recorded one (or the run records none) and the run did not start after it.
   The `2.1.285` refused `claude -p --resume <id>` publishes `SessionEnd` for
   a running worker's id from its own pid; since #326 the worker's run records
   the worker as its Host Process, so that `SessionEnd` leaves it alone.

### Transition table

"Run" is the session's active Agent Run, if any. Every row preserves the Issue
Binding of every other Agent Session Identity, including one sharing the Host
Process (#159).

| Boundary | Evidence observed | Session record | Agent Run and Issue Binding |
| --- | --- | --- | --- |
| Turn starts | Turn started | Running; turn clock set | Unchanged |
| Turn ends | Turn ended | Waiting, unless live delegates hold it running | Unchanged |
| Interrupt | Interrupted (Codex `Interrupt`) | Waiting | Unchanged |
| Client detaches (terminal, `attach`, `--remote`, OpenCode CLI) | None | Unchanged | Unchanged |
| Codex idle unload | `SessionEnd` after the unload delay | Ended | Ended ([ADR 0015](../adr/0015-reconcile-the-agent-run-at-session-end.md)), unless a Relocation Intent is pending ([ADR 0029](../adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)) |
| Claude idle eviction | Unmeasured | Unresolved: `SessionEnd` would end the run; a silent exit would leave an Orphaned Agent Run for ADR 0053 | #162 measures before advertising support |
| Graceful exit (`/exit`, `claude stop`, `exec` exit, SIGTERM) | Ended | Ended | Ended, unless an intent is pending |
| Daemon-hosted Codex terminal `/exit` | None until unload | Last-known state; live | Unchanged until the unload's `SessionEnd` |
| Crash (SIGKILL of the Host Process) | None | Gone once the process is gone | Orphaned Agent Run; stays until a continuity route or `work stop --session` |
| Runtime restart, same identity resumes | Began (`resume`) from a new Host Process | New record at the resume location | ADR 0053 continues it only for an exclusive Host Process at the same Worktree; ADR 0029 relocates it only with a declared intent; otherwise it stays orphaned and the session needs an explicit `work start` |
| Claude supervisor replacement (`--keep-workers`) | None | Unchanged; workers keep their pids | Unchanged. Not a restart and never a trigger for `work start` |
| Claude supervisor stop without `--keep-workers` | `SessionEnd` per worker | Ended | Ended |
| Claude worker SIGKILL under a live supervisor | Began (`resume`) from a new pid, measured with the `--resume` shape | New record | ADR 0053 continuation (Claude's Host Process is exclusive; follows from #326's measurement) |
| Claude `claude stop` then `claude respawn` | `SessionEnd` `other` from the worker, then Began (`resume`) in a claimed spare | Ended, then new | The stop ended the run, so the respawned session has no run to continue |
| Claude `respawn` or spare replacement after an abrupt exit | Unmeasured | Inferred: Began (`resume`) from a recognised spare | Inferred to continue under ADR 0053, since the spare shape is recognised; unmeasured |
| Conversation switch in one process (`/clear`, interactive `/resume`) | Ended for the old id, Began for the new | Old ended, new begins | Old run ended; the resumed conversation's own orphaned run may continue under ADR 0053 |
| Fork (Codex, Claude, OpenCode) | Began (`fork`) under a new id | New session | None. A fork never inherits the origin's run or binding |
| Delegate starts or ends | Delegate started / ended | Parent's live-delegate set changes (Q4) | Unchanged |
| OpenCode deletion | `session.deleted` | Ended | That exact run ended; a newer run for the same identity is untouched |
| OpenCode plugin disposal or loss | Generation retired or silent | Observation lost; the session is not ended | Unchanged; recovery per the [OpenCode design](opencode-integration-design.md#recovery-and-scenario-outcomes) |
| OpenCode backend exit and replacement | None, then Began in a new backend | Gone, then new | Orphaned; explicit `work start` after the old backend is proved gone (the agreed OpenCode policy) |
| Live location change | Moved, from the same Host Process | Freshest record at the new Worktree | Carried by Live Relocation when every Q5 condition holds; otherwise stays, with `work-session-elsewhere` |
| Declared sequential relocation | Ended at the origin, Began at the target | As ADR 0029 | As ADR 0029, unchanged |
| Observation loss (hooks uninstalled, publisher gone, store unreadable) | None, or unreadable | Unknown where liveness cannot be read; last-known otherwise | Unchanged; no inference |
| Unknown liveness | Process not observable | Unknown | Unchanged; blocks every gone-dependent rule |
| Late or out-of-order evidence | An older event arrives after a newer one | Freshness and the guards in Q7 decide | Never moves a run back, ends a newer run, or clears another identity's work |

## Q3. What happens to the Agent Run across boundaries

Decided by [ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
for runtime replacement, and completed here by Live Relocation. Identity
isolation from #159 is the precondition of every route: a route acts only on
the run whose recorded identity is the event's own `(harness, native session
ID)`, never on a run that merely shares the Host Process.

| Route | Host Process | Worktree | Declared | Decided by |
| --- | --- | --- | --- | --- |
| Ending | Same as recorded, or none recorded | Any Worktree of the Repository | — | ADR 0015, ADR 0038 |
| Declared relocation | New process, or a same-daemon cold resume after `SessionEnd` at the origin | Exactly the intended target | Relocation Intent by the session | ADR 0029 |
| Orphan continuation | New process; recorded one proved gone and exclusive | Same Worktree | — | ADR 0053 |
| Live Relocation | Same Host Process, same incarnation | Another Worktree of the Repository | Not required | ADR 0067 |
| No boundary | Same | Same | — | — |

Everything else leaves the run where it is (orphaned, or with a Diagnostic)
until a person or the session acts. The restart policy per harness is
therefore fixed, and #161, #162 and #163 implement it rather than choose it:

- **Codex.** A daemon-hosted or app-server-hosted thread is never
  continued by ADR 0053, because its Host Process is shared. A thread resumed
  after its server died is orphaned until the session runs `work start`. A
  standalone TUI or `exec` thread is also not continued until #161 measures
  that its process is exclusive; the adapter's `exclusive_session_process`
  stays false for Codex until then, and a per-Host-Process answer (daemon
  shared, standalone exclusive) needs that measurement and an amendment to
  ADR 0053's table.
- **Claude Code.** ADR 0053 continues a run through a crash or a resume in
  the same Worktree, including a supervised worker the supervisor replaces
  after an abrupt exit (following from #326's measurement of the `--resume`
  shape). `claude stop` ends the run, so a later `claude respawn` has none to
  continue. Supervisor replacement is not a boundary.
- **OpenCode.** Explicit `work start` after a backend restart, as already
  agreed. The Host Process is shared, so ADR 0053 never applies, and no
  cross-Worktree continuation is supported.

No route adopts a run from persistent history, a Branch, a path or a transcript.
An unbound session stays unbound on every route.

## Q4. Delegated work

A harness's delegated work comes in two shapes, and both aggregate onto the
parent without gaining any authority of their own.

| Shape | How an event is recognised as child-scoped | Evidence |
| --- | --- | --- |
| Codex sub-agent thread | Hook `session_id` is the root; `agent_id` names the child thread | Measured at `0.155.1`: the child's own shell claims the child id in `CODEX_THREAD_ID` and the root in `CODEX_SESSION_ID` |
| Claude Code sub-agent | Hook `session_id` and `CLAUDE_PID` are the parent's; `agent_id` present | Measured at `2.1.276` and `2.1.285`; its hook `cwd` is the parent's current cwd, except with `isolation: "worktree"`, where it is the sub-agent's own `.claude/worktrees/agent-<id>`; a sub-agent's `cd` is visible to no hook |
| OpenCode child session | Its own native id with `parentID` naming the parent | Measured at `1.18.30`; a fork carries no `parentID` and is a separate session |

The rule for every child-scoped event:

1. It updates only the parent's live-delegate set (ADR 0016) and the activity
   the set implies: a live delegate holds the parent running.
2. It never sets the parent's Observation Location, turn clock, Work Store
   routing, Issue Binding or ending. The publisher writes it to the store that
   holds the parent's freshest record, with that record's `cwd`,
   `repositoryRoot` and `branch`; only when no record of the parent is
   reachable does the event's own `cwd` route it.
3. It is never designated location evidence, so it can never trigger a Live
   Relocation.
4. A child's own claim never authorizes an Issue-work command. For Codex the
   child's shell claims the child id, which no hook confirms as a session, so
   the claim is refused. For a Claude sub-agent the claim is the parent's and
   indistinguishable from it; the ADR 0009 location refusal and the
   sub-agent rule in `AGENTS.md` remain the guard, as today. An OpenCode child
   is refused independent reassignment, as the
   [OpenCode design](opencode-integration-design.md#recovery-and-scenario-outcomes)
   specifies.
5. When a Live Relocation or any write moves the session's freshest record to
   another store, the live-delegate set and turn clock are seeded from the
   record it moved from, so a move never forgets a live delegate.

Claude Code agrees with [#279](https://github.com/ned2/dashpot/issues/279)'s
conservative shape: a sub-agent's work aggregates onto its parent's session
and has no location of its own. The isolated-worktree sub-agent is the only
case where the harness reports a sub-agent's own location, and even then it
neither places the parent nor becomes a session. Cleanup occupancy treats any
live delegate of a live or unknown session that a record places in the
Repository as possibly anywhere in that Repository, which is #279's rule
([ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
The sub-agent facts this relies on were measured under #279 on `2.1.285` and
are recorded in the reference's
[sub-agent section](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285),
which #162 cites rather than this summary.

Rules 2 and 5 do not replace ADR 0066's union of the live set over every
record of the session. A record the publisher could not reach when the session
moved, or one an older publisher left, can still hold a delegate the freshest
record lacks, and Cleanup reads only the Repository's own stores.

Codex's `SubagentStart` and `SubagentStop` are emitted at `0.155.1`. #161
subscribes them so that a Codex parent's delegates hold it running,
extending ADR 0016's live set to Codex.

Two defects in the publisher before #161 followed from this rule and were
#161's and #162's to fix: a child-scoped event overwrote the parent record's
`cwd`, `repositoryRoot` and `branch` and routed it by the child's location, so
an isolated Claude sub-agent could place its parent at
`.claude/worktrees/agent-<id>`; and a Codex sub-agent's `UserPromptSubmit`
set the root's turn state and location. The child-scope rule
#161 put in the shared publisher fixes both, since it keys on `agent_id`
whichever harness sent it.

## Q5. Observation Location and Live Relocation

### Authoritative Observation Location

A session's authoritative Observation Location is where the harness itself
says the session executes, taken only from designated, session-scoped
evidence. A tool call's working directory stays separate: a `cd` in a shell,
an OpenCode Bash `workdir`, a Claude sub-agent's `cd`, and a command run
elsewhere never place the session.

| Harness | Designated location evidence | Why |
| --- | --- | --- |
| Codex | Session-scoped `UserPromptSubmit` (no `agent_id`); `SessionStart` places a new incarnation | Hooks report `turn_context.cwd` (pinned source), measured to follow a `turn/start` override and a `-C` resume |
| Claude Code | Session-scoped `PostToolUse` of `EnterWorktree`, or of `ExitWorktree` with `action: keep`; `SessionStart` places a new incarnation | The tools move the session with no other hook ([ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md)). Ordinary hook `cwd` follows a persistent shell `cd` inside the project ([measured under #279](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285) on `2.1.285`), which is tool cwd and must not move a run |
| OpenCode | Session directory at registration | No native same-session move is supported |

The freshest-record rule of ADR 0009 continues to decide where a session is
for `work start`, `work show` and occupancy. Designated evidence only decides
what may carry a run.

### Live Relocation

A Live Relocation is a same-identity live location change: the session keeps
its native identity and Host Process and continues at another Worktree of the
same Repository with no `SessionEnd`, no `SessionStart`, and no Relocation
Intent. It is a route beside ADR 0029, not a replacement. The measured
triggers are a controller's Codex `turn/start` with a `cwd` override and a
Claude Code `EnterWorktree` or `ExitWorktree` with `action: keep`.
`ExitWorktree` with `remove` deletes the Worktree it leaves, and would take
that Worktree's Work Store with it, possibly before its `PostToolUse` runs;
its hook order is unmeasured, and it gains no carry until #162 measures it.

When the hook publisher writes a record H for session S at Worktree B, it
carries S's active Agent Run from Worktree A to B, preserving the Work Store
session key, `run_id`, `startedAt` and Issue Binding and adopting B's `cwd` and
Branch, only when every condition holds:

1. **Identity.** The run's recorded identity is H's `(harness, native session
   ID)`; an unresolved legacy run never qualifies.
2. **Same Host Process.** H's Host Process key equals the run's recorded key.
   A missing or unobservable key on either side refuses.
3. **Designated evidence.** H's event is the harness's designated location
   evidence and is session-scoped; it is not `SessionStart`, `SessionEnd` or a
   child-scoped event.
4. **Same Repository.** B is a different Worktree, main or linked, that
   `git worktree list` reports for A's Repository.
5. **Freshest, from the origin.** Under the session's hook-store locks, H is
   the identity's freshest record, and the freshest record outside B is at A,
   from the same Host Process, and not ended.
6. **Same incarnation.** B's store has seen no `SessionStart` for S after that
   origin record's `lastActivityAt` (the `lastSessionStartAt` stamp, Q6). A
   cold resume that reached B through a new incarnation is a restart and goes
   through ADR 0029 or ADR 0053, never here.
7. **No competing run.** B holds no other run for S under a different key.
8. **Intent.** A pending Relocation Intent whose target is exactly B is
   completed and cleared by the carry. An intent naming any other target
   blocks the carry, and the pending intent's existing Diagnostic reports it.
   While S's record at A is still live, that Diagnostic is today's
   `work-relocation-concurrent`, which counts every live record rather than
   the freshest and advises exiting the old client; #161 reads the freshest
   record there so that a Live Relocation to the wrong Worktree reports
   `work-relocation-mismatched` instead.

The carry reuses `WorkStore.complete_relocation`: both records locked in path
order, B written durably before A is compare-deleted. A crash between the two
leaves the same run, with the same session key and `run_id`, at both; the
next Live Relocation step for S finds that pair and compare-deletes A's copy,
and until then the existing `work-session-conflict` Diagnostic shows both. An
unbound session is never given a run.

Reconciliation order in the publisher becomes: an ended event ends work
before its record is written; otherwise, after the write, declared
completion (ADR 0029), then Live Relocation, then orphan continuation
(ADR 0053). At most one applies to one event. A carry is reported as the
existing `relocated` Work Store change, so no Runtime Event field changes.
Today's publisher tries relocation and continuation on the same event;
running at most one is a deliberate change for #161.

When a carry is refused while S's freshest record is at B and its run is at A,
observation reports a new warning Diagnostic, `work-session-elsewhere`: the
run is at A, the session is executing at B, and the recovery is `dashpot work
start` at B (which switches the run under ADR 0009 with a new `startedAt`) or
`dashpot work stop`. Because condition 6 holds across later events, a carry
refused for a transient reason (a lock, an unreadable store) is retried on the
next designated event at B: for Codex the session's next turn, for Claude
Code only its next worktree-tool call, so a refused Claude carry usually ends
in `work start` at B.

The record S left at A stays until S ends. While S is live at B, the
freshest-record rule already places S at B for `work start`, `work show` and
Cleanup occupancy, so the older record at A neither occupies A nor confirms a
command there. What must not happen is for that record to outlive S: after a
Codex Live Relocation the daemon stays alive, so when S's `SessionEnd` at B
removed only B's record, the record at A would become S's freshest, read live,
and occupy A until the daemon exits. The publisher therefore handles a
`SessionEnd` by also removing S's records at the Repository's other
Worktrees, under the session's hook-store locks and after `end_session_work`
has reconciled the Work Store, but only records that:

- carry S's own `(harness, native session ID)`;
- name the Host Process the `SessionEnd` event itself was observed from, not
  the process a run records, so a `SessionEnd` published by another process
  for S's id (the refused `2.1.285` `claude -p --resume`) removes nothing;
- have an observed Host Process key, as the event does: when either key is
  missing or unobservable nothing is removed, unlike today's same-store
  write, which treats two missing keys as a match;
- are not newer than the `SessionEnd` by `lastActivityAt`, so a record
  written after it, such as the target's `SessionStart` about 100 ms after the
  origin's `SessionEnd` in ADR 0029's daemon cold resume, is kept.

No other session's record is touched, even when it shares the Host
Process. [ADR 0069](../adr/0069-remove-an-ended-sessions-records-from-every-store-of-its-repository.md)
counts the global store among those Worktrees' stores, and
[ADR 0070](../adr/0070-refuse-a-live-relocation-on-evidence-it-cannot-read.md)
refuses a carry on any of the session's evidence that cannot be read. ADR 0029's confirmation
is unchanged: it sees S's record at A as a live claimant until S ends, which
is the same guard it applies today.

### Mid-turn moves and tool cwd

A Codex `turn/start` issued while a turn runs joins that turn and executes in
the old directory while `thread/read` already reports the new one. Observation
follows execution: the carry happens only at the next session-scoped
`UserPromptSubmit` at B. Whether the joined input publishes a
`UserPromptSubmit` of its own, and at which `cwd`, is unmeasured; #161 measures
it before a mid-turn move is claimed. A late `Stop` from the old turn is not
designated evidence and cannot move the run back, but it does place the
session at A again under the freshest-record rule until S's next designated
event; that is one reason a mid-turn move stays unsupported until measured.
#148's preflight requires an idle session, so its controller turn is itself
the designated evidence.

### What #148 verifies from this seam alone

After a controller move of session S from A to B, #148 needs no
harness-specific location logic. It reads:

- S's freshest session-scoped record is at B, from the same identity and Host
  Process;
- if S had a run, that run is at B with unchanged `run_id`, `startedAt` and
  Issue Binding, and no record of it remains at A;
- S's freshest record is not at A, so A's occupancy no longer names S;
- if S had no run, no Work Store record was created.

The opt-in question of #148 step 1 (what counts as an opted-in Codex thread:
a terminal Dashpot launched, an Issue Binding at the Worktree, or an explicit
in-session declaration, with the last recommended) is the maintainer's and is
recorded open. The observation contract is the same under all three: Live
Relocation neither requires nor grants authority, and who may trigger a move
stays #148's. If option 3's declaration is spelled as a Relocation Intent,
condition 8 completes it; if it is a separate consent record, the carry
ignores it.

### Effect on ADR 0009

A Claude Code session that holds a run at A and calls `EnterWorktree` or
`ExitWorktree` (`keep`) now has its run carried to where it went, instead of leaving
the run at A for a later `work start` to switch. The Issue-work skill's
handoff after `EnterWorktree` therefore checks `dashpot work show` before
running `work start`, as the Codex resume recipe already does. ADR 0009's
refusal of `work start` where the session is not, and its treatment of a
tool-call `cd` as wrong-location evidence, are unchanged.

## Q6. Evidence interface and persisted changes

Harness-native translation stays at the edge, in the Harness Adapter;
validation and reconciliation stay in shared Python. The interface grows by
the smallest amount the rules above need.

| Seam | Change | Owner |
| --- | --- | --- |
| Harness Adapter | Add a `locates(event) -> bool` predicate naming the designated location evidence (Q5). Keep `is_host_process` (which recognises supervised Claude workers since #326), `claim_session_identity` and `exclusive_session_process` | #161 (Codex, core), #162 (Claude) |
| Child scope | An event carrying `agent_id` (Codex, Claude) or a native `parentID` (OpenCode) is child-scoped; the publisher applies the Q4 rule | #161, #162, #163 |
| Hook record | Add optional `lastSessionStartAt`: set by `SessionStart`, carried from the same store's previous record of the identity like `turnStartedAt`, absent on legacy records. The record stays version 2 | #161 |
| Reconciliation | Add a Live Relocation step beside `complete_session_work_relocation` and `continue_session_work`, reusing `WorkStore.complete_relocation` | #161 core, #278 acceptance |
| `SessionEnd` handling | Also remove the session's records at the Repository's other Worktrees that name the ending event's own observed Host Process and are not newer than it, under the guards in Q5 | #161 |
| Diagnostics | Add `work-session-elsewhere` | #161 |
| Work Store | None; `WorkStoreRecord` stays version 2 and every v1 record stays readable | — |
| Published models and Runtime Events | None; a carry reuses the `relocated` change | — |
| OpenCode publication | Its generation document and sequence watermarks, as proposed in the [OpenCode design](opencode-integration-design.md#track-publisher-lifetime-without-redefining-agent-session) | #163 |

Not built, because no observation consumes it: a heartbeat, an attachment
inventory, a supervisor record, a runtime registry, a generic lifecycle-event
framework, or a controller registry (the controller seam is #148's).

## Q7. Compatibility, stale evidence and recovery

### Reading existing records

- No record is renamed, rekeyed or rewritten by an upgrade or by observation;
  `run_id`, `startedAt`, Issue Binding and any pending Relocation Intent are
  untouched until a route in Q3 acts on the exact run.
- A legacy hook record without `lastSessionStartAt` reads as "no
  `SessionStart` seen at this store", so condition 6 does not refuse a first
  move after upgrade; conditions 2 and 5 still require the same Host Process
  and an origin record.
- A publisher older than this design never carries a run; a newer reader of
  its records degrades to today's ADR 0009 behaviour plus the
  `work-session-elsewhere` Diagnostic.
- Unknown hook-record fields are already tolerated, so an older reader of a
  newer record ignores the new stamp.
- A pending Relocation Intent changes only through ADR 0029's completion, an
  exact-target Live Relocation, a cancellation by its session, or an explicit
  stop.

### Stale-event protection

A route acts only when all of its guards hold at the moment of mutation:

- Identity: the event's `(harness, native session ID)` equals the run's
  (ADR 0038). A shared Host Process never makes two identities one.
- Runtime: `SessionEnd` ends only work from its own Host Process and never
  work started after it; Live Relocation requires the same Host Process;
  continuation requires the recorded one proved gone.
- Evidence kind: only designated location evidence moves a run, so a late
  `Stop`, a tool hook, or a child's event cannot.
- Freshness under lock: the session's hook stores are locked in path order and
  H must be the freshest record; an older event arriving later is not.
- Incarnation: `lastSessionStartAt` separates a live move from a restart.
- Compare-and-replace: every Work Store mutation compares the complete
  expected record under its lock and does nothing when it changed.
- OpenCode: callback order is not guaranteed, so its bridge's sequence
  watermarks order events before they reach the shared rules.
- Hook dispatch per session is sequential for Codex (pinned source) and
  Claude Code (inference from every measured trace); both are re-measured on
  a release (below).

### Failure and recovery

| Failure | Outcome | Recovery |
| --- | --- | --- |
| Crash between writing B and deleting A in a carry | The same run at both; `work-session-conflict` | The next Live Relocation step for the session compare-deletes A's copy |
| Carry refused (a condition failed) | Run stays at A; `work-session-elsewhere` | Automatic retry on the next designated event; else `work start` at B or `work stop` |
| Host Process unknown | No carry, no continuation, no ending by liveness | Wait for observation, or `work stop --session` once proved gone |
| Lost `SessionEnd` | Run stays; orphaned once the process is gone | ADR 0053 (Claude), `work start` (Codex, OpenCode), or `work stop --session` |
| OpenCode lost disposal with a live backend | No automatic takeover | Operator backend restart, then `work start` |

## Scenario matrix

Each cell names its evidence class: **measured** (an isolated experiment on
the stated release), **source** (pinned source or current documentation),
**inference**, or **unresolved**.

| Scenario | Codex | Claude Code | OpenCode |
| --- | --- | --- | --- |
| Several conversations on one Host Process | Measured: app-server and daemon host many threads; `exec` is one per thread | Measured: one per headless process and per worker; Remote Control server unresolved | Measured: many sessions per backend |
| Hook id equals shell claim | Measured for roots and forks; a sub-agent's shell claims its own id | Measured headless and background; interactive inferred from the `2.1.278` channel environment | Measured for legacy Bash; a PTY can lack it |
| Client detach | Measured: no hook, execution continues | Measured: killed `attach` terminal, no hook | Measured: attached CLI exit does not stop work |
| Idle unload or eviction | Measured: `SessionEnd` 60 s after the last unsubscribe; source documents 30 min | Unresolved: documented about an hour, hook delivery unmeasured | Not applicable |
| Graceful exit | Measured: `exec`, SIGTERM, daemon stop, standalone `/exit`; daemon-hosted `/exit` none until unload | Measured: `/exit`, `claude stop`, headless exit, `daemon stop --any` | Measured: only `session.deleted` ends; backend exit does not |
| Crash | Measured: SIGKILL publishes nothing | Measured: SIGKILL publishes nothing; supervisor respawns with `resume` | Measured: backend exit publishes nothing |
| Same identity in a new Host Process | Measured: `resume` from a replacement server or `exec resume` | Measured: `resume` and `respawn` | Measured: resumed in a replacement backend |
| Supervisor replacement | Not applicable | Measured: workers keep pids, no hooks | Not applicable |
| Conversation switch in one process | Source: `/cd` forks a new thread | Source: `SessionEnd` reasons `clear` and `resume` | Unresolved |
| Fork | Measured: new id, `source` = `fork`, no parent field | Measured: new id, `source` = `fork`, no parent field | Measured: new id, no `parentID` |
| Delegated child | Measured: root `session_id` plus `agent_id` | Measured: parent's id and pid plus `agent_id`; parent's cwd except isolated worktree ([measured under #279](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)) | Measured: own id with `parentID` |
| Live location change, idle | Measured: `turn/start` `cwd` override sticky, same id, no `SessionStart` | Measured: `EnterWorktree` and `ExitWorktree` (`keep`) `PostToolUse` at the new cwd, same id and pid; `remove` unresolved | Unresolved; Bash `workdir` measured not to move the session |
| Live location change, mid-turn | Measured: joins the running turn in the old cwd; joined input's hooks unresolved | Unresolved | Unsupported |
| Declared sequential relocation | Measured on no-daemon, loaded and unloaded daemon routes | Not used | Unsupported |
| Sub-agent during a move | Unresolved | Unresolved | Unresolved |
| Terminal launched before the daemon; daemon autostart | Unresolved | Not applicable | Not applicable |
| Remote Control | Unresolved (pairing) | Unresolved (attachment and server) | Not applicable |
| Event ordering | Source: hooks dispatched from one core `Session` | Inference from measured traces | Measured: callback order not guaranteed |

## Support matrix

The first local support boundary. Anything not listed is unsupported. A mode
marked unsupported or unmeasured gains support only through a measurement
under its implementing Issue, never by assumption.

| Harness and mode | Status | Notes |
| --- | --- | --- |
| Codex standalone TUI | Supported today; lifecycle through #161 | Continuation not offered until #161 measures exclusivity |
| Codex `exec` | Supported today | Measured |
| Codex shared local App Server (`app-server --listen` with `--remote` clients) | First slice, #161 | Measured at `0.155.1` |
| Codex managed daemon with plain or `--remote` terminals | First slice, #161 | Measured at `0.155.1` |
| Codex Live Relocation by a controller | #161 core, #278 acceptance, triggered only by #148 | Idle only until the mid-turn row is measured |
| Codex terminal launched before the daemon; daemon autostart | Unsupported until #161 measures | Recorded on #161's acceptance matrix |
| Codex `/cd`, managed `/worktree` | `/cd` is a new Agent Session (source); `/worktree` unsupported | Neither preserves a run |
| Codex Remote Control pairing, Code Mode remote host, stdio transport, other operating systems | Unsupported | Unmeasured |
| Claude Code interactive and headless | Supported today; lifecycle through #162 | Measured |
| Claude Code supervised workers (`--bg`), including claimed spares | Recognised as Host Processes since #326 (Linux, `2.1.285`); lifecycle through #162 | A worker replaced after an abrupt exit continues its run under ADR 0053 (measured with the `--resume` shape); `claude stop` publishes its own `SessionEnd` and ends the run, so a later `claude respawn` has no run to continue; a respawn or spare replacement after an abrupt exit is unmeasured; macOS unmeasured |
| Claude Code `EnterWorktree`/`ExitWorktree` (`keep`) Live Relocation | #162, #278 acceptance | One-sided reach as measured at `2.1.278`; `ExitWorktree` with `remove` unsupported until measured |
| Claude Code idle eviction | Unresolved; #162 measures | Until then an evicted worker's run is treated by the transition table's measured rows only |
| Claude Code Remote Control (attachment and server), SDK, agent teams, cloud, desktop | Unsupported | Unmeasured; server mode needs a claude.ai login |
| OpenCode legacy local TUI | Later slice, #163 | TUI startup and exit unmeasured |
| OpenCode attached or shared local backend | Later slice, #163 | Measured on the legacy plugin path |
| OpenCode V2, ACP, SDK-owned server, remote backends, live cross-Worktree move | Unsupported | Unmeasured |

## Worked examples

### Two OpenCode sessions sharing one backend

Backend P (pid 4100) serves sessions `ses_a` and `ses_b`. `ses_a` runs
`work start 12` at Worktree W12 and `ses_b` runs `work start 13` at W13; each
Work Store record carries its own identity and P's key.

- `ses_a` is busy and `ses_b` idle: each record shows its own state; neither
  borrows the other's activity.
- `ses_b` is deleted: `session.deleted` ends exactly `ses_b`'s run; `ses_a`'s
  binding is untouched.
- The CLI attached to `ses_a` exits: nothing changes.
- P is killed: both sessions read gone and both runs are orphaned. A
  replacement backend resumes `ses_a`; it is observed again, but its run is
  not continued. After P is proved gone, `ses_a` runs `work start 12`, which
  replaces the orphaned record with a new run and a new `startedAt`.

### Two Codex threads on one App Server

Daemon D (pid 5200) hosts thread `T1` from a terminal at W1 (run for Issue 21)
and thread `T2` at W2 (run for Issue 22). Both runs record D's key.

- The W1 terminal types `/exit`: no hook. `T1` stays live and its run stays.
  About 60 s after its last unsubscribe, `SessionEnd` for `T1` ends only
  `T1`'s run, because `T2`'s identity differs.
- A controller authorized by #148 starts a turn on idle `T2` with `cwd` = W3.
  Its `UserPromptSubmit` at W3 comes from D, is session-scoped, and follows
  `T2`'s record at W2: Live Relocation carries the run for Issue 22 to W3
  with its `run_id` and `startedAt`. `T2`'s older record at W2 stays until
  `T2` ends, when its `SessionEnd` removes it with the rest.
- `T2` spawns a sub-agent at W3: its hooks carry `T2` plus `agent_id`, add
  one live delegate to `T2`'s record, and never place or bind anything.
- D is killed: no hook. Both threads read gone; any remaining run is orphaned.
  A resume in a new daemon is not continued (shared Host Process); the session
  runs `work start`.

### Two Claude Code workers under one supervisor

Supervisor S hosts worker `w1` (pid 6100, session `s1`, run for Issue 31 at
W31) and `w2` (pid 6200, session `s2`, run for Issue 32 at W32).

- `claude stop s2`: `SessionEnd` `other` from pid 6200 ends `s2`'s run. `s1`
  is untouched.
- `w1` is killed and the supervisor replaces it with pid 6300, a
  `--resume` worker: `SessionStart` `resume` for `s1` from 6300 at W31. Pid
  6100 is gone and Claude's Host Process is exclusive, so ADR 0053 continues
  the run with its `startedAt` and binding.
- Had `s1` been stopped with `claude stop` instead, its own `SessionEnd`
  would have ended the run, and a later `claude respawn` would resume `s1`
  with no run to continue.
- `s1` calls `EnterWorktree` into W33: the `PostToolUse` at W33 is
  designated, from 6300, and follows `s1`'s record at W31, so Live
  Relocation carries the run to W33.

Both continuing outcomes rely on #326's recognition of the supervised worker
as the Host Process, measured on Linux at `2.1.285`.

### Supervisor replacement with unchanged workers

`claude daemon stop --any --keep-workers`, then the next `claude --bg` starts
supervisor S′. No hook fires; `w1` and `w2` keep their pids, sessions,
records and runs; a turn begun under S finishes under S′ with its ordinary
`Stop`. Nothing in Dashpot observes the change, and nothing needs to: the
supervisor is not a recorded fact, and its replacement is never a reason to
run `work start`.

## Re-measure on a harness release

The identity equalities and hook shapes are per-release measurements, and the
pinned runners under `scripts/experiments/` are the only revalidation
mechanism. On a new supported release, rerun the matching runner and confirm:

- **Codex** (`codex-160`, `codex-269`, `codex-148`): hook `session_id` =
  `thread.id` = `CODEX_THREAD_ID` = `CODEX_SESSION_ID` for roots and forks;
  a sub-agent's root `session_id` plus `agent_id` and its child shell claim;
  `UserPromptSubmit` `cwd` after a `turn/start` override; the unload delay and
  its `SessionEnd`; no hook on SIGKILL; `SessionEnd` at the old cwd before
  `SessionStart` at the new on a cold resume; `SubagentStart`/`SubagentStop`.
- **Claude Code** (`claude-160`, `claude-148`, `claude-326`, `claude-345`,
  `claude-279`): hook `session_id` = `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID` =
  the worker pid; supervised worker and spare process names and argv;
  `PostToolUse` `cwd` after `EnterWorktree`/`ExitWorktree`; no `CwdChanged` for
  those tools; `SessionEnd` reasons for stop, exit and supervisor stop;
  `SessionStart` `resume` after respawn; sub-agent hook `cwd` and `agent_id`.
- **OpenCode** (`opencode-151`): shared backend pid; `parentID` on children
  and not on forks; `session.deleted` as the only ended evidence; plugin
  disposal ordering.

A changed equality is a support regression: the affected mode is unsupported
until the design or an ADR accounts for it.

## Work for each consumer

- **#161 (Codex and the shared core).** Add the adapter's `locates`
  predicate, the child-scope rule and seeding (fixing the parent-location
  overwrite), `lastSessionStartAt`, the Live Relocation step in the order
  above, the guarded `SessionEnd` removal of the session's older records
  elsewhere (Q5), and `work-session-elsewhere`. Subscribe
  Codex `SubagentStart`/`SubagentStop`. Keep `exclusive_session_process`
  false for Codex unless it measures a standalone TUI's exclusivity, and
  measure the terminal-before-daemon, daemon-autostart and mid-turn joined
  input rows. Mark ADR 0067 accepted with its consequences, amending ADR
  0009, ADR 0016 and ADR 0029 as that ADR lists.
- **#162 (Claude Code).** Designate the worktree-tool `PostToolUse` events,
  apply the child-scope rule to Claude sub-agents (including the isolated
  worktree case), carry supervised workers (recognised since #326) through
  Live Relocation, measure idle eviction and a respawn after an abrupt exit,
  and change the Issue-work skill to check `work show` after `EnterWorktree`.
- **#163 (OpenCode).** Translate `parentID` children, `session.deleted` and
  generation retirement into the shared rules; keep explicit `work start`
  after a backend restart; leave live relocation unsupported.
- **#278.** Accept the Live Relocation route through public seams with a
  fake Host Process and hook boundary: carry with `run_id`, `startedAt` and
  binding unchanged; unbound stays unbound; late evidence from A does not move
  the run back; ADR 0029 unchanged.
- **#148.** Decide the opt-in (step 1), build the controller and Cleanup flow,
  and verify each handoff through the seam in Q5 only.

## Open questions

- #148 step 1: which Codex threads count as opted in (options 1, 2 or 3).
- Claude Code idle eviction: whether it publishes `SessionEnd`.
- Codex standalone TUI exclusivity, a terminal launched before the daemon,
  daemon autostart, and the hooks of input joined to a running turn.
- A sub-agent live during a move, on every harness.
- Claude Code Remote Control in both modes, the SDK, agent teams, the desktop
  app; Codex Remote Control pairing and the Code Mode host; OpenCode local TUI
  startup and exit, V2 and ACP.
- A Claude session whose persistent shell `cd` inside the project enters a
  nested Worktree: its ordinary hooks then place it there under today's
  freshest-record rule, although no worktree tool ran. This design only keeps
  such a move from carrying a run; whether it should place the session at all
  is left to #162.
