---
status: research
date: 2026-11-02
---

# Codex root session departure experiment

The experiment for [Issue #681](https://github.com/ned2/dashpot/issues/681)
asks whether a root Codex Agent Session can leave its own Issue Worktree on
the pinned **codex-cli 0.166.0**, so that the Worktree becomes free for a
Cleanup the user requested. It lists every interface 0.166.0 offers for
changing a session's directory. It keeps a route the session can take
itself apart from one only a person or an external controller can take.
It also requalifies the user-operated `/cd` fallback, which the
[dispatch reference](../../src/dashpot/skills/dashpot-issue-work/references/dispatch.md)
last described at 0.154.0. Relocation driven by an external controller is
[#148](https://github.com/ned2/dashpot/issues/148)'s scope; this run measures
the controller's call only to show what the model cannot reach.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it. A
  timing is this run's single sample, which the verifier checks against a
  looser bound;
- **documented**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`;
- **inference**: concluded from the measured and documented facts, not
  observed;
- **unknown**: with the reason it is unknown.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Can a root session move itself? | No. None of the thirteen tools Codex offers a root thread changes the session's directory, no hook output can, and the session's own commands cannot reach the app-server that could. | measured; documented, `hooks/src/schema.rs`, `linux-sandbox/src/bwrap.rs` |
| What does change a session's directory? | Two things. A person's `/cd` forks a new session. An external controller's experimental `thread/settings/update` `cwd` keeps the same session. | measured; documented, `tui/src/app/working_directory.rs`, `app-server-protocol/src/protocol/common.rs` |
| Is `/cd` still the fallback the skill describes? | Yes, with three corrections. The fork's `SessionStart` now reports `source` `fork`, not `startup`. The old session stays live in the Worktree it left for about a minute. The client process never moves. | measured |
| Does `/cd` free the Issue Worktree for Cleanup? | Only once the old session ends, about 61 s after `/cd`, and only if the client's terminal was started outside the Worktree. A client started inside it keeps a `process` blocker until it exits. | measured |
| Does `thread/settings/update` free it? | Yes, once the next turn ends at the new directory. The update alone leaves the session placed where its last hook put it. | measured |
| Can the controller's update move a running turn? | No. Sent while a command of the turn runs, it is accepted, but the rest of that turn keeps the old directory and permissions. It applies from the next turn. | measured; documented, the `cwd` field's "for subsequent turns" in `app-server-protocol/src/protocol/v2/thread.rs` |
| Can a session request a move that takes effect after its turn ends? | No. Nothing the model holds requests a deferred move, and the controller's `thread/settings/update`, which does take effect from the next turn, is out of its reach. | measured; documented |
| What is missing upstream? | A same-session directory change that the model can request, the user approves, and that takes effect when the turn ends. The request to `openai/codex` is drafted but not filed, and [#681](https://github.com/ned2/dashpot/issues/681) stays open: recording the limitation does not complete it. | inference |
| Is there an authority and timing contract to record? | No. No route is adopted, so no ADR records one. The `/cd` fallback keeps the contract the skill already gives it: `work stop` before, `work start` in the fork. | inference |

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
Run the runner detached, from outside any harness, so that its refusal check
passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-681/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-681/verify.mjs /tmp/dashpot-codex-681-SUFFIX/trace.jsonl 0.166.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes about seven minutes, most of it the waits for an old session
to unload.

- [Runner](../../scripts/experiments/codex-681/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. It builds a disposable Dashpot Project under the
    temporary directory, with a linked `issue` Worktree beside the main
    one. Codex gets an isolated `HOME`, `CODEX_HOME`, XDG directories and
    `TMPDIR`. It runs as `codex` through a symlink on a fixture-local
    `PATH`. Its managed app-server daemon has its updater off.
  - **Sandbox.** `workspace-write` with no network and approval `never`.
    `exclude_slash_tmp` and `exclude_tmpdir_env_var` are set, so that the
    fixture's checkouts, which live under the temporary directory, are
    writable only as the session's workspace. Both checkouts are trusted.
  - **Hooks.** Every hook event that `dashpot integrate codex` subscribes
    goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`, trusted through the `hooks/list` ledger.
  - **Model.** A loopback Responses API stands in for the model. For each
    prompt it follows a fixed plan of `exec_command` calls to
    [`probe.mjs`](../../scripts/experiments/codex-681/probe.mjs). The probe
    runs inside the session's sandbox. It reports its directory, its
    thread, whether it may write in each checkout, and whether it can
    connect to the daemon's control socket. A connection that succeeded
    would be closed at once, with nothing sent; none did.
  - **Scenarios.**
    - `cd-standalone`: a terminal with `--disable daemon_auto_start` starts
      in the Issue Worktree with `-C`. After its first turn the person
      types `/cd` to the main Worktree, then a second prompt.
    - `cd-daemon`: the same on the managed daemon.
    - `cd-inside`: the same on the daemon, but with the terminal itself
      started inside the Issue Worktree, as a person's shell usually is.
    - `settings-daemon`: after a daemon-hosted first turn in the Issue
      Worktree, a controller on the daemon's socket sends
      `thread/settings/update` with the main Worktree as `cwd`, then the
      person sends a turn. In a third turn, while a held command runs, the
      controller sends the update back to the Issue Worktree. A fourth
      turn follows.
  - **Records.** It records every model request's thread, the tools
    offered, the fixture labels its input carries, and the probe report it
    received. It also records every hook, Dashpot's stored hook records,
    and `dashpot worktree check --json` of both Worktrees at each step.
- [Independent trace verifier](../../scripts/experiments/codex-681/verify.mjs)
  checks every **measured** claim below against the trace without importing
  the runner or Dashpot. It also checks the runner's sources, and with
  `--strict` Dashpot's session and Cleanup modules, against the hashes the
  trace records.
- [Retained trace](measurements/issue-681-codex-trace.jsonl) is the complete
  metadata stream of the successful run: 171 records. The fixture root
  appears as `$ROOT`, and the home directory as `~`. It holds no prompts
  beyond the fixture's labels.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-02 AEDT |
| Dashpot base | `25bc672ee37c00b3914ce71f713b033b1ea64c5b`, with the runner uncommitted |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, standalone and as a managed app-server daemon |
| Controller | Node `v24.18.0`, over the daemon's Unix socket |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |
| Model | `fixture`, a copy of a bundled catalog entry, served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The
  run lists the tools Codex offers and what they do, not whether a real
  model would find another way.
- **Network.** The sandbox ran with network off. There, seccomp refuses
  `connect` itself, which is the `EPERM` the probe saw. With
  `network_access` on, as the Arc's resume command sets, seccomp allows
  it. The daemon socket mask is then what keeps the control socket out of
  reach (documented, `linux-sandbox/src/seccomp.rs` and
  `append_daemon_socket_masks` in `linux-sandbox/src/bwrap.rs`; not
  measured).
- **Unsandboxed sessions.** A session running with `danger-full-access`,
  or with approval to run a command outside the sandbox, could reach the
  control socket. The run does not try it. That would be the model driving
  an experimental, masked control channel against its intent, which is no
  supported route.
- **Skill flow.** The mock model never runs the `dashpot-issue-work`
  skill, so the continuation flow, its `work` commands, and a refused,
  delayed or unknown outcome are outside this run. So are `/cd`'s
  refusals, which are documented only.
- **Platforms and clients.** macOS, where Codex sandboxes with Seatbelt,
  other releases, real models and `--remote` clients are unmeasured.

## 1. The interfaces

| Claim | Basis |
| --- | --- |
| Every root thread was offered the same thirteen tools: `apply_patch`, `create_goal`, `exec_command`, `get_goal`, `list_mcp_resource_templates`, `list_mcp_resources`, `read_mcp_resource`, `request_user_input`, `tool_search`, `update_goal`, `view_image`, `web_search` and `write_stdin`. None changes the session's directory. | measured |
| `exec_command`'s `workdir` sets one command's directory, not the session's. | documented, `core/src/tools/handlers/shell_spec.rs` |
| A hook can return a decision, context or updated tool input, but no directory: `cwd` appears only in hook inputs. | documented, `hooks/src/schema.rs` |
| Each user turn also made one auxiliary model request, on a thread id that published no hook, offered `apply_patch` alone. | measured |
| What that auxiliary request serves. | unknown: the fixture records no request content beyond its labels, and the run did not trace it in the source |
| `/cd` is a TUI command, typed by the person. It is refused while a turn is pending or running, so the model cannot issue it as part of its turn. | documented, `tui/src/chatwidget/slash_dispatch.rs` |
| `thread/settings/update` is an experimental app-server method. Its `cwd` overrides "the working directory for subsequent turns". | documented, `app-server-protocol/src/protocol/common.rs`, `app-server-protocol/src/protocol/v2/thread.rs` |
| A client must declare the `experimentalApi` capability at `initialize` to call an experimental method; the fixture's controller did. | documented, `experimental_api` in `app-server-protocol/src/protocol/v1.rs`, checked in `app-server/src/message_processor.rs`; the runner's `initialize` |
| `turn/start` takes a `cwd` too, overriding "the working directory for this turn and subsequent turns". It starts a turn, so it is a controller's call, not the model's. | documented, `app-server-protocol/src/protocol/v2/turn.rs` |
| The experimental `turn/settings/update` changes a running turn's reviewer, model, effort, summary and service tier, but takes no `cwd`: nothing moves a turn that has started. | documented, `app-server-protocol/src/protocol/v2/turn.rs` |
| Every one of these app-server methods is reached only through the daemon's control socket, or a client's own connection, which the model's commands cannot reach (below). | inference |
| `thread/resume`'s overrides are still ignored while the thread is running or has subscribers ("config overrides were provided and ignored while running"). | documented, `app-server/src/request_processors/thread_processor.rs` |
| None of the 0.166.0 command-line additions, `codex queue`, `codex agents` and `codex app-server proxy`, sets an existing thread's directory. `codex queue --resume` goes through the daemon and resumes an unloaded thread with no overrides. | documented, `cli/src/main.rs`, `tui/src/session_queue_commands.rs` |
| No sandboxed probe could reach the app-server, whether a daemon ran or not. The control socket was not visible, `connect` failed with `EPERM`, and the shared daemon directory could not be read (`EACCES`). | measured |
| The Linux sandbox masks every daemon socket directory after each bind that would expose it. Seccomp, with network off, denies `connect`. | documented, `append_daemon_socket_masks` in `linux-sandbox/src/bwrap.rs`, `linux-sandbox/src/daemon_mounts.rs`, `linux-sandbox/src/seccomp.rs` |
| Codex never changes its own process's working directory: the only `set_current_dir` calls in the source are in tests. | documented, `utils/absolute-path/src/lib.rs` |

## 2. `/cd`, requalified

| Claim | Basis |
| --- | --- |
| `/cd` forks. In every scenario the next turn ran on a new session id, whose `SessionStart` reported `source` `fork` and the destination as its `cwd`. Its first request carried the earlier turn's label, so the history moved with it. | measured |
| The fork's sandbox follows it. Before `/cd`, the Issue Worktree was writable and the main Worktree read-only (`EROFS`); after it, the reverse. | measured |
| Hook order: the fork publishes `SessionStart` at its first turn, followed by its `UserPromptSubmit` and `Stop`. The old session publishes nothing more until its `SessionEnd`. | measured |
| The old session is unsubscribed, not ended. It stayed live in the Issue Worktree, and Cleanup's `agent-session` blocker held it, until its `SessionEnd`, `reason` `other`, 61.2 s, 61.0 s and 61.1 s after `/cd`. Standalone and daemon-hosted clients behave alike. | measured; the unsubscribe documented, `tui/src/app/working_directory.rs` |
| A daemon-hosted fork ends about 60 s after its client exits (60.2 s twice); a standalone one ends with its client. | measured |
| With the terminal started outside the Worktree, the Issue Worktree was removable once the old session ended. | measured |
| With the terminal started inside it, Cleanup's `process` blocker named `script`, `sh` and `codex` before `/cd`, after the fork's turn, and after the old session ended. The Worktree became removable only once the client exited. | measured |
| `/cd` needs an idle primary session with no queued input, no active background terminal and no other running agent. It also needs saved conversation history, a trusted destination or the person's consent to trust it, and no unconfirmed named permission profile; through a remote app server, no named profile at all. It refuses a remote workspace or execution environment. | documented, `tui/src/app/working_directory.rs` |
| The skill's fallback contract still holds: the old run cannot follow a fork, so `work stop` first and `work start` in the new session. | inference |

## 3. The controller's `thread/settings/update`

| Claim | Basis |
| --- | --- |
| Sent while the thread was idle, the update returned `{}`. `thread/read` then gave the new `cwd`, the same id, and no fork. | measured |
| The terminal's next turn ran on the same session at the new directory. Its `UserPromptSubmit` hook named it, and its sandbox made that directory the writable one. No second `SessionStart` was published. | measured; the TUI following the update documented, `apply_thread_settings_cwd` in `tui/src/chatwidget/settings.rs` |
| Until that turn the Issue Worktree stayed blocked by the session's earlier hook record. After it, the Worktree was removable. | measured |
| Sent 3 s into a turn whose command was still running, the update also returned `{}`, and `thread/read` showed the thread `active` at its old `cwd`. That command and the turn's next one both ran at the old directory with the old write permission. The following turn ran at the new one, and the Worktree it left was blocked again. | measured |

## Implications for the skill

- **Leaving an Issue Worktree** stays a person's step: exiting the client,
  then `codex resume <session-id> -C <directory>`. `/cd` forks a new
  session rather than moving this one, and the skill keeps it to the
  dispatch handoff it already offered. The finish step says the model
  cannot move its own session.
- **`-C` and `/cd` move the session, not the client process.** A client
  started from a terminal inside the Worktree keeps it from Cleanup as a
  `process` blocker until it exits. The resume and fresh `-C` commands are
  best run from a terminal outside every Worktree the user may later
  remove.
- **After `/cd` the old session stays about a minute.** A Cleanup run at
  once still sees it.

The skill's dispatch and recovery references, the Arc skill's Codex
location note and the [agent sessions](../agent-sessions.md) Cleanup table
now say so.

## Implications for #148

An external controller can relocate a daemon-hosted Codex thread while
keeping its identity. `thread/settings/update` with `cwd` keeps the thread
id, and the next turn's hooks, sandbox and writable root follow it. A
running turn finishes where it started, and the method is experimental.

## Validation

The retained trace passed the independent verifier with `--strict` at the
run's base, `25bc672`: every script and Dashpot module it names matched the
hash the run recorded. The verifier checks only the form of the binary's
SHA-256; the value above is the one the trace records. After the run's
`daemon stop`, no fixture Codex process remained, the shared daemon
directory had gained and lost nothing, and every hook reached Dashpot's
publisher and exited 0.
