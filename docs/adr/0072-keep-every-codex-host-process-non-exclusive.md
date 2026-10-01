---
status: accepted
date: 2026-10-01
---

# Keep every Codex Host Process non-exclusive

[ADR 0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)
continues an Orphaned Agent Run when its conversation resumes in a new Host
Process, but only when the Harness Adapter declares `exclusive_session_process`.
For Codex it left one row open: "Codex, no daemon: Unmeasured".
[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
then listed a Codex terminal launched before the daemon, daemon autostart and
input joined to a running Codex turn among the modes that stay unsupported
until their implementing Issue measures them. The
[agent runtime lifecycle design](../proposals/agent-runtime-lifecycle-design.md#q3-what-happens-to-the-agent-run-across-boundaries)
said that a per-Host-Process answer (daemon shared, standalone exclusive) would
need a measurement of the standalone TUI and an amendment to ADR 0053's table.
[#161](https://github.com/ned2/dashpot/issues/161) made the measurement
on `codex-cli` 0.159.3. Dashpot's real Codex publisher ran in an isolated
`CODEX_HOME` with no standalone release linked, and the result is recorded in the
[Codex acceptance run](../agent-sessions.md#codex-hosting-modes) and its
[trace](../spikes/measurements/issue-161-codex-trace.jsonl). The measurement found:

- The `daemon_auto_start` feature is on by default. A plain `codex`
  terminal installs the managed daemon into
  `<CODEX_HOME>/packages/app-server-daemon` from its own binary. It starts the
  daemon as its child, and every hook and shell of the terminal then runs
  below the daemon. `codex remote-control start` installs and starts the same
  daemon.
- A terminal hosts its own thread only when it is launched with
  `--disable daemon_auto_start` and no daemon is running. Launched with that
  flag while a daemon runs, it attaches to the daemon instead.
- In that standalone mode, a SIGKILL of the terminal publishes no hook. The
  conversation then resumes in a new terminal with `SessionStart` `resume`
  under the same thread id. `/exit` publishes `SessionEnd` at once. `codex
  exec` likewise hosts its own thread and ends it with `SessionEnd`.

## Decision

Codex keeps `exclusive_session_process` false for every way it hosts a
thread: the managed daemon, `app-server`, a standalone terminal, and `codex
exec`. A Codex conversation resumed after its Host Process was killed is
never continued by ADR 0053. Its run stays listed as orphaned until the
session runs `dashpot work start` at that Worktree, which restarts the run
there, or someone ends it with `dashpot work stop --session`.

## Considered options

- **Declare the standalone terminal exclusive.** Rejected. The declaration
  is per harness, so Dashpot would have to tell a standalone terminal from a
  daemon-attached one at continuation time. The Work Store records only the
  gone process's pid and start time; only the hook record's argument vector
  would show its shape. Reading continuation evidence from an argument
  vector is the kind of shape inference ADR 0053 admits only where a harness
  measures it, as for Claude Code's supervised workers. Here the measured
  shape is not stable: the same `--disable daemon_auto_start` launch is
  daemon-hosted whenever a daemon happens to be running. The interactive
  `/new` and `/resume` conversation switches inside one terminal were not
  measured either.
- **Declare it exclusive for `codex exec` only.** Rejected for the same
  reason. An `exec` resume is a one-shot command whose next run binds nothing
  on its own, so continuation would rarely help.
- **Keep the row "Unmeasured".** Rejected. It is now measured, and the
  restart policy follows from the measurement rather than from its absence.

## Consequences

- The default Codex setup at 0.159.3 is daemon-hosted, so the shared Host
  Process that ADR 0053 already refuses to continue is the common case, not
  an edge.
- Amends ADR 0053's per-harness table: its "Codex, no daemon" row is now
  measured, and Codex does not continue in any mode.
- Recovery for Codex is the same in every mode. After the Host Process is
  gone, the session runs `work start` where it resumed. The acceptance run
  checks that this restores the binding on the new process with a new
  `startedAt`.
- A later Codex release that changes autostart, or makes a terminal's
  hosting stable and observable, needs a new measurement and a new ADR
  before Codex continues any run.
