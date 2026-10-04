---
status: living
date: 2026-10-05
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
dashpot integrate codex                 # hooks plus the bundled skills in ~/.agents/skills/
dashpot integrate claude-code           # hooks plus the bundled skills in ~/.claude/skills/
dashpot integrate <harness> --status    # diagnose hooks, skills, records, identity
dashpot integrate <harness> --remove    # remove Dashpot's hooks and managed skills
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
The same command installs every agent skill Dashpot bundles, among them the
model-invoked `dashpot-issue-work` skill and the user-invoked
`dashpot-execute-issues` skill, from that installed version. Each
copy is Dashpot's to manage only while its `SKILL.md` carries that skill's own
marker. Removal deletes only the Dashpot handlers and the files of each
managed skill; a different skill at the same path is reported and left
untouched, and installation is refused while one is there. If Codex hooks are also
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
| OpenCode | Move it to another location in OpenCode; within the Repository a bound Agent Run moves with it ([ADR 0090](adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md#moves)) | Delete it with `opencode session delete <id>`, or stop the OpenCode server it runs in, with `opencode service stop` or by quitting its `--standalone` client, which orphans every Agent Run on that server; quitting a client of the shared service leaves it running ([OpenCode hosting modes](#opencode-hosting-modes)) |

When the liveness is unknown because the Host Process could not be observed,
the blocker says how to verify it and names
`env LC_ALL=C TZ=UTC ps -p <pid> -o lstart=,args=` as the command that does:
Dashpot records a start time as `ps` renders it in the C locale and UTC, so
the command prints it the same way. An OpenCode session whose server is
observed and runs, but has no live Dashpot plugin instance, is told so
instead, with no command.
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
`src/dashpot/sessions/session_exits.py`. A harness without an entry is
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
its location, and the agent IDs it lists as working, says that Dashpot
cannot tell where a sub-agent works, and says to wait for it to finish. It
also says that a sub-agent stays listed until its harness reports that it
stopped, which one that was stopped or interrupted may never do, so if none
is still working, the way out is to end that session, in the
[harness's words](#agent-sessions-and-worktree-cleanup). A Codex child
interrupted through its own thread reports no stop
([#374](https://github.com/ned2/dashpot/issues/374)). Neither does a Claude
Code sub-agent that its session stops with `TaskStop`, or that a headless
SDK interrupt kills ([#419](https://github.com/ned2/dashpot/issues/419)).
The blocker clears when the last sub-agent's `SubagentStop` arrives, when a
live session starts again, or when the session's process is gone. A sub-agent
dispatched before its session entered another Worktree is listed both in
the record left behind and in the record the session moved to, and holds
the block while it works. Its `SubagentStop` removes it from both: the
stop also reaches each live record of the same session and Host Process in
the Repository's stores, and changes only that record's list, so the
record left behind never places the session there again
([ADR 0102](adr/0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)).
A record left in another Repository's store is out of the stop's reach:
once the session has left the Repository, the record it left there holds
the block until that Worktree records the session's end or the session's
process exits. A session at the Worktree itself is
reported as that Worktree's `agent-session` occupant instead.

A session's end does not clear its sub-agents
([ADR 0095](adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)).
A `SessionEnd` while the session lists live sub-agents ends the session and
its Agent Run as before, but keeps an ended hook record listing those
sub-agents, and that record holds the block while the session's process is
live or its liveness unknown. Each `SubagentStop` from that process removes
its agent, and the record goes with the last one; any other event of a
sub-agent neither revives the session nor lists it as waiting. A
`SessionStart` of the session on the same process, at the same Worktree,
carries the list into the new incarnation; at another Worktree the kept
record stays, and each `SubagentStop` still reaches it. An event of the
session from another process replaces the kept record and drops its list.
A `SessionStart` of a live session from the process its record names carries
the list the same way
([ADR 0097](adr/0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)):
Claude Code and Codex publish one when they compact a session, and its
sub-agents keep working across it. One from another process, or one that
names none, starts with no sub-agents. A compaction's `SessionStart` also
keeps the session's turn state rather than recording it running
([ADR 0100](adr/0100-keep-a-compacted-sessions-turn-state.md)).
A Claude Code Conversation Switch moves the list to the session that runs
its sub-agents
([ADR 0101](adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)).
`/clear`, `/resume` (with an id or through the picker) and `/branch` end the
session with `reason` `clear` or `resume`, then start another session id in
the same process with `source` `clear`, `resume` or `fork`. A working
sub-agent goes on under the new id, and its `SubagentStop` names it. That
`SessionStart` takes over the sub-agents of every ended record of the same
harness and process that ended with a switch `reason`. The new record lists
them first, then the ended record stops listing them, and goes once it lists
none. A Codex `/clear` follows no `SessionEnd`, and a thread a daemon unloads
ends with `reason` `other`, so neither moves a listing. Each `SubagentStop`
also removes its agent from every ended record of its process, whichever
session the record belongs to, so a stop that arrives before the switch's
`SessionStart` still clears it. Another live session's records are never
changed this way; the stopping session's own records left behind are
(above).
Here the blocker says the session *ended with* its sub-agents listed, and names the way out for one that was stopped, was
interrupted or ended with its session and will never report: once none is still working, run
`dashpot work forget-subagents SESSION_ID` from a Worktree of the
Repository. That management command removes only the named session's ended
records that list sub-agents, through the store's compare-and-delete, and
touches no live session, Agent Run or Work Store record; `--harness` chooses
between two harnesses' ended sessions that share the id.
`dashpot integrate <harness> --status` reports such a record as stale,
naming the sub-agents that keep it and the process it waits for.

A Codex session's sub-agents block the same way: the 0.159.3 trace of
[#373](https://github.com/ned2/dashpot/pull/373) (`d0a0a52`) and its 0.160.0
rerun show the blocker naming live Codex children. A Codex child whose own
turn is interrupted publishes no hook, so it keeps the block up until the
session starts again in another process, until the session's process
exits, or until `dashpot work forget-subagents` after the session has ended.
That was measured for a
controller's interrupt of the child's turn; upstream reports the same for
the parent model's `interrupt_agent` tool
([openai/codex#38142](https://github.com/openai/codex/issues/38142)), which
was not measured here. Nothing Dashpot receives tells that child from one
still working: measured on 0.160.0
([#374](https://github.com/ned2/dashpot/issues/374)), the parent's next
prompt and `Stop` arrived while a sibling still worked, so neither ends a
child, and Dashpot does not time one out. Interrupting the parent strands
no child: Esc in a daemon-attached terminal, or a controller's interrupt of
the parent's own turn, publishes the parent's `Interrupt` while each child
works on to its own `SubagentStop`, and Esc after the parent's turn has
stopped publishes nothing and leaves its children working. Interrupting a
child selected in the terminal's agent picker was not measured, nor was Esc
in a standalone terminal. `dashpot work show` lists under each Agent Run the
sub-agents its session still lists as working, with the same way out. A
Codex installation that predates the `SubagentStart` and `SubagentStop`
subscription reports no sub-agents until `dashpot integrate codex` runs
again.

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
| Plain `codex` terminal, the default | The managed daemon, which the first plain terminal starts | Not at `/exit`: `SessionEnd` about 60 s after the thread's last client leaves. A `codex app-server daemon stop` or `restart` publishes `SessionEnd` too, but leaves the run orphaned |
| `codex --remote`, or a controller on the daemon | The daemon | As above |
| A controller on `codex app-server --listen` | That app-server | `SessionEnd` about 60 s after the thread's last client leaves, or when the server exits |
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
  publishes no hook when a controller interrupts a sub-agent's own turn, so
  a sub-agent interrupted that way holds the session running, and blocks
  Cleanup across the Repository, until the thread unloads, resumes, or its
  Host Process is gone; `dashpot work show` and the `sub-agent` blocker say
  so ([#374](https://github.com/ned2/dashpot/issues/374)). Interrupting the
  parent's turn, by Esc in a daemon-attached terminal or through a
  controller, leaves its children working to their own `SubagentStop`.
- **Unloaded.** A daemon-hosted thread whose last terminal or client has
  left stays listed as waiting, at its Worktree and with its run, until the
  daemon unloads it about 60 s later. Its `SessionEnd` then removes the
  session from every Worktree of the Repository, and its run ends about 10 s
  later, once Dashpot has seen the daemon keep running
  ([ADR 0086](adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)).
  Until the unload the thread still occupies its Worktree for Cleanup. A
  thread resumed after it unloaded is a new incarnation of the same session
  with no run, though one resumed on the same daemon within those 10 s can
  show the old run until it ends.
- **Gone.** The Host Process was killed or crashed, and no hook says so, or
  the managed daemon was stopped or restarted. A bound run is listed as an
  [Orphaned Agent Run](domain-language.md) (`◌`) under the gone process
  (`codex pid N`), and an unbound session leaves the Sessions pane. A killed
  daemon orphans every bound run it hosted at once. So does
  `codex app-server daemon stop` or `restart`: the daemon publishes
  `SessionEnd` for every thread it holds, as an unload does, but exits within
  a few seconds of it, so Dashpot leaves each bound run orphaned under the
  stopped daemon rather than ending it (ADR 0086). A stop with a turn
  running first lets the turn finish, and ends no thread, busy or idle,
  until it has. A restart reloads every thread it held
  into the replacement daemon, with no hook: a reloaded thread's next turn
  runs there and is listed unbound beside its orphaned run, and a reloaded
  thread no client holds unloads about 60 s later, leaving the orphan as it
  was ([measured at 0.160.0](agent-harness-server-client-reference.md#managed-daemon-restart-and-stop-at-01600)).
- **Unknown.** Dashpot cannot observe the Host Process, so liveness is
  unconfirmed (`○`). Unknown never ends, carries or continues a run.

To recover an orphaned Codex run, resume the conversation in the Worktree
the run is in (the Sessions pane's `y` copies `codex resume <id> -C <worktree>`) and run
`dashpot work start <issue>` from the resumed session. After a restart the
conversation is already loaded in the replacement daemon, so its next turn
can run `work start` without a resume. Until then the session is listed
unbound beside its orphaned run. `work start` reports that
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

Claude Code support is pinned to **2.1.287** on Linux, the release the
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
  main turn stops. Claude Code publishes no `SubagentStop` for a sub-agent
  its session stops with `TaskStop`, or for one a headless SDK interrupt
  kills, so a sub-agent stopped either way holds the session running, and
  blocks Cleanup across the Repository, until the session ends or starts
  again or its Host Process is gone; `dashpot work show` and the
  `sub-agent` blocker say so
  ([#419](https://github.com/ned2/dashpot/issues/419)). Esc in an
  interactive terminal strands no sub-agent: it works on to its own
  `SubagentStop`. A compaction keeps the state: `/compact` publishes no
  prompt and no `Stop`, so a waiting session stays waiting, and automatic
  compaction runs inside a turn, which reads running until its `Stop`
  ([ADR 0100](adr/0100-keep-a-compacted-sessions-turn-state.md)).
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

Dashpot observes OpenCode v2 only, as
[ADR 0090](adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md)
decides. OpenCode support is pinned to **2.0.22** on Linux, the release the
[OpenCode acceptance run](../README.md#harness-acceptance-runs) last passed
on; its trace is
[`issue-163-opencode-trace.jsonl`](spikes/measurements/issue-163-opencode-trace.jsonl).
Another 2.x release is observed, with a warning from `dashpot integrate
opencode` and its `--status`, and is unsupported until that run passes on
it. OpenCode 1.x is refused: `integrate` will not install while it is on
PATH, and a 1.x server loads the plugin's v1 entry, which publishes nothing
and makes an agent's `dashpot work start` say that OpenCode v1 is refused
([what each release reads as](installation.md#observe-agent-sessions)). The
acceptance run drives the shared service with the TUI, `opencode run` and
the API, `--standalone` clients, the npm package's layout, Sub-agents in the
foreground and the background, forks, moves, plugin edits, repairs and
reloads, deletion, and the service replaced, stopped and killed. The measured
detail is in the [OpenCode v2 experiment](spikes/opencode-v2-spike.md) and
the [plugin protocol experiment](spikes/opencode-v2-plugin-protocol-spike.md).
Background shell commands, `opencode run` under a person's default
permissions, and retried and failed executions are measured on 2.0.22 by the
[background, permissions and failures experiment](spikes/opencode-v2-background-permissions-spike.md).

OpenCode has no command hooks. `dashpot integrate opencode` instead writes a
managed plugin, `plugins/dashpot.js`, to OpenCode's global configuration
directory, bound to this environment's `dashpot-opencode-hook` helper, and
the bundled skills to that directory's `skills/`
([ADR 0079](adr/0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)).
It also writes the managed `dashpot-worker` agent to `agent/dashpot-worker.md`
there: the agent the `dashpot-execute-issues` skill launches each worker
Sub-agent as, whose permissions deny `*session_move`. A worker can otherwise
move its lead's session, and Dashpot would relocate the lead's Agent Run with
it. The deny guards against a worker's mistake, not a determined process,
which can still move a session through OpenCode's HTTP API
([ADR 0093](adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)).
The plugin is thin: it reports OpenCode's own session events, in each
session's own order, to the helper, once per event under a 3 s deadline, and
every decision is the helper's.

An OpenCode server, the process named `opencode` (`opencode.exe` from the
npm package), is the Host Process of every session it serves, and is never
exclusive to one. It sets up one plugin instance, a Publisher Generation, per
location it serves; every instance sees every event of the server, and the
instances share one registry that publishes each event once:

| How the session runs | Host Process | How it ends |
| --- | --- | --- |
| The TUI or `opencode run`, against the shared service | `opencode serve --service`, one per user, which the first client starts; a client is never a Host Process | A client's exit ends nothing. `opencode service stop` stops the service, which publishes nothing about its sessions; they read gone. A TUI of another release, older or newer, replaces the service, and the new service serves the same sessions |
| A `--standalone` TUI or `run` | The client's private `opencode serve --stdio` | Quitting the client stops its server; its sessions read gone |

In the dashboard, an OpenCode session's state means:

- **Running or waiting.** Its server is live, and the state is that of its
  current execution: started reads running, and succeeded, failed or
  interrupted reads waiting. An execution stays running while OpenCode
  retries a provider error, and while a tool waits for a person to answer
  a permission ask. A child session, one with a `parentID`, is a
  Sub-agent of its root and holds it running, a background child past its
  root's execution included; a fork is a root of its own, and inherits no
  run.
- **Unknown.** When the server's last plugin instance is cleaned up and none
  is set up again within a second, as when the plugin is removed, its running
  sessions, and those holding Sub-agents, read unknown while the server runs,
  until their next event; the session and its Issue work are unchanged.
  Cleanup names that server. `opencode reload` cleans every instance up
  before setting any up again, but at 2.0.22 sets them up within that
  second, so a reload changes no session's state. As for every harness,
  unknown also means Dashpot cannot observe the server at all.
- **Gone.** The server exited. A bound run is listed as an
  [Orphaned Agent Run](domain-language.md) (`◌`) under the gone server
  ([ADR 0080](adr/0080-keep-a-retired-opencode-generations-backend-on-its-sessions.md)).
- **Deleted.** `opencode session delete <id>`, or the server's API, ends the
  session and its run. A deletion that reached no live instance is
  recovered when an instance is next set up at the session's location.

A session moves when OpenCode moves it: by the model's move tool or the API.
By the source, the TUI changing directory moves its session too; that is
documented, not measured, and the Issue-work skill moves a session with the
model's own tool instead. Within the Repository its
hook record and a bound run move with it, as a Live Relocation. A move
requested while the session works takes effect when its execution ends. A
move to another Repository, or outside every Project, leaves the run where
it was, reported as `work-session-elsewhere`. Resuming a session from
another directory, with `opencode <directory> --session <id>`, does not move
it: it still runs, and keeps its run, where it was.

To recover an orphaned run, resume the session in a running server, with
`opencode <worktree> --session <id>`, and run `dashpot work start <issue>`
from it: it reports that it restarted the run, and binds a new run to the
new server. To abandon the run instead, run
`dashpot work stop --session <key>` in the run's Worktree, as Cleanup's
`agent-run` blocker names it.

A shell command has an Agent Session Identity only when OpenCode ran it for
a model: OpenCode then sets `OPENCODE_SESSION_ID` and `OPENCODE=1` after the
plugin's `create.before` hook, which deletes both from every shell, blanks
every inherited claim, and sets `DASHPOT_OPENCODE_PID` to its server's pid.
A child session's command is refused as `delegated-session`, and a deleted
session's claim is refused. A command run with the TUI's `!` and a terminal
opened in OpenCode carry no claim, and a refused `work` command says which
one it is. A model's command on a server that has not loaded the plugin
carries OpenCode's variables without the pid, as a terminal that inherited
them does, and its refusal names both causes. Each shell waits at most 3 s
for the server's publications already admitted, so a session's first command
finds its record; a missing or stalled helper delays a command by no more
than that.

**The hour's limit.** OpenCode interrupts a session, and kills its running
command, after about an hour with no session event at its location, and a
running command publishes one only when it starts
([idle eviction](spikes/opencode-v2-spike.md#idle-eviction)). A validation
gate longer than that is lost; split it, or run it outside OpenCode.

**Background commands.** A model's shell command run with `background:
true` outlives the execution that started it, and Dashpot observes the
session, not the command: the session reads waiting while the command
runs, and the command's end wakes it with a new execution. Neither the
dashboard nor `dashpot work show` lists the command, and Cleanup does not
see it: a session that moves out of its Worktree, or is deleted, while its
command runs frees the Worktree for Cleanup with the command still running
there. OpenCode lists a running command with `GET /api/shell` at the
location it started in, named by the `x-opencode-directory` header.
Interrupting the session leaves the command running; stopping the service,
or quitting a `--standalone` client, kills it.

**`opencode run` and permission asks.** Under OpenCode's default rules,
which ask before reading `.env` files or a path outside the session's
location, `opencode run` never waits for a person: without `--auto` it
rejects every ask in its session, and by the source in the session's
Sub-agents, and the turn goes on without the action; with `--auto` it
approves each ask no rule denies. So a Lead turn that a Worker's
`opencode run --session <lead>` report starts has its asks rejected, as
measured without a TUI attached to the Lead, and while the report runs, by
the source, so do the Lead's Workers. An ask no client answers keeps the
session running until it is answered; a TUI shows it to the person.

Not supported, each for its reason:

- **`--server <url>`, local or remote, ACP (`opencode acp`), and the web,
  desktop and editor clients.** Not measured yet;
  [#455](https://github.com/ned2/dashpot/issues/455) tracks supporting
  them. `opencode web` is a v1 entry point.
- **The SDK's own embedded server.** No user need, and whether it loads the
  plugin, and which process is its Host Process, is unknown.
- **Workspaces**, a location with a `workspaceID`. No user need.
- **Two Host Processes serving one session at once.** A Worker's
  `opencode run --session` report to a `--standalone` Lead would make the
  shared service run the lead's session beside its private server, by the
  source; [#454](https://github.com/ned2/dashpot/issues/454) restricts
  leading workers to the shared service, so that no supported arrangement
  causes it, and #455 revisits it for the servers it adds.
- **Every operating system other than Linux.** No test environment, as for
  Codex and Claude Code.
An OpenCode started with `--pure` or `OPENCODE_PURE` loads no plugin and
publishes nothing.

### Agent-facing Issue-work skill

Codex, Claude Code and OpenCode consume the same bundled Agent Skills
payload. The short main workflow reads the repository's instructions, checks
that the installed Dashpot version matches the skill, resolves one fresh Issue, confirms
the Agent Session's Worktree, establishes and verifies its Issue Binding,
follows the repository workflow, and stops the Agent Run only after delivery
and CI are complete. Dispatch and refusal recovery are separate references so
an ordinary in-place opt-in does not load Worktree and harness detail.

Once the run has stopped, the skill takes the session out of its Issue
Worktree, which a live or idle session keeps from
[Cleanup](#agent-sessions-and-worktree-cleanup). A Claude Code session that
entered with `EnterWorktree` returns with `ExitWorktree(keep)`, and enters
the same Worktree again for follow-up changes
([ADR 0085](adr/0085-return-a-claude-code-session-before-entering-another-issue-worktree.md)).
A root OpenCode session moves itself to the Repository's main Worktree
([ADR 0094](adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)).
A Claude Code session started in the Worktree can leave it only for another
Worktree, and a Codex session cannot leave it itself, so for those, and for
an OpenCode move that fails, the skill tells the person what still holds the
Worktree and how it is released, as the Cleanup blocker's way out does.

When work needs another Worktree, the skill delegates path, Branch, base,
collision, and rollback policy to `issue show` and `worktree create`. Claude
Code relocates the running session with `EnterWorktree`. A session already
inside an entered Worktree first returns with `ExitWorktree(keep)`, after
finishing the current Issue when the move is to another one. When
`EnterWorktree` still refuses, the skill hands the work to a fresh Claude Code
session started in the Worktree with one quoted `cd <worktree> && claude`
command, which does not promise working `gh` credentials there
([#274](https://github.com/ned2/dashpot/issues/274)). A root OpenCode
session moves itself with OpenCode's `opencode.session_move` tool, on the
authority of the person's request to work on the Issue in that Worktree
(ADR 0094). It moves only once every Sub-agent and background command it
started has ended, calls the tool alone in its step, and runs no `work`
command and none of the Issue's work in the Worktree until the next step's
`pwd` and `integrate opencode --status` confirm it arrived: the move takes effect when the step ends, and the tool
reports it before then. A bound run moves with it as a Live Relocation, so
`work show` there retains it; an unbound session runs `work start`. A refused
or unconfirmed move falls back to a new OpenCode session started in the
Worktree with `opencode <worktree> --prompt`, after a session that arrived
without Dashpot's record of it has moved back
([acceptance](spikes/opencode-v2-self-relocation-acceptance.md)). Codex prefers a
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
dashpot work forget-subagents SESSION_ID  # forget an ended session's sub-agents
dashpot work assign 124 --worker ID --worktree ../w124  # a Lead assigns a Worker
dashpot work unassign ID       # end that Worker Assignment
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

Under an Agent Run whose session has sub-agents listed as working, in any
Worktree of the Repository, `dashpot work show` adds an indented line naming
them. They hold the run running until the harness reports each one stopped,
which one that was stopped or interrupted may never do: a Codex child
interrupted through its own thread
([#374](https://github.com/ned2/dashpot/issues/374)), or a Claude Code
sub-agent its session stops with `TaskStop`, or one a headless SDK interrupt
kills ([#419](https://github.com/ned2/dashpot/issues/419)). So the line names the
harness's way to end the session if none is still working, as the
[`sub-agent` blocker](#sub-agents-and-worktree-cleanup) does.

### Worker Assignments

A Lead running the bundled `dashpot-execute-issues` skill holds one Agent Run
bound to its Arc, while its Workers implement other Issues in their own Issue
Worktrees. A Worker shares its Lead's Agent Session, so it can hold no Agent
Run of its own. Instead the Lead declares a Worker Assignment for each Worker
it launches, from its own shell
([ADR 0096](adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)):

```bash
dashpot work assign 124 --worker <agent-id> --worktree ../repo-124
dashpot work unassign <agent-id>
```

`assign` confirms the Lead's session and its one active Agent Run, which must
not still be recorded under an earlier, gone Host Process, and resolves the
Issue as `start` does. A Claude Code Lead's next hook event continues such a
run; a Codex or OpenCode Lead recovers it with `work start`, which ends its
assignments, and assigns each Worker again. It requires the Worker's identity, as the
harness's launch returned it, to be a Sub-agent the Lead's own hook records
list as working, by the rule the Issues pane applies below. It also requires
the Worktree to be one of the Repository's. Anything else is refused with
nothing written. A refusal that names no listed Sub-agent can also mean the
harness has not yet published the Worker's start, so retry once it has; a
Worker that already finished cannot be assigned. The identity is:

- **Claude Code:** the `agentId` the Agent tool returns.
- **Codex multi-agent v1:** the `agent_id` that `spawn_agent` returns.
- **Codex multi-agent v2:** `spawn_agent` returns only a task name, so the
  Worker reports its shell's `CODEX_THREAD_ID` and the Lead assigns that.
- **OpenCode:** the `sessionID` the `subagent` tool returns.

The assignment is held on the Lead's run and changes nothing else about it:
not its Issue Binding, run identity, Observation Location, relocation state or
`startedAt`. A relocation or an Orphaned Agent Run's continuation carries it.
`work stop`, any `work start` (one on the run's own Issue restarts the run),
and the run's end at `SessionEnd` end it, and `stop` and `start` name the
assignments they ended. `work show` lists each assignment under its run, and
whether the Lead's records list the Worker as working, list it with unknown
liveness, or do not list it, as the Issues pane would report it. In
`dashpot --json`, each Agent Run carries its assignments as
`workers`, each with its observed `state`, or `null` when nothing reports the
Worker.

The Issues pane counts an assigned Worker toward its own Issue's `◈` cell,
never toward its Lead's Issue, and only while the Lead's hook records report
the Worker:

- **`running`** while the Lead's freshest live or unknown hook record lists
  it, and that record's Host Process is the run's own and is live.
- **`unknown`** while that record's Host Process cannot be observed, or while
  an ended record that
  [kept its Sub-agents](#sub-agents-and-worktree-cleanup) lists it, whichever
  Host Process wrote it.
- **Nothing** otherwise, including once the Worker's stop is reported, while
  its Lead's run is orphaned, or when only another Host Process's record
  lists it. An assignment alone never shows anything, and no Worker counts
  toward an Issue Identity more than one Project observes.

The cell's existing precedence combines assigned Workers with any directly
bound runs. When one Worker on an Issue finishes, any other contributor keeps
the cell lit. No harness reports a Worker's turn state, so a Worker is never
`waiting`.

What each harness reports bounds what the cell can claim:

- **A stop that is never reported.** A Claude Code Worker stopped with
  `TaskStop` and an interrupted Codex child publish no stop, so each still
  reads `running` until the Lead runs `work unassign` or its run ends.
- **A Codex Lead the daemon unloads.** Its run ends, and its assignments with
  it, while its Workers may still work.
- **A followed-up Codex v2 Worker** may read as not working: whether
  `followup_task` publishes a new start is unmeasured.
- **An OpenCode Worker between executions** reads as not working.

An assignment is attribution only. The Worktree it names is a declaration,
not evidence that the Worker is there. It proves neither that the Worker has
drained nor that it handed back, and gives no authority to move anything.
Cleanup still blocks on every live Sub-agent, assigned or not.

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

A Codex command's claim comes from two variables Codex's shell tool exports:
`CODEX_THREAD_ID`, the thread the command runs in, and `CODEX_SESSION_ID`,
the root thread of its Agent Session, which is the `session_id` every hook
of the session publishes. A root's or a fork's shell carries one thread in
both. A Sub-agent's shell carries its own thread beside its root's, no hook
publishes that thread as a session, and the session's `SubagentStart` pairs
the root's `session_id` with it as `agent_id`. The
[worker mechanics trace](spikes/codex-worker-mechanics-spike.md#5-shared-agent-session)
measured this at 0.160.0 for every lead and worker shell, v1 and v2 workers
alike. So the claim names the root, and the root's hook record confirms it
like any other claim. Neither variable is user-documented: the 0.160.0
source describes `CODEX_SESSION_ID` as the shared root-session identity,
and only the TypeScript SDK's README shows `CODEX_THREAD_ID`. A shell
without a readable `CODEX_THREAD_ID` makes no claim, and one without a
readable `CODEX_SESSION_ID`, as before 0.155.1, claims its thread alone.

A command a Codex Sub-agent runs therefore resolves to its root Agent
Session: from the Sub-agent's shell, `dashpot work show` lists that
session's recent events, and `dashpot integrate codex --status` reports the
root's identity. `work start`, `relocate`, `stop`, `assign` and `unassign`
refuse it as `delegated-session`, naming the Sub-agent and its session,
because a Sub-agent's work belongs to its session's Agent Run
([ADR 0067](adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)),
as an OpenCode child session's command is refused. A Claude Code
Sub-agent's shell carries its session's own identity, so Dashpot cannot
tell it apart from the session's own command and does not refuse it.

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
