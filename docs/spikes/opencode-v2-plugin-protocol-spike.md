---
status: research
date: 2026-10-03
---

# OpenCode v2 plugin registry, envelope and recovery experiment

The experiment for [Issue #405](https://github.com/ned2/dashpot/issues/405)
measures what the rewritten OpenCode plugin relies on that
[ADR 0090](../adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md#consequences)
asks to be measured before it is relied on: a registry shared by a server's
plugin instances, the event id and durable envelope, `ctx.session.get` and
recovery on registration, forks, moves, and one module that both OpenCode
2.0.22 and 1.18.30 load. It follows the
[OpenCode v2 hosting, plugin and identity experiment](opencode-v2-spike.md),
whose findings it does not repeat.

Dashpot is not involved. A throwaway plugin in the rewritten plugin's shape
records its instances, the registry they find, every session event's
envelope, `ctx.session.get` answers and the shells it prepares; the shells
report their identity variables. This is evidence for #405, not an accepted
ADR.

## Reproduce

The runner needs Node built-ins, Git, and two OpenCode binaries: **2.0.22**
and **1.18.30**. Neither may be the operator's own installation: the runner
starts its own shared service on a private port, in disposable
configuration and state, and never contacts the operator's service. No model
credentials are needed: a loopback OpenAI-compatible provider returns tool
calls to OpenCode's real execution loop.

The runner refuses to start below a harness session. From the assigned
Dashpot checkout, detach it with `setsid -f`:

```bash
TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-405/run.mjs \
  <absolute opencode 2.0.22 binary> <absolute opencode 1.18.30 binary> > run.log 2>&1
node scripts/experiments/opencode-405/verify.mjs <fixture root>/trace.jsonl
```

The run takes about a minute and a half, and is done when its log prints
`All scenarios completed`. The verifier needs no network.

- [Runner and trace receiver](../../scripts/experiments/opencode-405/run.mjs)
  creates the fixture (a Repository with a linked Worktree, a second
  Repository and a plain directory), serves the mock provider, and drives
  the service's HTTP API and CLI.
- [Measurement plugin](../../scripts/experiments/opencode-405/plugin.mjs) is
  one default export carrying the v2 `{id, setup}` definition and a v1
  `server` entry.
- [Shell reporter](../../scripts/experiments/opencode-405/command.mjs) and
  [ancestry reader](../../scripts/experiments/opencode-405/ancestry.mjs)
  report each shell's identity variables, location and process ancestry.
- [Independent trace verifier](../../scripts/experiments/opencode-405/verify.mjs)
  checks each claim below against the trace.
- [Retained trace](measurements/issue-405-opencode-trace.jsonl): 303 records.
  The first holds SHA-256 hashes of both binaries and the five experimental
  source files; fixture and binary paths appear as `$ROOT`, `$BINARY_DIR`
  and `$V1_BINARY_DIR`.

## Tested configuration and evidence boundary

OpenCode 2.0.22 and 1.18.30 on Linux x64, Node 24.18.0, Dashpot at
`69c7d72`. The scenarios are `registry` (a plugin file edit and
`opencode reload`), `subagent`, `fork`, `moves`, `recovery` and `v1`. Only
the shared service is measured; moves are requested through the HTTP API,
not the TUI.

## Findings

Every claim below passed the verifier against the retained trace.

- **One registry per Host Process.** All twelve instances the service set up,
  across four locations, a plugin file edit and `opencode reload`, found the
  same registry on `globalThis` under one `Symbol.for` key, while each was
  its own module evaluation: module state is not shared, `globalThis` is.
- **A reload leaves no live instance.** `opencode reload` cleaned every
  instance up before setting any up, so the Host Process had none between. A
  plugin file edit set the new instances up first.
- **The envelope.** Every session event carried an `id` and a `durable`
  envelope whose `aggregateID` is its session, and whose `seq` rises with
  every event of that session. Each event id reached several instances and
  was admitted first exactly once.
- **Children and forks.** A Sub-agent's `session.created` names its parent as
  `parentID`, and `ctx.session.get` agrees. A fork publishes
  `session.forked`, not `session.created`; its `parentID` names its source,
  and `ctx.session.get` reads it as a root, with no `parentID`.
- **Moves.** `session.moved` names the old location in its envelope and the
  new one in `data.location`, within the Repository, to another Repository,
  to a plain directory and back. After a move, the session's shells run at
  the new location, under an instance set up there.
- **`ctx.session.get`.** Every answer came within 500 ms, at most 1 ms here.
  A deleted session, and a session ID never issued, reject with an error
  whose `_tag` and `name` are both `Session.NotFoundError`. The answer's
  shape, the session itself or one wrapped as `data`, is not told apart by
  the trace, so the plugin accepts either.
- **Shell identity.** `create.before` receives the command, its `cwd` and its
  `env`, and no session. Deleting `OPENCODE_SESSION_ID` and `OPENCODE` there
  leaves a model-driven shell with both set by OpenCode.
- **One module for both releases.** OpenCode 1.18.30 calls the module's v1
  `server` entry, whose shell variable reaches the shell. It also calls
  `setup`, with no `ctx.app` and without the v2 API, so `setup` must check
  `ctx.app.version` before using anything else.

## Not measured

- The TUI's change of directory, which the 2.0.22 source says publishes
  `session.moved`.
- A shell event as a source of a session's location and parent: since
  `create.before` names no session, the plugin learns a session's location
  from `session.created`, `session.forked` and `session.moved`, and failing
  those from `ctx.session.get`.
- A `--standalone` client's private server.

## Validation

`node scripts/experiments/opencode-405/verify.mjs
docs/spikes/measurements/issue-405-opencode-trace.jsonl` reports `ok` for
all fifteen claims.
