---
status: living
date: 2026-09-17
---

# Dashpot development integration

This procedure develops Dashpot itself. It does not configure how other
Projects use Dashpot. The [README contribution sequence](../README.md#contributing)
owns local validation and review; [ADR 0037](adr/0037-review-locally-and-verify-pr-head-before-integration.md)
records the decision to verify before integration and
[ADR 0044](adr/0044-integrate-pull-requests-through-a-merge-queue.md) the
decision to integrate through GitHub's merge queue.

## Configure required CI

After a PR has demonstrated the `CI required` check, configure it in the
`Protect main` repository ruleset with GitHub Actions as the expected app
(integration ID `15368`), with enforcement on branch creation. Preserve signed
commits, linear history, prevention of force pushes/deletion, and the existing
empty bypass list. Require the exact job context `CI required`, not a
workflow-name prefix. Do not require branches to be up to date: the merge
queue below supplies that guarantee on the candidate it builds, and the
requirement would only force a rebase before a PR could enter the queue.
The aggregate explicitly rejects failed, cancelled, and unexpectedly skipped
prerequisites. Documentation-only
PRs still run quality checks and publish the revision artifact, but may skip the
test, build, installation, and minimum-Git jobs after successful classification.
Mixed changes and manual/reusable invocations run full verification. The
[CI performance guide](ci-performance.md) describes the lane and parallel test
execution; the required-check name and artifact checks below are unchanged.

The existing ruleset is `21862853` in `ned2/dashpot`. Read its current content
before any update and retain unrelated or newly added rules. The two rules
this workflow needs are:

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

```json
{
  "type": "merge_queue",
  "parameters": {
    "merge_method": "SQUASH",
    "grouping_strategy": "ALLGREEN",
    "max_entries_to_build": 5,
    "max_entries_to_merge": 5,
    "min_entries_to_merge": 1,
    "min_entries_to_merge_wait_minutes": 5,
    "check_response_timeout_minutes": 60
  }
}
```

Install the `merge_queue` rule only after a workflow that triggers on
`merge_group` has reached `main`; a queue whose candidates never receive the
`CI required` check stalls every merge until its response timeout. The
`grouping_strategy` of `ALLGREEN` merges only the PRs whose shared candidate
passed; a failed candidate removes the failing PR and rebuilds the rest.

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
require task authorization for queueing the PR; they do not grant lifecycle
authority to arbitrary agent sessions.

1. Confirm the PR is open in `ned2/dashpot`, targets `main`, and has the
   reviewed branch as its head. Verify the local coverage evidence and ensure
   the working tree and index contain no uncommitted implementation changes.
2. Identify the latest `ci.yml` **pull_request** run for that PR and head,
   including its latest run attempt. Wait for completion and require both a
   successful run and a successful `CI required` job. Check the run's
   `ci-revision-<attempt>` artifact records the reviewed head as
   `PR_HEAD_SHA`. Record the run URL and commit identities in the PR.
3. Queue the PR: `gh pr merge --squash --auto <number>`. GitHub adds it to the
   merge queue once every required check on the head is green. Do not update
   the branch after queueing; a new head leaves the queue and needs its own
   validation, review, and CI before it can be queued again.
4. The queue builds a candidate from the current `main` and the queued PRs,
   runs `ci.yml` on it under the **merge_group** event, and squash-merges the
   PRs whose candidate passed. Watch the candidate run with
   `gh run list --event merge_group` and `gh run watch <id> --exit-status`.
   The candidate's `ci-revision-<attempt>` artifact records the candidate as
   `PR_HEAD_SHA` and the `main` it was built on as `PR_BASE_SHA`.
5. If the candidate fails, the queue drops the PR and rebuilds the rest.
   Diagnose the failure against the candidate, not the branch: a green
   branch that fails in the queue conflicts semantically with what landed on
   `main` since review. Fix it on the branch, refresh validation and focused
   review, wait for green PR CI, and queue again.
6. Verify the PR is merged and remote `main` carries its squash commit. There
   is no ordinary main-push CI run to wait for. Update the local main checkout
   with an authorized fast-forward when applicable, then finish Issue work.

A textual conflict with `main` blocks queueing. Resolve it by the rebase the
[agent instructions](../AGENTS.md#independent-review-before-integration)
authorize, with the focused follow-up review a conflict resolution needs.
Release verification still checks out the release revision through reusable CI.

References: [merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue),
[merge_group event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#merge_group),
[required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[ruleset API](https://docs.github.com/en/rest/repos/rules#update-a-repository-ruleset).
