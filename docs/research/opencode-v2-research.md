---
status: research
date: 2026-10-02
---

# OpenCode v2 and Dashpot's OpenCode integration

This note compares OpenCode **v2.0.21** with **v1.18.30**, the only release
Dashpot's OpenCode integration supports
([ADR 0081](../adr/0081-support-opencode-1-18-30-on-linux.md)). It covers what
the integration depends on:
- the plugin API;
- an Agent Session Identity in a shell;
- activity events;
- hosting and process ancestry;
- the CLI.

It is the evidence behind [Issue #393](https://github.com/ned2/dashpot/issues/393),
which moves Dashpot to OpenCode v2 only.

All of this comes from reading source code and documentation. A claim marked
_inference_ is our reading of code that no document states, and #393's
measurement step had to confirm it before a design relied on it. That step is
the [OpenCode v2 experiment](../spikes/opencode-v2-spike.md), on 2.0.22,
which answered the [measurement questions](#measurement-questions) below. A
claim it confirmed is marked _measured_ with a link to the experiment; where
it overturned an inference, this note says so. A claim still marked
_inference_ was not measured.

The sources are the release tags [`v2.0.21`][v2] (`8a8bd622`) and
[`v1.18.30`][v1] of `anomalyco/opencode`, and the v2 documentation at
<https://opencode.ai/v2/docs/>. That documentation's source is in the
repository, under `services/www/src/docs/content/`.

## Releases

- **Release dates and packages.** OpenCode 2.0.0 was tagged on 2026-09-11 and
  2.0.21 on 2026-09-30. Both are published to npm as `@opencode/cli`. The v2
  tags sit on the upstream `v2` branch and have no GitHub Release.
- **1.x continues.** It is released from `dev` as `opencode-ai`, with 1.18.34
  on 2026-09-30.
- **Package scope.** The npm scope changed from `@opencode-ai/*` to
  `@opencode/*`, for example `@opencode/cli`, `@opencode/plugin` and
  `@opencode/client`.
- **Binary.** v1 and v2 both install an `opencode` command. v2's installer
  replaces the v1 binary and adds an `opencode2` shim.
- **No legacy engine.** The 1.x engine, `packages/opencode`, does not exist at
  2.0.0. The separate core that 1.18.30 already carried, `packages/core`, is
  v2's execution path, and _inference_: no flag selects another.
- **v1 plugins don't run.** The [migration guide][v2-migrate-plugins] says:
  "V1 plugin implementations do not run in V2. Moving a file or renaming its
  config entry is not enough."

The plugin API also changed within 2.0.x. The plugin context had `catalog` at
[2.0.0][v200-plugin-context]; at [2.0.21][v2-plugin-context] it has `model`
and `provider` instead. The shell tool sets `OPENCODE_SESSION_ID` from 2.0.19
on; 2.0.18's [shell tool][v2018-shell-tool] does not. So the practical floor
for v2 support is 2.0.19, and a support statement names one patch release, as
ADR 0081 did.

## Plugin API

**Module shape.** A v2 plugin module default-exports a definition with an `id`
and either a `setup` function (the Promise API) or an `effect` (the Effect
API). Anything else is refused with "Plugin must export a default definition
with an id and an effect or setup function" ([`module.ts`][v2-module]). A
1.18.30 plugin is either a function from `PluginInput` to `Hooks`, or an
object `{id?, server}` whose `server` is that function
([`index.ts`][v1-plugin-types]).

**The `setup` context.** `setup` receives a context with:
- `app`: `{name, version, channel}`;
- `location`: `{directory, workspaceID?, project}`;
- `options`;
- domain objects, among them `event`, `session`, `shell`, `tool`,
  `permission` and `worktree`.

`setup` may return a cleanup function, which runs when the plugin is unloaded
or replaced.

**The migration guide's mapping.** v1's `directory` and `project` become
`ctx.location`, its `client` becomes the domain methods, `dispose` becomes the
cleanup, and the `event` hook becomes `ctx.event.subscribe()`. Two v1 inputs
have no direct equivalent:
- v1's `worktree` path input. v2's `ctx.worktree` manages Git worktrees rather
  than naming one; the nearest path is `ctx.location.project.directory`.
- `$`, the Bun shell. The guide tells a plugin to import the process API it
  uses.

| Dashpot uses (1.18.30) | v2.0.21 equivalent |
| --- | --- |
| `event({event})` | `ctx.event.subscribe()`, an async iterable of events |
| `"shell.env"(input: {cwd, sessionID?, callID?}, output: {env})` | `ctx.shell.hook("create.before", invocation)`, where `invocation` is `{command, cwd, timeout, shell, env}` |
| `dispose()` | The cleanup returned by `setup` |
| `client.session.get({path: {id}})` | `ctx.session` domain methods; `session.created` carries `parentID` and `location` |
| None; only the [#151 experiment's plugin](../../scripts/experiments/opencode-151/plugin.mjs) used `tool.execute.before` / `after` | `ctx.tool.hook("execute.before" \| "execute.after", event)`. The event has `sessionID` and the call's `id`, and `execute.after` also fires on failure ([`tool.ts`][v2-tool-hooks]) |

**Discovery.** Plugins are still discovered under `plugin/` and `plugins/` in:
- the global configuration directory, `~/.config/opencode` (or
  `$OPENCODE_CONFIG_DIR`);
- each `.opencode/` directory above the location
  ([`source-directory.ts`][v2-source-directory]).

A local plugin is reloaded when its file changes: the cleanup runs, then
`setup` runs again ([`source.ts`][v2-plugin-source]).

**One file for both versions.** v1 and v2 read the same directories, so a 1.x
OpenCode also tries to load a v2 plugin. One default export can serve both,
per the [plugin guide][v2-plugin-guide-v1]: v1 calls the object's `server()`,
and v2 calls its `setup`. A v2 definition without `server()` makes v1 throw
"must default export an object with server()" ([`shared.ts`][v1-plugin-shared]).
v1 logs that as "failed to load plugin" ([`index.ts`][v1-plugin-load]); the
failure is not fatal (_inference_).

## An Agent Session Identity in a shell

This is the change that matters most to Dashpot. In 1.18.30, `shell.env`
received the session's `sessionID` and the tool call's `callID`
([`shell.ts`][v1-shell-env]). That is how Dashpot's plugin scopes a claim to
one command
([ADR 0078](../adr/0078-give-an-opencode-command-a-claim-only-for-its-own-bootstrap.md)).

In v2.0.21, `Shell.create` builds the invocation, triggers `create.before`, and
only then runs its caller's own `before` callback ([`shell.ts`][v2-shell-create]).
Abridged:

```ts
const invocation: ShellCreateBefore = { command, cwd, timeout, shell,
  env: { ...(sessionEnvironment ?? process.env), TERM: "xterm-256color", OPENCODE_TERMINAL: "1" } }
yield* hooks.trigger("shell", "create.before", invocation)
if (before) yield* before(invocation)
```

The model's shell tool passes a `before` callback that sets these variables
([`tool/plugin/shell.ts`][v2-shell-tool-env]):
- `AGENT=1` and `OPENCODE=1`;
- `AI_AGENT`, to `opencode` only if it is unset;
- `OPENCODE_SESSION_ID`.

So:

- A plugin's `create.before` sees neither a session ID nor a call ID, and
  cannot scope what it injects to one session.
- The shell itself receives OpenCode's own `OPENCODE_SESSION_ID`, which is set
  after every plugin hook. A plugin can therefore clear a leaked value without
  removing the real one ([_measured_](../spikes/opencode-v2-spike.md#shell-identity)).
- `create.before` runs for every `Shell.create`, not only the model's tool, so
  it also runs for a user shell ([_measured_](../spikes/opencode-v2-spike.md#shell-identity)). A PTY
  opened through `/api/pty` runs no plugin hook at all
  ([_measured_](../spikes/opencode-v2-spike.md#shell-identity); this note first inferred that every
  shell does).
  `OPENCODE_TERMINAL=1` is set on all of them, so it does not mark an agent's
  shell.
- 1.18.30 set `OPENCODE_PID` ([`index.ts`][v1-opencode-pid]); nothing in
  v2.0.21 does.

**The base environment.** A client pushes its own environment for each session
it opens, and the server holds it in memory.

`Shell.create` uses that environment only for a session outside a workspace
that has one. Otherwise it uses the server's own `process.env`
([`shell.ts`][v2-shell-env-fallback]). That covers every session in a
workspace, and:
- a Sub-agent's child session ([_measured_](../spikes/opencode-v2-spike.md#shell-identity));
- a session created through the HTTP API ([_measured_](../spikes/opencode-v2-spike.md#shell-identity));
- by _inference_, a session opened from the web or desktop client;
- by _inference_, any session after a server restart.

The server's own environment is the one the client that started it had
([_measured_](../spikes/opencode-v2-spike.md#shell-identity)).

## Activity and events

- **Event envelope.** An event is now
  `{id, type, created, data, location?, metadata?, durable?}`
  ([`event.ts`][v2-event]). 1.18.30's was `{type, properties}`.
- **Activity events.**
  - Activity is reported as `session.execution.started`, `.succeeded`,
    `.failed` and `.interrupted` ([`session-event.ts`][v2-execution-events]).
  - An interruption's `reason` is `user`, `shutdown`, `superseded` or
    `inactivity`.
  - A retry is `session.retry.scheduled` ([`session-event.ts`][v2-retry-event]).
- **No status events.** Schemas for `session.status` and `session.idle`
  remain, but nothing in `packages/core` or `packages/server` publishes them.
  The core derives idle from the execution events
  ([`projector.ts`][v2-projector]). 1.18.30's `session.error` becomes
  `session.execution.failed`.
- **Session events.**
  - `session.created` carries `sessionID`, `parentID?`, `location` and
    `projectID`. Session IDs keep their `ses_` prefix
    ([`session-id.ts`][v2-session-id]).
  - `session.deleted` carries `sessionID`. Deleting a session interrupts it
    and deletes its children first ([`session.ts`][v2-session-remove]).
  - A fork publishes `session.forked`.
- **Each plugin instance receives every location's events**
  ([_measured_](../spikes/opencode-v2-spike.md#the-shared-service-and-its-plugin-instances); this note
  first inferred the opposite). The
  [#393 experiment](../spikes/opencode-v2-spike.md#the-shared-service-and-its-plugin-instances)
  found, on 2.0.22 and under a 2.0.21 service, that every instance's
  `ctx.event.subscribe()` delivers
  every event of its server process, whichever location it belongs to. The
  source reading that measurement overturned was:
  - `ctx.event.subscribe()` reads the server-wide event bus
    ([`bus.ts`][v2-bus-node], [`host.ts`][v2-host-subscribe]) through a filter
    ([`bus.ts`][v2-bus-local]), which, when the subscriber's context names a
    location, keeps only that location's events and those with none.
  - The bus routes a session's events to the location that session belongs
    to, and `session.moved` to both the old and the new location
    ([`bus.ts`][v2-bus-routes]), with its own test
    ([`bus-session-routing.test.ts`][v2-routing-test]).
  - The plugin supervisor is per location ([`supervisor.ts`][v2-supervisor]),
    and the Promise adapter runs a plugin's subscription in the supervisor's
    context ([`adapter.ts`][v2-plugin-adapter]). The measurement shows that
    context does not narrow the subscription.

  So 1.18.30's shape, one Publisher Generation per backend and location
  publishing only that location's sessions, does not come for free: a v2
  plugin has to filter, and the activity events carry no location to filter
  on. A v2 location is a directory plus an optional `workspaceID`.
- **Idle eviction.**
  - A location with no session events for 60 minutes is evicted, and its
    running executions are interrupted with reason `inactivity`
    ([`location-activity.ts`][v2-location-activity]). Only a session event
    that carries a location renews the 60 minutes. The execution events
    carry none, and a shell's output goes to a file rather than to events,
    so a shell running for an hour is interrupted whether or not it prints;
    the [#393 experiment](../spikes/opencode-v2-spike.md#idle-eviction)
    measured this.
  - Eviction invalidates the location's services. Code still holding the old
    services keeps them until it releases them.
  - The 60-minute eviction cleans that location's plugin instance up, busy
    or idle ([_measured_](../spikes/opencode-v2-spike.md#idle-eviction)). The debug eviction route
    differs: it never cleans up an instance evicted while busy
    ([_measured_](../spikes/opencode-v2-spike.md#plugin-instance-lifecycle)).

## Hosting and process ancestry

**The default background server.** By default, every local client discovers
or starts one background server for the user: `opencode serve --service`
([`service-config.ts`][v2-service-command]). That server:
- is spawned detached and unreferenced by the client that starts it
  ([`service-contender.ts`][v2-service-contender]);
- changes its working directory to `$HOME` ([`server-process.ts`][v2-server-chdir]);
- is restarted when a client of another version connects
  ([`default.ts`][v2-version-mismatch]).

Its address and password are in `$XDG_STATE_HOME/opencode/service.json`, or
in `service-<channel>.json` outside the latest, dev, beta and next channels
([`service-config.ts`][v2-service-file]).

**Other hosting modes.**
- `--standalone` and `opencode acp` start a private child server,
  `opencode serve --stdio --port 0` ([`standalone.ts`][v2-standalone],
  [`acp.ts`][v2-acp]).
- `--server <url>` uses a given server.

**Where shells and plugins run.** A shell is a child of the server, in a
process group of its own ([`shell.ts`][v2-shell-spawn]). Plugins run inside
the server process, so the helper a plugin spawns is the server's child too
(_inference_). The experiment measured the rest
([_measured_](../spikes/opencode-v2-spike.md#the-shared-service-and-its-plugin-instances)):
- The TUI is an ancestor of a model's shell only under `--standalone`.
- Under the default server, the nearest `opencode` ancestor of a shell is
  `opencode serve --service`.

**What changes for Dashpot.** An OpenCode backend serving many sessions is not
new: at 1.18.30, `opencode serve` was already a non-exclusive Host Process
([ADR 0077](../adr/0077-observe-opencode-through-one-publisher-generation-per-plugin-instance.md)).
What is new is that the default is no longer the TUI hosting its own sessions.
It is one detached backend per user, which:
- runs in `$HOME`;
- serves every directory;
- outlives every TUI.

That backend is shared the way the managed Codex daemon is
([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)), but
not parented the same way: the Codex daemon is its terminal's child, and the
OpenCode server is detached from the client that started it.

**The CLI.** `attach` and `run --attach` are removed, and `--server <url>`
replaces them on the root command, `run`, `session` and others
([`commands.ts`][v2-commands]). New commands include:
- `service`, for starting, stopping, restarting and inspecting the server;
- `reload`, which gives running sessions fresh services at their next step;
- `pair`, for web and desktop clients;
- `plugin`, for managing plugins.

`session delete` asks the server to remove the session
([`delete.ts`][v2-session-delete]), and the server deletes its children too.

## Location, delegation, configuration and storage

- **Sessions can move.**
  - v2 publishes `session.moved` with the new `location`
    ([`session-event.ts`][v2-session-moved]).
  - A plugin moves a session with `ctx.session.move`.
  - The model can call an `opencode.session_move` tool
    ([`opencode.ts`][v2-session-move-tool]). The system prompt suggests that
    tool for adopting a worktree the model created
    ([`opencode.ts`][v2-session-move-hint]).
  - The TUI moves a session when its directory changes
    ([`index.tsx`][v2-tui-move]).
  - ADR 0081's premise that a session "never leaves the directory it was
    created in", and ADR 0077's refusal of a session outside its instance's
    directory, both rest on 1.18.30.
- **Delegation.**
  - The `task` tool is now `subagent` ([`subagent.ts`][v2-subagent]), and the
    `bash` tool is now `shell`.
  - A Sub-agent's session has `parentID` and inherits its parent's location
    ([`session.ts`][v2-session-create]).
  - `background: true` is an ordinary input to `subagent`
    ([`subagent.ts`][v2-subagent-background]). 1.18.30 required
    `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS` for it ([`task.ts`][v1-task]).
  - The shell tool can also run in the background
    ([`tool/plugin/shell.ts`][v2-shell-background]).
- **Configuration.**
  - Files stay where they were: `opencode.json(c)` globally, in the project,
    and in `.opencode/`.
  - v1 keys are still accepted and normalized in memory. In the native format,
    `plugin` becomes `plugins`, and `permission` becomes an ordered
    `permissions` list, with the actions `bash` → `shell` and `task` →
    `subagent`.
  - `tui.json` is replaced by a global `cli.json`, which v2 migrates
    automatically.
  - Skills are read from `~/.config/opencode/skills`, `~/.claude/skills`,
    `~/.agents/skills` and their project equivalents. Dashpot's status check
    already warns about a differing copy of its skill in the shared locations.
- **Storage.** v2 keeps 1.x's SQLite database, `<data>/opencode.db`, and
  _inference_ from `packages/core/src/database/v1-migration*.ts`: it migrates
  v1 sessions into it on first run. Dashpot reads none of OpenCode's storage.

## Open design questions

#393 holds the decision, the sequence, and a likely shape that depends on its
measurements. The questions this note raises for that design are:

- **Agent Session Identity.** Can it come from OpenCode's own
  `OPENCODE_SESSION_ID`, with the plugin's `create.before` contributing only
  its Publisher Generation and backend Host Process, and clearing any leaked
  claim?
- **Activity.** Can the `session.execution.*` events replace `session.status`
  in the plugin's translation?
- **Live Relocation.** Is `session.moved` a Live Relocation
  ([ADR 0067](../adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md))?
- **Generation churn.** What do hot reload, `opencode reload` and idle
  eviction do to Publisher Generations, given they can now be frequent?
- **Refusing v1.** How should Dashpot refuse OpenCode v1? The candidates are
  `dashpot integrate opencode`, the plugin's `server()` entry, and `setup`'s
  `ctx.app.version`.

## Measurement questions

#393's step 1 asked these, because the answers above were inferences. The
[OpenCode v2 experiment](../spikes/opencode-v2-spike.md) answered each of
them, except where it lists a case as not measured:

- Does each location's plugin instance see every server event, or only its
  own location's?
- What does a model-driven shell's ancestry look like under the shared server,
  and what are its process name and argv? Include the `opencode2` shim and the
  npm wrapper.
- What is the shell environment of a Sub-agent session, and of a session with
  no pushed client environment?
- Can a plugin clear a leaked `OPENCODE_SESSION_ID` in `create.before` and still
  see the tool set the real one?
- What do `session.moved` and the `session_move` tool do, including where later
  shells run?
- How do hot reload, `opencode reload`, 60-minute eviction, a server
  version-mismatch restart, and `session delete` affect Publisher Generations?
- What happens when the TUI quits, at `opencode service stop`, and when the
  server is killed?

[v1]: https://github.com/anomalyco/opencode/tree/v1.18.30
[v2]: https://github.com/anomalyco/opencode/tree/v2.0.21
[v1-opencode-pid]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/index.ts#L77
[v1-plugin-load]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/plugin/index.ts#L231
[v1-plugin-shared]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/plugin/shared.ts#L297
[v1-plugin-types]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/plugin/src/index.ts#L56-L80
[v1-shell-env]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/tool/shell.ts#L418
[v1-task]: https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/tool/task.ts#L100
[v200-plugin-context]: https://github.com/anomalyco/opencode/blob/v2.0.0/packages/plugin/src/promise/plugin.ts#L31
[v2018-shell-tool]: https://github.com/anomalyco/opencode/blob/v2.0.18/packages/core/src/tool/plugin/shell.ts
[v2-acp]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/commands/handlers/acp.ts#L14
[v2-bus-local]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/bus.ts#L726-L762
[v2-bus-node]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/bus.ts#L183
[v2-bus-routes]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/bus.ts#L205-L261
[v2-commands]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/commands/commands.ts
[v2-event]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/schema/src/event.ts
[v2-execution-events]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/schema/src/session-event.ts#L242-L262
[v2-host-subscribe]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/plugin/host.ts#L256
[v2-location-activity]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/location-activity.ts#L25-L81
[v2-migrate-plugins]: https://github.com/anomalyco/opencode/blob/v2.0.21/services/www/src/docs/content/migrate-v1.mdx#L555
[v2-module]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/plugin/module.ts#L111
[v2-plugin-adapter]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/plugin/src/promise/adapter.ts#L45-L53
[v2-plugin-context]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/plugin/src/promise/plugin.ts#L39-L43
[v2-plugin-guide-v1]: https://github.com/anomalyco/opencode/blob/v2.0.21/services/www/src/docs/content/build/plugins/index.mdx#L1716-L1719
[v2-plugin-source]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/plugin/src/source.ts
[v2-projector]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/session/projector.ts#L671-L673
[v2-retry-event]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/schema/src/session-event.ts#L572-L583
[v2-routing-test]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/test/bus-session-routing.test.ts
[v2-server-chdir]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/server-process.ts#L55
[v2-service-command]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/services/service-config.ts#L122
[v2-service-contender]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/client/src/service-contender.ts#L19-L41
[v2-service-file]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/services/service-config.ts#L30-L33
[v2-session-create]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/session.ts#L254-L256
[v2-session-delete]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/commands/handlers/session/delete.ts
[v2-session-id]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/schema/src/session-id.ts
[v2-session-move-hint]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/opencode.ts#L75
[v2-session-move-tool]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/opencode.ts#L110
[v2-session-moved]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/schema/src/session-event.ts#L95
[v2-session-remove]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/session.ts#L355-L364
[v2-shell-background]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/shell.ts#L198
[v2-shell-create]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/shell.ts#L254-L275
[v2-shell-env-fallback]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/shell.ts#L259-L269
[v2-shell-spawn]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/shell.ts#L305
[v2-shell-tool-env]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/shell.ts#L200-L215
[v2-source-directory]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/plugin/source-directory.ts#L7
[v2-standalone]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/services/standalone.ts#L21
[v2-subagent]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/subagent.ts#L17
[v2-subagent-background]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool/plugin/subagent.ts#L44-L46
[v2-supervisor]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/plugin/supervisor.ts#L258
[v2-tool-hooks]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/core/src/tool.ts#L104-L137
[v2-tui-move]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/tui/src/component/prompt/index.tsx#L303
[v2-version-mismatch]: https://github.com/anomalyco/opencode/blob/v2.0.21/packages/cli/src/commands/handlers/default.ts#L44
