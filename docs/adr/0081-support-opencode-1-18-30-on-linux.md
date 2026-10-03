---
status: superseded
date: 2026-10-02
superseded-by: 0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md
---

# Support OpenCode 1.18.30 on Linux

[ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)
installs OpenCode's managed plugin and keeps OpenCode unsupported until its
acceptance run passes, as each supported harness release is pinned by one
([README](../../README.md#harness-acceptance-runs)). That run is the second
half of [#163](https://github.com/ned2/dashpot/issues/163). Its
[runner](../../scripts/experiments/opencode-163/run.mjs) drives OpenCode
1.18.30 on Linux in a disposable fixture, with isolated configuration and a
loopback model, through a Dashpot wheel built from the checkout and installed
by `dashpot integrate opencode`. Its
[verifier](../../scripts/experiments/opencode-163/verify.mjs) checks the
documented claims against the retained, metadata-only
[trace](../spikes/measurements/issue-163-opencode-trace.jsonl), which records
the SHA-256 of the runner and of every Dashpot source it exercised. It
passed, and measured:

- the installer's round trips beside the user's own plugin, skills and
  Claude Code integration, and its `--status` for another release, a
  duplicate plugin and `OPENCODE_PURE`;
- one `opencode serve` backend serving several sessions in two Worktrees,
  with `opencode run --attach` and attached TUI clients that detach and
  reattach;
- the local TUI, its `!` shell, quitting it, closing its terminal, and
  resuming its session from the same and another Worktree;
- child, background child and forked sessions; retry, interrupt and a
  provider's refusal;
- a plugin's reload, removal and restoration; a missing or stalled helper;
- deletion through the backend and through `opencode session delete`;
- late, duplicate, retired, deleted and forged publications;
- a backend stopped by SIGTERM or killed, its orphaned runs, and Cleanup
  freed once they are stopped.

## Decision

**OpenCode 1.18.30 on Linux is supported**, in the modes the
[OpenCode hosting modes](../agent-sessions.md#opencode-hosting-modes) list:
the local TUI, and `opencode serve` with `opencode run --attach` and
`opencode attach` clients. `dashpot integrate opencode` and its `--status`
no longer say OpenCode is unsupported. `--status` names 1.18.30 as the
accepted release, and warns that any other release is unsupported because
another release may change what the plugin observes.

**Unsupported**, because the run did not measure it: `opencode web`, ACP
(`opencode acp`), the SDK's own server, the desktop app and editor
extensions; a remote backend, or one serving clients on another machine;
two backends serving one session at once; Live Relocation, since a session
never leaves the directory it was created in; and every operating system
other than Linux. An OpenCode started with `--pure` or `OPENCODE_PURE`
publishes nothing, as ADR 0079 records. A background child is measured, but
OpenCode runs one only under its experimental
`OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS` flag.

**Limitation.** `opencode session delete` on a bound session leaves its run
until the backend that served it exits
([ADR 0080](0080-keep-a-retired-opencode-generations-backend-on-its-sessions.md)).

## Considered options

- **Accept the 1.18.x line.** Rejected. Each harness pins the exact release
  its run passed on; a patch release can change plugin delivery.
- **Accept without the local TUI.** Rejected. It is how most people run
  OpenCode, and its shutdown turned out to differ from `serve`'s.

## Consequences

- ADR 0079's "unsupported until acceptance" is answered: its status is
  amended by this ADR.
- A new OpenCode release becomes supported by passing the acceptance run on
  it, and regenerating the trace with it.
- The trace is regenerated whenever the pinned release, or the lifecycle code
  it exercises, changes.
