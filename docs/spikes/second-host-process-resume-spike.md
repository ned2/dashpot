---
status: research
date: 2026-10-05
---

# Second Host Process resume experiment

The experiment for [Issue #460](https://github.com/ned2/dashpot/issues/460)
measures whether Codex has the gap
[#448](https://github.com/ned2/dashpot/issues/448) found in OpenCode: a
second Host Process takes on a session whose Sub-agent the first process
still runs, and Dashpot's `sub-agent` Cleanup blocker goes while the
Sub-agent works
([OpenCode's order](session-start-on-a-live-session-spike.md)). The Codex
case is a terminal resuming a lead the managed daemon hosts while the lead's
worker runs long commands in the daemon.
[ADR 0107](../adr/0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)
records the decision for the OpenCode order and cites these results.

The run used:

- a disposable directory outside every Dashpot Project, a Repository in it
  with one linked Worktree, and a loopback Responses API fixture;
- an isolated `CODEX_HOME`, with the daemon's updater off
  (`updater.autoUpdateEnabled=false`);
- the pinned release, run read-only through a fixture-local `PATH`
  symlink;
- the runner launched with `setsid -f` outside every harness process, as the
  [agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires.

Every hook went through a metadata wrapper to a Dashpot publisher built from
a named source and installed outside every Worktree. The scenario ran once
per publisher: `base`, built from `ff2c1c4`, the #460 branch's base, and
`fix`, built from the #460 branch at `fb2e727`. After each step the run
recorded the stored hook record and what `dashpot worktree check` reported
for the linked Worktree. The trace is metadata only, with paths rewritten to
placeholders. [`verify.mjs`](../../scripts/experiments/codex-460/verify.mjs)
checks the claims below against it.

## Codex 0.160.0

Runner [`codex-460`](../../scripts/experiments/codex-460/), trace
[`issue-460-codex-trace.jsonl`](measurements/issue-460-codex-trace.jsonl)
(219 records, SHA-256
`28b6db7650004f7d0c10791d26227b4732b2303aaead8087e1b4503cdf8bed18`). The
`base` publisher's `sessions/hook_records.py` was at SHA-256
`0c232451…91ff`, `sessions/hook_publish.py` at `dd1c5a3e…32f8` and
`sessions/hook_scan.py` at `2a9490d6…3b72`; the `fix` publisher's were at
`3f273b3b…fc63`, `75465b66…4b81` and `b6657ab2…beea`. The #460 branch
changed `hook_records.py`, `hook_publish.py`, `hook_scan.py` and
`agents.py` after the run, in behaviour only where no scenario here
reaches: a sub-agent of a process the publisher did not probe now carries,
while every sub-agent here runs in the daemon, the event's own process. The
rest removed an unused helper and moved code without changing it. So
`verify.mjs --strict` reports that drift. Receipt
numbers below are the trace's, from the `base` scenarios unless named.

- **Setup, each scenario.** A plain terminal started the managed daemon's
  lead (`SessionStart` `startup` from the daemon's process, #12). The lead
  spawned a multi-agent v2 worker in the linked Worktree (#17), whose six
  15-second commands all ran as children of the daemon. Cleanup reported
  the `sub-agent` blocker naming the worker (#22).
- **`attached`: a plain `codex resume` of the lead.** The second terminal
  started while the worker worked (#23). Its prompt reached the lead as
  `UserPromptSubmit` and `Stop` published by the daemon's process (#24,
  #27), with no `SessionStart` and no hook from the terminal's own process.
  The blocker held after the turn (#31) until the worker's `SubagentStop`
  (#49), which the daemon published, and was gone after it (#52). On exit
  the terminal printed "Disconnected from this task. Any running work
  continues." (#54). The terminal is a client of the daemon, which stays
  the lead's one Host Process.
- **`no-daemon`: `codex --no-daemon resume` of the lead.** The terminal's own
  process started (#72) and sat sleeping for the minute it was given, with
  no prompt run and no hook. It stayed that way for 30 s past the worker's
  `SubagentStop` (#94) and exited with no hook of its own (#99). The blocker
  held until the stop (#88) and was gone after it (#97).
- **The same with this change.** The `fix` scenarios read the same: the
  attached terminal's turn from the daemon (#118, #121), the blocker until
  `SubagentStop` (#125, #143, #146), and the disconnect notice (#148); the
  `--no-daemon` terminal silent until it exited after the stop (#182, #188,
  #193).
- **Control: `--no-daemon` resume after the daemon stopped.** Stopping the
  daemon ended each loaded lead (`SessionEnd`, #198–#201). A
  `codex --no-daemon resume` of a lead then published `SessionStart`
  `resume`, `UserPromptSubmit` and `Stop` from its own process (#206, #207,
  #210), and `SessionEnd` on exit (#214). So the silent terminal above was
  waiting on the daemon's hold on the thread, not failing to publish.

So in Codex 0.160.0 no second Host Process takes on a daemon-hosted lead
whose worker runs: a plain resume publishes from the daemon, and a
`--no-daemon` resume publishes nothing until the daemon lets the thread go.
The gap #448 found in OpenCode does not arise.

Not measured: a standalone terminal's own lead resumed by a second
standalone terminal, where the first exits when it is closed (ADR 0095), and
an App Server with attached clients, whose clients share its one process.

The run added `0128096251aad5308953f2419cbeb60922e82cb9e31f1bee006ca5657dce3d55`,
its `.lock` and `a0f817dc1108ea9ee2420ed5f7cd049adccc8be7685860a2becc1c5b13a7357b.lock`
to the shared `/tmp/codex-daemon-<uid>/`, which it left in place and
removed nothing from.

## Reproduce

From a checkout of the Worktree, outside every harness process. The run used
a private `TMPDIR` for the fixture root:

```sh
SPIKE_PUBLISHERS=base=ff2c1c4b3b4183c868721c118a1024c0e5c294cd,fix=worktree TMPDIR=<private dir> setsid -f node scripts/experiments/codex-460/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/bin/codex 0.160.0 > codex-460.log 2>&1
node scripts/experiments/codex-460/verify.mjs docs/spikes/measurements/issue-460-codex-trace.jsonl --strict
```

The runner prints its fixture root, and its `trace.jsonl` is the trace. The
trace records any uncommitted change under `src/` a `worktree` publisher was
built with, and `verify.mjs` fails on one. `--strict` also fails once a source a publisher was built from
has changed since.
