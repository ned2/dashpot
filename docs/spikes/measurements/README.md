---
status: living
date: 2026-10-03
---

# Measurements

The raw evidence the [spikes](../README.md) retain, so their claims can be
checked again without rerunning a harness or spending GitHub rate limit.

A `.jsonl` trace is one JSON record per line, written by the experiment's
`run.mjs` under [`scripts/experiments/`](../../../scripts/experiments/). Its
first record has `"kind": "environment"` and names the harness version,
platform, and, in most traces, the isolated configuration; the records after it are the lifecycle
hooks, process ancestry samples, and scenario steps the run observed. The
earlier traces keep the fixture's temporary paths; the later ones rewrite them
to placeholders such as `$ROOT`. The same experiment's `verify.mjs` checks the
document's claims against the trace.

A `.json` file is one JSON array of samples from the first-load latency spike.
The dashboard timings come from the profiling command its
[method](../github-startup-latency-experiments.md#method-and-limits) retains
by commit; the query and transport timings come from the experiment that
cites each file.

A `.txt` file is a `script --log-timing` record of a terminal's output: one
line per write, the seconds since the previous write and the bytes written.

| Trace | Format | Issue | Produced by | Recorded in |
| --- | --- | --- | --- | --- |
| [`issue-138-experiment1.json`](issue-138-experiment1.json) | JSON array of first-load timings, one entry per sample | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 1 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#individual-changes) |
| [`issue-138-experiment3.json`](issue-138-experiment3.json) | JSON array of first-load timings, one entry per sample | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 3 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#individual-changes) |
| [`issue-138-experiment4.json`](issue-138-experiment4.json) | JSON array of first-load timings, one entry per sample | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 4 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#individual-changes) |
| [`issue-138-final.json`](issue-138-final.json) | JSON array of first-load timings, one entry per sample | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency final comparison | [First-load GitHub observation latency](../github-startup-latency-experiments.md#final-comparison) |
| [`issue-138-identity.json`](issue-138-identity.json) | JSON array of GraphQL timings and rate-limit costs per query variant | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 2 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#2-repository-identity-validation) |
| [`issue-138-width.json`](issue-138-width.json) | JSON array of GraphQL timings, sizes, and counts per page width | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 5 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#5-pull-request-page-width) |
| [`issue-138-transport.json`](issue-138-transport.json) | JSON array of request timings and rate-limit costs per transport | [#138](https://github.com/ned2/dashpot/issues/138) | First-load latency experiment 7 | [First-load GitHub observation latency](../github-startup-latency-experiments.md#7-reuse-transport-connections) |
| [`issue-148-claude-trace.jsonl`](issue-148-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.278 | [#148](https://github.com/ned2/dashpot/issues/148) | [`claude-148`](../../../scripts/experiments/claude-148/) | [Cleanup session handoff feasibility experiment](../cleanup-session-handoff-feasibility-spike.md) |
| [`issue-148-codex-trace.jsonl`](issue-148-codex-trace.jsonl) | JSONL trace, Codex CLI 0.155.1 | [#148](https://github.com/ned2/dashpot/issues/148) | [`codex-148`](../../../scripts/experiments/codex-148/) | [Cleanup session handoff feasibility experiment](../cleanup-session-handoff-feasibility-spike.md) |
| [`issue-151-trace.jsonl`](issue-151-trace.jsonl) | JSONL trace, OpenCode 1.18.30 | [#151](https://github.com/ned2/dashpot/issues/151) | [`opencode-151`](../../../scripts/experiments/opencode-151/) | [OpenCode identity and lifecycle experiment](../opencode-identity-lifecycle-spike.md) |
| [`issue-160-claude-trace.jsonl`](issue-160-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.276 | [#160](https://github.com/ned2/dashpot/issues/160) | [`claude-160`](../../../scripts/experiments/claude-160/) | [Claude Code identity and lifecycle experiment](../claude-code-identity-lifecycle-spike.md) |
| [`issue-160-codex-trace.jsonl`](issue-160-codex-trace.jsonl) | JSONL trace, Codex CLI 0.155.1 | [#160](https://github.com/ned2/dashpot/issues/160) | [`codex-160`](../../../scripts/experiments/codex-160/) | [Codex identity and lifecycle experiment](../codex-identity-lifecycle-spike.md) |
| [`issue-161-codex-trace.jsonl`](issue-161-codex-trace.jsonl) | JSONL trace, Codex CLI 0.160.0 | [#161](https://github.com/ned2/dashpot/issues/161), with the sub-agent scenarios of [#355](https://github.com/ned2/dashpot/issues/355), rerun on 0.160.0 for [#375](https://github.com/ned2/dashpot/issues/375), and with the interrupted sub-agents of [#374](https://github.com/ned2/dashpot/issues/374) | [`codex-161`](../../../scripts/experiments/codex-161/), the Codex acceptance run | [Agent sessions: Codex hosting modes](../../agent-sessions.md#codex-hosting-modes) |
| [`issue-162-claude-trace.jsonl`](issue-162-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.287 | [#162](https://github.com/ned2/dashpot/issues/162), rerun on 2.1.287 for [#388](https://github.com/ned2/dashpot/issues/388) | [`claude-162`](../../../scripts/experiments/claude-162/), the Claude Code acceptance run | [Agent sessions: Claude Code hosting modes](../../agent-sessions.md#claude-code-hosting-modes) |
| [`issue-162-claude-idle-trace.jsonl`](issue-162-claude-idle-trace.jsonl) | JSONL trace, Claude Code 2.1.287 | [#162](https://github.com/ned2/dashpot/issues/162), rerun on 2.1.287 for [#388](https://github.com/ned2/dashpot/issues/388) | [`claude-162`](../../../scripts/experiments/claude-162/) with `SPIKE_IDLE_MINUTES`, the idle-eviction run | [Harness reference: clients and supervised workers](../../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286) |
| [`issue-163-opencode-trace.jsonl`](issue-163-opencode-trace.jsonl) | JSONL trace, OpenCode 2.0.22 with 2.0.21 and 1.18.30 | [#163](https://github.com/ned2/dashpot/issues/163), re-pinned on 2.0.22 for [#407](https://github.com/ned2/dashpot/issues/407) | [`opencode-163`](../../../scripts/experiments/opencode-163/), the OpenCode acceptance run | [Agent sessions: OpenCode hosting modes](../../agent-sessions.md#opencode-hosting-modes) |
| [`issue-269-codex-trace.jsonl`](issue-269-codex-trace.jsonl) | JSONL trace, Codex CLI 0.155.1 | [#269](https://github.com/ned2/dashpot/issues/269) | [`codex-269`](../../../scripts/experiments/codex-269/) | [Codex declared relocation on a daemon-hosted thread](../codex-declared-relocation-daemon-spike.md) |
| [`issue-279-claude-trace.jsonl`](issue-279-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#279](https://github.com/ned2/dashpot/issues/279) | [`claude-279`](../../../scripts/experiments/claude-279/) | [Harness reference: sub-agent hooks and location](../../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285) |
| [`issue-326-claude-trace.jsonl`](issue-326-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#326](https://github.com/ned2/dashpot/issues/326) | [`claude-326`](../../../scripts/experiments/claude-326/) | [Claude Code supervised worker process experiment](../claude-code-supervised-worker-process-spike.md) |
| [`issue-327-claude-2.1.283-trace.jsonl`](issue-327-claude-2.1.283-trace.jsonl) | JSONL trace, Claude Code 2.1.283 | [#327](https://github.com/ned2/dashpot/issues/327) | [`claude-327`](../../../scripts/experiments/claude-327/) | [Harness reference: worktree tools between Issue Worktrees](../../agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286) |
| [`issue-327-claude-2.1.286-trace.jsonl`](issue-327-claude-2.1.286-trace.jsonl) | JSONL trace, Claude Code 2.1.286 | [#327](https://github.com/ned2/dashpot/issues/327) | [`claude-327`](../../../scripts/experiments/claude-327/) | [Harness reference: worktree tools between Issue Worktrees](../../agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286) |
| [`issue-327-claude-2.1.287-trace.jsonl`](issue-327-claude-2.1.287-trace.jsonl) | JSONL trace, Claude Code 2.1.287 | [#327](https://github.com/ned2/dashpot/issues/327) | [`claude-327`](../../../scripts/experiments/claude-327/) | [Harness reference: worktree tools between Issue Worktrees](../../agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286) |
| [`issue-345-claude-2.1.280-trace.jsonl`](issue-345-claude-2.1.280-trace.jsonl) | JSONL trace, Claude Code 2.1.280 | [#345](https://github.com/ned2/dashpot/issues/345) | [`claude-345`](../../../scripts/experiments/claude-345/) | [Claude Code 2.1.285 changes experiment](../claude-code-2-1-285-changes-spike.md) |
| [`issue-345-claude-2.1.285-trace.jsonl`](issue-345-claude-2.1.285-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#345](https://github.com/ned2/dashpot/issues/345) | [`claude-345`](../../../scripts/experiments/claude-345/) | [Claude Code 2.1.285 changes experiment](../claude-code-2-1-285-changes-spike.md) |
| [`issue-356-codex-trace.jsonl`](issue-356-codex-trace.jsonl) | JSONL trace, Codex CLI 0.160.0 | [#356](https://github.com/ned2/dashpot/issues/356) | [`codex-356`](../../../scripts/experiments/codex-356/), the managed daemon restart acceptance run | [Harness reference: managed daemon restart and stop](../../agent-harness-server-client-reference.md#managed-daemon-restart-and-stop-at-01600) |
| [`issue-393-opencode-trace.jsonl`](issue-393-opencode-trace.jsonl) | JSONL trace, OpenCode 2.0.22 with 2.0.21 | [#393](https://github.com/ned2/dashpot/issues/393) | [`opencode-393`](../../../scripts/experiments/opencode-393/) | [OpenCode v2 hosting, plugin and identity experiment](../opencode-v2-spike.md) |
| [`issue-393-opencode-idle-trace.jsonl`](issue-393-opencode-idle-trace.jsonl) | JSONL trace, OpenCode 2.0.22 | [#393](https://github.com/ned2/dashpot/issues/393) | [`opencode-393`](../../../scripts/experiments/opencode-393/) with `SPIKE_IDLE_MINUTES`, the idle-eviction run | [OpenCode v2 hosting, plugin and identity experiment: idle eviction](../opencode-v2-spike.md#idle-eviction) |
| [`issue-405-opencode-trace.jsonl`](issue-405-opencode-trace.jsonl) | JSONL trace, OpenCode 2.0.22 with 1.18.30 | [#405](https://github.com/ned2/dashpot/issues/405) | [`opencode-405`](../../../scripts/experiments/opencode-405/) | [OpenCode v2 plugin registry, envelope and recovery experiment](../opencode-v2-plugin-protocol-spike.md) |
| [`issue-410-tmux-trace.jsonl`](issue-410-tmux-trace.jsonl) | JSONL trace, tmux 3.6 with OpenSSH 10.2 | [#410](https://github.com/ned2/dashpot/issues/410) | [`tmux-410`](../../../scripts/experiments/tmux-410/) | [tmux dropped SSH client experiment](../tmux-dropped-ssh-client-spike.md) |
| [`issue-410-dashboard-output-timing.txt`](issue-410-dashboard-output-timing.txt) | `script --log-timing` log of a tmux client's output | [#410](https://github.com/ned2/dashpot/issues/410) | A dashboard on this Repository at commit `69c7d72` and the default Refresh Periods, recorded as the spike's [Reproduce](../tmux-dropped-ssh-client-spike.md#reproduce) shows | [tmux dropped SSH client experiment](../tmux-dropped-ssh-client-spike.md#sshds-keepalive-needs-silence) |

The #279 and #327 traces and the #161, #162, #163 and #356 acceptance traces are
the ones whose writeups are not spikes: their findings went straight into the
living harness reference and agent sessions, which link them. The acceptance traces
are regenerated whenever the pinned Codex, Claude Code or OpenCode release, or
the lifecycle code they exercise, changes.
