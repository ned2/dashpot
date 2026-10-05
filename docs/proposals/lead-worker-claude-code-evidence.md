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

- **measured**: by a Dashpot experiment, linked; **measured (#479)** names
  [the #479 experiment](#the-479-experiment), on both pins;
- **documented**: in Claude Code's documentation at <https://code.claude.com/docs/en/>;
- **binary**: read from the strings of the retained 2.1.287 and 2.1.289
  executables, not exercised;
- **inference**: reasoning that no source states;
- **unknown**: not established.

The supported release is 2.1.287
([agent sessions](../agent-sessions.md)). This note was checked against
2.1.289, the newest release on 2026-10-05; 2.1.288 and 2.1.289 changed the
background-command time limit, `idle_prompt`, and the teammate and
`agent.spawn` surfaces, and the claims below that those touch name their
release. Claims marked measured (#479) come from the #479 experiment, which
ran 2.1.287 and 2.1.289 with Dashpot's real publisher in an isolated
fixture: its [runner](../../scripts/experiments/claude-479/), its traces
([2.1.287](../spikes/measurements/issue-479-claude-2.1.287-trace.jsonl.gz),
[2.1.289](../spikes/measurements/issue-479-claude-2.1.289-trace.jsonl.gz)) and
its [write-up](../spikes/root-session-workers-spike.md#claude-code-21289).

Revised 2026-10-05: a desk check of every claim against the documentation
and both binaries, and the #479 experiment, corrected the earlier draft, as
the [2026-10-05 review](../reviews/lead-worker-design-review-2026-10-05.md)
records. Teams keep a mailbox per agent, not per team; `--bg` prints only a
short id; a bound Worker's occupancy, once graded measured by #162, is now
measured by #479; only bypass is gated for `--bg`; a Worker receives the
supervisor's whole environment, not only forwarded variables; and a
SIGTERM respawn loses the Worker's Issue Binding.

## Conclusion

There is a better fit than a Sub-agent: **a root `claude --bg` session started
in the Issue Worktree, coordinated through cross-session messaging.** Dashpot
already observes such a session as an ordinary placed Agent Session
(measured, [#162](https://github.com/ned2/dashpot/issues/162)), its own
`work start` binds its own Agent Run, and it blocks only its own Worktree
(measured, #479). Claude Code's messaging between local sessions
(`SendMessage` and `ListAgents`, with `notify_when_idle`) is documented and
on by default since 2.1.224, and it returns to root sessions the two things
Sub-agents had: reports while working, and a notice on completion that
carries the Worker's final text (measured, #479). The
[harness reference](../agent-harness-server-client-reference.md) does not
yet describe it.

The #479 experiment found five constraints on that route (measured, #479):

1. **Dispatch in a subshell.** `(cd <worktree> && claude --bg …)`. An
   un-subshelled `cd` in a Lead whose added directories hold the Worktree
   moves the Lead's own session there.
2. **The environment is the supervisor's.** Every `--bg` Worker gets the
   whole environment of the shell that first started the configuration
   directory's supervisor; a dispatch's own shell variables never reach its
   Worker. Only `--settings` `env` reaches one Worker.
3. **A SIGTERM respawn loses the binding.** The supervisor resumes the same
   session, but the killed process's `SessionEnd` has already ended the
   Agent Run, so the Worker must run `work start` again.
4. **One permission class.** Messages between a session that bypasses
   permission checks and one that prompts are held, and a `-p` receiver
   drops a held message after five minutes.
5. **An asking Worker looks healthy.** A Worker blocked on a permission
   prompt reads `running` in Dashpot.

Agent teams do not fit. Neither does the Agent tool's `cwd`
([#474](https://github.com/ned2/dashpot/issues/474)), which is not offered
to the model.

## Capability matrix

| Mechanism | Own session id | Own `cwd` in hooks | Own lifecycle hooks | Dispatch | Progress and completion | Permission asks | Cancel | Headless | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Background Sub-agent** (today) | No: the Lead's session id, `CLAUDE_PID` and shell identity | No: the Lead's directory; a `cd` reaches no hook | `SubagentStart` / `SubagentStop` only, and the stop fires early while background work runs ([#472](https://github.com/ned2/dashpot/issues/472)) | `Agent` with `run_in_background` | `SendMessage` to the main conversation; `<task-notification>` wakes the Lead | Inherits the Lead's mode; asks appear in the Lead | `TaskStop` publishes no `SubagentStop` ([#429](https://github.com/ned2/dashpot/issues/429)) | Yes | Measured ([Worker mechanics experiment](../spikes/claude-code-worker-mechanics-spike.md)) |
| Sub-agent with `isolation: "worktree"` | No | Yes, but in Claude Code's own `.claude/worktrees/agent-<id>` | As above | `Agent` | As above | As above | As above | Yes | Measured ([harness reference](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)); binary: the bundled `/batch` skill uses background Sub-agents with this isolation |
| Agent tool `cwd` | No | Inference: yes, like isolation | As above | **Not offered to the model.** The schema defines `cwd`, but the tool's input schema omits it in 2.1.287 and 2.1.289. Binary only, undocumented: a plugin's script API, or its `agent.spawn` hook on a model's Agent call, can set it, though not together with `isolation: "worktree"`; the documented `agent.spawn` fields are only `model` and `deny` | — | — | — | — | Measured at 2.1.287: the schema sent to the model has no `cwd` ([#419 trace](../spikes/measurements/issue-419-claude-trace.jsonl)); binary at 2.1.289 |
| Dynamic workflows (`Workflow`) | No: they run Sub-agents | Only with `isolation: 'worktree'` | Sub-agent | A script's `agent()` | The script's return value | — | `/workflows` | — | Documented; no gain for observation |
| **Agent teams**, in-process teammates (the default) | Unclear: the documentation calls every teammate "a full, independent Claude Code session", but in-process teammates run in the Lead's process | The Lead's directory; binary: from 2.1.289 an `agent.spawn` hook's `cwd` does not apply to a teammate | `TeammateIdle`, `TaskCreated`, `TaskCompleted` | `Agent` with a `name`, teams enabled | A mailbox per agent (`~/.claude/teams/{team}/inboxes/{agent}.json`); an idle notice carries the final answer | Asks go to the Lead | A shutdown request | **No**: Claude Code spawns no teammates in non-interactive mode | Documented; experimental and off by default |
| Agent teams, split-pane teammates | Inference: yes, as their own processes | Launched with `cd <lead directory>` and `--parent-session-id <lead>`, a hidden option absent from the CLI reference that its help describes as "Parent session ID for analytics correlation", in tmux or iTerm2 | Inference: their own | Same | Same | Same | Same | Interactive and tmux only | Documented; the launch command and option binary only; teams don't isolate teammates in Worktrees |
| **`claude --bg` root session with cross-session messaging** | **Yes**: the hook session id matches the shell's claim and the listing's `sessionId` (measured, #479) | **Yes**: hooks, shell and listing agree | **Yes**: `SessionStart`, `SessionEnd`, `Stop`, and its own Sub-agents | The Lead's shell runs `(cd <worktree> && claude --bg --name <name> "<brief>")`; `--bg` prints an 8-character short id and ignores `--session-id`; the full id comes from `claude agents --json --cwd <worktree>` (measured, #479). Documented: a session started in a linked Worktree skips the managed one | The Worker sends `SendMessage` to the Lead by name or `uds:<socket>`: an idle Lead gets a new turn, a busy one receives it inside its running turn; the Lead's `SendMessage` with `notify_when_idle` gives a one-shot notice carrying the Worker's final text (measured, #479); `claude agents --json` reports `working`, `blocked`, `done`, `failed` or `stopped`, with `waitingFor` | **The weak point.** An ask parks the session until a person attaches, and Dashpot reads it as `running` (measured, #479); a message from another session cannot approve anything | `claude stop <id>` publishes `SessionEnd` with reason `other`, which ends the run; SIGTERM is followed by a respawn that loses the Issue Binding (measured, #479) | Yes | Measured: hooks, process, stop, respawn and eviction ([#162](https://github.com/ned2/dashpot/issues/162), [#326](https://github.com/ned2/dashpot/issues/326), under bypass only); identity, occupancy, messaging, permission classes, SIGTERM and environment ([#479](#the-479-experiment)) |
| `claude -p` or an Agent SDK root session | Yes | Yes, its launch directory | Yes, but a `claude -p` that exits published no `SessionEnd` at 2.1.289 (measured, #466; [#518](https://github.com/ned2/dashpot/issues/518)) | A process the Lead starts | Its output stream; receives cross-session messages: a new turn when idle, inside the running turn when busy (measured, #479) | `--permission-prompt-tool` or `canUseTool` | Kill, or close its input | Yes | `-p` hooks measured; SDK not measured |
| Channels and Remote Control | — | — | — | Push into one session; the Remote Control server needs a claude.ai login | — | Documented: a channel can relay permission asks | — | Development channels are interactive only | Partly measured at 2.1.278; the Remote Control server unmeasured ([#370](https://github.com/ned2/dashpot/issues/370)) |
| `EnterWorktree` / `ExitWorktree` | — | Moves a root session; refused from a Sub-agent | — | — | — | Asks before a Worktree outside `.claude/worktrees/` ([#389](https://github.com/ned2/dashpot/issues/389)) | — | — | Measured ([ADR 0085](../adr/0085-return-a-claude-code-session-before-entering-another-issue-worktree.md)) |

## What a `--bg` Worker gets from Dashpot as it stands

Measured through Dashpot's real publisher, at 2.1.286 and 2.1.287 (#162)
and at 2.1.287 and 2.1.289 (#479):

- **An ordinary Agent Session.** It has its own Host Process (located since
  #326), its own `work start`, Agent Run and Issue Binding. Its shells and
  hooks carry its own `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID` and `cwd`,
  never the Lead's, and the Lead's run stays bound where it was (measured,
  #479).
- **Exact occupancy** (measured, #479). A bound Worker blocks only its own
  Worktree, by its session, its run and its process.
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
  Repository-wide `sub-agent` blocker applies only while its own reviewer
  Sub-agent runs, and names that Worker. After its `work stop`, a Worker
  still live blocks its Worktree by session and process, not by run; after
  `claude stop`, by neither. #162 measured the lifecycle only, and ran no
  `worktree check` against a bound `--bg` Worker.
- **Its own activity.** Its own `Stop` and `UserPromptSubmit`, so #472 becomes
  [ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)'s
  existing case of a main session. A Worker blocked on a permission prompt
  reads `running`, though `claude agents --json` lists it `blocked`, waiting
  for a permission prompt (measured, #479).
- **A clean end.** `claude stop` publishes `SessionEnd` with reason `other`
  (measured, #162 and #479), so #429 and the
  [#458](https://github.com/ned2/dashpot/issues/458) strand do not arise.
- **No special row** in the Sessions pane.
- **Restart, in part.** A Worker sent SIGTERM publishes `SessionEnd`, and its
  supervisor resumes the same session id in a new process about 10.5
  seconds later (`SessionStart` with source `resume`). The `SessionEnd` has
  already ended the Agent Run, so there is no Orphaned Agent Run for
  [ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
  or [ADR 0075](../adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md)
  to continue: the respawned Worker is an unbound session, `work show`
  finds no Issue work, and it must run `work start` again (measured, #479).
  Inference: SIGKILL, a crash or idle eviction, which publish no
  `SessionEnd`, would leave an orphaned run for ADR 0053; #479 did not
  measure them.

## What would have to be built

- **The link to the Lead.** No hook carries it. `--bg` prints only the
  8-character short id, `backgrounded · <id8> · <name>`, and ignores
  `--session-id`, so the Lead cannot choose the Worker's id; it reads the
  full `sessionId` from `claude agents --json --cwd <worktree>` (measured,
  #479). The Worker's brief could carry the Lead's session id or messaging
  socket. A stamp in the launch shell's environment fails, but a
  `--settings '{"env":{…}}'` stamp reaches only its own Worker's shells and
  hooks, and survives a respawn (measured, #479;
  [environment](#environment-and-credentials)). Split-pane teammates do
  carry the hidden `--parent-session-id`, but teams are otherwise
  unsuitable, and a `--bg` launch with it is unmeasured.
- **Skill changes.** Dispatch with `(cd <worktree> && claude --bg --name
  issue-<n> …)` in a subshell, and give the Lead's directories the
  Worktrees if it runs in `dontAsk` (below). Inference: no documented cap
  bounds how many `--bg` sessions run at once, though each Worker's own
  Sub-agents keep the cap of 20; documented: ten agents in parallel use
  quota about ten times as fast. Report with `SendMessage` to the Lead's
  name or `uds:` address, wait with `notify_when_idle` and fall back to
  `claude agents --json`, cancel with `claude stop`, and run `work start`
  again after a respawn.
- **A permission policy.** Workers must run in a mode that does not ask, in
  the Lead's class:
  - **Classes** (documented; measured, #479). Bypass is one class; manual,
    `dontAsk` and auto are the other, which the message frame names
    `from-mode="prompting"`. With no `crossSessionInbound` setting, a
    prompting receiver holds a message from a bypassing sender, and a
    bypassing receiver holds every message except one from another
    bypassing sender or its own child processes; a sender that declares no
    class counts as prompting. Measured: bypass to bypass and `dontAsk` to
    `dontAsk` deliver both ways; across classes, the message is held.
  - **Holds.** A held message waits for approval until the `dialogExpiry`
    deadline, five minutes by default, set in user or managed settings, or
    per session by `CLAUDE_CODE_USER_DIALOG_TIMEOUT_MS` (documented); since
    a dispatch's shell variables never reach a `--bg` Worker, it would have
    to come through `--settings` (inference, unmeasured). A bypassing `-p`
    Lead dropped a held message 300 seconds after the hold (measured,
    #479). A background Worker with no terminal attached still held a
    message 330 seconds after its hold (measured, #479); the documentation
    says indefinitely, and 2.1.289's sender notice says a non-interactive
    receiver lets the hold expire.
  - **Notices.** A sender is told of a hold, and later of its expiry, by a
    stream warning and by a new, unlabelled turn in its own model (measured,
    #479). The held receiver raises a `Notification`, "A message from
    another session needs your approval", and lists as `blocked`.
  - **Other routes.** The receiver can set `crossSessionInbound: accept`,
    which a session takes through `--settings`, while a project-scope
    `accept` is ignored (documented; not exercised by #479). Queues hold at
    most 100 held and 50 waiting messages, of about a million characters
    each, dropping the oldest held message when full (documented).

## Environment and credentials

Measured (#479), on both pins:

- **The supervisor's whole environment.** The first `claude --bg` against a
  configuration directory starts its supervisor, and every later `--bg`
  Worker of that directory, from any Lead, inherits that first shell's
  environment, which included the Lead process's own. Each Worker carried
  the first dispatch's markers, never its own dispatch's; a second Lead's
  environment reached none of its Workers, which carried the first Lead's.
  No name filter applies: a variable named like a token passed exactly as a
  neutral one did. This refutes the earlier reading that a Worker receives
  only forwarded variables.
- **Only identity is the Worker's own.** `CLAUDE_CODE_SESSION_ID`,
  `CLAUDE_PID` and `cwd` in its shells and hooks are the Worker's. Binary:
  a routine removes `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID` from the
  supervisor's spawn environment, and every Claude Code process sets its own
  identity variables for its shells and hooks.
- **`--settings` `env` is per Worker.** A `--settings '{"env":{…}}'`
  variable, a token-named one included, reached only its own Worker's shells
  and hooks, and survived a SIGTERM respawn.

Inference, for real use: a Worker's credentials, such as a `GH_TOKEN`, are
whatever the shell that first started the user's supervisor held, which may
be another session's, another Project's or another checkout's `.envrc`, not
the Lead's. A credential a Lead exports before dispatch never reaches its
Worker, and a credential the supervisor holds reaches every Worker of every
Lead. When a later supervisor takes a new shell's environment, after the
supervisor exits, is unmeasured. A per-Worker credential would go through
`--settings` `env`, ideally a settings file rather than inline JSON, which
would put it on the command line.

## Permission posture and the commit instruction

- **Gating** (documented). `claude --bg` refuses
  `--permission-mode bypassPermissions` until someone has run
  `claude --dangerously-skip-permissions` once interactively. Auto and
  `dontAsk` given on the command line are not gated, and auto is the
  starting mode of an interactive terminal session since 2.1.283, while
  `--bg` starts a session the way a new `claude` session in that directory
  would; an auto or bypass `defaultMode`
  takes effect only from managed settings, `--settings` or the user's
  settings, never a project's.
- **`dontAsk`** never prompts: it denies what its allow rules do not allow.
  A `dontAsk` Worker ran unattended within its rules (measured, #479). A
  `dontAsk` Lead's `cd <worktree> && claude --bg` was denied until the Lead
  had `permissions.additionalDirectories` for the Worktree and allow rules
  `Bash(cd:*)` and `Bash(claude:*)`; then the un-subshelled `cd` persisted,
  the Lead's later commands and hooks ran in the Worker's Worktree, and
  Dashpot reported `work-session-elsewhere` for the Lead (measured, #479).
  A bypassing Lead's `cd` did not persist, since the Worktree lay outside its
  directories.
- **Auto** falls back to prompting after 3 blocks in a row or 20 in total,
  which parks a `--bg` Worker as `blocked`, and its classifier reviews every
  outgoing `SendMessage` (documented). With the fixture's loopback model the
  classifier could not answer, so an auto Worker blocked and then asked
  (measured, #479); auto's real behaviour is unmeasured.
- **An asking Worker.** It raises `PermissionRequest` and a `Notification`,
  "Claude needs your permission", and `claude agents --json` lists it with
  `status: waiting`, `state: blocked` and `waitingFor: permission prompt`,
  while Dashpot reports its run `running` (measured, #479). Dashpot installs
  no `Notification` or `PermissionRequest` hook for Claude Code today
  ([`registry.py`](../../src/dashpot/sessions/integrate/registry.py)); either could
  tell it the Worker is waiting on a person (inference).
- **The commit instruction.** Every `--bg` Worker's first model request
  carries a `# Background Session` system section that mentions
  `EnterWorktree`, and by default a line telling it to ask before
  committing; `--settings '{"worktree":{"bgIsolation":"none"}}'` removes that
  line, and the `EnterWorktree` mention remains (measured, #479, presence
  only, not the text). Binary (2.1.289): the line reads "If you didn't enter
  the worktree yourself this job, or you're in the user's own checkout, ask
  before committing or switching branches", and git instructions in the
  task, CLAUDE.md or memory take precedence. It is an instruction to the
  model, not a permission gate: a bypassing Worker committed with no
  `PermissionRequest` (measured, #479). Whether a real model asks under it
  is unmeasured. Binary: the instruction to call `EnterWorktree` tests for a
  `cwd` under `.claude/worktrees/`, not for a linked Worktree, so a real
  model might still try to enter one from an Issue Worktree (unmeasured).

## Further affordances

- **`claude agents --json`** (documented; measured, #479) lists `id`, the
  full `sessionId`, `pid`, `cwd`, `kind`, `name`, `status`, `state` and
  `waitingFor` (`permission prompt`, `input needed`, `sandbox request`,
  `worker request` or `dialog open`). `--cwd <path>` limits it to one
  Worktree, and `--all` keeps exited sessions. It carries no final message.
- **The hand-back.** Every `Stop` payload carried `last_assistant_message`
  (measured, #479), and the `notify_when_idle` notice quotes the Worker's
  final text (measured, #479; its truncation limit unmeasured);
  `claude logs <id>` is another route (documented). Dashpot keeps neither:
  [ADR 0059](../adr/0059-keep-an-append-only-event-log-in-each-checkout.md)
  records no prompts or raw payloads.
- **`--agent <name>`** puts `agent_type` in every hook payload, and the
  agent's frontmatter can set `permissionMode`, `tools` and `model`
  (documented); as a Worker tag it is unmeasured.
- **Lifecycle commands** (documented): `claude respawn [--all]`,
  `claude rm` and `claude attach`; pinning a session in agent view keeps
  its process past idle eviction, with no CLI flag for it found;
  `$CLAUDE_JOB_DIR/tmp` is the documented place for self-reported progress.
- **A `PermissionRequest` hook** can allow or deny an ask, so a policy could
  answer without a person; in a session that cannot prompt, no decision
  means deny (documented).
- **Not a Lead signal.** The `Notification` types `agent_needs_input` and
  `agent_completed` fire only while agent view is open, and from 2.1.288
  `idle_prompt` no longer fires while background agents run (documented).

## Risks and unknowns

1. **The supervisor's environment** (measured, #479;
   [above](#environment-and-credentials)). The Lead's identity does not
   reach a Worker, but neither do the Lead's credentials or stamps; the
   first shell to start the supervisor sets them for every Worker.
2. **A Worker blocked on an ask waits for a person**, and Dashpot shows it
   `running` (measured, #479). The Lead sees `blocked` in
   `claude agents --json` but cannot answer.
3. **Killing a Worker does not stop it.** Documented: the supervisor
   restarts a process that exits unexpectedly, so a Worker is ended with
   `claude stop` or by removing the session. The exceptions are documented
   too: a session backgrounded from the terminal with `←` or `/background`
   is marked stopped when killed, `claude daemon stop --any` ends every
   worker process, and a worker process killed while no supervisor runs is
   listed as `failed`. Measured (#479): after SIGTERM the respawned Worker
   has lost its Issue Binding.
4. **Usage limits.** Documented: the automatic wait for a usage limit to
   reset is not offered to background sessions or `-p` runs. What a `--bg`
   Worker's `state` then reads is unmeasured.
5. **Idle eviction.** An idle `--bg` session is retired about 61 minutes after
   its last `Stop`, with no hook (measured, #162). Its run is orphaned; that
   ADR 0053 continues it when someone attaches is unmeasured by #479, and
   harmless for a finished Worker.
6. **A `-p` or SDK Lead's waiting.** Documented: a background command in an
   unattended session (`-p`, the Agent SDK, CI) is limited to 30 minutes by
   default and 2 hours at most, which `BASH_DEFAULT_TIMEOUT_MS` and
   `BASH_MAX_TIMEOUT_MS` can raise, and a `-p` run's background commands end
   shortly after its final result, so such a Lead's `work wait` in a
   background shell is cut short. The limit came in 2.1.285 for every
   session; from 2.1.288 an interactive Lead is not limited.
   Whether a `--bg` Lead, which reads "background job · unattended" with no
   terminal attached, counts as unattended is unmeasured. A `claude -p` that
   exits published no `SessionEnd` at 2.1.289 (measured, #466;
   [#518](https://github.com/ned2/dashpot/issues/518)).
7. **New surfaces.** The agent view is a research preview and messaging is
   new. `notify_when_idle` is one-shot, expires after 12 hours, works from
   the main conversation only, is local only, and needs 2.1.236 in both
   sessions (documented). Each session's messaging socket is its own,
   falling back to `/tmp/cc-socks-<uid>`, and a sandboxed shell reaches it
   only when the sandbox allows Unix sockets; whether a sandboxed Lead can
   reach the supervisor to launch `--bg` is unmeasured. Sibling linked
   Worktrees inherit workspace trust (measured at 2.1.285); `--bg` in an
   untrusted directory errors "Workspace not trusted" (documented).
8. **Mid-turn delivery** (measured, #479). A message to a busy session
   arrives inside its running turn, after the current tool call, as a
   system-role message, with `UserPromptSubmit` and no `Stop` between. The
   receiver acted on it in the same turn. What a real model does with it,
   and with the notice turns a hold starts, is unmeasured.
9. **Lost Sub-agent conveniences.** Resuming by agent id becomes `--resume` or
   attaching to the root session. The Lead no longer receives a Worker's
   final message as a notification, but `notify_when_idle` quotes it
   (measured, #479).
10. **Cost.** Inference: each Worker is a full session, but a Sub-agent
    already has its own context, so the difference is small. Documented:
    Sub-agents default to a cap of 20 at once. Inference: no documented cap
    applies to `--bg` sessions, so only rate limits and the Lead's skill
    bound them.
11. **One permission rule covers both routes.** Documented: denying
    `SendMessage` also removes messaging to Sub-agents and teammates.

## The #479 experiment

[`scripts/experiments/claude-479/`](../../scripts/experiments/claude-479/),
cloned from `claude-162/`, which is unchanged, ran 2.1.287 and 2.1.289 in
turn through a fixture-local `claude` symlink, in a fixture outside every
Project, with isolated `HOME`, `CLAUDE_CONFIG_DIR`, XDG directories and
`TMPDIR`, a private `XDG_RUNTIME_DIR` for the messaging sockets, a loopback
model, `DISABLE_AUTOUPDATER=1` and Dashpot's real publisher, detached with
`setsid -f` and refusing to start under a harness. Its supervisor entry sat
beside the user's under `/tmp/cc-daemon-<uid>/`, which it left in place, and
it sent no stop or message outside the fixture. A bypassing
`claude -p --input-format stream-json` Lead in the main checkout dispatched
bypassing and manual Workers into their own Worktrees from its shell, and a
second, `dontAsk` Lead dispatched a `dontAsk` and an auto Worker. It
measured dispatch and identity, the environment and both stamps, occupancy
with a reviewer Sub-agent, messages both ways idle and busy,
`notify_when_idle`, the permission classes and holds, asks, the commit
instruction, `claude stop`, and SIGTERM with its respawn. Its `verify.mjs`
checks 45 claims on each of the two traces, 90 in all; the
[write-up](../spikes/root-session-workers-spike.md#claude-code-21289) has the
detail.

Still unknown:

- what a real model does: the commit instruction, the auto classifier, the
  `EnterWorktree` instruction, and mid-turn and notice turns;
- SIGKILL, a crash, idle eviction, and the supervisor's exit and lifetime,
  including when a new supervisor takes a new shell's environment;
- whether a background Worker's hold ever expires past 330 seconds, and
  `crossSessionInbound: accept`;
- an interactive, a sandboxed or a `--bg` Lead, and a Lead's restart;
- a `--bg` Worker at a usage limit, rate limits and cost on a real account.

The #419 trace records that 2.1.287 sends the model no Agent tool `cwd`
([#474](https://github.com/ned2/dashpot/issues/474)); the 2.1.289 binary
omits it too, and a re-record belongs to #474.

## Sources

- Documentation: [cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging),
  [agent view](https://code.claude.com/docs/en/agent-view),
  [agent teams](https://code.claude.com/docs/en/agent-teams),
  [agents](https://code.claude.com/docs/en/agents),
  [workflows](https://code.claude.com/docs/en/workflows),
  [permission modes](https://code.claude.com/docs/en/permission-modes),
  [settings](https://code.claude.com/docs/en/settings),
  [environment variables](https://code.claude.com/docs/en/env-vars),
  [tools reference](https://code.claude.com/docs/en/tools-reference),
  [hooks](https://code.claude.com/docs/en/hooks).
- Dashpot: [the #479 experiment](../spikes/root-session-workers-spike.md#claude-code-21289),
  its [runner](../../scripts/experiments/claude-479/) and traces
  ([2.1.287](../spikes/measurements/issue-479-claude-2.1.287-trace.jsonl.gz),
  [2.1.289](../spikes/measurements/issue-479-claude-2.1.289-trace.jsonl.gz)),
  the [Worker mechanics experiment](../spikes/claude-code-worker-mechanics-spike.md),
  the [supervised worker process experiment](../spikes/claude-code-supervised-worker-process-spike.md),
  the [harness reference](../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286),
  the [2026-10-05 review](../reviews/lead-worker-design-review-2026-10-05.md),
  the execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md)
  and [ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md).
