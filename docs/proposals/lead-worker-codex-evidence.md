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

- **measured**: by a Dashpot experiment, linked;
- **documented**: upstream, or shown in 0.160.0's `--help`;
- **source**: read in the [`rust-v0.160.0`](https://github.com/openai/codex/tree/rust-v0.160.0)
  source only, with paths relative to `codex-rs/`;
- **inference**: reasoning that no source states;
- **unknown**: not established.

Codex support is pinned to 0.160.0, the release the acceptance run last
passed on ([agent sessions](../agent-sessions.md#codex-hosting-modes)). Nothing in this
note was run.

## Conclusion

No Codex Sub-agent can be given its own location. Source
(`core/src/agent/child_config.rs`): the child's configuration copies the
parent turn's working directory, because, in the code's words, leaving that
runtime state stale "can make a child agent disagree with its parent about
approval policy, cwd, or sandboxing"; role overrides are layered after that
step and carry no `cwd`. `spawn_agent` takes no `cwd` argument, in v1 or v2,
at 0.160.0 or on `main` (`core/src/tools/handlers/multi_agents_v2/spawn.rs`,
`multi_agents/spawn.rs`).

What fits instead is a **root thread per Worker**, with a CLI primitive
Dashpot's documents don't mention yet as its mailbox: **`codex queue --thread
<id> --message <text>`**. It closes the gap that
[ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
is built around: Codex never wakes an idle Lead.

## `codex queue`

Source, and documented in `--help`:

- **Path.** `codex queue` (`cli/src/queue_cmd.rs`) takes a thread's UUID or
  exact name, and `tui/src/session_queue_commands.rs` calls
  `thread/queue/add`, a method marked experimental. It uses the local daemon
  when one runs; with none, it falls back to an embedded app server writing
  to the same store. It refuses `--no-daemon` unless `--remote` is given
  (`tui/src/session_queue_commands.rs`).
- **Storage.** The item lands in a durable SQLite queue
  (`thread-store/src/queue_store.rs`, served by `ext/queue/src/service.rs`).
- **Delivery.** When the target thread is loaded and idle, the item starts a
  new turn (`start_turn_if_idle`, `turn_trigger: "queue"`). A busy thread
  receives it when its turn ends. An unloaded thread receives it on the
  first poll after it is next loaded or resumed. Any app server with a SQLite
  state database polls it every 10 seconds for writes from other processes
  (`app-server/src/message_processor.rs`); inference: that includes the
  server embedded in `codex exec`.
- **Refusals**
  (`app-server/src/request_processors/thread_queue_processor.rs`): ephemeral
  threads, so an `exec --ephemeral` Worker can receive nothing; archived
  threads; and v2 Sub-agents (`DIRECT_INPUT_TO_MULTI_AGENT_V2_SUBAGENT_ERROR`,
  raised for a loaded v2 Sub-agent through `can_accept_direct_input`); and
  unloaded spawned Sub-agents of either version
  (`DIRECT_INPUT_TO_UNLOADED_SUBAGENT_ERROR`). A loaded v1 Sub-agent is
  accepted, so `codex queue` reaches root threads and loaded v1 Sub-agents.
- **Held, not refused.** An item for a thread whose last turn was
  interrupted is accepted but not dispatched (`ext/queue/src/service.rs`).
  After a person presses Esc in a Lead, a Worker's message cannot wake it
  until someone starts a turn by hand.
- **What it offers.** A Worker can wake an idle Lead, and a Lead can follow
  up an idle Worker, both from a shell, with no protocol client.
- **Unmeasured.** Whether a Worker's sandboxed shell can reach the daemon
  socket is unknown.

## Capability matrix

| Mechanism | Own identity | Own `cwd` in hooks | Own lifecycle hooks | Dispatch | Progress and completion | Permission asks | Cancel | Daemon restart or unload | Headless | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **v2 Sub-agent** (today; v1 is weaker, with no messaging) | A thread id as `agent_id` under the root session, not a session ([#420](https://github.com/ned2/dashpot/issues/420)) | No: always the Lead's, which the child configuration forces | `SubagentStart` and `SubagentStop` only | `spawn_agent` | `send_message` and a `wait_agent` loop; an idle Lead is never woken | Shown in the Lead's TUI, labelled with the thread (documented) | `interrupt_agent` sends no `SubagentStop` ([openai/codex#38142](https://github.com/openai/codex/issues/38142), still open) | A Lead's unload leaves its Workers running ([ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)); a restart with Sub-agents not measured | As the Lead | Measured ([Worker mechanics experiment](../spikes/codex-worker-mechanics-spike.md)) |
| **Detached `codex exec -C <worktree>`** from the Lead's shell | Its own root thread; `CODEX_THREAD_ID` equals `CODEX_SESSION_ID` for roots (measured; inference for a nested `exec`) | Yes, its process's directory (measured for `exec` at 0.155.1) | The full set, `SessionStart` to `SessionEnd` at exit (measured at 0.155.1, and through Dashpot's publisher at 0.160.0, [#356](https://github.com/ned2/dashpot/issues/356)) | A shell command (inference) | Process exit, an `-o` last-message file, a `--json` stream; the Worker runs `codex queue --thread <lead>` (source) | No one to ask: choose `-s`, `--approve-for-me` (which routes to `auto_review` and forces `workspace-write`), or bypass (documented and source) | A signal; whether SIGINT or SIGTERM publishes `SessionEnd` is unknown, and SIGKILL orphans the run (inference) | Its own process, so untouched by [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md) (inference) | Yes | Lifecycle measured; orchestration unknown |
| **Daemon-hosted TUI**: `codex -C <worktree> "<brief>"` in a tmux window | Its own root thread (measured) | Yes (inference for a `-C` launch; measured for `resume -C`) | The full set (measured) | `tmux new-window -c <worktree>` (inference) | `codex queue` both ways (source) | In that window; `codex agents` lists every thread on the daemon (documented in `--help` only) | Esc gives the root an `Interrupt` hook (measured at 0.159.3) | A restart orphans its run, which reloads with no hook (measured, ADR 0086); no unload while the TUI is attached | No: needs a terminal | Mostly measured ([harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload), [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)); the launch unknown |
| **Controller thread**: `thread/start {cwd}` then `turn/start`, driven by a Dashpot helper | Its own root thread (measured at 0.155.1) | Yes, from `thread/start`, which `turn/start` can override (measured) | The full set (measured) | Needs a protocol client the Lead's model cannot be, so a helper | `turn/completed` to a subscriber; `codex queue` (source) | Source: pending asks are **replayed to a client that later resumes the thread** (`replay_requests_to_connection_for_thread`), and an `approvalsReviewer: auto_review` exists | `turn/interrupt` gives an `Interrupt` hook (measured) | Unloads 60 seconds after it is idle with no subscriber, which ends the run (measured); source: the delay is configurable with `thread_unload_delay_secs`; a restart follows ADR 0086 (measured) | Yes | Mechanics measured ([harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload)); the helper unknown |

Rejected or minor:

- **`codex exec --worktree`**, present at 0.160.0 behind the `worktrees`
  feature, makes a Codex-managed checkout under `~/.codex/worktrees` with a
  detached HEAD, not an Issue Worktree (source, read at 0.154).
- **The agent message board** is behind a feature flag, scoped to one
  session's tree, v2 only, and "never queues a notification for an idle
  agent" (source, `core/src/agent_message_board.rs`).
- **Remote Control** needs a paired account and is unmeasured.
- **Resuming a Worker.** `-C` belongs to `codex exec`, not to its `resume`
  subcommand, so `codex exec resume <id> -C <worktree>` does not parse.
  `cd <worktree> && codex exec resume <id> "…"` was measured
  ([#160](https://github.com/ned2/dashpot/issues/160)); source suggests
  `codex exec -C <worktree> resume <id> "…"` also works, since the resumed
  thread is sent the configured `cwd`. A resume fails with "already has an
  active writer" while another process holds the thread. The resumed
  thread has no run
  ([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)),
  so the Worker runs `work start` again and its run gets a new start time.

## Recommendation

Root-thread Workers, with `codex queue` as the mailbox both ways.

- **By default, a detached `codex exec -C <issue-worktree>`.** It depends on
  no daemon, so it is free of ADR 0086's orphaning, the
  [#431](https://github.com/ned2/dashpot/issues/431) unload problem, the
  unknowns of [#398](https://github.com/ned2/dashpot/issues/398), the 60
  second unload and any per-session thread cap.
- **For a person who wants to watch, a daemon-hosted TUI in tmux.** Asks are
  visible, and an attached client keeps the run alive between turns, at the
  cost of exposure to ADR 0086.
- **Not first: a Dashpot controller.** [ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
  allows a named management command that mutates only what it names, on
  explicit invocation. But a controller makes Dashpot drive sessions, which
  is option 1 of [#148](https://github.com/ned2/dashpot/issues/148)'s consent
  question, not yet approved. It would also have to keep a subscription open,
  or raise `thread_unload_delay_secs`, or the thread unloads after 60 seconds
  idle, and it would own the routing of asks. In its favour, it would give #148 a controller it could verify.

What Dashpot gets as it stands (source and inference, against
[`harnesses.py`](../../src/dashpot/sessions/harnesses.py)):

- **Placement.** The Codex adapter reads `UserPromptSubmit`'s `cwd`.
- **Identity.** The Worker's shell makes a root claim, so its `work start` is
  accepted and gives it its own Agent Run and Issue Binding.
- **Ancestry.** Process ancestry finds the nearest `codex` process, which is
  the `exec` process, not the Lead's daemon.
- **Cleanup.** A Worker occupies only its own Worktree, so there is no
  Repository-wide Sub-agent blocker except while its own reviewers run.
- **Interrupts.** openai/codex#38142 strands only Sub-agents; a root ends with
  `Interrupt` and `SessionEnd`.
- **The Sessions pane.** Ordinary rows, which removes most of
  [#444](https://github.com/ned2/dashpot/issues/444),
  [#476](https://github.com/ned2/dashpot/issues/476) and
  [#477](https://github.com/ned2/dashpot/issues/477) for Codex Workers.

What it must build:

- **The link to the Lead.** Root threads have no parent, so it is a
  declaration, which would amend ADR 0092 and
  [ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md).
- **The skill for Codex.** The launch command, the Lead's thread id in the
  brief, reporting with `codex queue`, the status file as fallback, resume
  with `exec resume`, and binding again after a resume.
- **A policy for asks** in headless Workers.

## Risks and unknowns

1. **The sandbox.** Inference: the Lead's sandboxed shell likely confines a
   child `codex exec`, with no network to the model and no writes to other
   Worktrees. Launching probably needs per-command escalation, which doubles
   as consent.
2. **Headless asks.** `exec` cannot ask a person. A Worker runs with full
   access, as Dashpot's fixtures do, uses `auto_review`, or fails closed.
   Source: `--approve-for-me` also forces `on-request` approval and the
   `workspace-write` sandbox, which bears on a Worker's push, `gh` and
   network use. A
   Sub-agent had the Lead's TUI to ask through; a root Worker loses it.
3. **Leaking environment.** A nested `exec` inherits the Lead shell's
   `CODEX_THREAD_ID` and `CODEX_SESSION_ID`. Source: Codex sets both afresh
   for the Worker's own shells, so a Worker's shell makes a root claim of its
   own; its hook processes, though, receive the `exec` process's environment
   and so the Lead's ids. That is harmless today, since Dashpot's publisher
   never reads `CODEX_*` and only a command's own claim does
   ([`harnesses.py`](../../src/dashpot/sessions/harnesses.py)). Unmeasured.
4. **The run ends when `exec` exits.** Each follow-up is a new run, which is
   acceptable if the Worker's turn covers the push and the CI wait.
5. **`codex queue` is unmeasured**: the 10 second poll's latency, whether a
   turn it starts publishes `UserPromptSubmit`, whether a Worker's shell can
   reach the daemon socket, and whether mail reaches a running `exec` Worker
   before it exits at the end of its turn.
6. **Cost and limits.** Spawn caps apply only to spawned agents: for v2,
   `features.multi_agent_v2.max_concurrent_threads_per_session`, default 4;
   for v1, `agents.max_concurrent_threads_per_session`, of which
   `agents.max_threads` is a legacy alias. Inference: root threads are then
   bounded only by account rate limits, which can oversubscribe the machine.
   The per-Worker `--workers N` share of test workers still applies.

## Proposed experiment

A new `scripts/experiments/codex-479/`, cloned from `codex-420/`: Codex
0.160.0 through a fixture-local `PATH` symlink; isolated `HOME`,
`CODEX_HOME`, XDG directories and `TMPDIR`; the daemon updater off; a
loopback Responses fixture; Dashpot's real Codex publisher, trusted through
`hooks/list`; the runner started with `setsid -f`, refusing to run under a
harness, in a disposable Project outside every Dashpot Project, with
Worktrees A and B. The Lead is a daemon-hosted thread started by a
controller that keeps a subscriber open, bound to Issue 1.

1. The Lead's shell starts two detached `codex exec -C <A or B> --json -o …`
   Workers. Record hooks, `cwd`, the `CODEX_*` variables in the Workers'
   shells and hooks, Host Process ancestry, and each Worker's `work start`.
   Check that Cleanup of B is blocked only by Worker B.
2. A Worker runs `codex queue --thread <lead>` while the Lead is idle, busy
   and unloaded. Record the turn start, latency and hooks.
3. The Lead runs `codex queue` to a running `exec` Worker. Is it delivered at
   all?
4. `cd A && codex exec resume`: record hooks, run state and binding again.
5. SIGINT, SIGTERM and SIGKILL of an `exec` Worker mid-command: record hooks,
   the run's outcome and the Worktree's occupancy.
6. `daemon restart` mid-wave: Workers should be unaffected; does a queued
   completion reach the reloaded Lead?
7. A controller thread with a policy that asks, and no subscriber: record the
   pending ask, its replay to a late `thread/resume` client, and the 60
   second unload.
8. The same launch from a Lead in `workspace-write`: record the refusal and
   the escalation path.

A verifier checks every claim, as [#420](https://github.com/ned2/dashpot/issues/420)'s
did.

## Sources

- Upstream: the [App Server documentation](https://learn.chatgpt.com/docs/app-server),
  [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
  [Sub-agents documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents),
  and [`openai/codex` at `rust-v0.160.0`](https://github.com/openai/codex/tree/rust-v0.160.0).
- Dashpot: the [Worker mechanics experiment](../spikes/codex-worker-mechanics-spike.md),
  the [harness reference](../agent-harness-server-client-reference.md#loaded-threads-overrides-and-unload),
  [agent sessions](../agent-sessions.md#codex-hosting-modes),
  [`harnesses.py`](../../src/dashpot/sessions/harnesses.py), the
  execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md),
  and ADRs [0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md),
  [0029](../adr/0029-preserve-agent-runs-through-declared-codex-relocation.md),
  [0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md),
  [0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)
  and [0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md).
