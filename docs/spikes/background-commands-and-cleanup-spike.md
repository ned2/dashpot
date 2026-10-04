---
status: research
date: 2026-10-05
---

# Background commands and Cleanup experiment

The experiment for [Issue #466](https://github.com/ned2/dashpot/issues/466)
measures what becomes of a Background Command when its session moves,
`/clear`s, exits or is deleted, and what Cleanup names afterwards. A
Background Command is a command a harness leaves running after the turn
that started it. The run checks Dashpot's `process` Cleanup blocker
([ADR 0104](../adr/0104-block-worktree-removal-while-a-process-runs-inside-it.md))
after each step. The harnesses measured are:

- a Claude Code 2.1.289 `run_in_background` Bash command;
- a Codex 0.160.0 background terminal;
- an OpenCode 2.0.22 `background: true` shell command.

For each one, the run asks:

- whether the command outlives the turn and the session;
- whether its working directory stays in the Worktree;
- whether `dashpot worktree check --json` names it there.

[ADR 0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md)
records the decisions these measurements support.

Each runner builds the same fixture:

- a disposable Dashpot Project with linked Worktrees `a` and `b`;
- a loopback model fixture;
- an isolated harness configuration with its updater off;
- the pinned binary, run read-only through a fixture-local `PATH` symlink;
- the runner launched with `setsid -f` outside every harness process, as the
  [agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires.

The model starts the command in Worktree `a`. The command reports its pid,
parent, process group, session, working directory and identity environment,
then holds on a gate file that the runner opens. Every hook went to Dashpot's
real publisher, run from the #466 working tree over `6edef5c`.

After each step, the runner recorded the command's process state, the hook
records Dashpot stored, and the `worktree check` report of both Worktrees.
For each `process` blocker, it kept the pids the blocker named. The traces
are metadata only, with paths rewritten to placeholders.

The fixture's pseudo-terminal host (`script` and its `sh`) and an
interactive client launched in `a` are processes in `a` too. The `process`
blocker names them beside the command, just as it would name a person's
terminal.

## Claude Code 2.1.289

Runner [`claude-466`](../../scripts/experiments/claude-466/), trace
[`issue-466-claude-trace.jsonl`](measurements/issue-466-claude-trace.jsonl)
(179 records, SHA-256
`e6cd5bd76b571f3a2e5a3cf5fb7407095ecf6030267671d63fa73aa7c00ea727`).
[`verify.mjs`](../../scripts/experiments/claude-466/verify.mjs) checks the
claims below, 13 checks in all. Receipt numbers are the trace's.

- **The command.** The command is a child of a `bash` that the Host Process
  starts. That shell leads its own process session and group. The command's
  environment names the session (`CLAUDE_CODE_SESSION_ID`) and the Host
  Process (`CLAUDE_PID`) (#11).
- **`turn-end`.** The turn's `Stop` lists the command in `background_tasks`
  as `type` `shell` and `status` `running` (#12). The session was stored
  `waiting`. Worktree `a` was blocked by the session and by a `process`
  blocker naming the shell and the command (#13). The blocker gave the
  command's name as `MainThread`, the name Node gives its main thread, so
  only its `ps -ww` line shows it is `node command.mjs`. The Codex and
  OpenCode traces show the same name. The command's end woke the
  session with a task-notification `UserPromptSubmit` (#17). That turn's
  `Stop` listed no background task (#20), and the blocker no longer named
  the command (#22).
- **`move`.** `EnterWorktree` moved the session to `b` (#42). The command
  went on in `a`, and the `Stop` at `b` still listed it running (#44).
  Worktree `a` held only a `process` blocker naming the command, and `b`
  held the session and its Host Process (#45). The command's end woke the
  session at `b` (#49).
- **`clear`.** `/clear` ended the session (#72) and started another from the
  same Host Process (#73). The command went on, its environment still naming
  the ended session. Worktree `a` was blocked by the new session and by a
  `process` blocker naming the command (#76). The command's end woke the new
  session (#80).
- **`exit-stop`.** `/exit` opened a dialog: "Background work is running. The
  following will stop when you exit". It offered "Exit and stop tasks", "Move
  to background and exit" and "Stay". The first option ended the command
  with the client (#105, #106), and Worktree `a` was removable (#108).
- **`exit-background`.** "Move to background and exit" (#129) published a
  `SessionStart` with `source` `fork` and a new session id. It came from
  another Host Process, a background session under a transient daemon
  (#132), and it was followed by the first session's `SessionEnd`
  `prompt_input_exit` (#133). The daemon took a new entry under
  `/tmp/cc-daemon-<uid>/` (#136), and `claude agents` listed the fork as
  `background` (#138). The command went on in `a`. Its shell was reparented
  to pid 1, and its environment named the ended session. Worktree `a` was
  blocked by the fork's session and by a `process` blocker naming the
  command and the fork's Host Process (#139). The command's end woke the
  fork (#143). `claude daemon stop --any` ended the fork (#154) and removed
  its entry (#156).
- **`headless`.** `claude -p` published its `Stop` with the command running
  (#166), then exited with status 0 without waiting (#167). The command
  ended with it, and Worktree `a` was removable (#169). Its record stayed
  `waiting`, since a headless exit publishes no `SessionEnd`.

The entry already under `/tmp/cc-daemon-<uid>/` before the run stayed, and
no fixture process outlived the run (#177, #178).

## Codex 0.160.0

Runner [`codex-466`](../../scripts/experiments/codex-466/), trace
[`issue-466-codex-trace.jsonl`](measurements/issue-466-codex-trace.jsonl)
(166 records, SHA-256
`ce61b9d67fa6440e2f076c9c3eded4f66b07f46e030134197b4018bba24d7601`).
[`verify.mjs`](../../scripts/experiments/codex-466/verify.mjs) checks the
claims below, 10 checks in all. The fixture model calls `exec_command` with
a `yield_time_ms` of one second, which leaves the command running as a
background terminal.

- **The command.** The command is a direct child of the Codex process that
  hosts the thread, and it leads its own process session and group. Its
  environment names the thread (`CODEX_THREAD_ID`) (#9).
- **`turn-end`.** The turn's `Stop` came while the command ran (#11). No
  payload of the four events Dashpot subscribes to that fired carries a field
  about a background terminal. The session was stored
  `waiting`, and Worktree `a` was blocked by it and by a `process` blocker
  naming the command (#14). The command's end started no turn: no hook
  arrived (#15–#19).
- **`cd`.** `/cd` to `b` while the command ran left the session where it was.
  The next prompt's hooks carried the same session and `a` (#38–#43), and
  the command kept running in `a` (#44). The terminal's screen was not
  captured, so the refusal itself is not in the trace. By the
  [harness reference](../agent-harness-server-client-reference.md), Codex
  lists an active background terminal among `/cd`'s preconditions. After the command
  ended, the same `/cd` started a `source` `fork` session with a new id in
  `b` (#51), and the next prompt ran there (#57).
- **`clear`.** `/clear` started a session with `source` `clear` and a new id,
  and the first thread published no `SessionEnd` (#77). Both sessions were
  stored `waiting` and both blocked Worktree `a`, beside a `process` blocker
  naming the command (#85). The command's environment named the first
  thread. Both sessions ended only when the terminal exited (#92, #93).
- **`exit`.** `/exit` ended the command with the terminal (#109, #110), and
  Worktree `a` was removable (#113).
- **`daemon`.** The command was started from a terminal attached to the
  managed daemon with `--remote`, and the daemon process ran it (#121,
  #127). After the terminal exited (#133), the command went on. Worktree
  `a`'s `process` blocker named it alone, beside the still-loaded session
  (#135). About 60 s later the daemon unloaded the thread, with `SessionEnd`
  `other` (#136), and the command was gone, so `a` was removable (#138).
- **`exec`.** `codex exec` ended its turn and exited while the command ran
  (#152–#154). The command ended with it, and Worktree `a` was removable
  (#156).

No fixture process outlived the run (#164). The daemon left one lock file
in the shared `/tmp/codex-daemon-<uid>/`, which the run lists but never
removes (#165).

## OpenCode 2.0.22

Trace [`issue-466-opencode-trace.jsonl`](measurements/issue-466-opencode-trace.jsonl)
(317 records, SHA-256
`1a7404597263044fdce407adb114cf937e3aa320af50d383eeb7d4eb1c54f247`) is a
rerun of the unchanged
[`opencode-379`](../../scripts/experiments/opencode-379/) runner. The runner
was not extended. Its background scenarios already move and delete a
session while its command runs, and record a Cleanup report of the
Worktree. Since ADR 0104, those reports carry the `process` blocker.
[`opencode-466/verify.mjs`](../../scripts/experiments/opencode-466/verify.mjs)
checks the rerun, 6 checks in all. It checks that the trace came from the
#379 runner as retained, and it checks the claims below. The #379 verifier's
own claims that Cleanup named nothing after a move or a delete predate ADR
0104, and they fail on this trace by design.

- **`background`.** While the waiting session's command ran in `a` (#25,
  #26), Cleanup of `a` named the session, its Agent Run, and a `process`
  blocker naming the command (#30). The command's end woke the session (#32).
- **`background-move`.** The session moved to the main checkout (#57, #61)
  while its command ran on in `b` (#62). Cleanup of `b` named only a
  `process` blocker, and it named the command (#67). The command's end woke
  the session where it moved (#69).
- **`background-delete`.** The session was deleted (#112, #114) while its
  command ran on in `c` (#115). Cleanup of `c` named only a `process`
  blocker, and it named the command by pid and command name (#119). The
  command's end woke nothing (#121).
- **The shell listing.** `GET /api/shell` with the Worktree in the
  `x-opencode-directory` header named the command, its pid and its session.
  It still did so after the session was deleted (#116). The same query with
  a location query parameter listed nothing (#27, #63, #116).

## What the measurements show

- Each harness's Background Command outlives its turn and keeps working in
  the Worktree where it started. The `process` blocker names it there by
  pid in every case: the session may wait, move away, `/clear`, exit to the
  background, or be deleted, and the command is still named. A Worktree
  becomes removable once the command ends.
- The harness ends the command with its host in five cases: Claude Code's
  "Exit and stop tasks", a Codex terminal's `/exit`, the daemon unloading
  the thread, a headless `claude -p`, and `codex exec`.
- The command's own claim to an owner goes stale. A Claude Code command's
  environment names the session that started it, even after a `/clear` or an
  exit to the background has ended that session. Its shell can be reparented
  to pid 1. OpenCode's listing still names a deleted session.
- A Claude Code or OpenCode command's end wakes its session by itself. A
  Codex command's end does not. Only Claude Code reports the running command
  in a hook Dashpot subscribes to, through `Stop`'s `background_tasks`.

Not measured:

- a Claude Code `/resume` or `/branch` while a command runs;
- Codex's `/stop`, which stops every background terminal;
- an OpenCode shell event in its event stream, since the #379 runner
  records only session, permission and retry events;
- macOS, whose scan goes through `lsof`.

## Reproduce

From a checkout of the Worktree, outside every harness process. The runs
used a private `TMPDIR` for the fixture roots:

```sh
TMPDIR=<private dir> setsid -f node scripts/experiments/claude-466/run.mjs ~/.local/share/claude/versions/2.1.289 > claude-466.log 2>&1
TMPDIR=<private dir> setsid -f node scripts/experiments/codex-466/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/codex > codex-466.log 2>&1
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-379/run.mjs ~/.opencode/bin/opencode > opencode-466.log 2>&1
node scripts/experiments/claude-466/verify.mjs docs/spikes/measurements/issue-466-claude-trace.jsonl --strict
node scripts/experiments/codex-466/verify.mjs docs/spikes/measurements/issue-466-codex-trace.jsonl --strict
node scripts/experiments/opencode-466/verify.mjs docs/spikes/measurements/issue-466-opencode-trace.jsonl --strict
```

Each runner prints its fixture root, and that root's `trace.jsonl` is the
trace. `--strict` also fails once a Dashpot source the run hashed has
changed since. `SPIKE_SCENARIOS` runs a subset of the Claude Code and Codex
scenarios.
