---
status: research
date: 2026-10-01
---

# Claude Code supervised worker process experiment

The experiment for [Issue #326](https://github.com/ned2/dashpot/issues/326)
measures what `ps` reports for every process Claude Code's background
supervisor runs, on the installed **2.1.285**, so that Dashpot can locate a
supervised worker as a Claude Code host without also taking the supervisor,
a PTY host, or an unrelated process for one. The
[identity and lifecycle experiment](claude-code-identity-lifecycle-spike.md)
measured the supervised topology at 2.1.276 from `/proc`, keeping the first six
arguments of each process; this one probes each process with the `ps` columns
Dashpot's process adapter reads, in full, and follows a worker through an
abrupt exit, an explicit respawn, and a later dispatch. The reusable facts live
in the maintained
[server and client reference](agent-harness-server-client-reference.md#measured-supervisor-and-worker-lifecycle-at-21276);
this document is the dated evidence record with its fixtures and trace.

Every supervised process is named after the version, and three argument
vectors belong to a worker: the versioned executable with `--session-id` when
it is spawned for a new session, the same with `--resume <transcript>` when
the supervisor replaces a worker that died, and `claude bg-spare` when it
claimed a pre-warmed spare. `claude respawn` and a later dispatch both landed
in a claimed spare, so a respawned worker is recognised only if the spare
shape is. Each worker process, claimed spares included, hosted exactly one
session. The supervisor and every PTY host have their own shapes, and a PTY
host's argument vector carries its worker's whole command after `--`, so only
the start of the vector distinguishes the two.

## Reproduce

The retained experiment uses Node built-ins, Git, and an installed Claude Code.
The runner rejects a Claude Code version other than 2.1.285 unless a second
argument names it, and the verifier takes the same optional argument. No model
credentials or external model service are needed: a deterministic loopback
Messages API returns tool calls to the real Claude Code execution loop.

From the assigned Dashpot checkout, with the launcher symlink named `claude`:

```bash
node scripts/experiments/claude-326/run.mjs "$(command -v claude)"
node scripts/experiments/claude-326/verify.mjs /tmp/dashpot-claude-326-SUFFIX/trace.jsonl
```

Replace the second path with the exact fixture path printed by the runner. The
run takes about thirty-five seconds. A sandbox that blocks loopback needs a
command-scoped exception for the runner; the verifier needs no network.

- [Runner and trace receiver](../scripts/experiments/claude-326/run.mjs)
  create the fixture, serve the mock Messages API, drive the background
  clients, and probe each fixture process with `ps -o pid=,ppid=,lstart=,comm=`
  and `ps -o args=` in the C locale and UTC, as
  [`host_process_lookup`](../src/dashpot/sessions/processes.py) does. Each
  process a hook or shell names by `CLAUDE_PID` is probed while that hook or
  shell runs.
- The [hook publisher](../scripts/experiments/claude-326/hook.mjs),
  [shell reporter](../scripts/experiments/claude-326/command.mjs), and
  [ancestry reader](../scripts/experiments/claude-326/ancestry.mjs) are the
  #345 experiment's, unchanged but for the publisher's header comment.
- [Independent trace verifier](../scripts/experiments/claude-326/verify.mjs)
  checks the recorded shapes against the claims below without importing the
  runner, the publisher, or Dashpot.
- [Retained trace](measurements/issue-326-claude-trace.jsonl) contains the
  complete metadata stream from the successful run: 77 records. Its first
  record includes SHA-256 hashes of the five experimental source files. The
  fixture root, the experiment directory, and the operator's home directory
  appear as `$ROOT`, `$EXPERIMENT`, and `$HOME`.

The runner isolates Claude Code as the #160 and #345 runners do: a new
`/tmp/dashpot-claude-326-*` root holds an independent Git Repository, a linked
fixture Worktree, and an allowlisted environment with an isolated home, XDG
directories, temporary directory, and `CLAUDE_CONFIG_DIR`, with the
auto-updater, telemetry, error reporting, and non-essential traffic disabled.
It only probes or signals processes whose environment names the fixture
`CLAUDE_CONFIG_DIR`, stops the fixture supervisor, kills every fixture process
left behind, and records that none remains. `SPIKE_REMOVE_FIXTURE=1` deletes the
fixture root after the run. The supervisor's socket directory
`/tmp/cc-daemon-<uid>/<hash>/` is left to Claude Code.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-01 AEST; the trace's `lstart` values are UTC, 2026-09-30 |
| Dashpot base | `473edcfb47570c697cae952efd6cee0991fc23c1` |
| Claude Code binary | Native installer launcher symlink to `~/.local/share/claude/versions/2.1.285`, `--version` = `2.1.285 (Claude Code)` |
| Operating system | Linux `7.0.0-34-generic`, x86-64, procps `ps` |
| Controller | Node `v24.18.0` |
| Background clients | `claude --bg --name`, `agents --json`, `stop`, `respawn`, `daemon stop --any` |
| Model | Loopback Messages API streaming fixture selected by `ANTHROPIC_BASE_URL` |
| Hooks | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd`, each a `command` hook |

Beyond the metadata the #160 experiment retains, the trace keeps each probed
process's `ps` identity columns and full `args`. A worker's `args` include its
synthetic `SPIKE:` prompt and the path of its fixture transcript, not the
transcript itself.

macOS is unmeasured: the experiment host runs Linux only. Dashpot's probe reads
`comm` on macOS as the executable's full path, whose last component would be
the version if the native installer lays out its versions there as on Linux;
that, and whether macOS `args` shows the same vectors, is inferred, not
measured.

## Scenario results

| Scenario | Result | Trace records |
| --- | --- | --- |
| First dispatch | `claude --bg` starts a transient supervisor, `$HOME/.local/share/claude/versions/2.1.285 daemon run --origin transient --spawned-by {…}`, reparented to pid 1. Worker A is spawned directly as `…/versions/2.1.285 --session-id <sessionId> <prompt> --name fixture-a …` below its PTY host, `claude bg-pty-host --bg-pty-host <daemon>/pty/<job>.sock 200 50 -- …/versions/2.1.285 --session-id <sessionId> …`. At the same time the supervisor pre-warms a spare, `claude bg-spare --bg-spare <daemon>/spare/<id>.claim.sock`, below a PTY host whose vector ends `-- …/versions/2.1.285 --bg-spare`. | 2–10 |
| Second dispatch | Worker B, in the other Worktree, runs in the pre-warmed spare's process: its hooks and shell carry the spare's pid as `CLAUDE_PID`, `agents --json` lists that pid, and its `args` are still `claude bg-spare …`. The supervisor pre-warms another spare. | 11–30 |
| Abrupt worker exit | SIGKILL of idle worker A: about ten seconds later `SessionStart` `source` = `resume` arrives from a new pid whose `args` are `…/versions/2.1.285 --resume $ROOT/claude-config/projects/<project>/<sessionId>.jsonl --name fixture-a …`, below a new PTY host for the same job socket. No `SessionEnd`. | 31–37 |
| Explicit stop and respawn | `claude stop` publishes `SessionEnd` `other` from worker B's pid; `claude respawn` resumes the session in the pre-warmed spare, which publishes `SessionStart` `source` = `resume` with its `claude bg-spare …` vector unchanged. | 38–48 |
| Third dispatch | Worker C also runs in a claimed spare. | 49–64 |
| Supervisor stop | `daemon stop --any` ends every worker with `SessionEnd` `other`; four PTY hosts outlive it, reparented to pid 1, until the runner kills them. | 65–76 |

Across the run, every probed supervised process has `comm` `2.1.285`; the
worker shells and the reporter below them have `bash` and `MainThread`. The
five processes a hook or shell named by `CLAUDE_PID`, three dispatched workers
and two replacements, all have worker shapes: one spawned directly, one
resumed, three claimed spares. Each hosted exactly one `session_id`. A direct worker's
`--session-id` equals its hooks' `session_id`, and a resumed worker's
transcript is named after it. Neither the supervisor nor any PTY host was ever
named by `CLAUDE_PID`, and six of the PTY host observations carried
`--session-id` or `--resume` after `--`. A spare's vector is the same before
and after it is claimed, so the vector says only that a process is a worker,
not which session it hosts.

## Implications for Dashpot

- **Recognition rule.** `is_claude_code_host_process` in
  [`harnesses.py`](../src/dashpot/sessions/harnesses.py) keeps accepting a
  process named `claude`, the headless and interactive path, unchanged. A
  process with a version-shaped name is accepted only when its `args` begin
  with `claude bg-spare --bg-spare `, or with an absolute path ending
  `/claude/versions/<that version>` followed by `--session-id` or `--resume`.
  The supervisor, the PTY hosts, the `agents` and `attach` clients measured by
  the [2.1.285 changes experiment](claude-code-2-1-285-changes-spike.md), and a
  versioned executable started without a worker flag are not hosts. The
  vector is evidence of the process's role, never of its session: identity
  still comes from the hook's `session_id` and the shell claim, validated
  against the hook record.
- **Spares are supported.** A spare the supervisor dispatches a session to
  hosts that one session for its whole life, like any worker, so ADR 0053's
  exclusive-process condition holds for it. A spare no session was dispatched
  to ran no hook or shell here, so no walk reached one. The
  [2.1.285 changes experiment](claude-code-2-1-285-changes-spike.md) saw a
  spare publish `SessionStart` `startup` and later `SessionEnd` for a session
  of its own while the `claude agents` view was open, without `agents --json`
  ever listing it; located now as that session's host, it too hosted exactly
  one session. That every spare hosts at most one session is inferred from
  these traces, not documented.
- **A replaced worker continues its run.** A worker the supervisor replaces
  after an abrupt exit publishes no `SessionEnd`, and its replacement is a
  located host with a new pid at the same Worktree, so
  [ADR 0053](adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
  continues its Agent Run. The measured replacement had the `--resume` shape.
  `claude stop` publishes `SessionEnd` from the worker being stopped, which
  ends a run started from it, so the session the measured `claude respawn`
  resumed in a spare has no run to continue. A respawn, or a replacement in a
  spare, after an abrupt exit is unmeasured; it would continue the run too,
  since the spare shape is located.
- **A foreign `SessionEnd` no longer ends a worker's run.** A run started from
  a located worker records the worker's process, so the `SessionEnd` a refused
  `claude -p --resume <id>` publishes from its own process for the worker's
  session leaves the run alone, the gap the
  [2.1.285 changes experiment](claude-code-2-1-285-changes-spike.md#implications-for-dashpot)
  found.
- The rule depends on the native installer's layout and on undocumented
  process shapes. A future release that changes them leaves a worker
  unlocated, which is the behaviour before this change, never a supervisor
  taken for a host.

## Validation

The retained trace passes the independent verifier, and its recorded source
hashes match the retained experimental files. `ps` confirmed after the run
that no fixture supervisor, PTY host, or worker remained.
