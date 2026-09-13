---
status: living
date: 2026-09-13
---

# Agent harness server and client reference

This reference explains how Claude Code, Codex CLI, and OpenCode host
conversations, connect clients, execute tools, and report lifecycle changes.
Use it to distinguish conversation identity from the processes and connections
that serve it, and to choose the right upstream interface without repeating
three separate investigations.

Dashpot's proposed integration behavior belongs in the
[OpenCode integration design](opencode-integration-design.md) and the
[Codex relocation and handoff design](codex-relocation-handoff-design.md), not
in this reference. The [domain language](domain-language.md#observation) defines
Dashpot's Agent Session and Agent Run; upstream products' terms are preserved
below where their meanings differ.

## Scope and evidence

| Harness | Evidence available | Limits |
| --- | --- | --- |
| Codex | Local CLI help/version `0.154.0`; current official documentation; pinned `rust-v0.154.0` source and post-release `main` PRs read statically on 2026-09-13 | No live server, hook-mapping, or restart experiment; hook ordering is derived from the call graph, not timed |
| Claude Code | Local CLI version `2.1.261`; current official docs and Python SDK source | No live server or SDK experiment; Remote Control worker ancestry unverified |
| OpenCode | Isolated Linux experiment on `1.18.30`, legacy plugin path; pinned release source and current official docs | Local HTTP/SSE and attached CLI tested; interactive clients, V2 and remote execution untested |

Documentation was reviewed on 2026-09-13; OpenCode measurements were taken on
2026-09-12. Current documentation and source branches can change independently
of an installed binary. Version-sensitive commands and identity mappings need
checking when the supported release changes. Statements marked as inference or
unverified are not runtime findings.

This reference consolidates the Codex workflow research supplied from the main
checkout, the Codex and Claude comparison notes, and the reusable findings from
the [OpenCode experiment](opencode-identity-lifecycle-spike.md). The experiment
remains a dated evidence record with its fixtures and trace; maintain general
server/client facts here instead of creating another comparison note.

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
| Codex App Server | TUI/custom client to app-server; execution host is a separate connection | Multiple threads per app-server | Native thread IDs and thread/turn events |
| Claude interactive Remote Control | Web/mobile controls an existing local session | One remote session per interactive process | Local conversation continues when Remote Control disconnects |
| Claude Remote Control server | Anthropic-routed clients to a local server | Multiple sessions; exact worker ancestry unverified | Server session management, distinct from browser attachment |
| Claude background supervisor | Agent view/attach controls supervised workers | One worker process per background session | Supervisor can reconnect to surviving workers |
| Claude Python Agent SDK | Application controls its default CLI subprocess | Persistent client keeps one conversation; separate calls can own separate workers | Transport owns subprocess lifecycle |
| OpenCode serve | HTTP/SSE or attached CLI to one backend | Multiple native sessions sharing the measured backend PID | Native session events and command-scoped plugin context |

Source details, deployment boundaries, and caveats are in each harness section.
Sharing a server is independent of sharing history, sharing checked-out files,
or having multiple clients operate on the same conversation. It does not by
itself establish inter-agent collaboration, lower model costs, or safe parallel
edits. Distinct Worktrees isolate ordinary checked-out files while retaining
shared Git metadata; process isolation does not supply file isolation.

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
[Developer commands][commands]

Installed `0.154.0` help additionally exposes `codex agents` for browsing the
shared local daemon, and `codex app-server daemon` with `start`, `restart`,
`stop`, `version`, `bootstrap`, and Remote Control enable/disable subcommands.
This is local command-surface evidence from `codex --help` and
`codex app-server daemon --help`, not a daemon-lifecycle experiment.

### Documented server model

App Server multiplexes threads with separate turns and tool items. Its
bidirectional JSON-RPC wire format omits the `jsonrpc` field; initialize each
connection. `thread.id` identifies a conversation, whereas `thread.sessionId`
identifies its live session-tree root; the documentation says forks share it,
but the pinned `0.154.0` code and fork test give a forked root thread its own
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
subscribers or activity; the pinned `0.154.0` code default is sixty seconds
(see [Loaded threads, overrides, and unload](#loaded-threads-overrides-and-unload)).
Ephemeral threads have different persistence. These are current protocol
contracts, not local measurements. [App Server lifecycle][server]

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
hooks use the parent's session ID. These distinctions need checking against the
installed release and integration mode. [Hook documentation][hooks]

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
[Code Mode host][server]

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

### Thread ownership and competing resume

Evidence in this subsection is static reading of `rust-v0.154.0`, which
includes [PR #43253][pr-43253]; no lock or client was exercised.

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
lock. An abrupt kill releases the lock with no `SessionEnd`.
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
no parent or fork field). The old thread's `SessionEnd`, with the old ID and
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

### Changes on `main` after `rust-v0.154.0`

As of 2026-09-13 the newest stable release is `rust-v0.154.0` (published
2026-09-09) and the newest prerelease is `rust-v0.155.0-alpha.3.10`
(2026-09-11), whose notes are stubs. Merged PRs relevant to the mechanisms
above, none yet in a stable release: [#44349][pr-44349] adds `fork` as a
`SessionStart` source and reports supplied-history resumes as `resume`;
[#44870][pr-44870] enables `worktrees` by default and blocks worktree creation
and `/cd` when the local daemon lacks `thread/backgroundTerminals/list`;
[#44711][pr-44711] and [#44969][pr-44969] extend the read-only snapshot and
explicit retry to the command center and to tasks owned by another app
server; [#44183][pr-44183] releases the writer when a resume is cancelled
during startup; [#43848][pr-43848] preserves runtime workspace roots across
resume and retargets the old cwd root when cwd changes. No PR changes the
`codex resume` flags. Revalidate these against the release that ships them.

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
| `claude --bg <prompt>`, `claude agents` | Background dispatch or agent view |
| `claude attach <id>`, `claude respawn <id>` | Attach to a background job or replace its worker |
| `claude agents --json`, `claude daemon status` | Supported job/worker listing or supervisor diagnostics |

These are documented commands, not operations performed for this reference.
[CLI reference](https://code.claude.com/docs/en/cli-reference)

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
all conversations execute inside that server PID.

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

These fields provide candidate observation evidence, but the reviewed hook
reference does not establish Dashpot's shell variables
`CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`, their subagent values, or their
agreement with every hosting mode. In particular, do not assume a child's
`agent_id` is interchangeable with its parent's `session_id`.

Ordinary subagents have separate contexts and can run alongside the main
conversation. Their transcripts can be resumed through the containing session.
Conversation-fork subagents and independent background-session forks are
distinct features; the meaning of `/fork` depends on agent-view configuration.
Worktree isolation is also available to subagents.
[Source: subagents](https://code.claude.com/docs/en/sub-agents).

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

| Entry point | Startup and ownership |
| --- | --- |
| `opencode [project]` | Ordinary TUI with a server behind it |
| `opencode serve` | Headless HTTP backend |
| `opencode web` | Backend plus browser UI |
| `opencode attach <url> --session <id>` | TUI using an existing backend conversation |
| `opencode run --attach <url> --session <id> <prompt>` | Non-interactive request against that backend |

The ordinary TUI/server split is documented independently of the experiment.
The HTTP API has an OpenAPI schema at `/doc`, session operations, and SSE at
`/event` and `/global/event`.
[Server architecture](https://opencode.ai/docs/server/)
[CLI entry points](https://opencode.ai/docs/cli/)

`opencode web` and an attached TUI can simultaneously use the same sessions
and state. This establishes multiple interfaces, not unrestricted concurrent
prompt mutation. Browser closure, attached-TUI exit, and closing the TUI that
started a backend are distinct ownership cases; interactive shutdown was not
measured. [Web and terminal attachment](https://opencode.ai/docs/web/)

For attached `run`, `--dir` names a path on the server. Its files, tools, and
provider credentials belong to the execution machine. A remote client is not
a mechanism for copying its local checkout to that machine.
[Remote directory option](https://opencode.ai/docs/cli/#run)

The retained experiment ran `opencode serve --hostname 127.0.0.1 --port 0`
with independent local HTTP/SSE clients and attached CLI requests. Two native
conversations ran real shell tools concurrently under the same backend PID.
[Measured configuration](opencode-identity-lifecycle-spike.md#tested-configuration-and-evidence-boundary)

### SDK and editor transports

In `@opencode-ai/sdk`, `createOpencode()` starts both a server and client;
`createOpencodeClient({baseUrl})` connects without starting a backend.
The owning result exposes `server.close()`. Inline `config` augments normal
configuration rather than making the process isolated by itself.
[SDK startup and client-only mode](https://opencode.ai/docs/sdk/)

Pinned `1.18.30` SDK source launches `opencode serve`, inherits the launching
process environment, and injects inline configuration through
`OPENCODE_CONFIG_CONTENT`. Its close/abort path stops that spawned process.
A client-only connection has no corresponding ownership of an existing server.
[Released SDK server launcher](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/sdk/js/src/server.ts)

The pinned client's `directory` option is request-routing context, encoded in
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

In the tested legacy plugin path, `shell.env` supplies `sessionID` and a tool
`callID` for the model-driven Bash command. That native ID selects the executing
conversation, including a delegated child. The experimental plugin injected its
own identity claim; this was not evidence of a built-in shell environment
variable contract. A PTY invocation reached the same environment hook without a
session ID and received no injected identity.
[Measured identity cases](opencode-identity-lifecycle-spike.md#scenario-results)

Fetched native session metadata, plugin instance directory and Worktree context
agreed on the conversation's directory even when a Bash command requested a
different `workdir`. A command's cwd therefore did not change the conversation's
native location. The SSE connection was directory-scoped rather than an
identity authority for one conversation.
[Measured location cases](opencode-identity-lifecycle-spike.md#scenario-results)

A native task created a distinct child ID with `parentID` pointing to the parent.
A fork also received a new ID but had no `parentID` in the measured release;
its provenance came from the explicit fork operation. Background children could
remain busy after their parent became idle, with later completion notification
making the parent busy again. Background behavior required the experiment's
explicit feature flag.
[Measured delegation](opencode-identity-lifecycle-spike.md#scenario-results)

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
[scenario results](opencode-identity-lifecycle-spike.md#scenario-results).

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
[experiment](opencode-identity-lifecycle-spike.md#reproduce).

## Identity and lifecycle verification checklist

This is a reference coverage checklist, not a Dashpot implementation plan.
Record answers here as primary contracts or isolated measurements become
available, preserving release and mode boundaries.

| Question | Codex | Claude Code | OpenCode |
| --- | --- | --- | --- |
| Does one selected host PID distinguish conversations? | App Server hosts multiple threads | Explicit background workers are separate; other modes need ancestry verification | No in the tested backend |
| Does client disconnect stop execution? | Unsubscription starts an unload delay (sixty seconds by code default at `0.154.0`); the embedded TUI shuts its thread down on exit | Remote attachment and background workers can survive disconnect; SDK transport exit differs | Attached CLI exit did not stop its command |
| Does process restart erase history? | Stored thread resume documented; crash behavior unmeasured | Background workers resume retained conversations; Remote Control recovery is conditional | Same native ID resumed after backend replacement |
| Are hook/command IDs fully mapped? | Root and fork mapping read from `0.154.0` source (hook `session_id` = thread ID; a fork gets its own); child and execution-host mapping unverified | Remote/job/native/child and shell claim mapping unverified | Native shell ID measured for legacy Bash; PTY can lack ID |
| Is native parentage equivalent to fork origin? | No at `0.154.0`: the store records `forked_from_thread_id`, but the `SessionStart` payload has no parent field and reports `startup` for a fork (`fork` source lands after this tag) | Several fork and delegation forms; mapping unverified | No: measured fork lacked child `parentID` |

Remaining reference gaps include exact mode-specific hook delivery on eviction,
restart and abrupt exit; worker process ancestry in Claude Remote Control;
Codex child-thread and remote-execution hook identity mapping; OpenCode interactive/ACP shutdown and V2
behavior; and the precise configuration/hook mapping across remote execution
hosts. Do not turn a documented ability to subscribe into a guarantee of
concurrent mutation safety for one conversation.

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
