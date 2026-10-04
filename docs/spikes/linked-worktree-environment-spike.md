---
status: research
date: 2026-10-05
---

# Linked Worktree environment experiment

The experiment for [Issue #274](https://github.com/ned2/dashpot/issues/274)
measures which environment an agent's commands run with when its Agent
Session works in a linked Worktree. The Worktree Root lies outside the main
checkout (by default it is its sibling), so a direnv `.envrc` in the main checkout, the usual home of a
`GH_TOKEN`, does not apply there. Codex's managed daemon and OpenCode's
shared service run an agent's commands themselves, so whether a client's
environment reaches those commands had to be measured, not assumed. The
findings feed
[Credentials in a linked Worktree](../installation.md#credentials-in-a-linked-worktree)
and the `dashpot-issue-work` skill's dispatch reference.

One runner, [`environment-274`](../../scripts/experiments/environment-274/),
ran direnv, Codex and OpenCode in one disposable fixture against loopback
model fixtures. It built every process's environment from scratch, with an
isolated home, XDG directories, `CODEX_HOME`, direnv allow list, OpenCode
service port and password, and the Codex daemon's and OpenCode's updaters
off. It was launched with `setsid -f` outside every harness process, as the
[agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires, and
ran each pinned release read-only through a fixture-local symlink. Codex
runs its managed daemon from its own copy of the release in the fixture's
`CODEX_HOME`; the trace hashes each daemon's executable, and it matches the
pinned binary. The only
environment values it set are synthetic labels in `DASHPOT_274_MARKER` and
`DASHPOT_274_TOKEN`; the second name contains `TOKEN`, as `GH_TOKEN` does,
to expose any filtering by name. The fixture's main checkout has an
`.envrc` that exports both as `checkout-envrc`.

Each fixture model answers its first request with a tool call that runs a
probe, [`command.mjs`](../../scripts/experiments/environment-274/command.mjs).
The probe reports the markers in its own environment, its working directory,
and its ancestry with each fixture ancestor's markers, so the trace shows
which process the command descends from and what that process had. The
runner also records each client's and each Host Process's markers. The
trace, [`issue-274-environment-trace.jsonl`](measurements/issue-274-environment-trace.jsonl),
is metadata only, with paths rewritten to placeholders: it records the two
markers and `DIRENV_DIR` from each fixture process, and each probe's
`CODEX_THREAD_ID` or `OPENCODE_SESSION_ID`, which identify its session.
Another process's environment is only matched against the fixture's
configuration directory, never recorded.
[`verify.mjs`](../../scripts/experiments/environment-274/verify.mjs) checks
every finding below against it.

In short:

- **direnv does not follow a session into a linked Worktree.** `direnv exec`
  there loads nothing, and a shell with direnv's hook unloads the main
  checkout's `.envrc` at its first prompt in a linked Worktree, however it
  got there. A Worktree Root `.envrc` that runs `source_env` on the main
  checkout's makes it load in a linked Worktree.
- **Codex 0.160.0's managed daemon runs every command with its own
  environment, fixed when it started.** A later client's environment never
  reaches a command, nor does `codex resume -C`; a daemon that a
  direnv-loaded terminal autostarted gives that environment to every later
  session.
- **OpenCode 2.0.22's shared service runs a session's commands with the
  environment of the client that last opened or continued it**, which the
  client sends to the service, not with the service's own. A moved session
  runs with the moving client's; a service restart drops what a client sent,
  for a session then prompted only through the HTTP API.
- **A standalone client of either harness** gives its commands its own
  environment.
- **Claude Code was not measured.**

## Tested configuration

| Component | Release |
| --- | --- |
| Codex CLI | 0.160.0, `x86_64-unknown-linux-musl`, retained under `~/.codex/packages/standalone/releases/` |
| OpenCode | 2.0.22, `~/.opencode/bin/opencode` |
| direnv | 2.37.1 |
| bash | 5.3.9 |
| Platform | Linux 7.0.0, Node 24.18.0 |

The trace's first record holds the SHA-256 of both harness binaries and of
the three runner sources. A terminal client runs under `script` so it has a
terminal; a shell probe is typed into `bash -i` the same way, standing in for
the terminal a launcher opens. The fixture's `.bashrc` installs direnv's bash
hook. Linked Worktrees `a` to `h` sit in the Worktree Root beside the main
checkout.

## Launch order

The parts run in this order, each scenario's probe finishing before the next
starts:

1. **Shell.** `direnv exec` in the main checkout and in Worktree `a`; a
   hooked and an unhooked `bash -i` started in `a` with the main checkout's
   environment; a hooked shell in the main checkout that `cd`s into `a`
   (probes at the main checkout, on the `cd`'s own line, and at the next
   prompt); a hooked shell started in `a`. Then the runner writes the
   Worktree Root `.envrc`, `source_env <main checkout>/.envrc`, allows it,
   and repeats `direnv exec`, a hooked shell, and a launcher-style
   `direnv exec <worktree> bash -i` in `a`. The Worktree Root `.envrc` stays
   in place for the harness parts.
2. **Codex.** A `--disable daemon_auto_start` terminal with the markers set,
   while no daemon runs. A plain terminal in the main checkout without the
   markers, which autostarts the daemon. With that daemon running: a
   terminal through `direnv exec` in `b`, a terminal with the markers set in
   `c`, and `codex resume <first thread> -C d` through `direnv exec`. The
   daemon stops; a terminal through `direnv exec` in `e` autostarts the next,
   followed by a terminal without markers in the main checkout and
   `codex resume <first thread> -C f` without markers. The daemon stops;
   `codex app-server daemon start` with the markers set, then a terminal
   without them in `g`. The daemon stops; `codex resume --disable
   daemon_auto_start <first thread> -C h` with the markers set.
3. **OpenCode.** `opencode run --standalone` with the markers set, while no
   service runs. A TUI in the main checkout without the markers, which
   starts the shared service. With that service running: `opencode run`
   through `direnv exec` in `b`; a prompt through the HTTP API to `b`'s
   session; a TUI through `direnv exec` in `c`; `opencode run --session
   <first>` through `direnv exec` from `d`; the same again, its model moving
   the first session to `e` with `session_move` before probing. The service
   stops; a TUI through `direnv exec` in `f` starts the next, followed by
   `opencode run` without markers in the main checkout, `opencode run
   --session <first>` without markers, and a session created and prompted
   only through the HTTP API in `h`. The service stops; `opencode service
   start` with the markers set, then `opencode run` without them in `g`, and
   a prompt through the HTTP API to `b`'s session.

## Findings

Every finding is measured, from the trace, unless marked as read from the
source.

### direnv in a linked Worktree

- `direnv exec` loads the main checkout's `.envrc` in the main checkout and
  nothing in a linked Worktree.
- A `bash -i` started in a linked Worktree with the main checkout's
  environment keeps it without direnv's hook (`--norc`) and loses it at the
  first prompt with the hook: the hook unloads what no `.envrc` in the
  current directory's ancestry provides.
- A hooked shell in the main checkout that runs `cd <worktree> && <command>`
  gives that command the environment; at the next prompt in the Worktree it
  is gone.
- With the Worktree Root `.envrc`, `direnv exec` in a linked Worktree loads
  it and then the main checkout's through `source_env`, and both a hooked
  shell there and a launcher-style `direnv exec <worktree> bash -i` have the
  markers, with `DIRENV_DIR` naming the Worktree Root.
- No agent's command in a linked Worktree loaded the Worktree Root `.envrc`
  itself, in either harness, though the fixture's `.bashrc` installs the
  hook: every agent's command that ran in a linked Worktree without the
  markers had no `DIRENV_DIR` either. An agent's command is not an
  interactive shell.

### Codex 0.160.0

- Each command descends from its Host Process and has exactly that
  process's markers: the managed daemon's when one runs, the terminal's for
  a terminal launched with `--disable daemon_auto_start` while none runs.
- The daemon a plain terminal autostarts is that terminal's child, with its
  environment. With a daemon started without the markers, no later client's
  markers reached a command: not from `direnv exec` in a linked Worktree, not
  set in the client's own environment, and not through `codex resume -C` into
  a linked Worktree, which ran the command there, on the resumed thread.
- A daemon autostarted by a terminal launched through `direnv exec` gave its
  markers to every later session's commands, including a terminal without
  them in the main checkout and a resume of an older thread into another
  Worktree.
- `codex app-server daemon start` gave its own markers to a later client's
  commands.
- A standalone resume, `codex resume --disable daemon_auto_start -C`, ran
  the resumed thread's commands with the resuming terminal's markers.

### OpenCode 2.0.22

- A `--standalone` client's commands run under its private server with the
  client's markers.
- The shared service the first TUI starts is that TUI's child, with its
  environment. Each command descends from the service process, yet has the
  markers of the CLI client that opened or continued its session, not the
  service's: the service without markers ran commands with them for
  `opencode run` and a TUI launched through `direnv exec`, and for
  `run --session` continuing the first session; the service with markers ran
  commands without them for `opencode run` and `run --session` launched
  without them.
- `run --session` from another directory leaves the session where it was;
  `session_move` moved it, and the next command ran in the destination with
  the moving client's markers.
- A prompt sent through the HTTP API, with no client, ran with the markers a
  client had given that session earlier. A session created and prompted only
  through the API ran with the service's own markers. After the service
  restarted with other markers, an API prompt to a session a direnv-launched
  client had opened ran with the new service's markers: the session's
  variables do not outlive the service.
- Read from the 2.0.22 bundle: a client of the shared service sends its whole
  `process.env`, less `OPENCODE_PASSWORD` and `OPENCODE_SERVER_PASSWORD`, as
  the session's variables with `PUT /api/session/:id/environment` when it
  opens or continues a session. The TUI does so for the session it shows,
  the source suggests, but the trace has a TUI only on a service without the
  markers, so a TUI without them on a service with them is not measured.

### Both harnesses

- The `TOKEN`-named marker always matched the plain one: neither harness
  filtered a variable by name.
- The run added one lock file to the shared `/tmp/codex-daemon-<uid>/`
  directory and removed nothing.

## Not measured

- Claude Code. Its commands run as children of its client process, so its
  hosting differs from both measured shared Host Processes.
- A TUI without the markers continuing a session on a service that has them.
- A Codex daemon restarted with `codex app-server daemon restart`, and a
  Codex thread run by a controller on the daemon.
- Any credential, `gh`, or a real `.envrc`: the markers stand in for a
  `GH_TOKEN` an `.envrc` exports.

## Reproduce

From a checkout of this Repository, outside every harness process, with a
private `TMPDIR` that has no `.envrc` above it (the runner refuses one):

```sh
TMPDIR=<private dir> setsid -f node scripts/experiments/environment-274/run.mjs \
  ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/codex \
  ~/.opencode/bin/opencode > environment-274.log 2>&1
```

It prints its fixture root and is done at `All scenarios completed`; the
fixture's `trace.jsonl` is checked with:

```sh
node scripts/experiments/environment-274/verify.mjs docs/spikes/measurements/issue-274-environment-trace.jsonl
```

The verifier also checks that the runner's sources match the hashes the
trace records and that the trace holds no absolute fixture or home path.
