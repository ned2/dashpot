---
status: living
date: 2026-10-02
---

# Agent sessions

How Dashpot observes a coding-agent session, and how a session declares
the Issue it is working on. Agents working in this repository should read
[AGENTS.md](../AGENTS.md) first: it states the lifecycle rules that apply
here, and this document explains the commands behind them.

## Agent session observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` and
`dashpot-claude-code-hook` publishers. Nothing is installed into a harness
automatically; register the lifecycle hooks once per user with:

```bash
dashpot integrate codex                 # hooks plus ~/.agents/skills/dashpot-issue-work
dashpot integrate claude-code           # hooks plus ~/.claude/skills/dashpot-issue-work
dashpot integrate <harness> --status    # diagnose hooks, skill, records, identity
dashpot integrate <harness> --remove    # remove Dashpot's hooks and managed skill
```

Installation performs a surgical merge of the harness's user-level hook file:
existing hooks and unrelated settings are preserved, the registered command is
the absolute path of this environment's publisher (so hook and observer
versions stay in lock-step), and rerunning `integrate` is idempotent and
repairs stale paths. Because that path must outlive the Issue work it
observes, run `integrate` from the Repository's main working tree or an
installed tool environment: a publisher inside a linked Worktree's `.venv`
disappears with the Worktree, so `integrate` refuses to bind one and
`--status` warns about an existing binding while the file still exists.
The same command installs Dashpot's model-invoked
`dashpot-issue-work` skill from that installed version. Removal deletes only
the Dashpot handlers and files marked as its managed skill; a different skill
at the same path is reported and left untouched. If Codex hooks are also
defined inline in `~/.codex/config.toml`, Dashpot leaves that file alone and
points out that Codex merges both layers.
[`examples/codex-hooks.json`](../examples/codex-hooks.json) shows the equivalent
manual Codex configuration.

