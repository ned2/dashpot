---
status: living
date: 2026-09-04
---

# Agent sessions

How Dashpot observes a coding-agent session, and how a session declares
the Issue it is working on. Agents working in this repository should read
[AGENTS.md](../AGENTS.md) first: it states the lifecycle rules that apply
here, and this document explains the commands behind them.

## Agent session observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` and
`dashpot-claude-code-hook` publishers. Nothing is installed into a harness
automatically; register the lifecycle hooks once per user with:

```bash
dashpot integrate codex                 # hooks in ~/.codex/hooks.json
dashpot integrate claude-code           # hooks in ~/.claude/settings.json
dashpot integrate <harness> --status    # diagnose config, publisher, records
dashpot integrate <harness> --remove    # remove exactly the Dashpot hooks
```

Installation performs a surgical merge of the harness's user-level hook file:
existing hooks and unrelated settings are preserved, the registered command is
the absolute path of this environment's publisher (so hook and observer
versions stay in lock-step), and rerunning `integrate` is idempotent and
repairs stale paths. Removal deletes only the Dashpot handlers. If Codex hooks
are also defined inline in `~/.codex/config.toml`, Dashpot leaves that file
alone and points out that Codex merges both layers.
[`examples/codex-hooks.json`](../examples/codex-hooks.json) shows the equivalent
manual Codex configuration.

The hooks report session lifecycle only: which agent sessions are alive at a
worktree and whether they are running or waiting. Codex registers
`SessionStart`, `UserPromptSubmit`, `Stop`, `Interrupt`, and `SessionEnd`;
Claude Code the same set without `Interrupt`, plus `SubagentStart` and
`SubagentStop`, and `PostToolUse` matched to its `EnterWorktree` and
`ExitWorktree` tools alone, so a session that moves to another Worktree, or
back, is placed there as soon as it arrives — one hook invocation per
relocation, never per tool call
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
A session whose main turn has stopped stays running while a sub-agent it
delegated to is still working, since sub-agents share the session's Agent Run
([ADR 0016](adr/0016-hold-a-session-running-while-its-sub-agents-work.md)).
A session that has not
declared an Issue is not listed as Work; it is listed in the Sessions pane
with `no active Issue work` until it opts in with `dashpot work start`. Codex and Claude
Code sessions are observed side by side with distinct identities, and both may
work on the same Issue as separate Agent Runs. One user-level installation per
harness covers every configured repository, including linked worktrees: each
observation is routed to the checkout the session runs in, landing in that
worktree's ignored `.dashpot/state/sessions/`. Sessions outside any
Dashpot-configured checkout fall back to the platform's normal
application-state location; set `DASHPOT_STATE_DIR` to override that fallback.

Each refresh checks that a session's recorded process is still the one that
published the record. A graceful `SessionEnd` removes the session's record and
ends the session's Agent Run in the Work Store, wherever in the Repository's
worktrees it is recorded
([ADR 0015](adr/0015-reconcile-the-agent-run-at-session-end.md)). A
session that was killed, or whose `SessionEnd` hook never ran, is dropped
quietly and its stale record and lock file are cleaned up; it only becomes a Diagnostics
warning when it leaves an orphaned Agent Run behind (see below). When the
process cannot be observed at all (for example from inside a sandboxed process
namespace) the session is shown with `unknown` state rather than assumed to
have exited. `dashpot integrate <harness> --status` classifies every session
record as live, unknown, stale, or unreadable and lists the stale ones, which
is where to look when lifecycle events seem not to be delivered.

Every hook record carries the harness's own Agent Session Identity (its hook
`session_id`) beside the host process the hook observed from outside any
sandbox. Observation joins a Work Store record to its hook record by that
identity when the record carries one, and by host process identity otherwise,
so a run opted in from a sandbox adopts the same running/waiting state, and
is listed once in the Sessions pane, as one opted in from a plain shell.
Liveness and orphan detection still follow the host process: a session's
hooks always run on the host, so its record names the harness process even
when the session's own commands cannot see it.

## Issue work opt-in

An agent session declares which Issue it is working on from inside the
session, at the worktree where the work happens:

```bash
dashpot work start 123         # a bare Issue Number
dashpot work start '#123'      # the same Issue, # quoted for the shell
dashpot work start owner/repository#123   # or a full Issue Reference
dashpot work show              # list active Issue work at this worktree
dashpot work stop              # end this session's run; the session stays alive
dashpot work stop --session KEY  # end the orphaned run of a session that is gone
```

A bare number and its `#`-prefixed form resolve to the same Issue; Local
Issue Markdown Projects also accept the Issue's slug.

