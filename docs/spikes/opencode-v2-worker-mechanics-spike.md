---
status: research
date: 2026-10-04
---

# OpenCode v2 worker mechanics experiment

The experiment for [Issue #421](https://github.com/ned2/dashpot/issues/421),
part of [#403](https://github.com/ned2/dashpot/issues/403), measures the
worker mechanics a `dashpot-execute-issues` lead would rely on under OpenCode
2.0.22, the pinned release. The lead is an OpenCode session. It launches
**workers**, which are background children started with OpenCode's own
`subagent` tool. The eight questions below are the Issue's, answered in its
order. Each answer is marked **measured** (checked by the verifier against
the retained trace), **documented** (read from the 2.0.22 source or an
earlier spike, not measured here), or **unknown**.

The experiment builds on the [OpenCode v2 hosting, plugin and identity
experiment](opencode-v2-spike.md), the [plugin registry, envelope and
recovery experiment](opencode-v2-plugin-protocol-spike.md) and
[ADR 0090](../adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md),
and does not repeat their findings. This is evidence for #403. It is not an
accepted ADR, and it changes nothing in Dashpot.

## Reproduce

The runner needs Node built-ins, Git, `uv`, and the OpenCode **2.0.22** binary.
The binary is copied into the fixture, so the operator's own installation is
never run in place. The runner starts its own service on a private port, with
disposable configuration and state, a proxy that reaches nothing but
loopback, and autoupdate disabled. It never contacts the operator's service.
No model credentials are needed: a loopback OpenAI-compatible provider
returns tool calls to OpenCode's real execution loop. The runner builds
Dashpot from the checkout into a fixture environment. From that
installation, `dashpot integrate opencode` installs the plugin and the
Issue-work skill the run exercises.

The runner refuses to start below a harness session. From the assigned
Dashpot checkout, detach it with `setsid -f`:

```bash
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-421/run.mjs \
  <absolute opencode 2.0.22 binary> > run.log 2>&1
node scripts/experiments/opencode-421/verify.mjs <fixture root>/trace.jsonl
```

The run takes about four minutes and is done when its log prints
`All scenarios completed`. The verifier needs no network.

- The [runner and trace receiver](../../scripts/experiments/opencode-421/run.mjs)
  - creates a Dashpot Project with a markdown Issue Source and three linked
    Worktrees;
  - serves the fixture model;
  - drives the service through its HTTP API, its CLI and a TUI on a
    pseudo-terminal.
- The fixture model emits each session's tool calls, and records each request
  it receives: the notices in it, the skills it offers, and the tool result it
  answers.
- The [shell reporter](../../scripts/experiments/opencode-421/command.mjs) and
  [ancestry reader](../../scripts/experiments/opencode-421/ancestry.mjs)
  report each shell's identity variables, directory and ancestry. A
  `dashpot work` command or an `opencode run` runs from that shell.
- The [API caller](../../scripts/experiments/opencode-421/api.mjs) calls the
  service's HTTP API from a worker's shell, as any process of the user can.
  It reads the service registration and authenticates with its password,
  and reports the registration's field names, never their values.
- The [independent trace verifier](../../scripts/experiments/opencode-421/verify.mjs)
  checks each measured claim below.
- The [retained trace](measurements/issue-421-opencode-trace.jsonl) holds 800
  records. The first record holds the SHA-256 hashes of the binary, the
  experiment's sources and the Dashpot sources the run exercised. Fixture and
  binary paths appear as `$ROOT` and `$BINARY_DIR`.

## Tested configuration and evidence boundary

- **Versions.** OpenCode 2.0.22 on Linux x64 (binary SHA-256
  `32cf5aa0…5ad122`), Node 24.18.0.
- **Dashpot.** The run's checkout was at `206803b`, this branch's first
  commit, whose `src/` is `8e42212`'s: after multi-skill `integrate`
  ([#418](https://github.com/ned2/dashpot/issues/418)). The run installs the
  only bundled skill, `dashpot-issue-work`.
- **Service and models.**
  - Only the shared service is measured.
  - The leads are sessions created through the HTTP API, apart from one
    TUI lead.
  - Every model turn is the fixture's: a real model's choice of agent, tool or
    timing is not measured.
- **Configuration.**
  - The global configuration allows every tool and defines two agents with a
    `*session_move` deny: the worker agent `dashpot-worker`, and the lead
    agent `dashpot-lead`.
  - Project configuration is disabled with `OPENCODE_DISABLE_PROJECT_CONFIG`
    in every scenario but `project-agent`. That scenario restarts the fixture
    service without the flag after checking that no directory above the
    fixture holds configuration.
- **Scenarios.**
  - `installer`.
  - `launch`, `idle-wake`, `report` and `resume`: questions 1 to 4.
  - `location`, `move-while-working` and `guard`: question 6, and the defect
    below.
  - `depth`: question 1.
  - `interrupt`, `tui` and `delete`: question 7.
  - `skills`: question 8.
  - `project-agent`: question 6.
- **External skills.** Skills in `~/.claude/skills` and `~/.agents/skills` exist
  in the `skills` scenario only.
- **Shell timeout.** A worker's shell keeps OpenCode's default timeout,
  2 minutes by the 2.0.22 source, except in the timeout case of question 2.

## Findings

### 1. Launch and concurrency

**Measured.**

- **Background launch.** The lead calls
  `subagent({agent, description, prompt, background: true})`. Its other
  inputs are `model` and `sessionID`.
  - The call returns at once with `The subagent is working in the background
    (sessionID: ses_…)` and instructions not to poll.
  - Each worker ran the sequence its prompt named, so the lead's prompt
    reaches the worker; a `read your brief at <path>` prompt was not sent.
  - The child's first prompt is the lead's text after the line `You are a
    subagent spawned by another session.` (documented, from the 2.0.22
    source; the fixture model records only the prompt's label).
- **The lead keeps control.**
  - Three `subagent` calls made in one step ran at once. Two workers'
    shells started within 8 ms of the lead's next shell, a 9 s hold. The
    third worker reached its hold 1 s later, after two earlier commands.
  - All three finished while the lead's shell still held.
  - A turn that only launches a worker ended in about 50 ms, before the
    worker's first command.
- **No cap measured.** Four sessions were active at once: the lead and its
  three workers. No concurrency cap appears in the 2.0.22 source
  (documented); more than three workers were not measured.
- **Depth.** A worker cannot launch its own sub-agent by default:
  `Subagent depth limit reached (1). Increase "experimental.subagent_depth"
  to allow nested subagents.`
  - With `experimental: {subagent_depth: 2}` in the global configuration and
    `opencode reload`, the grandchild ran.
  - The grandchild's `work start` was refused as a delegated session naming
    the root lead.
- **The limit is configuration only** (documented). The `subagent` tool reads
  it from the configuration entries: global, project, `OPENCODE_CONFIG` or
  `OPENCODE_CONFIG_CONTENT`. No session or tool input sets it, and raising
  it raises it for every session of the service.

**Fallback for a worker's own reviewer.** The worker runs its review inline,
or the lead dispatches the reviewer as a worker of its own. Raising the depth
needs a configuration change for every session, which the skill should not
make.

### 2. Mid-flight report

**Measured.** A worker's shell can send its lead a message:
`opencode run --session <lead-session-id> "<message>"`. The worker knows its
lead's ID from its brief. Delivery depends on the lead's state:

- **Lead idle.** The message starts a new lead execution. The call returned in
  290 ms with the lead's reply on stdout.
- **Lead busy.** The message is steered into the running execution at its
  next step, and no new execution starts. The worker's call blocks until the
  lead's turn ends: 9.0 s here, behind a 9 s hold.
  - A foreground shell's default timeout is 2 minutes (documented, from the
    2.0.22 source), so a lead busy for longer would time the worker's shell
    out.
  - Under a 3 s `timeout`, the worker's shell got `Command exceeded timeout of
    3000 ms`, and the lead still received the message.
- **Non-blocking forms.**
  - A `background: true` shell returns at once. The worker went on while its
    report waited 9.0 s, and was notified when the report finished.
  - The HTTP API's `POST /api/session/<lead>/prompt` admits the message
    (`"delivery":"steer"`) and returns in 22 ms. It needs the service
    password from `$XDG_STATE_HOME/opencode/service.json`.
  - `opencode run` has no flag for not waiting (documented).
- **Side effects in Dashpot: none.**
  - Before the reports, after one to an idle lead, during one to a busy
    lead and after one from another Worktree, Dashpot showed the same Agent
    Runs on the same Host Process, the lead's at the main Worktree.
  - A report from a shell that had `cd`'d into another Worktree did not move
    the lead, and did not relocate its run.
  - `opencode run` is a client of the shared service, so it is neither a
    new Agent Session nor a Live Relocation.

**Recommendation.** Have the worker send its report from a background shell,
so a busy lead never stalls it, with a status file in its Worktree as the
fallback the lead reads.

### 3. Completion

**Measured.**

- **The notice.** When a worker ends, its lead receives a synthetic user
  message: `<subagent sessionID="…" state="completed" description="…">`
  followed by the worker's final text. The `state` can also be `error` or
  `cancelled` (documented).
- **A busy lead.** It got all three notices at its next step, inside the
  execution it was already running.
- **An idle lead.** One whose turn had ended was woken with a new execution
  carrying the notice.
- **The lead's state does not matter.** The notice also woke a lead whose turn
  had been interrupted, and one whose TUI had quit (question 7).

### 4. Resume

**Measured.**

- **Resuming a finished worker.** `subagent({…, sessionID: <worker>})`
  continued it in the same child session with its history: the resumed
  worker's shell claimed the same session ID, and no new child session was
  created.
- **Steering a running worker.** A prompt to a running worker steers it: the
  worker's next step followed the new prompt, and the step it had planned
  never ran.
- **Only the lead can resume** (documented). The tool refuses a `sessionID`
  that is not a child of the calling session.

### 5. Shared Agent Session

**Measured.** Yes: Dashpot attributes a worker's hooks and shells to its
lead's Agent Session. The lead's hook record lists the workers as its live
sub-agents, and a worker's `work show` reports the lead's run with them.

- **`work start` is refused.** A worker's `dashpot work start`, run from
  another Worktree, was refused with `(delegated-session): it is a child
  session of <lead>, whose Agent Run its work belongs to`. A grandchild's was
  refused naming the root lead.
- **The lead reads `running`.** The lead's Agent Run showed its session
  `running` while its workers ran, even after its own turn had ended, and
  `waiting` once they ended.
- **The Cleanup blocker.** The `sub-agent` blocker held every other Worktree
  of the Repository ("has 3 sub-agents listed as working") while the
  workers ran, and cleared when they ended.
- **`work show` from a worker.** From the lead's directory, it reports the
  lead's run with its sub-agents. From another Worktree, it reports `no
  active Issue work at this worktree`.

The lead keeps the Issue Binding; workers need no opt-in of their own. The
[Dashpot finding](#dashpot-finding-a-relocated-lead-keeps-a-finished-worker-listed)
below is an exception to "clears when they end".

### 6. Location

**Measured.**

- **Where a worker runs.** A worker's shell starts in its lead's directory.
  - `cd <worktree> && …` runs one command in another Worktree.
  - So does the shell tool's `workdir`.
- **A worker moving itself.** `opencode.session_move` on the worker moves only
  the worker: its later shells ran in the new Worktree. The lead and its run
  stayed where they were.
- **A worker moving its lead.** `opencode.session_move({sessionID: <lead>,
  directory})` called by a worker moved the lead, and Dashpot relocated the
  lead's run. The tool takes any session ID.

**Where a deny binds.** A permission rule
`{action: "*session_move", resource: "*", effect: "deny"}` removes the tool
from a worker; its call fails with `Unknown tool 'opencode.session_move'`.
The table below is measured unless marked:

| Where the deny lives | Binds the worker? |
| --- | --- |
| The worker's agent in the global `opencode.json` `agents` map | Yes |
| A global agent file, `~/.config/opencode/agent/<name>.md`, with the rule in its `permissions` frontmatter | Yes |
| A project agent file, `<repository>/.opencode/agent/<name>.md` | Yes, when project configuration is enabled. `OPENCODE_DISABLE_PROJECT_CONFIG` hides it |
| The lead session's own `permissions`, given when the session is created | Yes: its workers lost the tool too |
| The lead's agent | No: a `general` worker launched by a `dashpot-lead` lead moved it |
| The `subagent` call | Not possible: the tool has no permissions input |

**Not a security boundary.**
- **The HTTP API.** A worker whose tool was denied still moved its lead
  through the HTTP API (`POST /api/session/<lead>/move`, 204), with the
  password any process of the user can read from the service registration.
- **The CLI** (documented). The same shell can run `opencode session delete`,
  or `opencode run --session <lead>` to ask the lead to act.
- **What the deny is for.** It stops the model's tool path, not a determined
  process.

**Recommendation.**
- **Install a worker agent.** `integrate` installs a global agent file, say
  `dashpot-worker`, with the deny, and the skill launches every worker with
  `agent: "dashpot-worker"`.
- **What that relies on.** The model choosing that agent. Enforcing it would
  need a `subagent` permission on the lead, such as the lead session's own
  permissions. The model cannot set those without the HTTP API.
- **The global configuration is the wrong place.** A deny there would
  remove the tool from every session of the user.
- **The fallback.** Brief workers never to move a session, and have the lead
  check its own location with `work show` after each worker ends.

### 7. Interruption

**Measured.**

- **The lead's turn interrupted.**
  - `POST /api/session/<lead>/interrupt` answered `{interrupted: true}` and
    killed the lead's own running shell.
  - The background worker kept running and finished, and its notice woke the
    lead.
  - The lead's Agent Run showed its session `running` until then.
- **The lead's TUI quit.**
  - The worker kept running, and the lead's Agent Run showed its session
    live and `running`.
  - The notice woke the client-less lead.
- **The lead deleted.**
  - Its running worker was deleted with it (`404`): its hold never finished,
    and its next command never ran.
  - The lead's run left the observation, and the `sub-agent` blocker
    cleared.
- **Not measured here, documented elsewhere.**
  - Stopping the service stops every running session, workers included,
    and leaves the Agent Runs on it orphaned
    ([OpenCode hosting modes](../agent-sessions.md#opencode-hosting-modes)).
  - A running shell sends no session event, so a worker whose shell runs
    for about an hour with no other event at its location is interrupted,
    its command killed
    ([idle eviction](opencode-v2-spike.md#idle-eviction)).

**Fallback for long gates.** The idle eviction means a worker's validation
gate must finish well within the hour, or run outside OpenCode. A foreground
shell's 2-minute default timeout needs `timeout: 0` or `background: true` for
any long gate.

### 8. Skill loading

**Measured.**

- **Loading.** OpenCode 2.0.22 lists and loads the skill `integrate`
  installs, from `$XDG_CONFIG_HOME/opencode/skills/dashpot-issue-work/`.
  - It also lists skills in `~/.claude/skills` and `~/.agents/skills`.
  - The model's `skill` tool loaded the skill's content.
- **Hiding a skill.** Frontmatter `metadata: {opencode/autoinvoke: false}`
  hides a skill from the model's `<available_skills>` list.
  - The `skill` tool still loaded it by name, so the skill is not strictly
    user-only.
  - Claude Code's `disable-model-invocation: true` is ignored: such a skill
    stays in the list.
- **Invoking a hidden skill.** The user invokes one by naming it in the
  prompt's `skills` input, which put only its content in the turn.

**Unknown, not measured.**
- **The TUI.** How the TUI invokes a skill.
- **A deny on `skill`.** Whether `{action: "skill", resource: "<id>",
  effect: "deny"}` would make a skill strictly user-only. The 2.0.22 source
  checks that rule both when listing skills and in the `skill` tool, but its
  effect on the user's own invocation was not measured.

**Recommendation.** Mark `dashpot-execute-issues` with both flags: the
OpenCode metadata and Claude Code's flag. Say in the skill itself that it runs
only when the user asks.

## Dashpot finding: a relocated lead keeps a finished worker listed

**Measured.** A Dashpot defect against ADR 0066's blocker, filed as
[#427](https://github.com/ned2/dashpot/issues/427) and not fixed here.

**Sequence** (scenario `move-while-working`):

1. A bound lead at the main Worktree launches one background worker.
2. While the worker runs, the lead is moved to Worktree `b` through the HTTP
   API, a Live Relocation.
3. The worker ends, and its notice wakes the lead in `b`.

No child moves. A worker that moves its lead with `opencode.session_move`
(scenario `location`) follows the same path.

**Records.** Labels `mv-*` in the trace:
- **Before the move.** The main Worktree's hook record lists the worker.
- **After the move.** `b`'s new record lists it too.
- **After the worker ends.**
  - `b`'s record lists none.
  - The main Worktree's record still reads `running` and lists the worker.
    Nothing updates it again until the lead returns there.

**Effects.**
- **`work show`.** From the lead reports `has 1 sub-agent listed as working`
  for the finished worker.
- **Cleanup.** Every Worktree the lead does not occupy, here `a`, keeps the
  `sub-agent` blocker while the lead lives. `sessions_with_live_subagents`
  counts every record of a session that is not over.
- **Clearing.** Moving the lead back to the main Worktree and running one
  turn there cleared it.

**Cause, as read from the code.** A new location's record is seeded from the
freshest record of the session, so it inherits the live sub-agents. A
sub-agent's stop then updates only the store of the session's current
location. The same path would apply to any harness whose session relocates
while a sub-agent runs.

## Not measured

- A real model's behaviour: whether it picks the agent the skill names,
  waits for notices rather than polling, or follows a brief.
- More than three concurrent workers, workers on several Issues at once, and
  workers' own Worktree `git` work.
- Workers launched from a TUI lead's slash command, the TUI's skill
  invocation, and a `--standalone` lead.
- Changing a running lead session's permissions with `PATCH
  /api/session/<id>`.
- The hour's idle eviction of a worker, and a service stop with workers
  running (both documented above).

## Validation

`node scripts/experiments/opencode-421/verify.mjs
docs/spikes/measurements/issue-421-opencode-trace.jsonl` reports `ok` for
all 37 claims.
