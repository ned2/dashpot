---
status: research
date: 2026-10-02
---

# OpenCode v2 hosting, plugin and identity experiment

The experiment for step 1 of [Issue #393](https://github.com/ned2/dashpot/issues/393)
measures how OpenCode **2.0.22** hosts Agent Sessions, plugin instances and
shells, before Dashpot's OpenCode integration is redesigned for v2. It
settles the inferences the
[OpenCode v2 research note](../research/opencode-v2-research.md) marked for
measurement, and corrects one of them: every plugin instance receives every
location's events, not only its own.

Dashpot is not involved. A throwaway v2 plugin records what each plugin
instance is given and sees, the shells the fixture model runs report their
environment and ancestry, and the runner records OpenCode's server event
stream and the fixture's processes. This is evidence for the design steps of
#393, not an accepted ADR, and changes nothing in Dashpot.

## Reproduce

The retained experiment uses Node built-ins, Git, `script` from util-linux,
and two OpenCode 2.0.x binaries: the pinned **2.0.22** and an older 2.0.x
release, here **2.0.21**, for the version-mismatch scenario. The runner
rejects another pinned version. No model credentials or external model
service are needed: a deterministic loopback OpenAI-compatible provider
returns tool calls to the real OpenCode execution loop.

The binaries come from the npm platform package, for example:

```bash
npm install --prefix /tmp/oc2022 @opencode/cli@2.0.22
npm install --prefix /tmp/oc2021 @opencode/cli@2.0.21
```

The runner refuses to start below a harness session, because every client it
starts would then have that harness as an ancestor. From the assigned Dashpot
checkout, detach it with `setsid -f`:

```bash
setsid -f node scripts/experiments/opencode-393/run.mjs \
  /tmp/oc2022/node_modules/@opencode/cli-linux-x64/bin/opencode \
  /tmp/oc2021/node_modules/@opencode/cli-linux-x64/bin/opencode > run.log 2>&1
SPIKE_SCENARIOS=idle SPIKE_IDLE_MINUTES=64 setsid -f node scripts/experiments/opencode-393/run.mjs \
  /tmp/oc2022/node_modules/@opencode/cli-linux-x64/bin/opencode \
  /tmp/oc2021/node_modules/@opencode/cli-linux-x64/bin/opencode > idle.log 2>&1
node scripts/experiments/opencode-393/verify.mjs \
  /tmp/dashpot-opencode-393-SUFFIX/trace.jsonl /tmp/dashpot-opencode-393-IDLE/trace.jsonl
```

Replace the trace paths with the fixture roots each log prints. The first run
takes about a minute; the idle run takes about seventy-five minutes. The two
can run at once. The verifier needs no network.

- [Runner and trace receiver](../../scripts/experiments/opencode-393/run.mjs)
  create the fixture, serve the mock provider, drive TUI, `run`, CLI and HTTP
  API clients, and sample the fixture's processes.
- [Measurement plugin](../../scripts/experiments/opencode-393/plugin.mjs)
  records each instance's setup, its event subscription, its `create.before`
  shell hook, its tool hooks and its cleanup. It leaves out streamed output,
  a turn's steps, text and tool-input phases, usage, and configuration
  refreshes, to keep the trace small.
- [Shell reporter](../../scripts/experiments/opencode-393/command.mjs) and
  [ancestry reader](../../scripts/experiments/opencode-393/ancestry.mjs)
  report each shell's identity variables, location and process ancestry.
- [Independent trace verifier](../../scripts/experiments/opencode-393/verify.mjs)
  checks the claims below against both traces without importing the runner or
  the plugin.
- [Retained trace](measurements/issue-393-opencode-trace.jsonl): 1,324
  records from the successful run. The
  [retained idle trace](measurements/issue-393-opencode-idle-trace.jsonl)
  holds the idle-eviction run. The first record of each holds SHA-256 hashes
  of the five experimental source files. The fixture root, the directory
  holding it, the binaries' directories, the experiment directory, the
  Dashpot checkout and the operator's home directory appear as `$ROOT`,
  `$TMPDIR`, `$BINARY_DIR`, `$OLDER_BINARY_DIR`, `$EXPERIMENT`, `$CHECKOUT`
  and `$HOME`. In the main trace's process samples, the runner's own command
  line is cut at 300 characters inside the older binary's path, so its
  `/tmp/claude-1000` prefix is left unreplaced.

The runner creates a new `$TMPDIR/dashpot-opencode-393-*` root holding an
independent Git Repository and two linked Worktrees, `a` and `b`, which are
disposable fixtures, not Issue Worktrees. Every OpenCode process gets an
allowlisted environment with an isolated home, XDG directories and temporary
directory, with automatic updates, model catalog fetches and project
configuration disabled, and its own background service registration on a
private port, so the operator's own OpenCode service is never contacted. It
lays out three installs in the fixture home: the curl installer's
`~/.opencode/bin/opencode` with its `opencode2` shim, the npm package's
`opencode.exe` with `opencode` and `opencode2` links, and the older release.
It only signals processes whose environment names the fixture's
configuration directory, stops the fixture's service and clients, and records
that none remains. `SPIKE_REMOVE_FIXTURE=1` deletes the fixture root after
the run.

A first attempt showed why the isolation needs two more guards. OpenCode
2.0.21 requires a provider model's `capabilities.input` and `.output`, and
2.0.22 fills in defaults. With them omitted, 2.0.21 dropped the fixture model
and fell back to OpenCode Zen's free hosted model, which received one fixture
prompt and listings of the disposable fixture Repository. The runner now
declares full capabilities and points every fixture process's HTTP proxy at
a closed loopback port for anything but loopback. Its closing assertion that
every session the run created names the fixture model is weak, because the
runner creates each session with that model. The stronger evidence was
checked by hand: in both retained traces every prompted turn has a matching
request at the fixture provider, and every service record lists only the
private port.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-02 AEST |
| Dashpot base | `d07b36644bdc4317ef3c2a962d5ef1bccbdb35c8` |
| Pinned OpenCode | `@opencode/cli-linux-x64` 2.0.22, published 2026-10-02; `--version` = `opencode v2.0.22`; SHA-256 `32cf5aa0a69a650e36277e3315d189835ddc79fb9aa1d0aef5025be5af5ad122` |
| Older OpenCode | `@opencode/cli-linux-x64` 2.0.21; `--version` = `opencode v2.0.21`; SHA-256 `f916986543348d7953d8d43aa048516cdbc3f84f4d0dc9c0c5b9d1da3030cea7`, taken separately: the trace records only the pinned binary's hash |
| Plugin interface | v2 Promise API: a default export `{id, setup(ctx)}`, local `.js` plugin in the global `plugins/` directory |
| Operating system | Linux `7.0.0-34-generic`, x86-64 |
| Controller | Node `v24.18.0` |
| Hosting | The default shared service, `opencode serve --service`; `--standalone` |
| Clients | TUI under `script`, `opencode run`, `opencode session delete`, `opencode reload`, `opencode service stop` and `start`, and the HTTP API under `/api` |
| Provider | Loopback OpenAI-compatible streaming fixture, `aisdk:@ai-sdk/openai-compatible` |
| Flags | `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_MODELS_FETCH`, `OPENCODE_DISABLE_PROJECT_CONFIG`; snapshots, sharing, LSP and formatters off |

Not measured: macOS; the web, desktop and ACP clients; `--server <url>`;
workspaces (a location with a `workspaceID`); forks; retries; a failed
execution; background shells; and a TUI changing directory, which the source
says moves its session. The 60-minute idle eviction is measured once, on a
silent shell, a printing shell and an idle location; the debug eviction
route, `DELETE /api/debug/location`, stands in for it in the churn scenario.

## Scenario results

Receipts are the trace's `receipt` numbers.

| Scenario | Result | Trace records |
| --- | --- | --- |
| Shared service | A TUI started with a leaked `OPENCODE_SESSION_ID` spawns `$HOME/.opencode/bin/opencode serve --service`, a session leader in `$HOME`, as its child. Sessions in the main Worktree and in `a`, an `opencode run` in `b`, a user shell and a PTY all run in that one process. Quitting the TUI leaves the service running, reparented to pid 1, with no plugin cleanup. | 2–216 |
| Sub-agents | A synchronous child, a background child, and a background child whose parent is deleted while the child's shell runs. | 217–431 |
| Moves | The model's `opencode.session_move` tool to `a`, an API move to `b` while idle, and an API move back to the main Worktree during a five-second shell. | 432–583 |
| Plugin instance churn | A plugin file edit, `opencode reload`, a debug eviction while idle and while a shell runs, `opencode session delete`, an older `run` client, an older TUI that replaces the service, a newer TUI that replaces it back, `opencode service stop`, `service start`, and SIGKILL. | 584–1188 |
| `--standalone` | A `run --standalone` in `a` and a `--standalone` TUI in `b`. | 1189–1238 |
| Install layouts | `opencode run` through the npm `opencode` and `opencode2` links and the curl `opencode2` shim, each after `service stop`. | 1239–1318 |

## Findings

### The shared service and its plugin instances

- **One detached service per user.** The first client spawns
  `<install>/opencode serve --service` in its own session and process group,
  with working directory `$HOME`, as the client's child; once that client
  exits, the service is reparented to pid 1. Its registration, with a URL,
  password, version and pid, is the `$XDG_STATE_HOME/opencode/service.json`
  the runner reads. Inside the plugin, `process.argv` is
  `["bun", "/$bunfs/root/opencode", "serve", "--service"]`;
  `process.execPath` and `/proc/<pid>/cmdline` name the real binary.
- **Process names.** The runner lays out both installs as their 2.0.22
  sources do. The curl installer writes `~/.opencode/bin/opencode2` as a shim
  that runs `exec "$(dirname "$0")/opencode" "$@"`
  ([`install`](https://github.com/anomalyco/opencode/blob/v2.0.22/install#L374-L378)).
  The npm package `@opencode/cli` declares `opencode` and `opencode2` as
  `bin/opencode.exe`
  ([`publish.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/cli/script/publish.ts#L51-L72)),
  which its postinstall hard-links or copies from the platform package's
  binary
  ([`postinstall.mjs`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/cli/script/postinstall.mjs#L101-L115)),
  so no Node wrapper stays in the process tree; the installed 2.0.22
  package's `package.json` and `postinstall.mjs` match. Measured on those
  layouts, the curl install's service and clients are named `opencode`. The
  npm install's service is spawned from the real executable and is named
  `opencode.exe`, whichever link launched the client, while the client keeps
  its link's name, `opencode` or `opencode2`.
- **One plugin instance per location, `$HOME` included.** The service sets up
  an instance for a location when work first needs it: the main Worktree,
  `a`, `b`, and its own `$HOME`. `ctx.app` names the release: every setup
  record in the trace reads `{name: "cli", version: "2.0.22", channel:
  "latest"}`, or 2.0.21 under the older service.
- **Every instance receives every location's events.** From its setup on, an
  instance's `ctx.event.subscribe()` delivers every event of the whole
  service, whichever location it belongs to: each `session.created` reached
  every live instance of its process. The same holds under the 2.0.21
  service, whose `$HOME` instance receives the main Worktree's events. The
  research note's inference that subscriptions are filtered per location was
  wrong on both releases.
- **Which events name a location.** `session.created`, the shell events and a
  shell's `session.tool.progress` carry `location`. The activity events
  `session.execution.started`, `.succeeded` and `.interrupted`, and
  `session.deleted` and `worktree.resolved`, carry none, so an instance cannot
  tell from such an event alone which location's session it concerns.

### Shell identity

- **A model-driven shell** is a direct child of the service process, in a
  session and process group of its own. OpenCode sets `OPENCODE_SESSION_ID`
  to the shell's own session, `OPENCODE=1`, `AGENT=1` and
  `AI_AGENT=opencode`, after every plugin hook, so a leaked
  `OPENCODE_SESSION_ID` in the inherited environment is overridden.
  `OPENCODE_PID` is never set, and every shell in the trace has
  `OPENCODE_TERMINAL=1`.
- **Clearing, then overriding.** When the plugin deletes a leaked
  `OPENCODE_SESSION_ID` in `create.before`, the model-driven shell still gets
  its own session's ID: the `api-main-clear` shell inherited
  `ses_leakedfromanothersession00`, the hook cleared it (receipt 63), and the
  shell reported its real session (receipt 68). The verifier does not check
  this case.
- **The base environment.** A `run` client's own environment replaces the
  service's for its session's shells. A session created through the API, and
  every Sub-agent child, gets the service's environment instead, which is the
  environment of the client that spawned the service: here the TUI's, leaked
  `OPENCODE_SESSION_ID` included.
- **A user shell**, run through `/api/session/:id/shell`, which, per the
  source, the TUI's `!` uses, keeps an inherited `OPENCODE_SESSION_ID` and
  has none of `OPENCODE`, `AGENT` or `AI_AGENT`. The plugin's `create.before`
  hook runs for it, and deleting the variable there leaves the shell without
  one.
- **A PTY** opened through `/api/pty` is the service's child too, but no
  plugin hook runs for it, and it keeps an inherited `OPENCODE_SESSION_ID`.
- A shell runs under the plugin instance of its session's location: the
  instance whose `create.before` prepared it.

### Sub-agents

- A Sub-agent's shell has `OPENCODE_SESSION_ID` set to the child session.
  The child's `session.created` names its parent as `parentID`, and the
  child's model requests carry `x-opencode-parent-session-id`. The child's
  shell runs in its parent's directory, under that location's instance.
- **Background.** With `background: true`, the parent's turn ends at once,
  67 ms after the prompt in the trace, before the child's shell starts. The
  parent reports `session.execution.succeeded`, and when the child finishes, the
  parent gets a second execution, started and succeeded, of its own.
- **Deleting a running parent.** Deleting the parent interrupts the child with
  `session.execution.interrupted`, reason `user`, kills the child's shell
  before it reports its end, and publishes `session.deleted` for the child
  and then the parent (receipts 399 and 400). A `session.execution.started`
  for the deleted parent can follow, with no terminal event after it,
  although
  `/api/session/active` is then empty.

### Moves

- The model's move tool reaches tool hooks as `opencode_session_move`. The
  move applies when the step ends; the session's later shells run in the new
  location, under that location's instance.
- `session.moved` is delivered with the envelope's `location` naming the old
  location and `data.location.directory` the new one.
- A move requested through the API while the session is idle is an execution
  of its own: `started`, `moved`, `succeeded`.
- A move requested while a shell runs waits for the step boundary: the shell
  finishes in the old directory, then `session.moved` follows.

### Plugin instance lifecycle

- **Plugin file edit.** Every instance is cleaned up and every location is set
  up again at once.
- **`opencode reload`** prints `Configuration reloaded`, publishes
  `location.shutdown` for every location, cleans every instance up and sets
  each location up again.
- **Eviction of an idle location** cleans its instance up; the next work
  there sets a new one up.
- **Eviction of a busy location** publishes `location.shutdown` at once, but
  its instance is never cleaned up, not even when the service later exits.
  The running shell finishes; the next step sets a new instance up; the old
  one keeps receiving every event alongside its successor.
- **`opencode session delete`** goes through the service: no plugin loads in
  the CLI process, and the service publishes `session.deleted`.
- **`opencode service stop`** ends the service, which cleans up every
  instance, and removes the registration.
  **SIGKILL** runs no cleanup and leaves the registration, which
  `opencode service start` replaces with a new process.
- **Version mismatch.** An older `run` client reuses a newer service. An older
  TUI replaces it: the newer service shuts its locations down and exits, its
  running shell is killed before reporting its end, and the session is
  interrupted with reason `shutdown`. The older service then resumes that
  session in a new execution, reads the shared database without trouble, and
  its instances report `ctx.app.version` 2.0.21. A newer TUI replaces it back.

### `--standalone`

`run --standalone` and the `--standalone` TUI each start a private
`opencode serve --stdio --port 0` as the client's child. The plugin runs in
that process, so a shell's ancestry is shell, private server, client. The
plugin is cleaned up when the client exits. The private server shares the
session database with the shared service, whose session list includes the
standalone sessions.

### Idle eviction

The idle run starts three sessions and then leaves the service alone for 64
minutes: a quiet session in `a` whose turn ends at once, a session in `b`
whose shell would print nothing for 69 minutes, and a session in the main
Worktree whose shell would print a line every minute for 69 minutes.

- **Mechanism, from the 2.0.22 source.** The service keeps a 60-minute
  inactivity timer per location, which only a session event carrying that
  location renews, and checks it every minute. When it lapses, the service
  interrupts the location's active sessions with reason `inactivity`, waits
  for them to settle, and shuts the location down.
- **A running shell does not keep its location alive.** By the source, a
  shell publishes one `session.tool.progress`, with its location, when it
  starts, and writes its output to a file rather than to events. In the
  trace, the printing shell's progress events all came before the first idle
  minute.
- **Both busy sessions are interrupted.** 61 minutes after their shells
  started, the silent and the printing session were each interrupted with
  reason `inactivity`, their shells were killed before reporting an end, and
  their locations' instances were cleaned up. Neither session was active
  afterwards. Unlike the debug eviction of a busy location, this eviction
  cleans the instance up.
- **An idle location is evicted too.** `a` was shut down and its instance
  cleaned up 61 minutes after the quiet session's turn, in the same
  minute's check as the other two. The next prompt to that session set a new
  instance up in `a`, and its shell claimed the same session.
- **No fixed order.** The interruption, the location's shutdown and its
  instance's cleanup land within milliseconds of each other. The main
  Worktree's instance was cleaned up (receipt 131) and its event stream ended
  (receipt 137) without delivering its own session's
  `session.execution.interrupted`, which the other two instances received 4
  ms after that cleanup (receipts 138 and 139). An instance cannot count on
  seeing its own sessions' terminal events. The verifier checks only that
  each lands within the eviction's minute.

## Implications for #393

**Step 2, the identity and lifecycle ADR.**

- **Identity.** A model-driven shell's `OPENCODE_SESSION_ID`, with
  `OPENCODE=1`, is OpenCode's own claim and overrides a leaked one. A user
  shell and a PTY keep whatever they inherited, and `create.before` never
  sees a session ID, so the plugin cannot give a user shell its session's
  identity as the 1.18.30 plugin did for the TUI's `!`. The plugin should
  delete any inherited `OPENCODE_SESSION_ID` in `create.before` and add its
  Publisher Generation and service pid; Dashpot should accept a claim only
  with that generation marker and OpenCode's markers present, and refuse a
  PTY, which carries no marker.
- **Host Process.** The shared service is a non-exclusive Host Process, like
  the Codex managed daemon
  ([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)),
  but reparented to pid 1 and named `opencode` or `opencode.exe` depending on
  the install. No TUI is a shell's ancestor except under `--standalone`. A
  session can change Host Process without ending, when a client of another
  release replaces the service.
- **Activity.** The execution events replace `session.status`, with
  interruption reasons `user`, `shutdown` and `inactivity` observed. They
  carry no location, so a publisher must know each session's location from
  `session.created` and `session.moved`. `session.deleted` must end a
  session even if a stray `session.execution.started` follows it. OpenCode
  itself interrupts any session whose location has published no session event
  for an hour, so a long command, printing or not, has its session's
  execution interrupted with reason `inactivity`.
- **Sub-agents.** A child's shell claims the child, not its parent, and the
  plugin cannot mark it as delegated in `create.before`. Dashpot must resolve
  the child to its parent from `session.created`'s `parentID`. A background
  child runs after its parent's execution has succeeded, so holding the
  parent running needs the child's own execution events.
- **Location.** `session.moved` keeps the session ID and the Host Process and
  changes the directory where later shells run, which fits a Live Relocation
  ([ADR 0067](../adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
  ADR 0081's premise that a session never leaves its directory no longer
  holds.
- **Publisher Generations.** Since every instance sees every event, one
  instance per location publishing only its own location's sessions needs the
  plugin to filter, and to track session locations for the events that carry
  none. Cleanup is not a reliable retirement signal: an evicted busy instance
  is never cleaned up and keeps running, and SIGKILL runs nothing. Nor can
  an instance wait for its own sessions' ends: the idle eviction cleaned an
  instance up before its session's interruption reached it. The helper must
  prefer the newest generation of a process and location, fall back on the
  service's liveness, and not leave a retired generation's sessions shown as
  running.

**Step 3, the plugin.** The plugin is a `{id, setup}` default export using
`ctx.event.subscribe()`, `ctx.shell.hook("create.before")` and the cleanup
`setup` returns. It must deduplicate or filter the service-wide event stream,
and expect setup and cleanup to churn on configuration reloads, plugin edits
and evictions.

**Step 4, refusing v1.** `ctx.app.version` is available in `setup`, and a
mixed-version window is real: an older 2.0.x client replaces the service, so
the plugin can see a release other than the pinned one. `opencode --version`
prints `opencode v2.0.22`, where 1.18.30 printed a bare `1.18.30`
([identity and lifecycle spike](opencode-identity-lifecycle-spike.md#tested-configuration-and-evidence-boundary)).

**Step 5, the acceptance run.** The runner shapes measured here carry over:
the private service registration and port, Basic authentication with the
registration's password, the `x-opencode-directory` header, `POST
/api/session`, `/api/session/:id/prompt`,
`/api/experimental/session/:id/wait`, `/api/session/active`, the `/api/event`
stream, and the native `providers` and `permissions` configuration. Keep the
proxy guard, and replace the session-model assertion with checks that every
turn reaches the fixture provider and the service listens only on its
private port.

## Validation

The independent verifier checks 44 claims across the two retained traces: 36
against the 1,324-record main trace and 8 against the 180-record idle trace.
Each trace's recorded source hashes match the retained experimental files.
Both traces were also checked by hand for isolation: every prompted turn
reached the fixture provider, and every service listened only on its private
port. The complete pre-commit gate and the Python suite with coverage pass.
No dependency lockfile or production code changed.
