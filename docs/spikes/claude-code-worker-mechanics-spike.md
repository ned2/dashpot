---
status: research
date: 2026-10-04
---

# Claude Code worker mechanics experiment

The experiment for [Issue #419](https://github.com/ned2/dashpot/issues/419),
part of [#403](https://github.com/ned2/dashpot/issues/403), measures the worker
mechanics a `dashpot-execute-issues` lead would rely on under **Claude Code
2.1.287**, the release the acceptance run is pinned to. A lead is a Claude Code
session. In this document a **worker** is one of the lead's background
Sub-agents, started with the `Agent` tool, that works on one Issue in an
Issue Worktree. It is not the `--bg` supervisor's worker process of earlier
spikes. Every question the Issue asks was measured in a disposable fixture.
Each answer is marked **measured** (checked by the verifier against the
retained trace), **documented** (read from the harness's own tool schema or
text, recorded in the trace but not exercised), or **unknown**.

In short:

- **Launching and reporting.** A worker starts in the background, and the
  lead's turn goes on. A worker can report to the lead mid-flight with
  `SendMessage` to `main`. Its completion reaches the lead as a
  `<task-notification>` carrying the worker's final message, and that wakes an
  idle lead. `SendMessage` to a finished worker's agentId resumes it with its
  transcript. All of this behaves the same in the three launch modes
  measured for it: headless stream-json, `-p`, and an interactive terminal.
- **One Agent Session.** Dashpot attributes a worker to the lead's Agent
  Session and Agent Run. The lead reads `running` while a worker works, and
  Cleanup's `sub-agent` blocker holds until SubagentStop.
- **Location.** A worker cannot move the session with `EnterWorktree`, and a
  worker's `cd` lasts only for that command.
- **Workers that stop without a SubagentStop.** Two paths stop a worker
  without the SubagentStop Dashpot waits for, so the `sub-agent` blocker and
  the lead's `running` state stay up until the session ends. This document
  calls that a **strand**:
  - a headless SDK interrupt;
  - the lead's own `TaskStop`.

  After an interrupt the lead model is told nothing about the stopped worker.

## Reproduce

The experiment needs Node, util-linux `script` for the terminal launches,
the retained Claude Code release at
`~/.local/share/claude/versions/2.1.287`, and this checkout's `.venv` from
`uv sync --locked --group dev`. Run the runner outside every Claude Code
session. It refuses to start below one, because Dashpot would treat that
session as the host of every fixture process.

```bash
setsid -f node scripts/experiments/claude-419/run.mjs ~/.local/share/claude/versions/2.1.287 > /tmp/claude-419.log 2>&1
node scripts/experiments/claude-419/verify.mjs /tmp/dashpot-claude-419-SUFFIX/trace.jsonl --strict
```

Replace the trace path with the one the runner's log prints. The run takes
about ten minutes. `SPIKE_SCENARIOS` runs a comma-separated subset of
scenarios, and a second argument names another expected `claude --version`.
The verifier reports any Dashpot source the trace hashes that has changed
since the run, and `--strict` fails on one.

- **The [runner](../../scripts/experiments/claude-419/run.mjs).** It builds a
  fixture under a fresh temporary root:
  - a Dashpot Project with a markdown Issue Source of twelve Issues;
  - its main Worktree, where every lead starts;
  - a linked Worktree, `sibling`;
  - an isolated home whose `CLAUDE_CONFIG_DIR` is that home's `.claude`.

  It subscribes the hook events `dashpot integrate claude-code` subscribes,
  read from this checkout's `integrate.py`. A
  [hook wrapper](../../scripts/experiments/claude-419/hook.mjs) passes every
  event to this checkout's real `dashpot-claude-code-hook` publisher and
  records it.

  It copies the bundled `dashpot-issue-work` skill and two fixture skills into
  the skills directory `integrate` installs into. One fixture skill sets
  `disable-model-invocation: true`.

  A loopback Messages API stands in for the model. It emits the tool calls
  that the `SPIKE:<label>` in the latest labelled user message selects. A
  worker's final message, and each message the lead or a worker sends,
  carries the next label, so each delivery starts the reaction it names. Gate
  files, opened by the runner, hold a worker or a lead in a known state while
  Dashpot observes it.
- **The [fixture command](../../scripts/experiments/claude-419/command.mjs).**
  This is the Bash command the fixture model runs. It records the shell's
  directory, its Claude Code identity variables and its process ancestry. It
  either holds on a gate or runs this checkout's `dashpot work`. After each
  step of interest the runner records `dashpot --json`'s Agent Runs and
  `dashpot worktree check --json` on the sibling.
- **The [independent verifier](../../scripts/experiments/claude-419/verify.mjs).**
  It checks the 66 claims below against the trace without importing the
  runner. It also checks that the runner, hook wrapper and command that wrote
  the trace are the ones retained beside it, and with `--strict` that the
  Dashpot sources the trace hashes are unchanged.
- **The [retained trace](measurements/issue-419-claude-trace.jsonl).** It is
  the complete metadata stream of the successful run: 1,089 records.
  - Its first record names the release, the hook subscriptions, the skills
    directory, and the SHA-256 of the runner files and of the Dashpot sources
    exercised. The verifier checks the runner files. Those Dashpot sources
    move on after the run, so it reports a changed one and fails on it only
    under `--strict`.
  - Prompts and transcripts stay out of it. It keeps the fixture's labels
    and marks, and bounded excerpts of fixture-only output:
    - the first 240 characters of each delivered harness wrapper;
    - 600 of each watched tool's result;
    - 200 of a task notification's result, and 120 of a stream result;
    - 300 of the `Agent` tool's `run_in_background` description;
    - 700 of a terminal's last screen;
    - up to 2,000 of `dashpot work` output and of hook-publisher output;
    - 300 to 500 of observation diagnostics and Cleanup obstacle details;
    - 1,000 of `claude agents`, `stop`, `rm` and `daemon` output.
  - The fixture root, this checkout and the operator's home appear as `$ROOT`,
    `$CHECKOUT` and `$HOME`.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-04 AEST |
| Dashpot base | `29f61cc400e82d36cf3dba8a2f0ef125c82bbde8`; the trace's `dashpotHead` is a working commit on it that added only this experiment's files |
| Claude Code | `2.1.287 (Claude Code)`, the retained native build, `DISABLE_AUTOUPDATER=1`, `--dangerously-skip-permissions`, model `fixture-model` |
| Launches | headless `-p --input-format stream-json`, single-prompt `-p`, interactive under `script`, and `--bg` under the transient supervisor |
| Configuration | an isolated home with `CLAUDE_CONFIG_DIR=$HOME/.claude`, the default layout; hooks as `integrate` subscribes them; skills in `$HOME/.claude/skills` |
| Operating system | Ubuntu 26.04.1, Linux `7.0.0-34-generic`, x86-64 |
| Controller | Node `v24.18.0` |

The model is a fixture. It emits exactly the tool calls the scenario names,
so the trace shows what Claude Code does with those calls, not what a real
model would choose. What a real model reads is recorded as the wrapper text
the harness put in the next request.

All workers are `general-purpose` Sub-agents launched with
`run_in_background: true`. The `Agent` tool's parameters, recorded from the
schema 2.1.287 sends, are `description`, `prompt`, `subagent_type`, `model`,
`run_in_background` and `isolation`. There is no `name`, so the fixture
addresses workers by agentId.

Not measured:

- a non-default `CLAUDE_CONFIG_DIR`;
- agent teams;
- `isolation: "worktree"` or `"remote"`;
- a lead that is itself inside a linked Worktree;
- launch, report and resume from a `--bg` lead, which was used only for the
  session-end rows;
- the default concurrency cap's value, beyond three workers running at once;
- a worker's `work stop` or `work relocate`;
- releases other than 2.1.287.

## 1. Launch

**Measured.** The lead calls `Agent` with a description, the prompt and
`run_in_background: true`. **Documented:** the schema's own description of
`run_in_background` begins "Agents run in the background by default". The
call returns at once:

```text
Async agent launched successfully. … agentId: <17-character id> (internal ID - do not mention to user. Use SendMessage with to: '<id>', summary: '<5-10 word recap>' to continue this agent.)
```

SubagentStart fires with that id as `agent_id`. The lead keeps control: in
each of headless stream-json, `-p` and the interactive terminal, the lead's
next tool call ran and its turn stopped while the worker was still held at
its first step.

Three `Agent` calls in one lead step ran three workers at once under the
default cap, whose value was not measured. With `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=2`, two workers ran
and the third call failed:

```text
Concurrent subagent limit reached. You can run 2 subagents at once. Do not retry. If the user wants more concurrent subagents, ask them to increase CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS.
```

A lead that dispatches more workers than the cap must queue the rest and
launch each one as a running worker completes.

## 2. Mid-flight report

**Measured.** A worker's `SendMessage` with `to: "main"` returns
`Message queued for the main conversation's next turn.`, and the worker goes
on with its next step. How the message arrives depends on what the lead is
doing.

- **An idle lead gets a new turn.** The turn opens
  `Another Claude session sent a message:` followed by
  `<agent-message from="<agentId>">…</agent-message>`. UserPromptSubmit fires
  for it.
- **A lead in a tool call gets it at its next tool round, inside the same
  turn.** It is added to the next request after the tool's result, opening
  `Another Claude session sent a message while you were working:`. In the
  measured run the worker had also finished by then. One added message
  carried both the report and the completion's `<task-notification>`.
  UserPromptSubmit fired once for each, although no turn started, and the
  lead's turn stopped once.
- **The lead can message a running worker the same way.** `SendMessage` with
  the agentId returns
  `Message queued for delivery to <agentId> at its next tool round.`. The
  worker receives `The coordinator sent a message while you were working:`
  between two of its tool calls.

The idle-lead report and the lead's message to a running worker held in
headless stream-json, `-p` and the interactive terminal. The busy-lead case
was measured headless and interactive.

## 3. Completion

**Measured.** When a worker's turn ends, SubagentStop fires with its
`agent_id`. An idle lead wakes with a new turn holding a
`<task-notification>` with these fields:

- `task-id`: the agentId;
- `status`: `completed`;
- `summary`: `Agent "<description>" finished`;
- `result`: the worker's final message, verbatim;
- an `output-file` path.

A busy lead gets the same notification at its next tool round, as section 2
describes. Headless and `-p` hosts also see `system/task_started`,
`task_progress`, `task_updated` and `task_notification` messages on the SDK
stream.

A `-p` process, and a headless one whose stdin is closed, stays up until
its background workers finish. It lets the lead handle their notifications,
then exits with SessionEnd reason `other`.

## 4. Resume

**Measured.** `SendMessage` to a finished worker's agentId returns
`{"success":true,"message":"Resuming agent <first 7 characters>","resumedAgentId":"<agentId>",…}`.
After that:

- SubagentStart fires again with the same `agent_id`.
- The worker's next request carries its whole earlier transcript plus the new
  message, which arrives as `The coordinator sent a message while you were
  working:`.
- When the worker finishes again, a second `completed` notification follows.

This held in headless stream-json, `-p` and the interactive terminal.

## 5. Shared Agent Session

**Measured.** Dashpot attributes a worker to the lead's Agent Session and
Agent Run.

- **Shell identity.** A worker's shell carries the lead's
  `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`, and its parent is the lead's
  `claude` process. `dashpot work show` from the worker reports the lead's
  run, including the worker itself as a listed sub-agent.
- **`work start` from the sibling Worktree is refused** (exit 2), the case
  [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md)
  describes of a sub-agent sharing its session's key while the session's
  hooks fire from elsewhere:

  ```text
  dashpot: claude-code pid <pid> is at $ROOT/repository according to its freshest Claude Code hook record, not at $ROOT/repository.worktrees/sibling; Issue work is declared where the session itself runs (a tool call that changes directory, or a sub-agent, does not move the session), so nothing was written
  ```

- **`work start` where the lead is succeeds**, and it switches the whole
  session's Issue work: `switched from issue-1 to issue-3 (I_fixture_3)`. A
  worker sharing the lead's directory is not stopped by the refusal. Only the
  rule that `start` and `stop` belong to the main session protects the lead's
  Issue Binding.
- **The lead reads `running`** in `dashpot --json` while a worker works, even
  when its own turn has stopped.
- **Cleanup's `sub-agent` blocker** holds on the sibling while a worker is
  live
  ([ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
  It clears after the worker's SubagentStop, and the lead's state drops back
  to `waiting`.

## 6. Location

**Measured.** A worker's shell starts in the lead's directory.
`cd <worktree> && …` works for that one command. The worker's next command
starts in the lead's directory again, so every command in a worker's brief
needs its own `cd`.

A worker cannot move the lead's session or Agent Run with the worktree
tools, because Claude Code refuses them from a sub-agent:

- **`EnterWorktree` by path** to the sibling:
  `Cannot enter worktree: the current working directory $ROOT/repository is
  the repository root, not an isolated worktree — switching is only
  available to sessions whose working directory is inside a worktree of this
  repository.`
- **`EnterWorktree` by name:** `EnterWorktree cannot create a worktree from a
  subagent with a cwd override (isolation: "worktree" or explicit cwd) — it
  would mutate the parent session's process-wide working directory. To work
  in a different directory (including a worktree), spawn an Agent with
  `cwd` set to it.`
- **`ExitWorktree(keep)`** is refused the same way.

After these refusals the lead was still at the main Worktree, and its run
there was unchanged.

The one way a worker can move the session's Issue work is the `work start`
of section 5. The path-based refusal comes from a lead in the main Worktree,
and a lead inside a linked Worktree was not measured.

**Documented**, from the recorded `Agent` schema: `isolation: "worktree"`
gives a worker a Claude-managed temporary worktree rather than an Issue
Worktree. It was not exercised.

## 7. Interruption, and session end or delete

**Measured.** Each case below starts with the worker held mid-step.

| What happens to the lead | Worker | Hooks | What the lead model is told | Dashpot |
| --- | --- | --- | --- | --- |
| Headless SDK `control_request` interrupt | Stopped | No SubagentStop and no Stop. The SDK stream gets `task_notification` with status `stopped`, and the interrupted turn's result has subtype `error_during_execution` | Nothing about the worker. Its next turn says only `[Request interrupted by user for tool use]` | `running` and the `sub-agent` blocker stay until SessionEnd, which clears both |
| Interactive Esc | Keeps running and finishes | SubagentStop | A `completed` notification wakes it | Clears on SubagentStop |
| The lead's `TaskStop`, headless or interactive | Stopped | No SubagentStop | The tool result `Successfully stopped task: <id> (<description>)`, then a new turn with a notification of status `killed` and summary `Agent "<description>" was stopped by Claude`, with no `result` | `running` and the `sub-agent` blocker stay until SessionEnd, which clears both |
| Headless stdin closed | Finishes, then the process exits | SubagentStop, the lead's completion turn, then SessionEnd `other` | A `completed` notification | Clears |
| Interactive `/exit`, left unanswered | Keeps running and finishes | SubagentStop; no SessionEnd while the dialog is up | — | The blocker clears on SubagentStop; the session stays up |
| `/exit`, then "Exit and stop tasks" | Stopped | SessionEnd `prompt_input_exit` | — | Clears |
| `/exit`, then "Move to background and exit" | Stopped. It is not carried into the forked session | SessionEnd `prompt_input_exit` for the original session. SessionStart `fork` for a new session id under a transient supervisor | The fork's first turn holds a notification of status `failed` and summary `Background agent "<description>" didn't finish before the previous session ended` | The original run ends and its Work Store record is removed. The fork is a separate, unbound Agent Session, as [ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md) expects of a fork, and `work show` in it reports `no active Issue work at this worktree` |
| Terminal closed (`script` killed) | Stopped | SessionEnd `other` | — | Clears |
| `claude stop <id>` on a `--bg` lead | Stopped. The job is listed as stopped | SessionEnd `other` | — | Clears |
| `claude rm <id>` on a running `--bg` lead | Stopped. The job leaves `claude agents` | SessionEnd `other` | — | Clears |

The `/exit` dialog reads `Background work is running … 1. Exit and stop
tasks 2. Move to background and exit 3. Stay`.

**Fallback.**

- A headless SDK host that interrupts a lead must relay the `stopped` task
  notification itself, or the lead must treat a worker it never hears from
  again as a blocker hand-back.
- A lead should end a worker by letting its turn finish, not with `TaskStop`.
  If it does use `TaskStop`, it should expect the `killed` notification and
  the strand described under Dashpot findings below.

## 8. Skill loading and `disable-model-invocation`

**Measured.** Claude Code loads skills from `$HOME/.claude/skills`, the
directory `dashpot integrate claude-code` installs into, for leads and
workers alike.

- **Listing.** Both see `dashpot-issue-work` and the model-invocable fixture
  skill listed.
- **Model invocation.** The model loads the model-invocable fixture skill and
  `dashpot-issue-work` through the `Skill` tool (`Launching skill: <name>`),
  in a lead and in a worker.
- **User-only skills.** A skill whose frontmatter sets
  `disable-model-invocation: true` is not listed to the model, and the
  `Skill` tool refuses it:

  ```text
  Skill fixture-user-skill cannot be used with Skill tool due to disable-model-invocation. Ask the user to run /fixture-user-skill themselves — it cannot be invoked via the Skill tool. Do not replicate this skill's workflow by other means — it is reserved for explicit user invocation.
  ```

  A user's `/fixture-user-skill` loads its body, both headless and in the
  interactive terminal.

`disable-model-invocation: true` is therefore how `dashpot-execute-issues`
is made user-invoked only under Claude Code.

## Dashpot findings

These are the Dashpot findings. None needs a `src/` change in this Issue.

- **The `sub-agent` blocker's wording.** For Claude Code, the wording from
  `unreported_subagent_stop`, which the `sub-agent` blocker and `work show`
  share, is accurate for the headless-interrupt strand: `…which an
  interrupted one may never do, so if none is still working, end that
  session.` It names the remedy, and the measured SessionEnd clears both the
  run's `running` state and the blocker.
- **Two wording gaps,** filed as
  [#429](https://github.com/ned2/dashpot/issues/429):
  - the same strand follows the lead's own `TaskStop`, which "interrupted"
    does not name;
  - the function's docstring cites only Codex's interrupt case.
- **A worker the lead stops with `TaskStop` leaves the `sub-agent` blocker up
  until SessionEnd,** and the lead's state stays `running` until then. No
  hook reports the stop.
- **"Move to background and exit" ends the lead's Issue Binding.** Claude
  Code resumes the conversation under a new session id. Dashpot treats the
  graceful SessionEnd and the fork's new identity consistently, as
  [ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
  intends, so this is not a Dashpot defect.

## Guidance for the execute-issues skill

For [#422](https://github.com/ned2/dashpot/issues/422):

- **Launch and capacity.**
  - Launch each worker with `Agent` in the background, and address it by the
    agentId from the result.
  - Keep no more workers running than `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`
    allows, and queue the rest.
- **Messages.**
  - Workers report mid-flight with `SendMessage` to `main`, and their final
    message is the hand-back.
  - The lead resumes a finished worker with `SendMessage` to its agentId.
- **Endings that are not completions.**
  - Treat a `stopped`, `killed` or `failed` notification as a worker
    hand-back to redispatch.
  - Treat a worker that never reports after a headless interrupt the same
    way.
  - Avoid `TaskStop`, or expect the `sub-agent` strand until the session
    ends.
- **Worker briefs.**
  - Give every shell command its own `cd <worktree> && …`.
  - Never let a worker run `work start` or `work stop`, which act on the
    lead's session.
  - Never let a worker use the worktree tools, which Claude Code refuses
    from a sub-agent anyway.
- **Exiting.** At `/exit` with workers running, choose "Exit and stop tasks"
  or "Stay". After "Move to background and exit", run `work start` again in
  the forked session.
- **Making the skill user-only.** Give `dashpot-execute-issues`
  `disable-model-invocation: true`.

## Validation

The verifier passes all 66 claims against the retained trace with
`--strict`:

```text
66 claims verified against 1089 records.
Dashpot sources match the run's.
```

The run was taken at `29f61cc`, which already holds
[PR #417](https://github.com/ned2/dashpot/pull/417). The branch was then
rebased onto `34493dd`, which adds only the Codex spike's documents and
scripts, so every Dashpot source the trace hashes is unchanged there and
`--strict` reports none.

The run completed every scenario, every hook reached the publisher and
succeeded, and no fixture process outlived it.

The runner stops the transient supervisor its background scenarios start
with `claude daemon stop --any` in the fixture's environment. That removes
the supervisor's own directory under `/tmp/cc-daemon-<uid>/`. A listing
taken by hand after the run, not recorded in the trace, held no entry from
it.
