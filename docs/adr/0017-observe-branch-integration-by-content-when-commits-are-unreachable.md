---
status: accepted
---

# Observe Branch integration by content when commits are unreachable

[ADR 0012](0012-observe-branch-integration-by-reachability.md) defines
`INTEGRATED` by commit reachability from the Integration Branch and accepted
that a squash-merged Branch stays visibly unintegrated until a person reviews
it. On a Repository whose rules force squash merges — this one, and GitHub's
increasingly common default — every merged Branch's commits are unreachable
from `main` forever, so the pane accumulates `↑N` rows for finished work and
a merged Branch is indistinguishable from an unmerged one
([#92](https://github.com/ned2/dashpot/issues/92)). The column's question,
*does the Integration Branch contain this Branch's work?*, is about content;
reachability answers it only for fast-forward and true merges.

Dashpot will keep the exact reachability count and, for a Branch that has
retained commits, ask Git a second exact question about content, without a
fetch and without mutating anything:

- **Merging the tip would change nothing.** `git merge-tree --write-tree`
  merges the Branch onto the Integration Branch's tip in memory. A clean
  merge whose tree equals the Integration Branch's tree means the Branch
  contributes no content; this recognises a recent squash merge in one call.
  A clean merge with a different tree is work that never landed.
- **The squash commit exists.** When the tip merge conflicts — the
  Integration Branch has since changed the same lines — the first-parent
  commits of the Integration Branch since the merge base, committed after
  the Branch's last commit and touching every path the Branch changed, are
  candidates. The one whose tree is exactly what merging the Branch onto its
  parent produces is the squash commit. This needs one `merge-base`, one
  `diff --name-only`, one `log --name-only`, and one `merge-tree` per
  candidate, of which there is usually one.
- The result is a third `INTEGRATED` state, `≡`: the Integration Branch
  holds the Branch's content though its commits are not reachable. `⊆` and
  `↑N` keep their exact meanings; `↑N` now means work the Integration Branch
  does not contain, which is what a reader took it to mean.
- `False` means the content was not found by these two facts, never that it
  is absent from history. A Branch that changes nothing against its merge
  base — empty commits, or work reverted within the Branch — has no content
  to find and stays `↑N`: it is retained commits, not a squash merge. `git cherry` patch equivalence is not used: it
  cannot see a multi-commit Branch squashed into one commit, and GitHub's
  squash differs from the Branch's own diff whenever the Integration Branch
  moved under it, as measured on this Repository.
- Worktree removability reads the same fact. A Worktree whose Branch is
  integrated by content has no `unmerged` or `unpushed` obstacle, and its
  removal command is `git branch -D`, since `-d` refuses a Branch whose
  commits are unreachable.

The per-refresh cost is paid only by Branches with retained commits, which
reachability already identifies. Measured on this Repository (Git 2.53, a
small tree): the tip merge is 8–26 ms per Branch; the squash scan adds about
20 ms for the listing plus 10–20 ms per candidate, bounded by the Branch's
last commit date and by the paths it changed. A Branch that never landed pays
the tip merge and the listing on every refresh.

## Considered options

- **Presentation-only honesty** (a caveat in the legend, a note when the
  upstream is gone): rejected because the number still reads as unmerged
  work, and the pane's usefulness would still depend on Branch deletion
  hygiene the Repository does not enforce.
- **Patch-id equivalence (`git cherry`)**: rejected as above; it covers
  rebases and cherry-picks, not squashes.
- **Issue Source knowledge** (a merged pull request whose head matches the
  Branch): rejected here, as ADR 0012 did, because it imports forge state
  into a Git observation and does not exist for Local Markdown Projects. A
  Pull Requests pane ([#83](https://github.com/ned2/dashpot/issues/83)) may
  show that fact beside this one.
- **Change the meaning of `⊆`** to cover content: rejected; the reachability
  guarantee — deleting the ref loses no commit — is a different fact from
  content presence, and a reader deleting a `≡` Branch should know its
  history goes.

## Consequences

- Each local Branch reports `contentIntegrated` in the headless JSON beside
  `unintegratedCommits`: `true` or `false` when assessed, `null` when there
  was nothing to assess or Git could not answer, which is then a
  `branch-integration` diagnostic.
- The legend gains `≡`, and the domain language's Integration Branch entry
  no longer says a squash remains unintegrated until reviewed.
- ADR 0012's reachability meaning and its Integration Branch selection rule
  are unchanged; its consequence that a squash-merged Branch stays
  unintegrated is superseded by this decision.
- A conflict resolved by hand during a squash merge, or a squash edited
  before landing, produces a tree the Branch cannot reproduce and stays
  `↑N`: the conservative false negative is kept over a false positive.
