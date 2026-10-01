---
status: living
date: 2026-10-01
---

# Measurements

The raw evidence the [spikes](../README.md) retain, so their claims can be
checked again without rerunning a harness or spending GitHub rate limit.

A `.jsonl` trace is one JSON record per line, written by the experiment's
`run.mjs` under [`scripts/experiments/`](../../../scripts/experiments/). Its
first record has `"kind": "environment"` and names the harness version,
platform, and isolated configuration; the records after it are the lifecycle
hooks, process ancestry samples, and scenario steps the run observed. The
earlier traces keep the fixture's temporary paths; the later ones rewrite them
to placeholders such as `$ROOT`. The same experiment's `verify.mjs` checks the
document's claims against the trace.

A `.json` file is one JSON array of samples from the first-load latency spike.
The dashboard timings come from the profiling command its
[method](../github-startup-latency-experiments.md#method-and-limits) retains
by commit; the query and transport timings come from the experiment that
cites each file.

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
| [`issue-269-codex-trace.jsonl`](issue-269-codex-trace.jsonl) | JSONL trace, Codex CLI 0.155.1 | [#269](https://github.com/ned2/dashpot/issues/269) | [`codex-269`](../../../scripts/experiments/codex-269/) | [Codex declared relocation on a daemon-hosted thread](../codex-declared-relocation-daemon-spike.md) |
| [`issue-279-claude-trace.jsonl`](issue-279-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#279](https://github.com/ned2/dashpot/issues/279) | [`claude-279`](../../../scripts/experiments/claude-279/) | [Harness reference: sub-agent hooks and location](../../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285) |
| [`issue-326-claude-trace.jsonl`](issue-326-claude-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#326](https://github.com/ned2/dashpot/issues/326) | [`claude-326`](../../../scripts/experiments/claude-326/) | [Claude Code supervised worker process experiment](../claude-code-supervised-worker-process-spike.md) |
| [`issue-345-claude-2.1.280-trace.jsonl`](issue-345-claude-2.1.280-trace.jsonl) | JSONL trace, Claude Code 2.1.280 | [#345](https://github.com/ned2/dashpot/issues/345) | [`claude-345`](../../../scripts/experiments/claude-345/) | [Claude Code 2.1.285 changes experiment](../claude-code-2-1-285-changes-spike.md) |
| [`issue-345-claude-2.1.285-trace.jsonl`](issue-345-claude-2.1.285-trace.jsonl) | JSONL trace, Claude Code 2.1.285 | [#345](https://github.com/ned2/dashpot/issues/345) | [`claude-345`](../../../scripts/experiments/claude-345/) | [Claude Code 2.1.285 changes experiment](../claude-code-2-1-285-changes-spike.md) |

The #279 trace is the one whose writeup is not a spike: its findings went
straight into the living harness reference, which links it.
