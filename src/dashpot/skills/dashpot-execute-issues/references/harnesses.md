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
- A worker sees the skills installed for its harness, but needs none of
  them: its brief carries what it needs.

## Claude Code

**Invoke** the skill with `/dashpot-execute-issues`. Its
`disable-model-invocation: true` hides it from the model.

**Launch.** Call `Agent` with a `description`, a short `prompt` pointing at
the brief, and `run_in_background: true`. The call returns at once with the
worker's agentId; address the worker by that ID. Your turn goes on.

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
which leaves the `sub-agent` blocker up until your session ends, and
Dashpot's wording for that blocker is one of the
[Known Dashpot gaps](../SKILL.md#known-dashpot-gaps). Message the worker
to stop and hand back instead. A headless host that interrupts you stops
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

**Stay in your turn.** Codex never starts a turn for an idle lead, neither
for a worker's message nor for its completion. While any worker runs, keep
your turn going with the wait loop below. If the turn ends or is
interrupted, nothing re-enters it until the user sends a new message.

**Keep a client attached.** A daemon-hosted lead with no client attached is
unloaded about 60 s later, while its workers go on working (see
[Known Dashpot gaps](../SKILL.md#known-dashpot-gaps)). Ask the user to keep
the client open until every worker has finished.

**Launch (v2).** `spawn_agent` with a `task_name` and a `message` pointing
at the brief. It returns at once with the worker's path, `/root/<task_name>`.

**Capacity.** A session holds 3 open workers by default. A finished worker
holding unread mail keeps its slot. A launch past the limit fails with
"agent thread limit reached". Raise the limit with `[agents] max_threads`
in the user's Codex configuration, with their agreement; otherwise queue.

**Wait loop (v2).** Call `wait_agent` with a `timeout_ms` of up to
3 600 000. It returns on any mail: a worker's message or a worker
finishing. Read the mail, act on it, and wait again, until every worker has
handed back. When a wait times out or your turn was interrupted, call
`list_agents`: it shows each resident worker's status and final text.

**Worker reports (v2).** `{REPORTING}`: "To tell the lead something
mid-flight, call `send_message` to `/root`, then carry on. Before each
commit and each push, read the file `execute-issues-lead` in your
Worktree's Git directory (`git -C <path> rev-parse --absolute-git-dir`) if
it exists: the lead writes its broadcasts there. Your final message is your
hand-back."

**Messaging a worker (v2).** `send_message` to a running worker's path
queues the message for it. Its delivery to a running worker was not
measured: Codex delivers the lead's mail at its next model request, and
mail to a finished worker only queues. So also write each broadcast to the
file `execute-issues-lead` in the worker's Worktree Git directory
(`git -C <path> rev-parse --absolute-git-dir`), which the worker reads
before each commit and push.

**Completion (v2).** The worker's final message reaches your history as a
`FINAL_ANSWER` message from its path, and `list_agents` shows it
`completed`.

**Resume (v2).** `followup_task` to a finished worker starts a new turn
with its earlier context. `send_message` to a finished worker only queues.

**Fallback: v1.** On a model without v2, `spawn_agent` returns an
`agent_id`, and `wait_agent` takes `targets` and `timeout_ms` and returns
each finished worker's final text. A v1 session holds 6 workers by default,
through the same `[agents] max_threads`. Workers have no tool to message
you. `{REPORTING}`: "You cannot message the lead. Write anything it needs
mid-flight to the file `execute-issues-status` in your Worktree's Git
directory (`git -C <path> rev-parse --absolute-git-dir`), which is never
committed. Before each commit and each push, read the file
`execute-issues-lead` beside it if it exists: the lead writes its
broadcasts there. Your final message is your hand-back." Read the status
files between waits, and broadcast through the `execute-issues-lead` files.
Resume a finished worker with `send_input`.

**Stopping a worker.** `interrupt_agent` on a worker mid-command publishes
no stop, which leaves the `sub-agent` blocker up until your session ends.
Use it only on a worker that has gone quiet; otherwise `followup_task` it
with an instruction to stop and hand back.

**Location.** No tool a worker holds moves your session, and Dashpot
refuses a Codex worker's `work` commands (see
[Known Dashpot gaps](../SKILL.md#known-dashpot-gaps)).

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

**Launch.** Call `subagent` with `agent: "dashpot-worker"`, a
`description`, a short `prompt` pointing at the brief, and
`background: true`. It returns at once with the worker's `sessionID`.

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
waits until the lead's turn ends. If it fails, write the message to the
file `execute-issues-status` in your Worktree's Git directory
(`git -C <path> rev-parse --absolute-git-dir`), which is never committed.
Your final message is your hand-back."

**Completion.** A `<subagent sessionID="…" state="completed">` message
carrying the worker's final text wakes you, whether you were idle, busy or
interrupted. A state of `error` or `cancelled` is a blocker.

**Resume.** `subagent` with the worker's `sessionID` continues it with its
history. Only you, its parent, can. A prompt to a running worker steers it.

**Long commands.** A foreground shell times out after 2 minutes, so a
worker runs its gates and CI watches in background shells, or with
`timeout: 0`. A shell that runs for about an hour with no other session
event is interrupted, so a gate that long runs outside OpenCode. Add both
to the brief's gotchas.

**Stopping.** Deleting your session deletes its running workers. Stopping
the OpenCode service stops every session.

**Reviewer.** A worker cannot launch its own sub-agent: OpenCode's nesting
depth defaults to 1, and raising it changes every session of the service.
Launch each worker's reviewer yourself as a separate worker, giving it the
worker's base, branch and evidence, and forward its findings. If you cannot,
the worker reviews inline with the same prompt and says so in its PR.
