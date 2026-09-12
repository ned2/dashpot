---
status: research
date: 2026-09-12
---

# OpenCode identity and lifecycle experiment

The experiment for [Issue #151](https://github.com/ned2/dashpot/issues/151)
confirms command-scoped Agent Session Identity in OpenCode **1.18.30**:
two conversations execute overlapping shell commands in one backend without
sharing their identity claims. Native session metadata distinguishes session
location from a shell's requested `workdir`.

The lifecycle needs a more careful integration contract. A client can exit
while its command continues; a plugin can disappear while its backend and
conversation remain usable; a conversation can resume in a new backend.
Neither idle nor plugin disposal means the Agent Session has permanently ended.
The existing process-primary matching assumptions cannot represent these cases.

This is evidence and a recommendation for subsequent design, not an accepted
ADR or implemented Harness Adapter. It makes no changes to Dashpot's Work Store,
Issue-work commands, installation, or dashboard.

## Reproduce

The retained experiment uses Node built-ins, an installed OpenCode 1.18.30,
and Git. The runner rejects another OpenCode version. No model credentials or
external model service are needed: a deterministic loopback provider returns
tool calls to the real OpenCode execution loop.

From the assigned Dashpot checkout:

```bash
node scripts/experiments/opencode-151/run.mjs /absolute/path/to/opencode
node scripts/experiments/opencode-151/verify.mjs /tmp/dashpot-opencode-151-SUFFIX/trace.jsonl
```

Replace the second path with the exact fixture path printed by the runner.
The run takes approximately a minute. A sandbox that blocks loopback needs a
command-scoped exception for the runner. The verifier needs no network.

- [Runner and trace receiver](../scripts/experiments/opencode-151/run.mjs)
  create the fixture, serve the mock provider, drive API and CLI clients, inject
  publication delays/failures, and assert observable outcomes.
- [Observation plugin](../scripts/experiments/opencode-151/plugin.mjs) publishes
  metadata and injects the individual command environment. It does not import
  Dashpot or write Project state.
- [Independent trace verifier](../scripts/experiments/opencode-151/verify.mjs)
  checks emitted evidence and command results without importing publisher code.
- [Retained trace](measurements/issue-151-trace.jsonl) contains the complete
  metadata stream from the successful run: 913 records. Its first record includes
  SHA-256 hashes of all three experimental source files.

The runner creates a new `/tmp/dashpot-opencode-151-*` root, an independent Git
Repository with an empty fixture commit, and one linked fixture Worktree. These
are disposable experiment resources, not durable task Worktrees. It supplies an
allowlisted child environment with an isolated home, XDG configuration/data/
cache/state, temporary directory, and `OPENCODE_CONFIG_DIR`. It disables ordinary
Project configuration, external skills, Claude Code configuration, default
plugins, model catalog fetches, and automatic updates. No ordinary configuration,
credentials, Agent Sessions, Git metadata, or sibling Worktrees are copied or
modified. OpenCode bootstraps `@opencode-ai/plugin: 1.18.30` in the isolated
configuration directory; this can require package-registry access on a fresh run.

The runner stops its clients and backend and closes both loopback servers in
`finally`. It retains its fixture for inspection. After copying any desired
trace, remove only the exact printed fixture root, including its own linked
Worktree and ignored OpenCode data. Do not run Git worktree cleanup commands in
the Dashpot Repository. For a run whose artifacts are not needed, prefix the
runner command with `SPIKE_REMOVE_FIXTURE=1`; it deletes only the root that run
created, including when assertions fail. An externally killed runner may require
stopping the exact experiment-owned PIDs printed in its metadata trace before
removing that root.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-09-12 |
| Dashpot base | `8ed8781abc4f357c83024e750edefd2aa54ceb59` |
| OpenCode binary | Installed native binary, `--version` = `1.18.30` |
| Plugin interface | Legacy `Hooks`, `@opencode-ai/plugin` 1.18.30; local `.mjs` plugin |
| Operating system | Linux `7.0.0-30-generic`, x86-64 |
| Controller | Node `v24.18.0` |
| Backend | `opencode serve --hostname 127.0.0.1 --port 0` |
| Clients | Concurrent local HTTP/SSE clients and `opencode run --attach ... --session ...` |
| Provider | Loopback OpenAI-compatible streaming fixture; bundled `@ai-sdk/openai-compatible` path |
| Enabled experimental behavior | `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true` |
| Other flags | Exact isolation flags in trace record 1 and the runner's `env` object |
| Disabled behavior | Snapshotting, sharing, auto-update, LSP, file watching, default plugins |

The real model-driven `bash` tool emitted `tool.before`, `shell.bootstrap` with
a `callID`, and `tool.after`. The observed hook arguments and command result
match the released
[shell implementation](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/tool/shell.ts).
The [release entrypoint](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/script/build.ts)
and [serve command](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/cli/cmd/serve.ts)
explain this path. The separate
[V2 core shell](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/core/src/tool/bash.ts)
still has an environment-augmentation TODO. This experiment does **not** establish
V2 support; it does not invent a V2 flag or infer parity from TypeScript types.
Other releases, operating systems, interactive TUI/desktop clients, and remote
backends remain untested.

Only metadata crosses the experimental observation boundary: event kind/native
ID, session and parent IDs, activity/retry attempt, directories, shell cwd,
process IDs, publisher generation/sequence, timestamps, receiver decisions, and
harmless command identity/cwd results. The mock provider records scenario labels,
request counts and advertised tool names, not messages. Prompt text, transcripts,
provider payloads, general tool output, credentials and full environments are not
retained. OpenCode's own disposable data can contain the synthetic conversation;
it is not part of the retained evidence.

`sourceTime` means entry into the plugin publisher, not an asserted upstream
event-generation timestamp. `receiptTime` and `receipt` order receiver/controller
observations. Native event IDs are retained without interpreting their format.
Publication failures also go to a local metadata diagnostic file; the runner
appends those records at the end, preserving their original source times.

## Scenario results

Trace references below are the `receipt` field, not file line assumptions.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Shared backend | A and B have distinct native IDs. Both commands start before either ends, with correct `opencode:<id>` claims. Plugin PID and command parent PID are the same backend, `1332118`. | `action.sessions` at 8; first two command start/end pairs |
| Independent activity | B becomes idle while A's first command is still running. Later activity remains attributed to its own session ID. | First `session.status` sequences; verifier compares source times with command results |
| Other shell Worktree | A's command cwd is `other-worktree`; hook directory, Worktree context and fetched session directory remain `repository`. A's identity is unchanged. | Bootstrap with `call_location_1`; location readback at 121 |
| SSE detach/reconnect | Closing A's event connection causes no session deletion or plugin disposal in the interval; A can continue. The SSE stream itself is directory-scoped, not an identity authority for A. | 122–133, followed by A's command |
| Attached CLI exit | Client PID `1332640` exits during A's command. That command completes under backend `1332118`; new client PID `1332689` continues A and exits successfully. | Attach/detach/reconnect at 160, 189, 212, 251 |
| Fork | Fork gets a new native ID and command claim. Its `parentID` is absent; the explicit fork action is the recorded origin relationship. | 254 and `call_fork_1` |
| Foreground child | Native task creates a distinct child ID with `parentID=A`. The child shell claims the child ID; A settles after child completion. | Child `session.created`, `call_child_1`, child/parent statuses |
| Background child | Native background task creates a distinct child with `parentID=B`. B becomes idle before the child finishes, then becomes busy again for completion notification. | Second child creation, child command and B's subsequent statuses |
| Retry | One fixture 503 response yields session A's `retry`, attempt 1, then busy and successful completion. The fixture requests a 150 ms retry delay. | `model.request` scenario `retry`; `session.status` with `activity=retry` |
| Interrupt/continue | Abort during A's long command yields idle, including repeated idle observations. The interrupted command has no normal end report; a later prompt executes with A's original ID. | Abort at 527, then `call_resume_1` |
| Missing shell ID | Disposable PTY creation invokes `shell.env` without a session ID. The plugin emits `shell.identity-missing` and injects no identity. | PTY action at 566 and following publication |
| Delayed bootstrap | Init and initial command bootstrap acknowledgments are delayed 100 ms. Each first command finds its session evidence already accepted. | Delay action at 2; arrival `delayMs`, applied receipts, command `evidence=true` |
| Delayed event publication | Concurrent callbacks from two sessions overlap with a 100 ms receiver delay. Accepted publications remain increasing per session/generation. | 575 onward; source/receipt times and verifier |
| Duplicate/stale publication | Replaying an accepted idle and then an older busy yields `accepted=false` for both. | Replay actions at 662 and 665 |
| Unavailable receiver | Connection failure leaves the fresh session's command claim present but `bootstrapAck=false`, `evidence=false`; the prompt completes in 450 ms. | 668–686 and deferred publisher diagnostics |
| Receiver timeout | A 600 ms receiver delay exceeds the 250 ms publication timeout. The fresh session's command runs without corroboration; the prompt completes in 3001 ms. Late publications may subsequently arrive. | 699–724 and diagnostics |
| Disposal/reload | `/instance/dispose` invokes plugin disposal. A later request initializes a new plugin generation at the same PID; A's native ID and directory survive. | 743–748 and `call_reload_1` |
| Retired publisher replay | Replaying an old generation's bootstrap after replacement is rejected by the receiver. | 773 and its matching rejected publication |
| Observation loss/restoration | Removing the plugin using the fixture's `/global/config` API leaves A and its backend usable. A command has no claim; restoring the plugin restores the original claim. | 778–797 and subsequent `call_restored_1` |
| Conversation deletion | Deleting the fork emits `session.deleted` for that fork, without ending A or the backend. | Delete at 830 and matching native event |
| Backend exit/resume | SIGTERM ends the first backend; another backend, PID `1333394`, resumes A with the same directory/ID. SIGKILL then ends that backend. Neither signal exit emitted final plugin disposal for its active generation. | 845–849, `call_restart_1`, exit at 888 |

The fork and child differences agree with the pinned
[session implementation](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/session.ts)
and [task implementation](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/tool/task.ts).
Background behavior was exercised, not inferred from an available parameter.
Retry behavior was exercised against the real
[retry policy](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/retry.ts).
The missing-ID case is explained by the
[PTY environment adapter](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/plugin/pty-environment.ts).

## Candidate integration contract

| Native evidence | Confirmed meaning | Recommended Dashpot interpretation / remaining question |
| --- | --- | --- |
| `shell.env.sessionID` | Executing native conversation, including child conversations | Candidate command-scoped Agent Session Identity; accept only with corroborating publisher evidence |
| `session.created` / fetched session metadata | Native ID, directory and optional child parentage | Observation, never an Issue Binding or evidence that an idle persistent conversation is currently attached |
| Session directory plus matching plugin directory/Worktree | Consistent location in this tested local execution mode | Candidate Observation Location; a tool cwd must not relocate an Agent Session. Mismatches and cross-directory resume need a separate probe |
| `session.status: busy` | That conversation is executing its loop | Running activity for that Agent Session |
| `session.status: retry` | That conversation awaits automatic retry | Running engagement with retry detail, not waiting for a person |
| `session.status: idle`, `session.idle` | That conversation's loop settled | Waiting activity; deduplicate equivalent observations, and aggregate still-active children before marking the Agent Run waiting |
| `session.error` / abort followed by idle | A turn encountered an error or stopped | Do not end Issue work from the error alone |
| Child `parentID` | Native delegation relationship | Aggregate activity through the parent relationship; child identity does not authorize independent Issue reassignment |
| New ID returned by fork | A new conversation | Never copy an Issue Binding; `parentID` alone cannot recover fork origin |
| Client socket/process disappears | That client detached or exited | No termination inference about the backend or conversation |
| Plugin `dispose` | One instance's observation publisher was disposed | Observation loss/generation retirement; not Agent Session termination |
| `session.deleted` | Explicit removal of one persistent conversation | Distinct termination evidence; future work must decide reconciliation with bound work |
| Backend process proven gone | That recorded execution process ended | Process liveness evidence, scoped to its associated runtime. The conversation can resume later |
| No events, unavailable receiver, unobservable PID | Observation unavailable | Unknown, never gone; do not manufacture a lifecycle event |

The distinction between status idle and the additional deprecated idle event is
also visible in the pinned
[status publisher](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/status.ts).
The [plugin dispatcher](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/plugin/index.ts)
filters events by instance directory and does not await event callback promises;
it does await trigger hooks. Consequently the ordered publication guarantee in
this experiment comes from the bridge, not native callback completion ordering.

### Bootstrap, order and bounded failure

The plugin awaits its initialization publication. Every shell hook fetches native
session metadata with a 250 ms waiting bound, then waits for publication behind
that session's pending events. Only the individual command's environment is
changed; process-global environment state is never used to select a conversation.
The harmless command queries the receiver before doing its brief simulated work.
This is an opt-in-shaped corroboration check, not `dashpot work start`.

The bridge assigns a sequence at callback entry and serializes by native session
within a plugin generation. Separate sessions can progress concurrently. The
receiver rejects non-increasing sequences and publications from a replaced
generation. Its replay actions intentionally repeat already emitted metadata;
they establish bridge behavior, not a claim that OpenCode natively retransmits
those events. Native IDs are preserved for subsequent duplicate analysis.

Each publication request has a 250 ms timeout. A session queue admits at most
16 pending requests, bounding its publication wait to approximately four seconds
plus scheduling overhead; metadata lookup adds at most 250 ms of waiting.
Failure is recorded and swallowed so observation does not abort the tool. The
experiment exercises connection failure and timeout, not queue saturation or
every disk/network failure. Diagnostic file failure has a fixed stderr fallback.

The 600 ms receiver test deliberately allows processing after the publisher times
out. A timed-out bootstrap is not proof available to the first command, even if
its metadata appears later. A later accepted event with a higher sequence cannot
be replaced by an earlier one. Recovery of already-bound work after evidence loss
still needs an explicit production policy.

The receiver's generation registration and ordering maps are in memory. Explicit
instance disposal drains this plugin's current queues; replacement creates fresh
ones. Rejecting a replay from a retired generation is demonstrated. Receiver
restart, lost initialization, reversed initialization delivery, overlapping
generations without orderly disposal, and durable generation arbitration are
**unresolved**. The prototype is not a production persistence or authentication
design, and does not establish exactly-once native delivery.

### Why a session/runtime association is needed

Session-specific lifecycle evidence plus process liveness describes the observed
activity **only when the evidence includes which runtime and publisher observed
that session**. A bare native session ID and a live PID cannot detect the
demonstrated observation-loss case: the plugin disappeared while both remained
valid. A process-keyed record also conflates A with B; a persistent conversation
record alone survives backend exit and says nothing about current execution.

The evidence therefore supports retaining an explicit association between native
Agent Session Identity, observed backend process identity, plugin generation and
Observation Location. Preserve the existing distinction between proven gone and
unobservable process identity. Do not use a client PID, publisher subprocess PID,
or cwd as session identity. Here the publisher ran directly inside the backend;
there was no publisher subprocess, and attached CLI PIDs were observably different.

No lease, heartbeat, daemon or new persisted schema is justified by this spike
alone. Installation/reload recovery must first specify how evidence is restored
for existing sessions and how stale generations are rejected. Merely listing
persistent conversations at startup must not mark all of them live or working.
Command bootstrap restored A after replacement and backend restart; idle sessions
without another command were not automatically republished by this plugin.

## Recommended follow-up work

1. **Identity:** design the Harness Adapter and matching seams around native
   Agent Session Identity, preserving multiple sessions per host process. Audit
   process-primary Work Store record names and fallback matching through the
   public `WorkStore`, Issue-work commands and `observe_agent_runs` seams.
2. **Lifecycle:** separate activity, conversation deletion, publisher loss and
   runtime exit. Specify the session/runtime association, generation replacement,
   failure recovery and startup evidence before choosing storage. Preserve
   [sandbox identity](adr/0007-identify-sandboxed-sessions-by-agent-session-identity.md)
   and the existing unknown-liveness boundary.
3. **Delegation:** aggregate child and background activity into the parent's
   Agent Run while retaining the existing authority restriction; never infer
   separate child Issue work. Fork is independent, with no copied binding.
4. **Installation:** target the tested legacy local plugin/shell path first only
   if a subsequent decision accepts that scope. Version-check the optional hook
   inputs, refuse uncorroborated/missing identity, establish an awaited bootstrap
   barrier, and document bounded failure. Verify TUI/desktop and V2 separately.
5. **Relocation:** probe same-session continuation through another directory and
   Worktree, comparing persisted location, runtime context and simultaneous
   clients. Do not infer relocation from `workdir` or claim preservation of an
   Agent Run from the restart test.

For future harnesses such as Pi, the reusable facts are opaque conversation
identity, command-scoped claims, activity, parentage, Observation Location and
process liveness. Shared-process concurrency, session-end semantics, missing
shell identifiers and publisher lifetime are varying adapter contracts. This
experiment provides no live Pi evidence and proposes no generic extension API.

## Validation

The retained trace passes the independent verifier across all 913 records, and
its recorded source hashes match the retained experimental files. Node syntax
checks pass for all three modules. The complete pre-commit gate and an explicit
pre-commit run over the new files pass; documentation frontmatter/link checks
also include the new, unstaged report. The existing Python suite passes with
1,196 tests and 154 subtests. No dependency lockfile or production code changed.
