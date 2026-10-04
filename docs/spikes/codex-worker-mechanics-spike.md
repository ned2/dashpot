---
status: research
date: 2026-10-04
---

# Codex worker mechanics experiment

The experiment for [Issue #420](https://github.com/ned2/dashpot/issues/420)
measures how a Codex lead thread runs background workers on the pinned
**codex-cli 0.160.0**. The execute-issues skill of
[#403](https://github.com/ned2/dashpot/issues/403) needs those workers, and
[#422](https://github.com/ned2/dashpot/issues/422) compares the answers with
Claude Code's and OpenCode's.
This document is the dated evidence record. Sections 1 to 8 answer the
Issue's questions in its order.

Here the **lead** is the root thread of a Codex Agent Session, and a
**worker** is one of its [Sub-agents](../domain-language.md): a thread the
lead spawned, which shares the lead's Agent Session. Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it. A
  timing is this run's single sample, which the verifier checks against a
  looser bound;
- **documented**: read from the 0.160.0 source at tag
  [`rust-v0.160.0`](https://github.com/openai/codex/tree/rust-v0.160.0);
- **unknown**: with the reason it is unknown.

Codex has two sub-agent tool sets, and only multi-agent v2 gives a lead
everything the skill needs:

- **v2** (namespace `collaboration`) has background workers, a worker's
  mid-flight message, a waiting lead woken by either a message or a finished
  worker, and resume.
- **v1** (namespace `multi_agent_v1`) has background workers and resume.
  Its workers have no tool to report mid-flight.

Codex never starts a turn in an idle lead. A Codex lead therefore has to stay
inside its turn and loop on `wait_agent`, which returns on every worker
message and every completion.

## Choosing the tool set

A thread's tool set is fixed when it starts, by these rules in order
(documented, `Config::multi_agent_version` in `core/src/config/mod.rs`):

1. `[features] multi_agent_v2 = true`, or the `features.multi_agent_v2`
   override on `thread/start`, selects v2.
2. Otherwise the model's catalog entry decides, through its
   `multi_agent_version`.
3. A model with no `multi_agent_version` gets v1, as does one the catalog
   does not name, unless `[agents] enabled = false` turns sub-agents off.

The bundled catalog in 0.160.0 is retained in the trace's first record, and
`codex debug models --bundled` prints it:

| Tool set | Bundled models |
| --- | --- |
| v2 | `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-daybreak-blue-latest`, `gpt-daybreak-red-latest` |
| v1 | `gpt-5.6-luna`, `codex-auto-review`, and `gpt-5.5`, whose entry names no version |

A worker runs its lead's model unless the spawn names another. The flag does
not carry from a lead to its workers. This was measured:

- A lead on the flag but a non-v2 model got the v2 tools.
- Its worker, on the same model, got no collaboration tools at all, as a v1
  worker gets none. The flag set on the lead's `thread/start` did not reach
  it.
- A worker on a catalog-v2 model got the full collaboration set, including
  `spawn_agent`.

**Recommendation:** run the lead on a catalog-v2 model, so that the lead and
its workers both get v2. Use the flag only when the workers need no
collaboration tools of their own: the lead still gets v2's waiting and
resume, but its workers cannot send mid-flight messages. Treat a v1 model as
the fallback described under each question.

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
Run the runner detached, from outside any harness, so that its refusal check
passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-420/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/bin/codex 0.160.0 > run.log 2>&1'
node scripts/experiments/codex-420/verify.mjs /tmp/dashpot-codex-420-SUFFIX/trace.jsonl 0.160.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes under six minutes.

- [Runner](../../scripts/experiments/codex-420/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process. It builds a disposable Dashpot Project under the
    temporary directory, with Issues 1 to 4 as Local Issue Markdown and three
    linked Worktrees: `other`, `third` and `fourth`. The main lead binds
    Issue 1 in the main Worktree, and the unload scenario's lead binds
    Issue 3 in `third`. Codex gets an isolated
    `HOME`, `CODEX_HOME`, XDG directories and `TMPDIR`. It runs as `codex`
    through a symlink on a fixture-local `PATH`, under a managed app-server
    daemon whose updater is off.
  - **Hooks.** Every hook event that `dashpot integrate codex` subscribes
    goes through a metadata-only wrapper to Dashpot's real
    `dashpot-codex-hook`, trusted through the `hooks/list` ledger.
  - **Model.** A loopback Responses API stands in for the model and follows
    a fixed plan for each prompt or worker task. The catalog file adds
    `fixture-v2`, a copy of `gpt-5.5` whose `multi_agent_version` is `v2`.
    The default model, `fixture-model`, is in no catalog, so it gets v1.
  - **Skills.** Two user skills sit in `$HOME/.agents/skills`, where
    `dashpot integrate codex` installs Dashpot's skills, one of them
    explicit-only.
  - **Records.** For every model request it records the thread, the tools
    offered, the fixture markers in the input, each inter-agent item's
    author, recipient and opening text, and the latest tool output. It also
    records Dashpot's own view and Worktree checks, and the shells' `CODEX_*`
    variables, directory and `dashpot work` output.
- [Independent trace verifier](../../scripts/experiments/codex-420/verify.mjs)
  checks every **measured** claim below against the trace without importing
  the runner or Dashpot. It also checks the runner's sources, and with
  `--strict` Dashpot's session modules, against the hashes the trace
  records.
- [Retained trace](measurements/issue-420-codex-trace.jsonl) is the complete
  metadata stream of the successful run: 389 records. The fixture root
  appears as `$ROOT`, or as `<root>` inside Codex's own command output, and
  the home directory as `~`. It holds no prompts
  beyond the fixture's markers.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-04 AEST |
| Dashpot base | `8e422127d06683c875b01be6a0f292c0ac091200`, with the runner uncommitted |
| Codex | `codex-cli 0.160.0`, the musl standalone release, as a managed app-server daemon |
| Controller | Node `v24.18.0`, over the daemon's Unix socket |
| Operating system | Ubuntu, Linux `7.0.0-34-generic`, x86-64 |
| Models | `fixture-v2` (catalog v2), and `fixture-model` (uncatalogued, so v1), both served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls the tools on a fixed plan. The run
  measures what Codex does with those calls, not whether a real model makes
  them. A real catalog-v2 model is `code_mode_only`, so it reaches these
  tools through code mode, which the fixture's model does not use.
- **Hosting mode.** Every thread is daemon-hosted. The terminal client and
  `codex exec` host the same core, but their worker mechanics are not
  measured here.
- **Duration.** Timings are single samples on an idle machine, and the
  longest wait measured is 10 seconds. Hours-long waves are outside the run.
- **Platforms.** macOS, other releases and real models are unmeasured.

## 1. Launch

| Claim | Basis |
| --- | --- |
| A v2 lead's tools are `collaboration/{spawn_agent, send_message, followup_task, wait_agent, interrupt_agent, list_agents}`. v2 has no `close_agent`. | measured |
| `spawn_agent` takes `message`, `task_name`, and optionally `fork_turns` (`none`, `all`, or a number), `model`, `reasoning_effort` and `agent_type`. It has no working-directory argument. | documented, `tools/handlers/multi_agents_v2/spawn.rs` |
| `spawn_agent` returns at once with `{"task_name":"/root/worker_a"}`. Each spawn in the launch turn returned within 50 ms. The lead's turn ended 0.35 s after its first spawn, while its workers ran on for 12.0 s and 16.6 s. | measured |
| A v1 spawn returns `{"agent_id":"<thread id>","nickname":"<name>"}`. A v1 worker gets no multi-agent tools. | measured |
| `SubagentStart` and `SubagentStop` fire for each worker. They carry the root `session_id`, the worker's thread as `agent_id`, `agent_type` `default`, and the lead's `cwd`. A v1 worker's turns also fire `UserPromptSubmit` with its `agent_id`, which v2 workers do not. | measured |
| Every worker shell shares the lead's Host Process, the daemon. `CODEX_SESSION_ID` names the root session, and `CODEX_THREAD_ID` names the worker's own thread. | measured |
| **Concurrency.** A v2 session holds at most `max_concurrent_threads_per_session − 1` workers open at once, 3 by default. A finished worker stays open, but Codex unloads one with no pending mail to make room. In the run, the 3rd and 4th spawns of a turn failed with `collab spawn failed: agent thread limit reached`. They failed because a finished worker still held queued mail, which kept it resident. A 5th spawn worked once the first two workers had finished. | measured; the rule is documented, `agent/control/residency.rs` |
| **Raising the limit.** `[agents] max_threads = N` raises it to N workers. The canonical key is `max_concurrent_threads_per_session`, and v2 adds 1 for the root. The setting also works per thread as a `thread/start` override: a lead started with `{"agents.max_threads": 5}` opened five workers at once. `[features.multi_agent_v2] max_concurrent_threads_per_session` counts the root itself. v1 defaults to 6 workers, through the same `agents.max_threads`. | measured for the override; the rest documented, `config/src/config_toml.rs`, `core/src/config/mod.rs` |

## 2. Mid-flight report

| Claim | Basis |
| --- | --- |
| A v2 worker reports with `send_message` to `/root`. The message is queue-only: it never starts a lead turn. | measured |
| An idle lead is not woken. While two workers messaged and finished, the lead made no model request and the controller saw no `turn/started`. | measured |
| A waiting lead is woken. `wait_agent` returned within 43 ms of each of a worker's two messages, each reply reporting `Wait completed.` with `timed_out` false, and the message was in the lead's history at its next request. | measured |
| A lead that is busy when a message arrives sees it at its next model request, after its current tool call returns. | measured |
| A message carries the text the worker sent, as an `agent_message` item from `/root/<task>`, whose text opens `Message Type: MESSAGE`. | measured |
| A v1 worker has no tool to message its lead. | measured |

**Fallback under v1:** the lead polls, and workers cannot report mid-flight.
A worker that must report progress writes it somewhere the lead reads, such
as a file in its Worktree or `gh` output. The lead reads it between
`wait_agent` calls.

## 3. Completion

| Claim | Basis |
| --- | --- |
| Codex starts no lead turn when a worker finishes, in either tool set. | measured |
| **`wait_agent` (v2).** It takes `{timeout_ms}`: default 30 000, minimum 10 000, maximum 3 600 000. `[features.multi_agent_v2]` sets each bound through `default_wait_timeout_ms`, `min_wait_timeout_ms` and `max_wait_timeout_ms`, whose schema allows 0 to 3 600 000. A shorter request is clamped and the reply says so. A longer one is refused with `timeout_ms must be at most 3600000`. It returns `{"message":"Wait completed.","timed_out":false}` on any mail: a worker's message, or a worker finishing, which it answered within 17 ms. It returns `{"message":"Wait timed out.","timed_out":true}` when nothing arrives. New user input ends it with `Wait interrupted by new input.` It names no worker; the lead reads the mail that woke it. | measured for completion, message, clamp and timeout; the bounds and `Steered` documented, `tools/handlers/multi_agents_v2/wait.rs`, `core/src/config/mod.rs`, `features/src/feature_configs.rs` |
| **Where the final text appears (v2).** It reaches the lead's history as an `agent_message` from the worker, whose text is `Message Type: FINAL_ANSWER`, the task name, the sender, and `Payload:` followed by the worker's last message. Mail that arrived while the lead was idle was missing from the only model request of the lead's next turn. It first appeared in the request after that, the following turn's first, ahead of that turn's prompt. A lead turn that ends after one request therefore never sees it. | measured |
| **`list_agents` (v2)** returns each resident worker as `{"agent_name":"/root/worker_l","agent_status":{"completed":"DONE:wl"}}`, with the final text inline. It is the reliable read after an interrupted wait. It lists only resident workers: workers that Codex had unloaded to make room were missing from it. | measured |
| **v1.** `wait_agent` takes `{targets, timeout_ms}` and returns `{"status":{"<agent id>":{"completed":"<final text>"}},"timed_out":false}`. The finished worker's final text is also injected into the lead's history, as a user message, by its next turn. | measured |
| **Turn limits.** A search of the 0.160.0 core and configuration source found no turn-duration, tool-call or step limit. A waiting loop is bounded by the 3 600-second ceiling per `wait_agent` call, and by the model's context window, which grows with every call and every message. | unknown, because a turn of hours is unmeasured; the absence of a limit is documented |

**Fallback for the idle lead:** the lead stays in its turn and loops
`wait_agent` → read the mail → act → `wait_agent`. The skill should run that
loop until every worker reports `completed`, checking with `list_agents`
whenever a wait times out or the lead resumes after an interruption. Nothing
outside the turn re-enters it, so the person or controller must start a new
turn after any interruption.

## 4. Resume

| Claim | Basis |
| --- | --- |
| **v2.** `followup_task` to a finished worker starts a new turn on the same thread with all its earlier context: the original task, its messages, and its final answer. `SubagentStop` fires again with the same `agent_id`. | measured |
| **v2.** `send_message` to a finished worker only queues: the worker runs no turn. | measured |
| **v2.** `followup_task` toward `/root` is refused: `Follow-up tasks can't target the root agent`. | documented, `agent/control/api.rs` |
| **v1.** `send_input` to a finished worker starts a new turn with its context. `wait_agent` then returns its new final answer. v1 also has `resume_agent` and `close_agent`. | measured for `send_input`; the others documented |
| **Unloaded workers.** Whether `followup_task` reaches a worker that Codex unloaded to make room. | unknown, because the run followed up only a resident worker; the source can reopen an agent from its rollout (`agent/control/resume.rs`) |

## 5. Shared Agent Session

| Claim | Basis |
| --- | --- |
| `dashpot work start 2` from a worker's shell is refused with exit 2, whether the shell is in another Worktree or in the lead's. So are `work relocate .` and `work stop`. Each reports `no supported agent session encloses this command … no lifecycle hook record for Codex session <the worker's thread id> (from Codex environment)`. | measured |
| A refused `work stop` left the lead's run in place. | measured |
| The lead reads `running` while its workers work and `waiting` once they have stopped, through [ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md). | measured |
| The `sub-agent` Cleanup blocker of [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md) names the lead's session and its working workers on every linked Worktree while they work. The Worktree became removable once they stopped. | measured |
| `dashpot work show` lists the active runs recorded at the shell's Worktree, whatever session runs it, so its output does not depend on the worker's identity. From a worker in the lead's Worktree it printed the lead's run and its working workers, in full: `codex pid <pid>: fixture-1 (I_fixture_1) since <time>` then `  codex pid <pid> has 2 sub-agents listed as working (<worker A>, <worker B>). Dashpot lists a sub-agent until Codex reports that it stopped, which an interrupted one may never do, so if none is still working, end that session's client (a daemon-hosted thread ends about 60 s after its last client leaves)`. From a worker in another Worktree it printed `no active Issue work at this worktree`, because no run is recorded there. A worker of a lead that held no run printed the main lead's run in the same way. | measured; the listing is also documented, `show_issue_work` in `src/dashpot/sessions/work.py` |

**Defect, [#428](https://github.com/ned2/dashpot/issues/428).** Dashpot identifies a Codex shell by
`CODEX_THREAD_ID` (`_codex_claim` in `src/dashpot/sessions/harnesses.py`). In a
worker that names the worker's own thread, which no hook record carries, so
every management command run from a worker is refused as running outside any
session. The refusal is safe: `work stop` cannot end the lead's run, as it
can from a Claude Code sub-agent. But the reason it gives is wrong. The
recent session events `work show` appends after the runs depend on the
enclosing session, and from a worker they are silently empty: `wb.1` printed
none. The trace has no lead-side `work show` to compare it with.

The minimal sequence is:

1. A lead binds with `work start 1`.
2. It spawns a v2 worker.
3. The worker runs `work start 2` or `work stop` in any Worktree.

**Fix path.** A worker's shell also exports `CODEX_SESSION_ID`. That variable
equals the root `session_id` its hooks publish, and in a lead's own shell it
equals `CODEX_THREAD_ID`. So:

- When `CODEX_SESSION_ID` differs from `CODEX_THREAD_ID`, the shell is a
  sub-agent of that root session, as OpenCode's `parentID` marks a child in
  [ADR 0090](../adr/0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md).
- `SubagentStart` also pairs the root `session_id` with the worker's
  `agent_id`, which confirms the relationship.
- The model request carries `x-codex-parent-thread-id` too, but no hook or
  shell sees that header.

## 6. Location

| Claim | Basis |
| --- | --- |
| A worker's shell starts in the lead's directory. A per-command `cd <Worktree> && …` works, and the worker's next command without `cd` started in the lead's directory again. | measured |
| A worker's hooks and `thread/read` keep reporting the lead's `cwd` even while its commands run in another Worktree. Dashpot therefore cannot tell where a worker works, which is why the `sub-agent` blocker covers every Worktree. | measured |
| No spawn argument or worker tool sets a worker's directory. | documented |
| A worker cannot move the lead's session or run. Its `dashpot work relocate .` was refused, and its tools change no thread's directory: none of the tools offered to it does, so it cannot use the lead's directory overrides. Those overrides are `/cd` in the terminal client and `cwd` on `turn/start` or `thread/start`, and only a person or a controller holds them. | measured for `relocate` and the tool lists; documented for the overrides |

**Fallback:** the lead names each worker's Worktree by absolute path in the
task. The worker prefixes every command with `cd <path> &&`, or uses
`git -C <path>` and absolute paths for edits. Location is a per-command
discipline, not a property of the worker.

## 7. Interruption

| Claim | Basis |
| --- | --- |
| `interrupt_agent` returns `{"previous_status":"running"}`. The worker's running command carried on to its end, 17.6 s later, and the worker published no `SubagentStop`. Dashpot therefore kept listing it as working, and its `sub-agent` blocker stayed on every linked Worktree. This is [openai/codex#38142](https://github.com/openai/codex/issues/38142), which [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md) already describes, still present in 0.160.0. | measured |
| Interrupting the lead's turn with `turn/interrupt` while it waits fires `Interrupt` for the lead and leaves its worker running: the worker finished 14.0 s later. The worker's final answer did not reach the interrupted lead's history on its next turn, but `list_agents` reported it `completed`. | measured |
| When the lead's last client unsubscribes, the daemon unloads the lead 60.3 s later, with `SessionEnd`. Its worker keeps working: its fourth 25-second command started 14.3 s after the lead unloaded, and its `SubagentStop` came 99.9 s after the client left. | measured |
| Dashpot ends the unloaded lead's run while that worker still works, and the worker's `sub-agent` blocker goes with the session. The lead held Issue 3 in the `third` Worktree. The `SessionEnd` hook deferred the run to the settler of [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md), which found the daemon still live and ended the run within 10.3 s of `SessionEnd`. For the next 29 s no run and no `sub-agent` blocker covered the worker that was still working. Its late `SubagentStop` reached Dashpot's publisher, which recorded it in the Event Log as changing nothing. The details are under [Implications for Dashpot](#implications-for-dashpot). | measured |
| `thread/delete` of the lead ends the lead (`SessionEnd`) and its worker: both read `thread not loaded`. The worker's running command never finished, and no `SubagentStop` fired. | measured |

**Fallbacks:**

- Use `interrupt_agent` only for a worker that has already gone quiet. A
  worker interrupted mid-command leaves Dashpot's blocker stale until the
  lead's session ends.
- To stop a wave, interrupt the lead and then `followup_task` each worker
  with an instruction to stop, or delete the lead thread to end every worker
  at once.
- Keep a client subscribed to the lead for the whole wave. An unloaded lead
  leaves its workers running with no run or Cleanup blocker to show them.

## 8. Skill loading

| Claim | Basis |
| --- | --- |
| Codex loads user skills from `$HOME/.agents/skills/<name>/SKILL.md`, where `dashpot integrate codex` installs them. A lead and its workers, under v1 or v2, list a model-invoked skill in their context without its body. | measured |
| A skill whose `agents/openai.yaml` sets `policy: allow_implicit_invocation: false` is not listed, but `$<name>` in a prompt still injects its body. | measured |
| Whether a `$<name>` in a worker's spawn message injects the skill. | unknown, because the run named an explicit skill only in a person's prompt |

**Fallback:** a lead that wants a worker to follow a skill tells it, in
the task, to read the skill's `SKILL.md` by path. A model-invoked skill
needs no fallback, since workers see it listed.

## Implications for Dashpot

Both findings are reported, not fixed here.

- **A worker's shell names no session:
  [#428](https://github.com/ned2/dashpot/issues/428).** Recognise a Codex
  sub-agent's shell by `CODEX_SESSION_ID` ≠ `CODEX_THREAD_ID`, as in
  [section 5](#5-shared-agent-session), so that its refusal names a
  sub-agent and the session events of `work show` resolve the root session.
- **An unloaded lead's run ends while its worker works:
  [#431](https://github.com/ned2/dashpot/issues/431).** In the `lead-unload` scenario,
  lead N held Issue 3 in the `third` Worktree, and its worker G ran four
  25-second commands (`wg.0` to `wg.3`). The trace labels are these:
  - `lead-unload-bound` and `lead-unload-bound-fourth`: while N was loaded,
    its run was `running`, and G's `sub-agent` blocker held the `fourth`
    Worktree.
  - `SessionEnd`, 60.3 s after the last client left: the hook deferred the
    run (`work_store.change` `deferred` in the Event Log).
  - `lead-unload-first`, 2 s later: the run was still listed while
    the [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)
    settler watched the daemon.
  - `lead-unload-settled` and `lead-unload-settled-fourth`: the settler
    found the daemon live, took the end for an unload and ended the run
    (`ended` in the Event Log), within 10.3 s of `SessionEnd`. No run
    remained, and no obstacle named G.
  - `wg.3`: G's fourth command started 14.3 s after `SessionEnd` and was
    still running when the run ended; it ended about 29 s later.

  A `SubagentStop` for G did arrive, at trace receipt 360, about 29 s after
  the run ended. Dashpot's publisher accepted it, and the Event Log records it
  as `SubagentStop` with `work_store.change` `unchanged`. The session's
  record was gone, so the stop had no parent to update, which is the
  behaviour `hook_records.py` documents for a stop after its parent's
  `SessionEnd`. [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
  blocker assumes a worker never outlives its session's `SessionEnd`, and on
  the managed daemon it can.

## Validation

The retained trace passed the independent verifier with `--strict` at the
run's base, `8e42212`: every script and Dashpot session module it names
matched the hash the run recorded. On the rebased branch the runner's
scripts still match. Two session modules, `hook_scan.py` and
`processes.py`, changed in [PR #417](https://github.com/ned2/dashpot/pull/417)
after the run, so the verifier without `--strict` passes and reports them
as drifted. After the run's `daemon stop`, no fixture Codex process
remained, and every hook reached Dashpot's publisher and exited 0.
