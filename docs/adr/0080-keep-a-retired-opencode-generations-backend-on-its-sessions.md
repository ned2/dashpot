---
status: amended
date: 2026-10-02
amended-by: 0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md
---

# Keep a retired OpenCode generation's backend on its sessions

[ADR 0077](0077-observe-opencode-through-one-publisher-generation-per-plugin-instance.md)
takes a retiring generation's root sessions off their Host Process: their
hook records name no process, with the reason `opencode-publisher-retired`,
so they read unknown until a successor publishes them. The OpenCode
acceptance run of [#163](https://github.com/ned2/dashpot/issues/163)
measured OpenCode 1.18.30 on Linux through its
[runner](../../scripts/experiments/opencode-163/run.mjs), and found that
retirement is also how most OpenCode sessions end:

- The local TUI is one `opencode` process, its own backend. Quitting it with
  Ctrl+C, or closing its terminal (SIGHUP), runs every instance's `dispose`
  hook before the process exits. Its sessions publish no end; their
  generation retires.
- `opencode serve` stopped by SIGTERM, or any backend killed, exits without
  `dispose`, so its sessions keep their last status.
- `opencode session delete`, run in a session's directory, loads the plugin
  in its own short-lived process for that directory. That process's
  generation publishes the deletion, then retires.

A record that names no process cannot be verified, so under ADR 0077 a TUI
that had quit left its sessions unknown for good: Cleanup refused their
Worktrees with nothing a person could do but publish the session's end by
hand. Unknown should mean only that Dashpot cannot tell.

## Decision

**Retirement keeps the backend.** A retiring generation's root sessions keep
the backend they named, and gain the marker `opencode-publisher-retired` in
their record's `sessionProcessUnobservable`. Classification reads such a
record by its backend:

- **Backend live.** The session reads unknown, with the reason
  `opencode-publisher-retired`: the backend may still serve it, but nothing
  observes it. Cleanup's `agent-session` blocker names that backend, says it
  still runs, and gives OpenCode's way out.
- **Backend gone.** The session reads gone, as any session whose Host
  Process exited. A bound run is an Orphaned Agent Run, ended with
  `dashpot work stop --session <key>`.
- **A successor publishes it.** Its first word writes `SessionStart`, which
  clears the marker, as before.

A command's claim from a retired generation stays refused while its backend
runs: the claim's check reads the marker, not only a missing process.

**OpenCode's way out of a Worktree.** An OpenCode session never leaves the
directory it was created in, even resumed from another one. Cleanup's
`agent-session` blocker therefore says to quit the OpenCode TUI serving the
session, or stop the backend it runs in, and that closing an attached client
leaves it running; or to delete the session in the backend serving it.

**A deleted session's run.** `opencode session delete` run in the session's
own directory removes the session's hook record, but the run names the
backend that served the session, which still runs, so the run is neither
ended nor orphaned, and `work stop --session` refuses it as running. When an
OpenCode run's backend is live and no hook record of its session is left in
any store, Cleanup's `agent-run` blocker says no hook record of the session
is left, as after `opencode session delete`, while that backend still runs,
and names quitting or stopping it, then `dashpot work stop --session <key>`.
Ending such a run without its Host Process is not decided here. Run from any
other directory, the command still deletes the session in OpenCode, but its
process's instance is for that other directory, so the helper refuses the
deletion as outside it (ADR 0077's location rule) and Dashpot changes
nothing: the session stays listed as last published, and a bound run with
it, until its backend exits and the run reads orphaned.

## Considered options

- **Read a retired generation's sessions as gone, or ended, at once.**
  Rejected. A configuration reload retires a generation while the backend
  and its sessions carry on, and OpenCode does not say whether it disposed of
  an instance to reload it or to exit; gone would orphan their runs.
- **End a deleted session's run from the deleting process.** Rejected here.
  The deleting process is not the run's Host Process, and ending a bound run
  without it is a policy question for its own Issue.

## Consequences

- A quit TUI, a closed terminal and a stopped backend all end at gone, and
  Cleanup frees their Worktrees once any bound run is stopped.
- A reload still reads unknown, with Issue work unchanged, until the next
  turn or command.
- Deleting a bound session with `opencode session delete` leaves its run
  until its backend exits; the [hosting modes](../agent-sessions.md#opencode-hosting-modes)
  say to stop Issue work first, or delete the session through the backend
  serving it.
- ADR 0077's "Their records name no process" is replaced by the marker, and
  its last consequence, the unmeasured TUI and resume, is answered by
  [ADR 0081](0081-support-opencode-1-18-30-on-linux.md).
