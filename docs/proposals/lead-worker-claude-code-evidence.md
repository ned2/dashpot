---
status: research
date: 2026-10-05
---

# Claude Code evidence for Lead and Worker mechanisms

Which Claude Code mechanism best runs a Lead's Workers, each taking one Issue
in its own Issue Worktree. This is evidence for the
[Lead and Worker design](lead-worker-design.md) and its
[analysis](lead-worker-design-analysis.md), made for
[Issue #479](https://github.com/ned2/dashpot/issues/479). Its sibling notes
cover [Codex](lead-worker-codex-evidence.md) and
[OpenCode](lead-worker-opencode-evidence.md).

Each claim carries its evidence:

- **measured**: by a Dashpot experiment, linked;
- **documented**: in Claude Code's documentation at <https://code.claude.com/docs/en/>;
- **binary**: read from the strings of the retained 2.1.287 and 2.1.289
  executables, never run;
- **inference**: reasoning that no source states.

The supported release is 2.1.287
([agent sessions](../agent-sessions.md)); nothing in this note was run
against a live session.

## Conclusion

There is a better fit than a Sub-agent: **a root `claude --bg` session started
in the Issue Worktree, coordinated through cross-session messaging.** Dashpot
already observes such a session as an ordinary placed Agent Session
(measured, [#162](https://github.com/ned2/dashpot/issues/162)). Claude Code's
messaging between local sessions (`SendMessage` and `ListAgents`, with
`notify_when_idle`) is documented and on by default since 2.1.224, and it
returns to root sessions the two things Sub-agents had: reports while working
and a notice on completion. Dashpot has not measured it, and the
[harness reference](../agent-harness-server-client-reference.md) does not yet
describe it.

Agent teams do not fit. Neither does the Agent tool's `cwd`
([#474](https://github.com/ned2/dashpot/issues/474)), which is not offered
to the model.

## Capability matrix

| Mechanism | Own session id | Own `cwd` in hooks | Own lifecycle hooks | Dispatch | Progress and completion | Permission asks | Cancel | Headless | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Background Sub-agent** (today) | No: the Lead's session id, `CLAUDE_PID` and shell identity | No: the Lead's directory; a `cd` reaches no hook | `SubagentStart` / `SubagentStop` only, and the stop fires early while background work runs ([#472](https://github.com/ned2/dashpot/issues/472)) | `Agent` with `run_in_background` | `SendMessage` to the main conversation; `<task-notification>` wakes the Lead | Inherits the Lead's mode; asks appear in the Lead | `TaskStop` publishes no `SubagentStop` ([#429](https://github.com/ned2/dashpot/issues/429)) | Yes | Measured ([Worker mechanics experiment](../spikes/claude-code-worker-mechanics-spike.md)) |
| Sub-agent with `isolation: "worktree"` | No | Yes, but in Claude Code's own `.claude/worktrees/agent-<id>` | As above | `Agent` | As above | As above | As above | Yes | Measured ([harness reference](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)); binary: the bundled `/batch` skill uses background Sub-agents with this isolation |
| Agent tool `cwd` | No | Inference: yes, like isolation | As above | **Not offered to the model.** The schema defines `cwd`, but the tool's input schema omits it in 2.1.287 and 2.1.289. A plugin's script API, or its `agent.spawn` hook on a model's Agent call, can set it, though not together with `isolation: "worktree"` | — | — | — | — | Measured at 2.1.287: the schema sent to the model has no `cwd` ([#419 trace](../spikes/measurements/issue-419-claude-trace.jsonl)); binary at 2.1.289 |
| Dynamic workflows (`Workflow`) | No: they run Sub-agents | Only with `isolation: 'worktree'` | Sub-agent | A script's `agent()` | The script's return value | — | `/workflows` | — | Documented; no gain for observation |
| **Agent teams**, in-process teammates (the default) | Unclear: the documentation calls every teammate "a full, independent Claude Code session", but in-process teammates run in the Lead's process | The Lead's directory | `TeammateIdle`, `TaskCreated`, `TaskCompleted` | `Agent` with a `name`, teams enabled | A mailbox per team; an idle notice carries the final answer | Asks go to the Lead | A shutdown request | **No**: Claude Code spawns no teammates in non-interactive mode | Documented; experimental and off by default |
| Agent teams, split-pane teammates | Inference: yes, as their own processes | Launched with `cd <lead directory>` and `--parent-session-id <lead>`, a flag its help describes as "for analytics correlation", in tmux or iTerm2 | Inference: their own | Same | Same | Same | Same | Interactive and tmux only | Documented and binary; teams don't isolate teammates in Worktrees |
| **`claude --bg` root session with cross-session messaging** | **Yes**: the hook session id matches the shell's claim | **Yes**: hooks, shell and listing agree | **Yes**: `SessionStart`, `SessionEnd`, `Stop`, and its own Sub-agents | The Lead's shell runs `cd <worktree> && claude --bg --name <name> "<brief>"`; documented: a session started in a linked Worktree skips the managed one | The Worker sends `SendMessage` to the Lead by name or `uds:<socket>`; the Lead's `SendMessage` with `notify_when_idle` gives a one-shot notice on idle or exit; `claude agents --json` reports `working`, `blocked`, `done`, `failed` or `stopped` | **The weak point.** An ask parks the session in "Needs input" until a person attaches; a message from another session cannot approve anything | `claude stop <id>` publishes `SessionEnd` with reason `other`, which ends the run | Yes | Hooks, process, stop, respawn and eviction measured ([#162](https://github.com/ned2/dashpot/issues/162), [#326](https://github.com/ned2/dashpot/issues/326)); messaging documented only |
| `claude -p` or an Agent SDK root session | Yes | Yes, its launch directory | Yes | A process the Lead starts | Its output stream; documented: can receive cross-session messages | `--permission-prompt-tool` or `canUseTool` | Kill, or close its input: `SessionEnd` | Yes | `-p` hooks measured; SDK not measured |
| Channels and Remote Control | — | — | — | Push into one session; the Remote Control server needs a claude.ai login | — | Documented: a channel can relay permission asks | — | Development channels are interactive only | Partly measured at 2.1.278; the Remote Control server unmeasured ([#370](https://github.com/ned2/dashpot/issues/370)) |
| `EnterWorktree` / `ExitWorktree` | — | Moves a root session; refused from a Sub-agent | — | — | — | Asks before a Worktree outside `.claude/worktrees/` ([#389](https://github.com/ned2/dashpot/issues/389)) | — | — | Measured ([ADR 0085](../adr/0085-return-a-claude-code-session-before-entering-another-issue-worktree.md)) |

## What a `--bg` Worker gets from Dashpot as it stands

All measured at 2.1.286 and 2.1.287 through Dashpot's real publisher (#162):

- **An ordinary Agent Session.** It has its own Host Process (located since
  #326), its own `work start`, Agent Run and Issue Binding.
- **Exact occupancy.** It blocks only its own Worktree.
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
  Repository-wide blocker applies only while its own reviewer Sub-agent runs.
- **Its own activity.** Its own `Stop` and `UserPromptSubmit`, so #472 becomes
  [ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)'s
  existing case of a main session.
- **A clean end.** `claude stop` publishes `SessionEnd`, so #429 and the
  [#458](https://github.com/ned2/dashpot/issues/458) strand do not arise.
- **No special row** in the Sessions pane.
- **Restart handled.** Crash, respawn and idle eviction are already covered by
  [ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
  and [ADR 0075](../adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md).

## What would have to be built

- **The link to the Lead.** No hook carries it. The Lead could record the
  session id `--bg` prints, or the Worker's brief could carry the Lead's
  session id or messaging socket. Split-pane teammates do carry
  `--parent-session-id`, but teams are otherwise unsuitable.
- **Skill changes.** Dispatch with `cd <worktree> && claude --bg --name
  issue-<n>`. Inference: no documented cap bounds how many `--bg` sessions
  run at once, though each Worker's own Sub-agents keep the cap of 20. Report
  with
  `SendMessage` to the Lead's name or `uds:` address, wait with
  `notify_when_idle` and fall back to `claude agents --json`, and cancel
  with `claude stop`.
- **A permission policy.** Workers must run in a mode that does not ask.
  Documented: with no `crossSessionInbound` setting, a session that asks for
  permission holds a message from a sender that bypasses checks, and a
  session that bypasses holds every message except one from another
  bypassing sender (or from its own child processes); a sender that declares
  no class counts as asking. A held message waits for approval until the
  `dialogExpiry` deadline, five minutes by default and settable only in user
  or managed settings, but a background session with no terminal attached
  keeps it held past the deadline, indefinitely. So the Lead and its Workers
  share a permission class, or the receiver sets `crossSessionInbound:
  accept`, which a `-p` session can take through `--settings`. A `-p`
  receiver, unlike a background session, drops a held message once the
  deadline passes, which matters for the experiment's `-p` Lead. Queues hold at
  most 100 held and 50 waiting messages, of about a million characters
  each.

## Risks and unknowns

1. **The Lead's identity might leak into a Worker** (unmeasured, and
   probably unlikely). The `claude --bg` client started from the Lead's shell
   inherits the Lead's `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID` and
   `CLAUDECODE=1`, and binary: the `--bg` launch request carries an `env`
   field. But the Worker itself runs under the supervisor, not the Lead's
   shell, and receives only the forwarded variables (`PATH`, the provider
   selection and model overrides, documented; measured process tree in the
   [harness reference](../agent-harness-server-client-reference.md#measured-supervisor-and-worker-lifecycle-at-21276)),
   and binary: 2.1.287 and 2.1.289 both have a routine that removes
   `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID` from a child's environment. If the Lead's id did
   reach the Worker's shells, `identify_agent_session` would attribute them to
   the Lead. #162 launched `--bg` only from a plain shell, so this is still
   the first thing to measure.
2. **A Worker blocked on an ask waits for a person.** The Lead sees
   `blocked` but cannot answer. Documented: a session working in a checkout
   it did not isolate itself, including one started in an existing Worktree,
   asks before committing or switching branches, so an Issue Worktree Worker
   parks at its first commit unless its brief or instructions tell it to
   commit.
3. **Unattended permission modes are gated.** Documented: `claude --bg`
   refuses `--permission-mode bypassPermissions` until someone has run
   `claude --dangerously-skip-permissions` once interactively, and an `auto`
   or bypass `defaultMode` takes effect only from managed settings, a
   `--settings` file or the user's settings, never a project's.
4. **Killing a Worker does not stop it.** Documented: the supervisor restarts
   a process that exits unexpectedly, so a Worker is ended with `claude stop`
   or by removing the session. The exceptions are documented too: a session
   backgrounded from the terminal with `←` or `/background` is marked stopped
   when killed, `claude daemon stop --any` ends every worker process, and a
   worker process killed while no supervisor runs is listed as `failed`.
5. **Usage limits.** Documented: a `--bg` session's agent fails at a usage
   limit instead of waiting for the reset.
6. **Idle eviction.** An idle `--bg` session is retired about 61 minutes after
   its last `Stop`, with no hook (measured). Its run is orphaned and continues
   when someone attaches, which is harmless for a finished Worker.
7. **New, unmeasured surfaces.** The agent view is a research preview and
   messaging is new. `notify_when_idle` is one-shot, expires after 12 hours,
   works from the main conversation only, and needs 2.1.236 in both sessions.
   Each session's messaging socket is its own, falling back to
   `/tmp/cc-socks-<uid>`, and a sandboxed shell reaches it only when the
   sandbox allows Unix sockets; whether a sandboxed Lead can reach the
   supervisor to launch `--bg` is unmeasured. Sibling linked Worktrees
   inherit workspace trust (measured at 2.1.285).
8. **Lost Sub-agent conveniences.** Resuming by agent id becomes `--resume` or
   attaching to the root session, and the Lead receives a Worker's final
   message only if the Worker sends it.
9. **Cost.** Inference: each Worker is a full session, but a Sub-agent already
   has its own context, so the difference is small. Documented: Sub-agents
   default to a cap of 20 at once. Inference: no documented cap applies to
   `--bg` sessions, so only rate limits and the Lead's skill bound them.
10. **One permission rule covers both routes.** Documented: denying
    `SendMessage` also removes messaging to Sub-agents and teammates.

## Proposed experiment

Add a new `scripts/experiments/claude-479/`, cloned from `claude-162`, so
that the acceptance runner and its committed trace stay as they are.
`claude-162` already drives `--bg` with an isolated `CLAUDE_CONFIG_DIR`, a
loopback model, the real publisher and `DISABLE_AUTOUPDATER=1`, starts
detached with `setsid -f`, and refuses to start under a harness. Pin the new
runner to 2.1.287 through a fixture-local `claude` symlink.
The fixture's Lead is a `claude -p --input-format stream-json` session in the
main checkout, and every session bypasses permission checks so all share one
class.

1. **Dispatch.** The Lead's shell starts two Workers,
   `cd <worktree A or B> && claude --bg --name worker-a "<label>"`. Record each
   Worker's ancestry, its shell's `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`
   against the Lead's, its hook session id and `cwd`, and `claude agents
   --json`.
2. **Occupancy.** Each Worker runs `dashpot work start` in its Worktree, and
   `worktree check` should block A only for worker-a and leave the main
   checkout clear. Worker A also starts a reviewer Sub-agent, to record that
   blocker's scope.
3. **Worker to Lead.** A Worker sends `SendMessage` to the Lead, by name and
   by `uds:` address from its brief. Record the Lead's turn, idle and busy.
4. **Lead to Worker.** The Lead sends `SendMessage` with `notify_when_idle` to
   Worker B, then a message mid-turn. Record the notice after B's `Stop`.
5. **Stop.** `claude stop` on Worker A should end its run with `SessionEnd`.
6. **Permission classes.** A Worker that asks for permission: record the held
   message and what the Lead sees.
7. **Commit prompt.** A Worker started in an existing Issue Worktree commits:
   record whether it asks first, and what its brief must say to avoid that.

Retain metadata only, hash the runner and Dashpot's sources, and add a
verifier. The #419 trace already records that 2.1.287 sends the model no
Agent tool `cwd`
([#474](https://github.com/ned2/dashpot/issues/474)); re-record it on any
newer pin.

## Sources

- Documentation: [cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging),
  [agent view](https://code.claude.com/docs/en/agent-view),
  [agent teams](https://code.claude.com/docs/en/agent-teams),
  [agents](https://code.claude.com/docs/en/agents),
  [workflows](https://code.claude.com/docs/en/workflows).
- Dashpot: the [Worker mechanics experiment](../spikes/claude-code-worker-mechanics-spike.md),
  the [supervised worker process experiment](../spikes/claude-code-supervised-worker-process-spike.md),
  the [harness reference](../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286),
  the execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md)
  and [ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md).
