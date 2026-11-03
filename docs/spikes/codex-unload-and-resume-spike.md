---
status: research
date: 2026-11-03
---

# Codex unload and resume experiment

The experiment for [Issue #663](https://github.com/ned2/dashpot/issues/663)
qualifies how the managed app-server daemon of the pinned **codex-cli
0.166.0** unloads a thread once its last client has left, and what a
sequential resume of that thread meets. Two upstream changes since the
0.160.0 evidence motivate it:
[openai/codex#50380](https://github.com/openai/codex/pull/50380) attaches the
thread listener even when the client that started the thread disconnected
during MCP startup, so such a thread unloads at all, and
[openai/codex#51420](https://github.com/openai/codex/pull/51420) keeps
waiting for a thread's shutdown past a ten-second warning rather than
abandoning it. The Issue named 0.162.0; the maintainer's decision of
2026-11-03 moved it to 0.166.0, the release the Arc runs.

The 0.160.0 measurement ([#639](codex-sandboxed-worker-cycle-spike.md)) and
the 0.166.0 launch qualification
([#678](codex-lead-launch-qualification-spike.md)) and departure run
([#681](codex-root-session-departure-spike.md)) stay as dated history; this
run repeats their unload and resume observations at 0.166.0 and adds the
cases they did not cover.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it. A
  timing is this run's single sample, which the verifier checks against a
  looser bound;
- **documented**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`;
- **inference**: concluded from the measured and documented facts, not
  observed;
- **unknown**: with the reason it is unknown.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Did the idle-unload delay change? | No. In all four daemon-hosted sessions the daemon logged the idle shutdown 60.0 s after the session's last terminal exited, and the auxiliary thread each turn starts closed 60 s after it started. The code default of `thread_unload_delay_secs` is still 60, as it was at 0.160.0. | measured; documented, `config/src/config_toml.rs`, `core/src/config/mod.rs` |
| What ends an unload? | The daemon publishes `SessionEnd` from the thread's shutdown, at its start, then sends `thread/closed` once the shutdown has finished and the thread's writer lock is released. Without contention that took 0.3 s, and the lock file was gone at `thread/closed`. | measured; documented, `unload_thread_without_subscribers` in `app-server/src/request_processors/thread_lifecycle.rs` |
| Can a resume start straight after the old client exits? | Not while the daemon holds the thread. The resume command the execute-issues skill gives, with sandbox, writable-root and network options, runs in its own client. Codex refuses it with `thread-store conflict: thread <id> already has an active writer`, shows the transcript read-only and says the conversation is open in another app, as at 0.160.0. Each `R` before the unload was refused again. The first `R` after `thread/closed` resumed the thread, 8 s later at this run's retry cadence, and sent no prompt within 5 s, so the runner typed the one the command line had carried. | measured |
| Where does the resumed session run, and with what? | Where `-C` names, in the resuming client, which is then its Host Process. The resumed turns ran with the resume's grants: the Worktrees directory and the main checkout's `.git` writable and the network on, where the first turns had Codex's default `workspace-write` with only their own Worktree writable and no network. | measured |
| Does the Issue Binding survive an exit and resume at the same Worktree? | No. The daemon's `SessionEnd` defers the run's end, the resumed client's `SessionStart` leaves the run under the daemon, and Dashpot's settler ends the run 10.3 s after that `SessionEnd`, because the daemon is still live. The resumed session is then unbound; `work show` and `work start` recover it. | measured |
| Does it survive a declared relocation and resume at another Worktree? | Yes. After `work relocate` to Worktree B and the exit, the daemon's `SessionEnd` at A left the run pending, and the resumed client's `SessionStart` at B relocated the same run, with the same Issue and `startedAt`, to that client. `work show` at B reported it, and it ended at that client's own `SessionEnd`. | measured |
| In what order do the hooks arrive across that relocation? | `SessionStart`, then `UserPromptSubmit` and `Stop` for each of two turns, at A from the daemon; `SessionEnd` at A from the daemon, 60.0 s after the exit; then `SessionStart` (`source` `resume`), `UserPromptSubmit` and `Stop` at B from the resuming client, the `SessionStart` 8.1 s after `thread/closed`; `SessionEnd` at B when that client exits. | measured |
| What does a slow cleanup do? | With the writer coordination lock held by another process, as Codex's own regression test holds it, the daemon still starts the unload at 60 s and publishes `SessionEnd`, logs `codex.app_server.thread_shutdown_slow` 10 s later and keeps waiting. Meanwhile the thread stays in `thread/loaded/list` with its writer lock held, and the daemon refuses `thread/resume` with `-32600` `thread <id> is closing; retry thread/resume after the thread is closed`. | measured; documented, `app-server/src/request_processors/thread_lifecycle.rs` |
| Does the slow cleanup finish? | Yes, within a bound. Released 20 s into the cleanup, the daemon sent `thread/closed` at once and removed the lock file. Held longer, the cleanup gave up the coordination lock after Codex's 30 s wait, logged `failed to coordinate thread writer lock cleanup`, and sent `thread/closed` 30.3 s into the cleanup while the hold went on, leaving the thread's lock file in place but unlocked. Either way `codex exec resume` with the grants resumed the session afterwards. | measured; documented, `lock_coordination` and `Drop for WriterLockGuard` in `rollout/src/writer_lock.rs` |
| What does Dashpot report during a slow cleanup? | The run ends at the settler, 10 s after the `SessionEnd`, while Codex still holds the thread and refuses to resume it. A cleanup that outlasts the settler leaves no run and a loaded thread. | measured |
| Does a thread whose starting client disconnected during a blocked required MCP startup unload? | Yes. The thread is not loaded while its required MCP server blocks in `initialize`; once the server answered, after the controller had gone, it started with no subscriber and was unloaded 60.0 s later with `SessionEnd` and `thread/closed`. Codex stopped the MCP server as the thread shut down, removed the writer lock, and a later `thread/resume` succeeded. The thread had no turn, so it published no `SessionStart`. | measured; documented, `start_listener` in `app-server/src/request_processors/thread_lifecycle.rs` |
| Does a slow cleanup change the idle delay? | No. The delay before the unload starts was 60.0 s with the lock held too; the cleanup time adds to it, up to the 30 s coordination bound. | measured |
| What does a resume within the settler's 10 s do on a stopped daemon, or at the same Worktree after `work relocate .`? | Unknown: not run. A stopped daemon orphans the run (ADR 0086, measured at 0.160.0). Whether a same-Worktree declaration keeps the binding is untested. | unknown |
| Does any of this hold on macOS, or with a real model? | Unknown: Linux and the fixture model only. | unknown |

## Reproduce

The run needs Node 24 with `node:sqlite`, Python 3, `script`, the pinned
Codex binary, and this checkout's `.venv`. Run the runner detached, from
outside any harness, so that its refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-663/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-663/verify.mjs /var/tmp/dashpot-codex-663-SUFFIX/trace.jsonl
node scripts/experiments/codex-663/verify.mjs /var/tmp/dashpot-codex-663-SUFFIX/trace.jsonl 0.166.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it; `SPIKE_FIXTURE_PARENT` puts the fixture elsewhere. A run takes about
twenty minutes, most of it the waits for the daemon to unload threads.

- [Runner](../../scripts/experiments/codex-663/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. It builds a disposable Dashpot Project outside the
    system temporary directory, with two Markdown Issues and two linked
    Issue Worktrees, A and B. Codex gets an isolated `HOME`, `CODEX_HOME`,
    XDG directories and `TMPDIR`, runs as `codex` through a symlink on a
    fixture-local `PATH`, and its managed daemon has its updater off. The
    daemon's socket lives in Codex's shared per-user daemon directory,
    whose entries the run counts and never removes.
  - **Sandbox.** Codex's default for a trusted project, `workspace-write`
    with no network and approval `never`. Every resume adds the
    execute-issues grants: `--sandbox workspace-write`, `--add-dir` for the
    Worktrees directory and for the main checkout's `.git`, and
    `sandbox_workspace_write.network_access=true`.
  - **Hooks.** Every hook event that `dashpot integrate codex` subscribes
    goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`, trusted through the `hooks/list` ledger.
  - **Model.** A loopback Responses API stands in for the model. For each
    prompt it follows a fixed plan of `exec_command` calls to
    [`command.mjs`](../../scripts/experiments/codex-663/command.mjs),
    which runs inside the session's sandbox, runs the plan's `dashpot work`
    command, if any, and reports its directory, thread, the command's
    outcome, whether it may write in each checkout and outside them, and
    whether it can connect to loopback.
  - **Observer.** A client on the daemon's socket that never subscribes to
    a thread records every `thread/started` and `thread/closed`
    notification and polls `thread/loaded/list` every 500 ms.
    [`lock.py`](../../scripts/experiments/codex-663/lock.py) probes a
    thread's writer lock without creating it or taking the coordination
    lock, and holds the coordination lock for the slow cases.
  - **Scenarios.**
    - `ordinary`: a plain terminal starts in A with `-C`, its turn runs
      `work start 1`, and the person exits. The resume command, with the
      grants and a prompt, starts at once at A; the runner presses `r`
      every 8 s while it shows the read-only screen, and types the prompt
      once a retry resumes without sending it. Its turn runs `work show`.
    - `relocate`: the same with Issue 2, but a second turn runs
      `work relocate` to B and `work show` before the exit, and the resume
      names B.
    - `slow-release`: a plain terminal in A runs `work start 1` and exits;
      the runner then holds the coordination lock, tries a daemon
      `thread/resume` once the unload has begun, releases the lock 80 s
      after the exit, and resumes with `codex exec resume` and the grants.
    - `slow-timeout`: the same with Issue 2, holding the lock for 130 s.
    - `mcp-disconnect`: a controller sends `thread/start` at A with a
      required stdio MCP server,
      [`mcp-blocked.mjs`](../../scripts/experiments/codex-663/mcp-blocked.mjs),
      that answers nothing until a gate file exists. Once the server has
      received `initialize`, the controller disconnects; 3 s later the
      runner opens the gate, waits for the thread to unload, and resumes it
      through another controller.
  - **Records.** Every model request with its probe report, every hook
    with its Host Process, the observer's notifications and loaded lists,
    writer-lock probes, each resume's outcome, Codex's log lines for
    unloads, slow shutdowns and writer-lock refusals, each thread's
    per-turn directory, sandbox and permissions from its rollout, and
    `dashpot --compact-json` and `dashpot events --json` at each step.
- [Independent trace verifier](../../scripts/experiments/codex-663/verify.mjs)
  checks every **measured** claim above against the trace without
  importing the runner or Dashpot, and prints each interval it measured. It
  checks the runner's sources, and with `--strict` the Dashpot session
  modules, against the hashes the trace records, and the binary's SHA-256
  against the value below.
- [Retained trace](measurements/issue-663-codex-trace.jsonl) is the
  complete metadata stream of the successful run: 288 records, SHA-256
  `60bf6953f183b7d83ae4a72fee9c281b5a133327947eea24b62fe01c55f14b5a`. The
  fixture root appears
  as `$ROOT`, the experiment directory as `$EXPERIMENT`, the checkout as
  `$CHECKOUT` and the home directory as `~`; the TUI's elided paths are
  dropped from screen tails. It holds no prompts beyond the fixture's
  labels.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-03 AEDT |
| Dashpot base | `06df76a40cfd957ccb5210462569264632483123`, with the runner uncommitted |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, as a managed app-server daemon, its TUI clients and `codex exec` |
| Controller | Node `v24.18.0`, over the daemon's Unix socket |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |
| Model | `fixture`, a copy of a bundled catalog entry, served by the loopback fixture |

**Evidence boundary.**

- **Mock model and scripted person.** The fixture model calls the tools on
  a fixed plan, and the runner presses `r` on a fixed cadence. The 8 s
  between `thread/closed` and the resumed `SessionStart` is that cadence,
  not Codex's.
- **Slow cleanup by lock contention.** The run slows the cleanup the way
  Codex's regression test does, by holding the writer coordination lock.
  A cleanup slowed by something else, such as a hook or an MCP server that
  will not stop, is not measured; by source it waits on the same
  `shutdown_and_wait` without a bound of its own.
- **Codex's log.** Codex writes its log database in batches, keeps a
  bounded number of rows, and can lose its last batch when the daemon
  stops. The runner keeps each scenario's lines when it ends, and the
  verifier takes the daemon's `SessionEnd`, which it publishes within 1 s
  of the idle-shutdown line, where that line was not kept.
- **Platforms and releases.** macOS, other releases, real models and
  `--remote` clients are unmeasured.

## 1. Idle unload

`UnloadingState` in `app-server/src/request_processors/thread_lifecycle.rs`
targets the later of the moment the thread lost its last subscriber and the
moment it went idle, plus the thread's `thread_unload_delay`, whose code
default is 60 s (`config/src/config_toml.rs`; per thread in
`core/src/config/mod.rs`). In this run, the daemon logged `thread <id> has
no subscribers and is idle; shutting down` 60.0 s after each terminal
exited, in all four sessions, and the auxiliary ephemeral thread each user
turn starts, which runs no hook and is offered no `exec_command`, closed
60 s after it started. The 61 s #681 measured from `/cd` to the old
session's `SessionEnd` and the 60 s #639 measured at 0.160.0 are the same
delay.

`unload_thread_without_subscribers` then spawns a task that awaits the
thread's `shutdown_and_wait`, which runs `SessionEnd`, and only afterwards
removes the thread and sends `thread/closed`. With nothing in its way the
whole took 0.3 s.

## 2. Resume after the exit

The resume command the
[execute-issues skill](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md)
gives a Lead carries sandbox options, so it runs in its own client, as #678
measured. Started straight after the old client's exit, it met the
read-only screen; Codex's log shows the in-process `thread/resume` refused
with `thread-store conflict: thread <id> already has an active writer` on
the first attempt and on every `r` until the daemon closed the thread. The
first `r` after that resumed the session at the directory `-C` named, but
sent no prompt within 5 s, as at 0.160.0, so the runner typed the one the
command had carried.

The binding then depends on whether the move was declared:

- **Same Worktree, undeclared.** Dashpot's Event Log shows the daemon's
  `SessionEnd` with Work Store change `deferred`, the resumed client's
  `SessionStart` with `unchanged`, and the settler's `ended` 10.3 s after
  the `SessionEnd`. The settler ends the run because the daemon is still
  live ([ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md));
  the resumed `SessionStart` does not claim it, since the run is keyed to
  the daemon. Once the settler had decided, Dashpot listed the resumed
  session unbound.
- **Another Worktree, declared.** With the Relocation Intent pending, the
  daemon's `SessionEnd` changed nothing and the view showed the run
  `unknown` with the `work-relocation-pending` Diagnostic. The resumed
  `SessionStart` at B completed the relocation, as
  [ADR 0029](../adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)
  decides: same Issue, same `startedAt`, the resuming client as Host
  Process, no Diagnostic.

## 3. Slow cleanup

[openai/codex#51420](https://github.com/openai/codex/pull/51420) replaced
the ten-second timeout in `unload_thread_without_subscribers` with a warning
after which the task keeps waiting. Its regression test,
`app-server/tests/suite/v2/thread_unload.rs`, holds
`thread-writer-locks/.coordination.lock` from another process and expects
`thread/closed` once it is released. The run did the same with
[`lock.py`](../../scripts/experiments/codex-663/lock.py):

| | Released 80 s after the exit | Held 130 s |
| --- | --- | --- |
| Idle shutdown after the exit | 60.0 s | 60.0 s |
| `SessionEnd` | at the idle shutdown | at the idle shutdown |
| `thread_shutdown_slow` warning | 10.0 s later | 10.0 s later |
| During the cleanup | loaded, lock held, `thread/resume` refused as closing | the same |
| Dashpot | run ended at the settler, 10 s after `SessionEnd` | the same |
| `thread/closed` | 20.1 s into the cleanup, at the release | 30.3 s into the cleanup, still held |
| Lock file at `thread/closed` | removed | left, unlocked |
| Codex warning | none | `failed to coordinate thread writer lock cleanup` |
| `codex exec resume` afterwards | resumed | resumed |

The 30 s bound is `lock_coordination` in `rollout/src/writer_lock.rs`: when
it times out, `Drop for WriterLockGuard` logs the warning and returns, and
dropping the file releases its lock without removing it. The next
acquisition takes the stale, unlocked file. So a cleanup slowed by the
coordination lock ends within about 30 s; the run did not observe a
cleanup that never ended.

## 4. Disconnect during a blocked required MCP startup

[openai/codex#50380](https://github.com/openai/codex/pull/50380) starts the
thread listener, which drives the idle unload, even when the connection
that requested the thread has closed (`start_listener` in
`thread_lifecycle.rs`; the auto-attach logs `skipping auto-attach for
closed connection` in `thread_processor.rs`). Its regression test,
`app-server/src/message_processor_thread_lifecycle_tests.rs`, still at
0.166.0, blocks a required stdio MCP server on a barrier.

In the run the thread was absent from `thread/loaded/list` while its
required server blocked, including after the controller had gone. Once the
server answered, the thread started with no subscriber and unloaded 60.0 s
later: `SessionEnd`, the server stopped, `thread/closed`, the writer lock
removed. A later `thread/resume` through another controller succeeded with
no turns. The thread never ran a turn, so it published `SessionEnd` with no
`SessionStart` before it.

## Implications

- **The 60 s delay stands** for every rule that relies on it: the
  [agent sessions](../agent-sessions.md#codex-hosting-modes) states and
  Cleanup table, and the skill's "about 60 s".
- **The resume handoff takes a minute.** A resume with launch options
  started at once after the exit stays read-only until the daemon's unload,
  and the person must retype the prompt after `R`. The
  [dispatch](../../src/dashpot/skills/dashpot-issue-work/references/dispatch.md#resume-a-codex-session)
  and [recovery](../../src/dashpot/skills/dashpot-issue-work/references/recovery.md#failed-codex-resume)
  references now say so.
- **A same-Worktree resume of a bound session loses its run.** The skill's
  `work show` check after a resume recovers it with `work start`, which
  starts a new run. Whether Dashpot should keep the run, by claiming it
  from the resumed `SessionStart` or by a same-Worktree declaration, is a
  follow-up, not this Issue's change.
- **`SessionEnd` is the start of a daemon unload, not its end.** Dashpot
  ends the run 10 s later, which can be before Codex has released the
  thread; a resume during that gap is refused as closing. Nothing in
  Dashpot waits for `thread/closed`, and nothing measured here needs it to.
- **Execute-issues Codex reference.** Its Known Dashpot gap and resume
  notes are outside this Issue's files; the hand-back proposes the update.

## Validation

The retained trace passed the independent verifier in both forms, without
and with `--strict`, at the run's base `06df76a`: every script and Dashpot
module it names matched the hash the run recorded, and the binary's SHA-256
matched. After the run's `daemon stop`, no fixture Codex process remained,
the fixture daemon's entries in the shared daemon directory were gone, and
every hook reached Dashpot's publisher and exited 0.
