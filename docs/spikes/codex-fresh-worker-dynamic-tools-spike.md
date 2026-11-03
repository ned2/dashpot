---
status: research
date: 2026-11-03
---

# Codex fresh-Worker dynamic tools and delegation metadata experiment

The experiment for [Issue #666](https://github.com/ned2/dashpot/issues/666)
measures three app-server capabilities on the pinned **codex-cli 0.166.0**:

- a client-defined dynamic tool reaching a Worker started without the lead's
  history, behind the `multi_agent_v2_dynamic_tools` feature
  ([openai/codex#50082](https://github.com/openai/codex/pull/50082));
- the resolved model and reasoning effort in Sub-agent creation activity
  ([#51463](https://github.com/openai/codex/pull/51463));
- the turn lineage that ties a Worker's turn to the lead turn that issued it
  ([#51415](https://github.com/openai/codex/pull/51415)).

The Issue named 0.162.0. The maintainer moved it to 0.166.0, the release
`dashpot preflight codex` accepts. All three PRs, and
[#51329](https://github.com/openai/codex/pull/51329), which narrows
`fork_turns` to `none` and `all`, are ancestors of `rust-v0.166.0`. The
experiment is exploratory. It adds no observation adapter, claims no new
hook field, and changes no identity.

Here the **lead** is the root thread of a Codex Agent Session, and a
**Worker** is one of its [Sub-agents](../domain-language.md), started with
`spawn_agent`. A **fresh** Worker is started with `fork_turns: "none"`, and
a **full-history** Worker with `fork_turns: "all"`. The fixture threads only
delegate and call the tool, so they are a skill's Lead and Workers in shape
only. A **dynamic tool** is a function the app-server client declares in
`thread/start`'s experimental `dynamicTools`; Codex offers it to the model
and sends each call back to the client as an `item/tool/call` request.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **documented**: read from the source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, with paths under
  `codex-rs/`;
- **trace only**: the retained trace shows it, but the verifier does not
  check it;
- **unknown**: with the reason it is unknown.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Does a fresh Worker get the lead's dynamic tool with the flag off? | No. The tool is missing from its model requests. When the fixture model called it anyway, Codex answered `unsupported call: fixture_lookup` itself, and no request reached the client. | measured; documented, `fresh_child_history_and_tools` |
| With the flag on? | Yes. The fresh Worker was offered the tool, its call reached the client, and the client's result reached the Worker. | measured |
| Does a full-history Worker get it? | Yes, with the flag off as well as on. A fork inherits the tools recorded with the lead's history, and the flag does not apply to it. | measured; documented, `core/src/session/mod.rs` |
| Did the fresh Worker inherit the lead's conversation? | No. The lead's first prompt carried a sentinel. It was missing from every fresh Worker request, after follow-up, compaction and restart, and present in every full-history Worker request. | measured |
| Does the tool survive follow-up, compaction and resume? | Yes. A `followup_task` turn, a turn after the lead's compaction, and turns after an app-server restart all offered it, and every call reached the client. The resumed lead named no dynamic tool: Codex restored them from the rollout. Cold Workers reloaded on `followup_task` with the tool. | measured; documented, `core/src/session/session.rs` |
| Can a client compact a v2 Worker? | No. `thread/compact/start` on the Worker returned error `-32600`, `direct app-server input is not allowed for multi-agent v2 sub-agents`. The lead compacted normally. | measured; documented, `app-server/src/request_processors/thread_input.rs` |
| Who decides whether a call runs? | The client alone. No approval or other server request arrived under `approval_policy = "on-request"` and a read-only sandbox, and the dynamic tool handler names no approval or sandbox step. The request names the calling Worker's thread and turn, and a denial (`success: false`) reached the Worker as a failed call. | measured; documented, `core/src/tools/handlers/dynamic.rs` |
| Does creation activity carry the resolved model and effort? | Yes, on the `started` activity only. The fresh Worker, which asked for `low`, read `fixture-v2`/`low`. The full-history Worker, which asked for nothing, read `fixture-v2`/`medium`, the model's default, not the lead's unset effort. | measured; documented, `effective_spawn_config` |
| And other activity? | `interacted` and `completed` activity, and the `wait` tool's `collabAgentToolCall` item, carry both keys with `null` values. The protocol says the fields are absent from older records, so a reader treats a missing key and `null` alike. | measured for the nulls; older records documented |
| Is creation activity persisted? | Yes. `thread/read` on the live server, `thread/read` of the unloaded lead after a restart, and the lead's rollout all held the same values. | measured |
| How is a Worker's turn tied to the lead? | By turn lineage: its parent turn and root turn are the lead turn that issued the work, whether a spawn or a `followup_task`, before and after compaction and restart. Each lead turn, including the compaction turn, is its own root with no parent. | measured; documented, `core/src/thread_spawn.rs`, `message_tool.rs` |
| Is lineage an identity? | No. It names turns. The Worker's root moves to whichever lead turn issued its latest work. Its hooks still carry the lead's thread as `session_id`, the Agent Session Identity, and the Worker's own thread as `agent_id`. Nothing in lineage names an Issue. | measured |
| Does any of this reach Dashpot's hooks? | No. Hook payloads carry `model` but no reasoning effort, no parent or root turn, and no dynamic tool. As at 0.162.0, a Worker's follow-up turn publishes `SubagentStop` without `SubagentStart` ([#674](https://github.com/ned2/dashpot/issues/674)). | measured for the identity fields and the follow-up hooks; the absent keys trace only |

## Reproduce

The run needs Node 24 and the pinned Codex binary. It does not use
Dashpot's publisher. Run the runner detached, from outside any harness, so
that its refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-666/run.mjs <absolute path to the 0.166.0 codex binary> 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-666/verify.mjs <fixture root>/trace.jsonl
```

The runner prints the fixture root, a `dashpot-codex-666-` directory under
`$TMPDIR`; the trace is `trace.jsonl` inside it. A run takes under a
minute. Verify the retained trace with:

```bash
node scripts/experiments/codex-666/verify.mjs docs/spikes/measurements/issue-666-codex-trace.jsonl 0.166.0 --strict
```

- [Runner](../../scripts/experiments/codex-666/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. Codex gets an isolated `HOME`, `CODEX_HOME`, XDG
    directories and `TMPDIR`, and runs as `codex` through a symlink on a
    fixture-local `PATH`, with the daemon's updater off. The workspace is
    no Dashpot Project. Each phase runs `codex app-server` over stdio, with
    the feature set on its command line:
    `-c features.multi_agent_v2_dynamic_tools=<false|true>`.
  - **Hooks.** The events `dashpot integrate codex` subscribes go to a
    record-only hook, trusted through the `hooks/list` ledger. It keeps
    each payload's identity fields and key names.
  - **Tool.** Each lead is started with one dynamic tool, `fixture_lookup`,
    "Return a fixed marker for the given probe. Reads and changes nothing."
    The runner answers each call with `TOOLRESULT:<probe>`, and the probe
    `deny` with `success: false`.
  - **Model.** A loopback Responses API stands in for the model and follows
    a fixed plan for each prompt or Worker task. Its `fixture-v2` model, a
    copy of `gpt-5.5` whose `multi_agent_version` is `v2` and whose default
    effort is `medium`, gives each thread the v2 `collaboration` tools. It
    calls `fixture_lookup` even when a request does not offer it.
  - **Scenarios.**
    - `off` and `on`: a lead calls the tool, spawns `fresh` with
      `fork_turns: "none"` and `reasoning_effort: "low"`, and spawns
      `full` with `fork_turns: "all"`. Each Worker calls the tool.
    - In `on` only: the lead follows `fresh` up, and that turn calls the
      tool twice, denied and then allowed.
    - `compaction`: the runner compacts the lead and tries to compact
      `fresh`. The lead then follows `fresh` up again.
    - `resumed`: a new app-server reads all three threads unloaded,
      resumes the lead without naming any dynamic tool, and has it call
      the tool and follow up both Workers.
  - **Records.** For every model request it records whether the tool was
    offered, the fixture markers in input order, the latest tool output,
    and the lineage Codex sends in its client metadata and
    `x-codex-turn-metadata`. It also records every `item/tool/call` the
    client received and its answer, the app-server's turn and item
    notifications, `thread/read` of each thread, each rollout's creation
    metadata, turn attribution and Sub-agent activity, and every hook.
- [Independent trace verifier](../../scripts/experiments/codex-666/verify.mjs)
  checks every **measured** claim against the trace without importing the
  runner. It checks the runner's scripts against the hashes the trace
  records, and with `--strict` the hook example it read from the checkout
  too. It reads the runner's source only for what the trace records as an
  outcome: the effort each spawn asked for, and a resume call naming no
  dynamic tool. The verifier itself is not hashed, so it can change without
  a new run.
- [Retained trace](measurements/issue-666-codex-trace.jsonl) is the complete
  metadata stream of the successful run: 270 records. The fixture root
  appears as `$ROOT` and the home directory as `~`. It holds no prompts
  beyond the fixture's markers.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-03 AEDT |
| Dashpot base | `06df76a40cfd957ccb5210462569264632483123`, with the runner uncommitted |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, as `codex app-server` over stdio |
| Feature settings | `multi_agent = true`, `multi_agent_v2 = true`, `hooks = true`, `plugins = false`, `apps = false`; `multi_agent_v2_dynamic_tools` `false`, then `true` |
| Permissions | `approval_policy = "on-request"`, `sandbox_mode = "read-only"` |
| Controller | Node `v24.18.0` |
| Operating system | Linux `7.0.0-38-generic`, x86-64 |
| Model | `fixture-v2` (catalog v2), served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The run
  measures what Codex does with those calls, not whether a real model makes
  them.
- **Flag stability.** `multi_agent_v2_dynamic_tools` is `UnderDevelopment`
  and off by default at `rust-v0.166.0`
  ([`features/src/lib.rs#L1575-L1579`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/features/src/lib.rs#L1575-L1579)).
  Codex may change or remove it in any release, and `thread/start`'s
  `dynamicTools` is itself an experimental field. The measured behavior is
  this release's only.
- **Client-defined tools only.** The run measures one dynamic tool declared
  by the app-server client. MCP servers, connectors, apps and plugins have
  their own handlers and approval paths, were off or absent, and are not
  measured. Nothing here says what a Worker gets of them.
- **One client.** Each phase had one client connection, which received
  every call. Which connection receives a Worker's call when several are
  attached to the lead, and what happens when none is, is unknown.
- **Hosting mode.** Every thread ran in an app-server over stdio. A
  managed daemon and a terminal client host the same core, but a terminal
  declares no dynamic tools of its own and is not measured.
- **Platforms.** macOS, other releases and real models are unmeasured.

## 1. Dynamic tools by flag and fork mode

| Claim | Basis |
| --- | --- |
| With the flag off, the fresh Worker's requests did not offer `fixture_lookup`. Its call got `unsupported call: fixture_lookup` from Codex, and the client received no request from it. | measured |
| With the flag off, the full-history Worker was offered the tool. Its call reached the client naming the Worker's own thread and turn, and `TOOLRESULT:off-full` reached the Worker. | measured |
| With the flag on, both Workers were offered the tool, and each call and result went the same way. | measured |
| The lead was offered the tool and reached the client in every phase. | measured |
| A fresh v2 Worker copies its parent's dynamic tools only when the flag is on: `fresh_child_history_and_tools` returns an empty list otherwise, and a fork never calls it. | documented, [`core/src/agent/control/spawn.rs#L80-L98`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/spawn.rs#L80-L98), [`#L743-L752`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/spawn.rs#L743-L752), [`core/src/agent/host/spawn.rs#L125-L134`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/host/spawn.rs#L125-L134) |
| A fork takes the tools its forked history recorded, whatever the flag: "A fork records its initial catalog in the new thread's creation metadata." | documented, [`core/src/session/mod.rs#L849-L856`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/session/mod.rs#L849-L856) |
| The rollouts agree. The fresh Worker's creation metadata names no dynamic tool with the flag off and `fixture_lookup` with it on. Each full-history Worker's rollout holds two creation records, the lead's and its own, both naming the tool, and records the lead as the thread it forked from. | measured |
| `fork_turns` accepts `none` and `all`. A positive integer still parses, as full history, not a bounded window, and an omitted `fork_turns` means `all`. | documented, [`core/src/tools/handlers/multi_agents_v2/spawn.rs#L214-L239`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs#L214-L239) |

## 2. The fresh Worker's context

| Claim | Basis |
| --- | --- |
| The lead's first prompt in each phase carried `LEADSECRET:<phase>`. No fresh Worker request held it, in any of its four turns. Every full-history Worker request did. | measured |
| A fresh Worker's later turns held its own earlier turns: the follow-up's first request carried its first task and that task's tool result. | trace only |
| The lead's compaction summary replaced its earlier tool results, and its own prompts stayed, the sentinel among them. | trace only |

## 3. Follow-up, compaction and resume

| Claim | Basis |
| --- | --- |
| The fresh Worker's follow-up turn was offered the tool. Its first call was denied, `TOOLDENIED:deny` reached it, and the `dynamicToolCall` item completed with status `failed` and `success: false`. Its next call in the same turn succeeded. | measured |
| `thread/compact/start` on the lead ran as a turn of its own. It made one model request whose metadata's `request_kind` was `compaction`, and completed a `contextCompaction` item. The lead's rollout records one compaction. | measured |
| `thread/compact/start` on the fresh Worker was refused with `-32600`, `direct app-server input is not allowed for multi-agent v2 sub-agents`. The app-server refuses direct input, goals and queued input to a v2 Worker the same way. | measured; documented, [`app-server/src/request_processors/thread_input.rs#L8-L9`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server/src/request_processors/thread_input.rs#L8-L9) |
| After the lead's compaction, the lead and the fresh Worker's next follow-up were both offered the tool, and the Worker's call reached the client. | measured |
| A new app-server read the lead and both Workers as `notLoaded`. The lead, resumed without naming any dynamic tool, was offered the tool, and its call reached the new client. | measured |
| A resumed thread takes the dynamic tools its rollout recorded when the resume names none. | documented, [`core/src/session/session.rs#L1575-L1583`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/session/session.rs#L1575-L1583) |
| Each cold Worker reloaded on `followup_task` with the tool, and its call reached the new client. | measured |
| No approval or other server request arrived in the run. | measured |
| The dynamic tool handler sends the call to the client and waits for its answer. It names no approval or sandbox step. | documented, [`core/src/tools/handlers/dynamic.rs#L114-L183`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/dynamic.rs#L114-L183) |

So the permission boundary of a dynamic tool is the client's own code. The
client sees which Worker thread and turn called, and can refuse. Codex did
not ask the user (measured), and its handler applies no sandbox to the call
(documented). The run denied a call only in the first follow-up; it did not
repeat the denial after compaction or the restart. A client that
declares a tool on a lead thus hands it to every full-history Worker of
that lead, and with the flag on to every fresh Worker too.

## 4. Creation activity

| Claim | Basis |
| --- | --- |
| The `started` activity for `fresh` read `model: "fixture-v2"`, `reasoningEffort: "low"`, the effort the spawn asked for. For `full`, which asked for none, it read `"medium"`, the catalog default. The lead's own effort was unset. | measured |
| `started` takes both values from the spawned thread's configuration, filling an unset effort from the model's default. | documented, [`core/src/tools/handlers/multi_agents_v2/spawn.rs#L162-L174`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs#L162-L174), [`core/src/agent/control/spawn.rs#L43-L56`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/spawn.rs#L43-L56) |
| Each Worker turn's own turn context in its rollout records the same resolved effort; the lead's records none. | measured |
| `interacted` (a `followup_task`) and `completed` activity carry `model` and `reasoningEffort` as keys with `null` values. So does the `wait` tool's `collabAgentToolCall` item. A v2 spawn publishes no `collabAgentToolCall` item. | measured for the nulls; the missing spawn item trace only |
| `interacted` and `completed` set both to `None` in the source. The protocol documents `model` as "absent from older records and other activities". | documented, [`message_tool.rs#L88-L95`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_v2/message_tool.rs#L88-L95), [`core/src/agent/control/completion.rs#L74-L79`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/completion.rs#L74-L79), [`app-server-protocol/src/protocol/v2/item.rs#L460-L464`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/item.rs#L460-L464) |
| The activity lands in the lead's turn that issued the work, including `completed`. | trace only |
| `thread/read` on the live server, `thread/read` of the unloaded leads after a restart, and each lead's rollout (`item_completed`, `SubAgentActivity`, in snake case) held the same kinds, paths and values. The rollout's records carry the `model` and `reasoning_effort` keys even when `null`. | measured |

A reader of this field treats `null` and a missing key alike, and reads the
creation values from `started` alone.

## 5. Turn lineage and identity

| Claim | Basis |
| --- | --- |
| Every Worker turn's model requests carried `parent_turn_id` and `root_turn_id` equal to the lead turn that issued its work, in the client metadata and in `x-codex-turn-metadata`, with the lead's thread as `session_id` and `parent_thread_id`. This held for both spawns and for follow-ups after compaction and restart. | measured |
| The Worker's `turn/started` notification gave the same lead turn as `rootTurnId`. The wire `Turn` carries no parent turn. | measured; documented, [`app-server-protocol/src/protocol/v2/thread_data.rs#L384-L393`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/thread_data.rs#L384-L393) |
| The Worker's rollout `task_started` record held `root_turn_id` and a `turn_attribution` whose `parent_turn_id` and `root_turn_id` are that lead turn and whose `initiating_agent_path` is `/root`. `turn_trigger` was `null`. | measured for the parent, root and initiator; `turn_trigger` trace only |
| Each lead turn was its own root, with no parent turn in its requests or its attribution. The compaction turn was too, and its `task_started` record carries no `turn_attribution` at all. | measured |
| A spawn sets the Worker's parent turn to the issuing turn and inherits its root. A `followup_task` does the same, and mail queued with `send_message` clears the parent. | documented, [`core/src/thread_spawn.rs#L200-L204`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/thread_spawn.rs#L200-L204), [`message_tool.rs#L72-L76`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/handlers/multi_agents_v2/message_tool.rs#L72-L76), [`core/src/agent/control/api.rs#L155-L158`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/api.rs#L155-L158) |
| `turn/start` takes `parentTurnId` and `rootTurnId` from a client starting work on behalf of another turn. | documented, [`app-server-protocol/src/protocol/v2/turn.rs#L186-L200`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/turn.rs#L186-L200) |
| Every Worker hook carried the lead's thread as `session_id`, the Worker's thread as `agent_id`, and the Worker's own turn as `turn_id`. The first turn published `SubagentStart` and `SubagentStop`; each follow-up turn only `SubagentStop`. | measured |
| The lead published `SessionStart` with `source` `startup`, then `compact` after its compaction, then `resume` on the new server. No hook ran with any `CODEX_` variable. | measured |
| No hook payload holds a reasoning effort, a parent or root turn, or a dynamic tool. `SubagentStart` holds `model`. | trace only |

Lineage answers "which lead turn caused this Worker turn". It does not
answer which Agent Session or Issue the work belongs to. The Agent Session
Identity stays the lead's thread, which hooks already carry as
`session_id`, and Issue Identity comes from the Issue Binding. A Worker's
root turn changes with every follow-up, so it can name neither.

## Recommendations

| Capability | Recommendation | Flag stability | Unknowns |
| --- | --- | --- | --- |
| Dynamic tools for fresh Workers | No implementation Issue. Dashpot does not start Codex threads or declare dynamic tools: it observes them through hooks. A use would require Dashpot to host the lead as an app-server client, which no design proposes. If one does, the tool's only permission boundary is that client. | `UnderDevelopment`, off by default; `dynamicTools` is experimental | Routing with several or no attached clients; a managed daemon; macOS; later releases |
| Full-history inheritance | No Dashpot change. Worth stating in [#644](https://github.com/ned2/dashpot/issues/644)'s launch guidance: a full-history fork, the default when `fork_turns` is omitted, carries the lead's dynamic tools whatever the flag. | Not behind the flag | As above |
| Resolved model and effort in creation activity | No implementation Issue now. Hooks carry `model` but not effort. Reading it means reading app-server items or rollouts, a new observation adapter this Issue rules out. A future proposal to show a Worker's model and effort would read `started` activity and treat `null` and missing alike. | Not behind a flag, and not marked experimental in the protocol | Older rollouts' records, which the run did not read; real models' effort resolution |
| Turn lineage | No implementation Issue. It attributes a Worker's turn to a lead turn, which Dashpot does not model, and it is not an identity. Hooks already give a Worker's `session_id` and `agent_id`. | Not behind a flag, and not marked experimental in the protocol | Nested chains, where a Worker issues work and the parent and root turns differ: every measured Worker turn had the lead turn as both. Mail queued with `send_message`, read only in the source. `rootTurnId` in older history, which the protocol says may be `null`. v1 Workers |

## Implications for the skill

The `dashpot-execute-issues` skill's
[Codex notes](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex)
need no change from this run. Two facts belong with #644's launch wording:

- an omitted `fork_turns` forks the full history, and a numeric value does
  too;
- a full-history Worker inherits any dynamic tools its lead was given.

A client cannot compact a v2 Worker through the app-server, as
[section 3](#3-follow-up-compaction-and-resume) shows; whether Codex
compacts a Worker automatically was not measured.

## Validation

The retained trace passes the independent verifier, in its minimal form
and with `0.166.0 --strict`, on this branch: every script it names, and
the hook example, matches the hash the run recorded at its base `06df76a`. The
verifier checks only the form of the binary's SHA-256; the value above is
the one the trace records. Six altered copies of the trace failed it: a
flag-off fresh Worker offered the tool, the sentinel added to a fresh
Worker request, a Worker hook carrying the Worker's own thread as
`session_id`, the post-compaction lead's requests removed, one Worker
request naming another parent turn, and the updater on. After the run, no fixture Codex process remained.
