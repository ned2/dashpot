---
status: accepted
date: 2026-09-13
---

# Anchor the default Worktree Root on the main working tree

[ADR 0011](0011-prepare-issue-worktrees-by-convention.md) gave
`dashpot worktree create` a default Worktree Root of
`<anchor parent>/<anchor name>.worktrees/`, where the Repository Anchor is the
checkout the command runs in. The intent was one pool of Issue Worktrees per
Repository. The rule did not deliver it: an agent dispatched to an Issue
Worktree that prepares the next Issue's Worktree runs the command in a linked
Worktree, and the sibling of *that* checkout is a new
`<linked name>.worktrees/` pool beside it. Observed on 2026-09-13
([#194](https://github.com/ned2/dashpot/issues/194)): the Worktree for #184
was created under `157-explore-….worktrees/`, inside the pool of a Worktree
that will itself be removed. Every resulting Worktree was valid Git, and the
inside-a-Worktree refusal did not fire because a pool *beside* a Worktree is
not inside one.

## Decision

The default Worktree Root is a property of the Git Repository, not of the
checkout the command runs in. `worktree create` derives `default-sibling`
from the Repository's main working tree — the first record of
`git worktree list`, equivalently the parent of `git rev-parse
--git-common-dir` — as `<main parent>/<main name>.worktrees/`. Run from the
main working tree or from any linked Worktree of the same Repository, the
command chooses the same default root.

The Repository Anchor keeps every other role: it supplies the Project
configuration, the Issue Source, and the base. The explicit sources —
`--worktree-root`, `DASHPOT_WORKTREE_ROOT`, and the machine-local
`worktree_root` setting — keep their precedence over the default and are
unchanged. The plan reports the main working tree it derived the default
from (`mainWorktree` in `--json`; the text line reads
`worktree root: … (from default-sibling, beside the main working tree …)`),
so a person running the command from a linked Worktree can see why the root
is not beside them.

## Considered options

- **Refuse a default root whose parent is itself a `*.worktrees` pool.**
  Not adopted. With the main working tree as the anchor, that case arises
  only when the main checkout was cloned into a pool by hand, which is a
  layout to leave alone rather than a nesting the command created. The
  inside-a-Worktree refusal stays as it is.
- **Relocate the Worktrees the old rule nested.** Out of scope; moving a
  Worktree is a Cleanup decision for a person, and the orphaned
  `*.worktrees/` directories a removal leaves behind stay a human action.

## Consequences

- ADR 0011's consequence that a command run from a linked Worktree inside
  the main working tree (Claude Code's `.claude/worktrees/`) must name a root
  explicitly no longer holds: the default is the main working tree's
  sibling, which lies outside every Worktree of the Project.
- The domain language's *Worktree Root* names the main working tree, and
  *Repository Anchor* notes that an anchor may be a linked Worktree.
