---
status: research
date: 2026-10-05
---

# Root-session Workers experiment

The experiment for [Issue #479](https://github.com/ned2/dashpot/issues/479)
runs a Lead's Workers as root sessions of their harness, each at its own
Issue Worktree, rather than as the Lead's Sub-agents. It measures the
mechanisms the [Lead and Worker design](../proposals/lead-worker-design.md)
relies on: how a Lead launches a Worker, how each reaches the other, how a
Worker stops, what a restart does, and what Dashpot observes and Cleanup
names throughout. The harnesses measured are:

- Claude Code 2.1.289, with `claude --bg` Workers, and 2.1.287 for comparison;
- Codex 0.160.0, with detached `codex exec` Workers;
- OpenCode 2.0.22, with Workers created on the shared service through
  `opencode api`.

Each runner builds the fixture of the earlier mechanics experiments:

- a disposable Dashpot Project with linked Worktrees, one per Worker;
- a loopback model fixture;
- an isolated harness configuration with its updater off;
- the pinned binary, run read-only through a fixture-local `PATH` symlink or
  a fixture copy;
- the runner launched with `setsid -f` outside every harness process, as the
  [agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires.

Every hook went to Dashpot's real publisher, built from `c8069ac`. After
each step, the runner recorded the hook records Dashpot stored, `work show`
from each session, and the `worktree check --json` report of every
Worktree. The traces are metadata only, with paths rewritten to
placeholders; none contains a home path or a host name.

The fixture model only advances scripted steps. What a real model does with
the same notices, and what a real account's rate limits allow, is outside
the evidence.

## Claude Code 2.1.289

Runner [`claude-479`](../../scripts/experiments/claude-479/), traces
[`issue-479-claude-2.1.289-trace.jsonl.gz`](measurements/issue-479-claude-2.1.289-trace.jsonl.gz)
(676 records, SHA-256
`81c215d17b56dc5daf0471c730f234892ed8c31477140daa6e9fb2d33f00387b`) and,
from the same runner at the supported 2.1.287,
[`issue-479-claude-2.1.287-trace.jsonl.gz`](measurements/issue-479-claude-2.1.287-trace.jsonl.gz)
(676 records, SHA-256
`f5c572d84815f9baf9a26364da036daa1aff6045df99420f70467698fda0bba2`).
Both are gzipped to stay under the repository's large-file check, and each
SHA-256 is of the uncompressed JSONL.
[`verify.mjs`](../../scripts/experiments/claude-479/verify.mjs) reads them
as they are and checks the claims below against both, 45 checks for each
release. Every claim holds on
both releases; only the wording of the senders' notices differs.

Two headless `claude -p` Leads in the main checkout, one in bypass mode and
one in `dontAsk`, dispatch Workers from their own shells with
`claude --bg`. The fixture's configuration directory, its messaging sockets
and its supervisor entry under `/tmp/cc-daemon-<uid>/` were its own: the
run checked that before sending any message, kept the entry already there,
and stopped or messaged nothing outside the fixture. Receipt numbers are
the 2.1.287 trace's; the 2.1.289 trace's are within a few records.

- **Identity.** Each Worker's shells and hooks carry its own
  `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID` and directory, never the Lead's,
  and its `work start` binds its Issue at its Worktree. `--bg` prints only
  an 8-character id and ignores `--session-id`; `claude agents --json
  --cwd <worktree>` lists the Worker with its full `sessionId`, its pid,
  `state` and `waitingFor`.
- **Occupancy.** A bound Worker blocks only its own Worktree, by its
  session, run and processes (#131). While a Worker's reviewer Sub-agent
  runs, every other Worktree gains a `sub-agent` blocker naming that
  Worker:
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
  Repository-wide blocker (#273), cleared when the reviewer ends (#285).
  After `work stop`, a Worker still live blocks its Worktree by session and
  process (#335); after `claude stop`, by neither (#601).
- **Environment.** A Worker does not get its dispatching shell's
  environment. It gets the environment of the shell that first started the
  configuration directory's supervisor, and so does every later Worker,
  from either Lead. A variable named like a token passes like any other.
  A stamp exported for one dispatch reached none of its own Worker's shells
  and appeared in every other Worker's, from the first dispatch. An `env`
  given with `--settings` reaches only its own Worker, in its shells and
  hooks, and survives a respawn.
- **Dispatch.** From the bypass Lead, `cd <worktree> && claude --bg` works.
  The `dontAsk` Lead is refused until the Worktree is in its
  `permissions.additionalDirectories`, and then the `cd` persists: the
  Lead's own session runs on in the Worker's Worktree, which Dashpot
  reports as `work-session-elsewhere`. A subshell,
  `(cd <worktree> && claude --bg …)`, avoids it.
- **Messages.** `SendMessage` to an idle session starts a turn (#157). To a
  busy one it is delivered inside the running turn, after the current tool
  call, as a system message, with no `Stop` between (#175, #194).
  `notify_when_idle` starts a Lead turn after the Worker's `Stop`, and the
  notice carries the Worker's final reply (#248). Every `Stop` payload
  carries `last_assistant_message`.
- **Permission classes.** Messages pass between sessions of one class:
  bypass with bypass, or the prompting modes (manual, `dontAsk`, `auto`)
  with one another. Across classes they are held (#380, #424). The bypass
  `-p` Lead dropped a held message after 300 s (#641); a manual `--bg`
  Worker still held one at 330 s (#650). Each sender is told of a hold, and
  of an expiry, by a new turn.
- **Asks.** A manual Worker waiting on a permission prompt raises a
  `Notification` and is listed by `claude agents` as `blocked` with
  `waitingFor` `permission prompt`, while Dashpot reports its run
  `running` (#403). `auto` mode could not reach its classifier through the
  loopback model, so it blocked and then asked; its behaviour with a real
  model is outside this run.
- **Commit instruction.** Every `--bg` Worker's first request carries a
  background-session system section that mentions `EnterWorktree` and
  tells the model to ask before committing. It is an instruction, not a
  permission check: the bypass Worker committed with no permission request.
  `--settings '{"worktree":{"bgIsolation":"none"}}'` removes the
  ask-before-committing line.
- **Stop and respawn.** `claude stop` publishes `SessionEnd` `other` and
  frees the Worktree (#598, #601). After a SIGTERM to a Worker's process,
  the supervisor resumed the same session in a new process about 10.5 s
  later (#606, #608), but the killed process's `SessionEnd` had already
  ended the Agent Run. The resumed Worker is an unbound session and must
  run `work start` again (#613, #639, #640).

Not measured: a real model's compliance with the background-session
instructions and `auto` mode's classifier; SIGKILL, a crash and idle
eviction; how long the supervisor lives and when a new one takes a new
environment; whether a background Worker's hold ever expires; an
interactive or sandboxed Lead, and a Lead restart.

## Codex 0.160.0

Runner [`codex-479`](../../scripts/experiments/codex-479/), trace
[`issue-479-codex-trace.jsonl`](measurements/issue-479-codex-trace.jsonl)
(731 records, SHA-256
`f91f9da559a1e671776d57edbfd9f85f162f89aeed26a2dd10189c87e046a6d6`).
[`verify.mjs`](../../scripts/experiments/codex-479/verify.mjs) checks the
claims below, 18 checks in all, and the trace records the hashes of the
other runner files. The Lead is a thread on the fixture's own managed
daemon, whose control socket sits beside the user's under
`/tmp/codex-daemon-<uid>/`; the run added only its own entry there and
stopped or queued to nothing else. Receipt numbers are the trace's.

- **Launch.** A Lead shell running `codex exec -C <worktree> --json` with
  `setsid` starts a Worker that is its own Host Process (#98). The Worker's
  shell carries its own `CODEX_THREAD_ID`, so its `work start` is a root
  claim and succeeds. A `DASHPOT_LEAD` exported by the Lead reaches the
  Worker's shells and hooks. The hook processes inherit the Lead's thread
  ids in their environment, but Dashpot's publisher reads the payload's
  `session_id`, which names the Worker. Each Worktree is blocked only by
  its own Worker's session, run and processes; none names the Lead.
- **Launch from a sandbox.** From a `workspace-write` Lead's shell, a
  detached launch dies with the sandboxed command: bubblewrap runs it with
  `--die-with-parent` in its own pid namespace (#593). An escalated launch
  (`sandbox_permissions: require_escalated`) reaches the client as an
  approval request and, once accepted, runs the Worker outside the Lead's
  sandbox.
- **Worker to Lead.** `codex queue --thread <lead>` from an unsandboxed
  Worker shell starts a turn on an idle Lead before the command exits
  (#221), and on a busy one about 3 ms after its turn ends (#183). For an
  unloaded Lead the call succeeds but the daemon does not load the thread;
  the turn starts within 2 s of a client resuming it (#383). A thread held
  by another app-server process receives the message on its 10 s poll
  (#426).
- **Queueing from a sandbox.** From a `workspace-write` shell, Lead or
  Worker, `codex queue` fails: the daemon directory is masked, seccomp
  refuses every Unix-socket connect, and the embedded fallback cannot write
  `CODEX_HOME` (#593). A Worker made with `--approve-for-me` runs in
  `workspace-write` and fails the same way, though its `work start`
  succeeds (#624). A `-c` override on `codex queue` is refused while a
  daemon runs, and `codex queue` has no `--no-daemon` flag.
- **Lead to a running Worker.** A message queued to a running `exec`
  Worker is accepted, never reaches its model, and is consumed at exit by a
  second turn that publishes only `Interrupt` before `SessionEnd`
  (#120, #150, #151). The way to reach a Worker is a later
  `codex exec -C <worktree> resume <id>` with the message as its prompt
  (#277), which needs a new `work start`.
- **Resume posture.** A bare `codex exec resume` of a `workspace-write`
  Worker runs at the configured default, here `danger-full-access`.
  Restating `-s workspace-write` before `resume`, or `-c
  sandbox_mode=workspace-write` after it, keeps the sandbox (#365). The
  hooks' `permission_mode` reads `bypassPermissions` under every sandbox.
- **Stop.** SIGINT publishes `Interrupt` and `SessionEnd` and ends the run.
  SIGTERM and SIGKILL publish nothing, and the run is left orphaned,
  blocking its Worktree (#482).
- **Daemon restart.** `codex app-server daemon restart` took the full 60 s
  shutdown grace while a thread had an ask pending (inference: the ask held
  the drain). The new daemon reloaded the loaded threads, and the running
  `exec` Worker, its own process, went on. Its next `codex queue` reached
  the reloaded Lead at once. The Lead's own Agent Run stayed orphaned on
  the old daemon's pid (#710), as
  [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)
  describes.
- **Asks without a client.** A controller client that leaves while a
  Worker's ask is pending does not lose it: a client that resumes the
  thread later is sent the same request, with the same id, and can answer
  it. A thread with a pending ask did not unload in more than 110 s (#536).

Not measured: a person approving an escalated launch in a real terminal
client; a `workspace-write` Worker with network access reaching a real
model; whether the Unix-socket refusal breaks `gh` or a Git credential
helper inside a sandboxed Worker.

## OpenCode 2.0.22

Runner [`opencode-479`](../../scripts/experiments/opencode-479/), trace
[`issue-479-opencode-trace.jsonl`](measurements/issue-479-opencode-trace.jsonl)
(891 records, SHA-256
`ac56ea95877bb46df662efe73629ea057a780cc951ca25db2490ee2436449fa5`).
[`verify.mjs`](../../scripts/experiments/opencode-479/verify.mjs) checks the
claims below, 35 in all, and that Dashpot's sources match the run's. Every
`opencode api` call, from the runner and from the fixture's sessions, went
through [`guard.mjs`](../../scripts/experiments/opencode-479/guard.mjs),
which refused any call that would reach a service other than the fixture's.
The operator's service was never contacted. A fixture-only
[probe plugin](../../scripts/experiments/opencode-479/probe-plugin.js)
recorded the events plugins receive. Receipt numbers are the trace's.

- **Dispatch.** `opencode api POST /api/session` from the Lead's shell, with
  a location and metadata, then `/prompt`, makes a root session at the
  Worktree carrying the metadata (#89). Dashpot's plugin treats it as an
  ordinary root, and the Worker's `work start` binds its Issue there; the
  Worktree's blockers are all the Worker's own (#91–#93). The Worker gets
  the service's environment, not the Lead's: variables the Lead exported,
  such as `GH_TOKEN`, are absent.
- **Notices.** `POST /api/session/<lead>/synthetic` wakes an idle Lead at
  once with the notice as a new user message. To a busy Lead, `steer`
  delivers it at the next step and `queue` after the turn's last planned
  step, both in the same execution. A Lead waiting on its own ask keeps the
  ask; the notice waits until it is answered. A repeated message id returns
  the first message, and the model never sees the duplicate, but it starts
  an empty execution (#109, #110).
- **A Worker's ask.** A root session created with the `dashpot-worker`
  agent is accepted, and its `session_move` is denied (#202, #203). While
  its ask waits, Dashpot shows the Worker's run `running`. The Lead lists
  the ask through `GET /api/session/<id>/permission`, or through
  `/api/permission/request` with the Worker's location; without the
  location, the service answers for its own directory even from a shell in
  the Worktree (#232, #235).
- **Reply semantics.** `reject` rejects every pending ask in the session
  and ends the turn; `reject` with a `message` lets the turn go on.
  `always` saves a rule to the Project's database that also answers the
  Lead's asks at the main Worktree and survives a service restart, and is
  listed only by `GET /api/permission/saved?projectID=<p>`.
- **Forks.** A fork of a Worker is a root at the same location, with the
  same agent and a copy of its metadata, so it claims the same Lead and
  Issue (#261–#266).
- **Reviewer.** A foreground Sub-agent of a root Worker is a child that
  inherits the metadata; its `work start` is refused as `delegated-session`.
  While it ran, an unused Worktree showed a `sub-agent` blocker naming the
  Worker:
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
  Repository-wide blocker, back for the length of a review (#338, #349).
- **Finish.** After `work stop` and a move back to the main Worktree, the
  Worker's Worktree has no blockers. A `work show` from that Worker at the
  main Worktree then reported the Lead's run (#368): two root sessions of
  one service at one Worktree are not told apart.
- **Interrupt, delete and move.** `POST …/interrupt` records `outcome`
  `interrupted` and leaves the run `waiting`; deleting the session removes
  the run. Deleting the Lead leaves its Workers running and bound, and a
  Worker's later notice to it fails with `SessionNotFoundError`. Moving the
  Lead carries its run, and a Worker's notice reaches it at its new
  location.
- **`opencode run` from the Lead's shell.** A backgrounded
  `cd <worktree> && opencode run …` makes a root with no metadata whose
  shells carry the Lead's exports. The shell's completion notice wakes the
  Lead with the Worker's final text.
- **Service restart.** `opencode service stop` orphans every bound run. The
  next `opencode api` call starts a new service, which resumes the turns it
  cut off: it appends "The server restarted while you were working.
  Continue from where you left off without repeating completed work.",
  marks the cut-off tool `Command cancelled`, and continues at the next
  step. Interrupted and idle sessions are left alone. A pending ask is
  cancelled, not asked again. Dashpot's plugin, loaded after the resumption
  began, never sees those turns start, so their runs stay orphaned and
  `work start` from a resumed turn is refused as stale (#670, #683). Only a
  fresh `/prompt` binds a new run (#715). An environment replaced with
  `PUT /environment` is lost.
- **Standalone Lead.** `opencode api` from a `--standalone` Lead's shell
  reaches the shared service, and a Worker's notice to that Lead ran the
  Lead's session on the shared service while its standalone client was
  mid-turn: one session executing in two Host Processes, the case
  [ADR 0108](../adr/0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md)
  keeps out of Lead and Worker work.
- **Plugin API.** A plugin's `ctx.session` offers `create`, `prompt` and
  `synthetic` among its methods; none was called. A 330 s
  `POST /api/experimental/session/<id>/wait` through `opencode api` was not
  cut off, but `opencode api GET /api/event` buffers the body and printed
  nothing in 390 s.

Not measured: whether a real model told to continue after a restart repeats
a side effect such as a push; restart under load; the one-hour idle
eviction of a Worker's location (#467); calling the plugin `ctx.session`
methods.

## Reproduce

From a checkout of the Worktree, outside every harness process, with a
private `TMPDIR` for the fixture roots:

```sh
TMPDIR=<private dir> setsid -f node scripts/experiments/claude-479/run.mjs ~/.local/share/claude/versions/2.1.287 > claude-479-2.1.287.log 2>&1
TMPDIR=<private dir> setsid -f node scripts/experiments/claude-479/run.mjs ~/.local/share/claude/versions/2.1.289 2.1.289 > claude-479-2.1.289.log 2>&1
TMPDIR=<private dir> setsid -f node scripts/experiments/codex-479/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/bin/codex > codex-479.log 2>&1
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-479/run.mjs ~/.opencode/bin/opencode > opencode-479.log 2>&1
node scripts/experiments/claude-479/verify.mjs docs/spikes/measurements/issue-479-claude-2.1.287-trace.jsonl.gz docs/spikes/measurements/issue-479-claude-2.1.289-trace.jsonl.gz
node scripts/experiments/codex-479/verify.mjs docs/spikes/measurements/issue-479-codex-trace.jsonl --strict
node scripts/experiments/opencode-479/verify.mjs docs/spikes/measurements/issue-479-opencode-trace.jsonl --strict
```

Each runner's header lists its scenarios and options. `--strict` also fails
once a Dashpot source the run hashed has changed in the checkout.
