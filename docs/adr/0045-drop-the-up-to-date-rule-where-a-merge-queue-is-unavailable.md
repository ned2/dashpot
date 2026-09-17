---
status: accepted
date: 2026-09-17
---

# Drop the up-to-date rule where a merge queue is unavailable

[ADR 0044](0044-integrate-pull-requests-through-a-merge-queue.md) replaced
the `Protect main` ruleset's strict up-to-date requirement with a GitHub
merge queue, so that CI would still run on exactly what lands without every
merge invalidating every other open PR. The workflow half landed in
[#249](https://github.com/ned2/dashpot/pull/249). The operator half could
not: GitHub offers the `merge_queue` rule only on organization-owned
repositories, and `ned2/dashpot` is owned by a user account, so the rule is
absent from both the ruleset editor and the API.

Three paths remained. Transferring the repository to an organization would
make the queue available at the cost of a new owner for the repository and
every link to it. Keeping the strict up-to-date rule would keep the rebase
treadmill that ADR 0044 set out to remove. Dropping the strict rule without a
queue keeps integration unblocked and loses one guarantee: that CI ran on the
merged result before it reached `main`.

The decision is the third. A PR integrates by squash merge on the strength of
its own green `pull_request` run, enabled with `gh pr merge --squash --auto`.
Signatures, linear history, and the `CI required` check stay; the squash
commit GitHub creates is signed and keeps `main` linear whatever the branch
contains. What is given up is narrow: two PRs that each pass on their own but
conflict semantically now surface on `main`'s next run rather than before
merge. Textual conflicts still block the merge and are still resolved by the
authorized rebase with focused follow-up review. For a project of this size
and change rate that exposure is smaller than the cost of the treadmill, and
`main` breaking is visible and cheap to fix forward.

The `merge_group` trigger, the candidate branches of the verified-revision
expressions, and the lane classifier's `merge_group` handling are removed
rather than left inert: a path nothing exercises is a maintenance cost and a
false signal to readers about what the workflow guarantees. The hoisted
workflow-level `PR_HEAD_SHA` and `PR_BASE_SHA` stay, as the single expression
every checkout and the revision record share. ADR 0044's analysis of what the
up-to-date rule protected and its retirement of the routine rebase remain in
force; if the repository is ever transferred to an organization, ADR 0044
describes the queue to reinstate.

This decision concerns developing Dashpot. It adds no rules to the
application or the distributed Issue-work skill about how other Projects
integrate their work.
