---
status: living
date: 2026-09-13
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
dashpot integrate codex                 # hooks plus ~/.agents/skills/dashpot-issue-work
dashpot integrate claude-code           # hooks plus ~/.claude/skills/dashpot-issue-work
dashpot integrate <harness> --status    # diagnose hooks, skill, records, identity
dashpot integrate <harness> --remove    # remove Dashpot's hooks and managed skill
```

Installation performs a surgical merge of the harness's user-level hook file:
existing hooks and unrelated settings are preserved, the registered command is
the absolute path of this environment's publisher (so hook and observer
versions stay in lock-step), and rerunning `integrate` is idempotent and
repairs stale paths. Because that path must outlive the Issue work it
observes, run `integrate` from the Repository's main working tree or an
installed tool environment: a publisher inside a linked Worktree's `.venv`
disappears with the Worktree, so `integrate` refuses to bind one and
`--status` warns about an existing binding while the file still exists.
The same command installs Dashpot's model-invoked
`dashpot-issue-work` skill from that installed version. Removal deletes only
the Dashpot handlers and files marked as its managed skill; a different skill
at the same path is reported and left untouched. If Codex hooks are also
defined inline in `~/.codex/config.toml`, Dashpot leaves that file alone and
points out that Codex merges both layers.
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
with `no active Issue work` until it opts in with `dashpot work start`. Codex
and Claude Code sessions are observed side by side with distinct identities,
and both may work on the same Issue as separate Agent Runs. One user-level
installation per harness covers every configured repository, including linked
worktrees: each
observation is routed to the checkout the session runs in, landing in that
worktree's ignored `.dashpot/state/sessions/`. Sessions outside any
Dashpot-configured checkout fall back to the platform's normal
application-state location; set `DASHPOT_STATE_DIR` to override that fallback.

### Agent-facing Issue-work skill

Codex and Claude Code consume the same bundled Agent Skills payload. The
short main workflow reads the repository's instructions, checks that the
installed Dashpot version matches the skill, resolves one fresh Issue, confirms
the Agent Session's Worktree, establishes and verifies its Issue Binding,
follows the repository workflow, and stops the Agent Run only after delivery
and CI are complete. Dispatch and refusal recovery are separate references so
an ordinary in-place opt-in does not load Worktree and harness detail.

When work needs another Worktree, the skill delegates path, Branch, base,
collision, and rollback policy to `issue show` and `worktree create`. Claude
Code relocates the running session with `EnterWorktree`. Codex prefers a
sequential resume of the same Agent Session with `codex resume <session-id> -C
<path>`: the old client releases the thread by exiting, and the resumed turn
must publish fresh lifecycle evidence. Codex itself keeps a competing client
read-only until the owner exits, and that client publishes no hooks
([thread ownership](agent-harness-server-client-reference.md#thread-ownership-and-competing-resume)).
An active run first declares its exact target with `work
relocate <path>`; the resumed hook moves that same run only after the old client
is no longer live, and `work show` verifies the preserved binding. An unbound
session still runs `work start` after arrival. Codex versions that cannot
perform that resume use a disclosed fresh-session fallback, which creates a
new Agent Session and cannot preserve the old run. A person may instead run
`/cd <path>` in the live Codex client to keep the model's context: Codex forks
the conversation into a new thread there, so Dashpot observes a new Agent
Session with its own hook `session_id`, which declares its own Issue work
with `work start` after the old session ends its run with `work stop`
([working-directory change](agent-harness-server-client-reference.md#working-directory-change-and-worktree-commands)).
A shell tool's `cd` remains
repository preparation rather than session relocation.

Each refresh checks that a session's recorded process is still the one that
published the record. A graceful `SessionEnd` removes the session's record and
ends the session's Agent Run in the Work Store, wherever in the Repository's
worktrees it is recorded
([ADR 0015](adr/0015-reconcile-the-agent-run-at-session-end.md)). The declared
Codex resume in
[ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md)
is the one exception: `SessionEnd` preserves the pending run before removing
the old client's hook record. A
session that was killed, or whose `SessionEnd` hook never ran, is dropped
quietly and its stale record and lock file are cleaned up; it only becomes a
Diagnostics warning when it leaves an orphaned Agent Run behind (see below). When the
process cannot be observed at all (for example from inside a sandboxed process
namespace) the session is shown with `unknown` state rather than assumed to
have exited. `dashpot integrate <harness> --status` classifies every session
record as live, unknown, stale, or unreadable and lists the stale ones, which
is where to look when lifecycle events seem not to be delivered.

Every hook record carries the harness's own Agent Session Identity (its hook
`session_id`) beside the host process the hook observed from outside any
sandbox. Observation joins a Work Store record to its hook record by that
harness-scoped native identity, with compatible process evidence. Missing named
evidence produces unknown activity; another conversation on the same backend
cannot supply its state. Legacy unnamed runs remain unresolved and do not
consume a named hook observation.
Liveness and orphan detection still follow the host process: a session's
hooks always run on the host, so its record names the harness process even
when the session's own commands cannot see it.

## Issue work opt-in

The installed `dashpot-issue-work` skill is the agent-facing workflow for these
commands. An Agent Session declares which Issue it is working on from inside
the session, at the Worktree where the work happens:

```bash
dashpot work start 123         # a bare Issue Number
dashpot work start '#123'      # the same Issue, # quoted for the shell
dashpot work start owner/repository#123   # or a full Issue Reference
dashpot work show              # list active Issue work at this worktree
dashpot work relocate ../target-worktree  # preserve this Codex run across resume
dashpot work relocate .        # cancel a pending move after resuming here
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

