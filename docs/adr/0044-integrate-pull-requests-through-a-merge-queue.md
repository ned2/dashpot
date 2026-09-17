---
status: accepted
date: 2026-09-17
---

# Integrate pull requests through a merge queue

[ADR 0037](0037-review-locally-and-verify-pr-head-before-integration.md)
verified the exact PR head before integration and required that head to
contain the current `main`: the `Protect main` ruleset demanded an up-to-date
branch, and the quality job failed a PR whose event base was not an ancestor
of its head. Every merge to `main` therefore invalidated every other open PR,
which had to be rebased and fully re-verified before it could follow. The
2026-09-17 review wave opened four PRs at once
([#247](https://github.com/ned2/dashpot/issues/247)); serial integration of
four independent changes needed ten CI runs instead of four.

Squash merging already gives the ruleset's other guarantees on its own. GitHub
creates and signs the squash commit, so `main` stays linear and signed
whatever the branch contains. The up-to-date rule was the only one that
serialised integration, and what it protects is that CI ran on exactly the
content that lands.

A GitHub merge queue keeps that protection without the rebase treadmill. A PR
enters the queue once its own CI is green. The queue builds a candidate from
the current `main` plus every queued PR, runs the workflow on it under the
`merge_group` event, and squash-merges the PRs whose candidate passed. A PR
whose candidate fails is dropped from the queue and the rest are rebuilt. The
candidate is what lands, so the `merge_group` run is the integration
verification; the `pull_request` run remains the branch's own evidence for
review.

The workflow therefore triggers on `merge_group` as well as `pull_request`,
classifies a candidate's diff for the documentation lane exactly as it
classifies a branch diff, and records the verified head and base for both
events. It no longer refuses a PR because `main` advanced. The `Protect main`
ruleset gains the `merge_queue` rule with squash as its method and drops the
strict up-to-date requirement; signatures, linear history, and the
`CI required` check stay. Enabling the queue before the workflow reports on
`merge_group` runs would stall every merge, so the ruleset change follows the
workflow change and is recorded in
[development integration](../development-integration.md#configure-required-ci).

A rebase is no longer a routine step. It remains the authorised response to a
textual conflict with `main`, and a conflict-resolving rebase still changes the
reviewed diff and needs focused follow-up review. The validated fast-forward
push that ADR 0037 described is retired: integration is a GitHub merge
operation, and the implementing agent's authority ends at queueing the PR
with `gh pr merge --squash --auto`.

This decision concerns developing Dashpot. It adds no rules to the application
or the distributed Issue-work skill about how other Projects integrate their
work.