The hooks report session lifecycle only: which agent sessions are alive at a
worktree and whether they are running or waiting. Codex registers
`SessionStart`, `UserPromptSubmit`, `Stop`, `Interrupt`, `SubagentStart`,
`SubagentStop`, and `SessionEnd`; Claude Code the same set without
`Interrupt`, plus `PostToolUse` matched to its `EnterWorktree` and
`ExitWorktree` tools alone, so a session that moves to another Worktree, or
back, is placed there as soon as it arrives — one hook invocation per
relocation, never per tool call
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
A session whose main turn has stopped stays running while a sub-agent it
delegated to is still working, since sub-agents share the session's Agent Run
([ADR 0016](adr/0016-hold-a-session-running-while-its-sub-agents-work.md)).
A hook event carrying `agent_id` is a sub-agent's, not its session's: it is
recorded with the parent's freshest record and that record's location, and
it never places, binds, ends or moves the parent
([ADR 0067](adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
An installation made before Codex sub-agents were subscribed reports
`SubagentStart` and `SubagentStop` missing until `dashpot integrate codex`
runs again.
A session that has not
declared an Issue is not listed as Work; it is listed in the Sessions pane
with `no active Issue work` until it opts in with `dashpot work start`. Codex
and Claude Code sessions are observed side by side with distinct identities,
and both may work on the same Issue as separate Agent Runs. One user-level
installation per harness covers every configured repository, including linked
worktrees: each
observation is routed to the checkout the session runs in, landing in that
worktree's ignored `.dashpot/state/sessions/`. Sessions outside any
Dashpot-configured checkout fall back to the platform's normal
application-state location; set `DASHPOT_STATE_DIR` to override that fallback.

### Agent Sessions and Worktree Cleanup

Cleanup refuses to remove a Worktree where an Agent Session's freshest hook
record places it, while that session is live or its liveness is unknown
([ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
This check is separate from the Agent Run, so it holds after `work stop`, and
an idle (`waiting`) session blocks as a running one does. The `agent-session`
blocker in `dashpot worktree check`, the Cleanup preview, and the refusal of
`dashpot worktree remove` names the session, says it is live here or that
its liveness is unknown, and gives its harness's way out of the Worktree:

| Harness | Move the session out | Or end it |
| --- | --- | --- |
| Claude Code | A session `EnterWorktree` brought here runs `ExitWorktree` with `action: keep`, which still works after the session is resumed here. One whose shell came by `cd` changes back to the checkout it started in; its next hook then places it there, leaving any Agent Run behind ([ADR 0074](adr/0074-carry-a-claude-code-run-only-on-its-worktree-tools.md)). A session started in this Worktree has neither: `ExitWorktree` is a no-op there and a `cd` out of its project is reset, so it is ended, or moved by `EnterWorktree` to a sibling linked Worktree ([measured at 2.1.286](agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286)) | End the session |
| Codex | Once its client exits, `codex resume <id> -C <worktree>` resumes it elsewhere; a session holding an Agent Run first declares the move with `dashpot work relocate <worktree>` ([ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)) | End its client. A daemon-hosted thread stays loaded, and keeps the Worktree, until the daemon unloads it about 60 s after its last client leaves ([Codex hosting modes](#codex-hosting-modes)) |
| OpenCode | None: a session never leaves the directory it was created in, even resumed from another one | Quit the OpenCode TUI serving it, or stop the `opencode` backend it runs in; closing an attached client leaves it running. Or delete it in the backend serving it ([OpenCode hosting modes](#opencode-hosting-modes)) |

When the liveness is unknown because the Host Process could not be observed,
the blocker says how to verify it and names
`env LC_ALL=C TZ=UTC ps -p <pid> -o lstart=,args=` as the command that does:
Dashpot records a start time as `ps` renders it in the C locale and UTC, so
the command prints it the same way. A retired OpenCode plugin's session,
whose backend is observed and runs, is told so instead, with no command.
Inside a sandbox's process namespace (`isolated-namespace`) Dashpot cannot
see host processes, so checking again from a shell outside any sandbox
settles it, and a gone process then no longer blocks. When the probe itself
failed, the blocker gives its reason with the pid and the recorded start
time in UTC, which tells the session's process from a later one at the
same pid. A
record that names no Host Process cannot be verified, and blocks until its
session publishes its end; a session that already ended without one is
resumed and ended again. The
[`sub-agent` blocker](#sub-agents-and-worktree-cleanup) ends with the same
harness wording for ending its session.

Cleanup never moves or ends a session itself; moving it as part of a confirmed
removal is [#148](https://github.com/ned2/dashpot/issues/148). Each harness's
way out is one entry in `SESSION_EXITS` in
`src/dashpot/repository/cleanup/obstacles.py`. A harness without an entry is
told to move the session out with its harness's own tool or end it.

### Sub-agents and Worktree Cleanup

Cleanup refuses to remove a Worktree when an Agent Session is there, when
an Agent Run is recorded there, or when its Work Store cannot be read
([ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
A sub-agent is none of these. A Claude Code sub-agent's hooks carry its
parent session's identity and the parent's `cwd`, even when its shell has run
`cd` into an Issue Worktree
([measured on 2.1.285](agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)),
and a Codex sub-agent thread's carry its root thread's identity; Dashpot
records either at its parent's location, and neither holds an Agent Run of
its own. Dashpot knows a session's sub-agents are live but cannot tell which
Worktree any of them works in.

While any live Agent Session in the Repository has a sub-agent
working, removal of every Worktree of that Repository is blocked
([ADR 0066](adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
A session whose liveness is unknown counts as live here. The session is in
the Repository when a hook record places it at one of the Repository's
Worktrees; a session that moved between Worktrees has a record in each, and
its sub-agents are those any of them holds. The `sub-agent` blocker appears
in `dashpot worktree check`, the Cleanup preview, and
`dashpot worktree remove`, and again on confirmation. It names the session,
its location, and the agent IDs, says that Dashpot cannot tell where a
sub-agent works, and says to wait for it to finish or to end that session,
in the [harness's words](#agent-sessions-and-worktree-cleanup). It clears
when the last sub-agent's `SubagentStop` arrives, when the session ends or
starts again, or when the session's process is gone. A sub-agent
dispatched before its session entered another Worktree stays in the record
left behind, so it holds the block until that Worktree
records the session's end or the session's process exits, even after the
session has left the Repository. A session at the Worktree itself is
reported as that Worktree's `agent-session` occupant instead.

A Codex session's sub-agents block the same way: the 0.159.3 trace of
[#373](https://github.com/ned2/dashpot/pull/373) (`d0a0a52`) and its 0.160.0
rerun show the blocker naming live Codex children. A Codex child interrupted through its
own thread publishes no hook, so it keeps the block up until the session's
next `SessionStart` or `SessionEnd`
([#374](https://github.com/ned2/dashpot/issues/374)). A Codex installation
that predates the `SubagentStart` and `SubagentStop` subscription reports
no sub-agents until `dashpot integrate codex` runs again.

The Repository's Worktrees are every Worktree Git registers for it, wherever
it lives on disk, Worktrees under a Worktree Root such as the sibling
`dashpot.worktrees/` included; their
hook stores and the machine-global store are read. A session placed outside
them is not counted, so a sub-agent of a session at a checkout of another
Repository, or of one launched outside every configured checkout, can be
working in a Worktree that Cleanup offers to remove. That gap is accepted
([#357](https://github.com/ned2/dashpot/issues/357)): widening the scope
would block Cleanup across other Repositories or the whole machine for one
sub-agent, and
Cleanup already refuses a dirty Worktree, so the exposure is mainly an
interrupted task in a clean one. A Cleanup preview that would remove a
Worktree, in the dashboard and in `dashpot worktree remove --dry-run`, and
`dashpot worktree check` when it reports a Worktree removable, say so:
"Sub-agents of Agent Sessions outside this Repository are not checked."

### Codex hosting modes

Codex support is pinned to `codex-cli` **0.160.0** on Linux, the release the
[Codex acceptance run](../README.md#harness-acceptance-runs) last passed on;
its trace is
[`issue-161-codex-trace.jsonl`](spikes/measurements/issue-161-codex-trace.jsonl).
Another release is unsupported until that run passes on it. The
[harness reference](agent-harness-server-client-reference.md#hosting-modes-and-daemon-autostart-at-01593)
holds the upstream detail. A Codex thread is one Agent Session wherever it
runs. What changes between modes is its Host Process, the process whose pid
and start time Dashpot records and checks for liveness:

| How the thread runs | Host Process | Graceful end |
| --- | --- | --- |
| Plain `codex` terminal, the default | The managed daemon, which the first plain terminal starts | Not at `/exit`: `SessionEnd` about 60 s after the thread's last client leaves, or at `codex app-server daemon stop` |
| `codex --remote`, or a controller on the daemon or on `codex app-server --listen` | The daemon or that app-server | As above |
| `codex --disable daemon_auto_start`, launched while no daemon runs | The terminal itself | `SessionEnd` at `/exit` |
| `codex exec` | The `exec` process | `SessionEnd` when it exits |

Codex 0.160.0 starts the managed daemon automatically (`daemon_auto_start`
is on by default), so a plain terminal's thread, its hooks and its shells all
belong to the daemon, which outlives the terminal and serves every thread
started that way. A terminal launched with `--disable daemon_auto_start`
while a daemon runs attaches to it like a plain one.

In the dashboard, a Codex session's state means:

- **Running or waiting.** Its Host Process is live, and the state is that of
  its current turn. Input typed during a turn joins that turn and its
  `UserPromptSubmit` arrives when Codex takes it, so the session stays
  running until the joined input's turn stops. A sub-agent the turn spawned
  holds the session running after the turn's `Stop` until its own
  `SubagentStop`, and its prompt does not restart the turn clock. Codex
  publishes no hook when a sub-agent's own turn is interrupted, so a
  sub-agent interrupted that way holds the session running, and blocks
  Cleanup across the Repository, until the thread unloads, resumes, or its
  Host Process is gone.
- **Unloaded.** A daemon-hosted thread whose last terminal or client has
  left stays listed as waiting, at its Worktree and with its run, until the
  daemon unloads it about 60 s later. Its `SessionEnd` then ends its run and
  removes the session from every Worktree of the Repository. Until then it
  still occupies its Worktree for Cleanup. A thread resumed after it
  unloaded is a new incarnation of the same session with no run.
- **Gone.** The Host Process was killed or crashed: no hook says so. A bound
  run is listed as an [Orphaned Agent Run](domain-language.md) (`◌`) under
  the gone process (`codex pid N`), and an unbound session leaves the
  Sessions pane. A killed daemon orphans every bound run it hosted at once.
- **Unknown.** Dashpot cannot observe the Host Process, so liveness is
  unconfirmed (`○`). Unknown never ends, carries or continues a run.

To recover an orphaned Codex run, resume the conversation in the Worktree
the run is in (the Sessions pane's `y` copies `codex resume <id> -C <worktree>`) and run
`dashpot work start <issue>` from the resumed session. Until then the resumed
session is listed unbound beside its orphaned run. `work start` reports that
it restarted the run, and binds a new run, with a new `startedAt`, to the new
Host Process. To abandon the run instead, run
`dashpot work stop --session <key>`. Dashpot never continues an orphaned
Codex run on its own, in any mode
([ADR 0072](adr/0072-keep-every-codex-host-process-non-exclusive.md)).

A controller's `turn/start` with a `cwd` override in another Worktree of the
Repository carries a bound run there at the next turn's `UserPromptSubmit`,
keeping its id, `startedAt` and Issue Binding (Live Relocation,
[ADR 0067](adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
An override sent while a turn runs joins that turn in the old directory, so
the run moves only when the following turn starts at the new one.

Not supported, because they were not measured at the pinned release:
switching conversations inside one terminal (`/new`, `/resume`, `/cd`) and
Codex-managed `/worktree`; Remote Control paired with an account; the Code
Mode remote host; the stdio transport; and every operating system other than
Linux.

### Claude Code hosting modes

Claude Code support is pinned to **2.1.286** on Linux, the release the
[Claude Code acceptance run](../README.md#harness-acceptance-runs) last passed
on; its trace is
[`issue-162-claude-trace.jsonl`](spikes/measurements/issue-162-claude-trace.jsonl).
Another release is unsupported until that run passes on it. The
[harness reference](agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286)
holds the measured detail. The acceptance run drives headless clients and
supervised workers; the interactive terminal runs the same `claude` process
and hooks, measured at 2.1.278 and 2.1.285. Every Claude Code session runs in
a process of its own, which is its Host Process; its sub-agents share it:

| How the session runs | Host Process | Graceful end |
| --- | --- | --- |
| Interactive `claude` terminal, or headless `claude -p` | The `claude` process | `SessionEnd` when it exits |
| Supervised worker, `claude --bg` | The worker the supervisor runs for the session: a versioned executable with `--session-id` or `--resume`, or a claimed `claude bg-spare` | `SessionEnd` at `claude stop` or `claude daemon stop`; none when the supervisor retires an idle worker |

In the dashboard, a Claude Code session's state means:

- **Running or waiting.** Its Host Process is live, and the state is that of
  its current turn; a sub-agent still working holds it running after the
  main turn stops.
- **Moved.** `EnterWorktree`, and `ExitWorktree` with `action: keep`, move
  the session and carry a bound run with it, keeping its id, `startedAt` and
  Issue Binding. A Bash `cd` into another Worktree only places the session
  there, and the run left behind is reported as `work-session-elsewhere`
  until `work start` there switches it or the shell returns
  ([ADR 0074](adr/0074-carry-a-claude-code-run-only-on-its-worktree-tools.md)).
  `EnterWorktree` enters an Issue Worktree only when the session is not
  inside a Worktree it entered. Such a session, resumed there or not, is
  refused a direct switch to another one, so it returns with
  `ExitWorktree(keep)` to the directory it entered from and enters the next
  ([ADR 0085](adr/0085-return-a-claude-code-session-before-entering-another-issue-worktree.md)).
- **Gone.** The Host Process was killed or crashed: no hook says so, and a
  bound run is listed as an [Orphaned Agent Run](domain-language.md) (`◌`).
  A worker killed under a live supervisor is replaced within seconds by a
  new process for the same session. A worker killed while no supervisor runs
  is listed `failed` until `claude respawn`. A worker left idle with no
  client attached is retired by its supervisor about an hour after its last
  turn, also without a hook, and is listed `done` until `claude attach`
  respawns it. A terminal session resumes with
  `claude --resume <id>`; the Sessions pane's `y` copies
  `cd <worktree> && claude --resume <id>`.
- **Unknown.** Dashpot cannot observe the Host Process, so liveness is
  unconfirmed (`○`). Unknown never ends, carries or continues a run.

An orphaned Claude Code run continues by itself
([ADR 0053](adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md))
at the first hook its session's new Host Process publishes from the
Worktree holding the run, and the hook tells the agent so. A replacement
worker's `SessionStart` reports the directory the worker was first
dispatched from, so a worker that had entered another Worktree continues its
run only at its next turn there; stopped before that turn, its `SessionEnd`
ends the run
([ADR 0075](adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md)).
Replacing the supervisor with `claude daemon stop --keep-workers` changes
nothing: workers keep their processes and runs. `claude stop` ends a worker's
run, so a later `claude respawn` starts unbound.

`ExitWorktree(remove)` of a Worktree that `EnterWorktree` created by `name`
is not supported for Issue work: it deletes the Worktree and the run in it.
Not supported, because they were not measured at the pinned release: several
`claude attach` clients on one worker at once; Remote Control, whose server
needs a claude.ai login the isolated runs do not have; the Agent SDK, agent
teams, cloud and web sessions and the desktop app; and every operating system
other than Linux, including macOS's supervised process shapes.

Dashpot still records the hooks an unsupported release or mode publishes, but
nothing vouches for what they mean. Its recovery is the same in every mode:
`dashpot work show` from inside the session says which run it holds and
where; `work-session-elsewhere` is answered by `dashpot work start` where the
session now is; and a run whose session is not coming back is ended with
`dashpot work stop --session <key>`. A new release becomes supported by
passing the acceptance run.

### OpenCode hosting modes

OpenCode support is pinned to **1.18.30** on Linux, the release the
[OpenCode acceptance run](../README.md#harness-acceptance-runs) last passed
on; its trace is
[`issue-163-opencode-trace.jsonl`](spikes/measurements/issue-163-opencode-trace.jsonl)
([ADR 0081](adr/0081-support-opencode-1-18-30-on-linux.md)). Another release
is unsupported until that run passes on it, and
`dashpot integrate opencode --status` warns about one. The
[harness reference](agent-harness-server-client-reference.md#the-local-tui-and-shutdown-through-dashpot-at-11830)
holds the measured detail.

OpenCode has no command hooks. `dashpot integrate opencode` instead writes a
managed plugin, `plugins/dashpot.js`, to OpenCode's global configuration
directory, bound to this environment's `dashpot-opencode-hook` helper, and
the Issue work skill to that directory's `skills/`
([ADR 0079](adr/0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)).
The plugin is thin: it runs the helper once per publication, under a
deadline, with native metadata only, and every decision is the helper's.

An OpenCode backend, the process named `opencode`, is the Host Process of
every session it serves, and is never exclusive to one. Each plugin instance
is a Publisher Generation, and only the generation that owns the backend's
directory publishes
([ADR 0077](adr/0077-observe-opencode-through-one-publisher-generation-per-plugin-instance.md)):

| How the session runs | Host Process | How it ends |
| --- | --- | --- |
| Local TUI, `opencode [directory]` | The TUI itself: one `opencode` process that is its own backend | Quitting the TUI, or closing its terminal, retires its plugin instances; its sessions read gone once it exits |
| `opencode serve`, with `opencode run --attach` or `opencode attach` clients | The `serve` process; a client is never a Host Process | A client's exit ends nothing: its session, and a turn it started, carry on in the backend. Stopping the backend, by SIGTERM or a kill, publishes nothing; its sessions read gone |

OpenCode publishes no end for a session when its backend exits; only a
deletion ends one. In the dashboard, an OpenCode session's state means:

- **Running or waiting.** Its backend is live, and the state is that of its
  current turn: `busy` and `retry` read running, `idle` waiting. An
  interrupted turn, and one the provider refused, end waiting. A child
  session, one with a `parentID`, is a Sub-agent of its root and holds it
  running, a background child past its parent's turn included; a fork is a
  session of its own, and inherits no run.
- **Unknown.** When OpenCode reloads or disposes of an instance, its
  generation retires, and its sessions read unknown while their backend runs,
  until the next generation publishes them at their next turn or command;
  the session and its Issue work are unchanged. Cleanup names that backend.
  As for every harness, unknown also means Dashpot cannot observe the
  backend at all.
- **Gone.** The backend exited: a quit TUI, a closed terminal, a stopped or
  killed `serve`. A bound run is listed as an
  [Orphaned Agent Run](domain-language.md) (`◌`) under the gone backend
  ([ADR 0080](adr/0080-keep-a-retired-opencode-generations-backend-on-its-sessions.md)).
- **Deleted.** Deleting a session through the backend serving it, by its
  HTTP API's `DELETE /session/<id>`, ends the session and its run; its other
  sessions carry on. Deleting from the TUI was not measured.

There is no automatic continuation for OpenCode. To recover an orphaned run,
resume the session, with `opencode <worktree> --session <id>` or a client of
a new backend, and run `dashpot work start <issue>` from it: it reports that
it restarted the run, and binds a new run to the new backend. A session
resumed from another directory still runs in the one it was created in, and
its run stays there. To abandon the run instead, run
`dashpot work stop --session <key>` in the run's Worktree, as Cleanup's
`agent-run` blocker names it. Live Relocation is unsupported.

A shell command gets an Agent Session Identity only when the plugin gives it
one: it blanks every inherited claim, publishes the command's own bootstrap,
and sets `DASHPOT_OPENCODE_SESSION_ID`, `DASHPOT_OPENCODE_GENERATION` and
`DASHPOT_OPENCODE_PID` only once the helper acknowledged that bootstrap, for a
root session
([ADR 0078](adr/0078-give-an-opencode-command-a-claim-only-for-its-own-bootstrap.md)).
A command typed after `!` in the TUI is the session's own and carries its
claim. A child session's command, a terminal the user opened through the
backend, and a command whose helper was missing or slow carry no claim, and a refused
`work` command says why from `DASHPOT_OPENCODE_UNCORROBORATED`. A missing
helper costs a turn nothing; a stalled one delays each command until the
plugin's deadline, about 3.3 s at the pinned release. The claim is refused once its
generation retires or OpenCode deletes the session.

**`opencode session delete` and Issue work.** Before deleting a bound
session with the `opencode session delete` command, stop its Issue work with
`dashpot work stop` from inside it, or delete it through the backend serving
it instead. The command loads the plugin in a process of its own,
for the directory it runs in:

- Run in the session's own directory, it removes the session's hook record
  but not its run. The run still names the backend that served the session,
  which still runs, so it is not orphaned; Cleanup refuses the Worktree with
  an `agent-run` blocker saying no hook record of the session is left while
  that backend still runs, and
  `dashpot work stop --session <key>` is refused as still running. Quit or
  stop that backend, then run `dashpot work stop --session <key>` in the
  run's Worktree, the command the blocker names.
- Run in any other directory, it still deletes the session in OpenCode, but
  the helper refuses the deletion as outside the instance that published it,
  and Dashpot changes nothing: the session stays listed as last published,
  and a bound run stays with it, with Cleanup saying to stop it inside a
  session that no longer exists. Quit or stop the backend that served it;
  the run then reads orphaned, and `dashpot work stop --session <key>` in
  the run's Worktree ends it.

Not supported, because they were not measured at the pinned release:
`opencode web`, ACP (`opencode acp`), the SDK's own server, the desktop app
and editor extensions; a remote backend; two backends serving one session at
once; and every operating system other than Linux. A background child runs
only under OpenCode's experimental
`OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS` flag. An OpenCode started with
`--pure` or `OPENCODE_PURE` loads no plugin and publishes nothing.

### Agent-facing Issue-work skill

Codex, Claude Code and OpenCode consume the same bundled Agent Skills
payload. The short main workflow reads the repository's instructions, checks
that the installed Dashpot version matches the skill, resolves one fresh Issue, confirms
the Agent Session's Worktree, establishes and verifies its Issue Binding,
follows the repository workflow, and stops the Agent Run only after delivery
and CI are complete. Dispatch and refusal recovery are separate references so
an ordinary in-place opt-in does not load Worktree and harness detail.

When work needs another Worktree, the skill delegates path, Branch, base,
collision, and rollback policy to `issue show` and `worktree create`. Claude
Code relocates the running session with `EnterWorktree`. A session already
inside an entered Worktree first returns with `ExitWorktree(keep)`, after
finishing the current Issue when the move is to another one. When
`EnterWorktree` still refuses, the skill hands the work to a fresh Claude Code
session started in the Worktree with one quoted `cd <worktree> && claude`
command, which does not promise working `gh` credentials there
([#274](https://github.com/ned2/dashpot/issues/274)). An OpenCode session
cannot leave the directory it was created in, so the skill hands Issue work in
another Worktree to a new OpenCode session started there with
`opencode <worktree> --prompt`, which the acceptance run does not drive. Codex prefers a
sequential resume of the same Agent Session with `codex resume <session-id> -C
<path>`: the old client releases the thread by exiting, and the resumed turn
must publish fresh lifecycle evidence. Codex itself keeps a competing client
read-only until the owner exits, and that client publishes no hooks
([thread ownership](agent-harness-server-client-reference.md#thread-ownership-and-competing-resume)).
An active run first declares its exact target with `work
relocate <path>`; the resumed hook moves that same run only after the old client
is no longer live, and `work show` verifies the preserved binding. An unbound
session still runs `work start` after arrival. Codex versions that cannot
perform that resume use a disclosed fresh-session fallback, which creates a
new Agent Session and cannot preserve the old run. A person may instead run
`/cd <path>` in the live Codex client to keep the model's context: Codex forks
the conversation into a new thread there, so Dashpot observes a new Agent
Session with its own hook `session_id`, which declares its own Issue work
with `work start` after the old session ends its run with `work stop`
([working-directory change](agent-harness-server-client-reference.md#working-directory-change-and-worktree-commands)).
A shell tool's `cd` remains
repository preparation rather than session relocation.

Each refresh checks that a session's recorded process is still the one that
published the record. A graceful `SessionEnd` removes the session's record and
ends the session's Agent Run in the Work Store, wherever in the Repository's
worktrees it is recorded
([ADR 0015](adr/0015-reconcile-the-agent-run-at-session-end.md)). The declared
Codex resume in
[ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)
is the one exception: `SessionEnd` preserves the pending run before removing
the old client's hook record. A
session that was killed, or whose `SessionEnd` hook never ran, is dropped
quietly and its stale record and lock file are cleaned up, unless it leaves
an Orphaned Agent Run behind, which keeps the record for when it was last seen
(see below). When the
process cannot be observed at all (for example from inside a sandboxed process
namespace) the session is shown with `unknown` state rather than assumed to
have exited. `dashpot integrate <harness> --status` classifies every session
record as live, unknown, stale, or unreadable and lists the stale ones, which
is where to look when lifecycle events seem not to be delivered.

Every hook record carries the harness's own Agent Session Identity (its hook
`session_id`) beside the host process the hook observed from outside any
sandbox. Observation joins a Work Store record to its hook record by that
harness-scoped native identity, with compatible process evidence. Missing named
evidence produces unknown activity; another conversation on the same backend
cannot supply its state. Legacy unnamed runs remain unresolved and do not
consume a named hook observation.
Liveness and orphan detection still follow the host process: a session's
hooks always run on the host, so its record names the harness process even
when the session's own commands cannot see it.

## Issue work opt-in

The installed `dashpot-issue-work` skill is the agent-facing workflow for these
commands. An Agent Session declares which Issue it is working on from inside
the session, at the Worktree where the work happens:

```bash
dashpot work start 123         # a bare Issue Number
dashpot work start '#123'      # the same Issue, # quoted for the shell
dashpot work start owner/repository#123   # or a full Issue Reference
dashpot work show              # list active Issue work at this worktree
dashpot work relocate ../target-worktree  # preserve this Codex run across resume
dashpot work relocate .        # cancel a pending move after resuming here
dashpot work stop              # end this session's run; the session stays alive
dashpot work stop --session KEY  # end the orphaned run of a session that is gone
```

A bare number and its `#`-prefixed form resolve to the same Issue; Local
Issue Markdown Projects also accept the Issue's slug.

`dashpot work start` resolves the Reference against the Project configured at
that worktree, requires it to identify exactly one currently observed Issue,
and atomically records the resulting durable Issue Identity in the Project-local
Work Store (`.dashpot/state/work/`). Running `start` again switches the session
to a new Issue. A session holds one active run across the linked Worktrees of
its Git Repository
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)),
and its own hooks say where it is: the freshest hook record for the session
across the stores of every Worktree `git worktree list` reports, plus the
global store. When that record places the session at the Worktree where
`start` runs, a run it still holds at another Worktree is a move the hooks
did not carry (a Claude Code shell `cd` into a nested Worktree, for
instance): `start` ends it and reports
`switched from <ref> at <old Worktree> to <ref> at <new Worktree>`. When it
places the session elsewhere, the command is running where the session is
not — a tool call that changed directory, or a sub-agent's shell — and
`start` refuses, names that Worktree, and writes nothing. `stop` ends the
session's run wherever in the Repository it is recorded. A session with no
hook record anywhere starts where it runs, as before, so the invariant is
enforced only once the harness hooks are installed; runs recorded by an older
Dashpot, or across independent clones, keep the `work-session-conflict`
warning. Once recorded, the binding survives
repository renames, Issue Reference edits, Local Issue moves, and transfers
between configured Projects.
The ordinary TUI continues to show current References; raw identities remain in
headless output and diagnostics.

Run inside an Agent Session, `dashpot work show` ends with that session's
recent outcomes from the [Event Log](installation.md#read-the-event-log):
its hook and `work` command outcomes, Agent Session and Agent Run changes,
and failures, at most 20 from the last 7 days, oldest first. They are read
from every Worktree of the Repository and the machine-local fallback, one
day at a time and only as far back as needed. A session with no such
events, or a command no supported session encloses, adds nothing, and the
Issue work lines above them are unchanged. `dashpot events --session ID`
reads the rest.

`dashpot work relocate PATH` is the explicit first phase of preserving an
active Codex Agent Run through a sequential resume. It accepts only the live
session's one recorded run, a confirmed Codex Agent Session Identity, fresh
hook evidence at the current Worktree, and an exact linked Worktree target. It
adds a Relocation Intent without changing the Issue Binding, run identity, or
`startedAt`. The old client's `SessionEnd` then retains the pending record. A
hook at the intended target completes the second phase only when no hook record
places a live or unobservable client with that identity elsewhere; completion
moves the same Work Store record, adopts the resumed process, working directory,
and Branch, and clears the intent. When the session's freshest live record
places it at neither its origin nor the intended target, the pending run
emits `work-relocation-mismatched`; otherwise concurrent locations emit
`work-relocation-concurrent`. Either case, a missing hook, or unreadable state
leaves the intent unchanged and cannot make `work start` reassign it. A
proven-gone old process permits recovery when `SessionEnd` was lost. `work
relocate .` cancels after the same session resumes at its origin, while `work
stop --session KEY` explicitly ends an abandoned pending run. Claude Code
continues to move its live process with `EnterWorktree` and `ExitWorktree`
instead.

A live session that moves without ending is a Live Relocation
([ADR 0067](adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
For Codex, a session-scoped `UserPromptSubmit` at another Worktree of the
Repository, from the Host Process the run records, carries its run there with
its session key, run identity, `startedAt` and Issue Binding, adopting the new
working directory and Branch; the hook reports it as `relocated`. It carries
only when that hook record is the session's freshest, the record it follows
is from the same Host Process and not ended, no `SessionStart` began a new
incarnation at the target since, no other run of the session is there, and
any Relocation Intent names exactly that target, which the carry completes.
Every other event, a sub-agent's included, carries nothing, and an unbound
session stays unbound. Claude Code's designated events are the `PostToolUse`
of `EnterWorktree`, and of `ExitWorktree` with `action: keep`, so a bound
session that enters a Worktree or returns from one takes its run along under
the same conditions; its shell `cd`, which moves the `cwd` of its later
hooks, carries nothing
([ADR 0074](adr/0074-carry-a-claude-code-run-only-on-its-worktree-tools.md)). A run left
at one Worktree while its session's freshest live record places it at
another is reported as `work-session-elsewhere`, naming both; run
`dashpot work start` there or `dashpot work stop`. A `SessionEnd` also
removes the session's older records elsewhere in the Repository that its own
Host Process wrote no later than it, so a record a move left behind does not
read live after the session ends while a shared Codex process keeps
running.

### How the session is identified

`dashpot work start`, `work relocate`, and `work stop` identify the enclosing
Agent Session through one harness-neutral seam with a
[Harness Adapter](domain-language.md) per supported harness
(`src/dashpot/sessions/harnesses.py`). Both visible and sandboxed commands require a
native identity claim confirmed by its freshest hook record of the same
harness across the Repository's reachable hook stores. The record must describe
a live or unknown session. Visible host ancestry corroborates the harness and
full PID/start-time pair; a sandbox helper never stands in for the host.
A Claude Code host is a process named `claude`, or a worker of Claude Code's
background supervisor: that is named after its version, like the supervisor
and PTY hosts beside it, so it is located only when its argument vector starts
with a measured worker shape
([experiment](spikes/claude-code-supervised-worker-process-spike.md#implications-for-dashpot)).
Claude Code's claimed host PID must also agree when present. Process evidence
alone cannot authorize starting, switching, stopping, or relocating Issue work,
even if only one session hook is currently visible.

New Agent Runs use a deterministic harness-prefixed SHA-256 digest of the native
session ID as their storage key. Full stored identity remains authoritative:
a conflicting or unreadable destination is refused. Existing process-keyed
records carrying native IDs remain selectable without passive renaming;
observation and continuing relocation preserve their run identity, `startedAt`,
Issue Binding, and Relocation Intent. Explicit `work start` retains the selected
storage key and keeps its documented new-run/switch semantics.

An unnamed legacy record cannot prove ownership, even when its process differs
from the current runtime: a resumed conversation can change processes. Any such
record of the same harness in a linked Worktree blocks implicit adoption or new
work beside it. Inspect `dashpot work show` at that Worktree. Once its recorded
process is proved gone, use `dashpot work stop --session KEY` there to end exactly
that run, then declare fresh work from the intended named session. A live or
unobservable recorded process refuses external stop; for a legacy record with
neither native identity nor process evidence, the explicit key is the supported
recovery selection. Never reconstruct its Issue Binding from a Branch, Worktree,
or conversation history. These intentional legacy restrictions are documented in
[ADR 0038](adr/0038-isolate-native-agent-session-identities.md).

A missing, unreadable, ended, gone, cross-harness, or PID-mismatched hook
record refuses the opt-in with a message naming the record and the
`dashpot integrate <harness> --status` check to run, and writes nothing. When
the environment names live sessions of both harnesses — a Codex session
started from inside a Claude Code shell inherits both — the opt-in is refused
as ambiguous until `DASHPOT_AGENT_SESSION=<harness>:<session id>` states which
session the command belongs to; that explicit claim is validated like any
other. `dashpot integrate <harness> --status` reports the identity the
current environment claims for that harness and whether its hook record here
confirms or rejects it, which is the first thing to check when a sandboxed
`work start` is refused.

The Work Store is the sole authority for Issue association. Collection
correlates each recorded run with the hook's lifecycle observations by Agent
Session Identity (see
[Agent session observation](#agent-session-observation)); a hook record
that carries a global Issue binding (the retired
`DASHPOT_ISSUE_ID`/`DASHPOT_ISSUE_REF` environment convention) is rejected with
a diagnostic pointing at `dashpot work start`, never silently combined. When a
session is gone but its Work Store record remains, that record is an Orphaned
Agent Run: it stays listed with `orphaned` set, `state` unknown,
`lastActivityAt` when the session was last seen, and `hostRestarted` when the
host has booted since its process started. Resuming the same conversation at
the same Worktree continues it, keeping its Issue Binding, when its harness
runs one session per host process (Claude Code; not Codex) and the recorded
process is proven gone; the hook then tells the resumed agent so
([ADR 0053](adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)). The Sessions pane's `y`
copies the resume command, and `dashpot work stop --session <key>` ends a run
that will not be resumed. Dashpot never reassigns Issue work. It ends a run on its own only when the harness delivers
its session's graceful `SessionEnd`, except that a declared Codex relocation
retains the run until verified resume or explicit stop. Ending evidence must
match the recorded runtime, and conditional deletion rechecks the complete run
under its record lock so delayed evidence cannot clear replacement work. A killed session
without a valid target continuation still leaves visible work for a person to
end.
