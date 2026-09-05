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

Call `EnterWorktree` with the exact path reported above. After it succeeds, run
`<dashpot> work start <reference>` and `<dashpot> work show` from the entered
Worktree. The fresh relocation hook record must confirm that location.

## Resume a Codex session

Codex can resume the same Agent Session in another working directory, but the
old interactive client must exit before the resumed client starts. Concurrent
clients for one Agent Session are unsupported.

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

5. Tell the user to exit this client before running it, and do not continue in
   the old client after handing over the command. The resumed hook completes a
   declared relocation only after it proves the same Agent Session Identity at
   the intended Worktree and no live or unknown client remains elsewhere.

If session identity cannot be confirmed or this Codex version lacks compatible
resume support, explain the limitation and give the same quoted instruction to
a fresh session instead:

```text
codex -C <worktree-path> 'Continue Issue <reference>. First run <dashpot> work start <reference> and verify it with <dashpot> work show, then follow the repository workflow through green CI.'
```

This fallback creates a new Agent Session. It is compatibility behavior, not
the preferred path. It cannot preserve an active Agent Run: end the old run
explicitly once its session and agents are finished, then let the new session
establish its own run with `work start`.
