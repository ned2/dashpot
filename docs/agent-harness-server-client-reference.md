---
status: living
date: 2026-10-05
---

# Agent harness server and client reference

This reference explains how Claude Code, Codex CLI, and OpenCode host
conversations, connect clients, execute tools, and report lifecycle changes.
Use it to distinguish conversation identity from the processes and connections
that serve it, and to choose the right upstream interface without repeating
three separate investigations.

Dashpot's proposed integration behavior belongs in the
[agent runtime lifecycle design](proposals/agent-runtime-lifecycle-design.md), the
[OpenCode integration design](proposals/opencode-integration-design.md) and the
[Codex relocation and handoff design](proposals/codex-relocation-handoff-design.md), not
in this reference. The [domain language](domain-language.md#observation) defines
Dashpot's Agent Session and Agent Run; upstream products' terms are preserved
below where their meanings differ.

## Scope and evidence

| Harness | Evidence available | Limits |
| --- | --- | --- |
| Codex | Isolated Linux experiment on `0.155.1` (2026-09-19): two root threads on one `app-server --listen`, fork, sub-agent, second client, client departure, interrupt, unsubscribe and unload, `codex exec` and `exec resume`, competing resume on both routes, SIGKILL and SIGTERM of the server, and stored-thread resume with a `cwd` override; a second isolated experiment the same day on the managed daemon: `--remote` and plain terminals attached to it, a controller's `thread/resume` and `turn/start` `cwd` overrides on a loaded thread, a turn queued behind a running one, terminal exit and unload; a third isolated experiment (2026-09-20) on the sequential `codex resume <id> -C <path>` route with no daemon, with the daemon holding the thread loaded, and after the daemon unloaded it; the [#161 acceptance run](#hosting-modes-and-daemon-autostart-at-01593) on `0.159.3` (2026-10-01): daemon autostart, standalone and plain terminals, `remote-control start`, input joined to a running turn, and Dashpot's lifecycle through the managed daemon, extended (2026-10-02) for [#355](https://github.com/ned2/dashpot/issues/355) with sub-agents that outlive their parent's turn and a sub-agent's interrupt, and rerun on `0.160.0` (2026-10-02) for [#375](https://github.com/ned2/dashpot/issues/375) with the fixture daemon's updater off, for [#374](https://github.com/ned2/dashpot/issues/374) with a child interrupted while its sibling works and the parent's own turn interrupted, and for [#356](https://github.com/ned2/dashpot/issues/356) with the managed daemon's `SessionEnd` deferred to a settler and the daemon's hooks inheriting a terminal's `COLUMNS`; the [#356 acceptance run](#managed-daemon-restart-and-stop-at-01600) on `0.160.0` (2026-10-02): the managed daemon's unload, `daemon restart` and `daemon stop` with a turn running, the `SessionEnd` hook clamp, a detached process outliving the hook and the daemon, and threads reloaded into the replacement; the [#479 run](#codex-exec-signals-at-01600) on `0.160.0` (2026-10-05): SIGINT, SIGTERM and SIGKILL to detached `codex exec` processes; current official documentation; pinned `rust-v0.154.0` source and post-release `main` PRs read statically on 2026-09-13 | `/cd`, `/new` and `/resume` inside a terminal, `/worktree`, Remote Control pairing, the Code Mode remote host, stdio transport, and other operating systems unmeasured; the pinned source reading remains the only account of those modes |
| Claude Code | Isolated Linux experiment on `2.1.276`: headless, resume, fork, subagent, and background supervisor/worker modes; a second on `2.1.278` (2026-09-19): interactive sessions on a pseudo-terminal with a development channel, `EnterWorktree` and `ExitWorktree` from each launch state, channel delivery during a turn and beside a background job; a third on `2.1.285` against `2.1.280` (2026-09-30): sub-agents under bypass and auto mode, interactive turns, resume of a running background session, `--desktop`, `--bg` workspace trust, and `--setting-sources`; a fourth on `2.1.285` (2026-10-01): `ps` process names and argument vectors of the supervisor, PTY hosts, spares, and workers through abrupt exit and respawn; a fifth on `2.1.285` (2026-10-01): what sub-agent hooks carry and where a sub-agent's hooks place it; a sixth on `2.1.286` (2026-10-01), through Dashpot's real publisher: worktree tools, a shell `cd`, supervised worker replacement, respawn and idle eviction, repeated on `2.1.287` (2026-10-02); a seventh on `2.1.286` (2026-10-02), also through Dashpot's real publisher: when `EnterWorktree` accepts a linked Worktree outside `.claude/worktrees/`, from each launch state and after resume, repeated on `2.1.283` and `2.1.287`; current official docs and Python SDK source | Remote Control attachment, SDK, agent teams, cloud, and plugin-distributed channels untested; supervised process shapes on macOS unmeasured; Remote Control server mode refused to start without a claude.ai login; resume of a mid-turn background session, the desktop app, and `--setting-sources` forwarding to spawned sessions unmeasured |
| OpenCode | Isolated Linux experiment on `1.18.30`, legacy plugin path (2026-09-12), with that release's source and the official docs; the [#393 experiments](spikes/opencode-v2-spike.md) on `2.0.22` (2026-10-02 and 2026-10-03): the shared service and its plugin instances, shell identity, Sub-agents, moves, `--standalone`, idle eviction, and the plugin API Dashpot's plugin uses; the [#407 acceptance run](#the-shared-service-through-dashpot-at-2022) on `2.0.22` (2026-10-03), through Dashpot's real plugin and helper: the TUI, `opencode run` and the API against the shared service, `--standalone` clients, the npm layout, foreground and background Sub-agents, forks, moves, plugin edits, repairs, reloads and removal, deletion, and the service replaced by 2.0.21 and back, stopped and killed | `opencode web`, ACP, the SDK's own server, `--server <url>`, remote servers, the desktop app, editor extensions and other operating systems unmeasured; OpenCode 1.x is refused, so its measurements describe no supported mode |

Documentation was reviewed on 2026-09-13; OpenCode measurements were taken on
2026-09-12, 2026-10-02 and 2026-10-03, Claude Code measurements on 2026-09-18, 2026-09-19,
2026-09-30, 2026-10-01 and 2026-10-02, and Codex measurements on 2026-09-19,
2026-09-20, 2026-10-01 and 2026-10-02. Current documentation
and source branches can change independently
of an installed binary. Version-sensitive commands and identity mappings need
checking when the supported release changes. Statements marked as inference or
unverified are not runtime findings.

This reference consolidates the Codex workflow research supplied from the main
checkout, the Codex and Claude comparison notes, and the reusable findings from
the [OpenCode experiment](spikes/opencode-identity-lifecycle-spike.md), the
[Claude Code experiment](spikes/claude-code-identity-lifecycle-spike.md), the
[Codex experiment](spikes/codex-identity-lifecycle-spike.md), the
[Cleanup handoff feasibility experiment](spikes/cleanup-session-handoff-feasibility-spike.md)
on both, and the
[Claude Code 2.1.285 changes experiment](spikes/claude-code-2-1-285-changes-spike.md). Each
experiment remains a dated evidence record with its fixtures and trace;
maintain general server/client facts here instead of creating another
comparison note.

## Shared concepts

The following are explanatory terms for comparing the products, not additional
Dashpot domain entities:

| Concept | What it describes | What it does not establish |
| --- | --- | --- |
| Conversation | Stored history and its native identity; possibly loaded for execution | A live process, active turn, or attached client |
| Turn and tool execution | Work performed for a request within a conversation | Permanent conversation lifetime |
| Executing worker | Process hosting the agent loop or tool execution | A unique conversation in every harness mode |
| Server or supervisor | Service exposing control or managing workers | That each conversation shares that service's PID |
| Client and subscription | A terminal, editor, browser, or protocol connection controlling or observing work | Ownership of the conversation's entire lifetime |
| Checkout / Worktree | Files against which commands execute | Conversation identity, process identity, or exclusive access |

“Restart the backend” is ambiguous across these products. Name whether it means
replacing a shared agent runtime, restarting a supervisor while workers survive,
or restarting one conversation's worker. Likewise distinguish a disconnected
client, an idle conversation, an unloaded conversation, and deleted history.
The product sections below supply the evidence for these distinctions.

### Hosting comparison

| Mode | Controller and execution | Conversation concurrency | Evidence of ownership |
| --- | --- | --- | --- |
| Codex App Server | TUI/custom client to app-server; execution host is a separate connection | Multiple threads per app-server, measured as one `codex` process hosting root, forked, and sub-agent threads with their shells and hooks below it | Native thread IDs and thread/turn events; measured: a departing client changes nothing, a second client attaches to a loaded thread without a hook, and a competing resume from another process is refused while the server holds the thread |
| Claude interactive Remote Control | Web/mobile controls an existing local session | One remote session per interactive process | Local conversation continues when Remote Control disconnects |
| Claude Remote Control server | Anthropic-routed clients to a local server | Multiple sessions; exact worker ancestry unverified, and the server refused to start under an API key alone | Server session management, distinct from browser attachment |
| Claude background supervisor | Agent view/attach controls supervised workers | One worker process per background session, measured as supervisor → PTY host → worker | Measured: a replacement supervisor adopts surviving workers with unchanged pids and session IDs |
| Claude Python Agent SDK | Application controls its default CLI subprocess | Persistent client keeps one conversation; separate calls can own separate workers | Transport owns subprocess lifecycle |
| OpenCode serve | HTTP/SSE or attached CLI to one backend | Multiple native sessions sharing the measured backend PID | Native session events and command-scoped plugin context |

Source details, deployment boundaries, and caveats are in each harness section.
Sharing a server is independent of sharing history, sharing checked-out files,
or having multiple clients operate on the same conversation. It does not by
itself establish inter-agent collaboration, lower model costs, or safe parallel
edits. Distinct Worktrees isolate ordinary checked-out files while retaining
shared Git metadata; process isolation does not supply file isolation.

### Compaction and conversation switches with a sub-agent working

Measured under [#448](https://github.com/ned2/dashpot/issues/448) at Claude
Code 2.1.289, Codex 0.160.0 and OpenCode 2.0.22, each with a sub-agent
holding a command open across the action
([spike](spikes/session-start-on-a-live-session-spike.md)). In every case the
sub-agent kept working.

| Action | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Compaction, by command or automatic | `PreCompact`, a `SubagentStop` for the summarizer with no `SubagentStart`, `SessionStart` `compact` on the same session and process, `PostCompact`; no `SessionEnd`, and no `Stop` for a manual `/compact` | `PreCompact`, `PostCompact`; `SessionStart` `compact` on the same session and process at the next turn, or mid-turn for automatic compaction; no `SessionEnd` | Runs as, or inside, an execution of the root; compaction events of its own, and no `session.created` |
| Clear or new conversation | `/clear`: `SessionEnd` `clear`, then `SessionStart` `clear` with a new id in the same process; the sub-agent reports under the new id | `/clear`: `SessionStart` `clear` on a new thread, `/new`: `SessionStart` `startup`; the old thread gets no `SessionEnd` then, and its sub-agent stops on it | Not measured |
| Switch conversation | `/resume <id>`: `SessionEnd` `resume`, then `SessionStart` `resume` naming the other session; `/branch`: `SessionEnd` `resume`, then `SessionStart` `fork`; the sub-agent follows to the new session | A second client resuming a loaded thread publishes no `SessionStart` | A client or TUI attaching to the root publishes no `session.created` |

## Codex CLI and App Server

### Entry points and hosting choices

| Entry point | What it selects |
| --- | --- |
| `codex`, `codex resume <id>`, `codex fork <id>` | Interactive start, resume, or history fork |
| `codex --remote <endpoint>` | TUI attached to an existing app-server |
| `codex app-server --listen <endpoint>` | Explicit protocol listener for a client integration |
| `codex remote-control` | Foreground managed Remote Control |
| `codex remote-control start` / `stop` / `pair` | Managed daemon lifecycle and short-lived device pairing |

These are distinct CLI routes. Bare `codex` selects the interactive UI; that
alone does not prove one process per conversation. Managed Remote Control and
custom protocol listeners serve different integrations.
[Developer commands][commands] The
[Codex experiment](spikes/codex-identity-lifecycle-spike.md) exercised
`codex app-server --listen` with raw protocol clients, `codex exec`, and
`codex exec resume` on `0.155.1`; the
[handoff feasibility experiment](spikes/cleanup-session-handoff-feasibility-spike.md)
measured `codex --remote` and plain `codex` terminals on the managed daemon
at the same release; Remote Control pairing is documented and source-read,
not measured.

Installed `0.154.0` help additionally exposes `codex agents` for browsing the
shared local daemon, and `codex app-server daemon` with `start`, `restart`,
`stop`, `version`, `bootstrap`, and Remote Control enable/disable subcommands.
See [the managed daemon](#the-managed-daemon-and-attached-terminals-at-01551)
for what `0.155.1` measured of it.

### Documented server model

App Server multiplexes threads with separate turns and tool items. Its
bidirectional JSON-RPC wire format omits the `jsonrpc` field; initialize each
connection. `thread.id` identifies a conversation, whereas `thread.sessionId`
identifies its live session-tree root; the documentation says forks share it,
but the pinned `0.154.0` code and fork test give a forked root thread its own,
and the `0.155.1` measurement agrees with the code: a fork's `sessionId` is
its own `id`, and only a sub-agent thread reports its parent's
(see [Transport, execution host, and identity boundaries](#transport-execution-host-and-identity-boundaries)).
[App Server protocol][server]

| Operation or field | Meaning |
| --- | --- |
| `thread/start`, `thread/resume`, `thread/fork` | Create, reload stored identity, or copy history into a new identity |
| `thread/read`, `thread/loaded/list` | Read without loading/subscribing; enumerate loaded threads |
| Thread status | `notLoaded`, `idle`, `systemError`, or `active` |
| `turn/interrupt` | Stop a turn |
| `thread/delete` | Delete history |
| `thread/closed` | Unload runtime |
| Thread/turn cwd | Conversation execution context, distinct from one command's cwd |

Subscriptions are connection-scoped. After the last subscriber leaves, the
documentation says a thread can remain loaded until thirty minutes without
subscribers or activity; the pinned `0.154.0` code default is sixty seconds,
and the `0.155.1` measurement unloaded an unsubscribed root thread after
60,067 ms
(see [Loaded threads, overrides, and unload](#loaded-threads-overrides-and-unload)).
Ephemeral threads have different persistence. Apart from the measured unload
delay, these are current protocol contracts, not local measurements.
[App Server lifecycle][server]

### When this arrangement is useful

**Several independent efforts in one interface.** The desktop app presents
parallel work across projects and lets a person switch among chats. A server
hosting several conversations is a natural implementation of that workflow:
each conversation can retain its own progress while the interface changes focus.
The workflow is documented; this explanation of its architectural fit is an
inference, not a claim about every desktop release's process topology.
[Desktop app documentation][app]

**Foreground work plus background changes.** OpenAI recommends Worktrees for
independent parallel chats and for scheduled tasks that should not disturb the
foreground checkout. Handoff moves a chat between Local and its Worktree for
inspection, testing, or continued background work. A managed Worktree is
typically dedicated to one chat; a permanent Worktree can host multiple chats.
[Worktree documentation][worktrees]

**An interface on another device.** Remote lets a phone start or continue work,
send instructions, approve actions, and inspect changes. Execution and files stay
on the connected computer or its development environment. This is a concrete
product example of separating the controller from execution; the documentation
does not establish that every Remote connection uses the public app-server
transport. [Remote documentation][remote]

**A custom terminal or embedded client.** A protocol client can present
several threads' progress and approval requests in one interface.
[App Server clients][server]

### Compared with separate sessions in feature Worktrees

The practical comparison below is an architectural inference from those APIs,
the CLI connection options, and the documented Worktree workflows.
[Developer commands][commands] [Worktree documentation][worktrees]

| Concern | Separate Codex sessions | Conversations on a shared app-server |
| --- | --- | --- |
| Parallel feature work | Independent conversations can work in parallel. | Independent conversations can also work in parallel. |
| File isolation | Separate Worktrees separate checked-out files. | The same Worktree separation applies. |
| Context | Each conversation has its own history. | Sharing a server does not merge conversation histories. |
| Supervision | Separate terminal clients typically require switching among tabs or windows. | A client can combine progress and approval handling for several conversations. |
| Programmatic control | A controller needs a connection or integration for each separately hosted runtime. | A controller can address individual conversations through one server connection. |
| Remote access | Depends on the terminal or remote-client arrangement. | Clients can explicitly connect to the server over a supported transport. |

For independent feature implementation, the principal benefit of shared hosting
is easier supervision and control. It does not inherently improve the coding
work itself. A client could, for example, show that one conversation is running
tests, another needs approval, and a third has finished, with controls for each.
This is an integration opportunity: the benefit depends on a client using the
protocol, rather than merely on the conversations sharing a PID.

### Conversation and server lifetimes

OpenAI documents `SessionEnd` for the main thread when an open conversation is
archived or deleted, Codex closes normally, or the conversation has been idle
without a connected client for thirty minutes. Switching away or unsubscribing
does not immediately end it. Hook common fields include `session_id`; subagent
hooks use the parent's session ID. The `0.155.1` measurement confirms the
parent's `session_id` on every sub-agent hook, `SessionEnd` at the unload of
an unsubscribed root thread and at graceful server exit, and no `SessionEnd`
after SIGKILL of the server; the archive, delete, and thirty-minute
interactive cases remain documented, not measured. [Hook documentation][hooks]

Consequently, a live server process alone cannot establish whether a particular
conversation is loaded, active, or waiting. A conversation can end while the
server continues hosting others. These are lifecycle inferences from the
documented separation between the server and its conversations.

[server]: https://learn.chatgpt.com/docs/app-server
[app]: https://learn.chatgpt.com/docs/app
[worktrees]: https://learn.chatgpt.com/docs/environments/git-worktrees
[remote]: https://learn.chatgpt.com/docs/remote
[commands]: https://learn.chatgpt.com/docs/developer-commands?surface=cli
[hooks]: https://developers.openai.com/codex/hooks

### Transport, execution host, and identity boundaries

For a custom connection, a documented loopback pair is:

```bash
codex app-server --listen ws://127.0.0.1:4500
codex --remote ws://127.0.0.1:4500
```

The commands run in separate terminals. Stdio uses JSONL; Unix sockets use
WebSocket handshakes. WebSocket listeners use `ws://`; clients can use `wss://`
through TLS termination, with `--remote-auth-token-env` for bearer authentication.
App-server is an experimental integration surface. [Developer commands][commands]

App-server normally starts a local Code Mode host. `--code-mode-host` selects
an outbound remote host connection shared by its threads, independently of the
inbound `--listen` endpoint. Consequently, the client machine, orchestration
server, and tool execution host need not be the same machine. A client's local
checkout and environment should not be assumed to configure remote execution;
the exact remote configuration and hook execution mapping remains unmeasured.
With the default local host on Linux at `0.155.1`, every measured shell and
hook was a direct child of the single `codex app-server` process, and process
sweeps of the fixture `CODEX_HOME` taken while the threads were idle found no
other process; that the local Code Mode host is not a separate process in
that configuration is an inference from those idle snapshots, since a helper
alive only during a turn would not appear in them. `--code-mode-host` was not
exercised. [Code Mode host][server]

Shell `CODEX_THREAD_ID`, hook `session_id`, per-conversation `thread.id`,
shared `thread.sessionId`, and delegated `agent_id` must not be assumed
interchangeable across every mode. At `rust-v0.154.0` the pinned source
establishes the root-thread mapping: hook `session_id` is the session's
`SessionId`, which equals `thread.sessionId`; a new or forked root thread
takes `SessionId::from(thread_id)`, so for root threads hook `session_id`,
`thread.id`, `thread.sessionId`, and shell `CODEX_THREAD_ID` carry the same
UUID, and the fork test asserts `thread.session_id == thread.id`. A non-root
delegated agent reuses its parent's session ID. The documentation sentence
that forked threads keep the root's session ID does not match this code. The
mapping across remote execution hosts remains unverified.
[Identity source][identity-source] [Fork test][fork-test]

The `0.155.1` measurement confirms the root and fork mapping and supplies the
child mapping the source reading left open. For a root thread and for a fork,
`thread.id`, `thread.sessionId`, hook `session_id`, shell `CODEX_THREAD_ID`,
and the shell `CODEX_SESSION_ID` that `0.155.1` exports beside it are one
UUID, and a fork's UUID is new. A sub-agent spawned with `spawn_agent` is its
own loaded thread whose `thread/read` reports `parentThreadId` and
`sessionId` = the root; its shell exports `CODEX_THREAD_ID` = the child id and
`CODEX_SESSION_ID` = the root id; every hook it triggers carries `session_id`
= the root, `agent_id` = the child id, `agent_type` = `default`, and its own
`turn_id`; and it publishes no `SessionStart` or `SessionEnd`. A hook's
`session_id` is therefore parent-scoped and does not identify the executing
child; only `agent_id` and the child's own shell claim do. Hook processes
receive `CODEX_HOME` and no thread variable
([measured identity](spikes/codex-identity-lifecycle-spike.md#scenario-results)).

### Thread ownership and competing resume

Evidence in this subsection is static reading of `rust-v0.154.0`, which
includes [PR #43253][pr-43253], except where a paragraph names the `0.155.1`
measurement.

The local thread store takes one advisory OS lock per thread,
`<CODEX_HOME>/thread-writer-locks/<thread_id>.lock`, when a `Session` is
constructed for a new or resumed thread. A second process's `try_lock`
receives `WouldBlock` and the resume fails with `thread <id> already has an
active writer` (JSON-RPC `-32600`). The lock carries no PID, heartbeat, or
expiry; it is released when the guard drops at thread shutdown or when the
process exits, and a leftover file after an abrupt exit is reclaimed by the
next acquisition's stale sweep. Ownership persists while the owner is idle:
the regression tests complete a turn in the first app-server, still receive
the conflict from a second app-server on the same `CODEX_HOME` (even with a
different SQLite directory), and succeed only after the first shuts down.
Different `CODEX_HOME`s never conflict. [Writer lock][writer-lock]
[Ownership tests][ownership-tests]

Measured at `0.155.1`: while an app-server held an idle thread, `codex exec
resume <id>` exited 1 with `thread-store conflict: thread <id> already has an
active writer` and ran no command or hook, and a second app-server's
`thread/resume` returned `-32600` with the same message while its
`thread/read` succeeded with status `notLoaded`. The lock directory then held
`.coordination.lock` and one `<thread_id>.lock` per loaded thread, the
sub-agent's included. After SIGKILL of the server the lock files stayed on
disk, and a replacement server's `thread/resume` of the same thread succeeded
without any cleanup; after SIGTERM only `.coordination.lock` remained
([measured ownership](spikes/codex-identity-lifecycle-spike.md#scenario-results)).
The TUI's read-only fallback below is source reading only.

The interactive TUI at this tag is backed by an embedded app-server, so bare
`codex resume <id>` takes the same lock. On conflict the TUI falls back to a
`thread/read` snapshot: it shows the transcript read-only with a notice that
the conversation is open in another app, disables the composer, preserves a
draft or positional prompt, and offers `R` to retry, `Esc`/`q`/`Ctrl-C` to
exit. Retry sends a fresh `thread/resume`; there is no polling. `-C`/`--cd`
does not interact with the lock; on a successful resume the override wins
over the stored rollout cwd, so the resumed session's `turn_context.cwd` is
the new directory. [Read-only startup][read-only-startup]
[External-writer view][external-writer] [Retry keys][retry-keys]
[Resume cwd override][resume-cwd]

Hook consequences follow from where hooks live. Every Codex hook is dispatched
from a core `Session` (the `codex_hooks` feature must be enabled): the lock is
acquired inside `Session::new`, `SessionStart` is queued there and run at the
start of the next turn, `UserPromptSubmit` runs in the turn input path,
`Stop` at turn end, and `SessionEnd` from the shutdown handler. A read-only
competing client therefore has no `Session`, runs no `SessionStart`,
`UserPromptSubmit`, or `SessionEnd`, and publishes no `cwd` evidence; after a
successful retry the new `Session`'s `SessionStart` (`source: resume`) fires
on the first turn submitted, not at retry time. On the owning client's
graceful exit, `SessionEnd` is awaited inside the shutdown handler before the
live thread releases the lock, so the hook completes before a competitor can
acquire ownership; shutdown timeouts (ten seconds per thread) can let the
process exit with the hook unfinished, after which process exit releases the
lock. An abrupt kill releases the lock with no `SessionEnd`; the `0.155.1`
measurement saw no hook of any kind after SIGKILL, the lock files left in
place, and the next resume succeed, and saw `SessionEnd` with `reason` =
`other` for the loaded thread on SIGTERM.
[Session construction][session-new] [Hook dispatch][hook-runtime]
[Shutdown ordering][shutdown-order]

### Working-directory change and worktree commands

`/cd <path>` is a human-only TUI command; no tool or app-server method changes
a live thread's cwd. Its target must be an existing, trusted directory; there
is no Git or same-repository check, so an arbitrary pre-existing linked
worktree is a valid target. When the current thread has a saved rollout, `/cd`
forks it with `thread/fork` at the new cwd: core allocates a fresh thread ID,
copies the history into the child's rollout, and records
`forked_from_thread_id` in the store. The TUI then only unsubscribes from the
old thread. The child's hooks carry the new `session_id` and cwd, and its
`SessionStart` reports `source: startup` at this tag (the payload schema has
no parent or fork field); at `0.155.1` a `thread/fork` child's first turn
reports `source: fork`, still with no parent field, and takes its own
`sessionId`. At 0.160.0, `/cd` with a background terminal running left the
session where it was, and once the terminal had ended, `/cd` started a
`source: fork` session in the new directory
([measured under #466](spikes/background-commands-and-cleanup-spike.md#codex-01600)). The old thread's `SessionEnd`, with the old ID and
cwd, runs when the subscriber-less thread unloads after the unload delay or
when the client exits. Shell subprocesses of the child export the new
`CODEX_THREAD_ID`. Preconditions: an idle primary thread with no queued input,
pending steers, active background terminals, running side agent, loading MCP
inventory, named profile, or untrusted destination, otherwise the user sees
`Changing directories requires an idle primary session without queued input.`
or the specific blocker. [Directory change][cd-impl] [Idle conditions][cd-idle]
[Fork identity][fork-identity] [Session start source][start-source]

`/worktree` (feature `worktrees`, experimental and off by default at this tag)
creates a managed checkout with `git worktree add --detach` under
`~/.codex/worktrees/<hex>/<repo>` (or `desktop.git-worktree-root`), on a
detached HEAD with no branch, then forks or starts a thread there through the
same directory-change path and records the owner thread beside the checkout.
Its browser lists only managed checkouts and offers resuming their owner
threads; it cannot carry the current conversation into an existing worktree.
[Worktree creation][worktree-create] [Worktree picker][worktree-picker]

### Loaded threads, overrides, and unload

`thread/resume` on a thread already loaded in the app-server subscribes the
caller to the existing runtime. Overrides in that request, including `cwd`,
are honoured only when the thread has no subscribers, is idle, and is not
running; then the cached runtime is shut down and a cold resume applies them.
Otherwise the server logs that the overrides were ignored. `turn/start` may
override `cwd` for that turn and subsequent turns; the override becomes the
thread's sticky environment, is persisted per turn, and later hooks report it
as their `cwd`, while the original `SessionMeta.cwd` is not rewritten. There
is no `thread/unload` or `thread/close` request; `thread/unsubscribe` and a
dropped connection only remove the subscription. A thread with no subscribers
and no activity is unloaded after `thread_unload_delay_secs`, whose code
default is sixty seconds at this tag although the documentation says thirty
minutes; unload, archive, delete, resume-with-overrides of an idle
unsubscribed thread, and server exit each run `SessionEnd` before
`thread/closed`. Per-thread state is held in maps keyed by thread ID, and every
request resolves its own thread, which is the isolation evidence for sibling
conversations on one server. `codex --remote` attaches as a subscriber and
closes its connection on exit, so the thread ends only after the unload delay
unless another subscriber remains. [Loaded-thread resume][loaded-resume]
[Turn cwd override][turn-cwd] [Unload lifecycle][unload]

Measured at `0.155.1` with raw protocol clients: a second client's
`thread/resume` of loaded threads returned the same ids and ran no hook; when
the first client's socket closed mid-command, the command finished and the
second client received `turn/completed` with no `Interrupt` or `SessionEnd`;
`turn/interrupt` killed the running command, ended the turn as `interrupted`,
and ran `Interrupt` with `session_id` and `turn_id` but no `PostToolUse` or
`Stop`. After the last subscriber's `thread/unsubscribe`, the root fork ran
`SessionEnd` `other` after 60,067 ms and its `thread/closed` still reached the
unsubscribed client; an idle sub-agent thread unloaded with `thread/closed`
and no hook. A replacement server resumed a `notLoaded` thread with a `cwd`
override; the resume ran no hook, and the first turn's `SessionStart`
(`source` = `resume`) and every later hook and shell reported the new cwd
under the same thread id. `codex exec resume` from another directory behaved
the same way for a stored `exec` thread
([measured lifecycle](spikes/codex-identity-lifecycle-spike.md#scenario-results)).
The [handoff experiment](spikes/cleanup-session-handoff-feasibility-spike.md#scenario-results-codex)
then exercised the two remaining paths on the managed daemon: `thread/resume`
of a loaded, terminal-subscribed thread ignored its `cwd` override and ran no
hook, while `turn/start` with a `cwd` override ran that turn's hooks and shell
at the new directory, `thread/read` reported it afterwards, and the terminal's
own next turn ran there too, all under the same thread id. A `turn/start`
issued while a turn was running was answered with the running turn's own id
and `inProgress`: its input joined that turn, ran after the active command in
that turn's directory, and only then did `thread/read` report the requested
one.

### Measured lifecycle at 0.155.1

The [Codex experiment](spikes/codex-identity-lifecycle-spike.md) measured
`codex app-server --listen` and `codex exec` on Linux with an isolated
`CODEX_HOME`, a loopback Responses API as a custom provider, and nine command
hooks trusted through `[hooks.state]`. Trace receipts are in the experiment's
scenario table.

| Lifecycle event | Measured effect on the thread | Hooks delivered |
| --- | --- | --- |
| `thread/start` then first `turn/start` | Thread listed as loaded under the one server pid; shells and hooks descend from it | `SessionStart` `startup` at the first turn, not at `thread/start` |
| `thread/fork` | New `id` = new `sessionId`, `forkedFromId` = origin | `SessionStart` `fork` at its first turn; no parent field |
| `spawn_agent` from a root thread | Child listed as loaded; `parentThreadId` and `sessionId` = root; child shell claims child id in `CODEX_THREAD_ID`, root in `CODEX_SESSION_ID` | `SubagentStart`, child tool hooks, `SubagentStop` with root `session_id` and child `agent_id`; no `SessionStart` or `SessionEnd` for the child |
| Second client `thread/resume` of a loaded thread | Same ids; runtime shared | None |
| First client's socket closes mid-command | Command completes; turn completes for the other client | Ordinary tool hooks and `Stop`; no `Interrupt` or `SessionEnd` |
| `turn/interrupt` | Turn `interrupted`; the command process killed | `Interrupt` with `turn_id`; no `PostToolUse` or `Stop` |
| Last `thread/unsubscribe` | Root thread unloaded after 60,067 ms; `thread/closed` still delivered to the unsubscribed client; lock released | `SessionEnd` `other` for the root; none for an idle sub-agent thread's unload |
| `codex exec` | Own `codex` process and thread; shells and hooks under that pid | `SessionStart` `startup` … `Stop`, then `SessionEnd` `other` at its own exit; after a signal, only SIGINT publishes one ([measured at 0.160.0](#codex-exec-signals-at-01600)) |
| `codex exec resume <id>` from another directory | Same id; hook and shell cwd = the process cwd | `SessionStart` `resume` |
| Competing `exec resume` or second-server `thread/resume` of a loaded thread | Refused: exit 1 / `-32600` `already has an active writer`; `thread/read` still works | None |
| Server SIGKILL with loaded threads | Client close 1006; lock files remain; no leftover process | None |
| Replacement server `thread/resume` with `cwd` override | Stored thread reported `notLoaded` at its old cwd; resume succeeds despite the stale lock file | None at resume; `SessionStart` `resume` with the new cwd at the first turn |
| Server SIGTERM with a loaded thread | Exit 0; thread lock removed | `SessionEnd` `other` with the current cwd |

### The managed daemon and attached terminals at 0.155.1

The [handoff feasibility experiment](spikes/cleanup-session-handoff-feasibility-spike.md#scenario-results-codex)
started `codex app-server daemon start` in an isolated `CODEX_HOME`. The
command runs only the installer-managed standalone release at
`<CODEX_HOME>/packages/standalone/current`, refusing any other binary, and
reports `managedCodexVersion` and `appServerVersion`. It leaves one
`codex app-server --listen unix:// --managed-daemon` process, reparented to
pid 1, whose control socket is
`<CODEX_HOME>/app-server-control/app-server-control.sock`. That socket speaks
WebSocket over a Unix domain socket: a plain JSON line receives no answer, an
HTTP upgrade answers `101 Switching Protocols`, and `codex app-server proxy
--sock` only relays bytes, so a stdio client of the proxy must still speak
WebSocket. The daemon accepts the same JSON-RPC methods as an explicit
listener; `hooks/list` trust through `[hooks.state]` behaves as measured on
`--listen`.

Every terminal measured under that `CODEX_HOME` while the daemon ran hosted
its thread in the daemon — two attached explicitly with
`codex --remote unix://<socket>` and one launched as plain `codex` with no
remote setting in `config.toml`: the thread
appears in `thread/loaded/list`, its shells' ancestry is the daemon pid rather
than the terminal, and a second client's `thread/resume` subscribes to it.
The daemon also lists the terminals' helper threads, each `ephemeral: true`
with `historyMode` `legacy`; a listing that counts conversations filters
them. A terminal's `/exit` runs no hook and neither unloads the thread nor
releases its writer lock while another subscriber remains; the last
`thread/unsubscribe` starts the unload delay, after which `SessionEnd` `other`
fires at the thread's current cwd (60,049 ms measured). `daemon stop` ends the
remaining loaded threads with `SessionEnd` `other`, as `daemon restart` does
([measured at 0.160.0](#managed-daemon-restart-and-stop-at-01600)). A terminal launched before
the daemon starts was measured at 0.159.3
([below](#hosting-modes-and-daemon-autostart-at-01593)); `codex agents` was
not measured.

The [declared-relocation experiment](spikes/codex-declared-relocation-daemon-spike.md#scenario-results)
then measured the sequential `codex resume <id> -C <path>` route on the
daemon. When the old plain terminal has typed `/exit` and the thread is still
loaded, idle, and locked with no subscriber, a `codex resume` of it launched
98 ms later is daemon-hosted and does not reattach in the old directory: the
daemon shuts the cached runtime down, running `SessionEnd` `other` at the
**old** cwd, and cold-resumes the thread with the override, running
`SessionStart` `resume` at the new cwd 102 ms later, then the turn there,
all under the same thread id; `thread/read` reports the new cwd, the
terminal's own next turn runs there, no later `SessionEnd` arrives while the
resumed terminal lives, and its `/exit` starts the ordinary unload delay
(60,041 ms measured). This is the cold-resume branch of the loaded-thread
override rule above, reached because the exited terminal was the only
subscriber; the feasibility experiment's ignored override was of a thread
its terminal still subscribed to. A resume after the unload behaves as the
stored-thread resume: `SessionStart` `resume` at the new cwd first. Without a
daemon, the terminal's `/exit` runs `SessionEnd` at once and the resume is a
new process with the same first-hook order. No read-only notice or picker
appeared on any route. A resume launched while the old terminal is still
attached was not measured.

[#460's experiment](spikes/second-host-process-resume-spike.md) resumed a
daemon-hosted lead from a second terminal at 0.160.0 (2026-10-05) while the
lead's worker ran commands in the daemon. A plain `codex resume` attached to
the daemon: its turn's hooks came from the daemon's process, it published no
`SessionStart`, and its exit printed "Disconnected from this task. Any
running work continues." A `codex --no-daemon resume` of the thread
published nothing while it was open, through the worker's `SubagentStop` and
30 s beyond, and nothing on exit. Once the daemon had stopped, the same
command published `SessionStart` `resume` and its turn from its own process.
Neither route puts a daemon-hosted thread's events on a second Host Process
while the daemon holds it.

### Hosting modes and daemon autostart at 0.159.3

The [Codex acceptance run](agent-sessions.md#codex-hosting-modes) for
[#161](https://github.com/ned2/dashpot/issues/161) measured `codex-cli`
0.159.3 on Linux, and [#375](https://github.com/ned2/dashpot/issues/375)
reran it on 0.160.0 (2026-10-02). The run used the standalone release's
binary with an isolated `CODEX_HOME` that had no `packages/standalone` link,
a loopback Responses API as a custom provider, and Dashpot's real Codex
publisher as a trusted command hook for seven events. Since #375 the fixture
also turns the daemon's updater off (`updater.autoUpdateEnabled` false in
`<CODEX_HOME>/app-server-daemon/settings.json`), so the fixture daemon
neither contacts the network nor installs a release that could replace or
restart it mid-run. Every claim below held unchanged on 0.160.0, except the
updater-on observation, which only the 0.159.3 run measured. The
metadata-only [trace](spikes/measurements/issue-161-codex-trace.jsonl), now
from 0.160.0, records every other claim, and the runner's verifier checks
each one, timings within a tolerance. Where a claim names the 0.159.3 run,
that run's trace is retained at commit `d0a0a52`.

- **Autostart.** The `daemon_auto_start` feature is on by default: the
  fixture's configuration never sets it. A plain `codex` terminal with no
  daemon running installs the managed daemon from its own binary into
  `<CODEX_HOME>/packages/app-server-daemon/releases/<version>-<target>/`,
  linked as `current`. It then starts
  `codex app-server --remote-control --listen unix:// --managed-daemon` as
  its own child. The terminal's thread is daemon-hosted from the first turn:
  its hooks and shells descend from the daemon, not the terminal. When that
  terminal exits, the daemon is reparented (to pid 1 in the retained trace)
  and keeps its pid. With the updater left on, as in the 0.159.3 run (trace
  at `d0a0a52`), a companion `codex app-server daemon pid-update-loop`
  process, the daemon's updater, runs beside it and outlives `daemon stop`
  and `remote-control stop`; with it off, no such process starts.
  `app-server daemon start` and `stop` now name
  `packages/app-server-daemon/current`, where 0.155.1 required the
  standalone release.
- **Inherited environment.** The autostarted daemon keeps the environment of
  the terminal that started it, and its hooks inherit it in turn. The runner
  starts each terminal with `COLUMNS=120`. In an unretained
  [#356](https://github.com/ned2/dashpot/issues/356) rerun before the fix,
  the daemon's hooks saw `ps` cut its command line, about 200 characters in
  the fixture, at 120 columns, before `--managed-daemon`. Dashpot's probe
  now asks `ps` for unlimited width with `-ww`, and the retained trace's
  deferred unload ends depend on it.
- **Remote Control.** `codex remote-control start --json` installs and
  starts the same daemon even with no account, then exits 1 because the
  remote connection is errored. `remote-control stop` stops the daemon.
- **Standalone terminal.** A terminal launched with
  `--disable daemon_auto_start` while no daemon runs hosts its own thread:
  its hooks and shells descend from the terminal process. It keeps hosting
  that thread after a daemon starts beside it. Its `/exit` runs `SessionEnd`
  `other` at once, and a SIGKILL of it runs no hook. `codex resume <id>` in a
  new terminal publishes `SessionStart` `resume` under the same thread id
  from the new process.
- **Flag beside a daemon.** A terminal launched with
  `--disable daemon_auto_start` while a daemon runs attaches to that daemon.
  Its thread is daemon-hosted, its `/exit` runs no hook, and the thread
  unloads after the usual delay. The flag disables only starting a daemon,
  not using one.
- **Joined input.** Input typed into a terminal while its turn runs a
  command joins that turn. Its `UserPromptSubmit` carries the running turn's
  `turn_id` and fires only after the running command finishes, at the turn's
  cwd; one `Stop` ends the turn. A controller's `turn/start` on a busy
  thread likewise returns the running turn's id, even with a `cwd`
  override. The joined input's `UserPromptSubmit` and shell stay at the old
  cwd, while `thread/read` already reports the new one. The next turn's
  `UserPromptSubmit` is the first hook at the new cwd.
- **Unload and timeouts.** The unload delay after the last subscriber left
  was about 60 s (59.6 to 60.2 s in the retained trace), and `SessionEnd`
  `other` names the thread's current cwd. `codex exec` warns that it clamps the `SessionEnd` and
  `Interrupt` hook timeouts to 3 s; the daemon clamps `SessionEnd` the same
  way without a warning
  ([measured at 0.160.0](#managed-daemon-restart-and-stop-at-01600)).
- **Identity.** The 0.155.1 identity equalities held: hook `session_id` =
  `thread.id` = `CODEX_THREAD_ID` = `CODEX_SESSION_ID` for roots and forks. A
  sub-agent's shell claims its own thread id in `CODEX_THREAD_ID` and its
  root's in `CODEX_SESSION_ID`, and its hooks carry the root's `session_id`
  plus `agent_id`. No `codex-code-mode-host` process appeared in any hook or
  shell ancestry.
- **Sub-agents outliving their parent's turn.** Measured for
  [#355](https://github.com/ned2/dashpot/issues/355): a turn that spawned two
  sub-agents with `spawn_agent` and did not wait for them published the
  root's `UserPromptSubmit`, then the children's `SubagentStart` and the
  root's `Stop` within about 0.1 s, the `Stop` before or after a child's
  start in different runs, then each child's `UserPromptSubmit`, and each
  child's `SubagentStop` as it finished, about 7 s and 13 s after the root's
  `Stop` with holds of 6 s and 12 s. Every child event carried the root's
  `session_id`, the child's `agent_id` and the child's own `turn_id`; no
  child had a `SessionStart` or `SessionEnd`. Through Dashpot the bound run
  stayed running with no turn clock after the root's `Stop` and after the
  first child stopped, returned to waiting when the second did, and kept its
  id and Worktree; the other root threads on the daemon were unchanged.
- **Interrupting a sub-agent.** A controller's `turn/interrupt` naming a
  child's thread and turn, sent after its root's `Stop`, returned success and
  aborted the child's turn: the child's running command ran out its hold and
  the child made no further model request. Codex published no hook for it,
  neither `Interrupt` nor `SubagentStop`, then or later, in the 0.159.3 run
  (trace at `d0a0a52`) or the 0.160.0 one. The 0.160.0 run for
  [#374](https://github.com/ned2/dashpot/issues/374) spawned two children
  held 15 s and 30 s and interrupted the first. The root's next turn then
  published only its `UserPromptSubmit` and `Stop`, about 11 s before the
  working sibling's `SubagentStop`, so in the hooks the interrupted child
  and the working one looked alike: `SubagentStart`, then
  `UserPromptSubmit`, then nothing. Only a controller saw the difference:
  `thread/read` reported the interrupted child `idle` and the sibling
  `active`, and the controller that sent the interrupt received the
  child's `turn/completed` with status `interrupted`. Dashpot, which observes
  through hooks alone, therefore kept the child live: the bound run stayed
  running and the `sub-agent` Cleanup blocker stayed on an empty Worktree,
  naming the interrupted child after the sibling stopped, until the daemon
  was killed. This is the undelivered-`SubagentStop` risk
  [ADR 0016](adr/0016-hold-a-session-running-while-its-sub-agents-work.md)
  names, and the blocker and `dashpot work show` now say a listed sub-agent
  may have been interrupted and name the way to end the session. Upstream
  tracks the missing `SubagentStop` as
  [openai/codex#38142](https://github.com/openai/codex/issues/38142),
  reported on 0.147.0 for a third path not measured here: the parent model
  calling the `interrupt_agent` tool on a child. A commenter there traced
  the mechanism on Codex `main`: `SubagentStop`, like `Stop`, is dispatched
  only when a turn completes naturally, and a turn ended by interruption
  leaves through `TurnAborted` without reaching it, so any interrupt that
  aborts a child's own turn strands that child.
- **Interrupting the parent.** Interrupting the root's own turn does not
  end its children. A controller's `turn/interrupt` of a root turn waiting
  on a child (`wait_agent`), and Esc in a daemon-attached terminal at the
  same point, each published the root's `Interrupt` and no `Stop`; the
  child's command ran out its 20 s hold and the child published
  `SubagentStop` about 19 s after the interrupt. Esc in the terminal after
  the root's turn had stopped, while a child it spawned still worked,
  published nothing, and that child stopped at its hold with its own
  `SubagentStop`. Selecting a child in the terminal's agent picker and
  interrupting it there was not measured, nor was Esc in a standalone
  terminal.

Interactive conversation switches inside one terminal (`/new`, `/resume`),
Remote Control pairing with an account, and other operating systems were not
measured.

### Managed daemon restart and stop at 0.160.0

The [restart acceptance run](../scripts/experiments/codex-356/run.mjs) for
[#356](https://github.com/ned2/dashpot/issues/356) measured `codex-cli`
0.160.0 on Linux (2026-10-02, rerun on 2026-10-04 for
[#400](https://github.com/ned2/dashpot/issues/400)) with the fixture of the [#161
run](#hosting-modes-and-daemon-autostart-at-01593): an isolated `CODEX_HOME`
with the daemon's updater off, a loopback Responses API, and Dashpot's real
Codex publisher as a trusted command hook. The hook wrapper could also hold a
`SessionEnd` hook, posting a beat every 0.5 s, and start a waiter in a session
of its own, with none of the hook's streams, that watched the hook's Codex
host for 15 s. `codex app-server daemon start` ran the daemon as `codex
app-server --listen unix:// --managed-daemon`. The metadata-only
[trace](spikes/measurements/issue-356-codex-trace.jsonl) records each claim
below and the [verifier](../scripts/experiments/codex-356/verify.mjs) checks
it, timings within a tolerance. How Dashpot acts on it is [ADR
0086](adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md).

- **One `SessionEnd` for three causes.** An idle unload, `daemon restart` and
  `daemon stop` each run `SessionEnd` for every thread they end, with the same
  payload keys and `reason` `other`. Nothing in the payload tells them apart.
- **The 3 s clamp.** The daemon kills a `SessionEnd` hook about 3 s after it
  begins, although the hook configuration names 30 s, on an unload as on a
  stop: a hook holding for 6 s posted its last beat at 2.73 to 2.74 s and
  never reached its end. `codex exec` warns of this clamp; the daemon applies
  it without a warning.
- **Parallel hooks.** The four threads loaded at the restart began their
  `SessionEnd` hooks within 3 ms of one another, 74 ms after `daemon restart`
  began.
- **The daemon waits for its hooks.** On the restart, whose hooks ran only the
  publisher, the old daemon exited 0.23 s after the first hook began and
  within 16 ms of the last hook's end; the replacement was already listening,
  and `daemon restart` returned after 0.57 s. On the stop, whose hooks held
  until the clamp killed them, the daemon exited 3.0 s after they began.
- **A running turn drains first.** `daemon stop` sent while one thread's turn
  waited on the model and another thread sat idle let the turn finish before
  ending either: the model was released 20.0 s after the stop began, the turn
  completed, and both threads' `SessionEnd` hooks began 0.30 s later; `daemon
  stop` returned after 23.4 s. A restart with a turn running was not measured.
- **A detached process outlives both.** The waiter outlived the killed hook
  and the daemon. It saw the old daemon exit 0.23 to 0.25 s after its hook
  began on the restart and 3.00 to 3.01 s after on the stop, and on an unload
  saw the daemon still running 15 s later.
- **Reload with no hook.** The replacement daemon held every thread the old
  one had loaded: its `thread/loaded/list` named all four, and neither the
  reload nor a controller's `thread/resume` of one ran a hook. That thread's
  next turn ran on the replacement, its first hook `SessionStart` with
  `source` `resume`, under the same thread id. That `SessionStart` comes
  from the runner's resume, not the reload: without a resume, a reloaded thread's
  next hook is `UserPromptSubmit` from the replacement
  ([#380](https://github.com/ned2/dashpot/issues/380)).
- **A reloaded thread unloads.** The three reloaded threads no client resumed
  ran `SessionEnd` from the replacement 60.2 to 60.3 s after the old daemon
  exited, the unload delay counted from the reload.
- **Unload timing.** An idle thread's `SessionEnd` began 60.0 s after its last
  client left, as at 0.159.3.
- **Not measured.** The fixture's updater was off, so a restart the updater
  starts after installing a release was not seen; nor were a restart with a
  turn running, a `SIGTERM` of the daemon, or `remote-control stop`.

Through Dashpot's publisher and settler, `exec` and a standalone terminal's
`/exit` ended their runs at once. The unloaded thread's run ended 10.3 s after
its `SessionEnd`, once the settler had seen the daemon outlive it. The restart
left the three bound runs orphaned under the old daemon, each settler deciding
within 0.3 s; the reloaded thread's next turn was listed unbound beside its
orphaned run until `work start` bound a new run on the replacement; the
reloaded threads' later unload ended nothing of the orphans and started no
settler; and the stop left the recovered run and its idle sibling's run
orphaned under the replacement. Every hook and settler process had exited by
the end of the run.

### `codex exec` signals at 0.160.0

The [#479 experiment](spikes/root-session-workers-spike.md#codex-01600)
measured `codex-cli` 0.160.0 on Linux (2026-10-05) with an isolated
`CODEX_HOME`, the daemon's updater off, a loopback Responses API, and
Dashpot's real Codex publisher as a trusted command hook. Three detached
`codex exec -C <worktree> --json` processes, each bound by `work start` to its
own Issue in its own Worktree and each holding a running command, were sent
SIGINT, SIGTERM and SIGKILL at the same moment. Receipt 482 of the
metadata-only [trace](spikes/measurements/issue-479-codex-trace.jsonl)
records the hooks and exit statuses, and receipt 479 what Dashpot reported
about 23 s after the signals; the
[verifier](../scripts/experiments/codex-479/verify.mjs) checks both.

| Signal | Exit status | Hooks after the signal | Through Dashpot |
| --- | --- | --- | --- |
| SIGINT | 1 | `Interrupt` 0.26 s after it, then `SessionEnd` 0.26 s later | The run ended, and its Worktree was removable |
| SIGTERM | 143 | None | The run stayed, orphaned under the gone `exec` pid; `worktree check` named it as an `agent-run` blocker, `Orphaned Agent Run on <issue> for codex pid N` |
| SIGKILL | 137 | None | As for SIGTERM |

Each process's running command ended with it. The rule is the `exec`
process's own: an `app-server --listen` sent SIGTERM publishes `SessionEnd`
for its loaded thread ([measured at 0.155.1](#measured-lifecycle-at-01551)),
and a SIGTERM to the managed daemon was not measured. Dashpot reads the
SIGTERM and SIGKILL runs as orphaned, not ended, since with no `SessionEnd`
it cannot tell an `exec` killed for good from one about to be continued by
`codex exec resume`
([ADR 0067](adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
[Stopping `codex exec`](agent-sessions.md#stopping-codex-exec) gives the
SIGINT rule and the two recoveries, resuming the thread and running `work
start`, or `dashpot work stop --session <key>`. The execute-issues skill's
Codex Workers are Sub-agents, not `exec` processes, and
[its harness notes](../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex)
say so.

### Changes on `main` after `rust-v0.154.0`

As of 2026-09-13 the newest stable release was `rust-v0.154.0` (published
2026-09-09) and the newest prerelease `rust-v0.155.0-alpha.3.10`
(2026-09-11), whose notes are stubs; `rust-v0.155.1` shipped as a stable
release on 2026-09-18 and is the release the
[Codex experiment](spikes/codex-identity-lifecycle-spike.md) measured. Merged PRs
relevant to the mechanisms above: [#44349][pr-44349] adds `fork` as a
`SessionStart` source and reports supplied-history resumes as `resume`,
confirmed released by the measured `fork` source at `0.155.1`;
[#44870][pr-44870] enables `worktrees` by default and blocks worktree creation
and `/cd` when the local daemon lacks `thread/backgroundTerminals/list`;
[#44711][pr-44711] and [#44969][pr-44969] extend the read-only snapshot and
explicit retry to the command center and to tasks owned by another app
server; [#44183][pr-44183] releases the writer when a resume is cancelled
during startup; [#43848][pr-43848] preserves runtime workspace roots across
resume and retargets the old cwd root when cwd changes. No PR changes the
`codex resume` flags. The measurement also found `CODEX_SESSION_ID` exported
to shells beside `CODEX_THREAD_ID`, which the `0.154.0` reading did not
record. The other PRs were not exercised; revalidate them against the
installed release.

[identity-source]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/session/session.rs#L776-L797
[fork-test]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/tests/suite/v2/thread_fork.rs#L204-L206
[pr-43253]: https://github.com/openai/codex/pull/43253
[writer-lock]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/thread-store/src/local/writer_lock.rs
[ownership-tests]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/tests/suite/v2/thread_resume.rs#L311-L407
[read-only-startup]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/app/startup.rs#L451-L473
[external-writer]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/chatwidget.rs#L1749-L1796
[retry-keys]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/app/input.rs#L236-L272
[resume-cwd]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L3793-L3806
[session-new]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/session/session.rs#L911-L931
[hook-runtime]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/hook_runtime.rs#L124-L181
[shutdown-order]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/session/handlers.rs#L402-L486
[cd-impl]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/app/working_directory.rs#L332-L418
[cd-idle]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/chatwidget/working_directory.rs#L7-L40
[fork-identity]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/thread_manager.rs#L1399-L1441
[start-source]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/session/session.rs#L1616-L1622
[worktree-create]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/worktree/src/lib.rs#L61-L165
[worktree-picker]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/tui/src/chatwidget/worktree_picker.rs#L93-L133
[loaded-resume]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L4170-L4290
[turn-cwd]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server-protocol/src/protocol/v2/turn.rs#L189-L191
[unload]: https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L22-L125
[pr-44349]: https://github.com/openai/codex/pull/44349
[pr-44870]: https://github.com/openai/codex/pull/44870
[pr-44711]: https://github.com/openai/codex/pull/44711
[pr-44969]: https://github.com/openai/codex/pull/44969
[pr-44183]: https://github.com/openai/codex/pull/44183
[pr-43848]: https://github.com/openai/codex/pull/43848

## Claude Code

### Entry points

| Entry point | What it selects |
| --- | --- |
| `claude`, `claude -p <prompt>` | Interactive conversation or one-shot programmatic request |
| `claude --resume <id>`, `claude --continue` | Saved conversation or most recent conversation in this directory |
| `claude --desktop [--continue \| --resume <id>]` | The Claude desktop app on this directory or conversation (macOS and Windows x64) |
| `claude --bg <prompt>`, `claude agents` | Background dispatch or agent view |
| `claude attach <id>`, `claude respawn <id>` | Attach to a background job or replace its worker |
| `claude agents --json`, `claude daemon status` | Supported job/worker listing or supervisor diagnostics |

These are documented commands
([CLI reference](https://code.claude.com/docs/en/cli-reference)). The
[Claude Code experiment](spikes/claude-code-identity-lifecycle-spike.md) exercised
the headless, `--resume`, `--fork-session`, `--bg`, `agents --json`,
`attach`, `stop`, `respawn`, and `daemon` forms on `2.1.276`; the
[handoff feasibility experiment](spikes/cleanup-session-handoff-feasibility-spike.md)
measured the interactive terminal on `2.1.278` with a development channel
loaded and the two worktree tools
([channels and worktree tools](#channels-and-worktree-tools-at-21278)); the
[2.1.285 changes experiment](spikes/claude-code-2-1-285-changes-spike.md) measured
`--resume` of a running background session and `--desktop` on Linux
([changes after 2.1.278](#changes-after-21278)).

### Remote Control has both attachment and server modes

`claude --remote-control` and `/remote-control` expose an interactive local
conversation to web/mobile clients. Remote disconnection need not stop it;
`/resume` can switch its conversation. `claude remote-control` is server mode,
with default capacity 32. Connections go outbound through Anthropic;
execution, project files and local tools stay on the serving machine.
[Remote Control](https://code.claude.com/docs/en/remote-control)

| Server spawn setting | Directory behavior |
| --- | --- |
| `--spawn same-dir` (default) | Sessions share the launch directory |
| `--spawn worktree` | On-demand sessions get separate Worktrees; the default initial session stays in the launch directory |
| `--spawn session` | Exactly one served session |

Stopped sessions can be restored within an approximately four-hour window
under the documented conditions. Single-session recovery flags require
v2.1.200; crashed served sessions can restart on a new message since v2.1.238.
Eligibility, workspace trust, and server flags differ from ordinary interactive
startup; global flags before `remote-control` are not generally forwarded.
[Server setup and recovery](https://code.claude.com/docs/en/remote-control#resume-sessions-after-stopping-the-server)

These docs do not establish the executing worker's ancestry or remote URL ID's
mapping to hook `session_id`. Server concurrency is insufficient evidence that
all conversations execute inside that server PID. Server mode is gated on a
claude.ai login: in the isolated experiment `claude remote-control` under an
API key exited 1 with "You must be logged in to use Remote Control", so the
server topology stays unmeasured rather than inferred, and the operator's
account was not used
([experiment](spikes/claude-code-identity-lifecycle-spike.md#scenario-results)).

### The background supervisor explicitly has separate workers

Each background session has its own Claude Code process. Attached terminals
can leave without stopping it. An unattached idle worker may stop after about
an hour and later resume its retained conversation. Supervisor replacement with
`claude daemon stop --any --keep-workers` preserves workers; omitting
`--keep-workers` stops them. `CLAUDE_CONFIG_DIR` selects separate supervisor state.
[Supervisor contract](https://code.claude.com/docs/en/agent-view#the-supervisor-process)

`claude agents --json` distinguishes conversation `sessionId`, short job `id`,
and live `pid`; job state is separate from process activity. Private files are
not the stable interface. Workers receive credentials from the supervisor;
reattaching from a new shell does not replace that supervisor environment.
[Session listing and settings](https://code.claude.com/docs/en/agent-view#list-sessions-as-json)

Background sessions normally move into a Worktree before editing, with documented
exceptions including already being inside one. Removing a job can remove its
managed Worktree while preserving its transcript. Two live processes cannot
write the same transcript. Current docs also describe carrying selected
background work across worker replacement; its exact shell/subagent boundaries
need release-specific checks.
[Background ownership and recovery](https://code.claude.com/docs/en/agent-view#how-background-sessions-are-hosted)

The documented worker topology is stronger evidence than the Remote Control
page provides; it does not establish identical internals between the two modes.

#### Measured supervisor and worker lifecycle at 2.1.276

The [Claude Code experiment](spikes/claude-code-identity-lifecycle-spike.md) measured
the supervised topology on Linux with an isolated `CLAUDE_CONFIG_DIR` and a
loopback model. The first `claude --bg` starts a transient supervisor
(`daemon run --origin transient`, reparented to pid 1). Each worker is its own
process below a `bg-pty-host` process below the supervisor, and the worker's
shell commands and hooks descend from the worker. `agents --json` reports the
worker's `pid`, `sessionId`, `cwd`, `name`, `status`, and `state`; the short
job `id` is the first eight characters of `sessionId`. The shell claim
`CLAUDE_CODE_SESSION_ID` equals `sessionId`, `CLAUDE_PID` equals the worker
`pid`, and the shell's cwd and every hook `cwd` equal the listing's `cwd`.
A worker's shells carry `CLAUDE_JOB_DIR` as well; `CLAUDE_CODE_SESSION_KIND=bg`
and `CLAUDE_BG_BACKEND` sit in the worker process's own environment and reach
neither its shells nor its hooks. A worker's argv is not a session carrier,
because a worker claimed from a pre-warmed spare (`claude bg-spare …`) names
no session while a directly spawned worker carries `--session-id`. A live
job's `startedAt` is the current worker's start and moves forward when the
worker is replaced, as does the worker's `/proc` start time with its pid; a
stopped job listed with `--all` reports an earlier `startedAt` than any of its
workers had, presumably the job's own creation.

Under the native installer every supervised process — supervisor, PTY host,
and worker — runs the versioned executable, so its `comm` is `2.1.276`, while
a headless process started through the launcher symlink has `comm` `claude`.
An executable-name test written for that launcher does not recognise a
supervised worker; the interactive terminal process was not measured.

The [supervised worker process experiment](spikes/claude-code-supervised-worker-process-spike.md)
probed each process with `ps` on Linux at 2.1.285 (2026-10-01); macOS is
unmeasured. `comm` is `2.1.285` for all of them, and `args` tells them apart:

| Process | `ps` `args` |
| --- | --- |
| Supervisor | `<home>/.local/share/claude/versions/2.1.285 daemon run --origin transient --spawned-by {…}` |
| PTY host | `claude bg-pty-host --bg-pty-host <daemon>/pty/<job>.sock 200 50 -- <its worker's command>`, or `…/spare/<id>.pty.sock … -- <versioned executable> --bg-spare` for a spare |
| Worker spawned for a new session | `<versioned executable> --session-id <sessionId> <prompt> --name <name> …` |
| Worker replacing one that died | `<versioned executable> --resume <config>/projects/<project>/<sessionId>.jsonl --name <name> …` |
| Pre-warmed spare, before and after it is claimed | `claude bg-spare --bg-spare <daemon>/spare/<id>.claim.sock` |

A dispatch finding a pre-warmed spare, and `claude respawn`, run the session in
that spare, so a respawned worker's vector names no session. A worker's
process, spares included, hosted one session for its whole life. The
PTY host's vector carries its worker's flags after `--`, so only the start of
the vector identifies a worker; Dashpot's Claude Code adapter locates a
version-named process as a host only when its vector starts with one of the
three worker shapes. A worker the supervisor replaces after an abrupt exit,
measured with the `--resume` shape, therefore continues its Agent Run under
[ADR 0053](adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md),
while `claude stop` ends it before any `claude respawn`. It continues at the
first hook the replacement publishes from the run's Worktree, which
[at 2.1.286 and 2.1.287](#clients-and-supervised-workers-through-dashpot-at-21286)
is not always its `SessionStart`.

| Lifecycle event | Measured effect on the worker | Hooks delivered |
| --- | --- | --- |
| Attached terminal killed | Worker keeps its pid and continues | None |
| Worker killed with SIGKILL under a live supervisor | Same `sessionId`, new `pid` and later `startedAt`, listed again about ten seconds later | `SessionStart` with `source` = `resume` from the new pid; no `SessionEnd` |
| `daemon stop --any --keep-workers` | Workers keep their pids; `agents --json` still lists them from the roster with the supervisor absent | None |
| Next `claude --bg` after that stop | A new supervisor pid adopts every surviving worker; a turn begun under the old supervisor ends under the new one from the original pid | None for the adoption; the turn's `Stop` arrives as usual |
| `claude stop <id>` | Listed as `state` = `stopped` with no pid | `SessionEnd` with `reason` = `other` from the worker pid |
| `claude respawn <id>` | Same `sessionId`, new `pid` | `SessionStart` with `source` = `resume` |
| `daemon stop --any` | Every worker terminated and listed as `stopped`; orphaned `bg-pty-host` processes can outlive the stop | `SessionEnd` with `reason` = `other` per worker |
| `EnterWorktree` in a worker | Listing `cwd`, later hook `cwd`, and shell cwd move to the managed Worktree; `sessionId`, `pid`, and `CLAUDE_PROJECT_DIR` stay | Ordinary tool hooks; no `CwdChanged` |

`SessionEnd` therefore distinguishes an explicit or supervisor-driven stop from
a crash, a respawn, or a supervisor replacement, none of which end the
conversation. Idle eviction of an unattached worker, documented at about an
hour, publishes no hook either: it was measured at `2.1.286` and `2.1.287`
([idle eviction](#clients-and-supervised-workers-through-dashpot-at-21286)).

### Channels and worktree tools at 2.1.278

Channels are the documented route for an external event source to reach a
running session
([channels](https://code.claude.com/docs/en/channels)). The
[handoff feasibility experiment](spikes/cleanup-session-handoff-feasibility-spike.md#scenario-results-claude-code)
measured a development channel on `2.1.278`: an ordinary stdio MCP server
whose `initialize` result declares the `claude/channel` experimental
capability, loaded with `--mcp-config`, `--strict-mcp-config`, and
`--dangerously-load-development-channels server:<name>`. That flag is parsed
only for an interactive session, shows a `WARNING: Loading development
channels` confirmation at every launch, and the feature is gated by the
remotely served `tengu_harbor` flag, which an isolated fixture must seed from
its cache; without it the session logs `Channel notifications skipped:
channels feature is not currently available`. The channel process is a child
of the session pid and receives `CLAUDE_CODE_SESSION_ID`,
`CLAUDE_PROJECT_DIR`, `CLAUDE_CODE_MESSAGING_SOCKET`, and
`CLAUDE_CONFIG_DIR` in its environment, so a channel can be bound to one
session by identity. A `notifications/claude/channel` notification with
`content` and `meta` reaches the model as the next user turn, wrapped in a
`<channel>` element and preceded by `UserPromptSubmit`; one pushed during a
turn is queued and delivered after it with no `Stop` between the two turns,
the only `Stop` following the second.
The plugin-distributed form (`--channels plugin:...`), which needs no
per-launch confirmation, was not measured.

The worktree tools reach a directory from one side only. From a session
launched directly in a linked worktree, `EnterWorktree` of the main working
tree is refused (`is the main working tree, not a linked worktree`),
`EnterWorktree` of a sibling linked worktree succeeds and isolates the
session there, and `ExitWorktree` is a no-op. From a session isolated by
`EnterWorktree`, `ExitWorktree(keep)` returns to the launch directory, and
`EnterWorktree` of a linked worktree outside `<repo>/.claude/worktrees/` is
refused (measured with that directory absent). Both results hold at 2.1.286
with the directory present too, and a session resumed in a worktree it had
entered counts as isolated
([measured at 2.1.286](#worktree-tools-between-issue-worktrees-at-21286)).
Neither tool runs a dedicated hook: the tool's `PostToolUse`
carries the new cwd, the next turn's hooks and shells carry it, and
`claude agents --json` lists the interactive session (`kind` =
`interactive`) at the new cwd under the same session id and pid with no
`SessionEnd` or `SessionStart`. A `run_in_background` shell job does not
block `EnterWorktree`, and the listing reports `busy` while the job runs.
`/exit` ends an interactive session with `SessionEnd` `reason` =
`prompt_input_exit`. At 2.1.289, with a shell job running, `/exit` first asks
whether to "Exit and stop tasks", which ends the job, or "Move to background
and exit". The second forks the session into a background session under a
transient daemon, which keeps the job running and takes its completion
notice ([measured under #466](spikes/background-commands-and-cleanup-spike.md#claude-code-21289)).

### Changes after 2.1.278

The [changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) from 2.1.280 to
2.1.285 (there is no 2.1.279 entry) changes no hook, shell variable, or
listing contract described above. The
[2.1.285 changes experiment](spikes/claude-code-2-1-285-changes-spike.md) measured
the entries that touch them on Linux on 2026-09-30, on 2.1.285 and on 2.1.280
for comparison, in an isolated configuration with API-key credentials and
telemetry and non-essential traffic off:

- **Resuming a running background session.** 2.1.285's changelog says
  `/resume` and `claude --resume <id>` now open a session running under
  `--bg`, and send a prompt given with `--resume <id> "prompt"` as its next
  turn. On an idle worker, an interactive `claude --resume <id>` with no
  session-configuring flag replaces its own process with a `claude attach
  <job>` client, whose executable is named after its version. The prompt,
  given on the command line or typed into the opened session, runs as a turn
  in the worker: its hooks carry the worker's `session_id` and `CLAUDE_PID`,
  with no new `SessionStart`, and its shells descend from the worker. `/exit`
  in the opened session does not detach; the client switches to the
  `claude agents` view, a pre-warmed spare publishes `SessionStart` `startup`
  for a session of its own, and by the time the client has closed,
  `SessionEnd` `other` has been published for the spare's session and, from
  the client, for a session id that never started, never for the worker's.
  The worker stays running and idle. With `--model` alone, or with
  `--dangerously-skip-permissions` and `--model`, the resume is
  refused instead and exits 1 without a hook: "That session is running in the
  background (`<id>`). Run `claude attach <id>` to open it, or `claude stop
  <id>` first to resume it here." By the executable's source, the session
  opens only for a client given no session-configuring option, a list that
  also names `--permission-mode`, `--settings`, `--setting-sources`,
  `--agent`, `--mcp-config`, and `--add-dir`, only while the agents view is
  enabled, only when the client is not itself a background session, and only
  while a `tengu_resume_open_live_bg` gate, on by default, allows it. 2.1.280
  refuses every form with other wording. `claude -p --resume <id>` is refused
  the same way and, on both versions, publishes `SessionEnd` with `reason` =
  `other` for the running session's `session_id` from the refused process's
  own `CLAUDE_PID` while the worker runs on. Before Dashpot located
  supervised workers, that `SessionEnd` ended the worker's Agent Run
  ([implications](spikes/claude-code-2-1-285-changes-spike.md#implications-for-dashpot));
  a run started from a located worker records its process and survives it.
  `claude --bg --resume <id>` starts a copy under a new `session_id` with
  `SessionStart` `source` = `fork`. After `claude stop <id>`,
  an interactive `--resume` continues the conversation in the terminal's own
  `claude` process with `source` = `resume`.
- **`claude --desktop`** is new in 2.1.285. On Linux it exits 1 without
  launching anything or starting a session: with redirected output because it
  "can't run non-interactively", and on a terminal, with or without
  `--resume`, because it "isn't available on this platform. It works on macOS
  and Windows (x64)". The desktop app's host process is unmeasured.
- **Sub-agents in auto mode.** In auto mode a sub-agent is offered a
  `SubagentHandback` tool that delivers its report; under
  `--dangerously-skip-permissions` it is not. A sub-agent that hands back
  produces one `SubagentStart` and one `SubagentStop`. 2.1.285 ends the
  sub-agent at the handback and gives the parent one notification turn, where
  2.1.280 took one more sub-agent model turn and gave the parent two
  notification turns, each a `UserPromptSubmit` and a `Stop`. On both
  versions a sub-agent that ends without handing back is re-prompted three
  times, and each attempt publishes another `SubagentStop` for the same
  `agent_id` with `stop_hook_active` = true: four `SubagentStop` for one
  `SubagentStart`. In `claude -p` the
  parent's first `Stop` fires while the sub-agent still works, and its report
  arrives as a new `UserPromptSubmit` turn before `SessionEnd`, foreground or
  `run_in_background` alike.
- **After an interactive turn** nothing fired in the ten seconds after `Stop`,
  whether or not the session read the cached prompt-suggestion flag, under
  bypass and in auto mode. A `SubagentStop` without a `SubagentStart` seen
  after `Stop` in a live 2.1.285 session was not reproduced. Without a served
  classifier an
  interactive auto-mode session stalls at its first tool call, presumably
  waiting for the server-side classifier, unless
  `CLAUDE_CODE_AUTO_MODE_SERVER=0` selects the local one; `claude -p` did not
  stall.
- **Workspace trust for `--bg`** (2.1.281). A non-interactive `claude --bg` in
  an untrusted directory exits 1 with "Workspace not trusted. Run `claude` in
  `<dir>` once and accept the trust prompt, then retry." and starts no session
  or hook, with or without `--dangerously-skip-permissions`; 2.1.280 started it
  and ran its hooks. Trust is recorded per directory; a subdirectory of a
  trusted main working tree and a sibling linked Worktree of it inherit its
  trust. The interactive trust prompt was not measured.
- **`--setting-sources`** (2.1.281). A `claude -p` session and a `claude --bg`
  worker started with `--setting-sources project,local` run no user-scope hook
  on either version. The fix forwards the restriction to sessions spawned from
  such a session — teammates, `/bg`, `claude agents`, and `--worktree --tmux`
  — which were not measured.

A supervised worker's executable is still named after its version (`2.1.285`)
while a process started through the launcher is named `claude`, as measured at
[2.1.276](#measured-supervisor-and-worker-lifecycle-at-21276), where the
argument vectors that distinguish a worker are listed. Auto mode became
the default permission mode of interactive sessions in 2.1.284 and, on
third-party providers or with telemetry off, of `claude -p` in 2.1.285,
according to the changelog; no measured sub-agent ran without a mode flag, so
that the handback and its re-prompts apply to sessions that set no mode is
inferred, not measured.

### Sub-agent hooks and location at 2.1.285

The [sub-agent location experiment](../scripts/experiments/claude-279/run.mjs)
for [Issue #279](https://github.com/ned2/dashpot/issues/279) ran on Linux on
2026-10-01 against 2.1.285. It used headless `claude -p` under
`--dangerously-skip-permissions`, an isolated configuration, and a loopback
Messages API. It subscribed a metadata-only publisher to every lifecycle and
tool event and to `CwdChanged`. The fixture is a Repository with a `nested`
directory and a sibling linked Worktree. The
[verifier](../scripts/experiments/claude-279/verify.mjs) checks the claims
below against the retained
[trace](spikes/measurements/issue-279-claude-trace.jsonl). To reproduce, pass
the runner the absolute path of a symlink named `claude` that points at the
2.1.285 executable, then pass the verifier the printed trace path:

```bash
mkdir -p /tmp/claude-279
ln -s ~/.local/share/claude/versions/2.1.285 /tmp/claude-279/claude
node scripts/experiments/claude-279/run.mjs /tmp/claude-279/claude
node scripts/experiments/claude-279/verify.mjs <printed trace path>
node scripts/experiments/claude-279/verify.mjs docs/spikes/measurements/issue-279-claude-trace.jsonl
```

- **Payload fields.** `SubagentStart` carries `session_id`,
  `transcript_path`, `cwd`, `prompt_id`, `agent_id`, `agent_type` and
  `hook_event_name`. `SubagentStop` adds `permission_mode`, `effort`,
  `stop_hook_active`, `agent_transcript_path`, `last_assistant_message`,
  `background_tasks` and `session_crons`. In both, `session_id` and
  `transcript_path` are the parent's. A sub-agent's `PreToolUse` and
  `PostToolUse` carry its `agent_id` and `agent_type` beside the parent's
  `session_id`. No sub-agent event names a worktree, a parent agent, or the
  sub-agent's shell directory.
- **`cwd` is the session's, not the sub-agent's.** The `cwd` on
  `SubagentStart`, on the sub-agent's tool hooks, and on `SubagentStop` is
  the parent's current directory, and the sub-agent's shell starts there.
  That is the launch directory; a directory the parent reached with a
  persisting `cd`; or the Worktree it entered with `EnterWorktree`. A
  `run_in_background` sub-agent is no different. The exception is an Agent
  tool call with `isolation: "worktree"`: its sub-agent runs, and its hooks
  report, `<repo>/.claude/worktrees/agent-<agent_id>`, which was removed
  when the unchanged sub-agent stopped.
- **A sub-agent's change of directory reaches no hook.** A sub-agent's
  `cd <Worktree> && <command>` runs the command in that Worktree, but its
  `PreToolUse` and `PostToolUse` still report the parent's `cwd`. A
  standalone `cd` in a sub-agent does not persist to its next Bash call and
  fires no `CwdChanged`. Only the command text records the move, and file
  tools take absolute paths anywhere, so no hook field says where a
  sub-agent works.
- **`CwdChanged` belongs to the main conversation.** A persisting `cd` inside
  the project fired it with `old_cwd` and `new_cwd`, and later hooks carried
  the new `cwd`. A `cd` outside the project was reset ("Shell cwd was reset
  to …"). It still fired `CwdChanged` with `new_cwd` naming the target,
  while its own `cwd` and every later hook stayed at the launch directory,
  and no `CwdChanged` reported the reset.

Dashpot acts on this in
[ADR 0066](adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md).

### Clients and supervised workers through Dashpot at 2.1.286

The [Claude Code acceptance runner](../scripts/experiments/claude-162/run.mjs)
for [Issue #162](https://github.com/ned2/dashpot/issues/162) ran on Linux on
2026-10-01 against 2.1.286, and
[#388](https://github.com/ned2/dashpot/issues/388) reran it on 2.1.287
(2026-10-02). Every claim below held unchanged on 2.1.287, and every hook's
payload key set matched 2.1.286's; the 2.1.286 traces are retained at commit
`77075e6`. It drove headless `claude -p` clients, one stream-json turn per
user message, and `claude --bg` supervised workers, whose later turns it typed
through `claude attach` on a pseudo-terminal. All of them ran under
`--dangerously-skip-permissions` with an isolated `CLAUDE_CONFIG_DIR`, the
autoupdater off (`DISABLE_AUTOUPDATER=1`, which the trace's environment
records), and a loopback Messages API. The hooks were subscribed exactly as
`dashpot integrate claude-code` subscribes them, through a wrapper that hands
each payload to Dashpot's real publisher, and the model's Bash calls ran the
real `dashpot work` commands. The fixture is a Local Issue Markdown Project
with a sibling linked Worktree and a nested one inside the main checkout. The
[verifier](../scripts/experiments/claude-162/verify.mjs) checks the claims
below against the retained
[trace](spikes/measurements/issue-162-claude-trace.jsonl), now from 2.1.287,
which records the SHA-256 of the runner and of the Dashpot session modules it
exercised. The runner refuses to start inside a Claude Code session, so launch
it from a plain shell or with `setsid -f`; it creates its own `claude`
launcher symlink from the executable it is given:

```bash
node scripts/experiments/claude-162/run.mjs ~/.local/share/claude/versions/2.1.287
SPIKE_IDLE_MINUTES=80 node scripts/experiments/claude-162/run.mjs ~/.local/share/claude/versions/2.1.287
node scripts/experiments/claude-162/verify.mjs <acceptance trace> [<idle trace>]
node scripts/experiments/claude-162/verify.mjs docs/spikes/measurements/issue-162-claude-trace.jsonl \
  docs/spikes/measurements/issue-162-claude-idle-trace.jsonl
```

- **Worktree tools.** A client's `EnterWorktree` with `path` and its
  `ExitWorktree` with `action: keep` each fired one `PostToolUse` whose `cwd`
  was the Worktree reached, from the same `CLAUDE_PID`. A bound client's run
  moved with it both ways, keeping its Issue Binding and `startedAt`, and
  `work show` run from the entered Worktree reported it there. An unbound
  client's moves bound nothing.
- **`ExitWorktree` with `remove`.** On a Worktree entered by `path` the tool
  failed with "This session is not the owner of the worktree" and fired no
  `PostToolUse`; the Worktree stayed. `EnterWorktree` with `name` created
  `<repo>/.claude/worktrees/<name>`, and `ExitWorktree(remove)` deleted it
  with the run its Work Store held; the `PostToolUse` arrived at the original
  checkout afterwards and `work show` reported no active Issue work.
- **Persistent shell `cd`.** After a client's Bash `cd` into the nested
  Worktree, its `Stop` reported that Worktree. The run stayed at the main
  checkout and observation reported `work-session-elsewhere`; `work start`
  from the nested Worktree reported `switched from issue-2 at <main> to
  issue-2 at <nested>`. Killed with SIGKILL, the client left that run
  orphaned. In another client in the same state, `EnterWorktree` with the
  nested Worktree's path failed with "Cannot enter worktree: <nested> is the
  current working directory" and fired no `PostToolUse`.
- **Sub-agent outliving its parent's turn.** A background sub-agent kept the
  session running after the parent's `Stop`, and its `SubagentStop` returned
  it to waiting.
- **`SessionEnd`.** Closing a client's input published `SessionEnd`, which
  ended its run and removed every record of the session in the Repository.
- **Two workers under one supervisor.** Each was its own process, held its own
  run, and only the worker that called `EnterWorktree` had its run carried.
- **Abrupt exit under a live supervisor.** A worker that had entered the
  sibling Worktree was killed with SIGKILL and replaced by
  `<versioned executable> --resume <transcript>` for the same session, whose
  process `cwd` and listing `cwd` were the sibling. The replacement's
  `SessionStart` (`source` = `resume`) hook ran in, and reported as `cwd`,
  the directory the worker was first dispatched from, so it continued
  nothing: the run stayed orphaned at the sibling. The next attached turn's
  `UserPromptSubmit` arrived at the sibling and continued it under
  [ADR 0053](adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md).
  The other worker's run was untouched throughout.
- **Replacement stopped before its first turn.** Killed again and replaced,
  then stopped with `claude stop`, the replacement's only hook at the sibling
  was its `SessionEnd`, from a process the run did not record. It ends the
  run under
  [ADR 0075](adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md).
- **Abrupt exit with no supervisor.** After `daemon stop --any
  --keep-workers`, a worker killed with SIGKILL was not replaced, published
  nothing, and was listed with `state` = `failed` and no pid; its run was
  orphaned. `claude respawn` started a supervisor and ran the session in a
  claimed spare (`claude bg-spare`), whose `SessionStart` (`resume`) arrived
  at the Worktree holding the run and continued it with its `startedAt`.
- **Supervisor replacement.** `daemon stop --any --keep-workers` followed by a
  new dispatch left every worker's pid, process and run unchanged, and fired
  no hook for them.
- **Stop and respawn.** `claude stop` published `SessionEnd` (`other`) and
  ended the worker's run; `claude respawn` published `SessionStart`
  (`resume`) and found no run.
- **Idle eviction.** A separate run left a bound worker idle with no client
  attached; its supervisor retired it about 61 minutes after its last `Stop`
  (between the polls at 60 and 61 minutes, on 2.1.286 and again on 2.1.287),
  as in two earlier exploratory runs on 2.1.286. Retirement published no hook,
  not even `SessionEnd`: the job was listed with `state` = `done` and no pid,
  and the run was orphaned. `claude attach` respawned the worker as a new
  process whose `SessionStart` (`resume`) at the Worktree holding the run
  continued it with its `startedAt`. The retained
  [idle trace](spikes/measurements/issue-162-claude-idle-trace.jsonl) is
  verified with the acceptance trace.

### Worktree tools between Issue Worktrees at 2.1.286

The [worktree-tool experiment](../scripts/experiments/claude-327/run.mjs) for
[Issue #327](https://github.com/ned2/dashpot/issues/327) ran on Linux on
2026-10-02 against 2.1.286. It reused the
[#162 acceptance runner's](#clients-and-supervised-workers-through-dashpot-at-21286)
arrangement: headless `claude -p` clients under
`--dangerously-skip-permissions`, an isolated configuration, a loopback
Messages API, and hooks handed to Dashpot's real publisher, with the
sessions' shells running the real `dashpot work` commands. The Issue
Worktrees were linked Worktrees in a pool beside the main checkout, where
Dashpot's default Worktree Root puts them. Like that runner, it refuses to
start inside a Claude Code session, so launch it from a plain shell or with
`setsid -f`. The [verifier](../scripts/experiments/claude-327/verify.mjs) checks the claims
below against the retained
[trace](spikes/measurements/issue-327-claude-2.1.286-trace.jsonl). The same run
behaved identically on 2.1.283, the release the Issue observed
([trace](spikes/measurements/issue-327-claude-2.1.283-trace.jsonl)), and on
2.1.287 ([trace](spikes/measurements/issue-327-claude-2.1.287-trace.jsonl)),
each verified with its version as the second argument:

```bash
node scripts/experiments/claude-327/run.mjs ~/.local/share/claude/versions/2.1.286
node scripts/experiments/claude-327/verify.mjs \
  docs/spikes/measurements/issue-327-claude-2.1.286-trace.jsonl
node scripts/experiments/claude-327/verify.mjs \
  docs/spikes/measurements/issue-327-claude-2.1.283-trace.jsonl 2.1.283
```

- **From the main checkout.** `EnterWorktree` with `path` entered an Issue
  Worktree. After `work stop`, `ExitWorktree(keep)` returned the session to
  the main checkout. `EnterWorktree` then entered a second Issue Worktree,
  and after another return entered the first one again. Each call fired one
  `PostToolUse` whose `cwd` was the directory reached. `work show` and
  `work start` ran there, a bound run moved with each call, and no Worktree
  was removed.
- **A direct switch.** From an entered Issue Worktree, `EnterWorktree` to
  another one was refused, fired no hook, and left the session and its run
  where they were. With `<repo>/.claude/worktrees/` absent the refusal read
  "Cannot enter worktree: `<repo>`/.claude/worktrees does not exist, so
  `<target>` cannot be a worktree managed by Claude Code." With it present,
  it read "Cannot enter worktree: `<target>` is not under
  `<repo>`/.claude/worktrees. Switching from this session is limited to
  worktrees managed by Claude Code (created under .claude/worktrees/ of this
  repository).", and a direct switch to a linked worktree under that
  directory was accepted. The tool's own description states the rule: the
  first entry from the launch directory needs only a path in
  `git worktree list`, while a session already in a worktree may switch only
  to one under `.claude/worktrees/`.
- **Launched in a linked Worktree.** A fresh session started in a linked
  Worktree entered a sibling, with `.claude/worktrees/` absent or present,
  carrying its run. It was refused the main checkout ("is the main working
  tree, not a linked worktree"). Its `ExitWorktree(keep)` returned it to the
  Worktree it was launched in, from where it entered the other sibling. Its
  Bash `cd` to the main checkout was answered "Shell cwd was reset to
  `<launch Worktree>`".
- **Resumed in an entered Worktree.** A session that entered an Issue
  Worktree and ended there was resumed with `claude -p --resume <id>` from
  that Worktree, as the Sessions pane's copied resume command does. It kept
  its `session_id`, and its `SessionStart` reported `source` = `resume` at
  the Worktree. A direct switch to another Issue Worktree was refused with
  the "is not under" wording above, and a Bash `cd` to the main checkout was
  reset. Its `ExitWorktree(keep)` still returned it to the main checkout it
  had entered from, after which `EnterWorktree` succeeded. By the
  executable's source, the transcript records the worktree session and a
  resume restores it, which makes the resumed session count as already in a
  worktree.

This explains the refusal that
[Issue #327](https://github.com/ned2/dashpot/issues/327) observed on 2.1.283
in an interactive session launched in a linked Worktree. A fresh launch there
is accepted, so that session was most likely already in a restored worktree
session. That cause is inferred, not reproduced from the Issue's session.
Dashpot's Worktrees sit outside `.claude/worktrees/`, so a session moves
between them only through `ExitWorktree(keep)` and a new `EnterWorktree`
([ADR 0085](adr/0085-return-a-claude-code-session-before-entering-another-issue-worktree.md)).
By the executable's source, `EnterWorktree` outside `.claude/worktrees/`
asks the person for permission in a mode that does not bypass permissions.
That prompt, interactive terminals, and supervised workers were not
measured here.

### The Agent SDK normally owns a CLI subprocess

Python's `ClaudeSDKClient` keeps one conversation across successive
`client.query()` calls. The SDK session guide distinguishes this from passing
an explicit saved ID to `resume`; `continue` selects the latest conversation in
the current directory. A fork receives a new ID and independent history.
TypeScript's documented session-management API differs from Python's client
object. [Source: SDK sessions](https://code.claude.com/docs/en/agent-sdk/sessions).

The Python default transport starts the CLI as a child process, with piped
stdin/stdout and the configured `cwd`. Its cleanup is designed to terminate
and reap that child. This is lifecycle ownership, not merely a browser leaving
a shared server. Custom transports can replace the default and are outside
this conclusion. [Source: subprocess transport](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py).

`ClaudeSDKClient` creates that transport on connection, keeps it across query
calls, and disconnects on context-manager exit. Its `query(session_id=...)`
parameter is forwarded in input messages, but that implementation alone does
not prove independent conversations can be multiplexed over one CLI worker.
The documented same-conversation contract is the safe baseline pending an
experiment. [Source: Python client](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py).

Standalone `query()` creates its own default transport and closes the query
in a `finally` block. Thus multiple independently created SDK calls need not
mean multiple conversations inside one executing process; default calls own
separate transport instances. [Source: internal query lifecycle](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/client.py).

### Hooks and delegated work need their own identity mapping

Hook inputs include current `session_id` and `cwd`; subagent calls additionally
expose `agent_id`. `SubagentStop` distinguishes the main transcript from the
child transcript. `SessionStart` covers startup, resume, clear, compaction, and
fork. `SessionEnd` reasons include `/clear` and switching conversations with
interactive `/resume`, so it is not synonymous with process exit. `Stop`
describes the end of a response, not necessarily the whole session. The hooks
also include `CwdChanged` with old/new locations.
[Source: hooks reference](https://code.claude.com/docs/en/hooks).

The reviewed hook reference does not document Dashpot's shell variables
`CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`. The
[Claude Code experiment](spikes/claude-code-identity-lifecycle-spike.md#scenario-results)
measured them at `2.1.276` in the headless and background modes: hook
`session_id`, the shell's `CLAUDE_CODE_SESSION_ID`, and the headless result's
`session_id` agree, and `CLAUDE_PID` is the pid of the process running the
conversation, which is the worker for a background session. `--resume` keeps
the session ID in a new process and reports `SessionStart.source` = `resume`;
`--fork-session` mints a new ID, reports `source` = `fork`, and names no
parent in the payload. A headless process publishes `SessionEnd` with
`reason` = `other` at exit. A subagent started by the Agent tool runs in the
parent's process with the parent's `session_id` and `CLAUDE_PID`; only
`agent_id` and `agent_type` on `SubagentStart`, its tool hooks, and
`SubagentStop` distinguish it, and `CLAUDE_CODE_CHILD_SESSION=1` is present in
every measured shell, so it is not a subagent marker. Do not treat a child's
`agent_id` as interchangeable with its parent's `session_id`. The interactive
terminal, Remote Control, and SDK values are not measured; `CwdChanged` did not
fire for a background worker's `EnterWorktree`. A sub-agent's hooks carry
its parent's `cwd`, not its own location
([sub-agent hooks and location](#sub-agent-hooks-and-location-at-21285)).

Ordinary subagents have separate contexts and can run alongside the main
conversation. Their transcripts can be resumed through the containing session.
Conversation-fork subagents and independent background-session forks are
distinct features; the meaning of `/fork` depends on agent-view configuration.
Worktree isolation is also available to subagents.
[Source: subagents](https://code.claude.com/docs/en/sub-agents). In 2.1.289, with a
fresh configuration, `/fork` publishes no `SessionEnd`. It starts the copy
as a background session under a transient daemon, which publishes
`SessionStart` `fork` with a new id from its own process and begins no turn.
A background Sub-agent of the forking session stays with that session
([measured under #488](spikes/idle-session-start-and-fork-spike.md#claude-code-21289)).

Agent teams are another case: teammates are described as separate Claude Code
sessions. The default display mode is in-process, with split panes as an
alternative. In-process teammates are not restored by `/resume`, and their
background work cannot outlive the lead process. This makes teams a useful
concurrency test, without assuming their shell/hook ID mapping from the display
mode's name. [Source: agent teams](https://code.claude.com/docs/en/agent-teams).

### Cloud sessions are a separate execution location

Claude Code on the web runs in cloud infrastructure and can execute tasks in
parallel sessions. `--remote` starts cloud work; `--teleport` brings its branch
and conversation into a local terminal. That terminal receives its own copy:
subsequent local work is not mirrored back to the cloud conversation. This
differs from Remote Control attachment. The reviewed page does not establish
the resulting local-to-cloud native-ID relationship.
[Source: web sessions and teleport](https://code.claude.com/docs/en/claude-code-on-the-web).


## OpenCode

### Backend and clients

OpenCode v2 serves every session from a server process and connects clients
to it. As `opencode --help` lists them at 2.0.22:

| Entry point | Startup and ownership |
| --- | --- |
| `opencode [<directory>]` | TUI. It connects to the shared service, starting one if none runs, and works in `<directory>` |
| `opencode run [<message>]` | One non-interactive turn against the shared service |
| `--session <id>`, `--continue` | Continue a session, in either client; `--session` creates the session if it does not exist |
| `--standalone` | Either client with a private `opencode serve --stdio --port 0` of its own instead of the service |
| `--server <url>` | Either client against another server; unmeasured ([#379](https://github.com/ned2/dashpot/issues/379)) |
| `opencode service start` / `stop` | The shared service, `opencode serve --service`, one per user, registered in `$XDG_STATE_HOME/opencode/service.json` with its loopback port and a Basic-auth password |
| `opencode session delete <id>`, `opencode reload` | Requests to the shared service |
| `opencode serve`, `opencode acp`, `opencode pair` | The API and web server, the Agent Client Protocol server, and browser or app pairing; unmeasured |

OpenCode 1.x's `opencode attach <url>` and `opencode run --attach <url>` are
gone. The v2 API serves `POST /api/session`, `/api/session/:id/prompt`,
`/api/session/:id/move`, `/api/experimental/session/:id/wait`, and SSE at
`/api/event`; a request names its location with `x-opencode-directory`.
[Server architecture](https://opencode.ai/docs/server/)
[CLI entry points](https://opencode.ai/docs/cli/)

The [#393 experiments](spikes/opencode-v2-spike.md) measured the shared
service's process shape, plugin instances, shell identity, Sub-agents, moves,
`--standalone` and idle eviction at 2.0.22, and the
[plugin protocol experiment](spikes/opencode-v2-plugin-protocol-spike.md) the
plugin API Dashpot's plugin uses; what the acceptance run adds is
[below](#the-shared-service-through-dashpot-at-2022). The rest of this
section, down to that subsection, is the earlier experiment on 1.18.30, the
v1 release Dashpot now refuses.

The 1.18.30 experiment ran `opencode serve --hostname 127.0.0.1 --port 0`
with independent local HTTP/SSE clients and attached CLI requests. Two native
conversations ran real shell tools concurrently under the same backend PID.
[Measured configuration](spikes/opencode-identity-lifecycle-spike.md#tested-configuration-and-evidence-boundary)

### SDK and editor transports

In `@opencode-ai/sdk`, `createOpencode()` starts both a server and client;
`createOpencodeClient({baseUrl})` connects without starting a backend.
The owning result exposes `server.close()`. Inline `config` augments normal
configuration rather than making the process isolated by itself.
[SDK startup and client-only mode](https://opencode.ai/docs/sdk/)

The `1.18.30` SDK source launches `opencode serve`, inherits the launching
process environment, and injects inline configuration through
`OPENCODE_CONFIG_CONTENT`. Its close/abort path stops that spawned process.
A client-only connection has no corresponding ownership of an existing server.
[Released SDK server launcher](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/sdk/js/src/server.ts)

That client's `directory` option is request-routing context, encoded in
`x-opencode-directory` and rewritten as a query parameter on GET/HEAD requests.
It is not conversation identity or proof that any local process changed cwd.
[Released SDK client](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/sdk/js/src/client.ts)

Editors can instead launch `opencode acp` as an ACP subprocess using JSON-RPC
over stdio. This is a separate protocol entry point from HTTP/SSE attachment;
ACP identity and exit behavior were not exercised by the HTTP experiment.
[ACP integration](https://opencode.ai/docs/acp/)

### Configuration and connection ownership

`serve` defaults to loopback; remote listeners need a deliberate hostname.
`OPENCODE_SERVER_PASSWORD` enables HTTP Basic authentication, with
`OPENCODE_SERVER_USERNAME` overriding the default username. Browser CORS
allowlists are separate from authentication.
[Listener configuration](https://opencode.ai/docs/server/)

Runtime config combines user, project, custom-file, inline, and managed layers.
`OPENCODE_CONFIG` is a file override; `OPENCODE_CONFIG_DIR` changes the additional
configuration directory. They are not substitutes for isolating all configuration
and state roots. TUI preferences use `tui.json` separately from `opencode.json`.
[Configuration discovery](https://opencode.ai/docs/config/)

Plugin discovery includes project `.opencode/plugins/`, the effective global
plugin directory (documented as `~/.config/opencode/plugins/`), and configured
packages. Plugins execute with the server's project context and SDK client;
putting a plugin only on a remote terminal's machine does not install it into
the serving backend. The latter is an architectural inference from this context
and client/server separation.
[Plugin discovery](https://opencode.ai/docs/plugins/)

Skills can also come from project/global `.claude/skills` and `.agents/skills`
locations as well as OpenCode's own directories. Configuration isolation must
account for these shared discovery paths.
[Skill discovery](https://opencode.ai/docs/skills/)

### Identity, location and delegated work

This and the next subsection record the 1.18.30 experiment.

In the tested legacy plugin path, `shell.env` supplies `sessionID` and a tool
`callID` for the model-driven Bash command. That native ID selects the executing
conversation, including a delegated child. The experimental plugin injected its
own identity claim; this was not evidence of a built-in shell environment
variable contract. A PTY invocation reached the same environment hook without a
session ID and received no injected identity.
[Measured identity cases](spikes/opencode-identity-lifecycle-spike.md#scenario-results)

Fetched native session metadata, plugin instance directory and Worktree context
agreed on the conversation's directory even when a Bash command requested a
different `workdir`. A command's cwd therefore did not change the conversation's
native location. The SSE connection was directory-scoped rather than an
identity authority for one conversation.
[Measured location cases](spikes/opencode-identity-lifecycle-spike.md#scenario-results)

A native task created a distinct child ID with `parentID` pointing to the parent.
A fork also received a new ID but had no `parentID` in the measured release;
its provenance came from the explicit fork operation. Background children could
remain busy after their parent became idle, with later completion notification
making the parent busy again. Background behavior required the experiment's
explicit feature flag.
[Measured delegation](spikes/opencode-identity-lifecycle-spike.md#scenario-results)

### Lifecycle and observation

| Boundary | Measured outcome in OpenCode 1.18.30 |
| --- | --- |
| Close/reopen SSE | No conversation deletion or plugin disposal; conversation continued |
| Exit attached CLI during a command | Backend command completed; a new CLI continued the same conversation |
| Busy, retry, idle | Independent activity per native ID; retry did not end the conversation |
| Interrupt | Current command aborted; a later prompt reused the native ID |
| Instance/plugin disposal | A subsequent request loaded a new plugin generation at the same backend PID |
| Remove plugin | Backend and conversation remained usable; experimental identity publication disappeared |
| Delete a conversation | `session.deleted` for that conversation; other conversations and backend survived |
| Signal backend exit and restart | Native conversation resumed under a new backend PID; final plugin disposal was not observed for SIGTERM or SIGKILL |

These are measured outcomes, with trace positions and exclusions in the
[scenario results](spikes/opencode-identity-lifecycle-spike.md#scenario-results).

Native `session.status` distinguishes busy, retry and idle. Idle can be reported
more than once and does not establish conversation deletion. The pinned plugin
dispatcher awaits trigger hooks but does not await event-callback promises;
the experiment's ordered publication and stale-generation rejection came from
its own bridge, not an upstream delivery guarantee.
[Source: release plugin dispatcher](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/plugin/index.ts)

The separate V2 shell implementation had an environment-augmentation TODO in
this release. No V2, remote backend, or installed Dashpot helper compatibility
was established. The retained runner isolates home/XDG/configuration, uses a
loopback model fixture, and records metadata only; its reproduction steps and
exact flags remain in the
[experiment](spikes/opencode-identity-lifecycle-spike.md#reproduce).

### The shared service through Dashpot at 2.0.22

The OpenCode acceptance run, first written for 1.18.30 by
[#163](https://github.com/ned2/dashpot/issues/163) and re-pinned by
[#407](https://github.com/ned2/dashpot/issues/407), drove OpenCode 2.0.22 on
Linux through Dashpot's installed plugin and helper, in isolated
configuration with a loopback model, beside a 2.0.21 and a 1.18.30 binary;
its [trace](spikes/measurements/issue-163-opencode-trace.jsonl) is metadata
only. What it adds to the #393 experiments:

| Boundary | Measured outcome in OpenCode 2.0.22 |
| --- | --- |
| `opencode <directory> --prompt <text>` from another directory | The TUI starts the shared service as its child, which listens on the registered loopback port only, and creates the session in `<directory>`; the model's commands run there |
| A model's shell | `OPENCODE_SESSION_ID` and `OPENCODE=1`, set after every plugin hook, so the plugin's `create.before` hook can clear an inherited pair and OpenCode sets its own |
| A user's shell, as the TUI's `!` runs one through the API | The plugin's hook runs, but OpenCode sets neither variable |
| A terminal the server opens | No plugin hook runs: it inherits the server's environment, and with it whatever the client that started the service inherited |
| Quit the TUI, or `opencode run` exits | The service and every session in it keep running |
| `opencode <directory> --session <id>` from another directory | The session resumes where it was; its commands run there |
| `subagent` with `background: true` | Runs without a flag; the parent's execution ends before the child's first command starts, and the child's end starts the parent again |
| A move requested while the session works | Answered at once, and applied when the execution ends |
| A plugin file edit, or `opencode reload` | Every instance is set up again; a reload cleans every one up first, and sets them up before the last cleanup's one-second wait ends, so it marks no session |
| `opencode session delete <id>` from another location | Deletes the session in the service, which publishes `session.deleted` |
| A TUI of another release, older or newer | It stops the running service and starts its own, which serves the same sessions |
| `opencode service stop`, or SIGKILL to the service | The service exits without a session event; a stop removes its registration, a kill leaves it |
| `--standalone` TUI or `run` | A private `opencode serve --stdio --port 0`, the client's child, which exits with it |
| The npm package | The service is `opencode.exe`, from the package's own directory |

A missing helper costs a turn nothing measurable. A stalled one is cut off at
the plugin's 3 s deadline, and a shell waits no longer than that for it.
Dashpot's reading of each outcome is in
[OpenCode hosting modes](agent-sessions.md#opencode-hosting-modes).

## Identity and lifecycle verification checklist

This is a reference coverage checklist, not a Dashpot implementation plan.
Record answers here as primary contracts or isolated measurements become
available, preserving release and mode boundaries.

| Question | Codex | Claude Code | OpenCode |
| --- | --- | --- | --- |
| Does one selected host PID distinguish conversations? | No for app-server, measured at `0.155.1`: one `codex` process hosted two root threads, a fork, and a sub-agent thread, with every shell and hook below it; yes for `codex exec`, which is one process per thread; at `0.159.3` and `0.160.0` a plain terminal's thread is hosted by the managed daemon, and a terminal launched with `--disable daemon_auto_start` while no daemon runs is one process per thread | Yes for the measured modes at `2.1.276`: one process per headless conversation and per background worker, with a subagent inside its parent's process; Remote Control server mode unmeasured | No, measured at `2.0.22`: the shared service hosts every session of every location; a `--standalone` client's private server hosts that client's |
| Does client disconnect stop execution? | Measured at `0.155.1`: a departing client's command ran to completion with its ordinary tool hooks and `Stop` and no `Interrupt` or `SessionEnd`, and the last unsubscription unloaded the thread with `SessionEnd` after 60,067 ms (sixty seconds by code default at `0.154.0`); the embedded TUI's shutdown on exit is source reading | Measured: a killed `attach` terminal leaves the worker running with no hook; Remote attachment and SDK transport exit unmeasured | No for the shared service, measured at `2.0.22`: a TUI's quit and `opencode run`'s exit leave its sessions running; a `--standalone` client's exit stops its private server |
| Does process restart erase history? | Measured at `0.155.1`: after SIGKILL of the server a replacement server resumed the stored thread at another cwd under the same id, with `SessionStart` `resume` at the first turn and no `SessionEnd` for the kill; the stale lock file did not block it | Measured: a killed or respawned worker and a replaced supervisor keep the session ID; `SessionStart` reports `resume` for the new worker pid | No, measured at `2.0.22`: a service of another release, or one restarted after a stop or a kill, serves the same session ids |
| Are hook/command IDs fully mapped? | Measured at `0.155.1` for app-server and `exec`: root and fork hook `session_id` = `thread.id` = `thread.sessionId` = shell `CODEX_THREAD_ID` = shell `CODEX_SESSION_ID`; a sub-agent's shell claims its own id in `CODEX_THREAD_ID` and the root in `CODEX_SESSION_ID`, and its hooks carry the root `session_id` plus `agent_id`; hook processes carry no thread variable; Code Mode remote host unmeasured | Measured for headless and background: hook `session_id` = shell `CLAUDE_CODE_SESSION_ID` = listing `sessionId`; job `id` is its first eight characters; `CLAUDE_PID` = worker pid; a subagent reuses both and adds `agent_id`; remote URL ID unmeasured | Measured at `2.0.22`: a model's shell carries its own session's `OPENCODE_SESSION_ID` with `OPENCODE=1`, a child's included; a user's shell and a terminal carry neither of their own; event ids are per event, and `durable.seq` orders each session's |
| Is native parentage equivalent to fork origin? | No, measured at `0.155.1`: `thread/read` reports `forkedFromId` and `SessionStart` reports `source` = `fork`, but the payload has no parent field (`startup` for a fork at `0.154.0` by source reading); a sub-agent's `parentThreadId` is delegation, not fork origin | No at `2.1.276`: `SessionStart` reports `source` = `fork` without a parent field; the explicit `--resume` argument is the recorded origin | No, measured at `2.0.22`: a fork publishes `session.forked`, whose `parentID` names its source, and the forked session itself has no `parentID`; a Sub-agent's `parentID` is delegation |

Remaining reference gaps include worker process ancestry and remote URL
identity in
Claude Remote Control, whose server mode needs a claude.ai login;
plugin-distributed Claude channels; resuming a Claude background session
while its worker is mid-turn, and how a person detaches from one opened by
`--resume`; the Claude desktop app's host; `--setting-sources` forwarding to
sessions spawned from a restricted one; the source of a `SubagentStop` with no
`SubagentStart` seen after `Stop` in a live Claude session;
Codex
`/cd`, managed `/worktree`, Remote Control pairing, a terminal started before
the daemon, and
remote-execution hook identity mapping; OpenCode ACP, `opencode web`, the
desktop app and `--server <url>` clients; and the precise configuration/hook
mapping across remote execution hosts. Do not turn a documented ability to
subscribe into a guarantee of concurrent mutation safety for one conversation.

## Maintaining this reference

Update this document when a release changes the hosting or identity contract.
Keep command/version caveats next to the affected mechanism and distinguish
current docs from pinned code and measured behavior. Preserve reproducible
experiment records as evidence, and link them here rather than duplicating
traces. Keep proposed Dashpot policies and implementation sequencing in design
documents. The initial Codex workflow section was copied from
`docs/codex-app-server-workflows-research.md` in the operator's main checkout;
the OpenCode configuration section also incorporates the earlier
`docs/opencode-harness-support-research.md` from that checkout. Its static
lifecycle unknowns are superseded here where the retained experiment supplies
evidence. The main checkout has not been modified.
