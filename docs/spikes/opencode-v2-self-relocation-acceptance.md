---
status: research
date: 2026-10-04
---

# OpenCode v2 self-relocation acceptance run

The acceptance run for [Issue #423](https://github.com/ned2/dashpot/issues/423)
checks the decision in
[ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)
against OpenCode 2.0.22, the pinned release: a root OpenCode session moves
itself with OpenCode's own move, as the
[dispatch reference](../../src/dashpot/skills/dashpot-issue-work/references/dispatch.md#move-an-opencode-session)
of the bundled `dashpot-issue-work` skill describes. The fixture model follows
the skill's dispatch, finish and switch flows step by step and chooses each
step from the output of the one before. It also drives the cases the skill
hands off on, and the cases that defer a move. Each finding below is marked
**measured**, checked by the verifier against the retained trace, or
**documented**, read from the 2.0.22 source.

The run builds on the [OpenCode v2 worker mechanics
experiment](opencode-v2-worker-mechanics-spike.md), whose runner it was cut
down from, and on
[ADR 0090](../adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md),
and does not repeat their findings.

## Reproduce

The runner needs Node built-ins, Git, `uv`, and the OpenCode **2.0.22** binary.
The binary is copied into the fixture, so the operator's own installation is
never run in place. The runner starts its own service on a private port, with
disposable configuration and state, a proxy that reaches nothing but
loopback, and autoupdate disabled. It never contacts the operator's service.
No model credentials are needed: a loopback OpenAI-compatible provider
returns tool calls to OpenCode's real execution loop. The runner builds
Dashpot from the checkout into a fixture environment, and from that
installation `dashpot integrate opencode` installs the plugin and the skill
the run exercises.

The runner refuses to start below a harness session. From the assigned
Dashpot checkout, detach it with `setsid -f`:

```bash
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-423/run.mjs \
  <absolute opencode 2.0.22 binary> > run.log 2>&1
node scripts/experiments/opencode-423/verify.mjs <fixture root>/trace.jsonl
```

The run takes about a minute and is done when its log prints
`All scenarios completed`. The verifier needs no network; `--strict` also
fails it when the Dashpot sources the run exercised have changed since.

- The [runner](../../scripts/experiments/opencode-423/run.mjs) creates a
  Dashpot Project with a markdown Issue Source, ten Issues and five linked
  Worktrees, `a` to `e`, beside a missing path and a plain file. It serves the
  fixture model and drives the service through its HTTP API and CLI.
- The [shell reporter](../../scripts/experiments/opencode-423/command.mjs) and
  [ancestry reader](../../scripts/experiments/opencode-423/ancestry.mjs)
  report each shell's identity variables and directory around the
  `dashpot` command it runs.
- After each scenario the runner records the hook and Work Store records of
  every Worktree, the session's location from the HTTP API, an observation,
  and a Cleanup preview of the Worktree involved.
- The [independent trace verifier](../../scripts/experiments/opencode-423/verify.mjs)
  checks each measured claim below.
- The [retained trace](measurements/issue-423-opencode-trace.jsonl) holds
  319 records. The first holds the SHA-256 hashes of the binary, the
  runner's scripts and the Dashpot sources the run exercised, the skill
  included. Fixture and binary paths appear as `$ROOT` and `$BINARY_DIR`.

## Tested configuration and evidence boundary

- **Versions.** OpenCode 2.0.22 on Linux x64 (binary SHA-256
  `32cf5aa0…5ad122`), Node 24.18.0.
- **Dashpot.** The run's checkout was `243343f`, after the `dashpot-worker`
  agent ([#422](https://github.com/ned2/dashpot/issues/422)), with this
  change to the skill and `integrate --status` not yet committed. The trace
  records the SHA-256 of every source the run exercised, the skill included,
  and `verify.mjs --strict` fails unless the checkout's sources still match.
- **Service and models.**
  - Only the shared service is measured. Every session is a root session
    created through the HTTP API; a TUI, `--standalone` and `--server <url>`
    are not.
  - Every model turn is the fixture's. Whether a real model follows the
    skill, keeps the move alone in its step, or waits for its workers is not
    measured.
- **Configuration.** The global configuration allows every tool, except in
  `default-permissions`, which restarts the service with no permission rules.
  The `denied` and `asked` sessions add their own rule for `*session_move`.
  Project configuration is disabled with `OPENCODE_DISABLE_PROJECT_CONFIG`.
- **Scenarios**, in order: `installer`, `bound`, `unbound`, `finish`,
  `switch`, `same-step`, `refused-destination`, `unwritable`, `denied`,
  `asked`, `workers`, `default-permissions`.

## Findings

### The move and its timing

**Measured.**

- **The call.** The model calls
  `tools.opencode.session_move({ directory })` through `execute`. Its result
  is JSON, `{"sessionID": "ses_…", "directory": "<destination>"}`, returned
  while the session is still where it was.
- **When it applies.** OpenCode's `session.moved` for the session arrived
  after that result and before the model's next step. In `same-step`, a
  shell called beside the move in the same step ran at the main Worktree,
  where the session was; the next step's shell ran at the destination. This
  is why the skill makes the move alone in its step and checks it in the
  next.
- **The check.** In the next step, `pwd` and
  `dashpot integrate opencode --status`, run as one shell command, printed
  the destination and `Agent Session identity claimed here: OpenCode session
  <id> (from OpenCode environment), confirmed by its live hook record`. The
  session's `OPENCODE_SESSION_ID` was the same before and after the move.

### Bound and unbound sessions

**Measured.**

- **Bound.** A session bound to `issue-1` at the main Worktree moved to `a`.
  Its Agent Run moved with it, with the same `startedAt`, Agent Session and
  Issue Binding, and its `workingDirectory` became `a`. `work show` at `a`
  reported it, so the session retained it and ran no `work start`. A
  Cleanup preview of `a` named the session and its run. The next prompt to
  the same session continued the conversation at `a`.
- **Unbound.** A session with no run moved to `b`. `work show` there
  reported no active Issue work, so it ran `work start issue-2`, and its run
  was recorded at `b`.

### Finish and switch

**Measured.**

- **Finish.** The bound session at `a` ran `work stop`, saw no active Issue
  work in `work show`, moved to the main Worktree and confirmed it there.
  Before, a Cleanup preview of `a` named the session and its run; after, it
  named nothing. The session's earlier hook record at `a` stays, but the
  freshest record places the session at the main Worktree, and that is what
  Cleanup reads.
- **Switch.** The session at `b`, on `issue-2`, finished there, moved to the
  main Worktree, then dispatched to `c` and started `issue-3`. `b` was then
  free for Cleanup.

### Destinations OpenCode refuses

**Measured.**

- A missing path and a plain file each failed the tool at once with
  `Unable to move session to <path>`. The session stayed at the main
  Worktree with its bound run, and the skill's flow handed off.
- OpenCode prepares the destination before it accepts a move, and resolves a
  relative path against the session's directory (**documented**, from
  `session/move.ts`).

### A move Dashpot could not record

**Measured.** With `e/.dashpot/state` made read-only, OpenCode accepted and
made the move: the session was at `e`, and the next step's `pwd` printed `e`.
The plugin's hook event there failed with `EACCES`, the run's only
unsuccessful hook outcome, so the freshest hook record still placed the
session at the main Worktree.

Before this change, `integrate --status` printed "confirmed" for that
record from `e`. It now prints `elsewhere: its freshest hook record, live,
places it at <main Worktree>, not here`, the skill's check fails, and the
session hands off without `work start`. `work start` refused in this case
already.

### Permission

**Measured.**

- **Deny.** A session whose permissions deny `*session_move` does not have
  the tool: the call failed with `Unknown tool 'opencode.session_move'`, the
  session stayed put, and the flow handed off.
- **Ask.** OpenCode asked the person nothing, under a rule whose effect is
  `ask` and under a configuration with no rules; each session moved to `d`.
  The runner was ready to reject any request for the move, and none came. So
  a person's refusal of a move could not be exercised; the skill's
  instruction for it covers a release that asks.

### Work the session started

**Measured.** A bound lead launched a background worker as the
`dashpot-worker` agent `integrate` installs
([ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)),
then reached the dispatch. `work show` listed `1 sub-agent listed as working`, so the lead
waited and did not move. When the worker ended, its notice woke the lead,
whose next `work show` listed none; the lead then moved to `d`, confirmed it,
and retained its run. No hook record of the lead kept a live sub-agent, and
a Cleanup preview of `d` named no `sub-agent` obstacle. Moving while a worker
runs, which leaves the worker recorded at the old location
([#427](https://github.com/ned2/dashpot/issues/427)), is not exercised.

## Not measured

- A real model's behaviour, as above.
- A TUI, `--standalone` or `--server <url>` session, a Sub-agent attempting
  a move, and a move across Git Repositories.
- A person declining a move, since OpenCode 2.0.22 never asks.

## Validation

`node scripts/experiments/opencode-423/verify.mjs
docs/spikes/measurements/issue-423-opencode-trace.jsonl --strict` reports
`ok` for all 16 claims, and that the Dashpot sources match the run's.
