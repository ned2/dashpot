---
status: living
date: 2026-09-13
---

# Dashpot development integration

This procedure develops Dashpot itself. It does not configure how other
Projects use Dashpot. The [README contribution sequence](../README.md#contributing)
owns local validation and review; [ADR 0037](adr/0037-review-locally-and-verify-pr-head-before-integration.md)
records the decision to verify before integration.

## Configure required CI

After a PR has demonstrated the `CI required` check, configure it in the
`Protect main` repository ruleset with GitHub Actions as the expected app
(integration ID `15368`). Enable strict up-to-date checks and enforcement on
branch creation. Preserve signed commits, linear history, prevention of force
pushes/deletion, and the existing empty bypass list. Require the exact job
context `CI required`, not a workflow-name prefix. The aggregate explicitly
rejects failed, cancelled, and unexpectedly skipped prerequisites. Documentation-only
PRs still run quality checks and publish the revision artifact, but may skip the
test, build, installation, and minimum-Git jobs after successful classification.
Mixed changes and manual/reusable invocations run full verification. The
[CI performance guide](ci-performance.md) describes the lane and parallel test
execution; the required-check name and artifact checks below are unchanged.

The existing ruleset is `21862853` in `ned2/dashpot`. Read its current content
before any update and retain unrelated or newly added rules. The additional
rule is:

```json
{
  "type": "required_status_checks",
  "parameters": {
    "required_status_checks": [
      {"context": "CI required", "integration_id": 15368}
    ],
    "strict_required_status_checks_policy": true,
    "do_not_enforce_on_create": false
  }
}
```

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
require task authorization for the push; they do not grant lifecycle authority
to arbitrary agent sessions.

1. Establish exclusive ownership of the remote PR branch from final
   verification through the integration push. The implementing agent must
   coordinate with any other writers or automation so none can update that
   branch during this interval. If exclusive ownership cannot be established,
   stop integration. This is a process requirement: GitHub's main ruleset and
   the lease below do not lock the PR branch. A second read of its head is not
   a substitute for ownership.
2. Confirm the PR is open in `ned2/dashpot`, targets `main`, and has the reviewed
   branch as its head. Verify the local coverage evidence and ensure the
   working tree and index contain no uncommitted implementation changes.
3. Identify the latest `ci.yml` **pull_request** run for that PR and head,
   including its latest run attempt. Wait for completion and require both a
   successful run and a successful `CI required` job. A manual or release run
   is not the integration evidence for this procedure.
4. Download that run's `ci-revision-<attempt>` artifact from its successful
   quality job. When only failed jobs were rerun, this artifact can come from
   an earlier attempt of the same run. Check its `GITHUB_RUN_ID`,
   `GITHUB_RUN_ATTEMPT`, `PR_HEAD_SHA`, and `PR_BASE_SHA` against the selected
   run and PR. Record the run URL and commit identities in the PR.
5. Require the recorded head to equal the reviewed local `HEAD`, current PR
   head, CI run head, and `CI required` check run's `head_sha`. Require the
   recorded base to equal current remote
   `main` (read with `git ls-remote origin refs/heads/main`) and be an ancestor
   of that head. Fetch the named refs if needed to verify ancestry locally.
6. With `validated_head` and `validated_base` set to those verified full
   commit IDs, apply the update:

   ```bash
   git merge-base --is-ancestor "$validated_base" "$validated_head" &&
   git push --force-with-lease="refs/heads/main:$validated_base" \
     origin "$validated_head:refs/heads/main"
   ```

   The ancestry check makes this a fast-forward; the explicit lease rejects
   a remote-base change between verification and push. The server's
   non-fast-forward protection remains enabled. Never use an implicit lease,
   disable a protection, or refresh the lease and retry without revalidating.
7. Verify remote `main` equals `validated_head` and the PR is integrated. There
   is no ordinary main-push CI run to wait for. Update the local main checkout
   with an authorized fast-forward when applicable, then finish Issue work.

If head or base changes, stop integration and refresh applicable local
validation, review, and PR CI. A base-update commit must preserve the
repository's signed, linear history; perform a rebase only when authorized.
No force push or merge-conflict resolution is implied by a read-only check.

GitHub normally tests a synthetic PR merge, while attaching PR check runs to
the head commit. This workflow explicitly checks out the head and verifies
its base ancestry, so the signed commit pushed by the procedure is the code
that passed the matrix. The explicit lease closes the base race; exclusive
branch ownership prevents a concurrent PR-head update. Supporting simultaneous
writers would require a different integration contract, such as a GitHub merge
operation with an expected-head guard, and a decision about changed commit
identities and signatures.
Release verification still checks out the release revision through reusable CI.

References: [PR event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request),
[required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[ruleset API](https://docs.github.com/en/rest/repos/rules#update-a-repository-ruleset),
[Git push leases](https://git-scm.com/docs/git-push).
