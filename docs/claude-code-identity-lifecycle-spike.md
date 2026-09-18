---
status: research
date: 2026-09-18
---

# Claude Code identity and lifecycle experiment

The experiment for [Issue #160](https://github.com/ned2/dashpot/issues/160)
measures how Claude Code **2.1.276** hosts a conversation across its headless,
resumed, forked, delegated and background-supervised modes, and which identity
each mode publishes to hooks and to the shell. It supplies the Claude evidence
the maintained
[server and client reference](agent-harness-server-client-reference.md#claude-code)
previously lacked; the reusable facts live there, and this document is the
dated evidence record with its fixtures and trace.

Two findings matter most for Dashpot. A background worker keeps its native
session identity across its own abrupt death, an explicit `respawn`, and the
replacement of the supervisor above it, so a worker's process identity is not
the conversation's identity. And every process the supervisor spawns — supervisor,
PTY host, and worker — carries the versioned executable name `2.1.276` rather
than `claude`, so the executable-name test Dashpot applies to a launcher-started
Claude Code process does not recognise a supervised worker.

This is evidence for the shared lifecycle design, not an accepted ADR or a
changed Harness Adapter. It makes no changes to Dashpot's Work Store,
Issue-work commands, installation, or dashboard.

## Reproduce

The retained experiment uses Node built-ins, an installed Claude Code 2.1.276,
Git, and `script` from util-linux. The runner rejects another Claude Code
version unless a second argument names it; the verifier takes the same
optional argument. No model credentials or external
model service are needed: a deterministic loopback Messages API returns tool
calls to the real Claude Code execution loop.

From the assigned Dashpot checkout:

```bash
node scripts/experiments/claude-160/run.mjs "$(command -v claude)"
node scripts/experiments/claude-160/verify.mjs /tmp/dashpot-claude-160-SUFFIX/trace.jsonl
```

Replace the second path with the exact fixture path printed by the runner.
The run takes approximately eighty seconds. The first argument should be the
launcher the operator runs interactively (a symlink named `claude`), so the
executable-name comparison between interactive and supervised processes is
measured rather than assumed. A sandbox that blocks loopback needs a
command-scoped exception for the runner. The verifier needs no network.

- [Runner and trace receiver](../scripts/experiments/claude-160/run.mjs)
  create the fixture, serve the mock Messages API, drive headless and background
  clients, replace and stop the supervisor, and assert observable outcomes.
- [Hook publisher](../scripts/experiments/claude-160/hook.mjs) posts the
  identity fields of every configured hook event, the `CLAUDE*` environment,
  and the hook process's ancestry. It does not import Dashpot or write Project
  state.
- [Shell reporter](../scripts/experiments/claude-160/command.mjs) is the only
  Bash command the fixture model issues; it posts the executing shell's cwd,
  `CLAUDE*` environment, and ancestry.
- [Ancestry reader](../scripts/experiments/claude-160/ancestry.mjs) walks
  `/proc` upwards, recording pid, parent, `comm`, start time, cwd, and the first
  six arguments of each process, and stops at the runner so the operator's own
  session above it stays out of the trace.
- [Independent trace verifier](../scripts/experiments/claude-160/verify.mjs)
  checks the emitted evidence against the identity and lifecycle claims without
  importing the runner or publisher.
- [Retained trace](measurements/issue-160-claude-trace.jsonl) contains the
  complete metadata stream from the successful run: 220 records. Its first
  record includes SHA-256 hashes of the five experimental source files.

The runner creates a new `/tmp/dashpot-claude-160-*` root, an independent Git
Repository with an empty fixture commit, and one linked fixture Worktree used as
another location. These are disposable experiment resources, not durable task
Worktrees. It supplies an allowlisted child environment with an isolated home,
XDG directories, temporary directory, and `CLAUDE_CONFIG_DIR`; disables the
auto-updater, telemetry, error reporting, and non-essential traffic; and seeds
the isolated `.claude.json` with completed onboarding, accepted bypass
permissions, an approved fixture API key, and trust for the fixture. The
approved key matters: a supervised worker takes its credentials from the
supervisor's keychain check, and without the approval record the workers sit
at a login prompt. No ordinary configuration, credentials, saved
conversations, Git metadata, or sibling Worktrees are copied or modified, and
the runner only ever signals processes whose environment names the fixture
`CLAUDE_CONFIG_DIR`.

The runner stops the fixture supervisor, kills any process it left behind,
and closes both loopback servers in `finally`. It retains its fixture for
inspection. After copying any desired trace, remove only the exact printed
fixture root. For a run whose artifacts are not needed, prefix the runner
command with `SPIKE_REMOVE_FIXTURE=1`; it deletes only the root that run
created, including when assertions fail. The supervisor's socket directory
`/tmp/cc-daemon-<uid>/<hash>/` is created outside the fixture root regardless
of `TMPDIR` and is left to Claude Code.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-09-18 |
| Dashpot base | `1c0fd5f3a0ffa9490ad992ffd20f3454bad1c911` |
| Claude Code binary | Native installer launcher symlink, `--version` = `2.1.276 (Claude Code)` |
| Operating system | Linux `7.0.0-30-generic`, x86-64 |
| Controller | Node `v24.18.0` |
| Headless clients | `claude -p --output-format json`, `--resume`, `--fork-session`, `--dangerously-skip-permissions` |
| Background clients | `claude --bg --name`, `agents --json [--all]`, `attach` under `script`, `stop`, `respawn`, `daemon status`, `daemon stop --any [--keep-workers]` |
| Server mode | `claude remote-control --no-create-session-in-dir`, exit only |
| Model | Loopback Messages API streaming fixture selected by `ANTHROPIC_BASE_URL` |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, `CwdChanged`, each a `command` hook |
| Other flags | Exact isolation flags in trace record 1 and the runner's `env` object |

Only metadata crosses the experimental observation boundary: hook event names
and their identity fields (`session_id`, `cwd`, `source`, `reason`, `agent_id`,
`agent_type`, `prompt_id`, `tool_name`, `tool_use_id`, `permission_mode`,
`model`, `old_cwd`, `new_cwd`), the names of the other payload keys, the
`CLAUDE*` environment without `CLAUDE_CODE_MESSAGING_TOKEN`, process ancestry,
job listings, supervisor status and log lines, command exit status, and the
first six arguments of each process. The mock model records scenario labels,
request counts, and advertised tool names, not messages. Prompt text,
transcripts, tool inputs and responses, the fixture credential, and full
environments are not retained. Claude Code's own disposable data under the
fixture root can contain the synthetic conversation; it is not part of the
retained evidence.

`receipt` and `receiptTime` order controller observations. Native identifiers
are retained without interpreting their format beyond the measured job-ID
prefix relationship.

Interactive terminal sessions, Remote Control attachment (`--remote-control`)
and server mode, the Agent SDK, agent teams, cloud sessions, idle worker
eviction, other releases, and other operating systems remain untested. The
interactive terminal was left out of this run rather than blocked: the
`attach` scenario shows a `script`-hosted PTY can drive the TUI, so a
follow-up can measure it the same way. Remote Control is recorded as blocked:
with only an API key the server refuses to start, and the operator's claude.ai
account was not used.

## Scenario results

Trace references below are the `receipt` field, not file line assumptions.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Headless baseline | One `claude -p` process, executable name `claude`, runs the prompt. Hook `session_id`, shell `CLAUDE_CODE_SESSION_ID`, the result's `session_id`, and `CLAUDE_PID` = the process pid agree; `SessionStart.source` = `startup`; `SessionEnd.reason` = `other` at exit. | 2–15 |
| Resume | `--resume <id>` in a new process keeps the session ID; `SessionStart.source` = `resume` with a different `CLAUDE_PID`. | 16–29 |
| Fork | `--resume <id> --fork-session` yields a new session ID; `SessionStart.source` = `fork`; the payload names no parent. | 30–43 |
| Subagent | The Agent tool's child shares the parent's `session_id` and `CLAUDE_PID`; `SubagentStart`, its tool hooks, and `SubagentStop` add `agent_id` and `agent_type`. `CLAUDE_CODE_CHILD_SESSION=1` is present in every measured shell, so it does not mark a subagent. | 44–67 |
| Two background workers | `claude --bg` in the fixture and in the other Worktree starts one transient supervisor (`daemon run --origin transient`, parent pid 1) and two workers with distinct `sessionId` and `pid`; job `id` is the first eight characters of `sessionId`. Each worker runs as `bg-pty-host` → worker → shell; the shell's `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID` equal the listing's `sessionId` and `pid`, and its cwd and every hook `cwd` equal the listing's `cwd`. Every supervised process has `comm` `2.1.276`; the headless processes started through the launcher symlink have `comm` `claude`. A worker's shells carry `CLAUDE_JOB_DIR`, while `CLAUDE_CODE_SESSION_KIND=bg` and `CLAUDE_BG_BACKEND` stay in the worker process's own environment. | 68–105 |
| Worker argv | Worker A was spawned directly with `--session-id <sessionId>` in argv; worker B was claimed from a pre-warmed spare whose argv is `claude bg-spare …` and names no session. | 97 |
| Attached terminal dies | `claude attach` under `script` is killed with SIGTERM; the worker keeps its pid and no lifecycle hook fires. | 101 |
| Worker relocation | A worker asked to edit calls `EnterWorktree`; the listing's `cwd`, every later hook `cwd`, and the shell cwd move to `.claude/worktrees/<name>` while `session_id`, `pid`, and `CLAUDE_PROJECT_DIR` stay. No `CwdChanged` hook fired. After the supervisor stop, `agents --json --all` reports the stopped job at its dispatch directory again. | 106–129, 208 |
| Abrupt worker exit | SIGKILL of worker A under a live supervisor: about ten seconds later the listing shows the same `sessionId` with a new `pid` and a later `startedAt`, the new pid's `/proc` start time is later than the old one's, and the only new hook is `SessionStart` with `source` = `resume` from the new pid. No `SessionEnd`. | 130–138 |
| Supervisor replacement | `daemon stop --any --keep-workers` exits the supervisor; `daemon status` reports it not running with three workers in `roster.json`; `agents --json` still lists them with unchanged pids. Dispatching worker C starts a new supervisor pid that adopts all three (`bg adopt: adopted=3`); pids and session IDs are unchanged and no `SessionEnd` fired. Worker B's turn, started under the first supervisor, publishes its `Stop` under the second from its original pid. | 139–177, 209 |
| Explicit stop and respawn | `claude stop` publishes `SessionEnd` with `reason` = `other` from the worker pid; the listing shows `state` = `stopped` and no pid. `claude respawn` starts a new pid for the same `sessionId`, with a later `startedAt` and `SessionStart.source` = `resume`. | 178–194 |
| Supervisor stop | `daemon stop --any` terminates the four workers, each publishing `SessionEnd` `other`; every job lists as `stopped`, with `startedAt` at its dispatch time rather than its last worker's start. Five `bg-pty-host` processes outlived the stop until the runner killed them. | 195–208 |
| Remote Control eligibility | `claude remote-control` exits 1: "You must be logged in to use Remote Control … only available with claude.ai subscriptions". | 210–212 |

The supervised topology and the adoption on restart agree with the documented
[supervisor contract](https://code.claude.com/docs/en/agent-view#the-supervisor-process);
the measured `SessionEnd` and `SessionStart` deliveries are what the
[hooks reference](https://code.claude.com/docs/en/hooks) leaves open. The
`daemon status` warning that `claude agents` restarts the supervisor was not
exercised: the runner's `agents --json` calls read the roster without starting
one.

## Implications for Dashpot

- `is_claude_code_host_process` in
  [`harnesses.py`](../src/dashpot/sessions/harnesses.py) accepts a process
  whose executable name is `claude`. A supervised worker, its PTY host, and the
  supervisor are all named `2.1.276` under the native installer, so a
  background worker's shell claim currently resolves to no supported harness.
  The versioned name is an installer artefact, not a contract; the shell claim
  `CLAUDE_CODE_SESSION_ID` / `CLAUDE_PID` and the hook `session_id` are the
  stable identity, corroborated by `agents --json` for background workers.
- A worker's pid and start time change on abrupt death and on `respawn`,
  while its session ID, name, and cwd persist and the listing had the new pid
  by the runner's next read, about two seconds after the restart hook. A
  process-keyed record that treats a new pid as a new Agent Session would
  split one conversation; a record keyed by session ID must still expect
  `CLAUDE_PID` to change.
- Supervisor replacement is invisible to hooks. Observation that waits for
  `SessionEnd` before retiring a run sees the right thing here, and observation
  that keys anything on the supervisor pid does not.
- An attached terminal is a client, not the runtime: its exit publishes nothing
  and changes nothing.
- `EnterWorktree` relocates a background worker without a `CwdChanged` hook;
  the next hook's `cwd` and the listing carry the new location while
  `CLAUDE_PROJECT_DIR` keeps the dispatch directory.

## Validation

The retained trace passes the independent verifier across all 220 records, and
its recorded source hashes match the retained experimental files. Node syntax
checks pass for all five modules. No dependency lockfile or production code
changed.
