---
status: accepted
date: 2026-10-02
---

# Leave the PR merge to the operator

[ADR 0044](0044-integrate-pull-requests-through-a-merge-queue.md) ended the
implementing agent's authority at queueing its PR with
`gh pr merge --squash --auto`, and
[ADR 0045](0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md),
finding no merge queue on a user-owned repository, kept that command to
enable the squash merge. The agent instructions followed: an agent that
finished its PR enabled auto-merge, and GitHub merged the PR as soon as its
CI went green.

Commit `0193a6d` (2026-09-18) restored the practice from before ADR 0044.
It changed the [agent instructions](../../AGENTS.md#independent-review-before-integration)
alone and recorded no decision, so ADRs 0044 and 0045 went on naming
auto-merge as the agent's last step until
[#276](https://github.com/ned2/dashpot/issues/276) noted the withdrawal in
their text. Meanwhile the README and the integration procedure still told
an agent to enable auto-merge; on
[#273](https://github.com/ned2/dashpot/pull/273) that was caught only before
the command ran.

## Decision

The operator, not the implementing agent, merges a PR. The agent's work ends
with the PR open, its validation section recorded, and CI green. It neither
merges the PR nor enables auto-merge. The operator reviews the PR, checks the
recorded evidence, and squash-merges it, as the
[development integration procedure](../development-integration.md#integrate-a-verified-pr)
sets out.

The merge is the one step that changes remote `main`. Without an up-to-date
rule or a merge queue, a PR merges on its own green `pull_request` run, and
no CI run checks `main` itself afterwards (ADR 0045). The agent's independent review is a repository process gate, not
a GitHub approving review
([ADR 0037](0037-review-locally-and-verify-pr-head-before-integration.md)).
With auto-merge, a green run alone would carry the PR onto `main` with no
person having looked at it. The squash commit carries the PR title and body,
so the operator also reviews what `main` will say about the change. And the
operator, who sees every open PR, chooses the order in which they land.

## Unchanged

- A PR still integrates by squash merge on its own green `pull_request` run,
  with no up-to-date requirement (ADR 0045).
- There is still no merge queue. ADR 0044 describes the queue to reinstate if
  the repository moves to an organization.
- A rebase is still the authorized response to a textual conflict with
  `main`, with focused follow-up review when it resolves conflicts.
- The local review gate, independent review, and exact-head verification of
  the `pull_request` run stand as ADR 0037 records them.

## Consequences

- ADRs 0044 and 0045 are amended by this decision. Their merge-queue and
  up-to-date-rule analysis stands; only the closing instruction to run
  `gh pr merge --squash --auto` is withdrawn.
- A PR waits for the operator after its CI is green. A semantic conflict
  between two such PRs still surfaces on the first later run that contains
  both, as ADR 0045 accepts.
- A head change after the handover, such as a conflict-resolving rebase, is
  made by the operator or by an agent that takes up the Issue work again, and
  needs its own validation, review, and CI before it merges.

This decision concerns developing Dashpot. It adds no rules to the
application or the distributed Issue-work skill about how other Projects
integrate their work.
