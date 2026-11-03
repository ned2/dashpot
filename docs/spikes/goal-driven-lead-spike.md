---
status: research
date: 2026-11-03
---

# Goals that keep a Lead going on Codex and Claude Code

The experiment for [Issue #649](https://github.com/ned2/dashpot/issues/649)
measures whether a goal keeps a Lead of the `dashpot-execute-issues` skill
going while its Workers run, and how Dashpot records the turns a goal
starts. It covers Codex's thread goal on the pinned **codex-cli 0.166.0**
and Claude Code's `/goal` on the pinned **Claude Code 2.1.317**. It ends
with a recommendation for the skill's Codex "Stay in your turn" paragraph
and its Claude Code section, and drafts their wording. It changes no
skill text: a follow-up Issue carries the change.

Here a **lead** is the root thread or session of a fixture Agent Session
and a **worker** one of its [Sub-agents](../domain-language.md). The
fixture leads only delegate, so they are the skill's Lead and Workers in
shape only. Where this document capitalises Lead or Worker, it means the
[domain language's](../domain-language.md) roles under the
`dashpot-execute-issues` skill.
A **goal turn** is a turn the goal starts rather than a person or a
notification.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **source**: read from the Codex source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`, or from the Claude Code 2.1.317 bundle where it says so.
  With `--codex-source`, the Codex verifier checks each Codex fact cited in
  a checkout of that commit, by matching its code in the cited file, not at
  the cited line;
- **documented**: from Claude Code's
  [goal documentation](https://code.claude.com/docs/en/goal), read on
  2026-11-03;
- **trace only**: the retained trace shows it, but the verifier does not
  check it. Every timing is this run's single sample;
- **inference**: what follows for the skill, which neither the trace, the
  source nor the documentation states.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Codex: do a Worker's message and its completion start goal turns? | No. Neither starts a turn, with or without a goal. With a goal, Codex starts a goal turn as soon as the Lead's turn ends, whatever the Workers do, and a goal turn waiting in `wait_agent` receives their mail, which ends the wait early. Without a goal, a Lead whose Worker messaged and finished stayed idle. | measured; source |
| Codex: which hooks fire for a goal turn, and what does Dashpot show? | `Stop` only, once per goal turn, and no `UserPromptSubmit`. Dashpot shows the Lead `running` while a Worker runs, then `waiting` in a goal turn after the Workers stopped, though the Lead was working (measured). So a Lead driven by a goal reads `waiting` through every goal turn after its Workers stop (inference). | measured; source; inference |
| Codex: does a Lead waiting in `wait_agent` across goal turns reach `blocked`? Through which path? | Not by itself. A wait that times out is a tool call, and a tool call resets the goal extension's empty-turn count, so waiting goal turns never meet the empty-response stop. The goal became `blocked` only through the model's own `update_goal`, which takes effect at once; the three-turn rule is an instruction to the model, not a check Codex makes. Codex blocks a goal itself after three automatic turns with an empty answer and no tool call, and at once on a failed turn. | measured; source |
| Codex: does a skill's instruction count as the explicit request? | Codex does not check: `create_goal` made on a skill's instruction was accepted. The skill's text reaches the model as a user message, which the tool's description counts as an explicit request. Whether a real model makes the call is not measured. | measured for Codex; source for the description; inference for a real model |
| Codex: does a goal reload an unloaded Lead ([#492](https://github.com/ned2/dashpot/issues/492))? | Confirmed: it does not. A goal set active on an unloaded Lead made no request, loaded nothing and ran no hook. Resuming the Lead started a goal turn at once. An active goal does keep an unsubscribed Lead loaded and working, until the goal stops being active. | measured; source |
| Claude Code: the evaluator's Stop-hook verdicts against Dashpot's Stop-driven turn state | Claude Code defers evaluation while a background Worker runs, and each Worker's completion notice starts a turn that runs `UserPromptSubmit`, so Dashpot shows the Lead `running` through that phase. Once no Worker runs, a "not met" verdict continues the turn after `Stop` has fired, with no `UserPromptSubmit`, so Dashpot shows the working Lead `waiting`. | measured |
| Claude Code: check-ins while Workers run | In a headless Lead, a check-in comes only when a turn ends with work still running after the interval: it continues that turn, again after `Stop` and with no `UserPromptSubmit`. No check-in came while the Lead was idle. An interactive Lead's idle check-ins are documented, not measured. | measured; documented |
| Claude Code: a condition phrased as the skill's end | The condition reached the evaluator verbatim. The evaluator calls no tool, so it can judge only what the conversation already shows. A "met" verdict cleared the goal. Nine "not met" verdicts in a row with no tool call end the turn with the goal kept, until the next prompt. A condition phrased as merged would never be met by a Lead whose operator merges, so it would end in that cap (inference; the fixture evaluator is scripted). | measured; documented; inference |

## Recommendation

**Codex: yes, as a backstop to the wait loop, not in place of it**
(inference from the measured answers).

- A goal keeps a Lead whose turn ended going, so a turn the model ends
  early no longer leaves the Workers' mail unread until the user speaks.
  Without a goal, the measured Lead sat idle.
- The wait loop stays: a goal turn does nothing with the Workers unless it
  waits in `wait_agent`, and each goal turn spends at least one model
  request. With `wait_agent` waiting up to an hour, a waiting Lead spends
  about one goal turn an hour. A Lead that ends goal turns with text and
  no wait is never stopped by the empty-response rule, and spends requests
  continuously: the fixture's unsubscribed lead ran 15 goal turns in 80 s.
- A failed model request blocks the goal at once, and a usage limit sets
  `usage_limited` (source). The Lead then stops as it does today, so the
  skill tells it, and the user, how to restart.
- An active goal keeps an unsubscribed Lead loaded, which is the
  [#492](https://github.com/ned2/dashpot/issues/492) gap's workaround while
  the goal stays active. Once the goal is blocked, paused or complete, the
  Lead unloads about 60 s later and Dashpot ends its Issue work as before.
  The run measured an explicit `thread/unsubscribe` on a connection that
  stayed open, not a client process exiting from a daemon-hosted Lead.
  "Keep a client attached" stays.
- The cost to Dashpot is the measured gap: every goal turn after the
  Workers stop reads `waiting`. The skill names it as a Known Dashpot gap,
  and the draft Dashpot Issue below carries the fix.

**Claude Code: optional, set by the user, for an unattended Lead**
(inference).

- A Lead already gets a turn for each Worker's completion
  ([Claude Code worker mechanics](claude-code-worker-mechanics-spike.md#3-completion)).
  `/goal` adds a check, after the last Worker hands back, that the Lead
  does not stop before every pull request is open and green.
- `/goal` is a command the user types. Whether a model can set one is not
  measured, so the skill asks the user rather than setting it.
- Its limits shape the Lead's behaviour: the evaluator sees only the
  conversation, so the Lead's last message must state each pull request's
  state; nine "not met" verdicts with no tool call end the turn, so a Lead
  waiting on CI watches it with a background command, which defers
  evaluation, instead of answering again; and Dashpot shows a goal
  continuation as `waiting`.

### Drafted skill wording

For the Codex section of
[the skill's harness reference](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex),
in place of "Stay in your turn":

> **Stay in your turn, and set a goal.** Without a goal, Codex never starts
> a turn for an idle lead, neither for a worker's message nor for its
> completion. Before launching the first worker, call `create_goal` with
> the arc's end as its objective: "Every Issue in this arc has an open pull
> request with green CI, or its worker has reported a blocker" (say
> "merged" in place of "open" only when the user granted merge authority).
> This skill is the explicit request `create_goal` asks for. With the goal
> active, Codex starts a goal turn as soon as your turn ends, so a turn that
> ends early resumes. In every turn, keep waiting with the wait loop below
> while any worker runs: a wait that times out is a verified wait, not a
> blocker. Call `update_goal` with `complete` once the end holds, and never
> with `blocked` while a worker runs. Codex blocks the goal itself on a
> failed turn and after three goal turns that end with an empty answer and
> no tool call, and a usage limit stops it. Then nothing re-enters your turn
> until the user sends a new message: tell the user, who can set the goal
> active again. Dashpot shows you `waiting` in a goal turn once your workers
> have stopped (Known Dashpot gaps).

For the Claude Code section, after "Completion":

> **A goal (optional).** Before you leave an arc unattended, ask the user
> to run `/goal Every Issue in this arc has an open pull request with green
> CI, or its worker has reported a blocker, and the lead's last message
> lists each pull request with its CI state.` Claude Code does not evaluate
> the goal while a worker or a background command runs. Its evaluator has
> no tools and judges only the conversation, so end each turn by listing
> each pull request and its CI state. A "not met" verdict continues your
> turn; nine in a row with no tool call end it, and the goal waits for the
> user's next prompt. So while CI runs, watch it with a background command,
> such as `gh run watch <id> --exit-status`, rather than answering again.
> Dashpot shows you `waiting` while a goal's verdict keeps you working.

For the skill's Known Dashpot gaps: "A Codex goal turn reads `waiting`. A
turn a goal starts publishes `Stop` but no `UserPromptSubmit`, so once your
workers stop, Dashpot shows you `waiting` while you work."

## Reproduce

Each run needs Node 24, the pinned binary, and this checkout's `.venv`. It
starts no daemon and needs no credentials: a loopback model stands in for
the Responses API or the Messages API. Run each runner detached, from
outside any harness, so that its refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-649/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > codex.log 2>&1'
node scripts/experiments/codex-649/verify.mjs /var/tmp/dashpot-649-codex-SUFFIX/trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>
setsid -f sh -c 'node scripts/experiments/claude-649/run.mjs ~/.local/share/claude/versions/2.1.317 2.1.317 > claude.log 2>&1'
node scripts/experiments/claude-649/verify.mjs /var/tmp/dashpot-649-claude-SUFFIX/trace.jsonl 2.1.317 --strict
```

Each runner prints its fixture root, and the trace is `trace.jsonl` inside
it. The Codex run takes about five minutes, the Claude Code run about four.

- **Isolation.** Each runner refuses to start under a Codex, Claude Code or
  OpenCode process. Its fixture root is a fresh directory under `/var/tmp`,
  outside every Dashpot Project, holding a Dashpot Project whose Issues are
  Local Issue Markdown. The harness gets an isolated `HOME`, configuration
  directory, XDG directories and `TMPDIR`, runs through a symlink on a
  fixture-local `PATH`, and has its updater off. The Codex runner removes
  only the entries its own fixture derives in the shared
  `/tmp/codex-daemon-<uid>/`; the Claude Code runner only counts the
  entries `/tmp/cc-daemon-<uid>/` gains.
- **Hooks.** Every lifecycle event `dashpot integrate` subscribes goes
  through a metadata-only wrapper to Dashpot's real publisher. Between
  steps the runner records what Dashpot's published view shows.
- **Model.** A loopback model follows a fixed plan per directive. The Codex
  fixture tells a goal turn by its request's `turn_trigger` metadata. The
  Claude Code fixture serves the evaluator too: `/goal`'s evaluator runs on
  the model `ANTHROPIC_DEFAULT_HAIKU_MODEL` names, which the runner sets to
  `fixture-evaluator`, so the runner scripts every verdict.
- **Records.** Metadata only: each request's directive kind, markers,
  tool and turn trigger; each evaluator request's shape; the app-server's
  turn and goal notifications; each hook's identity fields; the shells'
  identity; and Dashpot's view. The only text kept is the fixture's own
  labels and verdicts, and the opening words of a message Claude Code
  itself writes, such as a feedback message or a check-in. The fixture root appears as `$ROOT` and the home directory as
  `~`.

The [Codex runner](../../scripts/experiments/codex-649/run.mjs) and its
[verifier](../../scripts/experiments/codex-649/verify.mjs), and the
[Claude Code runner](../../scripts/experiments/claude-649/run.mjs) and its
[verifier](../../scripts/experiments/claude-649/verify.mjs), check every
**measured** claim below without importing the runner or Dashpot. Each
verifier also checks the runner's scripts against the hashes the trace
records, and with `--strict` Dashpot's session modules too. The retained
traces are [the Codex trace](measurements/issue-649-codex-trace.jsonl)
and [the Claude Code trace](measurements/issue-649-claude-code-trace.jsonl).

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-11-03 AEDT |
| Dashpot base | `a47e86862cd4f3f3b4db1841d220ccc46a4b58c2`, with the runners uncommitted |
| Codex | `codex-cli 0.166.0`, the musl standalone release, SHA-256 `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, as one `codex app-server --listen` on loopback |
| Claude Code | `2.1.317`, SHA-256 `eb224419e344575faa4a1f39b290b649425a10cd5ee2ef1d003480cd9ae57eb0`, as `claude -p` with stream-json input |
| Controller | Node `v24.18.0` |
| Operating system | Ubuntu, Linux `7.0.0-38-generic`, x86-64 |
| Models | Codex: `fixture-v2`, a multi-agent v2 catalog model. Claude Code: `fixture-model`, and `fixture-evaluator` for the evaluator. Both served by the loopback fixture |

**Evidence boundary.**

- **Mock model.** The fixture model calls tools on a fixed plan, so the run
  measures what each harness does with those calls, not whether a real
  model makes them: whether a real Codex model calls `create_goal` on the
  skill's instruction, waits in `wait_agent` in each goal turn, or holds off
  `blocked`, and whether a real evaluator judges the condition well.
- **Hosting mode.** Every Codex lead runs on one app-server over a loopback
  WebSocket. Every Claude Code lead is headless, so the interactive idle
  check-ins and the terminal's `/goal` display are documented only.
- **Timings.** workers hold for seconds, not hours, and the Claude Code
  check-in interval is one minute, not the default thirty. Every timing is
  one sample.
- **Not measured.** Codex's usage-limit and execution-unavailable stops,
  an interrupted goal turn, a token budget, and Claude Code's automatic
  retries after a failed evaluation. A Claude Code lead with a `/goal` and
  a `SendMessage` from a worker was not run.
- **Platforms.** macOS, other releases and real models are unmeasured.

## Codex

The runner drives five multi-agent v2 leads. L1 creates its goal with
`create_goal` on a skill's instruction, spawns workers A and B and ends its
turn. Its goal turns wait in `wait_agent` for 30 s while the workers message
and finish, run a command, wait at least four more times for 10 s with no
progress and an empty final message, and then set the goal `blocked`. L2
spawns worker C with no goal and ends its turn; the client sets a goal once
C has messaged and finished. L3 creates a goal and spawns a worker; its
client unsubscribes, later pauses the goal, waits for the unload, sets the
goal active while L3 is unloaded, and resumes it. L4's goal turns answer
empty, and L5's model requests fail.

### Goals are on by default

The fixture configuration names no `goals` feature, and every request,
the workers' included, offered `get_goal`, `create_goal` and
`update_goal` (measured). `goals` is a stable feature, on by default
([`features/src/lib.rs` L2060-L2064](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/features/src/lib.rs#L2060-L2064)),
and the goal tools are hidden only from a review Sub-agent
([`ext/goal/src/extension.rs` L106-L109](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/extension.rs#L106-L109))
(source).

### A skill's instruction and `create_goal`

The fixture skill's body reached the model as a user message, not in its
instructions, and Codex accepted the `create_goal` L1 made on it: the
goal was active before the first spawn (measured). The tool's description
says "Create a goal only when explicitly requested by the user or
system/developer instructions; do not infer goals from ordinary tasks"
([`ext/goal/src/spec.rs` L46](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/spec.rs#L46)),
and `handle_create` checks no such request
([`ext/goal/src/tool.rs` L204](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/tool.rs#L204))
(source). A user-invoked skill's instruction is a user message, so it is an
explicit request by the description's terms (inference).

### Goal turns, and a worker's mail

Every L1 turn after its first was a goal turn: its request carried
`turn_trigger` `goal`, and its input ended with Codex's continuation as a
user message. The first goal turn started as the lead's turn ended, while
both workers still ran (measured; 15 ms later, trace only). The goal
extension's `on_thread_idle` calls `continue_if_idle`
([`extension.rs` L180-L203](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/extension.rs#L180-L203)),
which needs the live thread and calls `start_turn_if_idle` with
`turn_trigger: Some("goal")`
([`ext/goal/src/runtime.rs` L436-L497](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L436-L497))
(source).

A worker's message and its completion started no turn. With the goal, both
reached L1 inside a goal turn's `wait_agent`, which returned "Wait
completed" without timing out. Without one, L2 made no request and started
no turn after worker C messaged and finished; when the client then set a
goal, the first goal turn started at once and carried both C's message and
its completion (measured). A worker's completion is delivered with
`trigger_turn` false
([`core/src/agent/control/completion.rs` L117](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/agent/control/completion.rs#L117)),
and waking on agent messages is an under-development feature, off by
default
([`features/src/lib.rs` L1598-L1603](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/features/src/lib.rs#L1598-L1603))
(source). `wait_agent` waits 30 s by default, from 10 s to an hour
([`core/src/config/mod.rs` L262-L264](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/config/mod.rs#L262-L264))
(source).

### Hooks, and what Dashpot shows

Each goal turn of L1, L2 and L3 ran one `Stop` with its turn ID and no
`UserPromptSubmit`, while each lead's first turn ran both (measured). Only
user input runs `UserPromptSubmit`
([`core/src/hook_runtime.rs` L707-L713](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/hook_runtime.rs#L707-L713)),
and a goal turn's input is a response item (source).

Dashpot showed L1 `running` while its workers ran, which its live
Sub-agents explain. Once both had stopped, it showed L1 `waiting` while a
goal turn's command ran, and it showed L3 `waiting` while an unsubscribed
goal turn's command ran (measured). A lead driven by a goal reads `waiting`
for all its work after the workers stop: a gap the drafted Dashpot Issue
below records (inference).

### Blocking

Four or more L1 goal turns whose `wait_agent` timed out and whose final
message was empty left the goal active. The model's `update_goal` to
`blocked` took effect at once, and no turn started after it (measured;
five turns, trace only). L4's goal was blocked after three automatic turns
with an empty answer and no tool call. L5's was blocked after its one
failed turn, which ran no `Stop` hook (measured).

By source:

- `on_turn_error` maps a usage limit to `UsageLimit` and every other error
  to `TurnError`
  ([`extension.rs` L423-L436](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/extension.rs#L423-L436)).
- `stop_active_goal_for_turn`
  ([`runtime.rs` L277](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L277))
  sets `blocked` for a turn error, an empty response and unavailable
  execution, and `usage_limited` for a usage limit
  ([`runtime.rs` L316-L341](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L316-L341)).
- An automatic turn counts as empty only with no activity and an empty
  final message or an interruption, and three in a row block the goal
  ([`ext/goal/src/accounting.rs` L229-L246](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/accounting.rs#L229-L246)).
  Any tool outcome resets the count and marks the turn active, and an
  `exec` failure counts towards the execution-unavailable stop, also at
  three turns
  ([`accounting.rs` L121-L173](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/accounting.rs#L121-L173)).
  So a goal turn whose `wait_agent` times out is never empty.
- `handle_update` sets `blocked` with no count of turns
  ([`tool.rs` L247-L300](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/tool.rs#L247-L300)).
  The three-turn rule is in the tool's description
  ([`spec.rs` L66, L77](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/spec.rs#L66-L77))
  and the continuation, which also calls a poll of a live handle a
  "verified wait"
  ([`ext/goal/templates/goals/continuation.md` L24, L50](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/templates/goals/continuation.md#L24-L50)).

### An unsubscribed and an unloaded lead

For 80 s after its client unsubscribed, L3 stayed loaded, its goal turns
kept running, and it published no `SessionEnd` (measured; 15 goal turns,
trace only). Once the client paused the goal, the app-server unloaded L3
about 60 s after its last turn, and Dashpot ended its bound run (measured;
60.3 s, trace only). The app-server unloads a thread only once it has had
no subscriber and been inactive for `thread_unload_delay_secs`, 60 by
default
([`app-server/src/request_processors/thread_lifecycle.rs` L28-L100](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L28-L100),
[`core/src/config/mod.rs` L4143-L4144](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/config/mod.rs#L4143-L4144))
(source).

Setting L3's goal active while it was unloaded made no request, loaded
nothing and ran no hook. Resuming it started a goal turn at once, which
Dashpot showed as a new, unbound run (measured). A goal continuation needs
the live thread: without one, `continue_if_idle` logs "skipping goal
continuation because live thread is unavailable"
([`runtime.rs` L460-L463](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L460-L463)).
A resumed thread emits its goal snapshot and then its idle lifecycle,
which continues an active goal
([`app-server/src/request_processors/thread_processor.rs` L4568-L4572](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L4568-L4572))
(source). So #492's source claim holds.

### The 0.160.0 citations at 0.166.0

Each citation #649 makes at `rust-v0.160.0` still holds at
`rust-v0.166.0` (source):

| #649's citation at 0.160.0 | At 0.166.0 |
| --- | --- |
| `extension.rs`: `on_thread_idle` calls `continue_if_idle` | Holds: [`extension.rs` L180-L203](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/extension.rs#L180-L203) |
| `runtime.rs`: `continue_if_idle` calls `start_turn_if_idle` with `turn_trigger: "goal"` | Holds: [`runtime.rs` L436-L497](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L436-L497) |
| A goal only when "explicitly requested by the user or system/developer instructions" | Holds: [`spec.rs` L46](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/spec.rs#L46) |
| `spec.rs`: `blocked` only after three consecutive goal turns | Holds: [`spec.rs` L66, L77](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/spec.rs#L66-L77) |
| `runtime.rs`: `stop_active_goal_for_turn` blocks on a turn error, repeated empty responses and unavailable execution; a usage limit sets `usage_limited` | Holds: [`runtime.rs` L277-L341](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/runtime.rs#L277-L341); the three-turn thresholds are in [`accounting.rs` L155-L246](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/ext/goal/src/accounting.rs#L155-L246) |

## Claude Code

The runner drives three headless leads. C1 binds Issue 1 and sets a goal
phrased as the skill's end, "every fixture worker's pull request is open
and its CI checks are green", whose start turn launches two background
workers, of about 25 s and 70 s. Its evaluator answers "not met" once after
both finish, while the continuation runs a command, and "met" after. C2's
evaluator always answers "not met": its continuations each run a command
twelve times, then answer with text only. C3 sets a one-minute check-in
interval and launches two background workers, of about 80 s and 110 s.

### The evaluator

Each evaluator request went to the model `ANTHROPIC_DEFAULT_HAIKU_MODEL`
names, offered no tool, asked for a JSON schema with `ok`, `reason` and
`impossible`, named all three answers in its system prompt, quoted the
condition verbatim, and quoted the `Stop` hook's input, `background_tasks`
included (measured). The documentation says the evaluator calls no tools,
and that a condition can be up to 4,000 characters (documented). An
evaluator that calls no tools can judge only what the conversation shows,
so a condition about pull requests holds only once the lead's turns have
stated their state (inference).

### Deferral while workers run, and notifications

C1's goal start turn and a notification turn each ended with a worker
still running and no evaluation, and every evaluation came after the last
worker had finished, with an empty `background_tasks` in the hook input. C3 was
evaluated once, after its second worker finished (measured). The
documentation says background work defers evaluation (documented).

Each worker's completion notice started a turn that ran
`UserPromptSubmit`, and Dashpot showed the lead `running` while its
background workers ran (measured).

### Verdicts and Dashpot's turn state

A "not met" verdict continued the turn with "Stop hook feedback:" and the
condition as a user message. It came after the `Stop` hook had run, with
`stop_hook_active` false, and ran no `UserPromptSubmit`, so Dashpot showed
the lead `waiting` while that continuation ran a command. The `Stop` that
ended the continuation carried `stop_hook_active` true (measured). A "met"
verdict cleared the goal: a later prompt in C1 had no evaluation
(measured).

### The block cap

C2 continued through exactly twelve "not met" verdicts, one after each command.
Nine in a row with no tool call then made Claude Code end the turn with the
notice "A hook blocked the turn from ending 9 consecutive times"
(measured). That notice names `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` as the
setting that raises it (trace only). The goal survived: C2's next prompt
was evaluated again. An "impossible" verdict then cleared it, and the
prompt after had no evaluation (measured). The documentation describes
the same stop as Claude answering "without making progress (no tool use
for several turns in a row)", after which evaluation resumes with the next
prompt (documented).

### Check-ins

With `CLAUDE_CODE_GOAL_CHECKIN_MINUTES` at 1, C3 made no lead request in
the 80 s before its first worker finished. The notification turn that then
ended with the second worker still running was continued by a user message
opening "Goal check-in:", the condition, "is still active, and evaluation
has been deferred for 1", after its `Stop` hook and with no
`UserPromptSubmit` or evaluation. No further check-in came in the 30 s
before the second worker finished (measured). The documentation says a
check-in is due after 30 minutes deferred by default, each later one
waiting twice as long, up to four times the first interval, that a `-p` session gets one only "at the end of
the next turn that finishes with the work still running", and that an
interactive session gets at most three idle check-ins between prompts
(documented).

### Unbound leads

C2 and C3 bound no Issue, and Dashpot showed each as an unbound run
(measured).

## Follow-ups

- The skill change: the drafted wording above, in a follow-up Issue.
- A Dashpot Issue: a Codex goal turn, and a Claude Code goal continuation
  or check-in, read `waiting` while the Lead works. Codex publishes `Stop`
  and no `UserPromptSubmit` for a goal turn; Claude Code continues a turn
  after `Stop`.
- The research note's
  [stale instruction](../research/harness-arc-orchestration-research.md#stale-instructions-in-the-harness-reference)
  "never starts a turn for an idle lead" is now measured: without a goal,
  it holds; with one, it does not.

## Validation

Each retained trace passed its verifier in its minimal form, and with
`--strict` (and, for Codex, `--codex-source` at a `rust-v0.166.0`
checkout): 11 measured claims, and 14 with the source claims, against 467
Codex records; 10 claims against 288 Claude Code records. Every
script and Dashpot module each trace names matched the hash the run
recorded. The verifiers check only the form of each binary's SHA-256; the
values above are the ones the traces record. Every hook reached Dashpot's
publisher, which exited 0. Neither run left a fixture process. The shared
`/tmp/codex-daemon-<uid>/` held no entry derived from the Codex fixture
before or after its run, and `/tmp/cc-daemon-<uid>/` gained no entry
during the Claude Code run.
