---
status: research
date: 2026-09-19
---

# Cleanup session handoff feasibility experiment

The experiment for [Issue #148](https://github.com/ned2/dashpot/issues/148)
measures whether a deliberately opted-in controller can move a live,
interactive Agent Session out of a Worktree without ending its conversation,
on Claude Code **2.1.278** and Codex CLI **0.155.1**. It is the first step of
that Issue's implementation sequence and answers the read-only
[handoff research](cleanup-session-handoff-research.md) of 2026-09-12, which
proposed both controller arrangements but connected to nothing. This document
is the dated evidence record with its fixtures and traces; the reusable facts
are folded into the
[server and client reference](agent-harness-server-client-reference.md).
It proposes one supported controller arrangement per harness as the open
decisions the Issue's feasibility gate raises; nothing here changes Cleanup,
the Work Store, or a Harness Adapter.

Three findings matter most. On Claude Code, a development channel served by
Dashpot can deliver a relocation request into an interactive session, and the
session executes `ExitWorktree` back to its original directory under the same
session id and pid, with hooks, its shell, and `claude agents --json` all
reporting the new location; but the two worktree tools reach a directory only
from one side, so a session launched directly inside the linked Worktree
cannot reach the main Worktree, and a session isolated by `EnterWorktree`
cannot reach a sibling linked Worktree outside `.claude/worktrees/`. On
Codex, the terminals measured under a `CODEX_HOME` whose managed daemon was
running — two attached with `--remote` and one launched plainly — all hosted
their threads in that daemon, where a controller on the control socket moves
a thread with a `turn/start` `cwd` override that sticks for the terminal's
own later turns, under the same thread id and with no new session. And in
both harnesses the move is safe only on an idle session: a Claude channel
event is queued behind the running turn, and a Codex `turn/start` during a
running turn joins that turn, so its input executes in the old directory
while the thread already reports the new one.

## Reproduce

The retained experiments use Node built-ins, Git, and an installed Claude Code
2.1.278 or Codex CLI 0.155.1; each runner rejects another version unless a
second argument names it, and each verifier takes the same optional argument.
No model credentials or external model service are needed: a deterministic
loopback model (Anthropic Messages streaming for Claude Code, OpenAI Responses
streaming for Codex) returns the tool calls that drive the real harness.
Each interactive session runs on a pseudo-terminal hosted by `script`, because
a Claude development channel loads only in an interactive session and a Codex
terminal is the client under test.

From the assigned Dashpot checkout:

```bash
node scripts/experiments/claude-148/run.mjs "$(command -v claude)"
node scripts/experiments/claude-148/verify.mjs /tmp/dashpot-claude-148-SUFFIX/trace.jsonl
node scripts/experiments/codex-148/run.mjs "$(command -v codex)"
node scripts/experiments/codex-148/verify.mjs /tmp/dashpot-codex-148-SUFFIX/trace.jsonl
```

Replace each trace path with the exact fixture path the runner prints. The
Claude run takes about a minute; the Codex run about three, one of them the
daemon's thread unload delay measured in `terminal-exit`. The binary must be an
absolute path because the fixture environment carries no `PATH` entry for the
operator's tools. A sandbox that blocks loopback needs a command-scoped
exception for a runner; the verifiers need no network. `SPIKE_DEBUG_TERMINAL=1`
writes each pseudo-terminal's screen text beside the trace, and
`SPIKE_REMOVE_FIXTURE=1` deletes the run's fixture root, including on failure.

- [Claude runner](../scripts/experiments/claude-148/run.mjs) creates the
  fixture, serves the mock Messages API, hosts interactive sessions on
  pseudo-terminals, answers the development-channel confirmation, pushes
  relocation requests through each session's channel, reads
  `claude agents --json`, and asserts observable outcomes.
- [Development channel](../scripts/experiments/claude-148/channel.mjs) is the
  stdio MCP server each session loads. It declares the `claude/channel`
  experimental capability, exposes one `ack` tool, and takes pushes from the
  runner on a loopback control endpoint, emitting each as a
  `notifications/claude/channel` notification. It reports its own pid, parent,
  and `CLAUDE*` environment on start.
- [Codex runner](../scripts/experiments/codex-148/run.mjs) creates the
  fixture, serves the mock Responses API, starts the managed daemon, attaches
  terminals, and drives a controller client on the control socket.
- [Unix-socket WebSocket client](../scripts/experiments/codex-148/uds-websocket.mjs)
  is the minimal client the controller needs: the daemon's control socket
  speaks WebSocket over a Unix domain socket, which Node's built-in client
  cannot dial.
- The [Claude](../scripts/experiments/claude-148/hook.mjs) and
  [Codex](../scripts/experiments/codex-148/hook.mjs) hook publishers, the
  [Claude](../scripts/experiments/claude-148/command.mjs) and
  [Codex](../scripts/experiments/codex-148/command.mjs) shell reporters, and
  the shared [ancestry reader](../scripts/experiments/claude-148/ancestry.mjs)
  are those of the #160 experiments: metadata-only, importing nothing from
  Dashpot and writing no Project state.
- The [Claude verifier](../scripts/experiments/claude-148/verify.mjs) and
  [Codex verifier](../scripts/experiments/codex-148/verify.mjs) check the
  emitted evidence against the claims below without importing a runner.
- The retained [Claude trace](measurements/issue-148-claude-trace.jsonl)
  (204 records) and [Codex trace](measurements/issue-148-codex-trace.jsonl)
  (125 records) are the complete metadata streams of the successful runs; the
  first record of each holds SHA-256 hashes of its experimental source files.

Each runner creates a new `/tmp/dashpot-<harness>-148-*` root holding an
independent Git Repository with an empty fixture commit — its primary checkout
is the main Worktree — and two linked fixture Worktrees, `other` and `third`.
These are disposable experiment resources, not durable task Worktrees. The
child environment is an allowlist with an isolated home, XDG directories,
temporary directory, and `CLAUDE_CONFIG_DIR` or `CODEX_HOME`; no ordinary
configuration, credentials, saved conversations, Git metadata, or sibling
Worktrees are copied or modified. The Codex runner reads every process's
environment under `/proc` to find the fixture's own processes, and a runner
signals only the terminals it started and processes whose environment names
its fixture. Both runners stop what they started in
`finally`, close their loopback servers, and retain the fixture for
inspection; remove only the exact printed root afterwards.

The Claude fixture pre-accepts onboarding and trust for the three directories,
configures every hook as a command hook, and seeds one more thing: channels
are a research preview behind the remotely served `tengu_harbor` feature flag,
which the isolated fixture cannot fetch, so `.claude.json` carries the cached
value the operator's own account already holds and
`CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF=1` lets the session read the
cache with telemetry off. Without the seed the session logs
`Channel notifications skipped: channels feature is not currently available`.
Each session launches with `--mcp-config` naming the channel server,
`--strict-mcp-config`, and `--dangerously-load-development-channels
server:dashpot`, which is parsed only for an interactive session and shows a
`WARNING: Loading development channels` confirmation that the runner answers
with Enter.

The Codex fixture writes a `config.toml` selecting the loopback provider,
trusting the three directories, enabling hooks, and disabling plugin sync,
apps, and analytics, then trusts its nine command hooks through
`[hooks.state]` as the #160 experiment did. `codex app-server daemon start`
refuses to run without the installer-managed standalone release at
`<CODEX_HOME>/packages/standalone/current`, so the fixture links that path to
the release directory of the pinned binary; the daemon then reports
`managedCodexVersion` and `appServerVersion` of `0.155.1`.

## Tested configuration and evidence boundary

| Fact | Claude Code | Codex |
| --- | --- | --- |
| Date | 2026-09-19 | 2026-09-19 |
| Dashpot base | `31fcf2861e6201725f8742e2b8890ca6ca76dd70` | same |
| Binary | `claude --version` = `2.1.278 (Claude Code)` | Standalone installer launcher, `codex --version` = `codex-cli 0.155.1` |
| Operating system | Linux `7.0.0-30-generic`, x86-64 | same |
| Controller | Node `v24.18.0` | same |
| Sessions | Two interactive sessions on `script` pseudo-terminals, `--dangerously-skip-permissions`, named `fixture-a` (launched in `other`) and `fixture-b` (launched in the main Worktree) | `codex app-server daemon start` with `backend` = `pid`; two terminals `codex --remote unix://<control socket> -C <Worktree>` and one plain `codex -C <Worktree>`, each on a `script` pseudo-terminal |
| Controller surface | Stdio MCP development channel per session; `notifications/claude/channel` with `content` and `meta`; `claude agents --json` | Raw JSON-RPC v2 over WebSocket on `<CODEX_HOME>/app-server-control/app-server-control.sock`: `initialize` with `experimentalApi`, `hooks/list`, `thread/loaded/list`, `thread/read`, `thread/resume` with a `cwd` override, `turn/start` with a `cwd` override, `thread/backgroundTerminals/list`, `thread/unsubscribe` |
| Session actions | `EnterWorktree`, `ExitWorktree(keep)`, `Bash` foreground and `run_in_background`, the channel's `ack` tool | `exec_command` only; terminal prompts typed as text then Enter |
| Model | Loopback Messages API streaming fixture through `ANTHROPIC_BASE_URL` | Loopback Responses API streaming fixture as a custom `model_provider` |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, plus a `CwdChanged` probe entry that never fired | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, `Interrupt`, trusted through `[hooks.state]` |

Only metadata crosses the observation boundary: hook event names and identity
fields, the names of other payload keys, the `CLAUDE*` or `CODEX*`
environment, process ancestry, `agents --json` listings, channel protocol
phases and the `meta` of each push, the worktree tools' result text, Codex
thread summaries (ids, cwd, `source`, `status`, `ephemeral`), loaded-thread
and writer-lock listings, JSON-RPC error codes and messages, daemon command
output, and command exit status. The mock models record scenario labels,
request counts, tool names, and whether a turn arrived in a `<channel>`
wrapper, not messages. The fixture prompts are content-free `SPIKE:<label>`
markers. The only tool input retained is the channel `ack` tool's two
fixture-constant arguments. Process ancestry and the environment record name
the operator's binary, Node, and checkout paths, as the #160 traces do.
Prompt text, transcripts, other tool inputs and responses, terminal screen
text, and full environments are not retained; a pseudo-terminal's screen is
kept only under `SPIKE_DEBUG_TERMINAL=1`, beside the trace and outside the
retained evidence.

The boundary of what this proves: the Claude arrangement rests on a
development-channel flag that is interactive-only, confirmed at every launch,
and gated by a research-preview feature flag, first-party authentication, and
organisation policy; a plugin-distributed channel (`--channels plugin:...`)
would remove the per-launch confirmation and was not measured. A Claude
session's own `/cd` and the Codex terminal's `/cd` and `/worktree` are
human-only and unmeasured. Both fixtures ran with permissions bypassed
(`--dangerously-skip-permissions`, `approval_policy = "never"`), so the
permission prompts a move could raise are unmeasured, and the mock models
never checked that conversation history survived a move: identity
preservation is the session or thread id, not a conversation canary.
Unmeasured too are Claude sessions with an active subagent, Codex sub-agents,
a Claude session whose `.claude/worktrees/` directory exists, the Codex
daemon's Remote Control pairing, the `codex app-server
proxy` relay beyond the finding that it forwards bytes and so needs a
WebSocket-speaking client, a Codex terminal launched before the daemon starts,
sessions with an Issue Binding, and other operating systems or releases.

## Scenario results: Claude Code

Trace references are the `receipt` field. Session A is `fixture-a`, launched
directly in the linked Worktree `other`; session B is `fixture-b`, launched in
the main Worktree and isolated into `other` with `EnterWorktree`, which is the
route Dashpot's own dispatch takes.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Channel registration | The interactive session confirmed the development-channel warning, completed the MCP `initialize` (protocol `2025-11-25`, client `claude-code` `2.1.278`) with the server that declared `claude/channel`, and listed `mcp__dashpot__ack` among its tools. The channel process is a child of the session pid and its environment carries `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PROJECT_DIR`, `CLAUDE_CODE_MESSAGING_SOCKET`, and `CLAUDE_CONFIG_DIR`, so a controller can bind a channel to one session by identity. `agents --json` lists the interactive session with `kind` = `interactive`, its pid, cwd, session id, name, and `idle`/`busy` status. | 3–18 |
| Direct launch, move to main | A pushed request for A to reach the main Worktree: the turn arrived in a `<channel>` wrapper; `EnterWorktree(main)` returned an error, `Cannot enter worktree: … is the main working tree, not a linked worktree`, and `ExitWorktree` returned `No-op: there is no active EnterWorktree session to exit`. A's listing, shell cwd, and hook cwds stayed at `other`. | 19–40 |
| Direct launch, move to a sibling | A's `EnterWorktree(third)` succeeded: `PostToolUse` reported `third`, the shell ran there, and the listing shows `third` under the same session id and pid. | 41–62 |
| Entered session, return | B entered `other` on its first turn, then a pushed request drove `ExitWorktree(keep)`: `Exited worktree … Session is now back in <main>`; `PostToolUse`, the shell, and the listing report the main Worktree under B's original session id and pid, with no `SessionEnd` or `SessionStart`. | 63–110 |
| Busy delivery | A request pushed while A held an eight-second command was delivered 46 ms after the command ended, as the next turn, with no `Stop` between the two turns: the hold turn's `PostToolUse` is followed directly by the relocation turn's `UserPromptSubmit`, and the only `Stop` comes after the relocation turn. A `Stop` is therefore not a per-turn signal while channel events are queued. | 111–136 |
| Background job | B started a twenty-second `run_in_background` shell and its turn ended; a pushed relocation then entered `other` while the job still ran, and the listing showed `status` = `busy` during the job. The job did not block the move. | 137–173 |
| Isolated session, move to a sibling | B, now isolated in `other`, was asked to enter `third`: `Cannot enter worktree: <main>/.claude/worktrees does not exist, so … cannot be a worktree managed by Claude Code`; B stayed at `other`. The tool-free turn between the push and the relocation turn (177–179) is the earlier background job's completion notification, not part of the request. | 174–197 |
| Exit | `/exit` on each pseudo-terminal ended both sessions with `SessionEnd` `reason` = `prompt_input_exit`; the channel processes closed with their sessions. | 198–203 |

The reachability the two tools give an interactive session:

| Session state | `EnterWorktree(main)` | `EnterWorktree(sibling linked Worktree)` | `ExitWorktree` |
| --- | --- | --- | --- |
| Launched directly in a linked Worktree | Refused: main working tree | Allowed; the session becomes isolated there | No-op |
| Isolated by `EnterWorktree` (Dashpot dispatch) | — | Refused: not under `.claude/worktrees/`, which did not exist in the fixture; a Repository with that directory was not measured | Returns to the launch directory, which for Dashpot dispatch is the main Worktree |

The startup notice for channels was not observed on the pseudo-terminal
screen; the trace records `noticed: false` for both sessions. The
`initialize` and the delivered turns are the evidence that the channel loaded.

## Scenario results: Codex

Thread A belongs to the `--remote` terminal launched in `other`, thread B to
the `--remote` terminal launched in `third`, and "plain" to the terminal
launched in `third` without `--remote`.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Daemon start | `codex app-server daemon start` reported `started` with `backend` = `pid`; one `codex app-server --listen unix:// --managed-daemon` process, reparented to pid 1, holds the control socket. The controller's WebSocket `initialize` on that socket succeeded. `hooks/list` showed the fixture hooks `untrusted` and, after `[hooks.state]` was written, `trusted` without a restart. `thread/backgroundTerminals/list` exists and answers `-32600` `thread not found` for an unknown id. | 2–10 |
| Attached terminal | `codex --remote unix://… -C other` hosts thread A on the daemon: `thread/loaded/list` includes A, `thread/read` reports cwd `other` and `status` `idle`, the shell's `CODEX_SESSION_ID` and `CODEX_THREAD_ID` both equal A, and the shell's ancestry is the daemon pid, not the terminal. The terminal's `SessionStart` `startup` through `Stop` carry A. | 11–23 |
| Controller relocation | The controller's `thread/resume` of the loaded A with `cwd` = main subscribed it and left the cwd at `other`: the override was ignored, no hook ran. `turn/start` on A with `cwd` = main ran `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop` at the main Worktree under A's id, the shell ran there, `thread/read` then reported cwd = main, and the terminal rendered the controller's turn. The terminal's own next typed turn ran at the main Worktree: the override stuck. No `SessionStart` or `SessionEnd` occurred. | 24–47 |
| Sibling thread | With B loaded from `third`, a second controller move of A to `other` ran at `other`; B's next turn ran at `third` under B's id. The daemon also listed six further loaded ids, every one `ephemeral: true` with `historyMode` `legacy` at one of the three directories — helper threads the terminals create, not conversations. | 48–80 |
| Busy thread | `turn/start` on A with `cwd` = `third` while the terminal's eight-second command ran was answered with the running turn's own id and `status` `inProgress`: the request's input joined that turn rather than starting a second one. It executed 269 ms after the running command ended, with a second `UserPromptSubmit` under the same `turn_id`, and its hooks and shell ran at `other`, the running turn's directory, while `thread/read` afterwards reported `third`. There is no separate turn or `Stop` to attribute to the controller in this case. `thread/backgroundTerminals/list` for A was empty throughout. | 81–100 |
| Plain terminal | One `codex -C third` launched without `--remote` while the daemon ran, with no remote setting in the fixture `config.toml`: its shell's ancestry is the daemon pid, `thread/loaded/list` includes its thread, and the controller's `thread/resume` of it succeeded (cwd override ignored again). Its `/exit` ran no hook and left the thread loaded and locked. | 101–115 |
| Terminal exit and unload | `/exit` on A's terminal ran no hook; A stayed loaded with its writer lock while the controller remained subscribed. After the controller's `thread/unsubscribe`, `SessionEnd` `other` fired 60,049 ms later at A's current cwd, the lock was released, and A left the loaded list. `daemon stop` ended B the same way. | 116–124 |

## Proposed controller arrangements

These are the arrangements the Issue's feasibility gate decides on, to be
approved or rejected before implementation. Each is narrower than "every observed session": a session
is movable only when it was launched into the arrangement, and Cleanup must
still block on every other occupant.

**Claude Code.** Dashpot ships a channel server, and a session opts in at
launch by loading it (`--dangerously-load-development-channels
server:dashpot` today, with its per-launch confirmation; a distributed plugin
channel later). Dashpot registers the channel by the `CLAUDE_CODE_SESSION_ID`
its process receives and refuses to move any session without a live channel.
The only supported move is `ExitWorktree` back to the launch directory, which
is why the arrangement pairs with Dashpot's own dispatch: a session that
started in the main Worktree and entered the Issue Worktree with
`EnterWorktree` can return; a session launched directly in the Worktree
cannot, and is reported as such rather than moved. Preflight requires the
session `idle` in `agents --json` — a queued event runs only after the current
turn, and a background job leaves the listing `busy` — and completion is the
`PostToolUse` for `ExitWorktree` with the destination cwd plus the channel
`ack`, corroborated by the listing.

**Codex.** Dashpot connects to the managed daemon's control socket under the
operator's `CODEX_HOME`. Reach is wider than authority: `thread/loaded/list`
reported every terminal the fixture launched while the daemon ran, plain ones included,
but the Issue's rule stands — a daemon Dashpot can reach is not control of an
unrelated Codex client — so the arrangement moves only a thread that opted
in, which needs a registration the experiment did not design: the open
decision here is what counts as opt-in (a terminal Dashpot launched, an Issue
Binding declared from the thread, or an explicit marker), not whether the
daemon can reach the rest. The move is `thread/resume` to subscribe, then one
`turn/start` with the destination `cwd` on an `idle` thread with an empty
`thread/backgroundTerminals/list`; the override sticks for the terminal's
later turns. Preflight must refuse a thread whose `status` is not `idle`: a
`turn/start` then joins the running turn and its input executes in the old
directory. The controller must `thread/unsubscribe` afterwards, or the thread
outlives its terminal. Completion is the controller turn's `Stop` at the
destination cwd plus `thread/read` reporting it, which is attributable only
because the turn was started on an idle thread. This is a live-thread
relocation, a new lifecycle contract beside the sequential `codex resume`
route of
[ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md),
not a transparent implementation of it; the Issue's sequential-resume checks
were not exercised here. The
[declared-relocation experiment](codex-declared-relocation-daemon-spike.md)
exercised them the next day and found the sequential route relocates a
daemon-hosted thread correctly, loaded or unloaded.

## Implications for Dashpot

- Neither move changes session identity: Claude keeps `session_id` and pid,
  Codex keeps the thread id and daemon pid. Preserving an Agent Run through a
  move needs no new identity mapping, only the location update that
  [`work_reconciliation.py`](../src/dashpot/sessions/work_reconciliation.py)
  already completes from Codex relocation evidence.
- A Codex terminal's shells and hooks descend from the daemon, not from the
  terminal process. `is_codex_host_process` still matches, but the terminal
  pid a person sees is not the host of anything the hooks report.
- The daemon's loaded list carries ephemeral helper threads; a listing that
  counts occupants must filter `ephemeral`.
- Claude's `EnterWorktree` and `ExitWorktree` publish no dedicated hook; the
  `PostToolUse` of the tool, with the new cwd, is the first evidence of the
  move, and the next turn's hooks carry it.
- Of the research note's
  [acceptance list](cleanup-session-handoff-research.md#disposable-acceptance-needed-before-enabling-automatic-removal),
  this run covers the controller identity and origin/destination of item 1,
  the drain signals of item 3, the fresh destination hooks of item 4, and the
  direct-launch and isolated-session refusals of item 5. Untouched: an active
  Agent Run and Issue Binding through a move (item 2), a conversation canary
  and effective permissions at the destination (item 4), a Claude subagent
  and concurrent Codex clients on one thread (item 5), refusal, timeout,
  cancellation, and partial moves (item 6), and the final reinspection before
  removal (item 7).

## Validation

Both retained traces pass their independent verifiers, all 204 and 125
records, and the recorded source hashes match the retained experimental files.
Node syntax checks pass for every module. No dependency lockfile or production
code changed.
