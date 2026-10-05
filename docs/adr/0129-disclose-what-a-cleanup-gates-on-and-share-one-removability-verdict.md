---
status: accepted
date: 2026-10-05
---

# Disclose what a Cleanup gates on, and share one removability verdict

A Cleanup shows a preview, and a confirmation performs only what that preview
showed, compared by its fingerprint
([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
Several of the preview's facts did not hold to that
([#540](https://github.com/ned2/dashpot/issues/540)):

- A Branch counted as in use only where a Worktree record named it. Git
  lists a Worktree mid-rebase or mid-bisect as detached, yet refuses to
  delete the Branch being rebased or bisected there, so the preview offered
  a deletion Git would refuse.
- The fingerprint covered each target's identity, commit, dependency and
  blocker kinds, but not its integration state or consequences. A Branch
  that went from integrated to content-integrated between preview and
  confirmation was deleted on a confirmation of the other state.
- The commands a preview names were built by string interpolation, so a
  Branch name or a path with shell metacharacters printed a command that
  ran something else when pasted.
- Observation, `dashpot work` and Cleanup each wrote their own test for an
  Orphaned Agent Run, and Cleanup's omitted the pending relocation that the
  other two except.
- Report text carrying Git's own words, such as `! [remote rejected]`, and
  a path with brackets, were parsed as Textual markup, which either dropped
  them or failed the screen.
- The probe that says whether a lock's holding process is alive was a
  parameter the production adapter never supplied.
- `dashpot worktree check` assessed a Worktree by its own sequence and
  protected nothing, so it could call removable a checkout that Cleanup
  refuses, and it did not mention the ignored content its remove commands
  delete. The CLI and the dashboard each wrote their own rule for the
  checkouts a Cleanup protects.

## Decision

- **A Branch is in use as Git derives it.** It is in use when any other
  Worktree has it checked out, has a rebase of it in progress
  (`rebase-merge/head-name` or `rebase-apply/head-name` in that Worktree's
  administrative directory), or has a bisect of it in progress
  (`BISECT_START`), including a Branch a `rebase --update-refs` will move
  (`rebase-merge/update-refs`). The `checked-out` blocker's detail names which and
  where, and its command is the one that ends it: `git -C <path> status`
  for a rebase, `git -C <path> bisect reset` for a bisect. The dashboard
  shows the blocker by its detail.
- **The fingerprint is every disclosed fact but named exclusions.** It is
  taken from the whole preview, so a field added later counts by default.
  It excludes a target's `observed_at` (the Repository's last fetch, which
  proves nothing about one remote; what a fetch changed shows in the
  expected commit), a blocker's `detail` and `command` (narration of a
  gate whose kind counts: a blocked target is never performed), and a
  `sub-agent` blocker's session and agents, which the Sub-agent Override
  compares itself with a refusal that names both sets
  ([ADR 0112](0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)).
  A choice the dashboard keeps across a revised preview is kept by the same
  facts.
- **Every displayed command is built from an argument vector.** One helper
  joins the arguments with `shlex.join`, and one more prefixes a
  `cd <path> &&`, so each command a preview, a report or `worktree check`
  names pastes into a POSIX shell as the arguments it shows.
- **One predicate tells an Orphaned Agent Run.** A run is orphaned when its
  recorded Host Process is gone and no relocation is pending; observation,
  `dashpot work` and Cleanup call the same function, each with its own
  liveness probe. Cleanup words a run with a pending relocation as moving,
  names the `codex resume <session-id> -C <target>` that carries a Codex
  run, and offers `dashpot work stop --session` only for an abandoned
  relocation.
- **Text Dashpot did not write is never markup.** The Cleanup report, its
  problem line, tooltips, the notifications that interpolate Git output or
  paths, and the Runtime screen's event cells render as plain text.
- **A Sub-agent Override lifts only the Worktree's own hold.** It frees a
  Branch blocked only because the acknowledged Worktree, which cannot go,
  has it checked out; one function builds that blocker for the preview and
  for the override's comparison. A Branch also in use in another Worktree
  stays blocked
  ([ADR 0112](0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)).
- **The lock holder is probed from the process lookup.** The Worktree
  assessment derives the lock-holder probe from the process lookup it is
  given, so the production adapter probes the host and a test probes its
  fake table, with no separate parameter left unset.
- **`worktree check` is the Cleanup assessment.** It runs the sequence the
  preview runs, with the same protection, then holds the Worktree's Branch
  to the preservation checks its remove commands need. A removable report
  says that those commands also delete the ignored paths inside, and its
  JSON lists them as `ignored`.
- **One owner for protected checkouts.** One function names the checkouts a
  Cleanup never removes: the checkout Dashpot runs from, its Worktree root,
  and each Repository Anchor given, taken at its Worktree root. The
  dashboard gives its Project's anchors and calls it off the event loop;
  the Cleanup commands and `worktree check` give every anchor of the
  Workspace inventory.
- **A stale locked record inside a Worktree names its unlock.** A
  `nested-worktree` blocker for a stale record reads that record's own
  `locked` and `prunable` facts. A locked one gives
  `git worktree unlock <path> && git worktree prune`, since prune leaves a
  locked record alone.

## Considered options

- **Keep a fixed list of fingerprint facts and add integration and
  consequences to it:** rejected. Each new field would again be left out
  until someone noticed, which is how integration state was missed.
- **Fingerprint the blocker details too:** rejected. A pid, a count or an
  age in a detail changes between preview and confirmation without
  changing what may be performed, and every such change would refuse the
  confirmation for nothing.
- **Give the in-use Branch a new blocker kind per Git state:** rejected.
  The person's next step differs by its command, which the detail and
  command already carry, while every caller that gates on `checked-out`
  would have to learn the new kinds. The one caller that must tell them
  apart, the Sub-agent Override, compares the exact blocker instead.

## Consequences

- This amends ADR 0019: its fingerprint now covers every disclosed fact
  but the named exclusions, a Branch being rebased or bisected is in use,
  and the commands it names are shell-quoted.
- The command line's protection widens to the Worktree root of the
  checkout it runs from, whether or not that root carries a Project
  configuration, matching the dashboard.
- `WorktreeRemovability` gains `ignored`, and `dashpot worktree check
  --json` the `ignored` key.
