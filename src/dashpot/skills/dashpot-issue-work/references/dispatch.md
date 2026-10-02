# Dispatch Issue work

Use this reference only when the current Agent Session is not already observed
in the intended Worktree.

## Select or prepare the Worktree

1. Resolve the Issue first with `<dashpot> issue show <reference> --json`.
2. If the user selected an existing Worktree, verify its path and Branch. Do not
   treat either as an Issue Binding.
3. Otherwise run `<dashpot> worktree create <reference> --json`. Use the exact
   path, Branch, and base in its report. A refusal that lists an existing
   Worktree is a choice for the user, not authority to reuse it automatically.
4. Prepare the new Worktree using the repository's prescribed dependency or
   bootstrap command. A shell tool may do this before relocation because it is
   repository preparation, not evidence that the Agent Session moved.

## Move a Claude Code session

`EnterWorktree` with `path` enters an Issue Worktree only when the session is
not inside a Worktree it entered. A session launched in the main checkout or
in a linked Worktree can enter one. A session inside a Worktree it entered,
including one resumed there, cannot switch directly to another Issue
Worktree, because Claude Code limits that switch to its own
`.claude/worktrees/`. Such a session first returns to the directory it
entered from. `EnterWorktree` never enters the main checkout.

1. If this session entered a Worktree with `EnterWorktree` and has not left
   it, return first. When the move is to another Issue, first finish the
   current engagement as [Finish the engagement](../SKILL.md#finish-the-engagement)
   requires. Then call `ExitWorktree` with `action: "keep"`. The session goes
   back to the directory it entered from, and the Worktree and Branch stay in
   place. Use `keep`, never `remove`: Claude Code refuses `remove` on a
   Worktree entered by path, and `remove` is not supported for Issue work.
2. Call `EnterWorktree` with the exact path reported above. Its completion
   moves the Agent Session, and an Agent Run the session already holds moves
   with it.
3. Run `<dashpot> work show` from the entered Worktree. If it reports this
   Agent Session working on the intended Issue at that Worktree, retain that
   Agent Run. Otherwise run `<dashpot> work start <reference>` and verify it
   with `<dashpot> work show`.

`ExitWorktree` with `action: "keep"` carries a run back too, and a later
`EnterWorktree` can enter the same Worktree again. A shell `cd` places the
session's later hooks elsewhere but never takes its run along.

## Hand off when `EnterWorktree` is refused

This session cannot reach the Worktree when `EnterWorktree` is still
refused after the return above, when `ExitWorktree` reports that no worktree
session is active, or when the user declines the move. Do not retry, change
directory with the shell, or run `work start` here. The handoff cannot carry
an Agent Run: if `<dashpot> work show` reports an active one for this
session, run `<dashpot> work stop` once this session's delegated work is
done, before handing over.

Give the user one safely shell-quoted command of this shape, which starts a
fresh Claude Code session in the Worktree:

```text
cd <worktree-path> && claude 'Continue Issue <reference>. First run <dashpot> work start <reference> and verify it with <dashpot> work show, then follow the repository workflow through green CI.'
```

That session is a new Agent Session and establishes its own run with
`work start`. A session started in a linked Worktree may lack credentials
the main checkout's environment supplies, so do not promise that `gh` works
there ([#274](https://github.com/ned2/dashpot/issues/274)). Suggest starting
Claude Code sessions from the main checkout, from which a session can always
return and enter the next Worktree. Do not continue the Issue's work in this
session after handing it over.

## Start an OpenCode session in the Worktree

An OpenCode session never leaves the directory it was created in: resumed from
another directory, it still runs, and keeps its Agent Run, where it began. Work
in another Worktree is a new Agent Session there.

1. If `<dashpot> work show` reports an active Agent Run for this session on the
   same Issue, run `<dashpot> work stop` first once its delegated work is done.
2. Give the user one safely shell-quoted command of this shape to run in a
   terminal:

   ```text
   opencode <worktree-path> --prompt 'Continue Issue <reference>. First run <dashpot> work start <reference> and verify it with <dashpot> work show, then follow the repository workflow through green CI.'
   ```

3. Do not continue the Issue's work in this session after handing it over.

## Resume a Codex session

Codex can resume the same Agent Session in another working directory. Exit
the old client to release the thread before continuing the session: while another
runtime owns the thread, a competing client only shows a read-only transcript
with a retry key and publishes no lifecycle hooks. An idle client still owns
its thread.

1. Run `<dashpot> integrate codex --status` and capture the confirmed Agent
   Session Identity.
2. Run `codex resume --help`. Prefer resume only when this Codex version supports
   both a session identifier and `-C`/`--cd`.
3. Run `<dashpot> work show`. If it reports an active Agent Run for this
   session, run `<dashpot> work relocate <worktree-path>` and require its
   confirmation before exit. With no active run, omit this step; relocation
   never creates an Issue Binding.
4. Give the user one safely shell-quoted command of this shape:

   ```text
   codex resume <session-id> -C <worktree-path> 'Continue Issue <reference>. First run <dashpot> work show. If it reports this session already working on Issue <reference>, retain that Agent Run; otherwise run <dashpot> work start <reference> and verify it with <dashpot> work show. Then follow the repository workflow through green CI.'
   ```

5. Tell the user to exit this client and then run the command. If they run
   it first, the target client stays read-only until they exit this client
   and press `R`. Do not continue in the old client after handing over the
   command. The resumed client's first turn publishes the hook that completes
   a declared relocation once it proves the same Agent Session Identity at the
   intended Worktree with no live or unobservable client elsewhere.

If session identity cannot be confirmed or this Codex version lacks compatible
resume support, explain the limitation and give the same quoted instruction to
a fresh session instead:

```text
codex -C <worktree-path> 'Continue Issue <reference>. First run <dashpot> work start <reference> and verify it with <dashpot> work show, then follow the repository workflow through green CI.'
```

This fallback creates a new Agent Session. It is compatibility behavior, not
the preferred path. It cannot preserve an active Agent Run: end the old run
explicitly once its session and agents are finished, then let the new session
establish its own run with `work start`. When the user wants to keep the
model's context instead, offer the `/cd` handoff below.

## Hand off a Codex session with `/cd`

When the user prefers to keep the model's context without preserving the
Agent Session, they may run `/cd <worktree-path>` in the live Codex client.
Codex forks the conversation into a new thread at that directory: Dashpot
observes a new Agent Session with a new hook `session_id`, whose
`SessionStart` reports `startup` and names no parent thread (Codex 0.154.0).
The old session's Agent Run cannot move with it. Only a person can run `/cd`;
the model cannot invoke it.

1. Finish delegated work and let the turn end. At Codex 0.154.0, `/cd` needs
   an idle primary session with no queued input, active background terminals,
   or running side agent, and a trusted target directory.
2. If `<dashpot> work show` reports an active Agent Run for this session, run
   `<dashpot> work stop` first. Do not run `work relocate`: a forked thread
   cannot complete a Relocation Intent.
3. Tell the user to run `/cd <worktree-path>`, then send the quoted prompt
   from the fallback command above as the first turn there.
4. In the new session, declare Issue work only with `work start`. Never infer
   it from the inherited history or the destination path.

`/worktree` does not apply: it creates a managed detached checkout instead of
entering a prepared Issue Worktree.
