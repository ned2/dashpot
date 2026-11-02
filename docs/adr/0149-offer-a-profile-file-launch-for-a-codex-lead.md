---
status: accepted
date: 2026-11-02
---

# Offer a profile-file launch for a Codex Lead

[ADR 0148](0148-let-workers-write-their-own-arc-ledger-files-and-commit-under-codexs-sandbox.md)
decided that a Codex Lead whose sandbox checks fail gives the user one
command, a `codex resume` with `--sandbox workspace-write`, two `--add-dir`
options, the network option and the two cache options. It left one
interaction unmeasured: Codex documents that a configuration selecting a
named permissions profile with `default_permissions` must not be combined
with `sandbox_mode`, which that command sets.

The [Codex Lead launch qualification experiment](../spikes/codex-lead-launch-qualification-spike.md)
measured, on codex-cli 0.166.0 on Linux:

- **The command still qualifies.** The Lead's four checks pass, its control
  write is refused, and a fresh v2 Worker completes its whole cycle: gate,
  commit with hooks, push, and its Arc Ledger file.
- **It drops the user's own permissions profile.** Its `--sandbox` puts
  the session under Codex's legacy sandbox. Over a configuration whose
  `default_permissions` profile denied a file, the resumed session read
  that file.
- **A profile file grants the same without the legacy sandbox.**
  `$CODEX_HOME/<name>.config.toml`, selected with `--profile <name>`, can
  name its own permissions profile with the Worktree Root, the Git
  directory and the network, and set both caches. A new session started
  with it passes every check and a Worker completes its cycle.
- **A profile that extends the user's keeps their deny rules.** With
  `extends = "<their profile>"` and only the two directories added, the
  denied read still failed, the network stayed on, and a Worker completed
  its cycle.
- **A resume needs the profile pinned.** A resumed thread keeps the
  permissions profile it last ran under. A thread first started without
  options ran under the built-in `:workspace`, and
  `codex resume <id> --profile <name>` kept it and refused every grant.
  Adding `-c 'default_permissions="<name>"'` made the file's profile win,
  and that launch passed with a Worker's cycle.
- **The Git directory must be named.** A profile granting only the
  Worktree Root left the main checkout's `.git` read-only.
- **`--sandbox` and `--approve-for-me` undo the profile.** Beside
  `--profile`, either put back a legacy sandbox with no added directory and
  no network. `--approve-for-me` also set the automatic reviewer and
  `on-request` on the thread, and its later resumes kept them.

## Decision

**The Lead offers the profile-file launch beside the resume command.** When
a check fails, the Lead's message gives the user both:

- the resume command ADR 0148 records, unchanged;
- a profile file for the user to write in their Codex home, with the start
  command `codex -C <checkout> --profile <name>` and the resume command
  `codex resume <session-id> -C <checkout> --profile <name> -c 'default_permissions="<name>"'`.

Where the user's configuration sets `default_permissions`, the Lead tells
them the resume command runs without their profile, deny rules included,
and offers the profile launch in its place, with a file that extends their
profile.

The file names its own permissions profile, grants the Worktree Root and
the Git directory by explicit rule, enables the network unless the profile
it extends already does, and sets the gates' caches in `[shell_environment_policy.set]`.
The Lead never writes the file; it lives in the user's Codex home and
holds their policy. Neither launch takes `--sandbox` or `--approve-for-me`
beside `--profile`. The Lead runs its four checks in the new session either
way.

## Considered options

- **Replace the resume command with the profile launch.** Rejected. The
  command needs no file and qualified again on 0.166.0. For a user without
  a permissions profile of their own, it is the shorter remedy.
- **Keep only the resume command.** Rejected. For a user whose
  configuration selects a permissions profile, it silently removes that
  profile's deny rules for the whole Arc.
- **Offer `codex resume <id> --profile <name>` without the pin.** Rejected:
  it kept the thread's saved profile and refused every grant. Which profile
  it takes depends on the thread's history, which the Lead cannot see.
- **Let the Lead write the profile file.** Rejected. It is the user's
  Codex configuration, outside every directory the Lead's grant names, and
  a Lead that wrote its own permissions would be widening its own sandbox.

## Consequences

- Amends ADR 0148's sandbox remedy. ADR 0148's measured resume command
  stands as one of the two launches.
- The skill's `references/harnesses.md` Codex section gains the profile
  file, both launch commands, the `extends` rule, and the measured
  `default_permissions` interaction. It drops its claims that the fourth
  check and the Lead's own shell getting the moved caches are unmeasured.
- A launch with `--profile`, or a `-c` option outside a short list of
  display and feature switches, runs in its own TUI client, which is then
  the session's Host Process, so its commands get that terminal's
  environment. A plain launch runs on the managed daemon. The skill keeps
  the caches in `shell_environment_policy.set`, which reached every Worker
  under both launches.
- `codex sandbox --profile <name>` shows what a new session started with
  that file grants, as the read-only preflight
  [#679](https://github.com/ned2/dashpot/issues/679) proposes. It cannot
  show what a resume grants, since it reads no thread, so the checks in the
  session stay the Lead's evidence.
- Not measured: macOS, `gh` under either grant, a thread last saved under
  a named profile other than `:workspace`, and `approvals_reviewer` set in
  a profile file in place of `--approve-for-me`.
