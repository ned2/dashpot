---
status: amended
date: 2026-09-05
amended-by: 0029-preserve-agent-runs-through-declared-codex-relocation.md
---

# Hold one active Agent Run per Agent Session across a Repository's Worktrees

The Work Store is Project-local and per Worktree: `dashpot work start` writes
its record beneath the Worktree the command runs in, `stop` removes the record
at that same Worktree, and nothing looks across Worktrees. A record's key is
derived from the harness process, or from the Agent Session Identity its hooks
publish ([ADR 0007](0007-identify-sandboxed-sessions-by-agent-session-identity.md)),
so one Agent Session can hold an active record at two Worktrees of the same
Project. Observation lists both runs with a `work-session-conflict` warning;
neither is an Orphaned Agent Run, because the session is alive.

Two things make that state reachable. Claude Code's `EnterWorktree` tool moves
a running session to another Worktree (and `ExitWorktree` moves it back),
after which its hooks publish from the new working directory; a session that
opted in at Worktree A and then opts in
at B leaves A's record active. And a tool call that merely runs
`cd B && dashpot work start` while the harness stays at A records the run at
B, where no hook ever describes the session, so the run is listed with
`unknown` activity (measured during the handoff protocol review). A Claude
Code sub-agent working in its own Worktree is that second case on the process
route: its shell is a child of the same `claude` process, so it shares the
session's key while the session's hooks keep firing from A (whether its
sandboxed identity claim also carries the main session's identity is
unverified).

An Agent Session is the harness conversation identified by its stable opaque
identity, not one process. A running harness can move in place, and Codex can
resume the same conversation under a new process at another working directory.
Dashpot will hold that a live Agent Session has at most one active Agent Run
across the linked Worktrees of one Git Repository, and `work start` and `stop`
will enforce it by distinguishing a relocation from a wrong-location opt-in on
hook evidence:

- The session's *current location* is the `repositoryRoot` (else the `cwd`)
  of its freshest hook record by `lastActivityAt` across every hook store
  reachable from the Worktree the command runs in: the stores of every
  Worktree `git worktree list` reports, and the global store that receives
  records for a Worktree whose checkout predates `.dashpot/config.json`.
- When that location is the Worktree where `start` runs, the session has
  moved and nobody is left behind. `start` ends the session's active record
  at any other Worktree of the Repository and reports the switch, exactly as
  switching Issues within one Worktree already replaces the record.
- When that location is another Worktree, the command is running where the
  session is not. `start` refuses, names that Worktree, and writes nothing.
- `stop` ends the session's active record wherever in the Repository it is,
  so a relocated session that simply stops at B does not leave A live.
- A sandboxed claim is validated against the same freshest record, not
  against whichever live record happens to sit in the current Worktree's
  store, so a stale record left at A cannot confirm a `start` there.
- A session with no hook record anywhere in the Repository is identified by
  the process route alone and may start at the Worktree it runs in, as today.
  The invariant is therefore enforced only for sessions whose hooks are
  installed; without them the sub-agent rule in `CLAUDE.md` remains an
  instruction.

Dashpot subscribes to `SessionStart`, `UserPromptSubmit`, `Stop`, and
`SessionEnd` ([ADR 0006](0006-observe-agent-activity-at-turn-boundaries.md)),
and `EnterWorktree` fires none of them, so at the moment a relocated session
first runs `start` the freshest record would still say A. Claude Code's
integration therefore adds `PostToolUse` matched to `EnterWorktree` alone —
one hook invocation per relocation, not per tool call, so ADR 0006's cost
measurement does not apply. Measured on 2026-08-30 with Claude Code 2.1.251,
in a disposable Local Issue Markdown Project with linked Worktrees A and B and
a project-level `PostToolUse` hook matched to `EnterWorktree` running the
installed publisher: a session started at A that called `EnterWorktree` with
`path=B` fired the hook exactly once, its input carried
`hook_event_name: PostToolUse`, `tool_name: EnterWorktree`, and `cwd` already
at B (`tool_response.worktreePath` also named B), so the matcher selects the
tool as assumed; the record the publisher wrote from that event had `cwd`,
`repositoryRoot`, and `branch` at B and a `lastActivityAt` later than the
session's `UserPromptSubmit` record at A, so it was the freshest record for
the session across both stores. A `start` that follows `EnterWorktree` in the
same turn therefore sees the relocation, and the fallback this decision held
in reserve — verifying relocation from the next turn boundary and forbidding
a skill from chaining `EnterWorktree` and `start` in one turn — is not needed.
The same run showed that the session's graceful `SessionEnd` at B removed only
B's record; the record left behind at A is stale observation state, pruned
once its process is gone, and is never the freshest.

