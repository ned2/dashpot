---
status: research
date: 2026-10-05
---

# OpenCode v2 background commands, default permissions and failed executions

The experiment for [Issue #379](https://github.com/ned2/dashpot/issues/379)
measures the OpenCode 2.0.22 scenarios the
[acceptance run](../../README.md#harness-acceptance-runs) left out, on the
shared service and, where it applies, `--standalone`:

- a model's background shell command, which outlives the execution that
  started it;
- `opencode run` under a person's default permission rules, which ask for
  some tools, with and without `--auto`, and a worker's
  `opencode run --session <lead>` report starting a lead turn that asks;
- retried and failed executions.

Each finding below is marked **measured**, checked by the verifier against
the retained trace, or **documented**, read from the
[2.0.22 source](https://github.com/anomalyco/opencode/tree/v2.0.22). The run
builds on the [OpenCode v2 experiment](opencode-v2-spike.md), the
[worker mechanics experiment](opencode-v2-worker-mechanics-spike.md) and the
[self-relocation acceptance run](opencode-v2-self-relocation-acceptance.md),
and does not repeat their findings. It changes nothing in Dashpot's code: it
fixes OpenCode's support boundary in
[OpenCode hosting modes](../agent-sessions.md#opencode-hosting-modes).

## Reproduce

The runner needs Node built-ins, Git, `uv`, and the OpenCode **2.0.22** binary.
It is a separate runner on the pinned release, as the #421 and #423 runs
are, because the acceptance runner in `opencode-163/` also needs the 2.0.21
and 1.18.30 binaries for its version scenarios. The binary is copied into
the fixture, so the operator's own installation is never run in place. The
runner starts its own service on a private port, with disposable
configuration and state, a proxy that reaches nothing but loopback, and
autoupdate disabled. It never contacts the operator's service. No model
credentials are needed: a loopback OpenAI-compatible provider returns tool
calls, or HTTP errors, to OpenCode's real execution loop. The runner builds
Dashpot from the checkout into a fixture environment, and from that
installation `dashpot integrate opencode` installs the plugin, the skills and
the `dashpot-worker` agent.

The runner refuses to start below a harness session. From the assigned
Dashpot checkout, detach it with `setsid -f`:

```bash
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-379/run.mjs \
  <absolute opencode 2.0.22 binary> > run.log 2>&1
node scripts/experiments/opencode-379/verify.mjs <fixture root>/trace.jsonl
```

The run takes about three minutes and is done when its log prints
`All scenarios completed`. The verifier needs no network; `--strict` also
fails it when the Dashpot sources the run exercised have changed since.

- The [runner](../../scripts/experiments/opencode-379/run.mjs) creates a
  Dashpot Project with a markdown Issue Source, twelve Issues and three
  linked Worktrees, `a` to `c`. It serves the fixture model and drives the
  service through its HTTP API and CLI, and `opencode run` as a client.
- The [shell reporter](../../scripts/experiments/opencode-379/command.mjs)
  and [ancestry reader](../../scripts/experiments/opencode-379/ancestry.mjs)
  report each shell's identity variables, directory, pid and ancestry
  around the `dashpot` or `opencode` command it runs.
- After each step the runner records OpenCode's server events, the
  background command's process, OpenCode's list of running shells, the hook
  and Work Store records of every Worktree, an observation, and a Cleanup
  preview of the Worktree involved.
- The [independent trace verifier](../../scripts/experiments/opencode-379/verify.mjs)
  checks each measured claim below.
- The [retained trace](measurements/issue-379-opencode-trace.jsonl) holds
  317 records. The first holds the SHA-256 hashes of the binary, the
  runner's scripts and the Dashpot sources the run exercised. Fixture and
  binary paths appear as `$ROOT` and `$BINARY_DIR`.

## Tested configuration and evidence boundary

- **Versions.** OpenCode 2.0.22 on Linux x64 (binary SHA-256
  `32cf5aa0…5ad122`), Node 24.18.0.
- **Dashpot.** The run's checkout was `9f7a1e9` with this change's scripts.
  The trace records the SHA-256 of every source the run exercised, and
  `verify.mjs --strict` fails unless the checkout's sources still match.
- **Service and clients.**
  - Sessions are root sessions created through the HTTP API on the shared
    service, an `opencode run` against it, and one `opencode run
    --standalone`. A TUI is not driven: an ask a TUI would show the person
    is stood in for by one the runner answers through the API.
  - Every model turn is the fixture's.
- **Configuration.** The global configuration allows every tool until
  `background-stop`, which restarts the service with no permission rules,
  OpenCode's defaults, for every later scenario. Project configuration is
  disabled with `OPENCODE_DISABLE_PROJECT_CONFIG`.
- **Scenarios**, in order: `installer`, `background`, `background-move`,
  `background-interrupt`, `background-delete`, `retry`, `failed`,
  `background-stop`, `run-default`, `ask-pending`, `worker-report`,
  `standalone-background`.

## Findings

### Background shell commands

A shell tool call with `background: true` runs its command apart from the
session's executions. Dashpot observes the session, not the command.

**Measured.**

- **The call returns at once.** Its result is `Command moved to the
  background (shell ID: sh_…)`, with the file its output streams to, and
  the execution that made it succeeded before the command ended.
- **The process.** The command is a child of the service, in a process group
  and session of its own, running in the session's Worktree.
- **What Dashpot shows while it runs.** Dashpot shows the session
  **waiting**, as between any two executions. A Cleanup preview of the
  Worktree names the live session and its run, because the session is
  there, not because of the command.
- **The end wakes the session.** When the command ended, OpenCode started a
  new execution of the idle session carrying the notice
  `<shell id="sh_…" state="completed" …>` and the command's output; once
  that execution ended, Dashpot read the session waiting.
- **OpenCode lists it.** `GET /api/shell` with the location header
  `x-opencode-directory` lists the running command at the location it
  started in, with its session and its pid. The `directory` query parameter
  did not select the location: that form listed nothing.
- **A move leaves it behind.** The session moved to the main Worktree while
  its command ran on in Worktree `b`. The bound run moved with the session,
  as a Live Relocation, and a Cleanup preview of `b` named nothing,
  although the command still ran there. OpenCode kept listing the command at `b`, not at
  the session's new location. Its end woke the session where the session
  now was.
- **An interruption kills the foreground command only.** Interrupting the
  session ended its execution as `interrupted` with reason `user` and killed
  its foreground command. The background one ran on, and its end woke the
  session.
- **A deletion leaves it running.** The command outlived its deleted
  session and ran to its end. Dashpot ended the bound run with the
  session, a Cleanup preview of Worktree `c` named nothing while the
  command ran there, and no notice was delivered, since the session was gone.
- **Stopping the service kills it.** `opencode service stop` killed the
  running command. The service started again neither resumed the command
  nor woke the session; the session's next turn carried the notice
  `state="cancelled"`, `Command cancelled because the server restarted`.
- **`--standalone` loses it.** An `opencode run --standalone` exited as soon
  as its turn ended, while its background command ran, and the command died
  with the client's private server, never reaching its end.

**Documented.**

- A background command has no timeout of its own: the shell tool's
  `timeout` defaults to none for it, and OpenCode keeps no cap on how many
  run.
- OpenCode's API removes a listed command with `DELETE /api/shell/<id>`.
  No model tool lists or stops one.
- A running command publishes no session event, so it does not renew its
  location's hour of inactivity
  ([idle eviction](opencode-v2-spike.md#idle-eviction)). What the eviction
  does to it is not settled: the eviction interrupts only the location's
  executing sessions, and an interruption leaves a background command
  running, as measured above. The location's shell service, released with
  the location, kills the commands it still holds, so the command likely
  dies once nothing else holds the location, without a notice.

**Consequences for Dashpot.**

- An execution's end does not mean the session's work has drained, and
  neither the dashboard's waiting state nor `dashpot work show` says that a
  background command still runs. The session's own record of what it
  started, the notices, and OpenCode's shell list are the evidence.
- Cleanup does not see a background command. A session that leaves its
  Worktree, or is deleted, while its command runs frees the Worktree for
  Cleanup with the command still running in it. Before finishing Issue
  work, a session waits for every background command it started; the
  [Issue-work skill](../../src/dashpot/skills/dashpot-issue-work/SKILL.md#finish-the-engagement)
  already requires every process it started to be done.
- A `--standalone` client's exit stops its background commands with its
  server, so a long command belongs on the shared service.

### `opencode run` under default permissions

With no `permissions` key, OpenCode's rules allow every tool except some it
asks for: a path outside the session's location, and reading `.env` files
(documented). The run uses a `read` of `.env`, which the rules ask for
before the file is opened.

**Measured.**

- **Without `--auto`, `run` rejects.** It printed
  `! permission requested: read (.env); auto-rejecting` and rejected the ask
  with a message telling the model to continue without the action. The
  tool failed as `permission.rejected`, the turn went on to its next step,
  and `run` exited 0.
- **What Dashpot shows.** The run's session was bound in Worktree `c` and
  read waiting once its turn ended. After `run` exited, the session stayed
  live on the service, and a Cleanup preview of `c` named it and its run,
  as for any `run` session on the shared service.
- **With `--auto`, `run` approves.** It answered the same ask `once`.
- **An unanswered ask.** A session whose ask no client answered, as one a
  TUI shows the person, read **running** in Dashpot for as long as the ask
  waited: the execution stays open. Answering it through the API resumed the
  turn, which then ended, and Dashpot read waiting.
- **A worker's report.** A worker reporting to its idle lead with
  `opencode run --session <lead>` from a background shell, as the
  `dashpot-execute-issues` skill directs, started a lead turn that asked.
  The worker's `run` rejected the lead's ask, the lead's turn went on
  without the action, and the report exited 0. No ask was left for the
  person.

**Documented.**

- `run` answers every ask in its own session and in that session's
  children, and never prompts, whatever its stdin. A lead's workers are its
  children, so while a worker's report runs, an ask a worker raises is
  rejected too.
- `--auto` approves every ask the rules do not deny; a `deny` rule still
  refuses without asking. `--yolo` is a hidden alias.
- An ask waits with no timeout of its own. A client's exit leaves it
  pending; interrupting the session drops it; closing the location rejects
  it.

**Consequences for Dashpot.** An unattended `opencode run` never hangs on
an ask: it rejects it, or with `--auto` approves it. A lead turn that a
worker's report starts has its asks rejected, measured without a TUI
attached to the lead, so the lead acts on a report needing an approval in a
turn the person can answer. The
[execute-issues skill's OpenCode notes](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#opencode)
say so.

### Retried and failed executions

**Measured.**

- **A retry stays inside its execution.** The provider answered 500 twice.
  OpenCode published `session.retry.scheduled` for each, with the error
  type `provider.internal`, within one execution, then succeeded on the
  third request. Dashpot read the session running through the retries and
  waiting after.
- **A failure ends the execution.** The provider answered 400. OpenCode made
  one request, published `session.execution.failed` with the error type
  `provider.invalid-request` and status 400, and scheduled no retry. Dashpot
  read the session waiting, and its Agent Run kept its Issue Binding.
- **`run` exits 1** when its execution fails, printing the provider's
  error.

**Documented.**

- OpenCode retries a 429, a 408, a 409, a 5xx, a transport error and an
  incomplete stream, after 2, 4 and 8 s and then every 10 s, up to ten
  retries, longer when the provider's `retry-after` asks. Exhausted retries
  end the execution as `failed`, as a 400 does.
- A shell command that exits non-zero is a successful tool call, not a
  failed execution.

**Consequences for Dashpot.** Dashpot's translation needs no change: a
retrying session is running, and a failed execution reads waiting, as the
[hosting modes](../agent-sessions.md#opencode-hosting-modes) say.

## Not measured

Each for its reason:

- **A TUI**: its ask shown to the person, a worker's report reaching a lead
  whose TUI is attached, and its change of directory, which the source says
  moves the session. The runner drives no terminal, and the Issue-work
  skill uses the model's own move instead
  ([ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)).
- **Exhausted retries, a `retry-after` delay, and a malformed or cut
  stream.** Each ends as a retry or a `failed` execution, the two outcomes
  measured, so Dashpot's reading does not depend on which.
- **A background command removed with `DELETE /api/shell/<id>`.** Only the
  API removes one, never a model tool, and no Dashpot or skill flow calls
  it.
- **A background command past the hour's eviction.** The eviction needs an
  hour of idle service per run, as the
  [idle run](opencode-v2-spike.md#idle-eviction) did; the skills already
  keep gates that long outside OpenCode.
- **`--server <url>`, ACP, and the web, desktop and editor clients**, which
  [#455](https://github.com/ned2/dashpot/issues/455) owns.

## Validation

`node scripts/experiments/opencode-379/verify.mjs
docs/spikes/measurements/issue-379-opencode-trace.jsonl --strict` reports
`ok` for all 23 claims, and that the Dashpot sources match the run's.
