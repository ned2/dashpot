---
status: living
date: 2026-09-17
---

# Dashpot development integration

This procedure develops Dashpot itself. It does not configure how other
Projects use Dashpot. The [README contribution sequence](../README.md#contributing)
owns local validation and review; [ADR 0037](adr/0037-review-locally-and-verify-pr-head-before-integration.md)
records the decision to verify before integration and
[ADR 0045](adr/0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md)
the decision to integrate on green PR CI without an up-to-date requirement.

## Configure required CI

After a PR has demonstrated the `CI required` check, configure it in the
`Protect main` repository ruleset with GitHub Actions as the expected app
(integration ID `15368`), with enforcement on branch creation. Preserve signed
commits, linear history, prevention of force pushes/deletion, and the existing
empty bypass list. Require the exact job context `CI required`, not a
workflow-name prefix. Do not require branches to be up to date: a merge
queue, which would verify the merged result, is unavailable on this
user-owned repository, and the requirement would only force a rebase and a
full re-run for every PR behind `main`.
The aggregate explicitly rejects failed, cancelled, and unexpectedly skipped
prerequisites. Documentation-only
PRs still run quality checks and publish the revision artifact, but may skip the
test, build, installation, and minimum-Git jobs after successful classification.
Mixed changes and manual/reusable invocations run full verification. The
[CI performance guide](ci-performance.md) describes the lane and parallel test
execution; the required-check name and artifact checks below are unchanged.

The existing ruleset is `21862853` in `ned2/dashpot`. Read its current content
before any update and retain unrelated or newly added rules. The rule this
workflow needs is:

```json
{
  "type": "required_status_checks",
  "parameters": {
    "required_status_checks": [
      {"context": "CI required", "integration_id": 15368}
    ],
    "strict_required_status_checks_policy": false,
    "do_not_enforce_on_create": false
  }
}
```

GitHub offers the `merge_queue` rule only on organization-owned repositories.
If the repository is ever transferred to an organization, a queue would
restore verification of the merged result; that needs the `merge_group`
trigger and candidate handling that [ADR 0044](adr/0044-integrate-pull-requests-through-a-merge-queue.md)
describes, which were removed as unused.

This is a repository administration operation. Reading ruleset metadata or
having account-level admin rights does not prove that a token can update it;
the API needs Administration write permission. Verify the installed rule after
updating it and record the outcome in the implementing Issue. A permissions
failure is an outstanding enforcement step, not successful installation.

Independent agent review is a documented process gate with evidence in the
PR. It is not a GitHub approval by a separate account. No new bot, GitHub App,
or mandatory human approval is introduced by this workflow.

## Integrate a verified PR

Keep the Issue Binding active and work from the Issue Worktree. These steps
require task authorization for merging the PR; they do not grant lifecycle
authority to arbitrary agent sessions.

1. Confirm the PR is open in `ned2/dashpot`, targets `main`, and has the
   reviewed branch as its head. Verify the local coverage evidence and ensure
   the working tree and index contain no uncommitted implementation changes.
2. Identify the latest `ci.yml` **pull_request** run for that PR and head,
   including its latest run attempt. Wait for completion and require both a
   successful run and a successful `CI required` job. Check the run's
   `ci-revision-<attempt>` artifact records the reviewed head as
   `PR_HEAD_SHA`. Record the run URL and commit identities in the PR.
3. Enable auto-merge: `gh pr merge --squash --auto <number>`. GitHub
   squash-merges the PR once every required check on the head is green. A
   new head after that point needs its own validation, review, and CI before
   it merges. The branch need not contain the current `main`: CI verified the
   branch head, and no run exercises `main` itself. A semantic conflict
   between two PRs that each passed on their own therefore surfaces on the
   first later run that contains both, which is the next PR branched from
   the new `main` or a manual dispatch; the
   [agent instructions](../AGENTS.md#independent-review-before-integration)
   say who diagnoses it.
4. Verify the PR is merged and remote `main` carries its squash commit. There
   is no ordinary main-push CI run to wait for. Update the local main checkout
   with an authorized fast-forward when applicable, then finish Issue work.

A textual conflict with `main` blocks merging. Resolve it by the rebase the
[agent instructions](../AGENTS.md#independent-review-before-integration)
authorize, with the focused follow-up review a conflict resolution needs.
Release verification still checks out the release revision through reusable CI.

References: [merge queue availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue),
[required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[ruleset API](https://docs.github.com/en/rest/repos/rules#update-a-repository-ruleset).
