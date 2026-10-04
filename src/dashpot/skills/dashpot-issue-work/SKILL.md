---
name: dashpot-issue-work
description: Manage declared Dashpot Issue work, including starting, switching, finishing, handing off, recovering, and preparing or reusing Issue Worktrees. Use whenever repository work belongs to an Issue observed by Dashpot.
---

<!-- dashpot-managed-skill: dashpot-issue-work -->

# Work on a Dashpot Issue

This skill is written for Dashpot 0.1.0.

## Establish the workflow

1. Read the repository's agent instructions, contribution workflow, and domain
   language before changing anything. Use the Dashpot invocation they prescribe;
   otherwise use `dashpot`.
2. Run `<dashpot> --version`. If it is not `0.1.0`, stop and ask the user to
   rerun `<dashpot> integrate <harness>` before continuing. Do not guess at a
   newer or older command contract.
3. Run `<dashpot> issue show <reference> --json`. Continue only when exactly one
   fresh Issue resolves from the configured Issue Source and Profile.
4. Run `<dashpot> integrate <harness> --status` from the intended Worktree,
   using `codex` for Codex, `claude-code` for Claude Code, or `opencode` for
   OpenCode, and require its
   `Agent Session identity claimed here` line to be confirmed. If a Worktree
   must be selected, prepared, or entered, read
   [dispatch](references/dispatch.md) and complete that branch first.
5. Run `<dashpot> work show` from that Worktree. When it already reports this
   Agent Session working on the intended Issue, retain that Agent Run. Otherwise
   run `<dashpot> work start <reference>`, then `work show`. Continue only when
   `show` reports the intended Issue at the intended Worktree.
6. Follow the repository's implementation, test, commit, push, review, and CI
   workflow. Keep the Issue Binding active across the entire engagement.

Never infer an Issue Binding from a Branch, Worktree, conversation, or Issue
lookup. Only `work start` declares it; `work relocate`, Claude Code's
`EnterWorktree`, and OpenCode's session move can preserve that existing
binding but cannot create one.
Observation commands and dashboards stay passive; run a management command
only for the action the user requested.

## Finish the engagement

Wait until this Agent Session and every agent or process it started are done,
the final push has landed, and required CI is green. Then run `<dashpot> work
stop` and `<dashpot> work show`. Completion means `show` reports no active Issue
work for this Agent Session.

Then, if this session is in an Issue Worktree, take it out of that Worktree.
A session there, even an idle one, keeps the Worktree from Cleanup. This step
is the instruction to do so; do not wait for the user to ask:

- **Claude Code, entered with `EnterWorktree`.** Call `ExitWorktree` with
  `action: "keep"`, and only after `show` reports no active Issue work: an
  Agent Run still bound would move back with the session. Check that the
  result names the directory the session is back in; if that is another
  Issue Worktree, the session was started there, as in the next case. Never
  use `remove`.
- **Claude Code, started in the Worktree.** There is nothing to exit. If you
  cannot tell which case applies, call `ExitWorktree` with `action: "keep"`
  anyway: in a session that did not enter its Worktree, it reports that no
  worktree session is active and changes nothing. Here that answer is
  expected, not a refusal to recover from or a reason to hand off. Tell the
  user this session keeps the Worktree from Cleanup until it ends or enters
  another Worktree.
- **Claude Code, reached by a shell `cd`.** Change the shell back to the
  directory the session started in.
- **Codex.** The model cannot move its own session. Tell the user this
  session keeps the Worktree from Cleanup until its client exits, and that
  `codex resume <session-id> -C <directory>` continues it elsewhere after
  that. A daemon-hosted thread ends about 60 s after its last client leaves.
- **OpenCode.** Move the session to the Repository's main Worktree, the
  first entry of `git worktree list`, with steps 2 and 3 of the OpenCode
  move in [dispatch](references/dispatch.md), and only after `show` reports
  no active Issue work: an Agent Run still bound would move with the
  session. Run no `work start` there. If the move fails, tell the user the
  session keeps the Worktree from Cleanup until it is moved to another
  location in OpenCode, it is deleted with
  `opencode session delete <session-id>`, or the OpenCode server it runs in
  stops; quitting a client leaves it running.

If the user asks for follow-up changes afterwards, a session that left goes
back to the same Worktree and checks `<dashpot> work show` before any
`work start`: Claude Code enters it again with `EnterWorktree`, as steps 2
and 3 of the Claude Code move in [dispatch](references/dispatch.md)
describe, and OpenCode moves there with the whole OpenCode move. A session
still in the Worktree, or resumed there, continues from step 5 of
[Establish the workflow](#establish-the-workflow).

Keep the Issue Worktree and its Branch in place unless the user explicitly
requests Cleanup. Cleanup remains a separate preview-and-confirm workflow.

## Recover a refusal

Read [recovery](references/recovery.md) only when a command is refused, the
session is observed at the wrong location, resume is unavailable, or existing
state prevents the ordinary workflow. Preserve the refusal's safety boundary;
do not repair Dashpot state by hand.
