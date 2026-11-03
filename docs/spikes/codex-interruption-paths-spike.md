---
status: research
date: 2026-11-03
---

# Codex interruption paths experiment

[Issue #399](https://github.com/ned2/dashpot/issues/399) qualifies, on the
pinned **codex-cli 0.166.0**, three ways to interrupt a Codex Sub-agent
that the 0.160.0 evidence left unmeasured or measured once. Its scope names
0.162.0; the Arc measured 0.166.0, the release Dashpot now measures. The
three ways are:

1. a child selected in the terminal's agent picker and interrupted there;
2. Esc in a standalone terminal, with no daemon;
3. the parent model's multi-agent v2 `interrupt_agent`, a regression check
   of the 0.160.0 result.

Beside them the run takes its own ordinary-interruption control, Esc on the
parent in a daemon-attached terminal. It does not reuse the control of
[#665](codex-worker-permissions-spike.md), which ran on 0.162.0 with a
different hosting mode and target.

Here the **lead** is the root thread of a Codex Agent Session, and a
**child** is one of its [Sub-agents](../domain-language.md). The fixture
threads only delegate and hold a command, so they are Leads and Workers in
shape only.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **source**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`. With `--codex-source`, the verifier checks each cited fact
  in a checkout of that commit, by matching its code in the cited file,
  not at the cited line;
- **trace only**: the retained trace shows it, but the verifier does not
  check it. Every timing is trace only, this run's single sample, and the
  verifier checks only the bounds a claim depends on; earlier runs of the
  same scenarios, not retained, agreed with it;
- **inference**: what follows for Dashpot, which neither the trace nor the
  source states.

## Answers

| Path | What Esc or the tool interrupted | Hooks after it | The child's command and turn | Dashpot | Basis |
| --- | --- | --- | --- | --- | --- |
| Control: Esc in a daemon-attached terminal, the lead on screen | The lead's turn | The lead's `Interrupt`; the child's own `SubagentStop` 18.1 s later | The command ran its full 20 s hold; the child asked the model again and its turn completed | The run reads waiting; the `sub-agent` blocker clears | measured |
| Esc in a standalone terminal, the lead on screen | The lead's turn | The same as the control, the `SubagentStop` 18.2 s after Esc | The same as the control | The same as the control | measured |
| Agent picker, daemon-attached | The selected child's turn alone | None for the child, then or later; no `Interrupt` for the lead | The command was not signalled and ran its full hold; the child asked the model nothing more; its rollout records `turn_aborted` `interrupted` | The run stays running after the lead's `Stop`; the blocker names the child, and outlives the lead's unload until the daemon stops | measured |
| Agent picker, standalone | The selected child's turn alone | As daemon-attached | As daemon-attached | As daemon-attached, until the terminal exits and takes the Host Process with it | measured |
| `interrupt_agent`, daemon-hosted | The child's turn | None for the child, then or later | As the picker | The run stays running; the blocker names the child | measured |

Esc interrupts the thread the terminal has on screen. The selected thread
decides the target, not the hosting mode: in both kinds of terminal, Esc on
the lead strands no child, and Esc on a child selected in the picker strands
that child exactly as a controller's interrupt of the child's turn did on
0.160.0 ([#374](https://github.com/ned2/dashpot/issues/374)). The stranded
child's lead is not told: its `wait_agent` waits on until another child
finishes.

## Compared with 0.160.0

The 0.160.0 results stay as dated history in their own documents; this
table only sets them beside the new ones.

| Path | 0.160.0 | 0.166.0 |
| --- | --- | --- |
| A controller's `turn/interrupt` of a child's turn | No hook for the child; it stays listed ([#374](https://github.com/ned2/dashpot/issues/374), [harness reference](../agent-harness-server-client-reference.md#hosting-modes-and-daemon-autostart-at-01593)) | Not repeated |
| Esc on the lead, daemon-attached | The lead's `Interrupt`; the child's `SubagentStop` about 19 s later (same section) | The lead's `Interrupt`; the child's `SubagentStop` 18.1 s later |
| Esc on the lead, standalone | Not measured | As daemon-attached |
| Esc on a child selected in the agent picker | Not measured | Strands the child, in both hosting modes |
| `interrupt_agent` | `{"previous_status":"running"}`; the command ran on 17.6 s; no `SubagentStop` ([#420](codex-worker-mechanics-spike.md#7-interruption)) | `{"previous_status":"running"}`; the command ran on 17.2 s; no `SubagentStop` |

On 0.162.0, [#665](codex-worker-permissions-spike.md)'s ordinary
`interrupt_agent` under strict Guardian also reported the child
`interrupted` with no `SubagentStop` in its window. That run is its own
evidence, in [its trace](measurements/issue-665-codex-trace.jsonl.gz)
checked by
[its verifier](../../scripts/experiments/codex-639/permissions-verify.mjs);
this verifier checks only this trace.

## Reproduce

The run needs Node 24, tmux, the pinned Codex binary, and this checkout's
`.venv`. It needs no credentials: a loopback model stands in for the
Responses API. Run the runner detached, from outside any harness, so that
its refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-399/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-399/verify.mjs /var/tmp/dashpot-codex-399-SUFFIX/trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>
uv run python scripts/trace_drift.py scripts/experiments/codex-399/verify.mjs docs/spikes/measurements/issue-399-codex-trace.jsonl
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes about five minutes.

- [Runner](../../scripts/experiments/codex-399/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. Its fixture root is a fresh directory under
    `/var/tmp`, outside every Dashpot Project. Codex gets an isolated
    `HOME`, `CODEX_HOME`, XDG directories and `TMPDIR`, and runs as `codex`
    through a symlink on a fixture-local `PATH`. The fixture daemon's
    settings turn its updater off. Terminals run in a private tmux server
    whose socket and configuration are the fixture's own.
  - **The shared daemon directory.** Codex binds a daemon's control socket
    in `/tmp/codex-daemon-<uid>/` whatever `TMPDIR` or `CODEX_HOME` say,
    named by the SHA-256 of the socket path it advertises, beside a
    `.lock` (source: `uds/src/daemon_directory.rs`,
    `app-server-transport/src/transport/unix_socket.rs`). The runner never
    writes there. It records whether the fixture daemon's own entries exist,
    and the verifier checks that they existed only while that daemon ran.
    Other processes' entries come and go, so the counts of added and
    removed entries are recorded but not checked.
  - **Hooks.** Every lifecycle event that `dashpot integrate codex`
    subscribes goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`, trusted through the `hooks/list` ledger.
  - **Project.** A disposable Dashpot Project with five Local Issue
    Markdown Issues, the main working tree, and one linked Worktree no
    session works in, whose `worktree check` shows the Repository-wide
    `sub-agent` blocker. Each lead binds its own Issue with `dashpot work
    start` from its first shell.
  - **Model.** A loopback Responses API follows a fixed plan for each
    prompt or child task, as `fixture-v2`, a copy of a bundled model that
    declares multi-agent v2. Each child runs one command held 20 s; a
    sibling holds 25 s and then runs `dashpot work show`.
  - **Scenarios**, in order:
    - `daemon-esc`: the first plain terminal starts the managed daemon. Its
      lead spawns one child and waits; Esc with the lead on screen.
    - `daemon-picker`: a second terminal on the daemon. Its lead spawns two
      children and waits; `/subagents` selects the first child, and Esc is
      pressed on it. The terminal then exits, and the run waits for the
      daemon to unload the lead.
    - `interrupt-agent`: a controller starts a lead on the daemon, which
      spawns a child and calls `interrupt_agent` on it 3 s later.
    - `daemon-stop`: `codex app-server daemon stop`.
    - `standalone-esc` and `standalone-picker`: `daemon-esc` and
      `daemon-picker` again in `--no-daemon` terminals.
  - **Bounded windows.** After an interrupt, each scenario waits until the
    interrupted child's command has ended and a further 15 s has passed (5 s
    for the Esc-on-lead scenarios, whose child is meant to stop), and until
    every child expected to stop has, then 2 s more.
  - **Records.** Hooks (identity fields only), each shell's `CODEX_*`
    environment and lifetime, model requests by thread and step, Codex's
    reply text to the lead, every thread's turn events from its rollout
    (type, turn ID, root turn ID and reason), the picker's rows, the thread
    each terminal's status line names, `thread/read` statuses on the
    daemon, and Dashpot's view, `worktree check` and `work show`. It holds
    no prompt and no screen text: a child's final message appears as
    `<worker reply>`.
- [Independent trace verifier](../../scripts/experiments/codex-399/verify.mjs)
  checks every **measured** claim below against the trace, without
  importing the runner or Dashpot. It also checks the runner's sources
  against the hashes the trace records, and with `--strict` Dashpot's
  session and Cleanup modules too.
- [Retained trace](measurements/issue-399-codex-trace.jsonl) is the
  complete metadata stream of the successful run: 182 records. The fixture
  root appears as `$ROOT` and the experiment directory as `$EXPERIMENT`.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-03 AEDT |
| Dashpot base | `a47e86862cd4f3f3b4db1841d220ccc46a4b58c2`'s Dashpot sources. The trace records head `ba0b0aa05627c4ae861437194dcd6d101757edb8`, an unpublished local commit that added this experiment on that base and changed no Dashpot source, with the experiment's later edits uncommitted; the retained sources are checked by digest |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`; the managed daemon runs its own installed copy of the same release |
| Features | `hooks`, `multi_agent` and `multi_agent_v2` on; `plugins` and `apps` off |
| Permissions | `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`; every hook reported `permission_mode` `bypassPermissions` |
| Terminal | tmux 3.6, 220 by 50 |
| Controller | Node `v24.18.0` |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The run
  measures what Codex does, not whether a real model would interrupt.
- **Mid-command interrupts.** Every interrupted child was 3 s into a held
  command. A child interrupted while waiting on the model, or between
  tools, is not measured; the source's stop-hook path does not depend on
  where the turn was.
- **Permissions.** Only approval `never` with full access was run. A child
  waiting on an approval when it is interrupted belongs to #665.
- **Unload.** Only the picker lead's unload was observed with a stranded
  child. `dashpot work forget-subagents`, which the blocker then names, was
  not run.
- **Platforms.** macOS, other releases and real models are unmeasured.

## 1. Hosting and identity

| Claim | Basis |
| --- | --- |
| The first plain terminal started the managed daemon as its own child process; both daemon-attached terminals and the controller's lead ran their threads in that daemon, and every thread's shell was the daemon's child. The daemon's control socket and its `.lock` sat in the shared daemon directory while it ran, and were gone after `daemon stop`. | measured |
| Each `--no-daemon` terminal ran its lead and children in its own process, with no daemon and no control socket in the fixture or the shared directory; each shell was the terminal process's child. | measured |
| A child's hooks carry the lead's thread as `session_id` and the child's thread as `agent_id`, the same as its shell's `CODEX_THREAD_ID`; a child's rollout names the lead as `parent_thread_id` and the child's agent path. | measured |
| Each lead's `work start` from its own shell bound its Issue, in both hosting modes. | measured |
| Every hook's publisher exited 0. | measured |
| Each prompt typed in a terminal also produced one auxiliary model request on another thread, which offered no `exec_command` and so got a plain answer. It changed no scenario. | trace only |

## 2. Esc with the lead on screen

| Claim | Basis |
| --- | --- |
| In both kinds of terminal, the status line named `Main [default]`, and Esc while the lead's turn sat in `wait_agent` published the lead's `Interrupt` 0.3 s later and drew `Conversation interrupted`. | measured |
| The lead's rollout records `turn_aborted` `interrupted`; the child's records no abort and a completed turn. | measured |
| The child's command was not signalled and ran its full 20 s hold. The child then asked the model again, and published its `SubagentStop` 18.1 s after Esc daemon-attached and 18.2 s standalone, under the lead's `session_id`. | measured |
| On the daemon, `thread/read` showed lead and child `active` before Esc and `idle` after. | measured |
| Dashpot's run went from running to waiting, and the `sub-agent` blocker on the idle Worktree cleared. | measured |
| The terminal sends an interrupt to its active thread as `turn/interrupt` naming that thread and its turn, in both hosting modes; `--no-daemon` only chooses where the server runs (`tui/src/app/thread_routing.rs`, `tui/src/cli.rs`). | source |

## 3. Esc on a child selected in the agent picker

| Claim | Basis |
| --- | --- |
| `/subagents` opens the agent picker (`tui/src/slash_command.rs`, `tui/src/chatwidget/slash_dispatch.rs`). It listed `Main [default]`, marked current, and each child by agent path (`/root/worker_p`, `/root/worker_s`) and thread ID. Choosing a row selects that thread (`tui/src/app/event_dispatch.rs`). | measured; source |
| With the child chosen, the status line named its agent path and the composer read `Viewing sub-agent — direct input is disabled`. Esc 3.4 s into the child's command (3.2 s standalone) drew `Conversation interrupted`, with the child still on screen. | measured |
| The child's rollout records `turn_aborted` `interrupted` under the lead's turn as root; the lead's records no abort. | measured |
| The child's command was not signalled and ran on to its end, 16.7 s after Esc (16.8 s standalone). After Esc the child made no model request and published no hook, `SubagentStop` included, through 17 s after its command ended and to the end of the run. | measured |
| The lead got no `Interrupt`. Its `wait_agent` did not return on the interruption; it returned `Wait completed.` only when the sibling finished, 22.7 s after Esc (22.8 s standalone). `list_agents` then reported the child `interrupted` and the sibling completed, and the lead's `Stop` followed the sibling's `SubagentStop`. | measured |
| On the daemon, `thread/read` showed lead, child and sibling `active` before Esc and all `idle` after: the stranded child reads like the finished sibling. | measured |
| `SubagentStop` is dispatched only from a turn that finishes without a follow-up, and an interrupted turn's hooks return at once for any sub-agent, so no hook reports the abort (`core/src/session/turn.rs`, `core/src/hook_runtime.rs`). | source |

## 4. `interrupt_agent`

| Claim | Basis |
| --- | --- |
| The tool replied `{"previous_status":"running"}`: the target's status before the interrupt (`core/src/tools/handlers/multi_agents_v2/interrupt_agent.rs`). | measured; source |
| The child's rollout records `turn_aborted` `interrupted`. Its command was not signalled and ran on 17.2 s after the call. After the call the child made no model request and published no hook, never `SubagentStop`, through 17 s after its command ended and to the end of the run. | measured |
| `list_agents` reported the child `interrupted`, and the lead's own turn stopped with `Stop` 0.3 s after the call. | measured |

## 5. Dashpot's activity and Cleanup

| Claim | Basis |
| --- | --- |
| After a picker interrupt, the run stayed running after the lead's `Stop`, and the `sub-agent` blocker on the idle Worktree named only the interrupted child once the sibling stopped. The same held after `interrupt_agent`. | measured |
| The sibling's `dashpot work show`, run while it still worked, printed the session's run and `has 2 sub-agents listed as working`, naming the interrupted child and itself. | measured |
| Once the daemon-attached picker terminal exited, the daemon unloaded the lead 60.2 s later with `SessionEnd`, and kept running. Dashpot ended the run, but the ended session kept the child listed: the blocker stayed, now saying the session `ended with 1 sub-agent listed as working` and naming `dashpot work forget-subagents <session> --harness codex`. | measured |
| `daemon stop` published `SessionEnd` for the thread it still hosted, whose run then read unknown and orphaned; with the daemon gone, no `sub-agent` blocker remained. | measured |
| A standalone terminal's exit published its lead's `SessionEnd`, which ended the run, and the blocker cleared with the Host Process. | measured |

## Implications for Dashpot

- **inference** Dashpot's `sub-agent` blocker and `work show` text already
  say a listed sub-agent may have been interrupted. Every path that aborts
  a child's own turn needs that text: a controller's interrupt, the
  picker's Esc and `interrupt_agent`. Esc on the lead needs none.
- **inference** For a daemon-hosted session, the live blocker's way out,
  ending the session's client, leads to the ended-session blocker rather
  than clearing it. A person then needs `dashpot work forget-subagents` or a
  daemon stop. Whether that two-step path is intended is a question for a
  separate Issue, not this experiment.
- **inference** No hook tells the stranded child from a working one, so
  nothing here changes what Dashpot can observe;
  [#394](https://github.com/ned2/dashpot/issues/394) and
  [openai/codex#38142](https://github.com/openai/codex/issues/38142) track
  the missing hook.
- The scenarios stay in this separately verified fixture rather than the
  headless acceptance fixture: the picker and Esc paths need a terminal,
  driven here through tmux, and `interrupt_agent` runs beside them so all
  five share one daemon and one Project.

## Validation

- `node scripts/experiments/codex-399/verify.mjs docs/spikes/measurements/issue-399-codex-trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>`:
  23 claims verified against 182 records, the four source claims included.
- `uv run python scripts/trace_drift.py scripts/experiments/codex-399/verify.mjs docs/spikes/measurements/issue-399-codex-trace.jsonl`:
  no drift.