Measured on 2026-09-05 with Codex CLI 0.153.4, `codex resume <session-id> -C
<path>` preserved the exact Agent Session Identity and conversation history in
a new interactive client. Its `UserPromptSubmit` hook carried the new Worktree
as `cwd`, and a shell command in the resumed turn ran there, so a subsequent
`work start` can use the same verified-location rule. The old client must exit
before the resumed client starts; concurrent clients for one identity are
unsupported. Active Agent Run continuity through that process boundary is now
admitted only through the explicit, two-phase Relocation Intent in
[ADR 0029](0029-preserve-agent-runs-through-declared-codex-relocation.md). A
`cd` inside a tool call remains wrong-location evidence, not relocation.

`ExitWorktree` is the return trip and fires no lifecycle event either, so the
integration subscribes `PostToolUse` matched to `ExitWorktree` as well.
Measured on 2026-09-03 with Claude Code 2.1.259, in a disposable repository
with a project-level `PostToolUse` hook matched to each tool and recording
its input: a headless session that called `EnterWorktree` and then
`ExitWorktree` with `action: keep` fired each hook exactly once; the
`ExitWorktree` input carried `tool_name: ExitWorktree` and `cwd` already back
at the original checkout, which `tool_response.originalCwd` also named, so
the record the publisher writes from it places the session where it
returned, fresher than the `EnterWorktree` record at the Worktree it left.
Before this subscription a returning session stayed placed at the Worktree
it had left until its next turn boundary, and a `start` at the checkout it
returned to was refused for the rest of that turn
([#110](https://github.com/ned2/dashpot/issues/110)). An install that
predates the subscription is reported by `dashpot integrate claude-code
--status` as missing `PostToolUse(ExitWorktree)` and repaired by running
`dashpot integrate claude-code` again.

## Considered options

- **A skill obligation only (`work stop` before relocating):** rejected as
  the sole mechanism because the conflict it fails to prevent leaves declared
  work wrong for as long as the session lives, and because agents relocate
  through a harness tool that runs no Dashpot command.
- **Always move the record on `start` elsewhere:** rejected because a `cd`
  inside a tool call, or a sub-agent, would end the main session's declared
  work while the session keeps working at the old Worktree.
- **Always refuse while a record exists elsewhere:** rejected because a
  relocated Claude Code session could clear its old record only by re-entering
  A. A sequential Codex resume uses ADR 0029's explicit intent and target hook
  evidence to preserve the existing run instead.
- **An explicit `work start --here` or `--move` override:** rejected because
  it lets the agent assert a relocation without evidence, which is the
  inference the Work Store exists to refuse.
- **Claude Code's `CwdChanged` hook in place of the matched `PostToolUse`
  hooks:** left for a separate decision. It fires on every directory change,
  a `cd` inside a tool call included, so adopting it would reopen the
  question this decision answered — whether such a `cd` moves the session —
  and the per-change cost ADR 0006 measures for turn boundaries.
- **Extending the invariant to independent clones:** rejected; `git worktree
  list` does not reach another clone, and ADR 0003 keeps each clone's state
  distinct, so records in two clones keep the `work-session-conflict`
  diagnostic.

## Consequences

- The domain language's Work Store entry changes from authority "at that
  Worktree" to authority for the linked Worktrees of one Git Repository
  jointly, each record still stored beneath the Worktree its run is at; the
  Agent Run entry gains the one-active-run invariant.
- `work start` and `stop` enumerate Worktrees through `git worktree list`
  from the Worktree they run in, read every reachable hook store, and choose
  the freshest record; `validate_session_claim` uses the same rule.
- `dashpot integrate claude-code` installs the matched `PostToolUse` hooks
  for `EnterWorktree` and `ExitWorktree`, and `--status` reports them and
  names a missing one. Codex's ordinary lifecycle hooks publish the fresh
  location on the first resumed turn.
- The `work-session-conflict` diagnostic remains for records written before
  this decision, by an older Dashpot, or across independent clones.
