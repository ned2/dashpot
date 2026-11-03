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
   it, return first. When the move is to another Issue, finish the current
   engagement as [Finish the engagement](../SKILL.md#finish-the-engagement)
   requires, which already returns the session. Otherwise call
   `ExitWorktree` with `action: "keep"`. The session goes back to the
   directory it entered from, and the Worktree and Branch stay in place. Use
   `keep`, never `remove`: Claude Code refuses `remove` on a Worktree entered
   by path, and `remove` is not supported for Issue work.
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
session on the same Issue, run `<dashpot> work stop` once this session's
delegated work is done, before handing over. A run on another Issue ends
only as [Finish the engagement](../SKILL.md#finish-the-engagement) requires.

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

## Move an OpenCode session

A root OpenCode Agent Session moves itself with OpenCode's own move tool. The
user's request to work on the Issue, with the Worktree they selected or
`worktree create` reported, is the authority for the move; name the
destination as you make it. Only OpenCode's move relocates a session: a shell
`cd`, a prompt naming a path, or `opencode <directory> --session <id>` leaves
it, and its Agent Run, where it was. A Sub-agent moves no session, its own or
another's.

A session moves itself only on the user's shared OpenCode service, the one
hosting mode where the move is measured. Read the `OpenCode Host Process
mode` line that `<dashpot> integrate opencode --status` prints beside the
confirmed identity: move only when it reads `shared-service`. On
`standalone` or `unknown`, make no move. To dispatch, hand off as
[after a failed move](#hand-off-when-the-opencode-move-fails); to finish,
tell the user what holds the Worktree, as after a failed move back.

1. Move once every Sub-agent, background command, and other work this session
   started has ended; until then, wait for it. Run `<dashpot> work show`,
   which also lists a bound session's Sub-agents still reported as working.
   An active Agent Run moves with the session, so it must be on the intended
   Issue: a run on another Issue ends first, as
   [Finish the engagement](../SKILL.md#finish-the-engagement) requires, which
   returns the session to the main Worktree.
2. Call `tools.opencode.session_move({ directory: "<worktree-path>" })`
   through `execute`, with the exact absolute path and no `sessionID`, alone:
   no other code in that `execute` and no other tool call in the same step.
   Its result already reports the move, but the move takes effect when the
   step ends, so the result is a request, not evidence. If OpenCode asks the
   user to allow the move, the answer is theirs.
3. In the next step, run `pwd` and `<dashpot> integrate opencode --status` as
   one shell command, without `cd` or `workdir`. Continue only when `pwd`
   prints the Worktree path and the status confirms this session's Agent
   Session identity claimed there. Until then, run no `work` command and none
   of the Issue's work in the Worktree.
4. Run `<dashpot> work show`. If it reports this Agent Session working on the
   intended Issue at that Worktree, retain that Agent Run. Otherwise run
   `<dashpot> work start <reference>` and verify it with `<dashpot> work show`.

The move does not change the environment the session's commands run with
while the service keeps running, so `gh` works in the Worktree if it worked
before the move ([#274](https://github.com/ned2/dashpot/issues/274)).

## Hand off when the OpenCode move fails

The move has failed when the tool fails or is unknown, the user declines it,
or step 3 does not confirm it. A session whose Host Process mode is not
`shared-service` hands off the same way without trying the move. Do not
retry the move, change directory with the shell, or run `work start` where
the session is.

When step 3's `pwd` printed the Worktree but its status did not confirm the
identity there, the move took effect without Dashpot recording it, and
Cleanup would not see the session in that Worktree. Move the session back
first: steps 2 and 3 with the directory it came from, naming it as you move.
If that move is not confirmed either, tell the user the session is in the
Worktree without Dashpot's record of it, and holds it until the session is
moved elsewhere or deleted in OpenCode.

Work in the
Worktree becomes a new Agent Session there, started by a plain `opencode` in
that Worktree, which runs it in the user's shared OpenCode service. Do not
suggest `--server <url>`: Dashpot does not support a session on a server
named that way. The command gives the new session the environment of the
terminal it runs in ([#274](https://github.com/ned2/dashpot/issues/274)),
and a terminal in a linked Worktree may lack credentials the main checkout's
environment supplies: suggest running it from a terminal where `gh` works,
such as one in the main checkout.

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

The resume and fresh `-C` commands in this section run the session's
commands with its Host Process's environment
([#274](https://github.com/ned2/dashpot/issues/274)). While the managed
daemon, the default, keeps running, that is the environment it started
with: `-C` and the terminal that runs the command leave it unchanged, so
`gh` works in the Worktree if it works in this session now. When no daemon
runs, the terminal that runs the command starts one with its own
environment, and a terminal launched with `--disable daemon_auto_start`
hosts its session itself with that environment: then suggest running the
command from a terminal where `gh` works, such as one in the main checkout.

On Codex 0.166.0 on Linux, a launch with `--profile` or the sandbox/cache
`-c` options below runs in its own client instead (measured). Its commands
get that terminal's environment. A loaded client environment alone does
not prove the shell's credential or cache environment; recheck those in
the resumed session.

`-C` places the session, not the client process: Codex never changes its
own process's directory, so the client keeps the directory of the terminal
that runs the command. Cleanup's `process` blocker counts that client, and
the terminal's shell, inside whatever Worktree that directory is in, until
both leave. Suggest a terminal outside every Worktree the user may later
remove, such as one in the main checkout.

### Preserve launch options

Build `<launch-options>` from the session's original launch:

- **Legacy sandbox launch:** carry its `--sandbox`, `--add-dir`, network,
  `shell_environment_policy.set` cache/transport settings and chosen
  approval options. Use the same approved paths and values. The
  execute-issues resume command with these grants qualified on Codex
  0.166.0 on Linux (measured).
- **Profile launch:** carry `--profile <name>` and pin it with
  `-c 'default_permissions="<name>"'`. On 0.166.0 on Linux, `--profile`
  alone kept a resumed thread's saved `:workspace` permissions; adding the
  pin applied the intended profile (measured). Keep approval settings in
  the chosen profile. Beside `--profile` without the pin, `--sandbox` or
  `--approve-for-me` replaced its grants with legacy sandbox permissions
  (measured). Keep both legacy options off the profile launch.

These results are in the
[launch qualification](https://github.com/ned2/dashpot/blob/main/docs/spikes/codex-lead-launch-qualification-spike.md).
Losing grants or cache settings when moving with a bare resume is an
inference: a bare resume after legacy `-c sandbox_*` options remains
unmeasured. Use a bare resume only for a session with no extra launch
grants or environment settings to preserve. If the original options are
unknown, recover the operator's launch command before handing off; do not
invent grants. Replace `<launch-options>` with the actual options (or omit
it for that bare case), and recheck capabilities inside the resumed
session before Issue work.

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
   codex resume <session-id> -C <worktree-path> <launch-options> 'Continue Issue <reference>. Verify destination identity with <dashpot> integrate codex --status, run <dashpot> work show, and recheck launch capabilities before Issue work. If show reports this session already working on Issue <reference>, retain that Agent Run; otherwise run <dashpot> work start <reference> and verify it with <dashpot> work show. Then follow the repository workflow through green CI.'
   ```

5. Tell the user to exit this client and then run the command. If they run
   it first, the target client stays read-only until they exit this client
   and press `R`. On Codex 0.166.0 on Linux, a resume with launch options
   runs in its own client. While the managed daemon still holds the thread,
   that client stays read-only and says the conversation is open in another
   app, even when it starts after this client exits. Unhindered, the daemon
   releases the thread about 60 s after this client exits, and a retry
   before then is refused again. After the retry that resumes it, the
   client does not send the command's prompt, so the user types the prompt
   again (measured). Do not continue in the old client after handing over
   the command. The resumed client's first turn publishes the hook that completes
   a declared relocation once it proves the same Agent Session Identity at the
   intended Worktree with no live or unobservable client elsewhere.

If session identity cannot be confirmed or this Codex version lacks compatible
resume support, explain the limitation and give the same quoted instruction to
a fresh session instead:

```text
codex -C <worktree-path> <launch-options> 'Continue Issue <reference>. Verify destination identity with <dashpot> integrate codex --status, recheck launch capabilities, then run <dashpot> work start <reference> and verify it with <dashpot> work show. Follow the repository workflow through green CI.'
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
`SessionStart` reports `fork` (Codex 0.166.0). The old session's Agent Run
cannot move with it. Only a person can run `/cd`; the model cannot invoke it,
and no tool the model holds moves the session.

1. Finish delegated work and let the turn end. At Codex 0.166.0, `/cd` needs
   an idle primary session with no queued input, active background
   terminals, or other running agent, saved conversation history, and a
   trusted target directory or the user's consent to trust it. It refuses
   a remote workspace and a named permission profile not yet confirmed.
2. If `<dashpot> work show` reports an active Agent Run for this session, run
   `<dashpot> work stop` first. Do not run `work relocate`: a forked thread
   cannot complete a Relocation Intent.
3. Tell the user to run `/cd <worktree-path>`, then send the quoted prompt
   from the fallback command above as the first turn there.
4. In the new session, declare Issue work only with `work start`. Never infer
   it from the inherited history or the destination path.

The old session stays where it was: Dashpot shows it live there, and
Cleanup's `agent-session` blocker holds that Worktree, until Codex unloads
it about a minute after `/cd`. Like `-C`, `/cd` does not move the client
process, so the `process` blocker described under
[Resume a Codex session](#resume-a-codex-session) applies.

`/worktree` does not apply: it creates a managed detached checkout instead of
entering a prepared Issue Worktree.
