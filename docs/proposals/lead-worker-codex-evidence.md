---
status: research
date: 2026-10-05
---

# Codex evidence for Lead and Worker mechanisms

Whether Codex offers a better way than a Sub-agent to run a Lead's Workers,
each taking one Issue in its own Issue Worktree. This is evidence for the
[Lead and Worker design](lead-worker-design.md) and its
[analysis](lead-worker-design-analysis.md), made for
[Issue #479](https://github.com/ned2/dashpot/issues/479). Its sibling notes
cover [Claude Code](lead-worker-claude-code-evidence.md) and
[OpenCode](lead-worker-opencode-evidence.md).

Each claim carries its evidence:

- **measured**: by a Dashpot experiment, linked; **measured (#479)** names
  the experiment below;
- **documented**: upstream, in release notes, or shown in 0.160.0's `--help`;
- **source**: read in the [`rust-v0.160.0`](https://github.com/openai/codex/tree/rust-v0.160.0)
  source only, with paths relative to `codex-rs/`;
- **inference**: reasoning that no source states;
- **unknown**: not established.

Codex support is pinned to 0.160.0, the release the acceptance run last
passed on ([agent sessions](../agent-sessions.md#codex-hosting-modes)).
Claims marked measured (#479) come from
[the #479 experiment](#the-479-experiment), which ran 0.160.0 with Dashpot's
real publisher in an isolated fixture: its
[runner](../../scripts/experiments/codex-479/),
[trace](../spikes/measurements/issue-479-codex-trace.jsonl) and
[write-up](../spikes/root-session-workers-spike.md). Everything else was
read, not run.

## Conclusion

No Codex Sub-agent can be given its own location. Source
(`core/src/agent/child_config.rs`): the child's configuration copies the
parent turn's working directory, because, in the code's words, leaving that
runtime state stale "can make a child agent disagree with its parent about
approval policy, cwd, or sandboxing"; role overrides are layered after that
step and carry no `cwd`. `spawn_agent` takes no `cwd` argument, in v1 or v2,
at 0.160.0 or on `main` (`core/src/tools/handlers/multi_agents_v2/spawn.rs`,
`multi_agents/spawn.rs`).

What fits instead is a **root thread per Worker**: a detached
`codex exec -C <issue-worktree>`. It is its own Host Process, its shell's
`work start` binds its own Agent Run, and it blocks only its own Worktree
(measured, #479). A CLI primitive Dashpot's documents don't mention yet
carries its reports: **`codex queue --thread <id> --message <text>`** starts
a turn in an idle Lead. It closes the gap that
[ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
is built around: Codex never wakes an idle Lead.

The #479 experiment found four constraints on that route (measured, #479):

1. **Launch from a full-access or escalated shell.** A Worker launched from a
   sandboxed shell dies with the command that started it, `setsid -f` or not.
2. **Queue from a full-access or escalated shell.** `codex queue` fails in
   every `workspace-write` shell, the Lead's or a Worker's, so a sandboxed
   Worker cannot wake its Lead by queue.
3. **Reach a Worker by resuming it.** Mail queued to a running `exec` Worker
   is consumed at its shutdown and lost. The Lead reaches a Worker with
   `codex exec -C <worktree> <posture> resume <id> "<message>"`, restating
   the sandbox flags, which a bare resume drops.
4. **Stop with SIGINT.** SIGINT publishes `Interrupt` and `SessionEnd`.
   SIGTERM and SIGKILL publish nothing and leave an Orphaned Agent Run, which
   blocks that Worktree's Cleanup.

## `codex queue`

- **Path.** `codex queue` (`cli/src/queue_cmd.rs`) takes a thread's UUID, or
  the exact name of an active thread, and `tui/src/session_queue_commands.rs`
  calls `thread/queue/add`, a method marked experimental (source; added in
  0.149.0, documented in its release notes). It uses the local daemon when
  one runs. With none, it falls back to an embedded app server writing to the
  same store, and starts no daemon (source).
- **Overrides.** While a daemon runs, it refuses any `-c` override, a feature
  flag included: "cannot queue through an embedded app server while a local
  app-server daemon is running; remove configuration overrides or use
  --remote" (measured (#479) with `-c model=…` and `-c features.hooks=true`).
  `--no-daemon` is not one of its arguments: passing it exits 2 (measured,
  #479).
- **Storage.** A durable SQLite queue, `queue_1.sqlite` in `CODEX_HOME`
  (`thread-store/src/queue_store.rs`, served by `ext/queue/src/service.rs`),
  holding at most 100 items per thread (`state/src/lib.rs`) (source).
- **Delivery** to a daemon-hosted thread (measured, #479):
  - An idle, loaded thread starts a turn (`start_turn_if_idle`,
    `turn_trigger: "queue"`) before `codex queue` has exited, and its
    `UserPromptSubmit` carries the message.
  - A busy thread starts it about 3 ms after its turn ends.
  - An unloaded thread is not loaded by it. The item waits, with no hook,
    until a client resumes the thread, and then starts within 2 seconds.
- **Latency.** Delivery is immediate only through the server that holds the
  thread loaded (`wake_if_loaded`). A thread another process holds receives
  the item on that process's poll for external writes, every 10 seconds
  (`watch_external_messages` in `ext/queue/src/service.rs`, built by
  `app-server/src/message_processor.rs` only for a local thread store with a
  state database) (source). Measured (#479): 2.9 and 5.7 seconds.
- **A running `exec` Worker loses its mail** (measured, #479). The queue
  call returns 0 in about 20 ms, but the Worker never sees the message. When
  its turn ends, `exec`'s embedded server takes the item in a second turn
  that publishes only `Interrupt`, with no `UserPromptSubmit` and no model
  request, and then `SessionEnd`. The queue is empty afterwards, and no
  rollout holds the message.
- **Sandboxed shells cannot queue** (measured, #479, under
  `workspace-write`). The daemon's control socket is a symlink into
  `/tmp/codex-daemon-<uid>/`, which bwrap masks for every
  filesystem-restricted command (`linux-sandbox/src/bwrap.rs`), and seccomp
  refuses every Unix-socket `connect`, to a missing path too. Finding no
  daemon, `codex queue` falls back to an embedded server, which fails on the
  read-only `CODEX_HOME`: "failed to start embedded app server: Read-only
  file system (os error 30)". A Worker started with `-s workspace-write` or
  `--approve-for-me` fails the same way. Source: Seatbelt masks the same
  transport on macOS (`sandboxing/src/seatbelt.rs`).
- **Refusals** (source, not exercised;
  `app-server/src/request_processors/thread_queue_processor.rs`): ephemeral
  threads, so an `exec --ephemeral` Worker can receive nothing; archived
  threads; v2 Sub-agents (`DIRECT_INPUT_TO_MULTI_AGENT_V2_SUBAGENT_ERROR`,
  raised for a loaded v2 Sub-agent through `can_accept_direct_input`); and
  unloaded spawned Sub-agents of either version
  (`DIRECT_INPUT_TO_UNLOADED_SUBAGENT_ERROR`). A loaded v1 Sub-agent is
  accepted, so `codex queue` reaches root threads and loaded v1 Sub-agents.
- **Held, not refused** (source, not exercised). An item for a thread whose
  last turn was interrupted is accepted but not dispatched
  (`ext/queue/src/service.rs`). After a person presses Esc in a Lead, a
  Worker's message cannot wake it until someone starts a turn by hand.
  `thread/queue/list`, `update`, `delete`, `reorder` and `start` let a
  protocol client inspect, retract or start such mail (source).
- **What it offers.** A Worker in a full-access or escalated shell can wake
  an idle, loaded Lead, with no protocol client. A Lead cannot follow up a
  running `exec` Worker this way; it resumes the Worker once it has exited.

## Capability matrix

| Mechanism | Own identity | Own `cwd` in hooks | Own lifecycle hooks | Dispatch | Progress and completion | Permission asks | Cancel | Daemon restart or unload | Headless | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **v2 Sub-agent** (today; v1 is weaker, with no messaging) | A thread id as `agent_id` under the root session, not a session ([#420](https://github.com/ned2/dashpot/issues/420)) | No: always the Lead's, which the child configuration forces | `SubagentStart` and `SubagentStop` only | `spawn_agent` | `send_message` and a `wait_agent` loop; an idle Lead is never woken | Shown in the Lead's TUI, labelled with the thread (documented) | `interrupt_agent` sends no `SubagentStop` ([openai/codex#38142](https://github.com/openai/codex/issues/38142), still open) | A Lead's unload leaves its Workers running ([ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)); a restart with Sub-agents not measured | As the Lead | Measured ([Worker mechanics experiment](../spikes/codex-worker-mechanics-spike.md)) |
| **Detached `codex exec -C <worktree>`** from the Lead's shell | Its own root thread: in its shells `CODEX_THREAD_ID` and `CODEX_SESSION_ID` both equal its `thread.started` id, so `work start` makes a root claim | Yes, the `-C` directory; the `exec` process's own cwd stays where it was launched | The full set, `SessionStart` to `SessionEnd` at exit (also measured through Dashpot's publisher for [#356](https://github.com/ned2/dashpot/issues/356)) | A shell command, from a full-access or escalated shell only: launched from a sandboxed shell, it dies with that command | Process exit, an `-o` last-message file, a `--json` stream whose first event, `thread.started`, gives the Worker's id; the Worker runs `codex queue --thread <lead>` from an unsandboxed shell only; mail to a running Worker is lost | No one to ask: choose `-s`, `--approve-for-me` (which sets `auto_review`, `on-request` and `workspace-write`), or bypass (documented and source); every resume must restate it | SIGINT publishes `Interrupt` and `SessionEnd`; SIGTERM and SIGKILL publish nothing and orphan the run | Its own Host Process, so a daemon restart leaves it running | Yes | Measured ([#479](#the-479-experiment)) |
| **Daemon-hosted TUI**: `codex -C <worktree> "<brief>"` in a tmux window | Its own root thread (measured) | Yes (inference for a `-C` launch; measured for `resume -C`) | The full set (measured) | `tmux new-window -c <worktree>` (inference); inference: it fails from a sandboxed shell, whose Unix-socket `connect` to the tmux server seccomp refuses | `codex queue` to the Lead (measured (#479) for a daemon-hosted thread), from an unsandboxed shell | In that window; `codex agents` is an interactive dashboard of every thread on the daemon, which a Lead cannot parse (documented in `--help` and the 0.149.0 release notes) | Esc gives the root an `Interrupt` hook (measured at 0.159.3) | A restart orphans its run (measured, ADR 0086); measured (#479): the reloaded thread takes queued mail at once, but its Agent Run stays orphaned on the old pid; no unload while the TUI is attached | No: needs a terminal | Mostly measured ([harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload), [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md), [#479](#the-479-experiment)); the launch unknown |
| **Controller thread**: `thread/start {cwd}` then `turn/start`, driven by a Dashpot helper | Its own root thread (measured at 0.155.1) | Yes, from `thread/start`, which `turn/start` can override (measured) | The full set (measured) | Needs a protocol client the Lead's model cannot be: a helper, or `codex app-server proxy` from an unsandboxed shell (source) | `turn/completed` to a subscriber; `codex queue` (measured, #479) | A pending ask is **replayed, with the same request id, to a client that later resumes the thread** (measured, #479; `replay_requests_to_connection_for_thread`), and an `approvalsReviewer: auto_review` exists (source) | `turn/interrupt` gives an `Interrupt` hook (measured) | Unloads 60 seconds after it is idle with no subscriber, which ends the run (measured), but not while an ask is pending: measured (#479) loaded past 110 seconds; `thread_unload_delay_secs` is daemon-wide and needs a server restart (source), and its default is 60 seconds in source but 30 minutes on the App Server page; a restart follows ADR 0086 (measured) | Yes | Mechanics measured ([harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload), [#479](#the-479-experiment)); the helper unknown |

Rejected or minor:

- **`codex exec --worktree`** makes a Codex-managed checkout with a detached
  HEAD, under `CODEX_HOME/worktrees` or `desktop.git-worktree-root`, not an
  Issue Worktree. At 0.160.0 its `worktrees` feature is stable and on by
  default, and `exec` refuses it with `resume`, `review` or `--ephemeral`
  (source).
- **The agent message board** is behind a feature flag, under development and
  off by default, scoped to one session's tree, v2 only, and "never queues a
  notification for an idle agent" (source, `core/src/agent_message_board.rs`).
- **Remote Control.** `remote-control start` was measured in the
  [#161](https://github.com/ned2/dashpot/issues/161) acceptance run at
  0.159.3; pairing a device needs an account and is unmeasured.
- **`codex cloud exec`** runs remote tasks, which Dashpot cannot observe
  (documented in `--help`).
- **Resuming a Worker.** `-C` belongs to `codex exec`, not to its `resume`
  subcommand, so `codex exec resume <id> -C <worktree>` does not parse. Both
  `cd <worktree> && codex exec resume <id> "…"` and
  `codex exec -C <worktree> resume <id> "…"` work, each publishing
  `SessionStart` with source `resume` and the Worktree as `cwd`, under a new
  `exec` process (measured, #479). A bare resume runs at the configured
  default posture, not the Worker's: a `-s workspace-write` Worker resumed
  without it ran with full access. Sandbox flags before `resume`, or
  `-c sandbox_mode=…` after it, keep the posture (measured, #479). A resume
  fails with "already has an active writer" while another process holds the
  thread (source). The resumed thread has no run
  ([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)),
  so the Worker runs `work start` again and its run gets a new start time
  (measured, #479).

## Further affordances

- **The Worker's id.** `exec --json` emits `thread.started` with the thread
  id first (measured, #479), so the Lead learns the id for `work assign`,
  `codex queue` and `exec resume` without a report.
- **Thread names.** `thread/name/set` names a thread, which
  `codex queue --thread <name>` and `exec resume` accept; `exec` has no
  `--name` flag, so the name is set through the app server (source).
- **`exec --thread-source <string>`** stores a free-form source on the
  thread, which `thread/list` filters by `source_kinds`. It could tag
  Workers, but it is not a parent link and does not reach hooks (source).
- **`thread/list` by `cwd`** finds a Worker by its Worktree (documented).
- **`codex app-server proxy [--sock]`** relays stdio to the daemon's control
  socket, so a shell can speak JSON-RPC (`thread/start`, `turn/start`,
  `thread/queue/*`) with no helper binary, from an unsandboxed shell only
  (source and `--help`).
- **The `PermissionRequest` hook** runs in the approval path before the
  reviewer or a person, and can allow or deny
  (`hooks/src/events/permission_request.rs`) (source). It could tell Dashpot
  that a root Worker is waiting on an approval. The hooks' `permission_mode`
  reads `bypassPermissions` whatever the sandbox (measured, #479), so it does
  not reveal a Worker's posture.
- **A Lead stamp.** A `DASHPOT_LEAD` set on the launch command reaches the
  Worker's shells and its hook processes (measured, #479).
- **Upstream's orchestrator.** OpenAI's Symphony runs a `codex app-server`
  per run inside each Issue's workspace and drives it as a client, the
  controller shape (documented, its specification;
  [prior art](lead-worker-prior-art.md)). The Python SDK likewise spawns a
  private `codex app-server` with an approval callback (source).

## Recommendation

Root-thread Workers: `codex queue` from Worker to Lead, and
`codex exec … resume` from Lead to Worker.

- **By default, a detached `codex exec -C <issue-worktree>`, launched from a
  full-access or escalated shell.** It depends on no daemon, so it is free of
  ADR 0086's orphaning (measured: a daemon restart leaves it running), the
  [#431](https://github.com/ned2/dashpot/issues/431) unload problem, the
  unknowns of [#398](https://github.com/ned2/dashpot/issues/398), the 60
  second unload and any per-session thread cap. Its constraints are measured
  (#479): it reports by queue only from an unsandboxed shell, takes
  follow-ups only by resume with its posture restated, is stopped with
  SIGINT, and ends its run and its Background Commands when it exits.
- **For a person who wants to watch, a daemon-hosted TUI in tmux.** Asks are
  visible, and an attached client keeps the run alive between turns, at the
  cost of exposure to ADR 0086.
- **Not first: a Dashpot controller.** [ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
  allows a named management command that mutates only what it names, on
  explicit invocation. But a controller makes Dashpot drive sessions, which
  is option 1 of [#148](https://github.com/ned2/dashpot/issues/148)'s consent
  question, not yet approved. It would also have to keep a subscription open,
  or raise the daemon-wide `thread_unload_delay_secs`, or the thread unloads
  after 60 seconds idle, and it would own the routing of asks. In its favour,
  it would give #148 a controller it could verify, a pending ask survives a
  client's departure (measured, #479), and upstream's Symphony takes this
  shape.

What Dashpot gets as it stands (measured (#479), against
[`harnesses.py`](../../src/dashpot/sessions/harnesses.py)):

- **Placement.** The Codex adapter reads `UserPromptSubmit`'s `cwd`, the
  Worktree.
- **Identity.** The Worker's shell makes a root claim, so its `work start` is
  accepted and gives it its own Agent Run and Issue Binding, in a
  `workspace-write` Worker too, whose Work Store lies inside its Worktree.
- **Ancestry.** Process ancestry finds the nearest `codex` process, which is
  the `exec` process: the Worker's own Host Process
  ([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)),
  not the Lead's daemon.
- **Cleanup.** A Worker blocks only its own Worktree, by its session, its run
  and its command's process; nothing names the Lead. Its exit frees the
  Worktree with no teardown. There is no Repository-wide Sub-agent blocker
  except while its own reviewers run.
- **Interrupts.** openai/codex#38142 strands only Sub-agents; a root stopped
  with SIGINT ends with `Interrupt` and `SessionEnd`.
- **The Sessions pane.** Ordinary rows, which removes most of
  [#444](https://github.com/ned2/dashpot/issues/444),
  [#476](https://github.com/ned2/dashpot/issues/476) and
  [#477](https://github.com/ned2/dashpot/issues/477) for Codex Workers.
  Inference: [#492](https://github.com/ned2/dashpot/issues/492), an unloaded
  Lead ending its Workers' assignments, no longer ends a Worker's Issue work,
  which its own run holds.

What it must build:

- **The link to the Lead.** Root threads have no parent, so it is a
  declaration, which would amend ADR 0092 and
  [ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md).
- **The skill for Codex.** The escalated launch command; the Lead's thread id
  in the brief; the Worker's id from `thread.started`; reporting with
  `codex queue` from an unsandboxed shell, with a status file or the Lead's
  reading of `-o`, `--json` and exit as the fallback for a sandboxed Worker;
  follow-ups with `codex exec -C <worktree> <posture> resume`; binding again,
  with the link, after each resume; and stopping with SIGINT.
- **A policy for asks** in headless Workers.

## Risks and unknowns

1. **The sandbox** (measured, #479). A `workspace-write` Lead's shell cannot
   write outside its roots, open TCP, or `connect` any Unix socket, and its
   `CODEX_HOME` is read-only. A Worker launched from it never starts. An
   escalated launch works and doubles as an ask, but under
   `approvals_reviewer = "auto_review"` a model, not a person, judges it
   (source), so it is consent only when a person approves.
2. **Headless asks.** `exec` defaults to `never` and refuses a client's
   approval requests, returning the failure to the model (source). A Worker
   runs with full access, as Dashpot's fixtures do; uses `--approve-for-me`,
   which sets `on-request`, `auto_review` and the `workspace-write` sandbox
   (source), and so cannot queue or open TCP (measured, #479); uses
   `-c approvals_reviewer=auto_review`, which forces no sandbox and keeps the
   person's own permission profile (source); or fails closed. A Sub-agent had
   the Lead's TUI to ask through; a root Worker loses it.
3. **Inherited environment** (measured, #479). A nested `exec` inherits the
   Lead shell's `CODEX_THREAD_ID` and `CODEX_SESSION_ID`. Codex sets both
   afresh for the Worker's own shells, so a Worker's shell makes a root claim
   of its own, never a delegate claim. Its hook processes keep the Lead's
   ids, which is harmless: Dashpot's publisher reads the payload's
   `session_id`, and only a command's own claim reads `CODEX_*`.
4. **The run ends when `exec` exits**, and so do its Background Commands
   (measured, #479;
   [ADR 0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md)).
   Each follow-up is a new run. A Worker must wait for CI in the foreground,
   within its turn, and its turn must cover the push.
5. **A wrong signal blocks Cleanup** (measured, #479). After SIGTERM or
   SIGKILL the run is orphaned and blocks its Worktree in every later
   snapshot, until the Worker resumes and binds again or a person runs
   `dashpot work stop --session` ([domain language](../domain-language.md)).
6. **The Lead's own lifecycle** (measured, #479). A daemon-hosted Lead with no
   client still unloads after 60 seconds idle, which ends its run; a Worker's
   mail then waits, with no hook, until someone resumes the Lead. A
   `daemon restart` reloads the Lead and delivers later mail at once, but
   leaves its Agent Run orphaned on the old pid (ADR 0086). The restart took
   60.3 seconds, the daemon's default shutdown grace
   (`app-server-daemon/src/settings.rs`); inference: a pending ask held the
   drain open.
7. **Cost and limits.** Spawn caps apply only to spawned agents (source): for
   v2, `features.multi_agent_v2.max_concurrent_threads_per_session`, default
   4 including the root, so 3 Sub-agents; for v1,
   `agents.max_concurrent_threads_per_session`, of which `agents.max_threads`
   is a legacy alias, default 6. Inference: root threads are then bounded
   only by account rate limits, which can oversubscribe the machine. The
   per-Worker `--workers N` share of test workers still applies.

## The #479 experiment

`scripts/experiments/codex-479/`, cloned from `codex-420/`, ran Codex 0.160.0
through a fixture-local `PATH` symlink, with isolated `HOME`, `CODEX_HOME`,
XDG directories and `TMPDIR`, a loopback model, the updater off and Dashpot's
real publisher, detached with `setsid -f` in a disposable Project outside
every Dashpot Project. The fixture kept `/tmp` out of the writable roots, so
its `CODEX_HOME` was read-only to sandboxed shells, as `~/.codex` is in real
use. A controller-started, daemon-hosted Lead launched `exec` Workers into
Worktrees, and the runner measured launch and identity, queueing both ways,
resume and its posture, the three signals, a daemon restart mid-wave, a
controller's pending ask, and launches from a `workspace-write` Lead. Its
verifier passes 18 checks against the
[trace](../spikes/measurements/issue-479-codex-trace.jsonl); the
[write-up](../spikes/root-session-workers-spike.md) has the detail.

Still unknown:

- whether a person approving the escalated launch in a real TUI Lead behaves
  as the experiment's protocol client did;
- whether a `workspace-write` Worker with `network_access = true` reaches a
  real model, `git push` and `gh`;
- whether the refused Unix-socket `connect` breaks `gh` or git credential
  helpers in a sandboxed Worker;
- inference: whether a `workspace-write` Worker can commit at all, since a
  linked Worktree's Git directory lies in the main checkout, outside its
  writable roots;
- mail held after an interrupt, and the ephemeral and archived refusals,
  which were not exercised;
- rate limits and cost on a real account.

## Sources

- Upstream: the [App Server documentation](https://learn.chatgpt.com/docs/app-server),
  [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
  [Sub-agents documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents),
  [`openai/codex` at `rust-v0.160.0`](https://github.com/openai/codex/tree/rust-v0.160.0)
  and its release notes, and [Symphony](https://github.com/openai/symphony)'s
  specification.
- Dashpot: [the #479 experiment](../spikes/root-session-workers-spike.md),
  its [runner](../../scripts/experiments/codex-479/) and
  [trace](../spikes/measurements/issue-479-codex-trace.jsonl), the
  [Worker mechanics experiment](../spikes/codex-worker-mechanics-spike.md),
  the [harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload),
  [agent sessions](../agent-sessions.md#codex-hosting-modes),
  [`harnesses.py`](../../src/dashpot/sessions/harnesses.py), the
  execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md),
  and ADRs [0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md),
  [0029](../adr/0029-preserve-agent-runs-through-declared-codex-relocation.md),
  [0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md),
  [0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md),
  [0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
  and [0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md).
