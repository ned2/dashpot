---
status: accepted
date: 2026-10-02
---

# Return a Claude Code session before entering another Issue Worktree

The Issue-work skill moves a Claude Code session into an Issue Worktree with
`EnterWorktree`, which carries a bound run along
([ADR 0074](0074-carry-a-claude-code-run-only-on-its-worktree-tools.md)).
[Issue #327](https://github.com/ned2/dashpot/issues/327) saw that call refused
on 2.1.283 because the target was not under `<repo>/.claude/worktrees/`.
Measured on Linux against 2.1.286, and repeated on 2.1.283 and 2.1.287, with
each trace retained, through Dashpot's real publisher
([measurement](../agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286)):

- A session that is not inside a worktree it entered, whether launched in
  the main checkout or in a linked Worktree, enters any linked Worktree of
  the Repository with `EnterWorktree` and `path`.
- A session already in a worktree it entered may switch directly only to a
  worktree under `.claude/worktrees/`. This includes a session resumed in
  that worktree, whose transcript restores the worktree session. Claude
  Code refuses any other target and fires no hook.
- `ExitWorktree(keep)` returns such a session to the directory it entered
  from, resumed or not, and removes nothing. From there `EnterWorktree`
  enters the next Issue Worktree, or the same one again.
- `EnterWorktree` never enters the main checkout.

Dashpot's Worktrees cannot live under `.claude/worktrees/`. The Worktree Root
refuses a pool inside any Worktree of the Project, and
[ADR 0039](0039-anchor-the-default-worktree-root-on-the-main-working-tree.md)
puts the default pool beside the main checkout. Worktrees are also shared by
every harness, so one harness's private directory is the wrong home for them.

## Decision

A Claude Code session moves between Issue Worktrees through the directory it
entered from. When it is already inside an entered Worktree, the skill
finishes the current engagement if the move is to another Issue, then calls
`ExitWorktree` with `action: "keep"`, then `EnterWorktree` with the next
Worktree's path, then `work show` and, only when no carried run is shown,
`work start`. The skill never uses `action: "remove"` for Issue work.

When `EnterWorktree` still refuses, `ExitWorktree` finds no worktree session
to leave, or the person declines the move, the skill hands the work to a
fresh Claude Code session with one shell-quoted
`cd <worktree> && claude '<prompt>'` command, the Claude Code counterpart of
the Codex and OpenCode fresh-session routes. It runs no `work start` where
the session is and does not try a shell `cd`. A fresh session cannot carry
the old Agent Run, so the old session ends a run on the same Issue with
`work stop` once its delegated work is done, and the new session starts its
own; a run on another Issue ends only when its engagement finishes.
The handoff does not promise working `gh` credentials in a linked Worktree
([#274](https://github.com/ned2/dashpot/issues/274)). The skill suggests
launching Claude Code sessions from the main checkout, from which the return
route always exists. Worktree Root behaviour does not change.

## Considered options

- **Create Issue Worktrees under `.claude/worktrees/`.** Rejected: the
  Worktree Root refuses a pool inside a Worktree. The directory belongs to
  one harness, while every harness shares Issue Worktrees, and
  `ExitWorktree(remove)` deletes worktrees there along with their Work Store
  (ADR 0074).
- **Always hand off to a fresh session.** Rejected: it creates a new Agent
  Session and drops the model's context, while the measured return route
  keeps both and is available to every session that entered its Worktree.
- **Retry or `cd` after a refusal.** Rejected: the refusal is deterministic,
  a `cd` out of the project is reset, and a `cd` into another Worktree
  carries no run (ADR 0074).

## Consequences

- A session launched in the main checkout can work through any number of
  Issue Worktrees, one at a time, without a new Agent Session.
- A session launched in, or resumed in, an Issue Worktree can still return
  with `ExitWorktree(keep)`. The fresh-session handoff covers what remains:
  an unmeasured release or mode, or a person declining the move when Claude
  Code asks before entering a worktree outside `.claude/worktrees/`.
- Leaving a Worktree once its engagement finishes,
  [#347](https://github.com/ned2/dashpot/issues/347), can rely on
  `ExitWorktree(keep)` returning the session and on a later `EnterWorktree`
  of the same Worktree for follow-up changes.
