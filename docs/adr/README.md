---
status: living
date: 2026-09-26
---

# Architecture decision records

Every architectural decision, by number. An `amended` ADR still holds,
with the change recorded in its own Consequences; a `superseded` one no
longer describes the code.

This index is generated. Run
`uv run python scripts/maintain_docs.py --write-adr-index` after
adding or changing an ADR; the documentation gate fails while it is out
of date.

| ADR | Decision | Status | Resolved by |
| --- | --- | --- | --- |
| 0001 | [Own the Project and Issue model](0001-own-project-and-issue-model.md) | amended | [0003](0003-prefer-project-local-dashpot-state.md) |
| 0002 | [Require complete Issue profile snapshots](0002-require-complete-issue-profile-snapshots.md) | accepted | — |
| 0003 | [Prefer Project-local Dashpot configuration and work state](0003-prefer-project-local-dashpot-state.md) | amended | [0004](0004-observe-one-project-per-run.md) |
| 0004 | [Observe one Project per run](0004-observe-one-project-per-run.md) | accepted | — |
| 0005 | [Observe Branches without fetching](0005-observe-branches-without-fetching.md) | amended | [0008](0008-let-management-commands-mutate-on-explicit-invocation.md), [0014](0014-fetch-remotes-on-explicit-key-press.md) |
| 0006 | [Observe Agent Session activity at turn boundaries](0006-observe-agent-activity-at-turn-boundaries.md) | amended | [0016](0016-hold-a-session-running-while-its-sub-agents-work.md) |
| 0007 | [Identify sandboxed Agent Sessions by Agent Session Identity](0007-identify-sandboxed-sessions-by-agent-session-identity.md) | amended | [0038](0038-isolate-native-agent-session-identities.md) |
| 0008 | [Let named management commands mutate on explicit invocation](0008-let-management-commands-mutate-on-explicit-invocation.md) | amended | [0014](0014-fetch-remotes-on-explicit-key-press.md), [0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md), [0029](0029-preserve-agent-runs-through-declared-codex-relocation.md) |
| 0009 | [Hold one active Agent Run per Agent Session across a Repository's Worktrees](0009-hold-one-agent-run-per-session-across-worktrees.md) | amended | [0029](0029-preserve-agent-runs-through-declared-codex-relocation.md) |
| 0010 | [Derive the Legend from the Glyphs the panes render](0010-derive-the-legend-from-rendered-glyphs.md) | amended | [0040](0040-summarize-integration-across-a-branch-rows-refs.md), [0050](0050-describe-every-pane-column-once-for-the-tooltip-and-the-legend.md) |
| 0011 | [Prepare Issue Worktrees by convention, and only report their removability](0011-prepare-issue-worktrees-by-convention.md) | amended | [0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md), [0039](0039-anchor-the-default-worktree-root-on-the-main-working-tree.md), [0052](0052-read-machine-local-settings-as-toml.md) |
| 0012 | [Observe Branch integration by commit reachability](0012-observe-branch-integration-by-reachability.md) | amended | [0017](0017-observe-branch-integration-by-content-when-commits-are-unreachable.md), [0018](0018-assess-remote-tracking-branch-integration.md), [0040](0040-summarize-integration-across-a-branch-rows-refs.md) |
| 0013 | [Adopt Pydantic models at validating seams, keep dataclasses for trusted values](0013-adopt-pydantic-models-by-seam.md) | amended | [0041](0041-distinguish-github-wire-models-from-configuration.md) |
| 0014 | [Fetch remotes on an explicit key press](0014-fetch-remotes-on-explicit-key-press.md) | accepted | — |
| 0015 | [Reconcile the session's Agent Run at SessionEnd](0015-reconcile-the-agent-run-at-session-end.md) | amended | [0029](0029-preserve-agent-runs-through-declared-codex-relocation.md), [0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md) |
| 0016 | [Hold a session running while its sub-agents work](0016-hold-a-session-running-while-its-sub-agents-work.md) | accepted | — |
| 0017 | [Observe Branch integration by content when commits are unreachable](0017-observe-branch-integration-by-content-when-commits-are-unreachable.md) | amended | [0018](0018-assess-remote-tracking-branch-integration.md), [0040](0040-summarize-integration-across-a-branch-rows-refs.md) |
| 0018 | [Assess Remote-Tracking Branch integration](0018-assess-remote-tracking-branch-integration.md) | amended | [0040](0040-summarize-integration-across-a-branch-rows-refs.md) |
| 0019 | [Remove Branches and Worktrees on explicit confirmation](0019-remove-branches-and-worktrees-on-explicit-confirmation.md) | amended | [0036](0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md), [0054](0054-finish-a-worktree-with-its-branch-by-default.md) |
| 0020 | [Coalesce requests onto the observation in flight](0020-coalesce-requests-onto-the-observation-in-flight.md) | accepted | — |
| 0021 | [Bound each GitHub refresh by a budget](0021-bound-each-github-refresh-by-a-budget.md) | accepted | — |
| 0022 | [Refresh GitHub Issues incrementally between Reconciliations](0022-refresh-github-issues-incrementally-between-reconciliations.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0023 | [Reconcile GitHub Issues by identity in bounded parallel batches](0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0024 | [Build the command line on Cyclopts, with per-command options](0024-build-the-command-line-on-cyclopts.md) | accepted | — |
| 0025 | [Observe Linked Pull Requests from Pull Request changes](0025-observe-linked-pull-requests-from-pull-request-changes.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0026 | [Run fallback sweeps under their own Refresh Budget](0026-run-fallback-sweeps-under-their-own-refresh-budget.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0027 | [Keep the GraphQL change probe authoritative](0027-keep-the-graphql-change-probe-authoritative.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0028 | [Persist GitHub Issue snapshots as untrusted startup seeds](0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0029 | [Preserve Agent Runs through declared Codex relocation](0029-preserve-agent-runs-through-declared-codex-relocation.md) | amended | [0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md) |
| 0030 | [Combine startup evidence with mandatory reads](0030-combine-startup-evidence-with-mandatory-reads.md) | superseded | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0031 | [Observe complete Pull Request lifecycle history](0031-observe-complete-pull-request-lifecycle-history.md) | amended | [0032](0032-submit-pull-request-queries-to-github-advanced-search.md), [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0032 | [Submit Pull Request queries to GitHub advanced search](0032-submit-pull-request-queries-to-github-advanced-search.md) | amended | [0033](0033-query-pages-and-independent-issue-resolution.md) |
| 0033 | [Query pages and independent Issue resolution](0033-query-pages-and-independent-issue-resolution.md) | amended | [0055](0055-verify-the-query-context-in-the-response-that-carries-it.md), [0057](0057-observe-project-totals-in-the-query-page-request.md) |
| 0034 | [Publish an alpha with patch-compatible interfaces](0034-publish-an-alpha-with-patch-compatible-interfaces.md) | accepted | — |
| 0035 | [Open Worktrees on explicit key press](0035-open-worktrees-on-explicit-key-press.md) | accepted | — |
| 0036 | [Keep Cleanup subjects fixed and fetch inside their previews](0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md) | amended | [0054](0054-finish-a-worktree-with-its-branch-by-default.md) |
| 0037 | [Review locally and verify the PR head before integration](0037-review-locally-and-verify-pr-head-before-integration.md) | amended | [0044](0044-integrate-pull-requests-through-a-merge-queue.md), [0045](0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md) |
| 0038 | [Isolate native Agent Session identities](0038-isolate-native-agent-session-identities.md) | accepted | — |
| 0039 | [Anchor the default Worktree Root on the main working tree](0039-anchor-the-default-worktree-root-on-the-main-working-tree.md) | accepted | — |
| 0040 | [Summarize integration across a Branch row's refs](0040-summarize-integration-across-a-branch-rows-refs.md) | amended | [0050](0050-describe-every-pane-column-once-for-the-tooltip-and-the-legend.md) |
| 0041 | [Distinguish GitHub wire models from configuration](0041-distinguish-github-wire-models-from-configuration.md) | accepted | — |
| 0042 | [Group leaf and domain modules into subpackages](0042-group-leaf-and-domain-modules-into-subpackages.md) | accepted | — |
| 0043 | [Retain distinct query and collection adapters](0043-retain-distinct-query-and-collection-adapters.md) | accepted | — |
| 0044 | [Integrate pull requests through a merge queue](0044-integrate-pull-requests-through-a-merge-queue.md) | amended | [0045](0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md) |
| 0045 | [Drop the up-to-date rule where a merge queue is unavailable](0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md) | accepted | — |
| 0046 | [Raise every refusal as a DashpotError subclass](0046-raise-every-refusal-as-a-dashpoterror-subclass.md) | accepted | — |
| 0047 | [Keep the dashboard screen as one Textual adapter](0047-keep-the-dashboard-screen-as-one-textual-adapter.md) | accepted | — |
| 0048 | [Adopt Python 3.13 typing backports on the 3.12 baseline](0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md) | accepted | — |
| 0049 | [Interrupt observation commands at dashboard exit](0049-interrupt-observation-commands-at-dashboard-exit.md) | accepted | — |
| 0050 | [Describe every pane column once for the tooltip and the Legend](0050-describe-every-pane-column-once-for-the-tooltip-and-the-legend.md) | accepted | — |
| 0051 | [Adopt long-lived peer dashboard screens](0051-adopt-long-lived-peer-dashboard-screens.md) | accepted | — |
| 0052 | [Read machine-local settings as TOML](0052-read-machine-local-settings-as-toml.md) | accepted | — |
| 0053 | [Continue an Orphaned Agent Run when its session resumes](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md) | accepted | — |
| 0054 | [Finish a Worktree with its Branch by default](0054-finish-a-worktree-with-its-branch-by-default.md) | accepted | — |
| 0055 | [Verify the query context in the response that carries it](0055-verify-the-query-context-in-the-response-that-carries-it.md) | accepted | — |
| 0056 | [Refresh GitHub queries on their own period](0056-refresh-github-queries-on-their-own-period.md) | accepted | — |
| 0057 | [Observe Project Totals in the Query Page request](0057-observe-project-totals-in-the-query-page-request.md) | accepted | — |
