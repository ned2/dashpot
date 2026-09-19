---
status: research
date: 2026-09-20
---

# Codex declared relocation on a daemon-hosted thread

The experiment for [Issue #269](https://github.com/ned2/dashpot/issues/269)
measures the sequential `codex resume <id> -C <path>` route that
[ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)
relies on when the thread being resumed is hosted in the managed daemon, on
Codex CLI **0.155.1**. The
[Cleanup handoff feasibility experiment](cleanup-session-handoff-feasibility-spike.md)
had found that every terminal under a `CODEX_HOME` whose managed daemon is
running hosts its thread there, that a terminal's `/exit` runs no hook and
leaves the thread loaded for the daemon's unload delay, and that
`thread/resume` of a subscribed thread ignores its `cwd` override; it left
open whether a `codex resume -C <new>` issued inside that window reattaches to
the still-loaded thread in the old directory, and whether the old runtime's
`SessionEnd` then arrives after the resumed session is already running. This
document is the dated evidence record; the reusable facts are folded into the
[server and client reference](agent-harness-server-client-reference.md#the-managed-daemon-and-attached-terminals-at-01551).

The answer is that the route relocates correctly in every hosting state. A
daemon-hosted resume inside the unload window shuts the still-loaded runtime
down first — `SessionEnd` `other` at the **old** directory — and then
cold-resumes the same thread at the new one, whose first hook is
`SessionStart` `resume` at the new directory. The order ADR 0029 depends on,
origin `SessionEnd` before target `SessionStart` under one Agent Session
Identity, holds with the daemon exactly as it does without one, and no
`SessionEnd` arrives later while the resumed terminal lives. Nothing here
changes ADR 0029, the Work Store, or a Harness Adapter.

## Reproduce

The retained experiment uses Node built-ins, Git, and an installed Codex CLI
0.155.1; the runner rejects another version unless a second argument names it,
and the verifier takes the same optional argument. No model credentials or
external model service are needed: a deterministic loopback Responses API
returns the one `exec_command` call that drives the real harness. Each
interactive terminal runs on a pseudo-terminal hosted by `script`, because the
Codex terminal is the client under test.

From the assigned Dashpot checkout:

```bash
node scripts/experiments/codex-269/run.mjs "$(command -v codex)"
node scripts/experiments/codex-269/verify.mjs /tmp/dashpot-codex-269-SUFFIX/trace.jsonl
```

Replace the trace path with the exact fixture path the runner prints. The run
takes about five minutes, four of them the daemon's sixty-second unload delay
waited for three times plus the control's own exit. The binary must be an
absolute path because the fixture environment carries no `PATH` entry for the
operator's tools. A sandbox that blocks loopback needs a command-scoped
exception for the runner; the verifier needs no network.
`SPIKE_DEBUG_TERMINAL=1` writes each pseudo-terminal's screen text beside the
trace, and `SPIKE_REMOVE_FIXTURE=1` deletes the run's fixture root, including
on failure.

- [Runner](../scripts/experiments/codex-269/run.mjs) creates the fixture,
  serves the mock Responses API, starts and stops the managed daemon, hosts
  terminals on pseudo-terminals, types `/exit` and a second turn, launches
  `codex resume <id> -C <path>` at the moment each scenario prescribes, reads
  the daemon's `thread/read` and `thread/loaded/list` through a controller
  client that never subscribes, and asserts observable outcomes.
- [Verifier](../scripts/experiments/codex-269/verify.mjs) checks the emitted
  evidence against the claims below without importing the runner.
- The [hook publisher](../scripts/experiments/codex-269/hook.mjs), the
  [shell reporter](../scripts/experiments/codex-269/command.mjs), the
  [ancestry reader](../scripts/experiments/codex-269/ancestry.mjs), and the
  [Unix-socket WebSocket client](../scripts/experiments/codex-269/uds-websocket.mjs)
  are copies of the #148 experiment's: metadata-only, importing nothing from
  Dashpot and writing no Project state.
- The retained [trace](measurements/issue-269-codex-trace.jsonl) (139
  records) is the complete metadata stream of the successful run; its first
  record holds SHA-256 hashes of the experimental source files.

The runner creates a new `/tmp/dashpot-codex-269-*` root holding an
independent Git Repository with an empty fixture commit and two linked
fixture Worktrees, `other` and `third`. These are disposable experiment
resources, not durable task Worktrees. The child environment is an allowlist
with an isolated home, XDG directories, temporary directory, and `CODEX_HOME`;
no ordinary configuration, credentials, saved conversations, Git metadata, or
sibling Worktrees are copied or modified. The runner reads every process's
environment under `/proc` to find the fixture's own processes and signals only
the terminals it started and processes whose environment names its fixture.
It stops what it started in `finally`, closes its loopback servers, and
retains the fixture for inspection; remove only the exact printed root
afterwards. The fixture `config.toml`, hooks, and standalone-release link are
those of the #148 experiment; the hooks are trusted through `[hooks.state]`
by starting the daemon once, listing them, and stopping it again before the
control scenario.

## Tested configuration and evidence boundary

| Fact | Value |
| --- | --- |
| Date | 2026-09-20 |
| Dashpot base | `aee4a214c992f724460b5840625633a19380ebe5` |
| Binary | Standalone installer launcher, `codex --version` = `codex-cli 0.155.1` |
| Operating system | Linux `7.0.0-30-generic`, x86-64 |
| Runner | Node `v24.18.0` |
| Terminals | Plain `codex -C <other> <prompt>` and `codex resume <id> -C <third> <prompt>`, no `--remote` flag and no remote setting, each on a `script` pseudo-terminal; `/exit` and a second prompt typed as text then Enter |
| Daemon | `codex app-server daemon start` / `stop` with `backend` = `pid`; the controller's raw JSON-RPC v2 over WebSocket on the control socket used only `initialize`, `hooks/list`, `thread/read`, and `thread/loaded/list` |
| Model | Loopback Responses API streaming fixture as a custom `model_provider` |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, `Interrupt`, trusted through `[hooks.state]` |

Only metadata crosses the observation boundary: hook event names and identity
fields, the names of other payload keys, the `CODEX*` environment, process
ancestry, thread summaries (id, cwd, `source`, `status`, `ephemeral`),
loaded-thread and writer-lock listings, JSON-RPC error codes, daemon command
output, command exit status, and two booleans per resumed terminal saying
whether its screen showed a read-only notice or the session picker, matched
by a pattern over the whitespace-stripped screen; the stronger evidence that
a resume was live is the writer lock it holds and the two turns it ran. The mock
model records scenario labels and request counts, not messages. The fixture
prompts are content-free `SPIKE:<label>` markers. Prompt text, transcripts,
tool inputs and responses, terminal screen text, and full environments are
not retained.

The boundary of what this proves: one thread per scenario, idle at every
resume, with no sub-agent, background terminal, second subscriber, or
competing client; permissions bypassed (`approval_policy = "never"`); the
positional prompt as the resumed terminal's first turn; and no conversation
canary, so identity preservation is the thread id, not the history. The
in-window resume was launched 98 ms after the first terminal's exit, one point
in the sixty-second window; a resume launched while the old terminal is still
attached, a terminal started before the daemon, `--remote` resumes, `/cd`,
other operating systems, and other releases are unmeasured. Dashpot's own
`work relocate` / `work show` behaviour through a real Work Store was out of
scope by the Issue's definition; the harness facts here are its input.

## Scenario results

Trace references are the `receipt` field. Each scenario runs the same
sequence: a plain terminal in `other` completes one turn and types `/exit`;
`codex resume <id> -C third` launches when the scenario says; the resumed
terminal runs its positional prompt and a typed second turn; the runner
watches ninety seconds for a late `SessionEnd`; the resumed terminal types
`/exit` and the runner waits for the thread's end.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Hook trust and control setup | The daemon started, listed the nine fixture hooks, and after `[hooks.state]` was written listed them `trusted`; `daemon stop` then left no fixture process and no control socket. | 2–7 |
| No daemon (ADR 0029's control) | The plain terminal hosted its own thread: the shell's `codex` ancestor was the terminal process, nothing was loaded anywhere, and no daemon appeared. `/exit` ran `SessionEnd` `other` at `other` before the process ended and released the writer lock. `codex resume <id> -C third` launched 92 ms after the exit was a new process; its first hook was `SessionStart` `resume` at `third` (458 ms after launch), the turn and the typed second turn ran at `third` under the same thread id, and no read-only notice or picker was shown. No `SessionEnd` arrived while the resumed terminal lived; its `/exit` ran `SessionEnd` `other` at `third` at once. | 8–50 |
| Daemon-hosted, resume inside the unload window | With the daemon restarted, the plain terminal's thread was hosted in it: the shell descended from the daemon pid and `thread/loaded/list` included the thread. `/exit` ran no hook; the thread was still loaded, `idle` at `other`, with its writer lock held, when `codex resume <id> -C third` launched 98 ms after the exit. The resumed terminal was daemon-hosted too. Its hooks, in order: `SessionEnd` `other` at **`other`** 212 ms after launch (310 ms after the first terminal's exit), then `SessionStart` `resume` at `third` 314 ms after launch, then the turn at `third`; `thread/read` reported cwd `third`, `idle`. The typed second turn ran at `third`. No later `SessionEnd` arrived during the ninety-second watch, and the thread stayed loaded. `/exit` ran no hook; `SessionEnd` `other` at `third` fired 60,041 ms later, after which the thread was unloaded and its lock released. Both `SessionEnd` hooks descended from the daemon pid. | 51–95 |
| Daemon-hosted, resume after the unload | `/exit` ran no hook; `SessionEnd` `other` at `other` fired 60,035 ms later, after which `thread/read` reported `notLoaded` at `other` with no lock. `codex resume <id> -C third` then behaved as the stored-thread resume the [#160 experiment](codex-identity-lifecycle-spike.md#scenario-results) measured: daemon-hosted, `SessionStart` `resume` at `third` first (356 ms after launch), the turn and second turn at `third` under the same thread id, no late `SessionEnd`, and `SessionEnd` `other` at `third` 60,047 ms after the final `/exit`. | 96–137 |

The hook order at each resume, under one thread id throughout:

| Hosting state at resume | Hooks from the first terminal's `/exit` to the resumed turn's `Stop` |
| --- | --- |
| No daemon | `SessionEnd` `other` @ `other` (at exit) → `SessionStart` `resume` @ `third` → turn @ `third` |
| Daemon, thread still loaded | *(nothing at exit)* → `SessionEnd` `other` @ `other` → `SessionStart` `resume` @ `third` → turn @ `third` |
| Daemon, thread unloaded | `SessionEnd` `other` @ `other` (after the unload delay) → `SessionStart` `resume` @ `third` → turn @ `third` |

## Implications for Dashpot

- ADR 0029 stands as shipped. Its completion condition — the old client's
  `SessionEnd` preserves the pending run, then a hook of the same Agent
  Session Identity at the intended target completes the relocation — is met
  in the same order on every route. On the daemon route the `SessionEnd`
  that ends the origin record and the `SessionStart` that completes the move
  are 102 ms apart and both come from the daemon process, so the completion
  relies on the origin record being `ended`, not on the host process being
  gone; that is the branch
  [`_sequential_target_is_confirmed`](../src/dashpot/sessions/work_reconciliation.py)
  already takes.
- The in-window doubt rested on the feasibility experiment's `thread/resume`
  measurement, which was of a thread the old terminal still subscribed to.
  After `/exit` the thread has no subscriber, and a `thread/resume` with a
  `cwd` override then takes the cold path the
  [reference](agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload)
  describes: the cached runtime is shut down with `SessionEnd` and resumed
  with the override. The two measurements agree; the difference is the
  subscriber.
- The `work relocate` contract needs no new completion meaning for a
  daemon-hosted thread: "wait for `SessionEnd`" and "subscribe and use the
  `turn/start` `cwd` override" were the alternatives had the route failed,
  and neither is needed. The controller route remains a separate,
  live-thread contract for [#148](https://github.com/ned2/dashpot/issues/148)
  and [#261](https://github.com/ned2/dashpot/issues/261), as the feasibility
  experiment proposed.
- A resume inside the unload window is not a wait: the resumed terminal is
  neither read-only nor a picker, so the skill's "retry after release"
  wording applies only while the old terminal is still attached.
- The dispatch reference's claim that the old client must exit before the
  resumed client can continue is confirmed as sufficient on the daemon route
  too: the old terminal's exit alone, with no unload wait, releases the
  thread for the resume.

## Validation

The retained trace passes its independent verifier, all 139 records, and the
recorded source hashes match the retained experimental files. Node syntax
checks pass for both modules. No dependency lockfile or production code
changed.
