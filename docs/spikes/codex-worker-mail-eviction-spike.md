---
status: research
date: 2026-10-13
---

# Codex Worker mail and follow-up across eviction experiment

The experiment for [Issue #664](https://github.com/ned2/dashpot/issues/664)
measures what happens on the pinned **codex-cli 0.162.0** when a lead
runs more workers than Codex keeps loaded at once. It covers the mail the
lead leaves with a finished worker, a later `followup_task` to that worker,
and what remains of both when the lead or the daemon goes away. The
[Codex worker mechanics experiment](codex-worker-mechanics-spike.md)
measured 0.160.0, where a finished worker holding unread mail kept its slot,
and left `followup_task` to an unloaded worker unknown. 0.162.0 changed that
rule, as the
[0.162.0 change survey](../research/harness-arc-orchestration-research.md)
recorded.

Here the **lead** is the root thread of a Codex Agent Session, and a
**worker** is one of its [Sub-agents](../domain-language.md). The fixture
threads only delegate, so they are a skill's Lead and Workers in shape only.
Codex's own terms for where a worker is:

- a **loaded** worker is held by the daemon, and a v2 session counts it
  against its **residency capacity**;
- a **locally evicted** worker is one Codex unloaded to make room. Its
  session's runtime keeps a record of it, and keeps its unread mail in
  memory;
- a **cold** worker is one unloaded without that record: after its lead's
  runtime was unloaded and the lead resumed, or after the daemon restarted.
  Codex reloads it from its rollout on disk.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it. A
  timing is this run's single sample, which the verifier checks against a
  looser bound;
- **documented**: read from the 0.162.0 source at tag
  [`rust-v0.162.0`](https://github.com/openai/codex/tree/rust-v0.162.0),
  commit `c1382380de69521303b416720a52f42d51af6248`, paths under
  `codex-rs/core/src/`;
- **trace only**: the retained trace shows it, but the verifier does not
  check it;
- **unknown**: with the reason it is unknown.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| How many workers stay loaded? | 3 by default, `max_concurrent_threads_per_session − 1`, and the same `[agents] max_threads` sets it. Finished workers count until Codex evicts them. | measured; documented, `agent/control/residency.rs` |
| Is that the limit on running workers? | It is a separate counter with the same default: at most 3 workers run a turn at once (`agent/control/execution.rs`). With three running, a fourth spawn and a follow-up to an evicted worker both failed with `agent thread limit reached`. The two refusals read the same, so the lead cannot tell which limit it hit. | measured; the two counters documented |
| Does unread mail keep a finished worker loaded? | No, unlike 0.160.0. Workers A and F, finished and each holding unread `send_message` mail, were evicted to make room for B, C and D. Only mail that starts a turn keeps a worker loaded. | measured; documented, `is_unloadable` in `agent/control/residency.rs` |
| Does mail to a locally evicted worker reload or start it? | Neither. With every slot free again, A and F stayed unloaded, made no model request and published no hook, after two and one messages each. | measured; documented, `agent/control/api.rs` |
| Does `followup_task` reach an evicted worker? | Yes. It reloads the worker into the least recently used finished worker's slot and starts its turn: A took B's slot, then F took C's. | measured |
| Is held mail delivered in order and exactly once? | Yes. A's first request after reload carried its task, its final answer, its four messages in send order, from before and after its eviction, then the follow-up task. A second follow-up delivered no message again. The follow-up refused at the limit never arrived. | measured |
| Does a reloaded worker keep its context? | Yes. A, spawned with `fork_turns: "none"`, held only its own turns; F, spawned with the full history, still held the lead's two earlier prompts. | measured |
| Does the follow-up's completion reach the lead? | Yes. Each `wait_agent` returned `Wait completed.` on the worker's completion, and the lead's history carried each `FINAL_ANSWER` once. | measured |
| Does `list_agents` show an evicted worker? | No. It lists loaded workers only, so A and F were missing from it until their follow-ups reloaded them. | measured; documented, `list_agents` in `agent/control.rs` |
| What does Dashpot show of a follow-up turn? | A worker's follow-up turn publishes `SubagentStop` but no `SubagentStart`. Dashpot therefore does not list A as working while its follow-up runs, and the `sub-agent` Cleanup blocker does not cover it. | measured |
| What happens to held mail when the lead unloads? | It is lost. A lead's runtime goes with the lead: after the lead was resumed, the evicted worker's two messages were never delivered. | measured |
| And when the daemon restarts? | It is lost too. The replacement daemon reloads the leads but no worker, and the evicted worker's two messages were never delivered. | measured |
| What does mail do to a cold worker? | It reloads the worker without starting a turn: `list_agents` showed it `pending_init`. The message waited, and the worker's next follow-up got it once, then the task, with its earlier turns. | measured; documented, `agent/control/api.rs` |
| Is Codex's held mail durable? | No. It is held in memory by the runtime, and the run lost it across a lead's unload and across a daemon restart. Only what a worker already received survives, in its rollout. | measured; documented, `agent/control/residency.rs` |

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
Run the runner detached, from outside any harness, so that its refusal check
passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-664/run.mjs ~/.codex/packages/standalone/releases/0.162.0-x86_64-unknown-linux-musl/bin/codex 0.162.0 > run.log 2>&1'
node scripts/experiments/codex-664/verify.mjs /tmp/dashpot-codex-664-SUFFIX/trace.jsonl 0.162.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes under three minutes, most of it the wait for a lead to
unload.

- [Runner](../../scripts/experiments/codex-664/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. It builds a disposable Dashpot Project under the
    temporary directory, with Issues 1 and 2 as Local Issue Markdown and a
    linked `other` Worktree. Codex gets an isolated `HOME`, `CODEX_HOME`,
    XDG directories and `TMPDIR`. It runs as `codex` through a symlink on a
    fixture-local `PATH`, under a managed app-server daemon whose updater
    is off.
  - **Hooks.** Every hook event that `dashpot integrate codex` subscribes
    goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`, trusted through the `hooks/list` ledger.
  - **Model.** A loopback Responses API stands in for the model and follows
    a fixed plan for each prompt or worker task. Its `fixture-v2` model, a
    copy of `gpt-5.5` whose `multi_agent_version` is `v2`, gives each lead
    and worker the v2 `collaboration` tools.
  - **Scenarios.**
    - `local-eviction`: lead L binds Issue 1 with `work start 1` and runs
      at the default capacity. It spawns A with `fork_turns: "none"` and F
      with the full history, sends them mail once they finish, then spawns
      B, C and D, which run 9-second commands and evict A and F. While they
      run it tries a fourth spawn, E, and a follow-up to A. Once they
      finish it sends A and F more mail, follows each up, and follows A up
      again.
    - `lead-unload`: lead R runs at a capacity of one, through the
      per-thread override `{"agents.max_threads": 1}`. Its worker R1
      finishes, gets mail, is evicted by R2, and gets more mail. The
      controller then leaves R until the daemon unloads it, resumes it
      with the same override, and has it message and follow up R1.
    - `daemon-restart`: lead S does the same, but the controller runs
      `codex app-server daemon restart` in place of the unload.
  - **Records.** For every model request it records the thread, the
    fixture markers in input order with each item's type, each
    inter-agent item's author, recipient and opening line, and the latest
    tool output. It also records the daemon's loaded threads and their
    status (`thread/loaded/list`, `thread/read`), every hook, and Dashpot's
    own view: its Agent Runs, `work show` and
    `worktree check other --json`.
- [Independent trace verifier](../../scripts/experiments/codex-664/verify.mjs)
  checks every **measured** claim below against the trace without importing
  the runner or Dashpot. It also checks the runner's sources, and with
  `--strict` Dashpot's session modules, against the hashes the trace
  records.
- [Retained trace](measurements/issue-664-codex-trace.jsonl) is the complete
  metadata stream of the successful run: 310 records. The fixture root
  appears as `$ROOT`, and the home directory as `~`. It holds no prompts
  beyond the fixture's markers.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-13 AEDT |
| Dashpot base | `6227e7a1cdf04e37c008d14e42d54a6b5a39c71e`, with the runner uncommitted |
| Codex | `codex-cli 0.162.0`, the musl standalone release, SHA-256 `50ed828f357c655a3c82054d346cab8434f24901f14ec19b8267571bdd008b38`, as a managed app-server daemon |
| Controller | Node `v24.18.0`, over the daemon's Unix socket |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |
| Model | `fixture-v2` (catalog v2), served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The run
  measures what Codex does with those calls, not whether a real model makes
  them.
- **Hosting mode.** Every thread is daemon-hosted. A terminal client's
  in-process server and `codex exec` host the same core, but are not
  measured here.
- **Restoration.** The run restores a cold worker only by messaging it
  after its lead resumed. A lead that resumes in another daemon, or a
  worker restored with nothing addressed to it, is not measured. Codex
  does not reopen a v2 lead's workers when the lead resumes
  ([0.162.0 change survey](../research/harness-arc-orchestration-research.md)).
- **Platforms.** macOS, other releases and real models are unmeasured.

## 1. Capacity and eviction

| Claim | Basis |
| --- | --- |
| After A and F finished, both stayed loaded beside the lead, each holding unread mail. | measured |
| B, C and D spawned while A and F sat finished. The daemon then held B, C and D, and read A and F as `notLoaded`. | measured |
| With B, C and D running, a fourth spawn failed with `collab spawn failed: agent thread limit reached`, and E never ran. A `followup_task` to evicted A failed with `collab tool failed: agent thread limit reached`. | measured |
| Residency capacity and the running-turn limit are separate counters. Each defaults to `max_concurrent_threads_per_session − 1`. Each refusal is `AgentLimitReached`, which reads `agent thread limit reached`; only Codex's internal error context, `ExecutionCapacity` or `ResidencyCapacity`, tells them apart, and the model does not see it. | documented, `agent/control/residency.rs`, `agent/control/execution.rs`, `protocol/src/error.rs` |
| A finished worker is evictable unless it has a running turn, a durable sleep, or mail that starts a turn. Queue-only mail does not count: Codex drains it into the runtime's in-memory mailboxes before unloading the worker. | documented, `is_unloadable` and `try_unload_one_resident` in `agent/control/residency.rs` |
| Eviction picks the least recently used loaded worker. When A's follow-up reloaded it, B, the first of the three to be spawned, was evicted. When F's follow-up reloaded it, C went next. | measured; the order documented, `touch_resident` in `agent/control/residency.rs` |

## 2. Mail to an evicted worker

| Claim | Basis |
| --- | --- |
| `send_message` returns an empty string whether its recipient is loaded, evicted or cold. | measured |
| Mail to a finished, loaded worker only queues: neither A nor F ran a turn. | measured |
| Mail to a locally evicted worker neither reloads nor starts it. After B, C and D had finished, A and F got two messages and one, and stayed unloaded, with no model request and no hook. | measured |
| A message to a worker that is not loaded reloads it unless the runtime holds its eviction record. Only a locally evicted worker keeps its mail without reloading. | documented, `send_input` in `agent/control/api.rs` |
| When a follow-up reloads A, its first request carries, in order: its task, its final answer, the messages `a-pre1`, `a-pre2`, `a-post1` and `a-post2`, then the follow-up task. The messages read `Message Type: MESSAGE` and the tasks `Message Type: NEW_TASK`. No message appears twice in any request of A's or F's. F's reload is the same with its own `f-pre1` and `f-post1`. | measured |
| A second follow-up to A delivers no message again: its first request carries the earlier history once, then A's second final answer and the new task. | measured |
| The follow-up refused at the limit is dropped: its task never reached A. | measured |

## 3. Follow-up, context and completion

| Claim | Basis |
| --- | --- |
| `followup_task` to an evicted worker reloads it and starts its turn: A and F each ran their follow-up task once reloaded. | measured |
| A reloaded worker keeps its rollout. A, spawned with `fork_turns: "none"`, carried none of the lead's prompts before or after reload. F, spawned with the full history, carried the lead's two earlier prompts on its first turn and again after reload. | measured |
| The follow-up's completion reaches the lead that sent it: each `wait_agent` returned `{"message":"Wait completed.","timed_out":false}` on the worker's completion, and the lead's history carried A's three final answers and F's two, each once. | measured |
| `list_agents` lists only loaded workers. Before B, C and D, it listed A and F; with them loaded, it listed only B, C and D; after the follow-ups, A, D and F. | measured |

## 4. Dashpot's view of a follow-up

| Claim | Basis |
| --- | --- |
| While B, C and D ran, `work show` listed `3 sub-agents listed as working`, and the `sub-agent` blocker named them on the `other` Worktree. Once they finished, neither did. | measured |
| A follow-up turn publishes `SubagentStop` for the worker but no `SubagentStart`. A and F each published one `SubagentStart`, at the spawn, and a `SubagentStop` per turn. Neither published `SessionStart` or `SessionEnd`. | measured |
| So Dashpot does not list a followed-up worker while it works. Taken while A's follow-up command ran, the view showed L's run `running`, which follows the lead's turn, but listed no sub-agent working and gave the `other` Worktree no blocker. | measured |
| The 0.160.0 trace shows the same: its resumed worker's follow-up fired `SubagentStop` alone. | trace only, [#420's trace](measurements/issue-420-codex-trace.jsonl) |

## 5. Lead unload and cold restoration

| Claim | Basis |
| --- | --- |
| With a capacity of one, R2's spawn evicted finished R1. R1 then held `r1-pre`, sent before its eviction, and `r1-post`, sent after. | measured |
| The daemon unloaded R 60.3 s after its last client left, with `SessionEnd`. R2, finished, stayed loaded. | measured |
| `thread/resume` reloaded R. Its `list_agents` named R2 but not R1. | measured |
| A message to R1 then reloaded it without a turn: `list_agents` read it `pending_init`, and R1 made no model request. R1 reloaded beside R2 though R was resumed with the capacity-one override. Why it did is not established. | measured; the cause unknown |
| R1's follow-up got its task, its final answer, the cold message once, then the new task. `r1-pre` and `r1-post` never arrived. | measured |

## 6. Daemon restart

| Claim | Basis |
| --- | --- |
| `codex app-server daemon restart` returned 0 in 0.5 s, and a daemon with a new process ID took over. Each loaded lead published `SessionEnd`. | measured for the exit status and process ID; `SessionEnd` trace only |
| The replacement daemon held the three leads, which no client had resumed, and no worker. | measured |
| After S's `thread/resume`, `list_agents` named neither of its workers: S2, loaded before the restart, was gone too. | measured |
| A message reloaded S1 without a turn, as R1's had, and its follow-up got the cold message once, then the task, with its earlier turns. `s1-pre` and `s1-post` never arrived. | measured |
| S published a second `SessionEnd` when the controller resumed it, then `SessionStart` with `source` `resume`. | trace only |
| Dashpot showed L's run orphaned after the restart, as [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md) decides. | measured |

## Implications for the skill

The `dashpot-execute-issues` skill's Codex guidance was written for 0.160.0,
and changes with this evidence:

- **Capacity.** A finished worker no longer keeps its slot for unread mail.
  A lead that queues more Issues than the capacity still spawns into a
  freed slot, but its message to a finished worker may now sit with an
  evicted one.
- **Messaging an evicted worker.** The message waits, in memory, until the
  worker's next turn. Address it with `followup_task`, which reloads the
  worker and delivers the waiting mail first.
- **`list_agents`.** An evicted worker is missing from it. The lead keeps
  its own list of the workers it spawned, as the Arc Ledger does.
- **The lead's unload and a daemon restart** lose the waiting mail. The
  lead re-sends what matters in the follow-up task itself.

## Implications for Dashpot

- **A follow-up turn is invisible to the `sub-agent` blocker.** Codex
  publishes no `SubagentStart` for a worker's follow-up turn, so Dashpot
  does not list the worker while it works, and Cleanup's `sub-agent`
  blocker does not cover it. A Worker assigned an Issue reads `running`
  only while Dashpot lists it working
  ([ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)),
  so its Issue would not read `running` either; the run made no
  assignment. 0.160.0 does the same. This is reported, not fixed here.

## Validation

The retained trace passed the independent verifier with `--strict` at the
run's base, `6227e7a`: every script and Dashpot module it names matched the
hash the run recorded. After the run's `daemon stop`, no fixture Codex
process remained, and every hook reached Dashpot's publisher and exited 0.