`dashpot work start` resolves the Reference against the Project configured at
that worktree, requires it to identify exactly one currently observed Issue,
and atomically records the resulting durable Issue Identity in the Project-local
Work Store (`.dashpot/state/work/`). Running `start` again switches the session
to a new Issue. A session holds one active run across the linked Worktrees of
its Git Repository
([ADR 0009](adr/0009-hold-one-agent-run-per-session-across-worktrees.md)),
and its own hooks say where it is: the freshest hook record for the session
across the stores of every Worktree `git worktree list` reports, plus the
global store. When that record places the session at the Worktree where
`start` runs, a run it still holds at another Worktree is a relocation (a
Claude Code `EnterWorktree`, or the `ExitWorktree` that brings the session
back): `start` ends it and reports
`switched from <ref> at <old Worktree> to <ref> at <new Worktree>`. When it
places the session elsewhere, the command is running where the session is
not — a tool call that changed directory, or a sub-agent's shell — and
`start` refuses, names that Worktree, and writes nothing. `stop` ends the
session's run wherever in the Repository it is recorded. A session with no
hook record anywhere starts where it runs, as before, so the invariant is
enforced only once the harness hooks are installed; runs recorded by an older
Dashpot, or across independent clones, keep the `work-session-conflict`
warning. Once recorded, the binding survives
repository renames, Issue Reference edits, Local Issue moves, and transfers
between configured Projects.
The ordinary TUI continues to show current References; raw identities remain in
headless output and diagnostics.

### How the session is identified

`dashpot work start` and `stop` identify the enclosing Agent Session through
one harness-neutral seam with a [Harness Adapter](domain-language.md) per
supported harness (`src/dashpot/harnesses.py`), by two routes:

1. **Host process ancestry.** The command walks up its parent processes to
   the nearest Codex or Claude Code process, as it always has. A sandbox
   helper such as `codex-linux-sandbox` or `bwrap` is never taken for the
   harness. This route is authoritative whenever it works; the record is keyed
   by that process, and the harness's Agent Session Identity is recorded
   beside it when the environment names one that the hook record corroborates.
2. **Agent Session Identity.** When the ancestry is hidden — Codex's
   `codex-linux-sandbox` and Claude Code's bubblewrap sandbox each run the
   command as PID 2 of a fresh PID namespace — each adapter reads the identity
   its harness exposes to commands (Codex its thread identifier, Claude Code
   its session identifier and host PID). Neither harness documents these as
   stable, so a claim is never trusted on its own: its freshest lifecycle
   hook record for the same harness across the Repository's hook stores
   (each Worktree's `.dashpot/state/sessions/` and the global store) must
   still describe a live or unknown session, and for Claude Code the record's
   host PID must agree; a stale record left at a Worktree the session moved
   away from never confirms a `start` there. The record
   is then keyed by the host process the hook published, so the same session
   gets the same record whether or not its commands are sandboxed, and
   liveness and orphan detection work as before; a record whose hook never saw
   a host process is keyed by the identity's digest instead. `start`, switching
   Issues, and `stop` all resolve the session the same way, and a record
   written before this identity existed is adopted by the same session rather
   than duplicated.

A missing, unreadable, ended, gone, cross-harness, or PID-mismatched hook
record refuses the opt-in with a message naming the record and the
`dashpot integrate <harness> --status` check to run, and writes nothing. When
the environment names live sessions of both harnesses — a Codex session
started from inside a Claude Code shell inherits both — the opt-in is refused
as ambiguous until `DASHPOT_AGENT_SESSION=<harness>:<session id>` states which
session the command belongs to; that explicit claim is validated like any
other. `dashpot integrate <harness> --status` reports the identity the
current environment claims for that harness and whether its hook record here
confirms or rejects it, which is the first thing to check when a sandboxed
`work start` is refused.

The Work Store is the sole authority for Issue association. Collection
correlates each recorded run with the hook's lifecycle observations by Agent
Session Identity or process identity (see
[Agent session observation](#agent-session-observation)); a hook record
that carries a global Issue binding (the retired
`DASHPOT_ISSUE_ID`/`DASHPOT_ISSUE_REF` environment convention) is rejected with
a diagnostic pointing at `dashpot work start`, never silently combined. When a
session is gone but its Work Store record remains, that record is an orphaned
Agent Run: it is excluded from the listed runs and reported once as an
actionable `work-session-orphaned` diagnostic naming the Issue and the
`dashpot work stop --session <key>` command that ends it. Dashpot never
reassigns Issue work, and ends a run on its own only when the harness delivers
the session's graceful `SessionEnd`; a session that is killed still leaves an
orphaned Agent Run for a person to end.
