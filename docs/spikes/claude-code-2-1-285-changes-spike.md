---
status: research
date: 2026-09-30
---

# Claude Code 2.1.285 changes experiment

The experiment for [Issue #345](https://github.com/ned2/dashpot/issues/345)
measures the Claude Code changes from **2.1.280** to **2.1.285** that touch
Dashpot's Claude Code integration, on 2.1.285 and, for comparison, on 2.1.280.
Dashpot's integration was last measured on 2.1.278 by the
[Cleanup handoff feasibility experiment](cleanup-session-handoff-feasibility-spike.md).
The reusable facts live in the maintained
[server and client reference](../agent-harness-server-client-reference.md#changes-after-21278);
this document is the dated evidence record with its fixtures and traces.

No measured change breaks a contract Dashpot relies on. The hook events, their
`session_id`, the shell's `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`, and the
supervised worker's versioned executable name are as measured at 2.1.276. Four
findings bear on Dashpot:

1. On 2.1.285, `claude --resume <id>` with no session-configuring flag opens a
   session that runs in the background: the terminal's process becomes a
   `claude attach` client and the turn runs in the worker, which publishes its
   hooks. With `--model`, alone or with `--dangerously-skip-permissions`, it
   is refused, as 2.1.280 refuses every form.
2. A refused `claude -p --resume <id>` publishes `SessionEnd` for the running
   session's id from its own process, on both versions. While Dashpot does
   not identify the worker, that ends the worker's Agent Run in the Work Store.
3. In auto mode a sub-agent that ends without handing its report back
   publishes four `SubagentStop` for one `SubagentStart`.
4. A non-interactive `claude --bg` in an untrusted directory now exits
   without a session, while a sibling linked Worktree of a trusted main
   working tree inherits its trust.

This is evidence for the shared lifecycle design, not an accepted ADR or a
changed Harness Adapter. It makes no changes to Dashpot's Work Store,
Issue-work commands, installation, or dashboard.

## Reproduce

The retained experiment uses Node built-ins, Git, `script` from util-linux, and
an installed Claude Code. The runner rejects a Claude Code version other than
2.1.285 unless a second argument names it, and the verifier takes the same
optional argument; it records claims for 2.1.285 and 2.1.280 only. No model
credentials or external model service are needed: a deterministic loopback
Messages API returns tool calls to the real Claude Code execution loop.

From the assigned Dashpot checkout, with the launcher symlink named `claude`:

```bash
node scripts/experiments/claude-345/run.mjs "$(command -v claude)"
node scripts/experiments/claude-345/verify.mjs /tmp/dashpot-claude-345-SUFFIX/trace.jsonl
```

Replace the second path with the exact fixture path printed by the runner.
For the comparison, point a symlink named `claude` at the 2.1.280 executable
that the native installer keeps under `~/.local/share/claude/versions/`, and
pass `2.1.280` as the second argument of both commands. Each run takes about
three minutes. A symlink named `claude` keeps the executable name of the
interactive and headless processes `claude`, as the launcher gives them, so
the comparison with supervised processes is measured rather than assumed. A
sandbox that blocks loopback needs a command-scoped exception for the runner.
The verifier needs no network.

- [Runner and trace receiver](../../scripts/experiments/claude-345/run.mjs)
  creates the fixture, serves the mock Messages API, drives headless,
  interactive, and background clients, and records outcomes without asserting
  them.
- [Hook publisher](../../scripts/experiments/claude-345/hook.mjs) posts the
  identity fields of every configured hook event, the `CLAUDE*` environment,
  and the hook process's ancestry. It does not import Dashpot or write Project
  state.
- [Shell reporter](../../scripts/experiments/claude-345/command.mjs) is the only
  Bash command the fixture model issues; it posts the executing shell's cwd,
  `CLAUDE*` environment, and ancestry.
- [Ancestry reader](../../scripts/experiments/claude-345/ancestry.mjs) walks
  `/proc` upwards and stops at the runner, so the operator's own session above
  it stays out of the trace.
- [Opener stand-in](../../scripts/experiments/claude-345/opener.mjs) replaces
  `xdg-open`, `gio`, `open`, and the browser launchers on the fixture's `PATH`
  and records any launch `--desktop` attempts.
- [Independent trace verifier](../../scripts/experiments/claude-345/verify.mjs)
  checks the emitted evidence against the claims below without importing the
  runner or publisher. It recomputes each claim from the raw hook, command,
  process, model-request, and client-exit records inside its scenario, and
  requires the runner's summary records to agree with them.
- Retained traces contain the complete metadata stream of each successful
  run: [2.1.285](measurements/issue-345-claude-2.1.285-trace.jsonl) with 423
  records and [2.1.280](measurements/issue-345-claude-2.1.280-trace.jsonl) with
  417. The first record of each includes SHA-256 hashes of the six
  experimental source files. The runner writes the disposable fixture root
  as `$ROOT` and the experiment directory as `$EXPERIMENT` in the retained
  stream; it evaluates every observation against the real paths.

The runner creates a new `dashpot-claude-345-*` root under the temporary
directory with three Git fixtures: a Repository whose main working tree
directory the fixture configuration trusts, with a `nested` subdirectory; a
sibling linked Worktree at `repository.worktrees/sibling`, where Dashpot
places Issue Worktrees, with no trust entry of its own; and an unrelated
Repository whose directory has none. Claude Code records trust per directory.
These are disposable experiment resources, not Issue Worktrees. The runner
supplies an allowlisted child environment with an isolated home, XDG
directories, temporary directory, and `CLAUDE_CONFIG_DIR`; disables the
auto-updater, telemetry, error reporting, and non-essential traffic; and seeds
the isolated `.claude.json` with completed onboarding, accepted bypass
permissions, an approved fixture API key, trust for the main working tree,
and the cached prompt-suggestion flag, which only a session given
`CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF=1` reads. No ordinary
configuration, credentials, saved conversations, Git metadata, or sibling
Worktrees are copied or modified, and the runner only ever signals processes
whose environment names the fixture `CLAUDE_CONFIG_DIR`.

The runner stops the fixture supervisor, kills any process it left behind,
and closes both loopback servers in `finally`. It retains its fixture for
inspection; prefix the runner command with `SPIKE_REMOVE_FIXTURE=1` to delete
the root that run created. `SPIKE_ONLY` narrows a run to scenarios whose names
start with a listed prefix (`resume-running-background` runs all of scenario
3), and `SPIKE_DEBUG_TERMINAL=1` and `SPIKE_DEBUG_REQUESTS=1` retain terminal
output and model requests inside the fixture for diagnosis; neither is part of
the retained evidence.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-09-30 |
| Dashpot base | `89fa70c0af47fbd366bfa6403363a308360c6994` |
| Claude Code binaries | Native installer launcher symlink, `--version` = `2.1.285 (Claude Code)`; a symlink named `claude` to the installed `2.1.280` executable |
| Operating system | Linux `7.0.0-34-generic`, x86-64 |
| Controller | Node `v24.18.0` |
| Headless clients | `claude -p --output-format json` under `--dangerously-skip-permissions` and `--permission-mode auto`; `-p --resume`; `--setting-sources project,local` |
| Interactive clients | `claude` under `script` with `TERM=xterm-256color`, `--resume <id>` with and without a prompt and with and without session-configuring flags, `--desktop [--resume <id>]` |
| Background clients | `claude --bg --name`, `--bg --resume <id>`, `agents --json [--all]`, `stop`, `daemon stop --any`, in trusted and untrusted directories |
| Model | Loopback Messages API selected by `ANTHROPIC_BASE_URL`: streaming for turns, JSON for the auto-mode classifier, which it always allows |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionEnd`, each a user-scope `command` hook |
| Other flags | Exact isolation flags in trace record 1 and the runner's `env` object |

Only metadata crosses the experimental observation boundary: hook event names
and their identity fields (`session_id`, `cwd`, `source`, `reason`, `agent_id`,
`agent_type`, `prompt_id`, `tool_name`, `tool_use_id`, `permission_mode`,
`stop_hook_active`, `model`, `old_cwd`, `new_cwd`), the names of the other
payload keys, the `CLAUDE*` environment without `CLAUDE_CODE_MESSAGING_TOKEN`,
process ancestry, job listings, command exit status, the tail of each client's
output, and any launcher invocation. The mock model records the fixture label,
request counts, advertised tool names, the opening words of the system prompt,
and the opening words of a user message or tool result that is not a fixture
marker. Transcripts, tool inputs, the fixture credential, and full
environments are not retained. Claude Code's own disposable data under the
fixture root can contain the synthetic conversation; it is not part of the
retained evidence.

Which resume forms open a running session is read from the 2.1.285
executable's JavaScript source as well as measured. The open path runs only
on a terminal, only when the client's options carry no session configuration
— `--model`, `--permission-mode`, `--dangerously-skip-permissions`,
`--settings`, `--setting-sources`, `--agent`, `--mcp-config`, `--add-dir`, and
others — only while the agents view is enabled (neither
`CLAUDE_CODE_DISABLE_AGENT_VIEW` nor the `disableAgentView` setting disables
it), only when the client is not itself a background session, and only while
the `tengu_resume_open_live_bg` gate, on by default, allows it. The
runner measured the refusal with `--model` alone and with it and the bypass
flag, and the open path with no flag; the other options in that list were not
run.

Parts of Issue #345 stay unmeasured, each for a stated reason:

- **Resuming a mid-turn background session, and detaching.** The runner
  resumed the worker only while it was idle, after its turn's `Stop`; a
  prompt forwarded to a worker mid-turn is not measured. `/exit` in the opened
  session does not detach, and the key that does was not identified; the
  runner closed the client by ending its terminal.
- **The interactive trust prompt.** Only the non-interactive `claude --bg`
  refusal in an untrusted directory was measured, not the prompt an
  interactive session shows there.
- **The desktop app.** `--desktop` is refused on Linux before it launches
  anything; its behaviour on macOS and Windows is not measured.
- **`--setting-sources` forwarding.** The 2.1.281 fix forwards the restriction
  to teammates, `/bg`, `claude agents` sessions, and `--worktree --tmux`. The
  runner measured a restricted session and a directly dispatched worker, which
  already dropped user-scope hooks on 2.1.280, not the spawned sessions.
- **The unmatched `SubagentStop`.** A live 2.1.285 session recorded a
  `SubagentStop` with no `SubagentStart` shortly after the main turn's `Stop`.
  No interactive turn in the fixture reproduced it, whether or not the session
  read the cached prompt-suggestion flag, and in auto mode. Its source is
  unidentified.

An interactive auto-mode session in the fixture stalls at its first tool call
on both versions, presumably waiting for the server-side classifier the
loopback fixture does not serve. In exploratory runs, whose traces are not
retained, it made no progress within the runner's wait of up to 180 seconds,
and sent its local classifier request only after the runner typed `/exit`.
The runner gives that variant `CLAUDE_CODE_AUTO_MODE_SERVER=0` so the local
classifier runs at once; the
`claude -p` runs in auto mode did not stall. Other operating systems, other
releases, Remote Control, the Agent SDK, agent teams, and cloud sessions remain
untested.

## Scenario results

Trace references are the `receipt` field of the 2.1.285 trace, then the
2.1.280 trace; one range means both agree.

| Scenario | Observed result | Evidence |
| --- | --- | --- |
| Sub-agents under bypass | A foreground, a `run_in_background`, and a text-only sub-agent each publish one `SubagentStart` and one `SubagentStop` with the parent's `session_id`, `CLAUDE_PID`, and their own `agent_id` and `agent_type`. `SubagentHandback` is not offered. In `-p` the parent's first `Stop` fires while the sub-agent works, and its report arrives as a new `UserPromptSubmit` turn with its own `Stop` before `SessionEnd`, on both versions. | 2–70 |
| Sub-agents in auto mode, handing back | The sub-agent is offered `SubagentHandback`, calls it, and publishes one `SubagentStop`. On 2.1.285 the sub-agent makes two model requests and the parent one notification turn; on 2.1.280 the sub-agent makes a third request after its handback and the parent answers the report with two notification turns, each a `UserPromptSubmit` and a `Stop`. | 71–126; 71–134 |
| Sub-agent in auto mode, text only | A sub-agent that ends without calling `SubagentHandback` is re-prompted three times with "[handback-send-enforce] Your report has not been delivered". Each attempt ends with a `SubagentStop` for the same `agent_id`: four in all, the first with `stop_hook_active` = false and the rest true, for one `SubagentStart`. Both versions. | 127–158; 135–166 |
| Interactive turns | On a pseudo-terminal a turn publishes `SessionStart` `startup` through `Stop` from the terminal's `claude` process. Nothing fired and no model request followed in the ten seconds after `Stop`, whether or not the session read the cached prompt-suggestion flag, and in auto mode. | 159–204; 167–212 |
| Background session | `claude --bg --name fixture-bg` runs its turn in a worker whose executable is named after its version (`2.1.285`, `2.1.280`); the job listing names the worker's pid and `session_id`. | 205–223; 213–231 |
| Interactive resume while running, with a session-configuring flag | `claude --resume <id>` with a prompt, bare, each with `--dangerously-skip-permissions --model`, and with `--model` alone exits 1 with no hook and the worker alive. 2.1.285: "That session is running in the background (`<id>`). Run `claude attach <id>` to open it, or `claude stop <id>` first to resume it here. Add --fork-session to branch off a copy instead." 2.1.280 says the session "is running as a background session". | 224–247; 232–255 |
| Headless resume while running | `claude -p --resume <id>` exits 1 with the same refusal on stderr and runs no turn, but publishes `SessionEnd` `reason` = `other` for the running session's `session_id`, carrying its own pid as `CLAUDE_PID`. The worker keeps running. Both versions. | 248–254; 256–262 |
| Background resume while running | `claude --bg --resume <id>` exits 0 and starts a copy: "session `<id>` is already running in the background, so this started a copy as `<new>`". The copy has a new `session_id` and pid and `SessionStart` `source` = `fork`. Both versions. | 255–272; 263–280 |
| Interactive resume while running, with no flag | 2.1.285: `claude --resume <id>`, with a prompt or with one typed once it opens, replaces its process with `claude attach <job>`, named after its version. The prompt runs as a turn in the idle worker: `UserPromptSubmit` through `Stop` with the worker's `session_id` and `CLAUDE_PID`, no `SessionStart`, and a shell descending from the worker. `/exit` leaves the client running `claude agents`; a pre-warmed spare publishes `SessionStart` `startup` and later `SessionEnd` `other` for a session of its own, and closing the client publishes `SessionEnd` `other` from the client's pid for a session id that never started. Nothing is published for the worker's session, which stays idle. 2.1.280 refuses both forms, exit 1, no hook. | 273–326; 281–304 |
| Resume after stop | `claude stop <id>` publishes `SessionEnd` `other` from the worker pid; an interactive `--resume <id>` then continues the conversation with `SessionStart` `source` = `resume` from the terminal's own `claude` process, and its shells report that pid. Both versions. | 327–342; 305–320 |
| `--desktop` | 2.1.285 with redirected output: "--desktop opens the Claude Desktop app and can't run non-interactively". On a terminal, with or without `--resume`: "--desktop isn't available on this platform. It works on macOS and Windows (x64)." Exit 1, no launcher invoked, no hook. 2.1.280: `unknown option '--desktop'`. | 343–356; 321–331 |
| `--bg` workspace trust | Dispatch into the `nested` subdirectory of the trusted main working tree and into its sibling linked Worktree starts a session and runs its hooks on both versions. Into the unrelated Repository's untrusted directory, 2.1.285 exits 1 with "Workspace not trusted. Run `claude` in `<dir>` once and accept the trust prompt, then retry." and starts no session, with or without the bypass flag; 2.1.280 starts the session and runs its hooks there. | 357–394; 332–385 |
| `--setting-sources project,local` | A `-p` session and a `--bg` worker both run their command and publish no hook for their session. Both versions. | 395–412; 386–403 |

After `daemon stop --any`, five `bg-pty-host` processes of pre-warmed spares
outlived the supervisor on 2.1.285 and six on 2.1.280 until the runner killed
them, as the 2.1.276 experiment found.

## Implications for Dashpot

- The refused headless resume's `SessionEnd` names a live session, from a
  process Dashpot identifies as a Claude Code host. The hook record store
  keeps the worker's record: it ignores a `SessionEnd` whose `sessionProcess`
  differs from the one it recorded, and a replay through `HookRecordStore`
  kept the record whether the worker was unidentified, as today, or
  identified, as [#326](https://github.com/ned2/dashpot/issues/326) proposes.
  The Work Store does not. `publish_hook_event` reconciles the Work Store
  before the hook record, and `end_session_runs` ends a run of the same
  session at any Worktree of the Repository unless the run recorded a
  different process. A run started from a background worker records no
  process, because Dashpot does not identify the worker, so a replay through
  `end_session_runs` ended it; with a recorded worker process it kept the run.
  So today, `claude -p --resume <id>` against a background worker that holds
  Issue work, anywhere in that Repository, ends the Issue work while the
  worker runs on. The finding is recorded on #326, whose identification of
  the worker has since closed it
  ([supervised worker process experiment](claude-code-supervised-worker-process-spike.md#implications-for-dashpot));
  a replay test keeps a located worker's run through such a `SessionEnd`.
- Dashpot's Orphaned Agent Run resume command, `cd <location> && claude
  --resume <id>`, carries no session-configuring flag, so on 2.1.285 it opens
  a session still running in the background rather than being refused, unless
  the person has disabled the agents view. The
  turn it sends runs in the worker, which keeps publishing the session's hooks
  with its own `CLAUDE_PID`; the `claude attach` client publishes nothing for
  the session and is named after its version, so Dashpot would not take it
  for a host process either. The command is offered for a run whose process
  is gone, so this matters only for a background worker Dashpot does not
  identify, the gap #326 covers.
- Leaving an opened session through `/exit` shows the `claude agents` view,
  where a pre-warmed spare publishes `SessionStart` for a session of its own
  until the client closes. Its hooks carry the Repository's cwd, so Dashpot
  would show that session there as a running Agent Session for that time. The
  `SessionEnd` the client publishes for a session that never started finds no
  record to remove.
- The repeated `SubagentStop` of an auto-mode sub-agent that does not hand
  back removes the agent from `liveSubagents` at the first stop; the later
  ones find nothing to remove. Replayed through `HookRecordStore`, the
  session stayed `running` through the re-prompts and became `waiting` only at
  the parent's final `Stop`. A `SubagentStop` with no `SubagentStart` after a
  `Stop`, as seen live, left the session `waiting`.
- An Issue Worktree is a sibling linked Worktree of the main working tree, so
  the 2.1.281 trust check does not stop `claude --bg` from being dispatched
  into one when the main working tree is trusted.
- A session started with `--setting-sources` that excludes `user` runs none of
  the hooks `dashpot integrate claude-code` installs, so Dashpot sees only its
  process; this held on both versions and is not new.

## Validation

Both retained traces pass the independent verifier (423 records on 2.1.285,
417 on 2.1.280), and their recorded source hashes match the retained
experimental files. Node syntax checks pass for all six modules. Copies of
the 2.1.285 trace with three of the four enforcement `SubagentStop` records
removed, with the resumed `SessionStart` `source` changed to `startup`, with
the untrusted `--bg` dispatch given exit 0, or with an opened session's
`UserPromptSubmit` attributed to another process each fail the verifier. The
hook record replays used Dashpot's `HookRecordStore`, and the Work Store
replays `end_session_runs`, in a temporary directory; neither is retained. No
dependency lockfile or production code changed.
