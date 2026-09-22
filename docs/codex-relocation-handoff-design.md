---
status: proposal
date: 2026-09-13
---

# Codex relocation and handoff design

Investigation and recommendation for
[Issue #157](https://github.com/ned2/dashpot/issues/157): how a Codex Agent
Session should move between linked Worktrees, and which of the candidate paths
warrant implementation. Related Issues:
[#148](https://github.com/ned2/dashpot/issues/148) (Cleanup handoff),
[#160](https://github.com/ned2/dashpot/issues/160) (shared runtime contract),
and [#161](https://github.com/ned2/dashpot/issues/161) (Codex slice). Reusable upstream facts live in the
[harness reference](agent-harness-server-client-reference.md); this document
holds only Dashpot's constraints, the comparison, and the decision proposal.
It changes no accepted ADR, no domain language, and no lifecycle rule. The
existing exit-and-resume path remains the baseline until a follow-up delivers
and verifies an alternative.

## Evidence boundary

Every upstream claim below is static reading of the pinned `rust-v0.154.0`
source (the installed and current stable release on 2026-09-13) and of merged
`main` pull requests through `rust-v0.155.0-alpha.3.10`, cited from the
reference. The one runtime fact is older Dashpot evidence: sequential resume
on Codex `0.153.4` was measured live for
[Issue #58](https://github.com/ned2/dashpot/issues/58) and underlies ADR 0029.
No disposable Codex session, app-server, or lock was exercised here:
runtime verification needs Codex credentials and a `CODEX_HOME`, and the only
ones available were the operator's, which the Issue excludes. Hook ordering is
therefore a call-graph result, not a timed measurement. The verification table
at the end marks each point as source-verified or unverified.

## Two separate constraints

The workflow instructions conflated an upstream limitation with a Dashpot
requirement. They are different, and the correction keeps them apart.

**Upstream limitation.** Release the old Codex runtime before continuing the
same Agent Session through `codex resume <session-id> -C <path>`. A competing
client may open read-only, but cannot continue the session while another
runtime owns it. Ownership is a per-thread advisory lock under `CODEX_HOME`,
held from `Session` construction until thread shutdown or process exit, and it
persists while the owner is idle. There is no upstream rule that the competing
client may not be launched first.

**Dashpot requirement.** A declared relocation completes only from a hook of
the same Agent Session Identity at the intended target, when no hook record
places a live or unobservable client with that identity elsewhere, and exactly
one pending Relocation Intent names that target
([ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md),
[ADR 0038](adr/0038-isolate-native-agent-session-identities.md)). Dashpot needs
the old client's `SessionEnd`, or a proven-gone old process, before it moves
the Agent Run. It does not need the old client to have exited before the new
one was launched; it needs evidence, in order.

The two agree in practice because of where Codex runs hooks. A read-only client
has no core `Session`, so it runs no `SessionStart`, `UserPromptSubmit`, or
`SessionEnd` and publishes no location. The owning client's `SessionEnd` is
awaited inside its shutdown handler before the live thread releases the lock.
The first hook at the target is therefore the resumed session's first turn,
after the old client's `SessionEnd` has already reconciled the Work Store. One
qualification: shutdown timeouts can let the old process exit with the hook
unfinished, and an abrupt kill runs no hook at all; the lock then goes with
the process (inferred from advisory-lock semantics, not asserted by a test),
and ADR 0029's proven-gone rule already covers that record. The Dashpot
ordering that ADR 0029 relies on is preserved without any new guard.

## Candidate comparison

| Criterion | 1. Correct wording, keep sequential resume | 2. Open target read-only, retry after release | 3. `/cd` handoff to a new Agent Session | 4. Shared-runtime controller |
| --- | --- | --- | --- | --- |
| Human interventions | Exit old client; run resume command; submit turn | Same count; the resume command can be pasted before the exit and `R` replaces re-running it | Run `/cd <path>` in the live TUI; submit turn | None for the move once opted in; the arrangement itself must be set up |
| Conversation history | Same rollout, verbatim | Same rollout, verbatim | Copied into a new rollout; visible to the model | Same thread |
| Agent Session Identity | Preserved | Preserved | New thread ID, new hook `session_id` | Preserved |
| Agent Run and Issue Binding | Preserved through Relocation Intent | Preserved through Relocation Intent | Cannot be preserved; old run ends, new session declares `work start` | Not preservable today: the origin hook record stays live under the same process, so completion refuses |
| Hooks needed | Existing five | Existing five | Existing five; `fork` source arrives after `0.154.0` | Existing hooks fire from core with the overridden cwd; a controller evidence seam does not exist |
| Ownership and concurrency | Lock refuses a second writer | Lock refuses; read-only client is passive | Old thread stays loaded until unload delay or exit; both IDs share one process | Daemon holds the lock; overrides need `turn/start`, not `thread/resume` |
| Recovery after interruption | Pending intent stays visible; cancel at origin or explicit stop | Same; an abandoned read-only client leaves no evidence | Old run ends at old thread's `SessionEnd`; nothing pending | Unspecified until a controller contract exists |
| Supported versions | `0.153.4` measured live for #58, `0.154.0` source | `0.154.0` (PR #43253) and later | `0.154.0` for `/cd`; `/worktree` experimental and cannot enter an existing Worktree | App-server protocol at `0.154.0`; managed daemon behavior changing on `main` |
| Implementation complexity | Documentation only | Documentation only | Documentation now; optional diagnostics later | New evidence model, controller registration, completion contract; depends on #160 and #161 |

### Candidate 1: correct the explanation

The dispatch instructions said the old client must exit before the resumed
client starts. That overstated Codex; the accurate statement is the upstream
limitation above, with Dashpot's evidence requirement stated separately. This
correction is delivered with this document: the bundled skill's dispatch and
recovery references, [agent sessions](agent-sessions.md#agent-facing-issue-work-skill),
and [AGENTS.md](../AGENTS.md#issue-work-lifecycle). ADR 0029, the README, and
the domain language already describe Dashpot's requirement in evidence terms
and need no change.

### Candidate 2: open read-only, retry after release

Accepted as a documented option, not a new rule. Because the read-only client
publishes nothing, launching it early cannot mislead `work start`, `work
relocate`, or `_sequential_target_is_confirmed`; the freshest hook record for
the session remains the owning client's until its `SessionEnd`. The retry key
performs a fresh `thread/resume`, and the positional prompt survives as a
draft, so the handed-over instruction still runs `work show` first. The gain is
modest: one fewer command to re-run, and a visible confirmation that the old
client has released the thread. It needs no Dashpot code. Two caveats belong in
the skill text and are there: ownership persists while the old client is
idle, so only exit releases it; and the first hook at the target is the first
turn, so `work show` must run inside that turn, which the handed-over prompt
already does.

Where the old client is attached to a managed daemon rather than running its
own embedded server, exiting the TUI only unsubscribes; the daemon keeps the
thread loaded until its unload delay elapses (sixty seconds by code default at
`0.154.0`, documented as thirty minutes). This paragraph first inferred that a
resume inside that window would stay read-only until the unload; the
[declared-relocation experiment](codex-declared-relocation-daemon-spike.md#scenario-results)
of 2026-09-20 measured otherwise on `0.155.1`. A `codex resume <id> -C <path>`
launched 98 ms after the old terminal's `/exit` is hosted in the daemon and
takes the cold-resume path, because the exited terminal was the thread's only
subscriber: the daemon runs `SessionEnd` `other` at the old Worktree, then
`SessionStart` `resume` at the new one, under the same thread id, with no
read-only notice and no later `SessionEnd`. Dashpot's evidence order is
therefore the same on every route, and the only wait the retry key covers is
an old terminal that has not yet exited.

### Candidate 3: `/cd` as an explicit handoff to a new Agent Session

Feasible as a user-selected alternative to the fresh-session fallback, and
more useful than that fallback because the model keeps its context. It is not
relocation. `/cd` forks the thread: the new thread has its own ID, hook
`session_id`, and `CODEX_THREAD_ID`; its `SessionStart` reports `startup` and
carries no parent field; the old thread's `SessionEnd` arrives after the
unload delay or at client exit, from the same host process. Under ADR 0038 the
two IDs are distinct sessions on one backend and never match by process, so
observation already handles the pair correctly: the old session ends when its
`SessionEnd` arrives, and the new one starts unbound.

An honest workflow is: the old session runs `work stop` (its own run) before
`/cd`, then the new session runs `work start` and `work show` at the target.
If `work stop` is skipped, the old run ends at the old thread's `SessionEnd`,
which is the existing undeclared-end behavior, and the run shows as waiting
for up to the unload delay. Nothing may infer continuity: Dashpot must not
carry an Issue Binding to the forked ID from history, the destination path, or
the `forked_from_thread_id` in Codex's store. `/worktree` does not apply: it
creates a managed detached checkout and cannot enter a prepared Issue
Worktree. `/cd` is blocked while background terminals, queued input, a running
turn, or a side agent exist, and post-`0.154.0` changes gate it on the local
daemon's capabilities; those are user-facing limits, not Dashpot concerns.

Once a stable release includes the `fork` `SessionStart` source, a diagnostic
that labels the new session as forked would help a person read the pair; it
still could not link the IDs, because the payload carries no parent. That is
an optional follow-up, not part of this recommendation.

### Candidate 4: shared-runtime controller

Conditional. The protocol supports the move itself: a client subscribed to a
daemon-hosted thread may start a turn with a `cwd` override, the override
becomes the thread's sticky environment, and every later hook reports the new
cwd under the same `session_id`. Sibling threads are held in maps keyed by
thread ID and each request resolves its own thread, so a controller acting on
one thread has no protocol path to another. `thread/resume` overrides are
ignored while any subscriber remains, so the controller must use `turn/start`.

What Dashpot cannot do today is complete such a move. The origin hook record
for that session stays live because the daemon process is unchanged; the
declared-relocation completion refuses while a live same-identity record sits
elsewhere, and it requires a Relocation Intent that only the session's own
shell can declare. Accepting a same-process cwd change as relocation is the
Claude Code `EnterWorktree` shape, and it would need a new completion rule
plus a registered, authenticated controller seam. Those belong to the shared
runtime contract in #160 and its Codex slice in #161. A standalone TUI thread
is outside this candidate entirely: its embedded app-server holds the lock, it
exposes no listener, and no external client can start a turn in it.

The exact scenario #160 must verify before this candidate can be decided: one
daemon hosting two root threads in different Worktrees, with a TUI attached to
thread A; a second client subscribes to A and starts a turn with `cwd` set to
another linked Worktree; observe A's `UserPromptSubmit`, `Stop`, and later
`SessionEnd` payloads for `session_id` and `cwd`, the attached TUI's behavior,
B's hooks for any change, and the origin and target hook stores afterwards.
Until that is measured, this document records Candidate 4 as unverified.

## Recommendation

1. Apply Candidate 1 now, and document Candidate 2 as the same path with a
   relaxed launch order. Both are wording changes and are in this change.
2. Offer Candidate 3 as a disclosed user-selected handoff in the skill's
   Codex fallback, in a follow-up that changes the fresh-session fallback
   block of `dispatch.md`, the Codex path sentence in
   [agent sessions](agent-sessions.md#agent-facing-issue-work-skill), and the
   dispatch assertions in `tests/test_integrate.py`. It is a new Agent Session
   by construction; the guidance must say so and must require explicit
   `work stop` and `work start`.
3. Do not implement Candidate 4 here. Feed the scenario above to #160, and
   treat any same-process relocation completion as #161 scope with its own
   ADR.
4. Keep every ADR 0029 guard. Nothing found weakens the case for declared
   intent, target hook evidence, or the refusal of live or unobservable old
   clients.

## Documentation changes, ADR changes, executable changes

Documentation applied in this change:

- `src/dashpot/skills/dashpot-issue-work/references/dispatch.md`: the Codex
  resume section states the upstream limitation and Dashpot's requirement
  separately, and step 5 describes the read-only client and `R`.
- `src/dashpot/skills/dashpot-issue-work/references/recovery.md`: failed
  resume names the read-only state and the retry.
- `docs/agent-sessions.md` and `AGENTS.md`: relocation sentences describe
  release rather than launch order.
- `docs/agent-harness-server-client-reference.md`: thread ownership, `/cd`
  and `/worktree`, loaded-thread overrides and unload, root identity mapping,
  and post-release changes on `main`.

Documentation deferred to follow-ups: the Candidate 3 handoff text in the
dispatch reference; a `fork`-source note once a stable release ships it; the
#148 feasibility-gate wording, which lives in that Issue's "Harness
feasibility gate" section and is updated there, while the dated
[Cleanup session handoff research](cleanup-session-handoff-research.md) stays
as it was written.

ADR and domain-language changes: none qualify now. ADR 0029 already states
completion in evidence terms. A future Candidate 4 completion rule would amend
ADR 0029 and ADR 0038 and add a term for the controller arrangement; a
Candidate 3 diagnostic would not.

Executable lifecycle changes: none in this change. Candidates 1 and 2 need
none. Candidate 3 needs none for correctness; an optional diagnostic is
follow-up scope. Candidate 4 needs the #160 and #161 work.

## Verification evidence for the recommended path

| Point | Status | Evidence |
| --- | --- | --- |
| Native identity | Source-verified | Hook `session_id` equals the thread ID for root threads and survives resume; a fork gets its own ID ([reference](agent-harness-server-client-reference.md#transport-execution-host-and-identity-boundaries)) |
| Runtime ownership | Source-verified | Per-thread advisory lock held through idle, released at shutdown or process exit; regression tests at `thread_resume.rs` ([reference](agent-harness-server-client-reference.md#thread-ownership-and-competing-resume)) |
| Hook ordering | Source-verified by call graph; timed at `0.155.1` on 2026-09-20 | Read-only client runs no hooks; `SessionEnd` awaited before lock release; target `SessionStart` on first turn. Measured origin `SessionEnd` before target `SessionStart` `resume` on the no-daemon, daemon-loaded, and daemon-unloaded routes ([declared-relocation experiment](codex-declared-relocation-daemon-spike.md#scenario-results)) |
| Authoritative location | Source-verified | `-C` overrides the stored cwd on resume and hooks report `turn_context.cwd`; a read-only client publishes nothing |
| Interrupted handoff | Inferred, unverified | Lock release on abrupt kill follows advisory-lock semantics and the stale-file sweep, with no test asserting it; graceful shutdown awaits `SessionEnd` but has a ten-second bound; Dashpot's proven-gone rule and pending-intent Diagnostic cover both (ADR 0029) |
| Sibling isolation on one backend | Source-verified for structure, unverified at runtime | Per-thread maps and per-request thread resolution; ADR 0038 isolates identities; no live two-thread measurement |
| Live disposable session | Measured at `0.155.1` on 2026-09-20 | An isolated `CODEX_HOME` with a loopback model needs no credentials; the sequential resume relocated the thread on all three hosting routes ([declared-relocation experiment](codex-declared-relocation-daemon-spike.md)). The `0.153.4` live measurement for [Issue #58](https://github.com/ned2/dashpot/issues/58) was the earlier runtime evidence |

## Effect on #148

The Codex feasibility gate narrows rather than opens.

- The gate's sequential-resume bullet should read "release before continuing",
  matching this document; the requirement to verify the old client's exit
  before accepting the destination continuation stands, because it is
  Dashpot's evidence rule rather than Codex's launch rule.
- A standalone TUI thread has no control surface: its embedded server holds
  the writer lock and listens nowhere. The read-only fallback lets a person
  relaunch, which is the copy-and-paste handoff #148 excludes. Such occupants
  stay blocked.
- Only a daemon-hosted thread is a candidate for controller handoff, through
  `turn/start` with a `cwd` override by a registered, verified controller, and
  only after #160 measures the two-thread scenario above and #161 supplies a
  same-process completion rule. The disposable acceptance matrix gains that
  row and should drop any expectation of relocating a standalone TUI thread.
- `/cd` cannot serve #148: it is human-only and creates a new Agent Session,
  so it neither preserves the Agent Run nor can be driven by Cleanup.

No claim is made that #148 can relocate arbitrary observed sessions.

## Open questions and dependencies

Updated 2026-09-20. The
[Cleanup handoff feasibility experiment](cleanup-session-handoff-feasibility-spike.md#scenario-results-codex)
answered the daemon two-thread `turn/start` scenario, the unload timing, and
the controller-turn hook points on `0.155.1`, and the
[declared-relocation experiment](codex-declared-relocation-daemon-spike.md)
answered the question those findings raised about this document's baseline:
the sequential resume relocates a daemon-hosted thread correctly whether the
thread is still loaded or already unloaded, with origin `SessionEnd` before
target `SessionStart`. What remains:

- #148 and #261: Candidate 4 is measured feasible as a live-thread
  relocation by `turn/start` with a `cwd` override on an idle, opted-in
  thread, a separate lifecycle contract beside ADR 0029, not a replacement
  for it. Its completion rule and controller evidence seam are those Issues'
  scope; the sequential route needs no new completion meaning.
- Upstream: the `fork` `SessionStart` source, default-enabled worktrees, and
  the `/cd` daemon-capability gate were on `main` at the time of writing;
  revalidate against the shipped `0.155.x` behaviour. The documentation's
  thirty-minute unload disagrees with the measured sixty seconds.
- Unmeasured on the sequential route: a resume launched while the old
  terminal is still attached, an interrupted handoff (abrupt kill of the old
  client), a Codex `--remote` resume, and a terminal started before the
  daemon; the table above marks the interrupted handoff inferred.
