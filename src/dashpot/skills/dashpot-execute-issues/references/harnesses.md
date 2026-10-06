# Worker mechanics by harness

Reference for [dashpot-execute-issues](../SKILL.md). Read the section for
the harness your session runs in. Each one says how to launch, message,
wait for, resume and stop a worker, how a worker reports, where a worker's
reviewer runs, and the fallback where a mechanism is missing. The brief
template's `{REPORTING}` placeholder takes the worker-side text from here.

In every harness:

- A worker's shell starts in your directory, and a `cd` lasts for one
  command. Every command in a brief needs its own `cd <path> && …`, and
  file edits use absolute paths.
- Dashpot attributes a worker to your Agent Session. Your session reads
  `running` while any worker works, and Cleanup's `sub-agent` blocker holds
  every Worktree of the repository until each worker's stop is recorded.
- You assign each worker to its Issue by the ID Dashpot's hooks know it by
  ([Assign each worker](../SKILL.md#assign-each-worker)). Each section's
  **Worker ID** says where you get it.
- A worker sees the skills installed for its harness, but needs none of
  them: its brief carries what it needs.

## Claude Code

**Invoke** the skill with `/dashpot-execute-issues`. Its
`disable-model-invocation: true` hides it from the model.

**Launch.** Call `Agent` with a `description`, a short `prompt` pointing at
the brief, and `run_in_background: true`. The call returns at once with the
worker's agentId; address the worker by that ID. Your turn goes on.

**Worker ID.** The agentId. Assign the worker by it once the launch returns.

**Capacity.** `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` caps the workers
running at once. A launch past the cap fails with "Concurrent subagent
limit reached … Do not retry". Queue the rest, and launch each one as a
running worker hands back.

**Worker reports.** A worker calls `SendMessage` with `to: "main"`. An idle
lead gets a new turn with the message; a busy one gets it at its next tool
round. `{REPORTING}`: "To tell the lead something mid-flight, call
SendMessage with `to: "main"`, then carry on. Your final message is your
hand-back."

**Messaging a worker.** `SendMessage` to its agentId arrives at the
worker's next tool round.

**Completion.** A `<task-notification>` wakes you, with `status`
`completed` and the worker's final message as its `result`. A status of
`stopped`, `killed` or `failed` is a hand-back with no report: treat it as
a blocker.

**Resume.** `SendMessage` to a finished worker's agentId resumes it with
its whole transcript, and a second notification follows when it finishes
again.

**Stopping a worker.** Avoid `TaskStop`: it publishes no stop to Dashpot,
which leaves the `sub-agent` blocker up until your session ends. It also
leaves the worker's Issue reading `running` until you unassign it. Message
the worker to stop and hand back instead. A headless host that interrupts you stops
your workers without telling you; treat a worker you never hear from again
as a blocker.

**Exiting.** If you must `/exit` with workers running, choose "Exit and
stop tasks", or "Stay". "Move to background and exit" forks a new session
that holds no Issue work, and stops the workers. In that fork, bind again
with `dashpot-issue-work` and relaunch the workers on their briefs.

**Location.** With you in the main checkout, Claude Code refuses a
worker's `EnterWorktree` and `ExitWorktree`, so a worker cannot move your
session with them. From a lead already inside a linked Worktree that was
not measured, which is one more reason the brief forbids moving any
session.

**Reviewer.** A worker launches the reviewer as its own sub-agent with
`Agent`. If its `Agent` tool is unavailable, it asks you, and you launch
the reviewer as a separate worker.

## Codex

**Invoke** the skill with `$dashpot-execute-issues`. Its
`agents/openai.yaml` sets `allow_implicit_invocation: false`, which hides
it from the model.

**Run the lead on a multi-agent v2 model.** Codex gives a thread its
sub-agent tools when it starts. A model whose catalog entry has
`multi_agent_version` `v2` gives you and your workers the `collaboration`
tools; `codex debug models --bundled` shows each model's version. The
`[features] multi_agent_v2` flag gives them to you alone: a worker on a
model without v2 gets no tools to report with. Any other model gets v1, the
fallback below.

**Check your sandbox before you bind.** Your workers run under your
session's sandbox, with its writable directories, and nothing you pass
when you launch one changes either. Under `workspace-write`, a writable
directory keeps its own `.git` read-only, so:

- a worker can edit its Worktree only when your session can write the
  **Worktree Root**, the directory Dashpot creates Worktrees in. It is
  `<main checkout>.worktrees`, beside the main checkout, unless
  `DASHPOT_WORKTREE_ROOT` or the user's `worktree_root` setting names
  another; with the network on,
  `<dashpot> worktree create <n> --dry-run --json` prints it as
  `worktreeRoot`;
- `git commit` and `git worktree add` in a linked Worktree write the main
  checkout's Git directory, which
  `git rev-parse --path-format=absolute --git-common-dir` prints, so no
  agent of your session can commit there, or create a Worktree, unless
  that directory is writable too;
- pushing and `gh` need network access;
- the tools the repository's gates run write caches, which must be
  writable too. uv writes `~/.cache/uv` and pre-commit
  `~/.cache/pre-commit` unless `UV_CACHE_DIR` and `PRE_COMMIT_HOME` name
  another directory. Where a repository uses them, a worker without them
  can edit and push but cannot prepare its environment, run its gate, or
  commit through a hook that runs either, and the refused write shows only
  as a failed command in the shell that tried it. Other tools write
  elsewhere, such as the Pythons uv installs itself, under
  `~/.local/share/uv`.

Check all four from where you will bind:

```bash
touch <Worktree Root>/.execute-issues-check && rm <Worktree Root>/.execute-issues-check
touch <Git directory>/execute-issues-check && rm <Git directory>/execute-issues-check
git ls-remote --exit-code origin HEAD
echo "UV_CACHE_DIR=$UV_CACHE_DIR PRE_COMMIT_HOME=$PRE_COMMIT_HOME"
```

The fourth passes when the cache of each of those tools the repository's
gates use is writable: inside the Worktree Root, or under a directory your
session was given as writable, as `--add-dir ~/.cache` gives their default
locations. Without the sandbox, every check passes. The first three pass
under the grant below without the caches, so run the fourth whatever they
say. `git ls-remote` also fails without credentials: read its error before
you blame the sandbox. If a check fails for the sandbox, or the fourth
does, stop before binding.
Ask the user to create the Worktree Root if it does not exist yet, exit
this client, and resume your session with both directories writable, the
network on, and the caches in the Worktree Root:

```bash
codex resume <session-id> -C <checkout> --sandbox workspace-write --add-dir <Worktree Root> --add-dir <Git directory> -c sandbox_workspace_write.network_access=true -c 'shell_environment_policy.set.UV_CACHE_DIR="<Worktree Root>/.cache/uv"' -c 'shell_environment_policy.set.PRE_COMMIT_HOME="<Worktree Root>/.cache/pre-commit"'
```

Drop the option for a tool the repository does not use, and add one for
each other cache its gates write. `<session-id>` is the Agent Session
identity `<dashpot> integrate codex --status` confirms, and `<checkout>`
the one you will bind in; a new session takes the same options after
`codex`. This resume command is measured on Codex 0.160.0 on Linux: it
gives you and every worker these writable directories with the network
on, and your workers' shells and their Git hooks the two cache locations,
so a worker completes its whole cycle. Your own shell gets them by the
same setting, though that was not measured, so still run the four checks
again in the resumed session before you bind.
`--sandbox workspace-write` matters: under `read-only`, Codex refuses
`--add-dir` and the client exits. Tell the user that Codex's background
app-server may hold this thread for about a minute after this client
exits. Until then the resumed client shows the conversation read-only,
says it is open in another app, and retries when they press `r`. If the
resumed session does not start on a prompt given on the command line,
they type it again.

`--add-dir ~/.cache` in place of the two cache options also completes a
worker's cycle, but it lets every agent of the session write every tool's
cache, and code planted in one runs the next time that tool runs outside
the sandbox. Tell the user, as you ask, what the Git directory
costs: every agent of the session can then write its hooks and its
configuration, and code planted there runs the next time anything runs
`git` outside the sandbox, Dashpot's dashboard included. They may run the
session without the sandbox (`--sandbox danger-full-access`) instead, where
nothing is refused and every check passes. Your checkout is your
session's workspace, so your workers, under your sandbox, can write it,
and their files in your arc's ledger need nothing more.

Under the `on-request` approval policy, a refused write still fails as a
command. Only a command the agent asks to run outside the sandbox raises
an ask, and only the user can answer it, in your terminal, a worker's
included. If they decline a worker's ask while your turn has ended, that
worker's turn ends too and its report never comes. What a worker's ask
does to a turn of yours that is waiting on it is not measured.

**Stay in your turn.** Codex never starts a turn for an idle lead, neither
for a worker's message nor for its completion. While any worker runs, keep
your turn going with the wait loop below. If the turn ends or is
interrupted, nothing re-enters it until the user sends a new message.

**Keep a client attached.** A daemon-hosted lead with no client attached is
unloaded about 60 s later, while its workers go on working. Dashpot then
ends your Issue work and your workers' assignments
([Known Dashpot gaps](../SKILL.md#known-dashpot-gaps)). Ask the user to keep
the client open until every worker has finished.

**Launch (v2).** `spawn_agent` with a `task_name` and a `message` pointing
at the brief. It returns at once with the worker's path, `/root/<task_name>`.

**Worker ID (v2).** The path is not the ID Dashpot's hooks know. A worker's
shell holds its own thread ID in `CODEX_THREAD_ID`, and the worker's first
message reports it. Assign the worker by it when that message arrives in
your wait loop.

**Capacity.** A session holds 3 open workers by default. A finished worker
holding unread mail keeps its slot. A launch past the limit fails with
"agent thread limit reached". Raise the limit with `[agents] max_threads`
in the user's Codex configuration, with their agreement; otherwise queue.

**Wait loop (v2).** Call `wait_agent` with a `timeout_ms` of up to
3 600 000. It returns on any mail: a worker's message or a worker
finishing. Read the mail, act on it, and wait again, until every worker has
handed back. When a wait times out or your turn was interrupted, call
`list_agents`: it shows each resident worker's status and final text.

**Worker reports (v2).** `{REPORTING}`: "Before anything else, call
`send_message` to `/root` with `worker-id: ` followed by the output of
`echo "$CODEX_THREAD_ID"`. To tell the lead something mid-flight, call
`send_message` to `/root`, then carry on. Run each gate, commit and push as
a command of its own, so that the lead's messages reach you between them.
Your final message is your hand-back."

**Messaging a worker (v2).** `send_message` to a worker's path queues the
message for it. A running worker gets it at its next model request, which
comes when the command it is running ends, so broadcast with
`send_message` alone. A busy lead gets its mail at its next model request,
and mail to a finished worker only queues.

**Completion (v2).** The worker's final message reaches your history as a
`FINAL_ANSWER` message from its path, and `list_agents` shows it
`completed`.

**Resume (v2).** `followup_task` to a finished worker starts a new turn
with its earlier context. `send_message` to a finished worker only queues.

**Fallback: v1.** On a model without v2, `spawn_agent` returns an
`agent_id`, which is the worker's ID to assign, and `wait_agent` takes `targets` and `timeout_ms` and returns
each finished worker's final text. A v1 session holds 6 workers by default,
through the same `[agents] max_threads`. Workers have no tool to message
you, so they report in their files in your arc's ledger
([Worker files](arc-ledger.md#worker-files)). `{REPORTING}`: "You cannot
message the lead. To tell it something mid-flight, append an entry to
`<arc directory>/workers/<worker name>.md` with one command,
`{ date -u '+### %FT%TZ'; cat <<'EOF'; } >> <arc directory>/workers/<worker name>.md`, followed by your report, opening with your key line, then a line
`-- end`, then the line `EOF`. Write nothing else outside your Worktree.
Before each gate run, commit and push, read `<arc directory>/broadcast.md`
if it exists: the lead appends its broadcasts there, and an entry without
its `-- end` line is still being written. Your final message is your
hand-back." Read the worker files between waits, and broadcast by
appending to `broadcast.md`. Resume a finished worker with `send_input`.

**Stopping a worker.** `interrupt_agent` on a worker mid-command publishes
no stop, which leaves the `sub-agent` blocker up until your session ends,
and the worker's Issue reading `running` until you unassign it. Use it only
on a worker that has gone quiet; otherwise `followup_task` it
with an instruction to stop and hand back. A worker is a sub-agent of your
thread, not a `codex exec` process of its own, so no signal reaches it
alone, and the SIGINT rule below for a `codex exec` does not apply to it.

**A lead under `codex exec`.** If your own session is a `codex exec`, it
stops cleanly only on SIGINT (Ctrl-C), which publishes `SessionEnd` and
ends your run. SIGTERM and SIGKILL publish nothing: your run stays,
orphaned, and Cleanup's `agent-run` blocker keeps the checkout you bound
in. To recover, resume your thread in that checkout, run `<dashpot> work
start` with your Issue again, and assign every live worker again
([Assign each worker](../SKILL.md#assign-each-worker)). Only when the user
asks to end that run instead, run `<dashpot> work stop --session
<session-key>` in that checkout, where `<dashpot> work show` identifies the
orphaned run.

**Location.** No tool a worker holds moves your session, and Dashpot
refuses a Codex worker's `work` commands that would change your Issue work,
as running in a sub-agent.

**Reviewer.** A v2 worker can `spawn_agent` its reviewer, but each spawn
counts against the session's limit. With the default limit and a full
wave, launch the reviewer yourself between workers, or raise the limit. A
v1 worker has no spawn tool, so you launch its reviewer.

## OpenCode

Dashpot supports OpenCode v2.

**Invoke** the skill by naming it in the prompt's `skills` input. Its
`opencode/autoinvoke: false` metadata hides it from the model's list. How
the TUI invokes a skill was not measured: there, name the skill in your
request and confirm the model loaded it before going on.

**Lead only on the shared service.** While you set up, before you bind,
read the `OpenCode Host Process mode` line of
`<dashpot> integrate opencode --status`. Lead only when it reads
`shared-service`. On `unknown`, run it once more first, since a busy
machine can leave the server unread. On `standalone` or `unknown`, stop
before binding or launching any worker, and ask the user to start the
lead again with a plain `opencode`, without `--standalone`, which runs it
on their shared OpenCode service. A worker's report is a client of that shared service: to a
`--standalone` lead, whose session its client's private server also serves,
the shared service and your client's private server would both run your
session at once, which has not been measured.

**Launch.** Call `subagent` with `agent: "dashpot-worker"`, a
`description`, a short `prompt` pointing at the brief, and
`background: true`. It returns at once with the worker's `sessionID`.

**Worker ID.** The `sessionID`. Assign the worker by it once the launch
returns. Dashpot records a worker working only while it runs, so between
the runs you resume, its Issue reads idle.

`dashpot-worker` is the worker agent `<dashpot> integrate opencode` installs.
It removes the session-move tool, so a worker cannot move your session by
mistake. It does not stop a determined process, which can still move a
session through OpenCode's HTTP API. If the agent is missing, ask the user
to run `<dashpot> integrate opencode` from the environment that holds their
hooks. Until then, launch workers with the `general` agent, add to each
brief "Never move any session, your own or the lead's", and run
`<dashpot> work show` after each worker ends to confirm your session and
its Issue work are still where you bound.

**Capacity.** OpenCode sets no worker limit. Size waves by the machine.

**Your session ID.** Workers report to you by your session's ID. Read it
from the `Agent Session identity claimed here` line of
`<dashpot> integrate opencode --status`, and put it in the wave block.

**Worker reports.** `{REPORTING}`: "To tell the lead something mid-flight,
run `opencode run --session <lead-session-id> "<message>"` in a background
shell (the shell tool's `background: true`), then carry on: the command
waits until the lead's turn ends. If it fails, append an entry to
`<arc directory>/workers/<worker name>.md` with one command,
`{ date -u '+### %FT%TZ'; cat <<'EOF'; } >> <arc directory>/workers/<worker name>.md`, followed by your report, opening with your key line, then a line
`-- end`, then the line `EOF`. Write nothing else outside your Worktree.
Your final message is your hand-back." Read the worker files
([Worker files](arc-ledger.md#worker-files)) at the start of each turn of
yours and whenever a worker's report is overdue. Whether OpenCode asks
permission for that write outside the worker's Worktree is not measured; a
rejected ask leaves you only its hand-back.

**A report's turn.** A lead turn that a worker's report starts cannot ask
the person: the report's `opencode run` rejects every permission ask the
turn raises, and the turn goes on without the action. While a report runs,
an ask any worker raises is rejected too. Act on a report that needs an
approval in a turn the person can answer.

**Completion.** A `<subagent sessionID="…" state="completed">` message
carrying the worker's final text wakes you, whether you were idle, busy or
interrupted. A state of `error` or `cancelled` is a blocker.

**Resume.** `subagent` with the worker's `sessionID` continues it with its
history. Only you, its parent, can. A prompt to a running worker steers it.

**Long commands.** A foreground shell times out after 2 minutes, so a
worker runs its gates and CI watches in background shells, or with
`timeout: 0`. A foreground shell that runs for about an hour with no other
session event is interrupted, and what that hour does to a background
shell is unmeasured, so a gate that long runs outside OpenCode. A
background shell outlives the turn that started it, and neither Dashpot
nor Cleanup sees it, so a worker waits for its background shells before
handing back. Add these to the brief's gotchas.

**Stopping.** Deleting your session deletes its running workers. Stopping
the OpenCode service stops every session.

**Reviewer.** A worker cannot launch its own sub-agent: OpenCode's nesting
depth defaults to 1, and raising it changes every session of the service.
Launch each worker's reviewer yourself as a separate worker, giving it the
worker's base, branch and evidence, and forward its findings. If you cannot,
the worker reviews inline with the same prompt and says so in its PR.