`dashpot work relocate PATH` is the explicit first phase of preserving an
active Codex Agent Run through a sequential resume. It accepts only the live
session's one recorded run, a confirmed Codex Agent Session Identity, fresh
hook evidence at the current Worktree, and an exact linked Worktree target. It
adds a Relocation Intent without changing the Issue Binding, run identity, or
`startedAt`. The old client's `SessionEnd` then retains the pending record. A
hook at the intended target completes the second phase only when no hook record
places a live or unobservable client with that identity elsewhere; completion
moves the same Work Store record, adopts the resumed process, working directory,
and Branch, and clears the intent. A mismatched target emits
`work-relocation-mismatched`; concurrent locations emit
`work-relocation-concurrent`. Either case, a missing hook, or unreadable state
leaves the intent unchanged and cannot make `work start` reassign it. A
proven-gone old process permits recovery when `SessionEnd` was lost. `work
relocate .` cancels after the same session resumes at its origin, while `work
stop --session KEY` explicitly ends an abandoned pending run. Claude Code
continues to move its live process with `EnterWorktree` and `ExitWorktree`
instead.

### How the session is identified

`dashpot work start`, `work relocate`, and `work stop` identify the enclosing
Agent Session through one harness-neutral seam with a
[Harness Adapter](domain-language.md) per supported harness
(`src/dashpot/harnesses.py`). Both visible and sandboxed commands require a
native identity claim confirmed by its freshest hook record of the same
harness across the Repository's reachable hook stores. The record must describe
a live or unknown session. Visible host ancestry corroborates the harness and
full PID/start-time pair; a sandbox helper never stands in for the host.
Claude Code's claimed host PID must also agree when present. Process evidence
alone cannot authorize starting, switching, stopping, or relocating Issue work,
even if only one session hook is currently visible.

New Agent Runs use a deterministic harness-prefixed SHA-256 digest of the native
session ID as their storage key. Full stored identity remains authoritative:
a conflicting or unreadable destination is refused. Existing process-keyed
records carrying native IDs remain selectable without passive renaming;
observation and continuing relocation preserve their run identity, `startedAt`,
Issue Binding, and Relocation Intent. Explicit `work start` retains the selected
storage key and keeps its documented new-run/switch semantics.

An unnamed legacy record cannot prove ownership, even when its process differs
from the current runtime: a resumed conversation can change processes. Any such
record of the same harness in a linked Worktree blocks implicit adoption or new
work beside it. Inspect `dashpot work show` at that Worktree. Once its recorded
process is proved gone, use `dashpot work stop --session KEY` there to end exactly
that run, then declare fresh work from the intended named session. A live or
unobservable recorded process refuses external stop; for a legacy record with
neither native identity nor process evidence, the explicit key is the supported
recovery selection. Never reconstruct its Issue Binding from a Branch, Worktree,
or conversation history. These intentional legacy restrictions are documented in
[ADR 0038](adr/0038-isolate-native-agent-session-identities.md).

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
Session Identity (see
[Agent session observation](#agent-session-observation)); a hook record
that carries a global Issue binding (the retired
`DASHPOT_ISSUE_ID`/`DASHPOT_ISSUE_REF` environment convention) is rejected with
a diagnostic pointing at `dashpot work start`, never silently combined. When a
session is gone but its Work Store record remains, that record is an orphaned
Agent Run: it is excluded from the listed runs and reported once as an
actionable `work-session-orphaned` diagnostic naming the Issue and the
`dashpot work stop --session <key>` command that ends it. Dashpot never
reassigns Issue work. It ends a run on its own only when the harness delivers
its session's graceful `SessionEnd`, except that a declared Codex relocation
retains the run until verified resume or explicit stop. Ending evidence must
match the recorded runtime, and conditional deletion rechecks the complete run
under its record lock so delayed evidence cannot clear replacement work. A killed session
without a valid target continuation still leaves visible work for a person to
end.
