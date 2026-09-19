---
status: research
date: 2026-09-19
---

# Codex identity and lifecycle experiment

The experiment for [Issue #160](https://github.com/ned2/dashpot/issues/160)
measures how Codex CLI **0.155.1** hosts conversations on one app-server across
root, forked, delegated, resumed and abandoned threads, how the ordinary
`codex exec` client compares, and which identity each mode publishes to hooks
and to the shell. It supplies the Codex evidence the maintained
[server and client reference](agent-harness-server-client-reference.md#codex-cli-and-app-server)
previously drew only from a static reading of the pinned `rust-v0.154.0`
source; the reusable facts live there, and this document is the dated evidence
record with its fixtures and trace.

Three findings matter most for Dashpot. A root thread's `thread.id`,
`thread.sessionId`, hook `session_id`, shell `CODEX_THREAD_ID`, and the shell
`CODEX_SESSION_ID` that `0.155.1` adds all agree, and a fork takes a fresh
value for all five. A delegated child is its own loaded thread whose shell
carries the child id in `CODEX_THREAD_ID` beside the root id in
`CODEX_SESSION_ID`, while every hook the child triggers carries the root
`session_id` with the child only in `agent_id`; the child publishes no
`SessionStart` or `SessionEnd`. And an app-server killed with SIGKILL publishes
nothing and leaves its thread writer locks behind, yet a replacement server
resumes the stored thread at another Worktree and its hooks and shells report
the new location under the same thread id.

This is evidence for the shared lifecycle design, not an accepted ADR or a
changed Harness Adapter. It makes no changes to Dashpot's Work Store,
Issue-work commands, installation, or dashboard.

## Reproduce

The retained experiment uses Node built-ins, an installed Codex CLI 0.155.1,
and Git. The runner rejects another Codex version unless a second argument
names it; the verifier takes the same optional argument. No model credentials
or external model service are needed: a deterministic loopback Responses API,
configured as a custom model provider, returns tool calls to the real Codex
execution loop.

From the assigned Dashpot checkout:

```bash
node scripts/experiments/codex-160/run.mjs "$(command -v codex)"
node scripts/experiments/codex-160/verify.mjs /tmp/dashpot-codex-160-SUFFIX/trace.jsonl
```

Replace the second path with the exact fixture path printed by the runner.
The run takes approximately one minute and fifty seconds, one minute of which
is the default thread unload delay measured in the `unsubscribe-unload-wait`
scenario. The binary must be an absolute path because the fixture environment
carries no `PATH` entry for the operator's tools. A sandbox that blocks
loopback needs a command-scoped exception for the runner. The verifier needs
no network.

- [Runner and trace receiver](../scripts/experiments/codex-160/run.mjs)
  create the fixture, serve the mock Responses API, start and kill app-servers,
  drive app-server clients over WebSocket and `codex exec` clients, and assert
  observable outcomes.
- [Hook publisher](../scripts/experiments/codex-160/hook.mjs) posts the
  identity fields of every configured hook event, the `CODEX*` environment,
  and the hook process's ancestry. It does not import Dashpot or write Project
  state.
- [Shell reporter](../scripts/experiments/codex-160/command.mjs) is the only
  `exec_command` the fixture model issues; it posts the executing shell's cwd,
  `CODEX*` environment, and ancestry, then holds for a requested time so a
  client can leave or interrupt mid-command.
- [Ancestry reader](../scripts/experiments/codex-160/ancestry.mjs) walks
  `/proc` upwards, recording pid, parent, `comm`, start time, cwd, and the first
  six arguments of each process, and stops at the runner so the operator's own
  session above it stays out of the trace.
- [Independent trace verifier](../scripts/experiments/codex-160/verify.mjs)
  checks the emitted evidence against the identity and lifecycle claims without
  importing the runner or publisher.
- [Retained trace](measurements/issue-160-codex-trace.jsonl) contains the
  complete metadata stream from the successful run: 157 records. Its first
  record includes SHA-256 hashes of the five experimental source files.

The runner creates a new `/tmp/dashpot-codex-160-*` root, an independent Git
Repository with an empty fixture commit, and one linked fixture Worktree used as
another location. These are disposable experiment resources, not durable task
Worktrees. It supplies an allowlisted child environment with an isolated home,
XDG directories, temporary directory, and `CODEX_HOME`, and writes a
`config.toml` there that selects the loopback provider with `wire_api =
"responses"`, sets `approval_policy = "never"` and `sandbox_mode =
"danger-full-access"`, trusts the two fixture directories, enables hooks, and
disables the curated plugin sync, apps, and analytics. The plugin sync matters
for isolation: with it enabled, an app-server clones a GitHub repository at
startup. The runner writes `hooks.json` with nine command hooks and then trusts
them the way an operator would, by reading each hook's `currentHash` from
`hooks/list` and recording it under `[hooks.state]` in the same `config.toml`;
the trace keeps the `untrusted` listing before and the `trusted` listing after.
No ordinary configuration, credentials, saved conversations, Git metadata, or
sibling Worktrees are copied or modified, and the runner only ever signals
processes whose environment names the fixture `CODEX_HOME`.

The runner stops any fixture app-server still running, kills any process it
left behind, and closes both loopback servers in `finally`. It retains its
fixture for inspection. After copying any desired trace, remove only the exact
printed fixture root. For a run whose artifacts are not needed, prefix the
runner command with `SPIKE_REMOVE_FIXTURE=1`; it deletes only the root that
run created, including when assertions fail.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-09-19 |
| Dashpot base | `a3f678210b21b61eee366f126f5b64c5fd6a2e2a` |
| Codex binary | Standalone installer launcher, `--version` = `codex-cli 0.155.1` (stable release of 2026-09-18) |
| Operating system | Linux `7.0.0-30-generic`, x86-64 |
| Controller | Node `v24.18.0` |
| Server mode | `codex app-server --listen ws://127.0.0.1:<port>`, three instances in turn (primary, competitor, replacement) |
| App-server clients | Raw JSON-RPC v2 over WebSocket: `initialize` with `experimentalApi`, `hooks/list`, `thread/start`, `thread/fork`, `thread/resume` with a `cwd` override, `thread/read`, `thread/loaded/list`, `thread/unsubscribe`, `turn/start`, `turn/interrupt` |
| CLI clients | `codex exec --json --skip-git-repo-check -C <dir>` and `codex exec resume --json --skip-git-repo-check <id>` |
| Delegation | The model's `multi_agent_v1` `spawn_agent` and `wait_agent` tools, one child at depth 1 |
| Model | Loopback Responses API streaming fixture selected by a custom `model_provider` |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, `Interrupt`, each a `command` hook trusted through `[hooks.state]` |
| Other settings | Exact `config.toml` in the runner; isolation environment in trace record 1 |

Only metadata crosses the experimental observation boundary: hook event names
and their identity fields (`session_id`, `turn_id`, `cwd`, `source`, `reason`,
`agent_id`, `agent_type`, `tool_name`, `tool_use_id`, `permission_mode`,
`model`, `stop_hook_active`), the names of the other payload keys, whether a
`transcript_path` was present, the `CODEX*` environment, process ancestry,
thread summaries from the app-server (ids, cwd, `source`, `status`,
`originator`), loaded-thread and writer-lock listings, JSON-RPC error codes
and messages, command exit status, and the first six arguments of each
process. The mock model records scenario labels, request counts, and
advertised tool names, not messages. Prompt text, transcripts, tool inputs and
responses, and full environments are not retained. Codex's own disposable data
under the fixture `CODEX_HOME` can contain the synthetic conversation; it is
not part of the retained evidence.

`receipt` and `receiptTime` order controller observations. Native identifiers
are retained without interpreting their format.

The interactive terminal (`codex`, `codex --remote`, `/cd`, the managed
`/worktree` command), Remote Control and the managed daemon, the optional Code
Mode remote host (`--code-mode-host`), MCP-hosted clients, the stdio
app-server transport, other releases, and other operating systems remain
untested. The interactive terminal was left out of this run rather than
blocked; a PTY-hosted follow-up can measure it the same way. The reference's
[pinned source reading](agent-harness-server-client-reference.md#codex-cli-and-app-server)
remains the only account of those modes, and the reference labels each row
accordingly.

## Scenario results

Trace references below are the `receipt` field, not file line assumptions.
Thread A is the first root thread at the fixture Repository, thread B the
second at the other Worktree, F the fork of A, and "child" the sub-agent A
spawned.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Hook trust | Freshly written hooks list as `untrusted`; after their `currentHash` values are recorded under `[hooks.state]` in `config.toml`, the same server lists them `trusted` without a restart. | 5–6 |
| Two root threads | One app-server process (`comm` `codex`) holds A and B loaded at two cwds with no second Codex process. For each thread `thread.id` = `thread.sessionId` = hook `session_id` = shell `CODEX_THREAD_ID` = shell `CODEX_SESSION_ID`; hook cwd and shell cwd equal the thread cwd; every hook and shell descends from the app-server pid. `SessionStart` (`source` = `startup`) fires at the first turn, not at `thread/start`. Hook processes carry only `CODEX_HOME`, never a thread id. | 8–35 |
| Fork | `thread/fork` of A yields a new `id` with `sessionId` equal to its own id and `forkedFromId` = A. Its first turn publishes `SessionStart` with `source` = `fork`; the payload names no parent. The fork's shell claims the fork id in both variables. | 37–49 |
| Sub-agent | `spawn_agent` from A creates a child that appears in `thread/loaded/list`; `thread/read` reports `parentThreadId` = A, `sessionId` = A, and a `subAgent.thread_spawn` source at depth 1. The child's shell carries `CODEX_THREAD_ID` = child id and `CODEX_SESSION_ID` = A. `SubagentStart`, the child's `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `SubagentStop` all carry `session_id` = A, `agent_id` = child id, `agent_type` = `default`, and a `turn_id` distinct from A's turn. No `SessionStart` fired for the child, and no `SessionEnd` ever did. The child held its own writer lock. | 51–72, 124 |
| Second client attaches | A second WebSocket client's `thread/resume` of the loaded A and B returns the same ids and publishes no hook. | 74–75 |
| Client departs mid-turn | The first client's socket closes (code 1006) while B's command holds; the command runs to completion, the second client receives `turn/completed`, and no `Interrupt` or `SessionEnd` fires. | 76–86 |
| Interrupt | `turn/interrupt` on B ends the turn with status `interrupted`; the held command is killed before its end report; `Interrupt` carries `session_id` and `turn_id`; no `PostToolUse` or `Stop` follows. | 88–94 |
| `codex exec` | A separate `codex` process hosts its own thread; its shell and hooks descend from that pid, not the app-server. The thread id from `thread.started` equals the shell's two claims and the hook `session_id`. Hooks run `SessionStart` `startup` through `Stop`, then `SessionEnd` `other` at process exit. | 98–109 |
| `codex exec resume` from another cwd | Resuming that thread from the other Worktree keeps its id, publishes `SessionStart` with `source` = `resume`, and every hook cwd and the shell cwd are the resuming process's cwd. | 110–121 |
| Competing resume | While the primary server holds A, `codex exec resume A` exits 1 with `thread-store conflict: thread … already has an active writer`; no command ran and no hook fired. A second app-server's `thread/resume A` fails with JSON-RPC `-32600` and the same message, while its `thread/read A` succeeds with status `notLoaded`. The lock directory then held `.coordination.lock` and one lock per loaded thread, the child included. | 123–128 |
| Unsubscribe and unload | After the last subscriber's `thread/unsubscribe` of F, `SessionEnd` `other` fired after 60,067 ms, F left the loaded list, and `thread/closed` still reached the unsubscribed client. The idle child unloaded about eight seconds earlier with `thread/closed` and no hook. | 96, 130–131 |
| Abrupt server exit | SIGKILL of the primary server with A and B loaded: exit by signal, client close 1006, no hook of any kind, `.coordination.lock` and both thread locks left on disk, no leftover fixture process. | 133–136 |
| Stored thread resume | A replacement server's `thread/read A` returns the stored Repository cwd with status `notLoaded`. `thread/resume A` with `cwd` = the other Worktree succeeds despite the stale lock and publishes no hook. The next turn publishes `SessionStart` `resume`; hook cwd and shell cwd are the other Worktree, the shell claims A in both variables, and the shell descends from the replacement pid. | 138–152 |
| Graceful server exit | SIGTERM of the replacement server: exit 0, `SessionEnd` `other` for A with the overridden cwd, A's lock removed, only `.coordination.lock` left. | 154–156 |

The fork `source` confirms the post-`0.154.0` change the reference had cited
from `main` (PR #44349) as released. The `sessionId` reported for a fork
matches the `0.154.0` source reading and contradicts the upstream protocol
documentation the reference quotes, which says a fork's `sessionId` is the
origin thread's; the sub-agent case is where `sessionId` differs from `id`.

## Implications for Dashpot

- The shell claim Dashpot reads in
  [`harnesses.py`](../src/dashpot/sessions/harnesses.py), `CODEX_THREAD_ID`,
  names the executing thread: the root for a root thread's own shells, the
  child for a sub-agent's shells. `0.155.1` adds `CODEX_SESSION_ID`, which
  names the root in both cases and is the value that agrees with every hook's
  `session_id`. A sub-agent's shell claim therefore does not match the
  session key that hooks publish for the same work; a Harness Adapter that
  wants one key per conversation should prefer `CODEX_SESSION_ID` when it is
  present.
- A hook's `session_id` is a parent-scoped identity. The executing child is
  named only by `agent_id` in the sub-agent hooks, and never by a
  `SessionStart` or `SessionEnd` of its own.
- `is_codex_host_process` accepts a process named `codex`, which matched the
  app-server and the `codex exec` process alike; every hook and shell in this
  run descended from one or the other, and no Code Mode or other helper
  process appeared.
- An app-server thread outlives its clients. A departing client changes
  nothing; only the last subscriber's departure starts the unload timer, and
  `SessionEnd` arrives a minute later. Observation that retires a run on a
  client disconnect would retire a thread that is still executing.
- SIGKILL of the server publishes no `SessionEnd`. A run that waits for
  `SessionEnd` before ending must also tolerate the host pid disappearing, and
  the writer locks left behind do not stop a later resume elsewhere.
- Relocation is real for stored threads: `thread/resume` with a `cwd`
  override, and `codex exec resume` from another directory, keep the thread id
  and move every hook `cwd` and the shell cwd. The `SessionStart` `resume` hook
  that follows is the first evidence of the new location.

## Validation

The retained trace passes the independent verifier across all 157 records, and
its recorded source hashes match the retained experimental files. Node syntax
checks pass for all five modules. No dependency lockfile or production code
changed.
