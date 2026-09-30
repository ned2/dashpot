---
status: accepted
date: 2026-10-01
---

# Block Worktree removal while a sub-agent is working

[ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)
refuses to remove a Worktree occupied by an Agent Session or an Agent Run, and
[ADR 0036](0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md) and
[ADR 0054](0054-finish-a-worktree-with-its-branch-by-default.md) keep that gate
while changing the preview around it. The gate did not see a sub-agent
([#279](https://github.com/ned2/dashpot/issues/279)). A Claude Code sub-agent
runs inside its parent's process with the parent's `session_id`
([ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md)), so its
hook events land in the parent's record, at the parent's location. It holds no
Agent Run of its own, because a sub-agent must not run `work start`. A session
at the main checkout that dispatched one sub-agent per Issue Worktree showed
no occupant in any of them, and a confirmed Cleanup could remove a Worktree
with the sub-agent's uncommitted work in it.

The hook store already holds each session's live sub-agents, the `agent_id`
of each one started and not yet stopped
([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)). It
holds no location for any of them, and Claude Code 2.1.285 publishes none
([measurement](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)).
The `cwd` of `SubagentStart`, of the sub-agent's tool hooks, and of
`SubagentStop` is the parent's current directory. The one exception is a
sub-agent the Agent tool isolates in a worktree of its own. A sub-agent that
runs `cd <Worktree> && …`, or edits files by absolute path, shows up in no
hook's `cwd` and fires no `CwdChanged`.

## Decision

Cleanup will not call a Worktree unoccupied while a sub-agent it cannot place
might be working in it.

- **A live sub-agent blocks every Worktree of its Repository.** Cleanup
  checks each live Agent Session, or one whose liveness is unknown, that a
  hook record places at a Worktree of the target's Repository. If that
  session has any live sub-agent, Worktree removal gets a `sub-agent`
  blocker. Each checkout's store derives the live set from its own previous
  record, so a session that dispatched sub-agents and then entered another
  Worktree holds them only in the record it left behind: the live set is the
  union over every record of the session that is not over, and the blocker
  reports the session's freshest location. The blocker names the session, where it is, and the
  agent IDs. It also says that Dashpot cannot tell which Worktree a sub-agent
  works in, so the block is not read as a claim that a sub-agent is here. A
  session that is already at the target is reported only as the
  `agent-session` occupant.
- **The evidence ends with the sub-agent or its session.** `SubagentStop`
  removes the agent from the live set. A `SessionEnd` removes the record,
  and a new `SessionStart` starts with no sub-agents. A session whose process
  is gone blocks nothing. A session whose liveness is unknown still blocks,
  as it does at its own Worktree.
- **It is one more occupancy blocker.** It is assessed with the others, so
  `dashpot worktree check`, the Cleanup preview, `dashpot worktree remove`,
  and the re-inspection on confirmation all report it. Observation stays
  passive, and no Agent Run, Issue Binding, or Work Store record is created
  for a sub-agent.
- **Only Claude Code sub-agents are covered.** Dashpot's Codex integration
  does not subscribe to `SubagentStart` or `SubagentStop`, so a Codex
  session's sub-agents are not observed, and the refusal names Claude Code.

## Considered options

- **Place each sub-agent by `SubagentStart`'s `cwd` and block only that
  Worktree** (the precise shape #279 preferred): rejected. That `cwd` is the
  parent's directory at spawn, which is exactly the case this decision fixes.
  It would name the main checkout and leave the Issue Worktree removable.
- **Subscribe to every tool call and follow a sub-agent's Bash commands:**
  rejected. Tool hooks carry the session's `cwd`, not the shell's. Finding a
  `cd` in the command text is guesswork, and it still misses absolute-path
  file edits. It would also add the per-tool-call cost that
  [ADR 0006](0006-observe-agent-activity-at-turn-boundaries.md) and ADR 0016
  declined.
- **Consider every session on the machine:** rejected. A sub-agent of a
  session placed in another Repository blocks nothing here. One launched
  outside any Worktree of this Repository that works inside it is a known
  gap, recorded in the agent-session documentation.
- **Remove under a session that is only waiting:** rejected on 2026-09-30 for
  every occupant. A `waiting` observation does not prove that background work
  or sub-agents have drained.

## Consequences

- Removing a Worktree is refused, in both the preview and the command line,
  while any Claude Code session in the Repository has a sub-agent working,
  including in Worktrees no sub-agent is in. The person waits for the
  sub-agents to finish or ends the session.
- A `SubagentStop` that the harness never delivers keeps the block until the
  session ends or starts again. This is the same bound ADR 0016 accepted for
  holding the session running.
- A sub-agent that stops after its session has moved to another Worktree
  has its `SubagentStop` recorded in the new Worktree's store, which never
  listed it, so the record left behind keeps it live and the block holds
  until the session's process exits. The block errs toward refusing a
  removal rather than allowing one.
- Relocating occupants during Cleanup
  ([#148](https://github.com/ned2/dashpot/issues/148)) must account for
  sub-agents under this rule. It cannot place one either, unless a new source
  of evidence says where a sub-agent works.
