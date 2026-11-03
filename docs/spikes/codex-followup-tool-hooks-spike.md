---
status: research
date: 2026-11-03
---

# Codex follow-up tool hooks experiment

The experiment for step 1 of
[Issue #674](https://github.com/ned2/dashpot/issues/674) measures what a
lead's follow-up call publishes to hooks on the pinned **codex-cli
0.166.0**. It covers v2's `followup_task` and v1's `send_input`.
The [Codex Worker mail and follow-up across eviction experiment](codex-worker-mail-eviction-spike.md)
found on 0.162.0 that a worker's follow-up turn publishes `SubagentStop` but
no `SubagentStart`. So Dashpot, which adds a [Sub-agent](../domain-language.md)
to its live set only on `SubagentStart`, does not list the worker as working
while the follow-up runs. #674's decision is to infer that turn from the
lead's own tool hooks. This run answers what that inference can rest on. It
records no decision: the ADR on observation scope is step 2.

Here the **lead** is the root thread of a Codex Agent Session, and a
**worker** is one of its Sub-agents. The fixture threads only delegate, so
they are a skill's Lead and Workers in shape only. Where this document
capitalises Lead or Worker, it means the
[domain language's](../domain-language.md) roles under the
`dashpot-execute-issues` skill.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **source**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`. With `--codex-source`, the verifier checks each cited fact
  in a checkout of that commit, by matching its code in the cited file,
  not at the cited line;
- **trace only**: the retained trace shows it, but the verifier does not
  check it. Every timing is this run's single sample;
- **inference**: what follows for step 2, which neither the trace nor the
  source states.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| 1. Does a lead's `followup_task` fire `PreToolUse` and `PostToolUse` on the lead? With what payload? | `PreToolUse` fires for every call; `PostToolUse` fires only for a call that succeeded. Both carry `tool_name` `collaborationfollowup_task`, the lead's `session_id`, the model's call ID as `tool_use_id`, and no `agent_id`. `tool_input` has the keys `target` and `message`. `target` is the free string the lead wrote: an absolute agent path (`/root/worker_a`), a path relative to the lead (`worker_a`), or the worker's thread ID. A successful call's `tool_response` is the empty string. | measured; source for the name |
| 2. Does the target map to the `agent_id` Dashpot keys Sub-agents by? Also for a worker restored after eviction? | A thread-ID target is the worker's `agent_id`, character for character. A path target is not, and no hook payload pairs a path with an ID. The pairing is in the worker's transcript: `SubagentStart`'s `transcript_path` and `SubagentStop`'s `agent_transcript_path` name a file whose first line, Codex's session metadata, holds the worker's thread ID and `thread_spawn.agent_path`. A relative target resolves to `<lead's path>/<target>`, the lead's path being `/root`. The worker keeps its `agent_id` and its path after a local eviction, and after an app-server restart restored it from disk. | measured; source for the resolution |
| 3. How is a failed `followup_task` closed? | It is not closed by any hook. Each failure fired `PreToolUse`, and no hook of that call or of its target followed: an unknown path, an unknown thread ID, and a follow-up to an evicted worker while the only worker turn was taken (`agent thread limit reached`). `PostToolUse` runs only for a successful call. The failure reaches only the lead's model, as the tool's reply text. | measured; source |
| 4. The same for v1 `send_input`? | The same pattern. `tool_name` is `multi_agent_v1send_input`, and `tool_input` has the keys `target` and `message`. The target must be a thread ID, the worker's `agent_id`. On success, `PostToolUse` carries a JSON `tool_response` with the key `submission_id`. An unknown ID, a target that is not an ID, and a worker the lead closed each fired `PreToolUse` alone. | measured; source for the ID-only target |
| 5. Is a follow-up turn still missing its `SubagentStart`? | Yes, as [#664](https://github.com/ned2/dashpot/issues/664) found on 0.162.0. Every v2 follow-up turn, to a resident, an evicted and a restored worker, and v1's `send_input` turn, published one `SubagentStop` and no `SubagentStart`. A v1 worker's turn does publish a `UserPromptSubmit` carrying its `agent_id`; a v2 worker's turn publishes none. | measured |
| 6. Does a matcher on the tool name select those calls alone? | Only on the flattened name. The exact matchers `followup_task` and `send_input` selected nothing. `collaborationfollowup_task` and `multi_agent_v1send_input` each selected every hook of their tool and nothing else. The regular expression `followup_task$\|send_input$` selected both tools and nothing else. | measured; source |

Whether this is the decision's fallback case depends on the target's form.
A thread-ID target, and every v1 target, is the worker's `agent_id`, an
identity Dashpot resolves as it stands. A path target is not. The v2 Lead of
Dashpot's
[execute-issues skill](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md)
addresses its Workers by path. The hook payloads carry no identity for those
follow-ups that Dashpot can resolve. They resolve only by joining the path
to the `session_meta` line of the worker's transcript. If step 2 does not
accept reading that line, path-addressed follow-ups are the fallback case.
Separately, the decision's closing rule does not hold: no hook reports a
failed call.

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
It starts no daemon and needs no credentials: a loopback model stands in for
the Responses API. Run the runner detached, from outside any harness, so
that its refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-674/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-674/verify.mjs /var/tmp/dashpot-codex-674-SUFFIX/trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes about four minutes.

- [Runner](../../scripts/experiments/codex-674/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. Its fixture root is a fresh directory under
    `/var/tmp`, outside every Dashpot Project and outside the shared
    `/tmp/codex-daemon-<uid>/`, which it only counts. Codex gets an isolated
    `HOME`, `CODEX_HOME`, XDG directories and `TMPDIR`, and runs as `codex`
    through a symlink on a fixture-local `PATH`. Each lead runs in a
    `codex app-server` over stdio. The fixture daemon's settings turn its
    updater off, though no scenario starts the daemon.
  - **Hooks.** Every lifecycle event that `dashpot integrate codex`
    subscribes goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`. `PreToolUse` and `PostToolUse` are each
    subscribed once without a matcher, and once for each candidate matcher.
    Those are recorded only. Every hook is trusted through the `hooks/list`
    ledger.
  - **Model.** A loopback Responses API follows a fixed plan for each
    prompt or worker task. Two copies of a bundled model declare the
    multi-agent version: `fixture-v2` gives the v2 `collaboration` tools,
    and `fixture-v1` the v1 `multi_agent_v1` tools without tool search.
  - **Scenarios.** The v2 lead runs with `agents.max_threads` 1, which keeps
    one worker loaded and one worker turn running.
    - `v2-spawn` spawns worker A at `worker_a`.
    - `v2-path`, `v2-relative` and `v2-id` follow A up by absolute path,
      relative path and thread ID.
    - `v2-evict` spawns worker B, which evicts finished A.
    - `v2-evicted` follows up evicted A, which reloads it.
    - `v2-limit` follows A up with a five-second command, then follows up
      evicted B while A runs, into the running-turn limit. It then follows
      up A again, mid-turn.
    - `v2-unknown` follows up `/root/nobody` and a random UUID.
    - `v2-restart` stops the app-server and resumes the lead in a new one.
      `v2-restored` then follows up B, which is on disk only.
    - The v1 lead spawns worker V (`v1-spawn`) and resumes it with
      `send_input` (`v1-send`).
    - `v1-unknown` sends to an unknown UUID and to `worker_v`, which is not
      an ID.
    - `v1-closed` closes V, then sends to it.
  - **Records.** The trace holds payload keys, the values of identity
    fields only (IDs, tool names, targets, agent paths), and the shape of
    each tool's input and response. It also holds Codex's reply text to the
    lead, each worker shell's `CODEX_*` environment, the first line of each
    transcript a hook names, and the loaded threads. It holds no prompt and
    no message: a worker's final message, which `wait_agent` and
    `list_agents` relay, appears as `<worker reply>`.
- [Independent trace verifier](../../scripts/experiments/codex-674/verify.mjs)
  checks every **measured** claim below against the trace, without
  importing the runner or Dashpot. It also checks the runner's sources
  against the hashes the trace records, and with `--strict` Dashpot's
  session modules too.
- [Retained trace](measurements/issue-674-codex-trace.jsonl) is the
  complete metadata stream of the successful run: 522 records. The fixture
  root appears as `$ROOT` and the home directory as `~`.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-03 AEDT |
| Dashpot base | `06df76a40cfd957ccb5210462569264632483123`, with the runner uncommitted |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, as `codex app-server` over stdio |
| Controller | Node `v24.18.0` |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |
| Models | `fixture-v2` (catalog v2) and `fixture-v1` (catalog v1), served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The run
  measures what Codex does with those calls, not whether a real model makes
  them.
- **Hosting mode.** Every lead runs in an app-server over stdio. A managed
  daemon, a terminal client's in-process server and `codex exec` host the
  same core, but are not measured here.
- **Running-turn limit.** The limit was met by following up an evicted
  worker while the only worker turn was taken. With every worker resident,
  `max_threads` above one, or a spawn rather than a follow-up meeting the
  limit, the refusal is not measured.
- **Nesting.** Every worker is a direct child of a root lead at `/root`. A
  follow-up from a worker to its own child, whose relative targets resolve
  against that worker's path, is source only.
- **Platforms.** macOS, other releases and real models are unmeasured.

## 1. The lead's `followup_task` hooks

| Claim | Basis |
| --- | --- |
| Each of the ten `followup_task` calls fired `PreToolUse` once on the lead, under its `session_id`, with no `agent_id`. | measured |
| The hook's `tool_name` is `collaborationfollowup_task`: the v2 namespace `collaboration` and the name, with nothing between. Codex flattens a namespaced tool's name this way at the hook boundary ([`core/src/tools/mod.rs#L50-L64`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/mod.rs#L50-L64), [`core/src/tools/registry.rs#L1077-L1086`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/registry.rs#L1077-L1086)). Only `spawn_agent` is an exception: its hook name is the bare `spawn_agent` both without a namespace and in `multi_agent_v1`, so v1's spawn hooks read `spawn_agent` while v2's read `collaborationspawn_agent`. | measured; source |
| `PreToolUse` carries the keys `session_id`, `turn_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `tool_name`, `tool_input` and `tool_use_id`. `PostToolUse` adds `tool_response`. | measured |
| `tool_input` is an object with the keys `target` and `message`. `target` is the string the model wrote, unchanged, whatever form it took. | measured |
| `tool_use_id` is the model's call ID, the same on `PreToolUse` and `PostToolUse`, so the two pair exactly. | measured |
| Each of the seven successful calls fired one `PostToolUse`, before the worker's turn ended, since the tool returns once the task is queued ([`core/src/tools/handlers/multi_agents_v2/message_tool.rs#L100`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_v2/message_tool.rs#L100)). Its `tool_response` is the empty string. | measured; source for the return |
| Each `PostToolUse`, of `followup_task` and of `send_input`, came 43 to 61 ms after its `PreToolUse`. | trace only |

## 2. From target to `agent_id`

| Claim | Basis |
| --- | --- |
| A worker's `SubagentStart` and `SubagentStop` carry its thread ID as `agent_id`, the field Dashpot keys a Sub-agent by ([`harnesses.py`](../../src/dashpot/sessions/harnesses.py#L95)). The worker's shell holds the same ID as `CODEX_THREAD_ID`. | measured |
| A target that parses as a thread ID is used as one, with no lookup. So `v2-id`'s target is A's `agent_id` exactly, and its follow-up ran in A ([`core/src/agent/control/api.rs#L49-L51`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/api.rs#L49-L51)). | measured; source |
| Any other target is an agent path. One starting with `/` is absolute; any other is appended to the caller's path. A root lead's path is `/root`, so `worker_a` names `/root/worker_a` ([`protocol/src/agent_path.rs#L59-L71`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/protocol/src/agent_path.rs#L59-L71), [`core/src/agent/control/target.rs#L45-L58`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/target.rs#L45-L58)). Both forms reached A. | measured; source |
| No hook payload pairs an agent path with a thread ID. `SubagentStart` carries `agent_id` and `agent_type`, but no path. The lead's `spawn_agent` `PostToolUse` returns `task_name` (`/root/worker_a`), but no ID. | measured |
| Every `agent_type` was `default`. | trace only |
| The pairing is in the worker's transcript. `SubagentStart`'s `transcript_path`, and `SubagentStop`'s `agent_transcript_path`, name the worker's rollout file, whose name contains its thread ID. Its first line is Codex's `session_meta`, which holds the thread ID as `id` and, under `source.subagent.thread_spawn`, the `agent_path` and the lead's thread as `parent_thread_id`. On `SubagentStop`, `transcript_path` names the lead's rollout instead. | measured |
| The ID and the path held across eviction. A, evicted by B and reloaded by `v2-evicted`'s follow-up, ran it with the same `CODEX_THREAD_ID`, and stopped with the same `agent_id`. B, unloaded when the app-server stopped and restored from disk by `v2-restored`'s follow-up after the lead resumed in a new app-server, did the same. | measured |

## 3. A failed `followup_task`

| Claim | Basis |
| --- | --- |
| No worker published a hook in `v2-unknown`, and in `v2-limit` only A did: B, the failed call's target, published none. | measured |
| `/root/nobody` fired `PreToolUse`, and no `PostToolUse`. The lead's reply was ``live agent path `/root/nobody` not found``. | measured |
| A random UUID fired `PreToolUse`, and no `PostToolUse`. The reply was `agent with id <uuid> not found`. | measured |
| A follow-up to evicted B, while A ran the only worker turn, fired `PreToolUse`, and no `PostToolUse`. The reply was `collab tool failed: agent thread limit reached`. B made no model request. | measured |
| `PostToolUse` runs only when the call succeeded: a tool error, or an output that reports failure, skips it ([`core/src/tools/registry.rs#L935-L954`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/registry.rs#L935-L954)). No hook of the call or of its target worker follows it; only the lead's own turn goes on. | measured; source |
| A follow-up to a worker already running a turn succeeds and joins that turn. In `v2-limit`, A's second follow-up fired `PreToolUse` and `PostToolUse` while A's first follow-up ran. A ran both tasks and published one `SubagentStop` for them. | measured |

## 4. v1 `send_input`

| Claim | Basis |
| --- | --- |
| `send_input` fired `PreToolUse` as `multi_agent_v1send_input`, with `tool_input` keys `target` and `message`. v1's tools sit in the `multi_agent_v1` namespace ([`core/src/tools/handlers/multi_agents_spec.rs#L14`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_spec.rs#L14)). | measured; source |
| Its target is a thread ID only ([`core/src/tools/handlers/multi_agents/send_input.rs#L49`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents/send_input.rs#L49)). V's ID was the `agent_id` its `spawn_agent` returned, the `agent_id` of its `SubagentStart`, and its shell's `CODEX_THREAD_ID`. | measured; source |
| The successful send fired `PostToolUse`, with a JSON `tool_response` whose one key is `submission_id`. V ran the task and published one `SubagentStop`. | measured |
| An unknown UUID (`agent with id <uuid> not found`), `worker_v` (`invalid agent id worker_v: …`) and V after `close_agent` (`agent with id <V> not found`) each fired `PreToolUse` and no `PostToolUse`. No worker published a hook in `v1-unknown` or `v1-closed`. | measured |

## 5. The follow-up turn's start

| Claim | Basis |
| --- | --- |
| The run's only `SubagentStart` events are the three spawns: A in `v2-spawn`, B in `v2-evict` and V in `v1-spawn`. | measured |
| A's follow-ups in `v2-path`, `v2-relative`, `v2-id`, `v2-evicted` and `v2-limit`, B's in `v2-restored` and V's in `v1-send` each published one `SubagentStop`, and no `SubagentStart`. | measured |
| A v1 worker's turns, the spawned one and the one `send_input` started, each published a `UserPromptSubmit` carrying its `agent_id` and `agent_type`. No v2 worker turn published one. | measured |
| A worker's own tool calls fire `PreToolUse` and `PostToolUse` with its `agent_id`, under the lead's `session_id`. | measured |

## 6. Matchers

| Claim | Basis |
| --- | --- |
| A matcher of letters, digits, `_` and `\|` alone is a set of exact names; anything else is an unanchored regular expression, and an empty matcher or `*` matches every tool ([`hooks/src/engine/matcher.rs#L12-L39`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/hooks/src/engine/matcher.rs#L12-L39)). | source |
| The exact matchers `followup_task` and `send_input` selected no hook. The matcher compares the flattened name. | measured |
| `collaborationfollowup_task` selected each of the 17 hooks of that tool, and nothing else. `multi_agent_v1send_input` selected each of its 5, and nothing else. | measured |
| `followup_task$\|send_input$` selected all 22, and nothing else. | measured |
| Without a matcher, the same events also ran for every other tool call: the workers' shell commands and the leads' `spawn_agent`, `wait_agent`, `list_agents` and `close_agent`. | measured |

## Implications for step 2

These are inferences for the ADR and the implementation, not measurements.

- **Close on success, not on failure.** The decision counts the Worker as
  working from the lead's `PreToolUse` until its `SubagentStop`, "or until
  `PostToolUse` reports a failed call". No hook reports a failed call, so
  that rule would leave every failed follow-up working for good. Two
  alternatives fit what was measured:
  - start the Worker's working span on the successful `PostToolUse`, which
    fires only for an accepted task and before the worker's turn ends;
  - or start it on `PreToolUse` and drop it when no `PostToolUse` with the
    same `tool_use_id` follows. That needs a timeout, since nothing marks the
    failure.

  The ordering of `PostToolUse` before `SubagentStop` is this run's
  measurement, about 50 ms against a turn that waits on a model request; the
  source does not promise it. An end rule that ignores a `SubagentStop`
  arriving before the `PostToolUse` it would close is left to step 2.
- **A path needs the spawn's path.** The execute-issues skill's v2 Lead
  addresses Workers by path. Resolving that path to an `agent_id` needs the
  `agent_path` from the worker's `session_meta`, read through the
  `SubagentStart` transcript, and the lead's own path for a relative
  target. Whether Dashpot reads that first line is part of the
  observation-scope ADR.
- **A follow-up that joins a running turn.** It is accepted, and Codex
  publishes one `SubagentStop` for the turn. A span started by its
  `PostToolUse` ends at that stop, which is when the worker stops working.
- **Subscription.** If step 2 infers the follow-up from the lead's tool
  hooks, the subscription would be `PostToolUse`, or `PreToolUse` and
  `PostToolUse`, with the matcher
  `collaborationfollowup_task|multi_agent_v1send_input`, an exact set. The
  bare names select nothing. A future release that renames the
  namespace would silently stop matching: the regular expression
  `followup_task$|send_input$` survives a namespace rename, at the cost of
  being unanchored at the front.
- **v1 needs no new event to start.** A v1 worker's turn publishes a
  child-scoped `UserPromptSubmit`. Dashpot could take that as the start of
  the turn, though whether it should is step 2's question. v2 has no such
  event.

## Validation

The retained trace passed the independent verifier with `--strict` and
`--codex-source` at a `rust-v0.166.0` checkout: 19 claims against 522
records. Every script and Dashpot module the trace names matched the hash
the run recorded. The verifier checks only the form of the binary's
SHA-256; the value above is the one the trace records. Every lifecycle event
reached Dashpot's publisher, which exited 0 with nothing on stderr. The
shared `/tmp/codex-daemon-<uid>/` gained and lost no entry during the run.
