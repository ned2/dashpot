# Recover Issue work safely

Follow the branch matching the observed refusal. Keep resolution, Worktree
preparation, session relocation, Issue Binding, repository delivery, and cleanup
as separate actions.

## Version mismatch or missing skill

Ask the user to run `<dashpot> integrate <harness>` explicitly. The command
updates the lifecycle hooks and this skill together. Restart the harness only if
it does not detect the installed skill. Recheck `<dashpot> --version` before
resuming the workflow.

## Wrong Observation Location

Run `<dashpot> integrate <harness> --status` and inspect the `Agent Session
identity claimed here` line. A shell tool's `cd`, a sub-agent working elsewhere,
or a prompt that merely names a path does not move the Agent Session. Use
Claude Code's `EnterWorktree` or the sequential Codex resume flow in
[dispatch](dispatch.md), then retry `work show` only after fresh hook evidence
places the session there. Run `work start` only when no preserved run is shown.

## Installed hooks have not published this session

Do not continue past an unconfirmed identity. A non-interactive harness may be
unable to ask the user to trust a newly changed hook configuration; rerunning
`integrate` cannot grant that harness permission. Ask the user to review and
approve the installed hook in an interactive client, then begin a fresh turn so
`SessionStart` or `UserPromptSubmit` publishes the record. Do not disable hook
trust as an ordinary workflow shortcut.

## Existing Worktree or Branch collision

Report the paths and recovery commands from `worktree create`. Reuse an existing
Worktree only when the user selects it. Use `--branch NAME` only when the user
chooses a distinct approach. Do not delete, reset, force, or rename existing
work to clear a collision.

## Initializing lock or partial creation

Follow the recovery commands in Dashpot's refusal exactly. Inspect before
removing any lock or partial path, and ask before any destructive action. Retry
`worktree create` so Dashpot can revalidate the complete operation.

## Incompatible configuration or dirty Worktree

Do not bypass the Project configuration check or move uncommitted work. Report
the mismatch or dirty paths and let the user choose the correct base, Project,
or recovery action.

## Orphaned Agent Run

Use `work show` to identify it. End an orphan only with the explicit
`work stop --session <session-key>` management command and only when the user
asked to end that exact run. Never edit the Work Store directly.

## Pending Codex relocation

`work show` names the intended Worktree while the Relocation Intent is pending.
Resume the same session there. A target hook waits while an old client remains
live or unobservable; exit that client cleanly and begin another target turn.
A hook at a different Worktree cannot complete or reassign the run, so resume at
the named target instead. If resume at the target fails, resume the same session
at its original Worktree and run `<dashpot> work relocate .` to cancel the
intent without restarting the run. If the move is abandoned with no session to
resume, use the exact `work stop --session <session-key>` command from the
`work-relocation-pending` Diagnostic after confirming that run should end.

## Failed Codex resume

Keep the prepared Worktree. If the old client is still running, exit it before
retrying. If the installed Codex cannot resume the confirmed identity with
`-C`, use the fresh-session fallback from [dispatch](dispatch.md) and disclose
that it starts a new Agent Session. A fresh session cannot complete a Relocation
Intent for another Agent Session; end the old run explicitly, then run `work
start` and `work show` in the new session.
