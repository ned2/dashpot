---
status: accepted
date: 2026-10-05
---

# Block removing a Worktree that holds another Worktree

A Cleanup removes a Worktree with an unforced `git worktree remove`, after
its preview has shown every blocker and the ignored content that goes with
it ([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
Two cases let that removal destroy work the preview never named
([#536](https://github.com/ned2/dashpot/issues/536)).

- **A Worktree inside the one being removed.** An unforced
  `git worktree remove` checks only the status of the Worktree it removes,
  then deletes that directory recursively. A linked Worktree registered
  inside it shows in that status at most as an untracked directory, or, when
  its parent directory is ignored, only as an ignored path. Claude Code's
  `EnterWorktree` creates Worktrees under `.claude/worktrees/` inside the
  session's checkout, and Projects ignore `.claude`, so this happens in
  normal use. The inner Worktree's uncommitted work, its Work Store and its
  hook records went with the outer one. Its own dirty, Agent Session and
  Agent Run checks never ran, and Git left its record dangling as prunable
  (verified on Git 2.53). Disclosing `.claude/` as ignored content does not
  show that the Worktree inside it was safe to remove.
- **An ignored-content inventory that obeyed `status.showUntrackedFiles`.**
  Git lists ignored paths only while it collects untracked ones. Under
  `status.showUntrackedFiles=no` the inventory listed nothing, so the
  command line's `--delete-ignored` gate and the dashboard's disclosure both
  disappeared while `.venv` and `.dashpot/state` were still deleted. Under
  `all` it listed every file inside an ignored directory, so a `.pyc`
  written between preview and confirmation changed the fingerprint. An
  inventory Git refused read as no ignored content at all.

## Decision

- **A `nested-worktree` blocker for each Worktree inside.** When another
  registered Worktree of the Repository lies within the Worktree being
  assessed, the assessment gets one `nested-worktree` blocker per such
  Worktree. Each blocker names it, says that removing this Worktree would
  delete it without checking it, and gives `dashpot worktree remove <path>`
  as the command that removes it first; moving it out with
  `git worktree move` is the alternative it names. Git's own registry,
  already read for the preview, is the evidence, so nothing else is
  scanned. The blocker appears in the Cleanup preview, in
  `dashpot worktree check`, and in the re-inspection on confirmation. It is
  a blocker kind, so it is part of the preview's fingerprint: a Worktree
  nested between preview and confirmation refuses the confirmation as
  changed. It is not a `sub-agent` blocker, so a Sub-agent Override never
  lifts it
  ([ADR 0112](0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)).
- **The main Worktree is not assessed for it.** The main Worktree is never
  removable, and Worktrees inside it are an ordinary layout, as for the
  `process` blocker
  ([ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md)).
- **The inventory sets its own untracked collection.** The ignored-content
  inventory runs `git status --ignored=traditional --untracked-files=normal`,
  as the dirty check already does, so a fully ignored directory is one
  entry such as `.venv/` whatever the person's configuration says.
- **A failed inventory blocks.** When Git answers the inventory with a
  non-zero exit, the Worktree gets an `ignored-content` blocker carrying
  Git's reason and `git -C <path> status --ignored` as its command. Failing
  to list ignored content is not finding none. A runner failure, such as a
  timeout, still fails the whole preview, as for every other Git read.

## Considered options

- **Remove nested Worktrees with their parent, after assessing each:**
  rejected. It would make one confirmation reach a Worktree the person did
  not select, against ADR 0019's rule that only selected, concrete targets
  are removed. Removing the inner Worktree first is its own Cleanup with its
  own preview.
- **Rely on the ignored-content disclosure:** rejected. It names a path
  such as `.claude/`, not the Worktree inside it, and none of that
  Worktree's checks run.
- **Force `--untracked-files=all` to name every ignored file:** rejected.
  It makes the preview, its JSON and its fingerprint grow with every file
  in a `.venv`, and any file appearing there refuses the confirmation.
- **Treat a failed inventory as a refusal of the whole preview:** rejected.
  A blocker keeps the rest of the preview, including the Worktree's other
  blockers, in view and names the command to inspect the failure.

## Consequences

- This amends ADR 0019: a Worktree holding another registered Worktree is
  refused, and the ignored-content inventory no longer depends on
  `status.showUntrackedFiles`.
- `BlockerKind` gains `nested-worktree` and `ignored-content`. The dashboard
  shows both by their detail, as it shows every blocker kind without a
  summary of its own.
- A prunable record inside the Worktree also blocks, until
  `git worktree prune` clears it; `dashpot worktree remove` on that path
  names the same command. A stale record is cheap to clear, and removing
  the outer Worktree must not decide on its own that the inner one is gone.
