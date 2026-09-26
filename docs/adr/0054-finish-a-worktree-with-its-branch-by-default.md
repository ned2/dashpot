---
status: accepted
date: 2026-09-26
---

# Finish a Worktree with its Branch by default

Removing a Worktree from the dashboard cost more deliberate steps than the
action warrants, with defaults aimed at the less common outcome. In this
Project every Worktree carries ignored content — its own `.venv` and
`.dashpot/state/` — so the ignored-content acknowledgement
[ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)
requires appeared on essentially every Worktree Cleanup, and ticking it was
unconditional. The attached local Branch started unselected
([ADR 0036](0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md)),
although a Worktree prepared for Issue work and its Branch are normally
finished together. The Branch at the remote was not offered at all, so
finishing the work everywhere took a second `x` on the same Branch in the
Branches pane. A GitHub repository avoids that leftover only with
**Automatically delete head branches**, which is off by default and not a
setting every observer of a Project can change
([#287](https://github.com/ned2/dashpot/issues/287)).

## Decision

The Worktrees pane's Cleanup is the finish-the-work flow. Its preview starts
with the usual intent selected and says plainly what confirming does, instead
of asking for ticks that carry no decision.

- **Ignored content is disclosed, not acknowledged.** The dialog has no
  ignored-content checkbox. The inventory stays in view — the target's
  `Includes N ignored paths and their contents`, the **View ignored paths**
  disclosure, and the confirmation callout — and confirming a selected
  Worktree sends `delete_ignored` explicitly. The domain gate stays:
  confirmation of a Worktree removal without `delete_ignored` is refused, so
  `dashpot worktree remove` still refuses without `--delete-ignored`. A
  command-line caller has no preview in front of it; its flags are its
  disclosure. The preview fingerprint covers the ignored inventory, so content
  that appears between preview and confirmation still refuses as changed.
- **The Worktree preview offers its Branch at its push remote.** Beside the
  attached local Branch, the preview offers the Branch of the same name at the
  remote a plain `git push` of it reaches — Git's order: the Branch's
  `pushRemote`, the Repository's `pushDefault`, the Branch's upstream remote,
  then `origin` — when that remote is configured and has the Remote-Tracking
  Branch. Only that one remote is offered: a Branch at any other remote, such
  as a fork's `upstream`, stays the Branches pane's to delete, and a
  differently named upstream, which may be shared, is never offered. The
  target carries the evidence, blockers, and leased push ADR 0019 already
  gives a remote target, and like the local Branch it requires the Worktree:
  a Worktree that cannot be removed holds both unavailable. Where there is no
  such Remote-Tracking Branch — head branches auto-deleted and pruned by a
  fetch, or never pushed — no target and no line render. The push remote is
  used rather than the upstream because agents here push with an explicit
  `git push origin <branch>`, which configures no upstream.
- **Default selection, on a first preview only.** An available attached local
  Branch starts selected; a person unticks it to retain the Branch. The Branch
  at the push remote starts selected only when it and the local Branch are both
  available and it is at the local Branch's tip, so nothing reached the
  remote that the preview has not accounted for; otherwise it starts
  unticked. The narrower rule is
  deliberate: deleting a Branch at a remote is the one step that changes what
  other people see, and a forge closes an open Pull Request for it. The
  existing `unintegrated` and `unknown-integration` blockers already exclude
  an unmerged Branch. Defaults apply to the first preview alone. A refreshed
  preview keeps choices by ADR 0036's rule — an unchanged target keeps the
  person's choice, a changed or new target starts unticked even when it would
  qualify for a default — and a preview reopened because the state changed
  since confirmation starts with no optional target selected. A Remote Fetch
  never silently re-arms a deletion.
- **A stable button and a prominent recap.** The confirm button reads
  **Remove Worktree** in the Worktree dialog and **Delete Branch** in the
  Branch dialog whatever is selected. What confirming does is stated by an
  alert-styled callout at the end of the dialog's scrolling body, updated as
  choices change, with one line per selected target: the Worktree with its
  ignored-path count and first names, the local Branch, the Branch at the
  remote. It is hidden while confirming would delete nothing, and nothing
  scrolls it into view. Focus opens on the first choice, never on the confirm
  button — on the dialog body when there is no choice — so a stray `Enter`
  after `x` never confirms.
- **A stale block says how to check again.** An `unintegrated` or
  `unknown-integration` blocker judged against a Remote-Tracking Branch adds, on
  the blocked target, that a fetch checks again if the work has since merged.
  Dashpot never fetches on its own
  ([ADR 0014](0014-fetch-remotes-on-explicit-key-press.md)), so a merged Pull
  Request whose squash commit is not yet in the local `origin/main` blocks in
  the safe direction; the hint makes the reason legible without working
  around it.
- **The command line opts in per target.** `dashpot worktree remove` gains
  `--delete-remote-branch` beside `--delete-branch`, independent of it, and
  refuses when the Worktree has no Branch or its Branch has no Remote-Tracking
  Branch at the push remote. No default applies to the command line; a
  different remote remains `dashpot branch delete --remote`.

The Branches pane is unchanged: nothing starts selected there. It is a
general-purpose Branch editor, where no one selection is the usual intent, and
the finish-the-work defaults belong only to the Worktree whose work is being
finished.

## Considered options

- **Remove the ignored-content gate and the `delete_ignored` field outright:**
  rejected. It would also drop `--delete-ignored`, leaving a script or an agent
  one flag short of deleting a Worktree's `.venv` and Work Store without
  saying so.
- **Offer every remote carrying the Branch's name, ticking only one:**
  rejected. A fork's `upstream` in a finish-the-work flow invites a mistake
  without saving a step.
- **Offer only the configured upstream remote:** rejected. Branches pushed
  with an explicit remote carry no upstream, so the choice would never
  appear in this Project's workflow.
- **Re-evaluate the defaults after a refresh:** rejected. A person who
  deselected a target, or a target whose facts moved, must not be re-armed by
  pressing `f`.
- **A confirm label that tracks the selection** (`Remove Worktree and
  Branch`): rejected. A label that changes under the cursor is easy to
  misread; one fixed label and one recap put the selection where it is read.
- **Scroll the callout into view on focus or open:** rejected in favour of
  leaving the scroll with the person; the fixed label still names the primary
  action.
- **Focus the confirm button on open:** rejected; `x` then `Enter` would
  delete a Branch at a remote with no pause.

## Consequences

- This amends ADR 0019: ignored content is disclosed rather than
  acknowledged in the dashboard, not every target starts unselected, and the
  remote-first ordering it reasons "favours the revisable path" now also runs
  from the Worktrees pane, still stopping at a refused or unknown remote
  outcome before the Worktree and local Branch. It amends ADR 0036: the
  attached local Branch starts selected, and a first preview's defaults are
  outside its retention rule, which governs every refresh.
- A Worktree preview may now hold three targets, removed in ADR 0019's
  order: the Branch at the remote, then the Worktree, then the local Branch.
- The confirm button no longer summarises the selection; tests and
  documentation read the callout for it.
