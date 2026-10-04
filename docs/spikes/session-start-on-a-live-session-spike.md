---
status: research
date: 2026-10-04
---

# SessionStart on a live session experiment

The experiment for [Issue #448](https://github.com/ned2/dashpot/issues/448)
measures which `SessionStart` each harness publishes for a session that is
still live, with no `SessionEnd` before it, while a Sub-agent the session
delegated to is still working. Until #448, Dashpot's hook record started a
session's live Sub-agent list over, empty, on every such `SessionStart`
([ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)),
so a working Sub-agent stopped blocking Cleanup and stopped holding the
session running. [ADR 0097](../adr/0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
records the decision the measurements support.

Each harness ran in a disposable fixture against a loopback model fixture
with an isolated configuration and its updater off, launched with `setsid -f`
outside every harness process, as the
[agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires. Every
hook went to Dashpot's real publisher, and each run recorded the hook record
Dashpot stored after every write. In every scenario the session first
started a Sub-agent whose shell held a gated command open across the action,
so the Sub-agent was demonstrably still working when the action ran. Each
trace is metadata only, with paths rewritten to placeholders, and each
experiment's `verify.mjs` checks the claims below against it.

In short:

- **Claude Code 2.1.289 and Codex 0.160.0 compact a live session with a
  `SessionStart` whose `source` is `compact`**: the same session id, the same
  Host Process, no `SessionEnd` first. The Sub-agent works on across it and
  its `SubagentStop` follows on the same session. This is the case #448 fixes.
- **OpenCode 2.0.22 publishes nothing Dashpot writes as `SessionStart` when
  it compacts.** Its compaction runs inside an execution, so the root's
  record carries its Sub-agents through it unchanged.
- **No other `SessionStart` reaches a live record of the same Host Process
  and the same session id** in the measured scenarios. A switch of
  conversation (`/clear`, `/resume`, `/branch`, `/new`) starts another
  session id, and a second Host Process is another process.

## Claude Code 2.1.289

Runner [`claude-448`](../../scripts/experiments/claude-448/), trace
[`issue-448-claude-trace.jsonl`](measurements/issue-448-claude-trace.jsonl)
(424 records, SHA-256
`5823a804607b5fbead087bf7bad2047c5173fc64e7d3da5e4bdc49ce4f47d63e`). The
publisher ran Dashpot `b08e762`, the base of #448, exported into the fixture,
except in the scenario `compact-worktree`, which ran #448's `hook_records.py`
(SHA-256 `2fa71614…ad82`). Receipt numbers below are the trace's.

- **`compact`, a manual `/compact` in an interactive session (measured).**
  `PreCompact` (`manual`), then a `SubagentStop` for the compaction's own
  summarizer, an `agent_id` with `agent_type` `""` that never had a
  `SubagentStart` (#18), then `SessionStart` `compact` on the same session
  from the same pid (#19), then `PostCompact`. No `SessionEnd`, and no
  `UserPromptSubmit` or `Stop` for the command. Dashpot `b08e762` stored
  `running` with no Sub-agents at #19 while the worker still held its
  command (#22). The worker's `SubagentStop` (#32) then found nothing to
  remove. Its completion notification is the session's next turn (#33, #35).
- **`compact-worktree`, the same with #448's store (measured).** The
  `SessionStart` `compact` (#66) stored `running` with the worker listed; its
  `SubagentStop` (#79) removed it.
- **`headless-compact`, `/compact` over stream-json (measured).** The same
  order as the interactive session (#312–#316); the worker stopped on the
  same session (#336).
- **`auto-compact` (measured).** The fixture reported 199 000 input tokens on
  a mid-turn response. `PreCompact` (`auto`), the summarizer's `SubagentStop`,
  `SessionStart` `compact` on the same session and pid (#115), `PostCompact`,
  then the same turn's `Stop` (#119) with no new prompt. Dashpot `b08e762`
  stored `waiting` with no Sub-agents while the worker still worked (#121).
- **`clear`, `/clear` (measured).** `SessionEnd` `clear` (#162), then
  `SessionStart` `clear` with a new session id from the same pid (#163). The
  worker survives and reports under the new id: its model requests and its
  shell carry the new id, and its `SubagentStop` (#174) names it. The old
  session's ended record, which
  [ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)
  keeps for the worker, is never cleared by that stop and stays until the
  process exits. `headless-clear` behaves the same (#380–#398).
- **`resume-switch`, `/resume <id>` (measured).** `SessionEnd` `resume` (#217),
  then `SessionStart` `resume` naming the other session, same pid (#218). The
  worker follows to that session (#229).
- **`branch`, `/branch` (measured).** `SessionEnd` with reason `resume`, not
  `fork` (#261), then `SessionStart` `fork` with a new id, same pid (#262).
  The worker follows to the new id (#273).

A manual `/compact` publishes no `Stop`, so a session that was waiting reads
`running` from its `SessionStart` until its next turn ends. That holds with
or without Sub-agents and is unchanged by #448.

Not measured: `/resume` through the interactive picker, `/fork`, which uses
the shared background daemon, and how observation reports the stranded ended
records after their process exits.

## Codex 0.160.0

Runner [`codex-448`](../../scripts/experiments/codex-448/), trace
[`issue-448-codex-trace.jsonl`](measurements/issue-448-codex-trace.jsonl)
(247 records, SHA-256
`81ba2a4d2444b175af2fba2d92e1514e6526c0ff5d562dbcb3290af758fe1c02`). The
publisher ran #448's `hook_records.py` (SHA-256 `2fa71614…ad82`). A
standalone terminal (pid 24542) and a daemon (pid 33862) hosted the
leads; each lead's worker was a v2 Sub-agent.

- **`compact`, manual (measured).** A standalone terminal's `/compact`
  published `PreCompact` and `PostCompact` (#18, #20) and nothing else until
  the next prompt, whose turn opened with `SessionStart` `compact` on the
  same session and Host Process (#23), then `UserPromptSubmit` (#24). The
  daemon's `thread/compact/start` behaved the same: `SessionStart` `compact`
  (#79) only at the next `turn/start`. No `SessionEnd` either way, and each
  worker stopped on the same session afterwards (#46, #90).
- **`auto-compact` (measured).** With `model_auto_compact_token_limit=5000`,
  automatic compaction ran mid-turn and published `SessionStart` `compact`
  inside the turn with no prompt before it (#106); the turn's `Stop`
  followed (#114). Same session and daemon, no `SessionEnd`; the worker's
  `SubagentStop` came at #128.
- **`clear` and `new` (measured).** A standalone `/clear` published
  `SessionStart` `clear` on a new session id from the same process (#31),
  with no `SessionEnd` for the old session, whose worker stopped on the old
  session (#46) and which ended with the terminal (#50). On the daemon,
  `/new` published `SessionStart` `startup` (#145) and `/clear`
  `SessionStart` `clear` (#162), each on a new thread; each old worker
  stopped on its old session (#184, #188), and each old thread ended about
  61 s later, as an unload does (#185, #191).
- **`second-client-resume` (measured).** A second client's `thread/resume` of
  a loaded thread (#207) and a terminal `codex resume --remote` (#217)
  published no `SessionStart`; the thread's only one was its startup (#197).

With #448's store, every `SessionStart` `compact` (#23, #79, #106) stored the
worker still listed and the session `running`; each `SubagentStop` emptied
the list. New `startup` and `clear` sessions began with none.

The terminal client also sends each prompt to a second thread with its own
id that publishes no hooks; its purpose was not established. Not measured: a
`/compact` typed into a daemon-attached terminal, and a worker running
longer than about 60 s across a compaction.

## OpenCode 2.0.22

Runner [`opencode-448`](../../scripts/experiments/opencode-448/), trace
[`issue-448-opencode-trace.jsonl`](measurements/issue-448-opencode-trace.jsonl)
(1180 records, SHA-256
`7292c54f09e3192384de10df5892aa3472aa85d6b958f5c681fa368c81a458b1`). The
publisher ran #448's `hook_records.py` (SHA-256 `2fa71614…ad82`). A fixture plugin recorded the raw OpenCode
events beside Dashpot's.

- **`compact`, `compact-busy`, `auto-compact`, `overflow-compact`
  (measured).** Manual compaction of an idle root ran as an execution of the
  root (#87–#92); one requested during the root's turn was steered into it
  (#211–#221); automatic compaction near the context limit (#348, #350) and
  after a provider's `context_length_exceeded` (#487, #489) ran inside the
  execution. Dashpot's plugin does not report the compaction events, so
  Dashpot wrote only `UserPromptSubmit` and `Stop` for the root. Each kept
  the child listed and the `sub-agent` blocker present (#97, #224, #360,
  #498) until the child's `SubagentStop`.
- **Fork, client prompts, TUI attach, reload (measured).** A fork wrote
  `SessionStart` for the fork's own id only (#619). A client's `opencode run
  --session` and a TUI attaching to the root wrote no `SessionStart` (#634,
  #660), nor did `opencode reload` (#794). The root kept its child listed
  throughout.

Two measured cases do drop a working child, neither through a same-process
`SessionStart` on the same record, and #448 leaves both as they are:

- **A move to another Project.** The root's next publication after
  `session.moved` wrote `SessionStart` and `Stop` in the other Project's
  store with no Sub-agents, from the same Host Process (#951), while the
  record left in the first store keeps the child listed and `running` (#1020).
- **A second Host Process.** `opencode run --standalone --session <root>`
  wrote `SessionStart` naming its own process with no Sub-agents (#1108)
  while the service's child still worked, and its exit marked the record
  unobserved, after which Cleanup showed no `sub-agent` blocker (#1128).

Not measured: the TUI's `/new` and `/compact` keystrokes, a service restart,
a failed compaction, and two services sharing a data directory.

## Reproduce

From a checkout of the Worktree, outside every harness process. The Claude
Code runner exports the checkout's committed HEAD as its base publisher and
runs the working tree's in `compact-worktree`, so these runs had HEAD at
`b08e762` with #448's changes uncommitted; after #448 lands, HEAD's
publisher is #448's, and the base scenarios' checks fail. The OpenCode
runner exports HEAD too, and these runs set `SPIKE_DASHPOT_SOURCE=worktree`
and a private `TMPDIR`:

```sh
setsid -f node scripts/experiments/claude-448/run.mjs ~/.local/share/claude/versions/2.1.289 > claude-448.log 2>&1
setsid -f node scripts/experiments/codex-448/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/bin/codex 0.160.0 > codex-448.log 2>&1
SPIKE_DASHPOT_SOURCE=worktree TMPDIR=<private dir> setsid -f node scripts/experiments/opencode-448/run.mjs ~/.opencode/bin/opencode > opencode-448.log 2>&1
```

Each prints its fixture root; its `trace.jsonl` is checked with the same
experiment's `verify.mjs`:

```sh
node scripts/experiments/claude-448/verify.mjs docs/spikes/measurements/issue-448-claude-trace.jsonl --strict
node scripts/experiments/codex-448/verify.mjs docs/spikes/measurements/issue-448-codex-trace.jsonl 0.160.0 --strict
node scripts/experiments/opencode-448/verify.mjs docs/spikes/measurements/issue-448-opencode-trace.jsonl --strict
```

`--strict` also fails once a Dashpot source the run hashed has changed since.
The Claude Code runner hashes both publishers it ran, `b08e762`'s
`hook_records.py` (SHA-256 `20c68f27…5105`) and #448's.
