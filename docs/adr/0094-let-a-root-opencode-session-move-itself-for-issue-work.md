---
status: accepted
date: 2026-10-05
---

# Let a root OpenCode session move itself for Issue work

[ADR 0090](0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md)
reads a root OpenCode session's `session.moved` as a Live Relocation. A move
within one Git Repository keeps the session's identity and carries a bound
Agent Run, with its identity, `startedAt` and Issue Binding. ADR 0090 left
who may trigger a move to [#148](https://github.com/ned2/dashpot/issues/148),
so the Issue-work skill told an OpenCode session never to move itself. Work
in another Worktree went to a new session, started with
`opencode <worktree> --prompt`, and a finished session stayed in its Issue
Worktree, keeping it from Cleanup, until the person moved or deleted it.
Each handoff dropped the conversation.

#148 asks something else: whether Dashpot, as an outside controller, may move
an occupying session as part of a confirmed Cleanup. A session moving itself
while it does Issue work the person asked for is a smaller question, and
[#423](https://github.com/ned2/dashpot/issues/423) asked it on its own. The
maintainer chose the options below on 2026-10-04, in the session that worked
#423; its pull request records the choices.

The model moves its own session with OpenCode's `opencode.session_move`
tool, reached through `execute`. OpenCode 2.0.22's source and the
[acceptance run](../spikes/opencode-v2-self-relocation-acceptance.md) for
#423 settle how the move behaves:

- **When it applies.** The tool's result reports the move at once, but the
  move takes effect when the step ends, and the tool's own description says
  not to run destination-dependent tools in the same call
  ([`tool/plugin/opencode.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/tool/plugin/opencode.ts#L109-L133)).
  A shell called beside the move, in the same step, ran where the session
  was. The next step ran at the destination.
- **The destination.** OpenCode refuses a missing path, a file, or a
  directory whose location cannot be set up before it accepts the move
  ([`session/move.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/session/move.ts#L74-L101)),
  and resolves a relative path against the session's own directory.
- **Permission.** Under the configurations the run tested, OpenCode asked
  the person nothing before a move: a session rule whose effect is `ask`
  over a global rule allowing every tool, and a configuration with no rules.
  A `deny` rule takes the tool away, as
  [#421](https://github.com/ned2/dashpot/issues/421) measured.

## Decision

**Authority.** The person's request to work on an Issue, together with the
Worktree they selected or `worktree create` reported, authorizes a root
OpenCode session to move itself there. The skill names the destination as it
moves and asks for no separate confirmation, as for Claude Code's
`EnterWorktree`. Once the session's Agent Run has stopped, the Issue-work
skill's instruction to leave the Worktree is the authority for the move back.
This decides the session's own moves only. An outside controller moving a
session, and confirmation during Cleanup, stay #148's.

**Who moves.** Only a root session moves, and only itself, within the same
Git Repository: into an Issue Worktree, or back to the Repository's main
Worktree, the first entry of `git worktree list`. A Sub-agent moves no
session, and a worker launched as the `dashpot-worker` agent has no move
tool to call
([ADR 0093](0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)).
The skill moves a session only with OpenCode's own move: a shell
`cd`, a prompt naming a path, or `opencode <directory> --session <id>` leaves
it where it was. A fork or a fresh session is a fallback, never a substitute
for a move that succeeded.

**When.** The session moves once every Sub-agent, background command and
other work it started has ended. A move under running work would leave a
Sub-agent recorded at the place the session left
([#427](https://github.com/ned2/dashpot/issues/427)). A bound run must be on
the Issue of the destination: a run on another Issue finishes first, with its
work delivered and its CI green, then `work stop`. So switching Issues means
finishing the current one, returning to the main Worktree, and dispatching
from there. Finishing never happens implicitly.

**The timing contract.**

1. The session calls the tool through `execute` with the exact absolute path
   and no `sessionID`, alone: no other code in that call and no other tool
   call in its step.
2. The tool's result is a request, not evidence. In the next step the
   session runs `pwd` and `dashpot integrate opencode --status` as one shell
   command, without `cd` or `workdir`. It goes on only when `pwd` prints the
   destination and the status confirms this session's Agent Session
   Identity there. Until then it runs nothing at the destination.
3. At an Issue Worktree, `work show` retains a run that came with the
   session, and only when none did does the session run `work start`. An
   unbound session stays unbound until that explicit opt-in. At the main
   Worktree after finishing, it runs no `work start`.

**Failure.** The move has failed when the tool fails or is unknown, the
person declines it, or the next step's check places the session elsewhere.
The session does not retry the move, change directory with the shell, or
touch Dashpot's state. A move that took effect without Dashpot recording it,
as when the next step's `pwd` prints the destination but `--status` does not
confirm the session there, leaves the session where Cleanup cannot see it,
so the session first moves back to where it came from, with the same check,
or tells the person it is there unrecorded. For dispatch it then falls back
to the fresh-session handoff, after `work stop` for a run on the same Issue.
For finish it tells the person what still holds the Worktree, as before.

**Where `--status` places the session.** Until now, `integrate --status`
confirmed a claimed identity against its freshest hook record wherever that
record was. The acceptance run found that a move Dashpot could not record at
the destination left the freshest record at the source, and `--status` still
read "confirmed" at the destination. The identity line now says
`elsewhere: its freshest hook record, <outcome>, places it at <worktree>, not
here` when that record is in another Worktree, and "confirmed" only when it
places the session here. `work start` already refused in that case. This
applies to every harness, and makes step 4 of the skill's workflow, which
requires "confirmed" at the intended Worktree, mean what it says.

## Considered options

- **Keep the fresh-session handoff only.** Rejected: OpenCode moves the same
  session, with its conversation and run, as a measured Live Relocation,
  while a handoff drops the conversation and cannot carry the run.
- **Ask the person to confirm each move.** Rejected: the request to work on
  the Issue, with its Worktree, already names the destination. OpenCode
  asked nothing itself in the configurations tested, so a separate question
  would come only from the skill, and Claude Code's `EnterWorktree` has
  none. Should OpenCode ask, the person's answer decides.
- **Return to the checkout the session came from.** Rejected: it may be
  unknown, as for a session started in its Issue Worktree, or after context
  compaction. The main Worktree always exists, and a session there holds no
  Worktree from Cleanup.
- **Trust the tool's result.** Rejected: the result comes before the move
  takes effect, and says nothing of whether Dashpot recorded it.
- **Move between Issue Worktrees directly.** Rejected for a bound session:
  the run would move to a Worktree of another Issue. Finishing first and
  returning to the main Worktree keeps one rule for every switch.

## Consequences

- A root OpenCode session started in the main Worktree can work through any
  number of Issue Worktrees, one at a time, in one conversation, and leaves
  each one free for Cleanup once its run has stopped.
- The fresh-session handoff stays for a refused, failed or unconfirmed move.
- The skill relies on the model moving only when it should. A user who wants
  no self-moves can deny `*session_move` for their primary agent. The skill
  then reads the unknown tool as a refusal and hands off.
- A session started at a `--server <url>`, or an OpenCode release that
  changes the move's timing or result, is outside what the acceptance run
  measured
  ([#455](https://github.com/ned2/dashpot/issues/455),
  [#416](https://github.com/ned2/dashpot/issues/416)).
- Amends ADR 0090: who may trigger a move is #148's question only for a move
  made by anyone other than the session itself.
- Amended by
  [ADR 0108](0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md):
  a session moves itself only when `integrate opencode --status` reports its
  Host Process as the shared service; a `--standalone` session, or one whose
  mode is unknown, hands off instead.
